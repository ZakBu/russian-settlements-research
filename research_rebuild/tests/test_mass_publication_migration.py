import copy
import unittest

import pandas as pd

from research_rebuild.mass_linkage.migrate_publication_bindings import (
    MigrationError,
    migrate_records,
)


class PublicationBindingMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selected, cls.edges, cls.points, cls.review = cls._fixture()

    @staticmethod
    def _fixture():
        bindings = []
        dispositions = []
        edges = []
        selected = []
        points = []
        point_ids = [f"2021:point:{i:03d}" for i in range(81)]
        for i, sid in enumerate(point_ids):
            selected.append({"source_record_id": sid, "census_year": 2021, "population": 1000 + i})
            points.append({
                "decision_id": f"point-decision-{i:03d}",
                "target_source_record_id": sid,
                "coordinate_source_record_id": sid,
                "selection_projection_status": "active_endpoints_selected",
            })

        for i in range(50):
            old_id = f"2010:old:{i:03d}"
            new_id = f"2010:new:{i:03d}"
            selected.append({"source_record_id": new_id, "census_year": 2010, "population": 2000 + i})
            other_2002 = f"2002:other:{i:03d}"
            selected.append({"source_record_id": other_2002, "census_year": 2002, "population": 3000 + i})
            edge_ids = [f"identity-edge-{i:03d}-a"]
            first_from_id, first_from_year = (other_2002, 2002) if i == 3 else (old_id, 2010)
            first_to_id, first_to_year = (old_id, 2010) if i == 3 else (other_2002, 2002)
            edges.append({
                "decision_id": edge_ids[0], "relation": "same_place",
                "from_source_record_id": first_from_id, "from_year": first_from_year,
                "to_source_record_id": first_to_id, "to_year": first_to_year,
                "decision_status": "accepted_rule", "evidence_uri": f"source:{i}",
                "selection_projection_status": "held_endpoint_not_selected_pending_publication_binding",
            })
            if i < 4:
                edge_ids.append(f"identity-edge-{i:03d}-b")
                edges.append({
                    "decision_id": edge_ids[-1], "relation": "same_place",
                    "from_source_record_id": old_id, "from_year": 2010,
                    "to_source_record_id": point_ids[i], "to_year": 2021,
                    "decision_status": "accepted_rule", "evidence_uri": f"source:{i}:b",
                    "selection_projection_status": "held_endpoint_not_selected_pending_publication_binding",
                })
            bindings.append({
                "old_2010_source_record_id": old_id,
                "replacement_2010_source_record_id": new_id,
                "affected_identity_edge_ids": edge_ids,
                "affected_edge_count": len(edge_ids),
                "verdict": "accept_publication_binding",
                "component": "murmansk",
                "old_source": {"sha256": f"oldhash{i}", "locator": f"oldrow:{i}"},
                "replacement_source": {"sha256": f"newhash{i}", "locator": f"newrow:{i}"},
                "reason": "same-census publication equivalence only; identity unchanged",
            })
            for edge_id in edge_ids:
                dispositions.append({
                    "affected_identity_edge_id": edge_id,
                    "displaced_2010_source_record_id": old_id,
                    "replacement_2010_source_record_id": new_id,
                    "binding_verdict": "accept_publication_binding",
                    "effect": "eligible_to_restore_original_same_place_edge_endpoint",
                    "identity_decision": "preserved unchanged",
                })
        # One already-active edge joins an existing component without changing its year grain.
        edges.append({
            "decision_id": "existing-active-edge", "relation": "same_place",
            "from_source_record_id": "2002:other:000", "from_year": 2002,
            "to_source_record_id": "2021:point:000", "to_year": 2021,
            "decision_status": "accepted_rule", "evidence_uri": "source:active",
            "selection_projection_status": "active_endpoints_selected",
        })
        selected_df = pd.DataFrame(selected)
        review = {
            "review_id": "national_source_selection_r2_publication_binding_review_r1_20260930",
            "verdict": "PASS: accept 50 unique 2010 publication bindings; eligible to restore 54 pre-existing same_place edge records to replacement endpoints.",
            "upstream_manifest_sha256": "reviewed-manifest-hash",
            "binding_summary": {
                "packet_rows": 54, "unique_displaced_2010_endpoints": 50,
                "unique_replacement_2010_endpoints": 50, "accepted_bindings": 50,
                "held": 0, "affected_identity_edges": 54,
            },
            "binding_reviews": bindings,
            "edge_dispositions": dispositions,
        }
        return selected_df, pd.DataFrame(edges), pd.DataFrame(points), review

    def test_replays_review_without_changing_identity_decisions_or_provenance(self):
        original_points = self.points.copy(deep=True)
        bindings, migrated, audit = migrate_records(
            self.edges, self.points, self.selected, self.review
        )
        bindings_again, migrated_again, _ = migrate_records(
            self.edges, self.points, self.selected, self.review
        )
        held_ids = set(self.edges.loc[
            self.edges.selection_projection_status.eq("held_endpoint_not_selected_pending_publication_binding"),
            "decision_id",
        ])
        self.assertEqual(len(bindings), 50)
        self.assertEqual(len(migrated), len(self.edges))
        self.assertEqual(bindings.publication_binding_id.tolist(), bindings_again.publication_binding_id.tolist())
        self.assertEqual(bindings.review_entry_id.tolist(), bindings_again.review_entry_id.tolist())
        self.assertEqual(int(migrated.selection_projection_status.eq(
            "active_after_reviewed_publication_binding_migration").sum()), 54)
        self.assertEqual(set(migrated.decision_id), set(self.edges.decision_id))
        migrated_held = migrated[migrated.decision_id.isin(held_ids)]
        binding_map = {b["old_2010_source_record_id"]: b["replacement_2010_source_record_id"]
                       for b in self.review["binding_reviews"]}
        for row in migrated_held.itertuples(index=False):
            original = self.edges.loc[self.edges.decision_id.eq(row.decision_id)].iloc[0]
            if original.from_year == 2010:
                self.assertEqual(row.original_from_source_record_id, original.from_source_record_id)
                self.assertEqual(row.from_source_record_id, binding_map[original.from_source_record_id])
                self.assertEqual(row.to_source_record_id, original.to_source_record_id)
            else:
                self.assertEqual(row.original_to_source_record_id, original.to_source_record_id)
                self.assertEqual(row.to_source_record_id, binding_map[original.to_source_record_id])
                self.assertEqual(row.from_source_record_id, original.from_source_record_id)
        self.assertEqual(migrated.set_index("decision_id").evidence_uri.to_dict(),
                         self.edges.set_index("decision_id").evidence_uri.to_dict())
        pd.testing.assert_frame_equal(migrated, migrated_again)
        self.assertTrue(migrated.relation.eq("same_place").all())
        self.assertTrue(migrated.migration_scope.dropna().loc[lambda x: x.ne("")].str.contains(
            "identity evidence and decision unchanged").all())
        self.assertEqual(len(self.points), len(original_points))
        pd.testing.assert_frame_equal(self.points, original_points)
        self.assertEqual(audit["counts"]["coordinate_claims_changed"], 0)
        self.assertEqual(audit["graph_invariants"]["same_year_component_collisions"], 0)

    def test_rejects_changed_held_status(self):
        edges = self.edges.copy()
        edges.loc[edges.decision_id.eq("identity-edge-000-a"), "selection_projection_status"] = "active_endpoints_selected"
        with self.assertRaisesRegex(MigrationError, "projection statuses"):
            migrate_records(edges, self.points, self.selected, self.review)

    def test_rejects_binding_without_accepted_review_verdict(self):
        review = copy.deepcopy(self.review)
        review["binding_reviews"][0]["verdict"] = "hold"
        with self.assertRaisesRegex(MigrationError, "not accepted by review"):
            migrate_records(self.edges, self.points, self.selected, review)

    def test_rejects_unselected_replacement_or_dangling_nonmigrated_endpoint(self):
        selected = self.selected[self.selected.source_record_id.ne("2010:new:000")]
        with self.assertRaisesRegex(MigrationError, "absent from current selected observations"):
            migrate_records(self.edges, self.points, selected, self.review)
        edges = self.edges.copy()
        edges.loc[edges.decision_id.eq("identity-edge-001-a"), "to_source_record_id"] = "2002:not-selected"
        with self.assertRaisesRegex(MigrationError, "dangling/nonselected ID"):
            migrate_records(edges, self.points, self.selected, self.review)

    def test_rejects_null_selected_source_record_id(self):
        selected = self.selected.copy()
        selected.loc[selected.index[0], "source_record_id"] = None
        with self.assertRaisesRegex(MigrationError, "null or blank"):
            migrate_records(self.edges, self.points, selected, self.review)

    def test_rejects_non_identity_event_or_wrong_kind_binding_effect(self):
        edges = self.edges.copy()
        edges.loc[edges.decision_id.eq("identity-edge-000-a"), "relation"] = "incorporation_event"
        with self.assertRaisesRegex(MigrationError, "event or non-same_place"):
            migrate_records(edges, self.points, self.selected, self.review)
        review = copy.deepcopy(self.review)
        review["edge_dispositions"][0]["effect"] = "create_new_same_place_decision"
        with self.assertRaisesRegex(MigrationError, "wrong-kind effect"):
            migrate_records(self.edges, self.points, self.selected, review)


if __name__ == "__main__":
    unittest.main()

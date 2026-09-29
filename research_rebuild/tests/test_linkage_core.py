import sys
from pathlib import Path
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_rebuild/linkage"))
from core import (apply_decision_events, coordinate_claims, make_identity_candidates,
                  prepare_observations, rule_coordinate_decisions,
                  reviewer_results_to_events, identity_components, component_lineage)
from build import effective_after_dependency_cascade


class LinkageCoreTests(unittest.TestCase):
    def test_observation_ids_are_2021_independent_and_input_is_immutable(self):
        source = pd.DataFrame([{"source_record_id": "2002:file:7", "census_year": 2002, "population": 10,
                                "settlement_name": "Ёлки", "settlement_type": "село", "region_raw": "Карелия"}])
        original = source.copy(deep=True)
        result = prepare_observations(source)
        pd.testing.assert_frame_equal(source, original)
        self.assertTrue(result.provisional_place_id.iloc[0].startswith("PLACE-"))
        self.assertEqual(result.census_year.iloc[0], 2002)

    def test_candidate_generation_never_accepts_textual_agreement(self):
        source = pd.DataFrame([
            {"source_record_id": "2002:a", "census_year": 2002, "population": 1, "settlement_name": "Ёлки", "settlement_type": "село", "region_raw": "Карелия"},
            {"source_record_id": "2010:a", "census_year": 2010, "population": 2, "settlement_name": "Елки", "settlement_type": "село", "region_raw": "Карелия"},
            {"source_record_id": "2021:a", "census_year": 2021, "population": 3, "settlement_name": "Елки", "settlement_type": "село", "region_raw": "Карелия"},
            {"source_record_id": "2010:b", "census_year": 2010, "population": 4, "settlement_name": "Елки", "settlement_type": "село", "region_raw": "Карелия"},
        ])
        obs = prepare_observations(source)
        candidates = make_identity_candidates(obs)
        self.assertGreater(len(candidates), 0)
        self.assertFalse(candidates.acceptance_allowed.any())
        self.assertIn("conflict", set(candidates.candidate_status))

    def test_only_multisource_corrobation_produces_pending_proposal(self):
        source = pd.DataFrame([{
            "source_record_id": "2021:sample", "census_year": 2021, "population": 100,
            "settlement_name": "Пример", "settlement_type": "село", "region_raw": "Карелия",
            "district_raw": "Район", "municipality_raw": "Сельсовет", "latitude": 62.0, "longitude": 34.0,
            "coordinate_source": "DaData via Tochno 2021 CC BY 4.0", "coordinate_quality": "3",
            "population_scope": "settlement", "source_file": "sample.parquet", "source_row": 1,
            "source_dataset_url": "https://tochno.st/datasets/allsettlements",
        }])
        obs = prepare_observations(source)
        claims = coordinate_claims(obs)
        evidence = pd.DataFrame([{
            "source_record_id": "2021:sample", "wikidata_id": "Q123", "wikidata_match_method": "exact_oktmo_okato_agree",
            "wikidata_match_accepted": True, "wikidata_candidate_name_agrees": True,
            "wikipedia_url_ru": "https://ru.wikipedia.org/wiki/Пример", "wikidata_latitude": 62.001,
            "wikidata_longitude": 34.001, "wikidata_admin_label_ru": "Сельсовет",
        }])
        proposal = rule_coordinate_decisions(obs, claims, evidence)
        self.assertEqual(len(proposal), 1)
        self.assertEqual(proposal.decision_class.iloc[0], "rule")
        self.assertEqual(proposal.decision_status.iloc[0], "pending_blind_validation")
        self.assertEqual(proposal.event_action.iloc[0], "propose")
        self.assertIn("wikidata.org", proposal.evidence_uri.iloc[0])
        self.assertEqual(len(rule_coordinate_decisions(obs, claims, evidence.assign(wikidata_match_method="fuzzy_name"))), 0)

    def test_shared_point_is_quarantined_even_if_only_one_row_has_wikidata(self):
        source = pd.DataFrame([
            {"source_record_id": f"2021:{i}", "census_year": 2021, "population": 1, "settlement_name": f"Пример {i}",
             "settlement_type": "село", "region_raw": "Карелия", "latitude": 62, "longitude": 34,
             "coordinate_source": "DaData", "coordinate_quality": "3", "population_scope": "settlement"}
            for i in (1, 2)
        ])
        obs = prepare_observations(source)
        claims = coordinate_claims(obs)
        evidence = pd.DataFrame([{
            "source_record_id": "2021:1", "wikidata_id": "Q123", "wikidata_match_method": "exact_oktmo_okato_agree",
            "wikidata_match_accepted": True, "wikidata_candidate_name_agrees": True,
            "wikipedia_url_ru": "https://ru.wikipedia.org/wiki/Пример", "wikidata_latitude": 62,
            "wikidata_longitude": 34,
        }])
        self.assertEqual(len(rule_coordinate_decisions(obs, claims, evidence)), 0)

    def test_decision_ledger_supports_apply_then_revoke(self):
        events = pd.DataFrame([
            {"decision_id": "d1", "event_order": 1, "event_action": "apply", "decision_type": "coordinate_admission",
             "observation_id": "o1", "coordinate_claim_id": "c1"},
            {"decision_id": "d2", "event_order": 2, "event_action": "revoke", "decision_type": "coordinate_admission",
             "observation_id": "o1", "coordinate_claim_id": "c1"},
            {"decision_id": "d3", "event_order": 3, "event_action": "apply", "decision_type": "coordinate_admission",
             "observation_id": "o2", "coordinate_claim_id": "c2"},
        ])
        active = apply_decision_events(events)
        self.assertEqual(set(active.decision_id), {"d3"})

    def test_reviewer_verdict_applies_two_edges_without_leaking_prediction(self):
        proposals = pd.DataFrame([
            {"decision_id": f"p{i}", "candidate_id": "chain1", "event_order": 1, "event_action": "propose",
             "decision_type": "identity_link", "relation_type": "same_place", "observation_id": pd.NA,
             "from_observation_id": f"o{i}", "to_observation_id": f"o{i+1}", "coordinate_claim_id": pd.NA,
             "decision_status": "pending_blind_validation", "reviewer": "automated_rule", "reviewed_at": pd.NA,
             "supersedes_decision_id": pd.NA, "rationale": "candidate"}
            for i in (1, 2)
        ])
        key = pd.DataFrame([{"review_key": "r1", "candidate_id": "chain1", "candidate_status": "predicted"}])
        results = pd.DataFrame([{"review_key": "r1", "review_result": "accept", "reason": "sources checked"}])
        events = reviewer_results_to_events(proposals, results, key, "independent-reviewer", 2)
        self.assertEqual(len(events), 2)
        self.assertTrue(events.event_action.eq("apply").all())
        self.assertNotIn("candidate_status", events.columns)
        self.assertTrue(events.decision_status.eq("review_accepted").all())

    def test_component_ids_are_release_derived_and_revoke_splits_them(self):
        nodes = pd.DataFrame([
            {"place_id": "p1", "observation_id": "o1"},
            {"place_id": "p2", "observation_id": "o2"},
            {"place_id": "p3", "observation_id": "o3"},
        ])
        applied = pd.DataFrame([{"decision_id": "a", "event_order": 2, "event_action": "apply",
            "decision_type": "identity_link", "relation_type": "same_place", "observation_id": pd.NA,
            "from_observation_id": "o1", "to_observation_id": "o2", "coordinate_claim_id": pd.NA}])
        first, first_membership = identity_components(nodes, applied, "r1")
        self.assertEqual(first.member_count.max(), 2)
        self.assertEqual(first_membership.place_id.tolist(), ["p1", "p2", "p3"])
        revoked = pd.concat([applied, applied.assign(decision_id="r", event_order=3, event_action="revoke")])
        effective = apply_decision_events(revoked)
        second, _ = identity_components(nodes, effective, "r2")
        self.assertTrue(second.member_count.eq(1).all())
        lineage = component_lineage(first, second)
        self.assertEqual(lineage.overlap_node_count.sum(), 3)
        self.assertTrue(lineage.lineage_relation.str.contains("pending_manual_alias_decision").all())

    def test_only_same_place_edges_join_components(self):
        nodes = pd.DataFrame([{"place_id": "p1", "observation_id": "o1"},
                              {"place_id": "p2", "observation_id": "o2"}])
        inclusion = pd.DataFrame([{"decision_id": "inc", "event_order": 1, "event_action": "apply",
            "decision_type": "identity_link", "relation_type": "incorporation", "observation_id": pd.NA,
            "from_observation_id": "o1", "to_observation_id": "o2", "coordinate_claim_id": pd.NA}])
        components, _ = identity_components(nodes, inclusion, "release")
        self.assertEqual(len(components), 2)

    def test_revocation_cascade_follows_only_the_required_identity_path(self):
        events = pd.DataFrame([
            {"decision_id": "i1", "event_order": 1, "event_action": "apply", "decision_type": "identity_link",
             "relation_type": "same_place", "observation_id": pd.NA, "from_observation_id": "o1",
             "to_observation_id": "o2", "coordinate_claim_id": pd.NA},
            {"decision_id": "i2", "event_order": 1, "event_action": "apply", "decision_type": "identity_link",
             "relation_type": "same_place", "observation_id": pd.NA, "from_observation_id": "o2",
             "to_observation_id": "o3", "coordinate_claim_id": pd.NA},
            {"decision_id": "c2002", "event_order": 2, "event_action": "apply", "decision_type": "coordinate_admission",
             "observation_id": "o1", "coordinate_claim_id": "historic-2002", "decision_class": "inferred_continuity",
             "depends_on_identity_decision_ids": '["i1", "i2"]'},
            {"decision_id": "c2010", "event_order": 3, "event_action": "apply", "decision_type": "coordinate_admission",
             "observation_id": "o2", "coordinate_claim_id": "historic-2010", "decision_class": "inferred_continuity",
             "depends_on_identity_decision_ids": '["i2"]'},
            {"decision_id": "c2021", "event_order": 4, "event_action": "apply", "decision_type": "coordinate_admission",
             "observation_id": "o3", "coordinate_claim_id": "current-2021", "decision_class": "rule",
             "depends_on_identity_decision_ids": "[]"},
        ])
        before = effective_after_dependency_cascade(events)
        self.assertEqual(set(before.coordinate_claim_id.dropna()), {"historic-2002", "historic-2010", "current-2021"})
        revocation = events.iloc[0].to_dict()
        revocation.update({"decision_id": "i1-revoke", "event_order": 4, "event_action": "revoke"})
        after_i1 = effective_after_dependency_cascade(pd.concat([events, pd.DataFrame([revocation])], ignore_index=True))
        self.assertEqual(set(after_i1.coordinate_claim_id.dropna()), {"historic-2010", "current-2021"})
        revocation_i2 = events.iloc[1].to_dict()
        revocation_i2.update({"decision_id": "i2-revoke", "event_order": 5, "event_action": "revoke"})
        after_i2 = effective_after_dependency_cascade(pd.concat([events, pd.DataFrame([revocation_i2])], ignore_index=True))
        self.assertEqual(set(after_i2.coordinate_claim_id.dropna()), {"current-2021"})


if __name__ == "__main__":
    unittest.main()

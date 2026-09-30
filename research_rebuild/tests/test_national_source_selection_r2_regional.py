import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research_rebuild.linkage.build_national_source_selection_r2_regional import (
    NW_DIR, ARK_DIR, R1, R5B, build,
)


class NationalSourceSelectionR2RegionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="settlement-source-r2-")
        cls.output = Path(cls.tmp.name) / "release"
        cls.manifest = build(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exact_selected_ids_deltas_scopes_and_null_semantics(self):
        selected = pd.read_parquet(self.output / "selected_observations.parquet")
        r1 = pd.read_parquet(R1 / "selected_observations.parquet")
        self.assertFalse(selected.source_record_id.astype(str).duplicated().any())
        expected = {2002: (158072, 145155005), 2010: (152314, 142202712), 2021: (155414, 147182123)}
        for year, (count, pop) in expected.items():
            y = selected[selected.census_year.eq(year)]
            self.assertEqual((len(y), int(y.population.sum())), (count, pop))
            oldids = set(r1.loc[r1.census_year.eq(year), "source_record_id"].astype(str))
            newids = set(y.source_record_id.astype(str))
            if year != 2010:
                self.assertEqual(oldids, newids)
        old10 = r1[(r1.census_year.eq(2010)) & r1.region_norm.isin(["мурманская", "калининградская", "архангельская", "ненецкий"])]
        new_ids = set(pd.read_csv(NW_DIR / "murmansk_2010_primary_population_selection_proposal.csv").candidate_source_record_id.astype(str))
        new_ids |= set(pd.read_csv(NW_DIR / "kaliningrad_2010_primary_population_selection_proposal.csv").candidate_source_record_id.astype(str))
        new_ids |= set(pd.read_csv(ARK_DIR / "arkhangelsk_2010_primary_selection_component.csv").source_record_id.astype(str))
        before_ids = set(r1.loc[r1.census_year.eq(2010), "source_record_id"].astype(str))
        expected_2010 = (before_ids - set(old10.source_record_id.astype(str))) | new_ids
        actual_2010 = set(selected.loc[selected.census_year.eq(2010), "source_record_id"].astype(str))
        self.assertEqual(actual_2010, expected_2010)
        y10 = selected[selected.census_year.eq(2010)]
        self.assertEqual(int(y10.population.isna().sum()), 1)
        self.assertIn("ARK2010:archive20131022:html_table1_tr4365", set(y10.source_record_id.astype(str)))
        self.assertTrue(pd.isna(y10.loc[y10.source_record_id.eq("ARK2010:archive20131022:html_table1_tr4365"), "population"].iloc[0]))
        self.assertEqual(len(y10[y10.region_norm.eq("мурманская")]), 140)
        self.assertEqual(len(y10[y10.region_norm.eq("калининградская")]), 1099)
        self.assertEqual(len(y10[y10.region_norm.isin(["архангельская", "ненецкий"])]), 4004)
        self.assertEqual(int(y10.loc[y10.region_norm.eq("архангельская"), "population"].sum()), 1185536)
        self.assertEqual(int(y10.loc[y10.region_norm.eq("ненецкий"), "population"].sum()), 42090)

    def test_immutable_archive_and_claim_projection_do_not_activate_stale_ids(self):
        selected = pd.read_parquet(self.output / "selected_observations.parquet")
        ids = set(selected.source_record_id.astype(str))
        archive = pd.read_csv(self.output / "archived_source_observations.csv")
        self.assertFalse(archive.source_record_id.astype(str).duplicated().any())
        # This includes 799 original Karelia 2010 observations superseded in R1,
        # the earlier Moscow aggregate, and all three newly replaced region slices.
        self.assertEqual(len(archive), 6042)
        self.assertEqual(int(archive.census_year.eq(2010).sum()), 6041)
        self.assertEqual(len(set(archive.source_record_id.astype(str)) & ids), 0)
        edges = pd.read_csv(self.output / "identity_edge_selection_projection.csv")
        active = edges.selection_projection_status.eq("active_endpoints_selected")
        self.assertTrue(edges.loc[active, "from_source_record_id"].astype(str).isin(ids).all())
        self.assertTrue(edges.loc[active, "to_source_record_id"].astype(str).isin(ids).all())
        self.assertEqual(int(active.sum()), 1108)
        self.assertEqual(int((~active).sum()), 54)
        self.assertEqual(int((~active).sum()), int(self.manifest["identity_claims"]["held_due_to_displaced_or_unselected_endpoint"]))
        # The scientific decision ledger is unchanged and all displaced links remain present as held rows.
        original_edges = pd.read_csv(R5B / "identity_edges_accepted.csv")
        self.assertEqual(len(edges), len(original_edges))
        self.assertEqual(set(edges.decision_id), set(original_edges.decision_id))
        coords = pd.read_csv(self.output / "coordinate_claim_selection_projection.csv")
        self.assertEqual(len(coords), 81)
        self.assertEqual(int(coords.selection_projection_status.eq("active_endpoints_selected").sum()), 81)
        packet = pd.read_csv(self.output / "affected_identity_edges_publication_binding_review_packet.csv")
        self.assertEqual(packet.affected_decision_id.nunique(), 54)
        self.assertEqual(packet.displaced_2010_source_record_id.nunique(), 50)
        strict_packet = packet[packet.candidate_binding_status.eq("strict_unique_name_type_population_candidate_pending_independent_binding_review")]
        self.assertEqual(strict_packet.displaced_2010_source_record_id.nunique(), 50)
        self.assertTrue((strict_packet.new_region_norm == strict_packet.old_region).all())
        self.assertEqual(int(packet.candidate_binding_status.eq("no_predecessor_mapping_candidate_found_pending_review").sum()), 0)
        ark_city = packet[packet.displaced_2010_source_record_id.eq("2010:pub-11-1-4.pdf:pdf_page_1:48")]
        self.assertEqual(set(ark_city.published_reference_id.dropna()), {"ROSSTAT2010:T5:p58:l12"})
        self.assertTrue(packet.loc[packet.new_source_record_id.notna(), "new_source_sha256"].notna().all())
        self.assertTrue(packet.loc[packet.new_source_record_id.notna(), "old_source_sha256"].notna().all())

    def test_migration_candidates_are_not_acceptances_and_exclude_dash_only_equality(self):
        candidates = pd.read_csv(self.output / "publication_binding_migration_candidates_pending_review.csv")
        self.assertEqual(len(candidates), 10811)
        self.assertEqual(set(candidates.decision_status), {"not_admitted_pending_independent_review"})
        self.assertFalse(candidates.candidate_binding_status.str.startswith("strict").isna().any())
        dash = candidates.candidate_binding_status.eq("unique_key_zero_derived_from_raw_dash_population_not_binding_proof")
        self.assertGreater(int(dash.sum()), 0)
        # Any strict proposal has unique 1:1 endpoints, exact normalized name/type and equal observed P.
        strict = candidates[candidates.candidate_binding_status.eq("strict_unique_name_type_population_candidate_pending_independent_binding_review")]
        self.assertGreater(len(strict), 0)
        self.assertTrue((strict.new_name == strict.old_name).all())
        self.assertTrue((strict.new_type == strict.old_type).all())
        self.assertTrue((strict.new_population.astype(int) == strict.old_population.astype(int)).all())
        self.assertTrue(strict.new_source_sha256.notna().all())
        self.assertTrue(strict.old_source_record_id.notna().all())

    def test_annual_controls_and_output_hashes_are_recorded(self):
        m = json.loads((self.output / "release_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["annual_controls"]["2010"]["known_population_delta"], 30674)
        self.assertEqual(m["annual_controls"]["2010"]["row_delta"], 1)
        self.assertEqual(m["annual_controls"]["2002"]["known_population_delta"], 0)
        self.assertEqual(m["annual_controls"]["2021"]["known_population_delta"], 0)
        self.assertEqual(m["binding_migration"]["accepted"], 0)
        for name, rec in m["outputs"].items():
            self.assertTrue((self.output / name).is_file())
            self.assertEqual((self.output / name).stat().st_size, rec["bytes"])


if __name__ == "__main__":
    unittest.main()

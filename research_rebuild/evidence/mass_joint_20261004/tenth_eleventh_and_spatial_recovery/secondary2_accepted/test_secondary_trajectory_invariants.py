"""Two required regressions for the scoped secondary trajectory layer."""
import pathlib
import unittest
import pandas as pd

OUT = pathlib.Path(__file__).parent

class SecondaryTrajectoryInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.obs = pd.read_parquet(OUT / "scoped_trajectory_observations.parquet")
        cls.edges = pd.read_parquet(OUT / "accepted_scoped_physical_continuity_edges.parquet")

    def test_year_precision_stays_year_only(self):
        secondary = self.obs[self.obs.observation_source_class == "secondary_dated_wikidata_P1082"]
        self.assertEqual(len(secondary), 2)
        self.assertEqual(set(secondary.observation_year), {2021})
        self.assertEqual(set(secondary.observation_year_precision), {"year_only_P585_precision_9"})
        self.assertTrue(secondary.P585_precision.astype(int).eq(9).all())
        self.assertEqual(set(secondary.P585_raw), {"+2021-00-00T00:00:00Z"})

    def test_secondary_rows_never_promote_or_add_to_national_2021(self):
        secondary = self.obs[self.obs.observation_source_class == "secondary_dated_wikidata_P1082"]
        self.assertTrue(secondary.population_source_status.eq("secondary_wikidata_claim_only").all())
        self.assertTrue(secondary.national_2021_additive.eq(False).all())
        self.assertTrue(secondary.native_2021_binding.eq(False).all())
        self.assertTrue(secondary.source_record_id.isna().all())
        self.assertEqual(len(self.edges), 4)
        self.assertTrue(self.edges.decision_status.eq("accepted_scoped_physical_continuity").all())
        self.assertTrue(self.edges.population_scope_comparability_asserted.eq(False).all())

if __name__ == "__main__":
    unittest.main()

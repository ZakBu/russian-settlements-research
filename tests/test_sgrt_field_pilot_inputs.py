import unittest

import numpy as np
import pandas as pd

from scripts.sgrt_field_pilot.input_inventory import prepare


def source_frame():
    return pd.DataFrame([
        dict(root=f"r{i}", source_record_id=f"s{i}", name=f"place{i}", region="r", district="d",
             lat=55., lon=40., population_2021=pop, credit_2021=credit,
             budget_population_credit=credit, ordinary_spatial_2021=True,
             analysis_origin=True, population_role="ordinary_settlement_record",
             accepted_point_present=True)
        for i, (pop, credit) in enumerate([(100., True), (0., True), (50., False), (0., False), (np.nan, True)])
    ])


class PopulationAccountingTest(unittest.TestCase):
    def test_uncredited_publication_is_not_zero_or_missing_source_value(self):
        reference = source_frame()
        endpoints = pd.DataFrame([dict(source_record_id="s0", road_node_index=1,
            snap_km=.5, road_endpoint_accepted=True, verified_component_id=1,
            verified_component_node_count=100)])
        got = prepare(reference, endpoints).set_index("source_record_id")
        self.assertEqual(len(got), 5)
        self.assertEqual(got.loc["s0", "mass_2021"], 100)
        self.assertEqual(got.loc["s1", "mass_2021"], 0)
        self.assertEqual(got.loc["s2", "population_2021"], 50)
        self.assertTrue(pd.isna(got.loc["s2", "mass_2021"]))
        self.assertEqual(got.loc["s2", "mass_status"], "published_value_not_credited")
        self.assertEqual(got.loc["s3", "mass_status"], "published_value_not_credited")
        self.assertEqual(got.loc["s4", "mass_status"], "unknown_or_invalid_population")
        self.assertEqual(got.loc["s0", "connector_minutes"], 2)
        self.assertFalse(got.loc["s1", "routable"])

    def test_current_identity_duplication_rejected_before_mass_sum(self):
        reference = source_frame()
        reference.loc[1, "source_record_id"] = "s0"
        with self.assertRaisesRegex(ValueError, "Current reference IDs"):
            prepare(reference, pd.DataFrame())

    def test_nonadditive_context_is_not_reintroduced_as_a_source(self):
        reference = source_frame()
        reference.loc[0, "ordinary_spatial_2021"] = False
        reference.loc[0, "population_role"] = "external_context_nonadditive"
        endpoints = pd.DataFrame(columns=["source_record_id", "road_node_index", "snap_km",
            "road_endpoint_accepted", "verified_component_id", "verified_component_node_count"])
        got = prepare(reference, endpoints)
        self.assertNotIn("s0", got.source_record_id.tolist())
        self.assertEqual(got.mass_2021.sum(), 0)


if __name__ == "__main__":
    unittest.main()

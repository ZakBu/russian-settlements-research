import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.build_official_primary_scoped_trajectories_20261004 import (
    DEFAULT_SELECTED,
    STAGE,
    _validate_stage,
    build_records,
)


class ScopedOfficialTrajectoryTests(unittest.TestCase):
    def test_full_three_place_projection_and_root_interop_fields(self):
        summary, tables = build_records(STAGE, DEFAULT_SELECTED)
        rows = tables["accepted_scoped_trajectory_projection.csv"]
        self.assertEqual(len(rows), 9)
        self.assertEqual(summary["full_trajectory_population_sums"], {"2002": 72341, "2010": 68658, "2021": 75000})
        self.assertEqual({(r["place"], r["census_year"]) for r in rows}, {
            (place, year) for place in ["Кущевская", "Калининец", "Трудовое"] for year in [2002, 2010, 2021]
        })
        for r in rows:
            self.assertEqual(r["source_record_id"], r["primary_source_record_id"])
            self.assertEqual(r["population"], r["population_value"])
            self.assertTrue(r["current_2021_source_record_id"])
            self.assertIn("latitude", r)
            self.assertIn("longitude", r)
            self.assertFalse(r["population_boundary_comparability_asserted"])
            self.assertFalse(r["historical_coordinate_asserted"])
            self.assertFalse(r["historical_provider_binding_asserted"])
        # Distinct protected/selected counterparts remain discoverable for the
        # official rows without replacing those selected observations.
        by_id = {r["source_record_id"]: r for r in rows}
        self.assertEqual(by_id["ROSSTAT2002:T4:01-04:r1212"]["preferred_same_census_alternate_selected_source_record_id"],
                         "2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:3723")
        self.assertEqual(by_id["ROSSTAT2010:T5:p36:l82"]["preferred_same_census_alternate_selected_source_record_id"],
                         "2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11238")
        self.assertEqual(by_id["ROSSTAT2010:T5:p199:l277"]["preferred_same_census_alternate_selected_source_record_id"],
                         "2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:565")
        self.assertEqual(by_id["ROSSTAT2010:T5:p79:l18"]["preferred_same_census_alternate_selected_source_record_id"],
                         "ROSSTAT2010:T5:p79:l18")
        self.assertEqual(by_id["ROSSTAT2010:T5:p79:l18"]["same_census_source_alias_record_ids"],
                         '["ROSSTAT2010:T5:p79:l76"]')

    def test_vlasikha_is_separate_two_year_display_and_kalininets_qid_unresolved(self):
        summary, tables = build_records(STAGE, DEFAULT_SELECTED)
        vlas = tables["vlasikha_two_year_display_only.csv"]
        self.assertEqual([r["year"] for r in vlas], [2010, 2021])
        self.assertTrue(all(r["no_2002_observation_claimed"] for r in vlas))
        self.assertFalse(summary["vlasikha_2002_observation_claimed"])
        self.assertIn("unresolved", summary["kalininets_qid_native_binding"])

    def test_six_adjacent_links_use_only_the_three_full_paths(self):
        _, tables = build_records(STAGE, DEFAULT_SELECTED)
        edges = tables["accepted_scoped_continuity_links.csv"]
        self.assertEqual(len(edges), 6)
        self.assertEqual({(e["place"], int(e["from_year"]), int(e["to_year"])) for e in edges}, {
            (p, 2002, 2010) for p in ["Кущевская", "Калининец", "Трудовое"]
        } | {
            (p, 2010, 2021) for p in ["Кущевская", "Калининец", "Трудовое"]
        })
        self.assertTrue(all(e["scoped_layer_only"] and not e["graph_mutation_performed"] for e in edges))

    def test_kush_parts_are_exclusive_and_all_ids_listed_as_excluded(self):
        summary, tables = build_records(STAGE, DEFAULT_SELECTED)
        parts = tables["exclusive_partition_policy.csv"]
        self.assertEqual(sum(int(r["child_population_value"]) for r in parts), 29533)
        self.assertTrue(all(r["child_counted_in_addition_to_parent"] == "False" for r in parts))
        self.assertEqual(set(summary["excluded_partition_source_record_ids"]), {r["child_source_record_id"] for r in parts})

    def test_stage_mutation_fails_frozen_checksum(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "stage"
            shutil.copytree(STAGE, d)
            with (d / "scoped_continuity_links.csv").open("a", encoding="utf-8") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                _validate_stage(d)


if __name__ == "__main__":
    unittest.main()

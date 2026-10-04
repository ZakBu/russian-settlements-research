import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_ukraine2001_to_2014_temporal_rule as stage


class TemporalRuleTests(unittest.TestCase):
    def test_name_normalization_is_explicit_not_fuzzy(self):
        self.assertEqual(stage.normalize_name("Старий Крим"), ("старыйкрым", "explicit_Ukrainian_Russian_place_name_alias"))
        self.assertEqual(stage.normalize_name("Курпати"), ("курпаты", "explicit_Ukrainian_Russian_place_name_alias"))
        self.assertNotEqual(stage.normalize_name("Новый Крым")[0], stage.normalize_name("Старый Крым")[0])

    def test_rule_holds_when_a_required_competitor_or_event_guard_fails(self):
        passed = {"typed_name_unique": True, "no_move_event": True}
        self.assertEqual(stage.evaluate_rule(passed)[0], "eligible_for_fixed_independent_review")
        status, holds = stage.evaluate_rule({"typed_name_unique": False, "no_move_event": True})
        self.assertEqual(status, "held_not_rule_admissible")
        self.assertEqual(holds, ["typed_name_unique"])
        status, holds = stage.evaluate_rule({"typed_name_unique": True, "no_move_event": False})
        self.assertEqual(status, "held_not_rule_admissible")
        self.assertEqual(holds, ["no_move_event"])

    def test_full_source_vector_is_candidate_only_and_keeps_measurement_limits(self):
        rules, edges, point_uses, paths, risk, aux = stage.build_packet()
        self.assertEqual(len(rules), 27)
        self.assertEqual(int(rules.candidate_status.eq("eligible_for_fixed_independent_review").sum()), 27)
        self.assertEqual(int(rules.name_normalization_class.eq("explicit_Ukrainian_Russian_place_name_alias").sum()), 2)
        self.assertEqual(int(rules.current_event_flags_raw.eq("P571").sum()), 8)
        self.assertTrue(edges.decision_status.eq("candidate_for_independent_fixed_risk_review_not_admitted").all())
        self.assertFalse(edges.native_code_binding_asserted.any())
        self.assertFalse(edges.current_QID_binding_asserted.any())
        self.assertFalse(rules.population_boundary_comparability_asserted.any())
        self.assertFalse(rules.historical_coordinate_measurement_claimed.any())
        self.assertTrue(point_uses.historical_measurement_claimed.eq(False).all())
        self.assertTrue(point_uses.historical_provider_binding_asserted.eq(False).all())
        self.assertTrue(paths.full_same_place_path_admitted.eq(False).all())
        self.assertTrue(risk.source_record_id_2001.isin(rules.source_record_id_2001).all())
        self.assertTrue(aux["origin_hashes"])

    def test_table5_population_replays_total_column(self):
        universe = stage.read_2001_universe()
        obs = stage.read_csv(stage.PINS["ukraine2001_reviewed_source_rows"][0])
        first = obs.iloc[0]
        raw = [x for x in universe if x["row"] == int(first.official_row_1based)]
        self.assertEqual(len(raw), 1)
        self.assertEqual(int(float(raw[0]["population"])), int(first.population_raw_table5))


if __name__ == "__main__":
    unittest.main()

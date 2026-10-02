import json
import unittest

import pandas as pd

from research_rebuild.mass_linkage.candidates import (
    CandidateError,
    build_candidate_ledger,
)


class MassCandidateLedgerTests(unittest.TestCase):
    @staticmethod
    def _inputs():
        rows = []

        def add(sid, year, name, typ, region="region_a", district="district_a", *, pop=100,
                scope="settlement", grain="atomic_physical_settlement", quality="direct_value",
                raw=None, okato="001", oktmo="0001"):
            rows.append({
                "source_record_id": sid, "census_year": year,
                "source_file": f"{year}_source.pdf", "source_path": f"data/{year}_source.pdf",
                "source_sheet": "table1", "source_row": len(rows) + 1,
                "source_native_id": f"native:{sid}", "source_sha256": f"sha:{year}",
                "source_locator": f"page:row:{len(rows) + 1}", "extraction_version": f"extractor-{year}",
                "source_selection_component": "test", "source_name_raw": raw or name,
                "settlement_name": name, "settlement_type": typ, "region_raw": region,
                "district_raw": district, "municipality_raw": None, "region_norm": region,
                "district_norm": district, "name_norm": name, "type_norm": typ,
                "okato": okato, "oktmo": oktmo, "fias_id": "fias-raw", "source_population_raw": str(pop) if pop is not None else "—",
                "population": pop, "population_value_quality": quality, "population_scope": scope,
                "is_additive_settlement_record": True, "analysis_population_additive": True,
                "entity_grain_status": grain,
            })

        add("02-alpha", 2002, "Alpha", "город", district="D1", pop=50000, raw="Сырой Альфа")
        add("10-alpha", 2010, "Alpha", "город", district="D1", pop=51000, quality="confidentiality_perturbed_within_ten", okato="00002", oktmo="00002")
        add("21-alpha", 2021, "Alpha", "пгт", district="D1", pop=52000)
        add("02-beta-a", 2002, "Beta", "деревня", district=None, pop=300)
        add("02-beta-b", 2002, "Beta", "деревня", district=None, pop=301)
        add("10-beta", 2010, "Beta", "деревня", district="D2", pop=None, scope="settlement_population_2010_census_date", quality="reviewed_primary_source_value_or_null")
        add("21-beta", 2021, "Beta", "деревня", district="D2", pop=305)
        add("02-cross", 2002, "Cross", "деревня", region="region_a", district="D3")
        add("10-cross", 2010, "Cross", "деревня", region="region_b", district="D4")
        add("21-cross", 2021, "Cross", "деревня", region="region_b", district="D4")
        add("02-shift", 2002, "Shift", "город", region="region_a", district="D5")
        add("10-shift", 2010, "Shift", "пгт", region="region_a", district="D5")
        add("21-shift", 2021, "Shift", "пгт", region="region_a", district="D5")
        add("02-moscow-aggregate", 2002, "Москва", "город", region="region_moscow", district=None,
            scope="federal_city_region", grain="federal_city_aggregate")
        add("10-moscow", 2010, "Москва", "город", region="region_moscow", district=None)
        selected = pd.DataFrame(rows)
        legacy = pd.DataFrame([
            {"source_record_id": "10-alpha", "identity_status": "quarantined", "identity_reasons": "admin conflict",
             "quality_flag": "auto_high_admin_mismatch:entity_year_collision", "entity_year_record_count": 2,
             "match_method": "legacy_ordinal_route", "matched_to_source_record_id": "02-alpha",
             "match_score": 1.0, "accepted": True, "is_territorial_aggregate": False,
             "population": 50999, "source_file": "legacy.csv", "source_sheet": "Sheet1", "source_row": 2,
             "source_name_raw": "Alpha old", "settlement_name": "Alpha", "settlement_type": "город",
             "region_raw": "region_a", "district_raw": "D1", "region_norm": "region_a", "district_norm": "D1",
             "name_norm": "Alpha", "type_norm": "город", "okato": "legacy-okato", "oktmo": "legacy-oktmo"}
        ])
        return selected, legacy

    def test_exact_variants_and_change_screens_remain_candidates_only(self):
        selected, legacy = self._inputs()
        ledger, sample, audit = build_candidate_ledger(selected, legacy)
        base = ledger[(ledger.candidate_family.eq("region_name_type")) &
                      (ledger.year_pair.eq("2002-2010")) &
                      (ledger.from_source_record_id.eq("02-alpha"))]
        self.assertEqual(len(base), 1)
        self.assertEqual(base.iloc[0].to_source_record_id, "10-alpha")
        district = ledger[(ledger.candidate_family.eq("region_district_name_type")) &
                          (ledger.year_pair.eq("2002-2010")) &
                          (ledger.from_source_record_id.eq("02-alpha"))]
        self.assertEqual(len(district), 1)
        self.assertEqual(district.iloc[0].to_source_record_id, "10-alpha")
        urban = ledger[(ledger.candidate_family.eq("urban_region_name")) &
                       (ledger.year_pair.eq("2002-2021")) &
                       (ledger.from_source_record_id.eq("02-alpha"))]
        self.assertEqual(len(urban), 1)
        self.assertTrue(bool(urban.iloc[0].type_change_or_mismatch))
        self.assertEqual(urban.iloc[0].admission_status, "candidate_only_no_admission")
        self.assertGreater(len(ledger[ledger.candidate_kind.eq("type_change_screen_group")]), 0)
        self.assertGreater(len(ledger[ledger.candidate_kind.eq("region_mismatch_screen_group")]), 0)
        self.assertTrue(ledger.admission_status.eq("candidate_only_no_admission").all())
        self.assertEqual(audit["counts"]["admissions_created"], 0)
        self.assertGreater(len(sample), 0)
        self.assertEqual(sample.seed_locked.nunique(), 1)
        self.assertEqual(sample.seed_locked.iloc[0], "20261002")

    def test_ambiguities_aggregate_blank_keys_and_conflicts_are_retained_without_cartesian_expansion(self):
        selected, legacy = self._inputs()
        ledger, _, audit = build_candidate_ledger(selected, legacy)
        ambiguous = ledger[(ledger.candidate_family.eq("region_name_type")) &
                           (ledger.year_pair.eq("2002-2010")) &
                           (ledger.candidate_kind.eq("ambiguous_competing_key_group")) &
                           (ledger.key_values.str.contains("Beta"))]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(int(ambiguous.iloc[0].potential_cartesian_pair_count_not_materialized), 2)
        self.assertEqual(json.loads(ambiguous.iloc[0].from_candidate_ids_json), ["02-beta-a", "02-beta-b"])
        self.assertFalse(ambiguous.iloc[0].legacy_same_year_collision_present)
        self.assertTrue(ambiguous.iloc[0].within_year_key_collision)
        self.assertGreater(sum(v["blank_or_missing_key_rows_not_joined"] for v in audit["source_key_completeness"]
                               if v["candidate_family"] == "region_district_name_type" and v["year"] == 2002), 0)
        alpha = ledger[(ledger.candidate_family.eq("region_name_type")) &
                       (ledger.year_pair.eq("2002-2010")) & ledger.from_source_record_id.eq("02-alpha")].iloc[0]
        evidence = json.loads(alpha.to_endpoint_evidence_json)[0]
        self.assertEqual(evidence["legacy_identity_status"], "quarantined")
        self.assertTrue(evidence["legacy_identity_conflict"])
        self.assertTrue(evidence["legacy_same_year_collision"])
        self.assertTrue(evidence["legacy_ordinal_route_present"])
        self.assertFalse(evidence["legacy_route_is_acceptance_signal"])
        self.assertEqual(evidence["legacy_accepted"], True)
        self.assertTrue(alpha.legacy_ordinal_route_present_not_acceptance_signal)
        self.assertTrue(ledger.loc[ledger.candidate_kind.eq("unique_exact_key_pair"), "admission_status"].eq("candidate_only_no_admission").all())

    def test_aggregate_block_unknown_population_raw_provenance_and_identifiers_are_explicit(self):
        selected, legacy = self._inputs()
        ledger, _, _ = build_candidate_ledger(selected, legacy)
        aggregate = ledger[(ledger.candidate_family.eq("region_name_type")) &
                           (ledger.year_pair.eq("2002-2010")) &
                           ledger.from_source_record_id.eq("02-moscow-aggregate")]
        self.assertEqual(len(aggregate), 1)
        self.assertTrue(bool(aggregate.iloc[0].federal_aggregate_block))
        beta = ledger[(ledger.candidate_family.eq("region_name_type")) &
                      (ledger.year_pair.eq("2010-2021")) &
                      ledger.from_source_record_id.eq("10-beta")].iloc[0]
        self.assertEqual(int(beta.from_unknown_population_rows), 1)
        self.assertEqual(int(beta.from_known_population), 0)
        alpha = ledger[(ledger.candidate_family.eq("region_name_type")) &
                       (ledger.year_pair.eq("2002-2010")) & ledger.from_source_record_id.eq("02-alpha")].iloc[0]
        from_evidence = json.loads(alpha.from_endpoint_evidence_json)[0]
        to_evidence = json.loads(alpha.to_endpoint_evidence_json)[0]
        self.assertEqual(from_evidence["source_name_raw"], "Сырой Альфа")
        self.assertEqual(from_evidence["okato"], "001")
        self.assertEqual(to_evidence["oktmo"], "00002")
        self.assertTrue(bool(alpha.confidentiality_perturbation_present))

    def test_candidate_ids_and_fixed_sample_are_deterministic_and_null_ids_fail_closed(self):
        selected, legacy = self._inputs()
        first, sample1, _ = build_candidate_ledger(selected, legacy)
        second, sample2, _ = build_candidate_ledger(selected.sample(frac=1, random_state=7), legacy)
        self.assertEqual(first.set_index("candidate_id").candidate_kind.to_dict(),
                         second.set_index("candidate_id").candidate_kind.to_dict())
        self.assertEqual(sample1.sort_values("candidate_id").candidate_id.tolist(),
                         sample2.sort_values("candidate_id").candidate_id.tolist())
        sample_strata = ["candidate_family", "year_pair", "population_band", "region_risk_class", "region_stratum"]
        self.assertLessEqual(int(sample1.groupby(sample_strata, dropna=False).size().max()), 3)
        self.assertTrue(sample1.precision_interpretation.str.contains("not a national probability estimate").all())
        broken = selected.copy()
        broken.loc[broken.index[0], "source_record_id"] = None
        with self.assertRaisesRegex(CandidateError, "null or blank"):
            build_candidate_ledger(broken, legacy)


if __name__ == "__main__":
    unittest.main()

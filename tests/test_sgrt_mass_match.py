"""Identity regressions, using illustrative records rather than empirical rows."""
import unittest
from unittest.mock import patch

import pandas as pd

from scripts.sgrt_mass.match import build_reference, match_addresses, normalize_name, normalize_region, normalize_district, normalize_settlement_oktmo, FEDERAL_AGGREGATE_IDS


class AddressIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = pd.DataFrame([
            ("ural", "Уральск", "башкортостан", "Учалинский муниципальный район", "80653491101"),
            ("birch1", "Берёзовка", "башкортостан", "Учалинский муниципальный район", "80653491102"),
            ("birch2", "Березовка", "башкортостан", "Аскинский муниципальный район", "80653491103"),
            ("bash_name", "Башкортостан", "башкортостан", "Аскинский муниципальный район", "80653491104"),
            ("new_world", "Новый Свет", "башкортостан", "Учалинский муниципальный район", "80653491105"),
            ("world", "Свет", "башкортостан", "Учалинский муниципальный район", "80653491106"),
            ("mezh", "Межозёрный", "челябинская", "Верхнеуральский муниципальный район", "75653491101"),
            ("moscow", "Москва", "москва", "Городской округ город Москва", "45000000001"),
        ], columns=["source_record_id", "name", "region", "district", "oktmo"])
        cls.reference["name_norm"] = cls.reference.name.map(normalize_name)
        cls.reference["region_norm"] = cls.reference.region.map(normalize_region)
        cls.reference["district_norm"] = cls.reference.district.map(normalize_district)

    def one(self, address="", region="Башкортостан", **fields):
        frame = pd.DataFrame([dict(activity_address=address, source_region_literal=region, **fields)])
        options = {"name_col": "settlement"} if "settlement" in fields else {}
        if "oktmo" in fields:
            options["oktmo_col"] = "oktmo"
        return match_addresses(frame, self.reference, **options).iloc[0]

    def test_region_administrative_labels(self):
        self.assertEqual(normalize_region("Ханты-Мансийский автономный округ — Югра"), "ханты мансийский югра")
        self.assertEqual(normalize_region("Республика Удмуртия"), "удмуртская")

    def test_diacritics_and_type(self):
        self.assertEqual(normalize_name("д. Берёзовка"), "березовка")

    def test_homonym_is_held(self):
        row = self.one("с. Березовка, ул. Ленина, 1")
        self.assertEqual(row.match_status, "ambiguous")
        self.assertEqual(row.candidate_count, 2)

    def test_literal_district_resolves_homonym(self):
        row = self.one("Республика Башкортостан, Учалинский район, д. Березовка, ул. Ленина, 1")
        self.assertEqual(row.source_record_id, "birch1")

    def test_wrong_district_does_not_disappear(self):
        row = self.one("Республика Башкортостан, Аскинский район, с. Уральск")
        self.assertEqual(row.match_status, "conflict")
        self.assertIsNone(row.source_record_id)

    def test_street_is_not_settlement(self):
        row = self.one("Республика Башкортостан, Учалинский район, улица Уральск, 1")
        self.assertEqual(row.match_status, "unmatched")

    def test_region_is_not_same_named_village(self):
        row = self.one("Республика Башкортостан, ул. Ленина, 1")
        self.assertEqual(row.match_status, "unmatched")

    def test_explicit_same_named_village_can_match(self):
        row = self.one("Республика Башкортостан, Аскинский район, село Башкортостан, ул. Ленина, 1")
        self.assertEqual(row.source_record_id, "bash_name")

    def test_long_name_wins_only_over_contained_name(self):
        row = self.one("Учалинский район, поселок Новый Свет, ул. Мира, 2")
        self.assertEqual(row.source_record_id, "new_world")

    def test_activity_region_can_differ_from_registry_jurisdiction(self):
        row = self.one("Челябинская область, Верхнеуральский район, п. Межозерный, ул. Мира, 1")
        self.assertEqual(row.source_record_id, "mezh")
        self.assertTrue(row.source_region_differs_from_activity_region)

    def test_multiple_address_regions_are_held(self):
        row = self.one("Республика Башкортостан, Челябинская область, п. Межозерный")
        self.assertEqual(row.match_status, "ambiguous")

    def test_code_name_conflict(self):
        row = self.one(settlement="Березовка", oktmo="80653491101")
        self.assertEqual(row.match_status, "conflict")

    def test_code_activity_conflict(self):
        row = self.one("Учалинский район, с. Березовка", oktmo="80653491101")
        self.assertEqual(row.match_status, "conflict")

    def test_exact_code_and_name(self):
        row = self.one(settlement="с. Уральск", oktmo="80653491101")
        self.assertEqual(row.source_record_id, "ural")

    def test_municipal_code_is_not_settlement_code(self):
        row = self.one(oktmo="80653491")
        self.assertEqual(row.match_status, "not_settlement_grain")
        self.assertEqual(row.source_code_status, "not_settlement_11digit_code")

    def test_legal_only_does_not_become_activity(self):
        row = self.one(legal_address="Учалинский район, с. Уральск, ул. Ленина, 1")
        self.assertEqual(row.match_status, "unmatched")

    def test_federal_city_can_be_literal(self):
        row = self.one("Москва, улица Ленина, 1", region="Москва")
        self.assertEqual(row.source_record_id, "moscow")

    def test_federal_region_does_not_exclude_ordinary_child(self):
        fixture = {"root": ["aggregate", "child"]}
        for year in [2002, 2010, 2021]:
            fixture.update({f"source_record_id_{year}": [None, None], f"settlement_name_{year}": [None, None],
                            f"region_norm_{year}": [None, None], f"district_raw_{year}": [None, None],
                            f"oktmo_{year}": [None, None], f"effective_population_{year}": [None, None],
                            f"population_value_quality_{year}": [None, None], f"population_overlay_applied_{year}": [False, False],
                            f"working_credit_present_{year}": [False, False]})
        fixture.update(source_record_id_2021=[next(iter(FEDERAL_AGGREGATE_IDS)), "illustrative_ordinary_child"],
                       settlement_name_2021=["Москва", "Поселение"], region_norm_2021=["москва", "москва"],
                       district_raw_2021=["Москва", "Москва"], oktmo_2021=["45000000000", "45000000101"],
                       effective_population_2021=[100, 5], working_credit_present_2021=[False, True],
                       accepted_latitude_2021=[55.7, 55.8], accepted_longitude_2021=[37.6, 37.7],
                       accepted_point_present_2021=[True, True])
        with patch("pandas.read_parquet", return_value=pd.DataFrame(fixture)):
            reference = build_reference("illustrative_fixture")
        self.assertFalse(reference.loc[0, "ordinary_spatial_2021"])
        self.assertTrue(reference.loc[1, "ordinary_spatial_2021"])
        self.assertEqual(reference.loc[1, "population_role"], "ordinary_settlement_record")

    def test_leading_zero_in_numeric_census_code_is_restored(self):
        self.assertEqual(normalize_settlement_oktmo("3701000171"), "03701000171")
        self.assertIsNone(normalize_settlement_oktmo("80653491"))

    def test_typed_station_is_not_a_different_name(self):
        self.assertEqual(normalize_name("железнодорожный разъезд 34 км"), "34 км")
        self.assertEqual(normalize_name("пгт Калининец рп"), "калининец")

    def test_eleven_digit_aggregate_has_no_name_fallback(self):
        row = self.one(settlement="с. Уральск", oktmo="80653491000")
        self.assertEqual(row.match_status, "not_settlement_grain")
        self.assertIsNone(row.source_record_id)

    def test_explicit_city_aggregate_is_not_a_point_measurement(self):
        row = self.one(settlement="город Уральск", source_row_grain="city_aggregate")
        self.assertEqual(row.match_status, "not_settlement_grain")


if __name__ == "__main__":
    unittest.main()

import unittest

from research_rebuild.mass_linkage.coordinate_rules import (
    in_broad_russia_envelope,
    propose_coordinate_review,
    valid_wgs84,
)


def valid_modern_candidate(**updates):
    row = {
        "source_record_id": "2021:tochno:parquet:31816",
        "target_year": 2021,
        "coordinate_source_record_id": "2021:tochno:parquet:31816",
        "coordinate_provider": "DaData via Tochno",
        "coordinate_provider_family": "dadata",
        "coordinate_lineage_id": "tochno-dadata-source-row",
        "coordinate_provider_id": "fias-object-uuid-123",
        "settlement_provider_id": "fias-settlement-uuid-456",
        "latitude": 64.5890912,
        "longitude": 30.6015362,
        "object_level": "Населенный пункт",
        "object_kind": "physical_settlement",
        "population_scope": "settlement",
        "fias_level_dadata": 6,
        "qc_geo_dadata": 3,
        "measurement_date": "unknown",
        "evidence_uri": "source://tochno/2021/row/31816",
        "evidence_sha256": "a" * 64,
        "corroborators": [],
    }
    row.update(updates)
    return row


def independent_osm_geometry(**updates):
    row = {
        "provider_family": "osm",
        "lineage_group_id": "osm-attic-2021-10-01",
        "lineage_independence_documented": True,
        "evidence_uri": "https://api.openstreetmap.org/api/0.6/relation/123/full",
        "evidence_sha256": "b" * 64,
        "name_match": "exact",
        "admin_context_match": "exact",
        "evidence_kind": "named_settlement_geometry_containment",
        "geometry_object_kind": "settlement_footprint",
        "contains_primary_point": True,
    }
    row.update(updates)
    return row


class MassCoordinateRuleTests(unittest.TestCase):
    def test_negative_chukotka_longitude_is_valid_russia_candidate(self):
        self.assertTrue(valid_wgs84(66.32, -179.12))
        self.assertTrue(in_broad_russia_envelope(66.32, -179.12))

    def test_strong_physical_point_and_independent_geometry_is_only_review_candidate(self):
        candidate = valid_modern_candidate(corroborators=[independent_osm_geometry()])
        proposal = propose_coordinate_review(candidate)
        self.assertEqual(proposal.status, "candidate_for_blind_validation")
        self.assertEqual(proposal.independent_corroborator_count, 1)
        self.assertTrue(proposal.measurement_date_unknown)
        self.assertFalse(proposal.admission_allowed)
        self.assertEqual(proposal.coordinate_source_record_id, candidate["coordinate_source_record_id"])
        self.assertEqual(proposal.coordinate_provider_id, candidate["coordinate_provider_id"])
        self.assertEqual(proposal.settlement_provider_id, candidate["settlement_provider_id"])

    def test_qc_geo_quality_4_alone_does_not_supply_independent_evidence(self):
        proposal = propose_coordinate_review(valid_modern_candidate(qc_geo_dadata=4))
        self.assertEqual(proposal.status, "candidate_needs_independent_evidence")
        self.assertEqual(proposal.independent_corroborator_count, 0)
        self.assertFalse(proposal.admission_allowed)

    def test_fias_city_level_with_physical_settlement_scope_can_be_reviewed(self):
        proposal = propose_coordinate_review(
            valid_modern_candidate(fias_level_dadata=4, corroborators=[independent_osm_geometry()])
        )
        self.assertEqual(proposal.status, "candidate_for_blind_validation")
        self.assertFalse(proposal.admission_allowed)

    def test_same_claim_origin_does_not_count_as_independent_provider(self):
        same_origin = independent_osm_geometry(
            provider_family="wikidata",
            lineage_group_id="tochno-dadata-source-row",
            evidence_kind="named_settlement_geometry_containment",
            wikidata_id="Q123",
            identifier_match_method="exact_oktmo_and_okato",
        )
        proposal = propose_coordinate_review(valid_modern_candidate(corroborators=[same_origin]))
        self.assertEqual(proposal.independent_corroborator_count, 0)
        self.assertEqual(proposal.status, "candidate_needs_independent_evidence")

    def test_wikidata_label_or_coordinate_match_without_exact_identifier_does_not_corroborate(self):
        label_only = independent_osm_geometry(
            provider_family="wikidata",
            lineage_group_id="wikidata-claim-snapshot-1",
            evidence_kind="point",
            latitude=64.589,
            longitude=30.602,
            wikidata_id="Q123",
            identifier_match_method="label_match",
        )
        proposal = propose_coordinate_review(valid_modern_candidate(corroborators=[label_only]))
        self.assertEqual(proposal.independent_corroborator_count, 0)

    def test_wikidata_can_only_corroborate_with_exact_code_binding_and_independent_lineage(self):
        exact_code_claim = independent_osm_geometry(
            provider_family="wikidata",
            lineage_group_id="wikidata-claim-snapshot-1",
            evidence_kind="point",
            latitude=64.589,
            longitude=30.602,
            wikidata_id="Q123",
            identifier_match_method="exact_oktmo_and_okato",
        )
        proposal = propose_coordinate_review(valid_modern_candidate(corroborators=[exact_code_claim]))
        self.assertEqual(proposal.independent_corroborator_count, 1)
        self.assertFalse(proposal.admission_allowed)

    def test_municipality_street_snt_and_nonlocality_fias_levels_are_blocked(self):
        cases = [
            {"object_level": "Муниципалитет нижнего уровня"},
            {"object_level": "улица"},
            {"object_kind": "garden_partnership", "object_level": "Населенный пункт"},
            {"fias_level_dadata": 7},
            {"fias_level_dadata": 65},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                proposal = propose_coordinate_review(valid_modern_candidate(**overrides))
                self.assertEqual(proposal.status, "blocked")
                self.assertFalse(proposal.admission_allowed)

    def test_federal_city_region_aggregate_is_blocked(self):
        proposal = propose_coordinate_review(
            valid_modern_candidate(population_scope="federal_city_region", fias_level_dadata=1)
        )
        self.assertEqual(proposal.status, "blocked")
        self.assertIn("federal_city_region_aggregate_excluded", proposal.blocking_reasons)

    def test_invalid_or_partial_coordinates_are_blocked(self):
        for overrides in ({"latitude": 55.0, "longitude": None}, {"latitude": 95, "longitude": 37}):
            with self.subTest(overrides=overrides):
                proposal = propose_coordinate_review(valid_modern_candidate(**overrides))
                self.assertEqual(proposal.status, "blocked")

    def test_duplicate_and_known_provider_conflict_are_blocked(self):
        for overrides in (
            {"duplicate_point_group_size": 2},
            {"provider_coordinate_conflict": True},
            {"wikidata_distance_km": 5.1},
        ):
            with self.subTest(overrides=overrides):
                proposal = propose_coordinate_review(valid_modern_candidate(**overrides))
                self.assertEqual(proposal.status, "blocked")

    def test_missing_source_or_provider_identity_and_evidence_locator_block_mass_candidate(self):
        for overrides in (
            {"coordinate_source_record_id": None},
            {"coordinate_provider_id": None, "fias_id_dadata": None},
            {"evidence_uri": None},
            {"evidence_sha256": None},
        ):
            with self.subTest(overrides=overrides):
                proposal = propose_coordinate_review(
                    valid_modern_candidate(corroborators=[independent_osm_geometry()], **overrides)
                )
                self.assertEqual(proposal.status, "blocked")
                self.assertFalse(proposal.admission_allowed)

    def test_historical_target_needs_separate_continuity_review(self):
        proposal = propose_coordinate_review(valid_modern_candidate(target_year=2010))
        self.assertEqual(proposal.status, "blocked")
        self.assertIn("historical_use_requires_separate_reviewed_continuity", proposal.review_reasons)

    def test_measurement_date_unknown_is_review_limitation_not_standalone_blocker(self):
        proposal = propose_coordinate_review(
            valid_modern_candidate(corroborators=[independent_osm_geometry()], measurement_date=None)
        )
        self.assertEqual(proposal.status, "candidate_for_blind_validation")
        self.assertTrue(proposal.measurement_date_unknown)
        self.assertTrue(proposal.provider_query_receipt_missing)
        self.assertIn("provider_query_receipt_missing", proposal.review_reasons)
        self.assertFalse(proposal.admission_allowed)


if __name__ == "__main__":
    unittest.main()

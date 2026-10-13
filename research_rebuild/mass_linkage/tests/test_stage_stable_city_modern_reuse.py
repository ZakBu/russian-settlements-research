import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research_rebuild.mass_linkage.stage_stable_city_modern_reuse import (
    EXPECTED_HOLD,
    POINT_CHOICE_REVIEW_ID,
    RAW_2021_SOURCE_SHA256,
    load_point_choice_approvals,
    recovered_frozen_source_origin,
    sha,
    stage,
)


class StableCityModernReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.output = self.root / 'stage'
        self.target_id = '2010:source:city-a'
        self.carrier_id = '2021:source:city-a'
        self.origin = self.inputs / 'point.jsonl.gz'
        self.origin.write_bytes(b'fixture origin bytes')
        self.origin_sha = hashlib.sha256(self.origin.read_bytes()).hexdigest()
        self.target = self.selected_row(self.target_id, 2010)
        self.carrier_selected = self.selected_row(self.carrier_id, 2021)
        self.evidence_target = self.evidence(self.target_id, 2010)
        self.evidence_carrier = self.evidence(self.carrier_id, 2021)
        self.carrier = self.carrier_row(self.carrier_id, 2021)
        self.edge = self.edge_row()
        self.case = self.case_row()
        self.hrow_data = self.hrow()
        self.write_inputs()

    def tearDown(self):
        self.temp.cleanup()

    def selected_row(self, source_id, year):
        return {
            'source_record_id': source_id,
            'census_year': year,
            'settlement_name': 'Город А',
            'settlement_type': 'город',
            'source_name_raw': 'г. Город А',
            'source_file': f'source_{year}.csv',
            'source_sheet': None,
            'source_row': 15 if year == 2010 else 23,
            'source_sha256': f'{year:064x}',
            'source_locator': f'row={year}',
            'source_native_id': f'native-{year}',
            'population': 12345 if year == 2010 else 12600,
            'population_scope': 'settlement',
            'population_value_quality': 'direct_official_city_value',
            'is_additive_settlement_record': True,
            'entity_grain_status': 'city',
            'region_raw': 'Регион А',
            'region_norm': 'регион а',
            'okato': None,
            'oktmo': '12345' if year == 2021 else None,
        }

    def evidence(self, source_id, year, **changes):
        value = {
            'source_record_id': source_id,
            'census_year': year,
            'settlement_name': 'Город А',
            'settlement_type': 'город',
            'region_norm': 'регион а',
            'source_file': f'source_{year}.csv',
            'source_row': 15 if year == 2010 else 23,
            'source_sha256': f'{year:064x}',
            'source_locator': f'row={year}',
            'population': 12345 if year == 2010 else 12600,
            'population_scope': 'settlement',
            'population_value_quality': 'direct_official_city_value',
            'is_additive_settlement_record': True,
            'is_federal_aggregate': False,
            'legacy_identity_conflict': False,
            'legacy_same_year_collision': False,
            'legacy_entity_year_record_count': 1,
        }
        value.update(changes)
        return {'source_record_id': source_id, 'source_evidence_json': json.dumps(value, ensure_ascii=False)}

    def carrier_row(self, source_id, year, latitude=55.0, longitude=37.0):
        return {
            'target_source_record_id': source_id,
            'target_year': year,
            'latitude': latitude,
            'longitude': longitude,
            'coordinate_quality': 'reviewed modern representative point',
            'coordinate_source': 'wikidata_p625',
            'coordinate_source_record_id': source_id,
            'coordinate_provenance': 'accepted physical city point; no boundary claim',
            'admission_rule': 'accepted_city_point_rule_v1',
            'coordinate_admission_status': 'reviewed_rule_accepted',
            'provider_fias_binding_status': 'not_asserted',
            'coordinate_measurement_date_unknown': True,
            'boundary_comparability_asserted': False,
            'population_scope_comparability_asserted': False,
            'direct_historical_coordinate_measurement': False,
            'point_origin_file': str(self.origin),
            'point_origin_sha256': self.origin_sha,
            'point_origin_locator': 'file=point.jsonl.gz:line=8',
            'point_origin_kind': 'wikidata_truthy_p625_raw_claim',
            'point_claim_artifact_file': str(self.origin),
            'point_claim_artifact_sha256': self.origin_sha,
        }

    def edge_row(self, status='checked_rule_accepted'):
        return {
            'decision_id': 'edge:city-a',
            'relation': 'same_place',
            'decision_status': status,
            'from_source_record_id': self.target_id,
            'from_year': 2010,
            'to_source_record_id': self.carrier_id,
            'to_year': 2021,
        }

    def case_row(self, hold_reasons=None, distance='2.0', accepted='True'):
        return {
            'target_source_record_id': self.target_id,
            'year': '2010',
            'settlement_name': 'Город А',
            'population': '12345',
            'carrier_source_record_id': self.carrier_id,
            'carrier_point_accepted_current': accepted,
            'point_distance_km': distance,
            'hold_reasons_json': json.dumps(hold_reasons if hold_reasons is not None else EXPECTED_HOLD),
        }

    def hrow(self, hold_reasons=None, roles=None):
        return {
            'target_source_record_id': self.target_id,
            'year': 2010,
            'settlement_name': 'Город А',
            'population': 12345,
            'carrier_source_record_id': self.carrier_id,
            'point_distance_km': 2.0,
            'identity_path_decision_ids_json': json.dumps(['edge:city-a']),
            'lineage_event_roles_json': json.dumps(roles if roles is not None else []),
            'gate_passed': False,
            'hold_reasons_json': json.dumps(hold_reasons if hold_reasons is not None else EXPECTED_HOLD),
        }

    def write_inputs(self, cases=None, hrows=None, carrier=None, evidence=None,
                     edge=None, blocked=None, prior_holds=None, extra_base=None):
        self.paths = {key: self.inputs / filename for key, filename in {
            'cases': 'cases.csv', 'hledger': 'hledger.parquet', 'selected': 'selected.parquet',
            'selected_current': 'selected_current.parquet', 'evidence': 'evidence.parquet',
            'graph': 'graph.parquet', 'blocked': 'blocked.json', 'prior_holds': 'prior_holds.parquet',
            'base': 'base.parquet',
        }.items()}
        pd.DataFrame(cases if cases is not None else [self.case_row()]).to_csv(self.paths['cases'], index=False)
        pd.DataFrame(hrows if hrows is not None else [self.hrow_data]).to_parquet(self.paths['hledger'], index=False)
        selected = [self.target, self.carrier_selected]
        pd.DataFrame(selected).to_parquet(self.paths['selected'], index=False)
        pd.DataFrame(selected).to_parquet(self.paths['selected_current'], index=False)
        pd.DataFrame(evidence if evidence is not None else [self.evidence_target, self.evidence_carrier]).to_parquet(
            self.paths['evidence'], index=False)
        pd.DataFrame([edge if edge is not None else self.edge]).to_parquet(self.paths['graph'], index=False)
        self.paths['blocked'].write_text(json.dumps({'blocked_target_source_record_ids': blocked or []}))
        pd.DataFrame({'target_source_record_id': prior_holds or []}).to_parquet(self.paths['prior_holds'], index=False)
        base_rows = [carrier if carrier is not None else self.carrier]
        base_rows.extend(extra_base or [])
        pd.DataFrame(base_rows).to_parquet(self.paths['base'], index=False)

    def run_stage(self):
        return stage(self.paths['base'], self.output, cases_path=self.paths['cases'],
                     h_ledger_path=self.paths['hledger'], selected_path=self.paths['selected'],
                     selected_current_path=self.paths['selected_current'],
                     evidence_path=self.paths['evidence'], graph_path=self.paths['graph'],
                     blocked_path=self.paths['blocked'], prior_holds_path=self.paths['prior_holds'])

    def test_stages_exact_accepted_carrier_point_and_retains_source_population(self):
        receipt = self.run_stage()
        staged = pd.read_parquet(self.output / 'staged_point_uses.parquet')
        self.assertEqual(receipt['staged_rows'], 1)
        row = staged.iloc[0]
        self.assertEqual(row['target_source_record_id'], self.target_id)
        self.assertEqual(row['target_year'], 2010)
        self.assertEqual(row['latitude'], self.carrier['latitude'])
        self.assertEqual(row['longitude'], self.carrier['longitude'])
        self.assertEqual(row['point_origin_file'], str(self.origin))
        self.assertEqual(row['point_origin_sha256'], self.origin_sha)
        self.assertEqual(row['source_file'], 'source_2010.csv')
        self.assertEqual(row['target_population'], 12345)
        self.assertEqual(row['target_population_value_quality'], 'direct_official_city_value')
        self.assertEqual(row['historical_named_point_candidate_status'], 'held_distance_only_not_applied')
        self.assertEqual(row['application_inference_kind'],
                         'stable_city_retrospective_representative_point_from_accepted_2021_city_carrier')
        self.assertFalse(row['admission_allowed'])
        self.assertFalse(row['direct_historical_coordinate_measurement'])
        self.assertTrue(row['coordinate_measurement_date_unknown'])
        self.assertFalse(row['boundary_comparability_asserted'])
        self.assertFalse(row['population_scope_comparability_asserted'])

    def test_explicit_blocked_point_conflict_target_is_held(self):
        self.write_inputs(blocked=[self.target_id])
        self.assertEqual(self.run_stage()['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('explicit_or_prior_actual_point_conflict_block', held.iloc[0]['hold_reasons_json'])

    def test_prior_actual_point_conflict_is_held_even_without_blocked_json_entry(self):
        self.write_inputs(prior_holds=[self.target_id])
        self.assertEqual(self.run_stage()['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('explicit_or_prior_actual_point_conflict_block', held.iloc[0]['hold_reasons_json'])

    def test_distance_only_gate_is_exact_and_unexpected_reasons_hold(self):
        self.write_inputs(hrows=[self.hrow(hold_reasons=['some_other_gate'])])
        self.assertEqual(self.run_stage()['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('historical_gate_ledger_not_exact_distance_only_hold', held.iloc[0]['hold_reasons_json'])

    def test_nonreceiving_or_unknown_event_role_holds(self):
        roles = [{'event_id': 'event:split', 'event_type': 'split_created',
                  'native_code_roles': ['from_settlement_id_legacy_candidate'], 'point_veto': True}]
        self.write_inputs(hrows=[self.hrow(roles=roles)])
        self.assertEqual(self.run_stage()['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('lineage_event_role_not_safe_for_representative_point_reuse',
                      held.iloc[0]['hold_reasons_json'])

    def test_receiving_city_absorption_role_is_eligible_but_boundary_stays_unasserted(self):
        roles = [{'event_id': 'event:receiving-absorption', 'event_type': 'absorbed_into_city',
                  'native_code_roles': ['to_settlement_id_legacy_candidate'], 'point_veto': False,
                  'boundary_comparability': 'not_asserted',
                  'event_evidence_status': 'legacy_candidate_not_newly_verified'}]
        self.write_inputs(hrows=[self.hrow(roles=roles)])
        self.assertEqual(self.run_stage()['staged_rows'], 1)
        staged = pd.read_parquet(self.output / 'staged_point_uses.parquet')
        self.assertFalse(staged.iloc[0]['boundary_comparability_asserted'])

    def test_unaccepted_graph_path_holds(self):
        self.write_inputs(edge=self.edge_row(status='pending_review'))
        self.assertEqual(self.run_stage()['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('identity_path_has_unaccepted_or_non_same_place_edge',
                      held.iloc[0]['hold_reasons_json'])

    def test_source_aggregate_conflict_holds(self):
        bad = self.evidence(self.target_id, 2010, is_federal_aggregate=True)
        self.write_inputs(evidence=[bad, self.evidence_carrier])
        self.assertEqual(self.run_stage()['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('source_is_federal_aggregate', held.iloc[0]['hold_reasons_json'])


if __name__ == '__main__':
    unittest.main()


class PointChoiceOverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review_dir = self.root / 'review'
        self.review_dir.mkdir()
        self.asset = self.root / 'p625.jsonl.gz'
        self.asset.write_bytes(b'approved raw P625 asset')
        self.asset_sha = hashlib.sha256(self.asset.read_bytes()).hexdigest()
        self.ids = [f'2010:target:{i}' for i in range(12)]
        self.carrier_ids = [f'2021:carrier:{i}' for i in range(12)]
        self.cases = {target: {'carrier_source_record_id': carrier}
                      for target, carrier in zip(self.ids, self.carrier_ids)}
        self.carriers = {
            carrier: {
                'target_source_record_id': carrier,
                'target_year': 2021,
                'latitude': 50.0 + i,
                'longitude': 40.0 + i,
                'coordinate_source': 'wikidata_p625',
                'coordinate_provider_id': f'Q{i}',
                'point_origin_file': str(self.asset),
                'point_origin_sha256': self.asset_sha,
                'point_origin_locator': f'line={i};entity=Q{i};claim=P625',
                'point_origin_kind': 'wikidata_truthy_p625_raw_claim',
            }
            for i, carrier in enumerate(self.carrier_ids)
        }
        self.inputs = {}
        for name, filename in (
            ('distance_only_cases', 'cases.csv'),
            ('accepted_graph_R2', 'graph.parquet'),
            ('selected_R2', 'selected.parquet'),
            ('prior_point_conflict_holds', 'prior.parquet'),
        ):
            path = self.root / filename
            path.write_bytes(('fixture:' + name).encode())
            self.inputs[name] = path
        self.inputs.update({
            'distance_only_cases': self.inputs['distance_only_cases'],
            'accepted_graph_R2': self.inputs['accepted_graph_R2'],
            'selected_R2': self.inputs['selected_R2'],
            'prior_point_conflict_holds': self.inputs['prior_point_conflict_holds'],
        })

    def tearDown(self):
        self.temp.cleanup()

    def write_review(self, *, unauthorized=False, changed_carrier_point=False):
        rows = []
        for i, (target, carrier_id) in enumerate(zip(self.ids, self.carrier_ids)):
            carrier = self.carriers[carrier_id]
            rows.append({
                'target_source_record_id': target,
                'modern_carrier_source_record_id': carrier_id,
                'accepted_point_latitude': str(carrier['latitude'] + (1 if changed_carrier_point and i == 0 else 0)),
                'accepted_point_longitude': str(carrier['longitude']),
                'accepted_point_origin_kind': carrier['point_origin_kind'],
                'accepted_point_qid': carrier['coordinate_provider_id'],
                'accepted_point_claim_raw_file': carrier['point_origin_file'],
                'accepted_point_claim_sha256': carrier['point_origin_sha256'],
                'accepted_point_claim_raw_locator': carrier['point_origin_locator'],
                'legacy_hold_is_same_claim_as_current_carrier': 'True',
                'point_choice': 'HOLD' if unauthorized and i == 0 else 'APPROVE_BOUNDED_MODERN_POINT_REUSE',
                'point_choice_reason': 'approved exact carrier point',
            })
        row_path = self.review_dir / 'row_level_point_choice_review.csv'
        pd.DataFrame(rows).to_csv(row_path, index=False)
        frozen = {
            '/workspace/settlements-work/continuation_20261003/next_loop_residual_diagnostic_v1/historical_city_distance_only_cases.csv': sha(self.inputs['distance_only_cases']),
            '/workspace/settlements-work/identity/accepted_historical_v2/accepted_identity_edges.parquet': sha(self.inputs['accepted_graph_R2']),
            '/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet': sha(self.inputs['selected_R2']),
            '/workspace/settlements-work/coordinates/accepted_final_v1/additional_legacy_point_conflict_holds.parquet': sha(self.inputs['prior_point_conflict_holds']),
        }
        review = {
            'review_id': POINT_CHOICE_REVIEW_ID,
            'decision': 'APPROVE_BOUNDED_MODERN_POINT_REUSE for all 12 named targets',
            'approved_for_bounded_modern_point_reuse_ids': self.ids,
            'remaining_hold_ids': [],
            'target_count': 12,
            'frozen_input_sha256': frozen,
        }
        review_path = self.review_dir / 'review.json'
        review_path.write_text(json.dumps(review, ensure_ascii=False))
        (self.review_dir / 'receipt.json').write_text(json.dumps({
            'review_id': POINT_CHOICE_REVIEW_ID,
            'target_count': 12,
            'approved_count': 12,
            'held_count': 0,
            'files': {
                'review.json': sha(review_path),
                'row_level_point_choice_review.csv': sha(row_path),
            },
        }))
        return review_path

    def load(self, review_path, expected_sha=None):
        blocked = set(self.ids)
        return load_point_choice_approvals(
            review_path, self.cases, self.carriers, self.inputs, blocked,
            expected_sha or sha(review_path),
        )

    def test_exact_review_carrier_origin_pins_authorize_only_reviewed_ids(self):
        review_path = self.write_review()
        approved, receipt = self.load(review_path)
        self.assertEqual(set(approved), set(self.ids))
        self.assertEqual(receipt['review_id'], POINT_CHOICE_REVIEW_ID)
        self.assertEqual(len(receipt['approved_ids']), 12)

    def test_unapproved_row_cannot_override_block(self):
        review_path = self.write_review(unauthorized=True)
        with self.assertRaisesRegex(ValueError, 'row-level point-choice approval missing'):
            self.load(review_path)

    def test_changed_review_hash_cannot_override_block(self):
        review_path = self.write_review()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.load(review_path, '0' * 64)

    def test_changed_current_carrier_point_cannot_override_block(self):
        review_path = self.write_review(changed_carrier_point=True)
        with self.assertRaisesRegex(ValueError, 'coordinates differ'):
            self.load(review_path)

    def test_voronezh_frozen_point_origin_recovery_requires_exact_raw_match(self):
        carrier = {
            'target_source_record_id': '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:16108',
            'target_year': 2021,
            'source_name': 'Воронеж',
            'latitude': 51.6593943,
            'longitude': 39.196922,
            'coordinate_admission_status': 'frozen_r5b_reviewed_baseline_preserved',
            'point_origin_kind': 'reviewed_frozen_assertion',
            'point_origin_locator': 'frozen target;review URL',
            'point_claim_artifact_file': '/frozen/review.csv',
            'point_claim_artifact_sha256': 'a' * 64,
        }
        # The raw provider has a typed display prefix while the accepted point-use
        # projection leaves source_name blank; row identity plus exact coordinates
        # and the frozen reviewed claim are the provenance gates here.
        raw = {'settlement': 'г. Воронеж', 'region': 'Воронежская область',
               'latitude_dadata': 51.6593943, 'longitude_dadata': 39.196922}
        frozen = {'target_source_record_id': carrier['target_source_record_id'],
                  'target_year': '2021',
                  'coordinate_source_record_id': carrier['target_source_record_id'],
                  'coordinate_kind': 'direct_source_row_representative_point',
                  'latitude': '51.6593943', 'longitude': '39.196922'}
        recovered = recovered_frozen_source_origin(
            carrier, raw, frozen, self.asset, RAW_2021_SOURCE_SHA256
        )
        self.assertEqual(recovered['point_origin_file'], str(self.asset))
        self.assertIn('parquet_row_1based=16108', recovered['point_origin_locator'])
        self.assertIn('settlement_raw=г. Воронеж', recovered['point_origin_locator'])
        self.assertEqual(recovered['supporting_carrier_point_origin_kind'], 'reviewed_frozen_assertion')
        with self.assertRaisesRegex(ValueError, 'raw 2021 source parquet hash'):
            recovered_frozen_source_origin(carrier, raw, frozen, self.asset, '0' * 64)
        raw['latitude_dadata'] = 51.65
        with self.assertRaisesRegex(ValueError, 'coordinates differ'):
            recovered_frozen_source_origin(carrier, raw, frozen, self.asset,
                                           RAW_2021_SOURCE_SHA256)

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research_rebuild.mass_linkage.propagate_continuation_points import (
    ACCEPTED_COLUMNS,
    SELECTED_COLUMNS,
    build,
)


class ContinuationPointStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.output = self.root / 'output'
        self.origin = self.inputs / 'point_origin.csv'
        self.origin.write_text('source_id,lat,lon\ncarrier,55.0,37.0\n')
        self.origin_sha = hashlib.sha256(self.origin.read_bytes()).hexdigest()
        self.target_id = 'legacy:2010:target'
        self.carrier_id = 'current:2021:carrier'
        self.base_accepted = self.accepted_row(self.carrier_id, 2021)
        self.base_graph = self.graph_row(self.target_id, 2010, self.carrier_id, 2021)
        self.base_selected = [self.selected_row(self.target_id, 2010),
                              self.selected_row(self.carrier_id, 2021, oktmo='12345')]
        self.base_evidence = [self.evidence_row(self.target_id, 2010),
                              self.evidence_row(self.carrier_id, 2021)]
        self.write_inputs()

    def tearDown(self):
        self.temp.cleanup()

    def accepted_row(self, source_id, year, latitude=55.0, longitude=37.0):
        row = {column: None for column in ACCEPTED_COLUMNS}
        row.update({
            'target_source_record_id': source_id,
            'target_year': year,
            'latitude': latitude,
            'longitude': longitude,
            'coordinate_quality': 'reviewed_point',
            'coordinate_source': 'raw_geography_2011',
            'coordinate_source_record_id': 'geo:row:carrier',
            'coordinate_provider': 'raw source',
            'coordinate_provider_id': 'raw-id',
            'coordinate_provenance': 'source point with preserved row locator',
            'admission_rule': 'accepted_current_point_rule',
            'provider_binding_status': 'not_independently_asserted',
            'provider_fias_binding_status': 'not_asserted',
            'coordinate_admission_status': 'accepted',
            'coordinate_measurement_date_unknown': True,
            'boundary_comparability_asserted': False,
            'coordinate_provider_family': 'raw_geography',
            'provider_query_receipt_missing': True,
            'coordinate_uncertainty_flags_json': '[]',
            'coordinate_application_family': 'reviewed_current_city_point',
            'review_id': 'review:fixture',
            'application_inference_kind': 'direct_source_point',
            'direct_historical_coordinate_measurement': False,
            'population_scope_comparability_asserted': False,
            'coordinate_source_sha256': self.origin_sha,
            'coordinate_source_locator': 'row=1',
            'coordinate_source_file': str(self.origin),
            'coordinate_source_origin': 'raw source point',
            'coordinate_source_input_artifact_sha256': self.origin_sha,
            'coordinate_source_date': '2011-01-01',
            'coordinate_source_latitude_raw': '55.0',
            'coordinate_source_longitude_raw': '37.0',
            'inference_modern_point_use_target_source_record_id': None,
            'inference_identity_path_decision_ids_json': '[]',
            'inference_identity_path_from_source_record_id': None,
            'inference_identity_path_to_source_record_id': None,
            'inference_identity_path_edge_count': 0,
            'point_origin_file': str(self.origin),
            'point_origin_sha256': self.origin_sha,
            'point_origin_locator': 'row=1',
            'point_origin_kind': 'source_coordinate_row',
            'point_claim_artifact_file': None,
            'point_claim_artifact_sha256': None,
        })
        return row

    def selected_row(self, source_id, year, oktmo=''):
        row = {column: None for column in SELECTED_COLUMNS}
        row.update({
            'source_record_id': source_id,
            'census_year': year,
            'settlement_name': 'Пример',
            'settlement_type': 'город',
            'source_name_raw': 'г. Пример',
            'source_file': 'source_2010.csv' if year == 2010 else 'source_2021.csv',
            'source_sheet': None,
            'source_row': 17 if year == 2010 else 22,
            'source_sha256': f'{year:064x}',
            'source_locator': f'row={17 if year == 2010 else 22}',
            'source_native_id': f'native-{year}',
            'source_path': '/raw/source.csv',
            'population': 100,
            'population_scope': 'settlement',
            'population_value_quality': 'reported',
            'is_additive_settlement_record': True,
            'entity_grain_status': 'locality',
            'region_raw': 'Область Пример',
            'region_norm': 'область пример',
            'district_raw': None,
            'municipality_raw': None,
            'okato': '12345678000',
            'oktmo': oktmo,
        })
        return row

    def evidence_row(self, source_id, year, **changes):
        value = {
            'source_record_id': source_id,
            'census_year': year,
            'settlement_name': 'Пример',
            'settlement_type': 'город',
            'source_name_raw': 'г. Пример',
            'source_file': 'source_2010.csv' if year == 2010 else 'source_2021.csv',
            'source_row': 17 if year == 2010 else 22,
            'source_sha256': f'{year:064x}',
            'source_locator': f'row={17 if year == 2010 else 22}',
            'region_norm': 'область пример',
            'okato': '12345678000',
            'oktmo': '12345' if year == 2021 else '',
            'entity_grain_status': 'locality',
            'is_additive_settlement_record': True,
            'is_federal_aggregate': False,
            'legacy_identity_conflict': False,
            'legacy_same_year_collision': False,
        }
        value.update(changes)
        return {'source_record_id': source_id, 'census_year': year,
                'source_evidence_json': json.dumps(value, ensure_ascii=False)}

    def graph_row(self, left, left_year, right, right_year, status='checked_rule_accepted'):
        return {
            'decision_id': f'edge:{left}:{right}',
            'relation': 'same_place',
            'from_source_record_id': left,
            'from_year': left_year,
            'to_source_record_id': right,
            'to_year': right_year,
            'decision_status': status,
        }

    def write_inputs(self, accepted=None, graph=None, selected=None, evidence=None,
                     carrier_ids=None, events=None, blocked=None):
        self.paths = {
            'accepted': self.inputs / 'accepted.parquet',
            'carrier_delta': self.inputs / 'carrier_delta.parquet',
            'graph': self.inputs / 'graph.parquet',
            'selected': self.inputs / 'selected.parquet',
            'evidence': self.inputs / 'evidence.parquet',
            'events': self.inputs / 'events.json',
            'blocked': self.inputs / 'blocked.json',
        }
        pd.DataFrame(accepted if accepted is not None else [self.base_accepted],
                     columns=ACCEPTED_COLUMNS).to_parquet(self.paths['accepted'], index=False)
        pd.DataFrame({'target_source_record_id': carrier_ids or [self.carrier_id]}).to_parquet(
            self.paths['carrier_delta'], index=False)
        pd.DataFrame(graph if graph is not None else [self.base_graph]).to_parquet(
            self.paths['graph'], index=False)
        pd.DataFrame(selected if selected is not None else self.base_selected,
                     columns=SELECTED_COLUMNS).to_parquet(self.paths['selected'], index=False)
        pd.DataFrame(evidence if evidence is not None else self.base_evidence).to_parquet(
            self.paths['evidence'], index=False)
        self.paths['events'].write_text(json.dumps(events if events is not None else []))
        self.paths['blocked'].write_text(json.dumps({
            'blocked_target_source_record_ids': blocked if blocked is not None else []
        }))

    def run_build(self):
        return build(self.paths['accepted'], self.paths['carrier_delta'], self.paths['graph'],
                     self.paths['selected'], self.paths['evidence'], self.paths['events'],
                     self.paths['blocked'], self.output)

    def test_stages_target_with_exact_path_and_separate_source_origin(self):
        receipt = self.run_build()
        staged = pd.read_parquet(self.output / 'staged_point_uses.parquet')
        self.assertEqual(receipt['staged_rows'], 1)
        row = staged.iloc[0]
        self.assertEqual(row['target_source_record_id'], self.target_id)
        self.assertEqual(row['target_year'], 2010)
        self.assertEqual(row['source_name'], 'Пример')
        self.assertEqual(row['source_file'], 'source_2010.csv')
        self.assertEqual(row['source_row'], 17)
        self.assertEqual(row['point_origin_file'], str(self.origin))
        self.assertEqual(row['coordinate_source_record_id'], 'geo:row:carrier')
        self.assertEqual(row['inference_modern_point_use_target_source_record_id'], self.carrier_id)
        self.assertEqual(row['inference_identity_path_edge_count'], 1)
        self.assertFalse(row['admission_allowed'])
        self.assertFalse(row['direct_historical_coordinate_measurement'])
        self.assertTrue(row['coordinate_measurement_date_unknown'])
        self.assertFalse(row['boundary_comparability_asserted'])
        self.assertEqual(row['provider_fias_binding_status'],
                         'not_asserted_for_historical_target_by_graph_continuity')
        self.assertTrue(receipt['staged_admission_allowed_all_false'])

    def test_explicit_quarantine_or_prior_conflict_id_is_held(self):
        self.write_inputs(blocked=[self.target_id])
        receipt = self.run_build()
        self.assertEqual(receipt['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('explicit_blocked_target_id', held.iloc[0]['hold_reasons_json'])

    def test_exact_native_oktmo_event_in_target_interval_holds(self):
        events = [{'event_id': 'evt:role-change', 'event_type': 'settlement_role_change',
                   'source_asserted_effective_date': '2015-01-01',
                   'settlement_id_from': 'RU-OKTMO-12345'}]
        self.write_inputs(events=events)
        receipt = self.run_build()
        self.assertEqual(receipt['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('exact_native_carrier_oktmo_lineage_event_evt:role-change',
                      held.iloc[0]['hold_reasons_json'])

    def test_provider_code_is_compared_literally_without_padding(self):
        events = [{'event_id': 'evt:other-code', 'event_type': 'settlement_role_change',
                   'source_asserted_effective_date': '2015-01-01',
                   'settlement_id_from': 'RU-OKTMO-012345'}]
        self.write_inputs(events=events)
        self.assertEqual(self.run_build()['staged_rows'], 1)

    def test_same_year_exact_coordinate_collision_with_accepted_point_holds(self):
        other = self.accepted_row('accepted:2010:other', 2010)
        self.write_inputs(accepted=[self.base_accepted, other])
        receipt = self.run_build()
        self.assertEqual(receipt['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('same_year_exact_coordinate_collision_with_accepted_target',
                      held.iloc[0]['hold_reasons_json'])

    def test_source_identity_conflict_holds(self):
        evidence = [self.evidence_row(self.target_id, 2010, legacy_identity_conflict=True),
                    self.evidence_row(self.carrier_id, 2021)]
        self.write_inputs(evidence=evidence)
        receipt = self.run_build()
        self.assertEqual(receipt['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('legacy_identity_conflict', held.iloc[0]['hold_reasons_json'])

    def test_nonaccepted_same_place_edge_does_not_provide_path(self):
        graph = [self.graph_row(self.target_id, 2010, self.carrier_id, 2021,
                                status='pending_review')]
        self.write_inputs(graph=graph)
        receipt = self.run_build()
        self.assertEqual(receipt['staged_rows'], 0)
        held = pd.read_parquet(self.output / 'held_targets.parquet')
        self.assertIn('target_not_in_accepted_same_place_graph', held.iloc[0]['hold_reasons_json'])


if __name__ == '__main__':
    unittest.main()

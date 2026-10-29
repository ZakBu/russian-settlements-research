import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from scripts.sgrt_saratov.population_mass_scope import (
    mass_sources, external_city_costs, _init_unbounded, _unbounded_origin,
    _unknown_origin_fields, run_unbounded,
)


class AcceptedPopulationMassTests(unittest.TestCase):
    def fixture(self):
        reference = pd.DataFrame({
            'source_record_id': ['a', 'unlocated', 'moscow', 'spb', 'sev'],
            'population_2021': [100., 39., 1000., 500., 2000.],
            'credit_2021': [True, True, False, False, False],
            'budget_population_credit': [True, False, False, False, False],
            'population_role': ['ordinary_settlement_record'] * 2 + ['external_context_nonadditive'] * 3,
            'accepted_source_endpoint': [True, False, True, True, True],
            'region': ['test', 'test', 'москва', 'санкт петербург', 'севастополь'],
            'lat': [50., np.nan, 50., 50., 50.], 'lon': [45., np.nan, 45., 45., 45.],
            'road_node_index': [0., np.nan, 1., 2., 3.], 'snap_km': [0., np.nan, 0., 0., 0.],
        })
        federal = pd.DataFrame({'census_year': [2021, 2021],
            'territory_key': ['RU-FED-MOW', 'RU-FED-SPB'],
            'population_source_record_id': ['moscow', 'spb'], 'territory_population': [1000., 500.]})
        graph = csr_matrix(([10., 30., 20., 40., 30., 50.],
                            ([0, 1, 0, 2, 0, 3], [1, 0, 2, 0, 3, 0])), shape=(4, 4))
        return reference, federal, graph

    def test_federal_totals_once_and_unlocated39_do_not_mutate_census_credit(self):
        reference, federal, _ = self.fixture()
        result = mass_sources(reference, federal)
        pd.testing.assert_series_equal(result.credit_2021, reference.credit_2021)
        pd.testing.assert_series_equal(result.budget_population_credit, reference.budget_population_credit)
        self.assertEqual(result.field_mass_2021.sum(), 1639.)
        self.assertEqual(result.loc[result.source_record_id.eq('unlocated'), 'field_mass_2021'].iloc[0], 39.)
        self.assertTrue(result.loc[result.source_record_id.eq('sev'), 'field_mass_2021'].isna().all())
        with self.assertRaises(ValueError):
            mass_sources(reference, pd.concat([federal, federal.iloc[[0]]], ignore_index=True))

    def test_reverse_search_keeps_origin_to_city_direction_and_both_connectors(self):
        reference, federal, graph = self.fixture()
        sources = mass_sources(reference, federal)
        origins = reference.iloc[[0]].copy()
        origins['snap_km'] = .5
        anchors = sources[sources.eligible_federal_territory_field_mass].copy()
        anchors.loc[anchors.source_record_id.eq('moscow'), 'snap_km'] = .25
        result = external_city_costs(graph, origins, anchors).set_index('city_id')
        self.assertEqual(result.loc['moscow', 'cost_minutes'], 13.)
        self.assertNotEqual(result.loc['moscow', 'cost_minutes'], 33.)

    def test_unbounded_field_federal_component_and_unlocated_bound_are_separate(self):
        reference, federal, graph = self.fixture()
        source = mass_sources(reference, federal)
        dest = source[source.accepted_source_endpoint].reset_index(drop=True)
        origins = reference.iloc[[0]].copy()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'costs.npy'
            costs = np.lib.format.open_memmap(path, mode='w+', dtype='float64', shape=(1, 4))
            costs[:] = np.nan
            context = {'graph': graph, 'origins': origins, 'source_by_id': source.set_index('source_record_id'),
                'dest': dest, 'dest_ids': dest.source_record_id.to_numpy(),
                'dest_nodes': dest.road_node_index.to_numpy(int), 'dest_connectors': np.zeros(4),
                'dest_mass': dest.field_mass_2021.to_numpy(float),
                'ordinary_dest': np.array([True, False, False, False]),
                'federal_dest': np.array([False, True, True, False]),
                'mass_dest': np.array([True, True, True, False]),
                'outside_dest': np.array([False, False, False, True]),
                'crimea_dest': np.zeros(4, dtype=bool),
                'sevastopol_dest': np.array([False, False, False, True]),
                'raw_dest_pop': dest.population_2021.to_numpy(float),
                'unmapped': source[source.source_record_id.eq('unlocated')],
                'outside_unmapped': source.iloc[:0], 'unlocated_mass': 39.,
                'city_indices': [1, 2, 3], 'cost_cache_path': str(path), 'half_times': [10.]}
            _init_unbounded(context)
            _, rows, cities = _unbounded_origin(0)
            result = pd.DataFrame(rows)
            included = result[result.kernel.eq('exponential') & result.include_self].iloc[0]
            excluded = result[result.kernel.eq('exponential') & ~result.include_self].iloc[0]
            self.assertEqual(included.ordinary_known_field, 100.)
            self.assertEqual(included.federal_context_field, 625.)
            self.assertEqual(included['value'], 725.)
            self.assertEqual(excluded['value'], 625.)
            self.assertEqual(included.unmapped_mass_upper, 39.)
            self.assertEqual(included.accepted_mass_field_upper, 764.)
            self.assertEqual(included.tail_upper, 0.)
            self.assertEqual(included.outside_frame_sevastopol_routed_reference_contribution, 250.)
            np.testing.assert_array_equal(np.load(path)[0], [0., 10., 20., 30.])
            self.assertFalse(next(r for r in cities if r['city_id'] == 'sev')['in_accepted_federal_territory_mass'])

    def test_missing_origin_is_unknown_not_zero_potential(self):
        reference, federal, _ = self.fixture()
        source = mass_sources(reference, federal).set_index('source_record_id')
        rows = _unknown_origin_fields(reference.iloc[1], 1, source)
        self.assertEqual(len(rows), 36)
        self.assertTrue(all(np.isnan(r['value']) for r in rows))
        self.assertTrue(all(r['own_credited_mass'] == 39. for r in rows))

    def test_unbounded_search_keeps_far_mass_and_distinguishes_graph_unreachable(self):
        reference, federal, _ = self.fixture()
        source = mass_sources(reference, federal)
        dest = source[source.accepted_source_endpoint].reset_index(drop=True)
        # Moscow is farther than the old 480-minute cutoff; SPb has no path
        # in this synthetic directed road graph. Neither case is missing data.
        graph = csr_matrix(([600.], ([0], [1])), shape=(4, 4))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'costs.npy'
            cache = np.lib.format.open_memmap(path, mode='w+', dtype='float64', shape=(1, 4))
            context = {'graph': graph, 'origins': reference.iloc[[0]],
                'source_by_id': source.set_index('source_record_id'), 'dest': dest,
                'dest_ids': dest.source_record_id.to_numpy(),
                'dest_nodes': dest.road_node_index.to_numpy(int), 'dest_connectors': np.zeros(4),
                'dest_mass': dest.field_mass_2021.to_numpy(float),
                'ordinary_dest': np.array([True, False, False, False]),
                'federal_dest': np.array([False, True, True, False]),
                'mass_dest': np.array([True, True, True, False]),
                'outside_dest': np.array([False, False, False, True]),
                'crimea_dest': np.zeros(4, dtype=bool),
                'sevastopol_dest': np.array([False, False, False, True]),
                'raw_dest_pop': dest.population_2021.to_numpy(float),
                'unmapped': source[source.source_record_id.eq('unlocated')],
                'outside_unmapped': source.iloc[:0], 'unlocated_mass': 39.,
                'city_indices': [1, 2], 'cost_cache_path': str(path), 'half_times': [120.]}
            _init_unbounded(context)
            _, rows, cities = _unbounded_origin(0)
            row = next(r for r in rows if r['kernel'] == 'exponential' and r['include_self'])
            self.assertEqual(row['federal_context_field'], 31.25)
            self.assertEqual(row['known_field'], 131.25)
            self.assertEqual(row['tail_upper'], 0.)
            self.assertEqual(row['unmapped_mass_upper'], 39.)
            self.assertEqual(cities[0]['cost_minutes'], 600.)
            self.assertEqual(cities[1]['status'], 'unreachable_in_directed_graph_model')
            self.assertTrue(np.isposinf(cities[1]['cost_minutes']))
            np.testing.assert_array_equal(np.load(path)[0], [0., 600., np.inf, np.inf])

    def test_full_pass_checkpoint_resume_preserves_costs_fields_and_unknown_rows(self):
        reference, federal, graph = self.fixture()
        reference['name'] = reference.source_record_id
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fields = root/'fields'
            fields.mkdir()
            reference.to_parquet(fields/'national_reference_with_endpoints.parquet', index=False)
            regional = reference.iloc[:2].copy()
            regional.to_parquet(fields/'regional_roster.parquet', index=False)
            regional.iloc[:0].to_parquet(fields/'halo_roster.parquet', index=False)
            dest = reference[reference.accepted_source_endpoint].reset_index(drop=True)
            dest['destination_index'] = np.arange(len(dest))
            dest['destination_connector_minutes'] = 0.
            dest.to_parquet(fields/'destinations.parquet', index=False)
            pd.DataFrame({'source_record_id': ['a']}).to_parquet(fields/'fields.parquet', index=False)
            pd.DataFrame({'source_record_id': []}).to_parquet(fields/'halo_fields.parquet', index=False)
            (fields/'summary.json').write_text('{}')
            federal.to_csv(root/'federal.csv', index=False)
            args = (fields, root/'federal.csv', root, root/'unused-catalog.json', root/'out', root/'cache')
            with patch('scripts.sgrt_saratov.population_mass_scope.verify_federal_csv'), \
                 patch('scripts.sgrt_saratov.population_mass_scope.load_graph', return_value=graph):
                run_unbounded(*args, workers=1)
                first = pd.read_parquet(fields/'fields.parquet')
                first_costs = np.load(root/'cache/full_destination_costs.npy').copy()
                run_unbounded(*args, workers=1, resume=True)
                original_contract = (root/'cache/contract.json').read_bytes()
                with patch('scripts.sgrt_saratov.population_mass_scope.load_graph',
                           side_effect=AssertionError('Scalar refresh must not rerun routing')):
                    run_unbounded(*args, workers=1, refresh_from_cache=True)
                self.assertEqual((root/'cache/contract.json').read_bytes(), original_contract)
                tampered = np.load(root/'cache/full_destination_costs.npy', mmap_mode='r+')
                tampered[0, 0] = 1.
                tampered.flush()
                with self.assertRaisesRegex(ValueError, 'own zero cost'):
                    run_unbounded(*args, workers=1, refresh_from_cache=True)
                tampered[0, 0] = 0.
                tampered[1, 0] = 0.
                tampered.flush()
                with self.assertRaisesRegex(ValueError, 'entirely unknown cost rows'):
                    run_unbounded(*args, workers=1, refresh_from_cache=True)
                tampered[1, 0] = np.nan
                tampered.flush()
            pd.testing.assert_frame_equal(first, pd.read_parquet(fields/'fields.parquet'))
            np.testing.assert_array_equal(first_costs, np.load(root/'cache/full_destination_costs.npy'))
            self.assertTrue(np.isnan(first_costs[1]).all())
            self.assertEqual(len(first), 72)
            selected = first[first.source_record_id.eq('a') & first.kernel.eq('exponential')
                             & first.half_time.eq(10.) & first.include_self]
            self.assertEqual(selected.iloc[0]['value'], 725.)
            self.assertTrue(json.loads((root/'cache/complete.json').read_text())['complete'])


if __name__ == '__main__':
    unittest.main()

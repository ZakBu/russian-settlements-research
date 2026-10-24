"""Regressions for national routing, not desired catchment sizes."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

spec = importlib.util.spec_from_file_location(
    'mass_routes', Path(__file__).resolve().parents[1]/'scripts/sgrt_mass/routes.py')
routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routes)


def endpoints(ids, nodes, snaps=None, accepted=None):
    return pd.DataFrame({
        'origin_id': ids, 'source_record_id': ids, 'name': ids,
        'road_node_index': nodes, 'snap_km': snaps or [0.]*len(ids),
        'road_endpoint_accepted': accepted or [True]*len(ids),
        'road_endpoint_status': ['synthetic_test_endpoint']*len(ids),
        'road_connector_over_2km': [False]*len(ids),
    })


def supply(ids, statuses=None):
    return pd.DataFrame({'source_record_id': ids, 'provider_id': ['site:'+x for x in ids],
                         'service_code': ['school']*len(ids),
                         'supply_status': statuses or ['observed']*len(ids)})


class NationalRouteTests(unittest.TestCase):
    def test_missing_historical_identities_are_retained_without_null_key_loss(self):
        points = pd.DataFrame({'source_record_id':['known','missing-a','missing-b','moved'],
                               'root':['r1','r2','r3','r4'], 'lat':[54.,54.,54.,54.1], 'lon':[59.]*4})
        legacy = pd.DataFrame({'source_record_id_2021':['known','moved'],
                               'root':['r1','r4'], 'id':['old-known','old-moved'],
                               'lat':[54.,54.], 'lon':[59.,59.]})
        road = pd.DataFrame({'id':['old-known','old-moved'],'road_node_index':[0,1],
                             'snap_km':[0.,0.], 'weak_component':[0,0], 'accepted_snap':[True,True],
                             'road_snap_lat':[54.,54.], 'road_snap_lon':[59.,59.],
                             'connector_scenario_kmh':[15,15]})
        result = routes.prepare_endpoints(points, legacy, road).set_index('source_record_id')
        self.assertEqual(len(result), 4)
        self.assertEqual(result.road_endpoint_accepted.sum(), 1)
        self.assertEqual(result.loc['missing-a','road_endpoint_status'], 'no_exact_road_identity')
        self.assertEqual(result.loc['missing-b','road_endpoint_status'], 'no_exact_road_identity')
        self.assertEqual(result.loc['moved','road_endpoint_status'], 'accepted_census_point_differs_from_historical_road_point')

    def test_destination_connector_changes_the_optimal_provider(self):
        # A is nearest by road alone, B is nearest by complete access cost.
        graph = csr_matrix(np.array([[0., 1., 3.], [0., 0., 0.], [0., 0., 0.]]))
        dist, selected = routes.weighted_multisource(graph.T.tocsr(), [1,2], [10.,0.])
        self.assertEqual(selected[0], 1)
        self.assertAlmostEqual(dist[0], 3.)

    def test_direction_is_not_reversed_and_nonzero_seed_cost_is_retained(self):
        graph = csr_matrix(np.array([[0., 2.], [30., 0.]]))
        dist, selected = routes.weighted_multisource(graph.T.tocsr(), [1], [3.])
        self.assertAlmostEqual(dist[0], 5.)
        self.assertAlmostEqual(dist[1], 3.)
        self.assertTrue(np.all(selected == 0))

    def test_shared_seed_ties_are_visible_and_local_zero_is_explicit(self):
        graph = csr_matrix(np.array([[0.,2.],[0.,0.]]))
        ep = endpoints(['origin','provider-a','provider-b'], [0,1,1], [.1,1.,1.])
        providers,_ = routes.provider_settlements(supply(['provider-a','provider-b']), ep, 'school')
        result = routes.nearest_for_service(ep, providers, graph.T.tocsr(), 'school').set_index('origin_id')
        self.assertIn(result.loc['origin','selected_provider_source_record_id'], {'provider-a','provider-b'})
        self.assertAlmostEqual(result.loc['origin','cost_minutes'], 6.4)
        self.assertEqual(result.loc['origin','nearest_tie_count_lower_bound'], 2)
        self.assertIn('known_shared_road_seed_tie', result.loc['origin','tie_status'])
        self.assertFalse(result.loc['origin','geographic_ties_exhaustively_checked'])
        self.assertEqual(result.loc['provider-a','selected_provider_source_record_id'], 'provider-a')
        self.assertEqual(result.loc['provider-a','cost_minutes'], 0.)
        self.assertTrue(result.loc['provider-a','zero_cost_np_assumption'])

    def test_equal_paths_at_different_seeds_do_not_claim_unique_choice(self):
        graph = csr_matrix(np.array([[0.,2.,2.],[0.,0.,0.],[0.,0.,0.]]))
        ep = endpoints(['origin','provider-a','provider-b'], [0,1,2])
        providers,_ = routes.provider_settlements(supply(['provider-a','provider-b']), ep, 'school')
        result = routes.nearest_for_service(ep, providers, graph.T.tocsr(), 'school').set_index('origin_id')
        self.assertAlmostEqual(result.loc['origin','cost_minutes'], 2.)
        self.assertFalse(result.loc['origin','geographic_ties_exhaustively_checked'])
        self.assertEqual(result.loc['origin','tie_status'], 'other_equal_geographic_paths_not_exhaustively_checked')

    def test_missing_route_and_unaccepted_origin_never_become_zero(self):
        graph = csr_matrix((3,3), dtype=float)
        ep = endpoints(['isolated','provider','unaccepted'], [0,1,np.nan], accepted=[True,True,False])
        providers,_ = routes.provider_settlements(supply(['provider']), ep, 'school')
        result = routes.nearest_for_service(ep, providers, graph.T.tocsr(), 'school').set_index('origin_id')
        self.assertTrue(np.isnan(result.loc['isolated','cost_minutes']))
        self.assertEqual(result.loc['isolated','route_status'], 'no_directed_route_to_known_eligible_provider')
        self.assertTrue(np.isnan(result.loc['unaccepted','cost_minutes']))
        self.assertEqual(result.loc['unaccepted','route_status'], 'origin_road_endpoint_unavailable')

    def test_unknown_supply_and_hundred_duplicate_sites_do_not_gain_mass(self):
        graph = csr_matrix(np.array([[0.,2.,10.],[0.,0.,0.],[0.,0.,0.]]))
        ep = endpoints(['origin','near','city'], [0,1,2])
        rows = pd.concat([supply(['near','city']), supply(['city']*99), supply(['origin'], ['unknown'])], ignore_index=True)
        providers,_ = routes.provider_settlements(rows, ep, 'school')
        self.assertEqual(len(providers), 2)
        result = routes.nearest_for_service(ep, providers, graph.T.tocsr(), 'school').set_index('origin_id')
        self.assertEqual(result.loc['origin','selected_provider_source_record_id'], 'near')
        self.assertEqual(result.loc['origin','local_supply_status'], 'unknown')
        self.assertTrue(result.loc['origin','missing_local_supply_could_change_choice'])
        self.assertFalse(result.loc['origin','assignment_established'])

    def test_known_local_supply_without_road_snap_is_not_erased(self):
        ep = endpoints(['local'], [np.nan], accepted=[False])
        providers,_ = routes.provider_settlements(supply(['local']), ep, 'school')
        result = routes.nearest_for_service(ep, providers, csr_matrix((1,1)), 'school').iloc[0]
        self.assertEqual(result.cost_minutes, 0.)
        self.assertTrue(result.zero_cost_np_assumption)
        self.assertEqual(result.routable_known_provider_settlements, 0)

    def test_actual_site_without_np_identity_is_routed_without_fake_local_service(self):
        graph = csr_matrix(np.array([[0.,2.],[0.,0.]]))
        ep = endpoints(['origin'], [0])
        sites = pd.DataFrame({'provider_id':['osm:node:1'], 'service_code':['school'],
                              'supply_status':['observed'],'road_node_index':[1], 'snap_km':[0.],
                              'accepted_snap':[True],'site_lat':[54.], 'site_lon':[59.],
                              'source_record_id':[None], 'proxy_reference_source_record_id':['origin']})
        providers = routes.site_providers(sites, 'school')
        result = routes.nearest_for_sites(ep, providers, graph.T.tocsr(), 'school').iloc[0]
        self.assertEqual(result.provider_id, 'osm:node:1')
        self.assertTrue(pd.isna(result.selected_provider_source_record_id))
        self.assertEqual(result.selected_provider_proxy_reference_source_record_id, 'origin')
        self.assertEqual(result.cost_minutes, 2.)
        self.assertFalse(result.zero_cost_np_assumption)
        self.assertEqual(result.local_supply_status, 'unknown')
        self.assertTrue(result.missing_local_supply_could_change_choice)

    def test_strict_local_site_overlay_retains_unconstrained_site_cost(self):
        graph = csr_matrix(np.array([[0.,2.],[0.,0.]]))
        ep = endpoints(['origin'], [0])
        sites = pd.DataFrame({'provider_id':['osm:node:1'], 'service_code':['school'],
                              'supply_status':['observed'],'road_node_index':[1], 'snap_km':[.5],
                              'accepted_snap':[True],'site_lat':[54.], 'site_lon':[59.],
                              'source_record_id':['origin']})
        providers = routes.site_providers(sites, 'school')
        result = routes.nearest_for_sites(ep, providers, graph.T.tocsr(), 'school').iloc[0]
        self.assertEqual(result.cost_minutes, 0.)
        self.assertEqual(result.unconstrained_nearest_site_cost_minutes, 4.)
        self.assertTrue(result.zero_cost_np_assumption)
        self.assertEqual(result.candidate_unit_kind, 'institution_site_not_settlement')

    def test_closed_or_future_sites_do_not_attract_even_when_closer(self):
        graph = csr_matrix(np.array([[0.,1.,5.],[0.,0.,0.],[0.,0.,0.]]))
        ep = endpoints(['origin'], [0])
        sites = pd.DataFrame({'provider_id':['closed','not-yet-open','active'],
                              'service_code':['school']*3,
                              'supply_status':['excluded_lifecycle','excluded_temporal','observed'],
                              'road_node_index':[1,1,2], 'snap_km':[0.]*3,
                              'accepted_snap':[True]*3,'site_lat':[54.]*3,'site_lon':[59.]*3,
                              'source_record_id':[None]*3})
        providers = routes.site_providers(sites, 'school')
        self.assertEqual(providers.provider_id.tolist(), ['active'])
        result = routes.nearest_for_sites(ep, providers, graph.T.tocsr(), 'school').iloc[0]
        self.assertEqual(result.provider_id, 'active')
        self.assertEqual(result.cost_minutes, 5.)

    def test_fresh_resnap_changes_geometry_not_census_identity(self):
        ep = endpoints(['missing'], [np.nan], accepted=[False])
        ep['root'] = 'unchanged-root'
        ep['lat'], ep['lon'] = 54., 59.
        ep['road_snap_lat'], ep['road_snap_lon'] = np.nan, np.nan
        ep['road_identity_basis'] = 'no_exact_road_identity'
        ep['accepted_snap'] = False
        ep['weak_component'], ep['connector_scenario_kmh'] = np.nan, 15.
        fresh = pd.DataFrame({'source_record_id':['missing'],'root':['unchanged-root'],
                               'lat':[54.],'lon':[59.],'road_node_index':[1], 'snap_km':[.1],
                               'road_snap_lat':[54.001],'road_snap_lon':[59.], 'weak_component':[0],
                               'road_endpoint_accepted':[True], 'connector_scenario_kmh':[15.],
                               'census_identity_changed':[False], 'legacy_identity_used':[False]})
        result = routes.apply_fresh_resnaps(ep, fresh).iloc[0]
        self.assertEqual(result.source_record_id, 'missing')
        self.assertEqual(result.root, 'unchanged-root')
        self.assertTrue(result.road_endpoint_accepted)
        self.assertFalse(result.historical_road_endpoint_accepted)
        self.assertIn('fresh_', result.road_identity_basis)
        bad = fresh.copy()
        bad.loc[0,'root'] = 'guessed-other-settlement'
        with self.assertRaisesRegex(ValueError, 'roots differ'):
            routes.apply_fresh_resnaps(ep, bad)
        bad = fresh.copy()
        bad.loc[0,'lat'] = 55.
        with self.assertRaisesRegex(ValueError, 'accepted current census coordinates'):
            routes.apply_fresh_resnaps(ep, bad)


if __name__ == '__main__':
    unittest.main()

"""Regression controls for the scientific errors behind the197-centre count."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts/sgrt_zero'))
from scripts.sgrt_zero.transport import reuse_prepared_geometry
from scripts.sgrt_zero.education import np_offers
from scripts.sgrt_zero.centre_stars import build_centre_stars
from scripts.sgrt_zero.level0_centres import build
from scripts.sgrt_zero.cartographic_identity import literal_localities
from scripts.sgrt_zero.explicit_locality_identity import ExplicitLocalityIndex
from scripts.sgrt_zero.medical_need_review import review_medical_need_scope, review_np_presence_after_site_holds
from scripts.sgrt_zero.repair_source_identities import hold_existing_owner_conflicts
from scripts.sgrt_zero.commerce import np_offers as commerce_offers
from scripts.sgrt_zero.screens import with_admission


class IdentityPipelineTests(unittest.TestCase):
    def test_bad_coordinate_cannot_assign_a_near_or_local_service_territory(self):
        frame=pd.DataFrame({'provider_site_id':['local','near'], 'cost_minutes':[0.,5.],
            'local_service_present':[True,False], 'origin_coordinate_location_held':[True,False],
            'provider_coordinate_location_held':[False,True], 'routable_external_provider_seeds':[1,1],
            'known_offer_records':[1,1], 'origin_road_endpoint_accepted':[True,True]})
        result=with_admission(frame,'grocery','daily_grocery','fixture',20.,'fixture')
        self.assertFalse(result.l0_admitted.any())
        self.assertEqual(result.service_status.tolist(),['held_named_settlement_coordinate_conflict']*2)
        self.assertEqual(result.local_service_present.tolist(),[True,False])
        pd.testing.assert_series_equal(frame.cost_minutes,result.cost_minutes)

    def test_medical_np_presence_requires_an_unheld_site_or_independent_registry(self):
        offers = pd.DataFrame({'source_record_id':['a','b','c'], 'service_code':['medical_basic_primary']*3,
            'source_id':['["OSM_fixture"]']*3, 'has_official_registry':[False,False,True],
            'local_supply_eligible':[True]*3})
        sites = pd.DataFrame({'source_record_id':['a','b','b','c'], 'service_code':['medical_basic_primary']*4,
            'supply_status':['proxy']*4, 'route_eligible':[False,False,True,False]})
        checked = review_np_presence_after_site_holds(offers,sites)
        self.assertEqual(checked.route_eligible.tolist(),[False,True,True])
        self.assertEqual(checked.local_supply_eligible.tolist(),[False,True,True])
        pd.testing.assert_series_equal(offers.source_id,checked.source_id)

    def test_old_owner_conflict_is_not_silently_retained_as_active_supply(self):
        old = pd.DataFrame({'source_record_id':['city','village'],
            'source_record_id_before_identity_repair':['city','village'],
            'cartographic_identity_status':['held_existing_source_owner_conflict','cartographic_containment_no_literal_locality'],
            'route_eligible':[True,True], 'identity_evidence_tier':['legacy','legacy'],
            'np_identity_basis':['raw_address','raw_address']})
        result = hold_existing_owner_conflicts(old)
        self.assertEqual(result.route_eligible.tolist(), [False,True])
        pd.testing.assert_series_equal(old.source_record_id,result.source_record_id)
        self.assertIn('held',result.identity_evidence_tier.iloc[0])

    def test_literal_status_cannot_hide_a_different_old_owner(self):
        frame=pd.DataFrame({'source_record_id':['city','village'],
            'source_record_id_before_identity_repair':['city','village'],
            'cartographic_candidate_source_record_id':['village','city'],
            'cartographic_identity_status':['held_literal_locality_conflict']*2,
            'cartographic_contains_other_census_places':[False,True], 'route_eligible':[True,True],
            'identity_evidence_tier':['legacy']*2,'np_identity_basis':['raw']*2})
        checked=hold_existing_owner_conflicts(frame)
        self.assertEqual(checked.route_eligible.tolist(),[False,True])
        # An unresolved coarse parent polygon cannot overrule a finer old claim.
        pd.testing.assert_series_equal(frame.source_record_id,checked.source_record_id)

    def test_held_buildings_cannot_reappear_as_zero_cost_np_aggregates(self):
        sites = pd.DataFrame([dict(eligible=True,route_eligible=False,source_record_id='a',
            service_code='school_general',observation_year=2026,source_year=2026,
            source_snapshot='2026-10-26',supply_status='observed',source_id='fixture',provider_id='school')])
        reference = pd.DataFrame([dict(source_record_id='a',lat=50.,lon=40.,region='region',
            population_role='ordinary_settlement_record',ordinary_spatial_2021=True)])
        official = pd.DataFrame(columns=['supply_status','source_record_id'])
        self.assertTrue(np_offers(sites,official,reference).empty)
        self.assertTrue(commerce_offers(sites).empty)

    def test_specialized_clinic_and_departmental_access_are_not_universal_primary_proof(self):
        frame = pd.DataFrame({'provider_name':['Поликлиника лечения позвоночника',
                           'Поликлиника №1 Управления делами Президента РФ', 'Сельская амбулатория'],
                              'service_code':['medical_basic_primary'] * 3, 'supply_status':['proxy'] * 3})
        result = review_medical_need_scope(frame)
        self.assertEqual(result.route_eligible.tolist(), [False, False, True])
        pd.testing.assert_series_equal(frame.supply_status, result.supply_status)

    def test_actual_full_address_overrides_an_unrelated_map_location(self):
        row = {'source_addr_full': '215642, Смоленская область, Холм-Жирковский район, село Боголюбово, Суворова ул.,2'}
        self.assertEqual(literal_localities(row), {'боголюбово'})
        for address, expected in [('рп Рогнедино, Улица 40 Лет Победы 3', 'рогнедино'),
                                  ('аул Новая Адыгея, Урюковая Улица 12', 'новая адыгея'),
                                  ('село Родниково, Бахчисарайская Улица 9', 'родниково')]:
            self.assertEqual(literal_localities({'activity_address': address}), {expected})

    def test_house_numbers_and_institution_names_are_not_address_localities(self):
        self.assertEqual(literal_localities({'activity_address': 'Иркутская область, Ангарск,278кв-л,1,д.1А'}), set())
        self.assertEqual(literal_localities({'name': 'Филиал школы с. Шигоны', 'source_addr_full': 'улица С.П. Королёва, 1'}), set())

    def test_independent_polygon_can_resolve_a_literal_homonym_without_nearest(self):
        ref = pd.DataFrame([dict(source_record_id=sid, name='Питерка', region=region, district='район',
                                settlement_type_2021='село', lat=50., lon=40.)
                            for sid, region in [('a', 'саратовская'), ('b', 'тамбовская')]])
        result = ExplicitLocalityIndex(ref).match({'tags_json': '{"addr:city":"Питерка"}',
                                                 'verified_boundary_source_record_id': 'b', 'lat':50., 'lon':40.})
        self.assertEqual(result['explicit_locality_source_record_id'], 'b')

    def geometry(self, *, kind='np', external=False):
        old = pd.DataFrame([dict(provider_id='old', source_record_id='a', input_kind=kind,
            site_lat=50., site_lon=40., road_node_index=1, snap_km=.1, accepted_snap=True)])
        new = pd.DataFrame([dict(provider_id='new', source_record_id='b', input_kind=kind,
            site_lat=51., site_lon=41., default_external_seed_eligible=external, admitted_offer=True)])
        return old, new

    def test_local_presence_does_not_invent_an_external_snap(self):
        old, new = self.geometry()
        result = reuse_prepared_geometry(new, old, allow_local_presence_without_geometry=True)
        self.assertFalse(result.external_seed_eligible.iloc[0])
        self.assertFalse(result.road_endpoint_accepted.iloc[0])
        self.assertTrue(pd.isna(result.road_node_index.iloc[0]))

    def test_external_np_and_moved_building_still_require_real_geometry(self):
        for kind, external in [('np', True), ('sites', False)]:
            old, new = self.geometry(kind=kind, external=external)
            with self.assertRaisesRegex(ValueError, 'new or moved'):
                reuse_prepared_geometry(new, old, allow_local_presence_without_geometry=True)

    def test_np_aggregation_does_not_turn_cartography_into_literal_address(self):
        sites = pd.DataFrame([dict(eligible=True, source_record_id='a', service_code='school_general',
            observation_year=2026, source_id='fixture', provider_id='school',
            identity_evidence_tier='dated_cartographic_locality_containment')])
        ref = pd.DataFrame([dict(source_record_id='a', lat=50., lon=40., region='region',
            population_role='ordinary_settlement_record', ordinary_spatial_2021=True)])
        official = pd.DataFrame(columns=['supply_status', 'source_record_id'])
        offers = np_offers(sites, official, ref)
        self.assertIn('cartographic', offers.evidence_quality.iloc[0])
        self.assertNotIn('exact_census_bridge', offers.evidence_quality.iloc[0])
        self.assertEqual(offers.identity_evidence_tier.iloc[0], 'dated_cartographic_locality_containment')

    def test_full_centre_survives_when_different_neighbours_use_different_services(self):
        ref = pd.DataFrame(dict(source_record_id=['a', 'b', 'c'], name=['A', 'B', 'C'], region='region', district='district',
            lat=[50., 50.01, 50.02], lon=[40., 40.01, 40.02], population_2021=[10., 20., 100.],
            population_role='ordinary_settlement_record', budget_population_credit=True, analysis_origin=True))
        profiles = {'a': {'school': 'c'}, 'b': {'medical_basic': 'c'},
                    'c': {'school': 'c', 'medical_basic': 'c', 'grocery': 'c'}}
        edges = pd.DataFrame([dict(origin_id=o, service_family=f, provider_settlement_id=p,
            provider_site_id='site-' + p, cost_minutes=5., l0_admitted=True,
            admission_basis='test', scenario_id='test', school_stage_unknown=True)
            for o, values in profiles.items() for f, p in values.items()])
        tables, old_summary = build_centre_stars(edges, ref)
        self.assertEqual(old_summary['strict_three_core_model_screened_stars'], 0)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, frame in tables.items():
                frame.to_parquet(folder / (name + '.parquet'), index=False)
            edges.to_parquet(folder / 'daily_edges.parquet', index=False)
            with contextlib.redirect_stdout(io.StringIO()):
                result = build(folder, folder / 'registry')
            self.assertEqual(result['registered_level0_centres'], 1)
            self.assertEqual(result['full_three_function_centres_with_external_participants'], 1)
            self.assertEqual(result['strict_same_three_external_diagnostic_subset'], 0)

    def test_population_accounting_does_not_remove_a_physical_centre_or_neighbour(self):
        ref = pd.DataFrame(dict(source_record_id=['a', 'b'], name=['A', 'B'], region='region', district='district',
            lat=[50., 50.01], lon=[40., 40.01], population_2021=[10., 100.],
            population_role='ordinary_settlement_record', budget_population_credit=[False, False], analysis_origin=True))
        rows = [('a', 'school', 'b'), ('b', 'school', 'b'), ('b', 'medical_basic', 'b'), ('b', 'grocery', 'b')]
        edges = pd.DataFrame([dict(origin_id=o, service_family=f, provider_settlement_id=p,
            provider_site_id='site-' + p, cost_minutes=5., l0_admitted=True,
            admission_basis='test', scenario_id='test', school_stage_unknown=True) for o,f,p in rows])
        tables, _ = build_centre_stars(edges, ref)
        self.assertEqual(tables['centre_stars'].one_or_more_core_external_positive_whole.iloc[0], 1)
        self.assertTrue(tables['centre_memberships'].budget_population_within_star.isna().all())
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, frame in tables.items(): frame.to_parquet(folder / (name + '.parquet'), index=False)
            edges.to_parquet(folder / 'daily_edges.parquet', index=False)
            with contextlib.redirect_stdout(io.StringIO()): result = build(folder, folder / 'registry')
            self.assertEqual(result['registered_level0_centres'], 1)
            self.assertEqual(result['centres_with_partial_population_budget'], 1)


if __name__ == '__main__':
    unittest.main()

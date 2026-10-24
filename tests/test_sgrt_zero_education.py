import sys
from pathlib import Path
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.education import build_sites, np_offers, school_orders, parse_literal_levels, regional_coverage, FEDERAL_CITY_IDS


def reference():
    return pd.DataFrame({'root':['root-a','root-b','root-m'],
        'source_record_id':['a','b','m'],'name':['А','Б','Москва'],
        'region':['вологодская','вологодская','москва'],
        'population_role':['ordinary_settlement_record','ordinary_settlement_record','external_context_nonadditive'],
        'ordinary_spatial_2021':[True,True,False],
        'lat':[59.,59.1,55.75],'lon':[39.,39.1,37.62]})


def legacy():
    r=reference();return pd.DataFrame({'id':['old-a','old-b','old-m'],'root':r.root,
        'source_record_id_2021':r.source_record_id,'name':r.name,'region':r.region,'lat':r.lat,'lon':r.lon})


def objects(**changes):
    d={'site_id':'osm:node:1','education_group':'school','source_snapshot':'2026-10-19T20:21:11Z',
       'lat':59.,'lon':39.,'tags_json':'{"amenity":"school"}',
       'baseline_uid':'old-a','candidate_uid':None,'source_address_locality':'А',
       'source_address_state':None,'link_status':'explicit_address_locality_unique_within5km',
       'possible_duplicate_of':None,'source_start_date':None,'source_end_date':None,'name':'Средняя школа №11'}
    d.update(changes);return pd.DataFrame([d])


def official():
    return pd.DataFrame([{'provider_id':'official:'+s,'source_record_id':s,'service_code':'preschool_official',
        'source_id':'ROSSTAT_NP2025_PRIMARY_BOOKS','observation_year':2025,'supply_status':'observed',
        'known_positive_source_rows':1,'capacity_total':100.,'capacity_unit':'total_preschool_places_not_vacant_places'} for s in ['a','b']])


class ZeroEducationTest(unittest.TestCase):
    def test_literal_identity_is_separate_from_nearest_geometry(self):
        a=build_sites(objects(),reference(),legacy())
        self.assertEqual(a.source_record_id.iloc[0],'a')
        b=build_sites(objects(link_status='spatial_candidate_within2_5km_separated_not_identity_proof',baseline_uid=None,candidate_uid='old-a'),reference(),legacy())
        self.assertIsNone(b.source_record_id.iloc[0])
        self.assertTrue(b.eligible.iloc[0])
        self.assertEqual(b.nearest_reference_source_record_id.iloc[0],'a')
        self.assertFalse(b.nearest_reference_is_identity.iloc[0])

    def test_explicit_status_alone_does_not_override_name_conflict_or_empty_name(self):
        for name in ['Б',None,'']:
            d=build_sites(objects(source_address_locality=name),reference(),legacy())
            self.assertIsNone(d.source_record_id.iloc[0])

    def test_source_year_is_read_from_snapshot(self):
        new=build_sites(objects(),reference(),legacy())
        old=build_sites(objects(source_snapshot='2021-01-01'),reference(),legacy())
        self.assertEqual(new.observation_year.iloc[0],2026)
        self.assertEqual(old.observation_year.iloc[0],2021)
        self.assertNotEqual(new.source_id.iloc[0],old.source_id.iloc[0])

    def test_inactive_and_proven_date_conflicts_are_excluded(self):
        for change in [{'tags_json':'{"amenity":"school","abandoned":"yes"}'},
                       {'tags_json':'{"amenity":"school","disused:amenity":"school"}'},
                       {'source_end_date':'2016'},{'source_start_date':'2027'}]:
            d=build_sites(objects(**change),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertNotEqual(d.supply_status.iloc[0],'observed')
        uncertain=build_sites(objects(source_end_date='2026'),reference(),legacy())
        self.assertTrue(uncertain.eligible.iloc[0])

    def test_specialized_duplicate_and_invalid_geometry_retained_but_excluded(self):
        for change in [{'education_group':'specialized_non_general_school'},
                       {'possible_duplicate_of':'osm:way:2'},{'lat':95.}]:
            d=build_sites(objects(**change),reference(),legacy())
            self.assertEqual(len(d),1)
            self.assertFalse(d.eligible.iloc[0])

    def test_school_name_never_creates_grade_evidence(self):
        d=build_sites(objects(name='Средняя школа №11'),reference(),legacy())
        self.assertTrue(school_orders(d).empty)
        self.assertFalse(d.grade_inferred_from_name_or_population.iloc[0])

    def test_explicit_isced_does_not_imply_lower_levels(self):
        d=build_sites(objects(source_isced_level='3'),reference(),legacy())
        a=school_orders(d)
        self.assertEqual(a.service_code.tolist(),['school_upper_secondary'])
        self.assertFalse(a.complete_stage_offering_established.any())
        d=build_sites(objects(source_grades='5-11'),reference(),legacy())
        self.assertEqual(set(school_orders(d).service_code),{'school_lower_secondary','school_upper_secondary'})
        self.assertEqual(parse_literal_levels('11-1',1,12),[])
        self.assertEqual(parse_literal_levels('1;2;3'),[1,2,3])

    def test_official_centroid_not_added_on_top_of_own_strict_osm_site(self):
        sites=build_sites(objects(education_group='preschool'),reference(),legacy())
        d=np_offers(sites,official(),reference())
        own=d[d.source_pool.eq('osm_strict_np_presence')]
        self.assertFalse(own.default_external_seed_eligible.any())
        obs=d[d.source_pool.eq('official_preschool_np2025')].set_index('source_record_id')
        self.assertFalse(obs.loc['a','default_external_seed_eligible'])
        self.assertTrue(obs.loc['b','default_external_seed_eligible'])
        self.assertTrue(d.np_offer_rows_are_not_institution_counts.all())

    def test_unknown_site_does_not_cancel_official_np_presence(self):
        sites=build_sites(objects(education_group='preschool',link_status='unresolved_no_locality_identity',baseline_uid=None),reference(),legacy())
        d=np_offers(sites,official(),reference())
        self.assertTrue(d.default_external_seed_eligible.all())
        self.assertFalse(d.capacity_is_vacant_places.any())

    def test_federal_context_with_zero_ordinary_denominator_is_unknown_fraction(self):
        sites=build_sites(objects(lat=55.75,lon=37.62,baseline_uid='old-m',source_address_locality='Москва'),reference(),legacy())
        offers=np_offers(sites,official(),reference())
        c=regional_coverage(sites,offers,reference())
        m=c[c.region.eq('москва')]
        self.assertTrue(m.np_known_offer_fraction.isna().all())
        self.assertEqual(int(m.eligible_source_sites.sum()),1)

    def test_repeated_physical_identity_is_not_silently_replicated(self):
        a=objects()
        with self.assertRaisesRegex(ValueError,'Repeated OSM'):
            build_sites(pd.concat([a,a]),reference(),legacy())

    def test_explicit_non_general_school_profile_excluded_without_overriding_general_name(self):
        for name in ['Детская музыкальная школа №4','Школа английского языка','Автошкола']:
            d=build_sites(objects(name=name),reference(),legacy())
            self.assertFalse(d.eligible.iloc[0])
            self.assertTrue(bool(d.non_general_school_reason.iloc[0]))
        normal=build_sites(objects(name='Средняя общеобразовательная школа с углубленным изучением английского языка'),reference(),legacy())
        self.assertTrue(normal.eligible.iloc[0])
        tagged=build_sites(objects(tags_json='{"amenity":"school","school:type":"music"}'),reference(),legacy())
        self.assertFalse(tagged.eligible.iloc[0])

    def test_literal_known_region_conflict_holds_legacy_identity(self):
        d=build_sites(objects(source_address_state='Москва'),reference(),legacy())
        self.assertIsNone(d.source_record_id.iloc[0])
        self.assertTrue(d.literal_region_conflicts_with_legacy_identity.iloc[0])
        self.assertTrue(d.eligible.iloc[0])

    def test_federal_city_literal_address_preserves_context_role_without_nearest_identity(self):
        ref=reference();sid=FEDERAL_CITY_IDS['москва']
        ref.loc[ref.source_record_id.eq('m'),'source_record_id']=sid
        leg=legacy();leg.loc[leg.source_record_id_2021.eq('m'),'source_record_id_2021']=sid
        changes=dict(lat=55.9,lon=37.7,baseline_uid=None,link_status='unresolved_no_locality_identity',
            source_address_locality='Москва',tags_json='{"amenity":"school","addr:city":"Москва"}')
        d=build_sites(objects(**changes),ref,leg)
        self.assertEqual(d.source_record_id.iloc[0],sid)
        self.assertEqual(d.population_role.iloc[0],'external_context_nonadditive')
        self.assertFalse(d.nearest_reference_is_identity.iloc[0])
        bad=build_sites(objects(**changes,source_address_state='Вологодская область'),ref,leg)
        self.assertIsNone(bad.source_record_id.iloc[0])

    def test_derived_city_coordinate_fills_geography_only_not_identity_or_census(self):
        ref=reference();ref.loc[ref.source_record_id.eq('m'),['lat','lon']]=float('nan')
        ctx=pd.DataFrame({'source_record_id':['m'],'lat':[55.75],'lon':[37.62]})
        d=build_sites(objects(lat=55.75,lon=37.62,baseline_uid=None,source_address_locality=None,
            link_status='unresolved_no_locality_identity'),ref,legacy(),ctx)
        self.assertIsNone(d.source_record_id.iloc[0])
        self.assertEqual(d.region.iloc[0],'москва')
        self.assertTrue(d.region_is_proxy.iloc[0])
        self.assertTrue(d.nearest_reference_uses_derived_city_coordinate.iloc[0])
        self.assertTrue(ref.loc[ref.source_record_id.eq('m'),'lat'].isna().all())


if __name__=='__main__':
    unittest.main()

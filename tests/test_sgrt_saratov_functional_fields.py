import unittest
import tempfile
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.functional_fields import (
    documented_campus_proxies, select_functional_links, configuration_groups,
    functional_potentials, normalize_offers, FAMILIES)
from scripts.sgrt_saratov.functional_fields import build_functional_results
from scripts.sgrt_saratov.functional_fields import loss_counterfactual
from scripts.sgrt_saratov.functional_fields import basic_centre_profiles
from scripts.sgrt_saratov.functional_fields import summarize_units
from scripts.sgrt_saratov.functional_fields import refresh_functional_potentials,load_full_field_costs
from scipy.sparse import csr_matrix, save_npz


def roster():
    return pd.DataFrame({'source_record_id':['village','branch','city'], 'row_index':[0,1,2],
        'accepted_source_endpoint':[True]*3, 'population_2021':[50,100,1000000]})


def presence():
    return pd.DataFrame([{'family':'school','source_record_id':'city','known_presence':True,
        'historical_only':False,'operation_verified':False,'restriction_scope_unknown':True,
        'representative_catalog_id':'city-school','source_id':'["old"]','source_year':'[2026]',
        'any_nonhistorical_evidence':True}])


def catalogue():
    return pd.DataFrame([{'catalog_id':'city-school','family':'school',
        'correctsource_record_id':'city','historical_only':False, 'operation_verified':False,
        'restriction_scope_unknown':True,'source_id':'old','source_year':'2026'}])


def candidates():
    return pd.DataFrame([{'origin_id':'village','family':'school','catalog_id':'city-school',
        'destination_group_key':'np:city','cost_minutes':40.}])


class FunctionalFieldTests(unittest.TestCase):
    def test_far_offer_beyond_480_is_integrated_and_unknown_endpoint_bound_is_separate(self):
        r=roster().iloc[:1]
        dest=pd.DataFrame({'source_record_id':['village','a','b','c','d'],'destination_index':range(5)})
        p=pd.concat([presence().assign(source_record_id=sid) for sid in ['village','a','b','missing']])
        links,_=select_functional_links(r,p,candidates(),catalogue())
        truncated=csr_matrix((np.array([0.]),np.array([0]),np.array([0,1])),shape=(1,5))
        full=np.array([[0.,600.,np.inf,np.inf,np.inf]])
        result=functional_potentials(r,dest,truncated,p,links,half_times=(80.,),full_costs=full)
        x=result[result.family.eq('school')&result.kernel.eq('exponential')].iloc[0]
        self.assertAlmostEqual(x.known_np_offer_potential,1.+2.**(-600/80),places=14)
        self.assertAlmostEqual(x.external_known_np_offer_potential_lower,2.**(-600/80),places=14)
        self.assertAlmostEqual(x.known_np_offer_potential_upper,x.known_np_offer_potential+1.,places=14)
        self.assertEqual(x.known_np_offers_without_destination_endpoint,1)
        self.assertEqual(x.known_np_offers_unreachable_in_road_model,1)
        self.assertEqual(x.computational_tail_upper,0.)
        self.assertTrue(x.field_costs_unbounded)
        self.assertIsNone(x.field_integration_horizon_minutes)

    def test_uncomputed_full_row_is_never_treated_as_zero_or_unreachable(self):
        r=roster().iloc[:1]
        dest=pd.DataFrame({'source_record_id':['village','city'],'destination_index':[0,1]})
        p=presence().assign(source_record_id='village')
        links,_=select_functional_links(r,p,candidates(),catalogue())
        with self.assertRaisesRegex(ValueError,'incomplete or invalid'):
            functional_potentials(r,dest,None,p,links,half_times=(80.,),full_costs=np.array([[0.,np.nan]]))
        unknown=r.assign(accepted_source_endpoint=False)
        result=functional_potentials(unknown,dest,None,p,links,half_times=(80.,),full_costs=np.array([[np.nan,np.nan]]))
        x=result[result.family.eq('school')&result.kernel.eq('exponential')].iloc[0]
        self.assertTrue(pd.isna(x.known_np_offer_potential))
        self.assertEqual(x.known_np_offer_potential_lower,1.)
        self.assertFalse(x.origin_route_geometry_known)
        self.assertEqual(x.field_cost_status,'origin_endpoint_unavailable')
        with self.assertRaisesRegex(ValueError,'all-NaN'):
            functional_potentials(unknown,dest,None,p,links,half_times=(80.,),full_costs=np.array([[np.inf,np.inf]]))

    def test_zero_population_outlier_does_not_expand_positive_population_service_extent(self):
        m=pd.DataFrame({'evidence_scenario':['all_dated_known']*2,'system_id':['one']*2,
            'family':['grocery']*2,'destination_group_key':['np:city']*2,
            'origin_id':['village','ghost'],'population_2021':[50.,0.],
            'cost_minutes':[10.,100.],'model_choice_unique':[True]*2})
        unit=summarize_units(m,roster()).iloc[0]
        assert unit.maximum_selected_minutes==100
        assert unit.maximum_external_positive_minutes==10
        assert unit.external_positive_population_member_records==1

    def test_new_physical_shop_with_unknown_np_is_accessible_but_not_fictitious_np_supply(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);fields=base/'fields';providers=base/'providers';out=base/'out'
            fields.mkdir();providers.mkdir();r=roster()
            r.to_parquet(fields/'regional_roster.parquet',index=False)
            pd.DataFrame({'source_record_id':r.source_record_id,'destination_index':range(3)}).to_parquet(fields/'destinations.parquet',index=False)
            cost=np.array([[0.,5.,40.],[5.,0.,35.],[40.,35.,0.]])
            save_npz(fields/'destination_costs.npz',csr_matrix((cost.ravel(),np.tile(np.arange(3),3),np.arange(0,10,3)),shape=(3,3)))
            np.save(fields/'regional_costs.npy',cost)
            catalogue().to_parquet(providers/'provider_catalog.parquet',index=False)
            presence().to_parquet(providers/'np_function_presence.parquet',index=False)
            candidates().to_parquet(fields/'physical_provider_candidates.parquet',index=False)
            candidates().to_parquet(fields/'current.parquet',index=False)
            shop=catalogue().assign(catalog_id='new-shop',family='grocery',correctsource_record_id=None,
                provider_destination_key='site:new-shop',routable_provider=True)
            shop.to_parquet(base/'shops.parquet',index=False)
            route=candidates().assign(catalog_id='new-shop',family='grocery',destination_group_key='site:new-shop',cost_minutes=4.)
            route.to_parquet(base/'shop-routes.parquet',index=False)
            build_functional_results(fields,providers,out,current_candidates=fields/'current.parquet',
                supplementary_provider_catalog=base/'shops.parquet',supplementary_candidates=base/'shop-routes.parquet',
                single_inventory='physical_official_enrichment')
            links=pd.read_parquet(out/'functional_links.parquet')
            result=links[links.origin_id.eq('village')&links.family.eq('grocery')]
            assert result.cost_minutes.eq(4.).all() and result.provider_settlement_id.isna().all()
            assert result.inventory_scenario.eq('physical_official_enrichment').all()
            school=links[links.origin_id.eq('village')&links.family.eq('school')]
            assert school.provider_settlement_id.eq('city').all() and school.cost_minutes.eq(40.).all()
            p=pd.read_parquet(out/'np_function_presence_enriched.parquet')
            assert not p.family.eq('grocery').any()
            potential=pd.read_parquet(out/'functional_potentials.parquet')
            assert potential[potential.family.eq('grocery')].known_np_function_offer_count.eq(0).all()

    def test_historical_duplicate_organisations_give_one_np_and_vanish_from_current_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);fields=base/'fields';providers=base/'providers';out=base/'out'
            fields.mkdir();providers.mkdir()
            r=roster();r.to_parquet(fields/'regional_roster.parquet',index=False)
            pd.DataFrame({'source_record_id':r.source_record_id,'destination_index':range(3)}).to_parquet(fields/'destinations.parquet',index=False)
            cost=np.array([[0.,5.,40.],[5.,0.,35.],[40.,35.,0.]])
            save_npz(fields/'destination_costs.npz',csr_matrix((cost.ravel(),np.tile(np.arange(3),3),np.arange(0,10,3)),shape=(3,3)))
            np.save(fields/'regional_costs.npy',cost)
            catalogue().to_parquet(providers/'provider_catalog.parquet',index=False)
            presence().to_parquet(providers/'np_function_presence.parquet',index=False)
            candidates().to_parquet(fields/'physical_provider_candidates.parquet',index=False)
            candidates().to_parquet(fields/'current.parquet',index=False)
            pd.DataFrame([{'provider_id':'historic-'+str(i),'source_record_id':'branch',
                'service_code':'school_general','eligible_np_presence_proxy':True,
                'physical_route_seed_eligible':False,'source_id':'old_org_list','retrieval_year':2026,
                'source_year':None,'metadata_creation_year':2013,'metadata_last_modified_year':2014,
                'historical_only':True,'actual_operational_status_verified':False} for i in [1,2]]).to_csv(base/'historical.csv',index=False)
            build_functional_results(fields,providers,out,current_candidates=fields/'current.parquet',supplementary_presence=base/'historical.csv')
            links=pd.read_parquet(out/'functional_links.parquet')
            s=links[links.origin_id.eq('village')&links.family.eq('school')].set_index('evidence_scenario')
            assert s.loc['all_dated_known','provider_settlement_id']=='branch'
            assert s.loc['nonhistorical_evidence_only','provider_settlement_id']=='city'
            assert s.loc['all_dated_known','destination_is_np_proxy']
            assert 'not_current_building' in s.loc['all_dated_known','offer_evidence_scope']
            p=pd.read_parquet(out/'np_function_presence_enriched.parquet')
            assert len(p[p.source_record_id.eq('branch') & p.family.eq('school')])==1
            proxy=pd.read_parquet(out/'supplementary_np_offer_proxies.parquet')
            assert len(proxy)==1 and proxy.historical_only.all()
            assert proxy.iloc[0].source_year=='content_date_unknown'

    def test_basic_centre_counts_one_village_once_across_three_functions(self):
        r=roster().assign(budget_population_credit=1,credit_2021=1,
            settlement_type_2021=['деревня','село','город'])
        rows=[{'origin_id':'village','centre_id':'city','family':f,'cost_minutes':10.,
            'population_2021':50.,'model_choice_unique':True,'evidence_scenario':'all_dated_known'}
            for f in ['school','medical_basic','grocery']]
        rows.append({**rows[0],'origin_id':'branch','population_2021':100.,'cost_minutes':20.})
        p=pd.concat([presence().assign(family=f) for f in ['school','medical_basic','grocery']])
        profiles,members=basic_centre_profiles(r,pd.DataFrame(rows),p)
        assert len(members)==2 and len(profiles)==1
        profile=profiles.iloc[0]
        assert profile.external_positive_origin_count==2
        assert profile.external_credited_rural_population_2021==150
        assert profile.known_own_basic_function_count==3
        assert members[members.origin_id.eq('village')].iloc[0].contributing_basic_family_count==3

    def test_zero_final_population_stays_in_demographic_cohort_without_creating_service_demand(self):
        r=roster().assign(population_2021=[50.,0.,1000000.],population_2002=[70.,100.,800000.],
            population_2010=[60.,30.,900000.],budget_population_credit=True,credit_2021=True,
            settlement_type_2021=['деревня','деревня','город'])
        rows=[]
        for origin,pop,time in [('village',50.,10.),('branch',0.,100.)]:
            for family in ['school','medical_basic','grocery']:
                rows.append({'origin_id':origin,'centre_id':'city','family':family,'cost_minutes':time,
                    'population_2021':pop,'model_choice_unique':True,'evidence_scenario':'all_dated_known'})
        # A zero-population reference by itself must not turn village into a centre.
        rows.append({**rows[-1],'centre_id':'village'})
        supply=pd.concat([presence().assign(family=f) for f in ['school','medical_basic','grocery']])
        profiles,members=basic_centre_profiles(r,pd.DataFrame(rows),supply)
        positive_profiles,positive_members=basic_centre_profiles(r,pd.DataFrame(rows),supply,
            demographic_scope='inhabited_only')
        self.assertEqual(profiles.centre_id.tolist(),['city'])
        self.assertEqual(set(members.origin_id),{'village','branch'})
        self.assertEqual(len(members),2) # three functions must not triple count the abandoned village
        ghost=members[members.origin_id.eq('branch')].iloc[0]
        self.assertTrue(ghost.population_credit_eligible)
        self.assertEqual(ghost.credited_population_2021,0.)
        self.assertEqual(ghost.demographic_membership_role,'zero_reference_no_current_user_flow')
        self.assertEqual(ghost.contributing_basic_family_count,3)
        profile=profiles.iloc[0]
        self.assertEqual(profile.external_positive_origin_count,1)
        self.assertEqual(profile.external_demographic_origin_count,2)
        self.assertEqual(profile.published_zero_record_count,1)
        self.assertEqual(profile.external_credited_rural_population_2021,50.)
        self.assertEqual(profile.school_maximum_external_positive_minutes,10.)
        fixed=r.set_index('source_record_id').loc[members.origin_id]
        self.assertEqual(fixed.population_2002.sum(),170.)
        self.assertEqual(fixed.population_2021.sum(),50.)
        self.assertEqual(set(positive_members.origin_id),{'village'})
        self.assertEqual(positive_profiles.iloc[0].external_demographic_origin_count,1)
        self.assertEqual(positive_profiles.iloc[0].external_positive_origin_count,1)

    def test_zero_reference_does_not_override_rejected_population_credit(self):
        r=roster().assign(population_2021=[50.,0.,1000000.],budget_population_credit=[True,False,True],
            credit_2021=[True,False,True],settlement_type_2021=['деревня','деревня','город'])
        m=pd.DataFrame([{'origin_id':origin,'centre_id':'city','family':'school','cost_minutes':10.,
            'population_2021':pop,'model_choice_unique':True,'evidence_scenario':'all_dated_known'}
            for origin,pop in [('village',50.),('branch',0.)]])
        profiles,members=basic_centre_profiles(r,m,presence())
        ghost=members[members.origin_id.eq('branch')].iloc[0]
        self.assertFalse(ghost.population_credit_eligible)
        self.assertTrue(pd.isna(ghost.credited_population_2021))
        self.assertTrue(ghost.zero_final_population_kept_for_historical_demography)
        self.assertEqual(profiles.iloc[0].external_positive_origin_count,1)
        self.assertEqual(profiles.iloc[0].external_demographic_origin_count,2)

    def test_zero_only_directions_do_not_establish_any_basic_centre(self):
        r=roster().assign(population_2021=[0.,0.,100.],budget_population_credit=True,credit_2021=True)
        rows=pd.DataFrame([{'origin_id':'village','centre_id':'city','family':'school',
            'cost_minutes':10.,'population_2021':0.,'model_choice_unique':True,
            'evidence_scenario':'all_dated_known'}])
        profiles,members=basic_centre_profiles(r,rows,presence())
        self.assertTrue(profiles.empty);self.assertTrue(members.empty)


    def test_loss_of_one_coequal_centre_has_zero_time_penalty_and_no_uncredited_mass(self):
        r=roster().assign(budget_population_credit=1,credit_2021=[1,1,0])
        cat=pd.concat([catalogue(),catalogue().assign(catalog_id='branch-school',correctsource_record_id='branch')])
        opts=pd.concat([candidates(),candidates().assign(catalog_id='branch-school',destination_group_key='np:branch')])
        links,_=select_functional_links(r,presence(),opts,cat)
        detail,centres=loss_counterfactual(r,links,opts)
        village=detail[detail.origin_id.eq('village') & detail.family.eq('school')]
        assert len(village)==2 and village.additional_minutes.eq(0).all()
        city=centres[centres.removed_destination_group_key.eq('np:city') & centres.family.eq('school')].iloc[0]
        assert city.credited_positive_population_2021==50
        assert city.external_credited_positive_population_2021==50
        unknown=detail[detail.origin_id.eq('branch') & detail.family.eq('medical_basic')].iloc[0]
        assert unknown.alternative_status=='primary_direction_unknown_counterfactual_undefined'
        assert pd.isna(unknown.additional_minutes)

    def test_full_current_axis_does_not_duplicate_unaffected_school_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);fields=base/'fields';providers=base/'providers';out=base/'out'
            fields.mkdir();providers.mkdir()
            r=roster();r.to_parquet(fields/'regional_roster.parquet',index=False)
            pd.DataFrame({'source_record_id':r.source_record_id,'destination_index':range(3)}).to_parquet(fields/'destinations.parquet',index=False)
            cost=np.array([[0.,5.,40.],[5.,0.,35.],[40.,35.,0.]])
            # Dense-to-CSR removes zeroes; retain them explicitly for the diagonal.
            save_npz(fields/'destination_costs.npz',csr_matrix((cost.ravel(),np.tile(np.arange(3),3),np.arange(0,10,3)),shape=(3,3)))
            np.save(fields/'regional_costs.npy',cost)
            cat=pd.concat([catalogue(),catalogue().assign(catalog_id='old-clinic',family='medical_basic',historical_only=True)],ignore_index=True)
            cat.to_parquet(providers/'provider_catalog.parquet',index=False)
            presence().to_parquet(providers/'np_function_presence.parquet',index=False)
            candidates().to_parquet(fields/'physical_provider_candidates.parquet',index=False)
            candidates().to_parquet(fields/'current.parquet',index=False)
            result=build_functional_results(fields,providers,out,current_candidates=fields/'current.parquet')
            links=pd.read_parquet(out/'functional_links.parquet')
            assert len(links)==3*len(FAMILIES)*2
            assert not links.duplicated(['origin_id','family','evidence_scenario']).any()
            before={p.name:p.read_bytes() for p in out.glob('*') if p.is_file()
                and p.name not in {'functional_potentials.parquet','functional_summary.json'}}
            np.save(base/'full.npy',cost)
            pd.DataFrame({'source_record_id':r.source_record_id,'full_row_index':range(3)}).to_parquet(base/'origin_axis.parquet',index=False)
            pd.DataFrame({'source_record_id':r.source_record_id,'destination_index':range(3)}).to_parquet(base/'destination_axis.parquet',index=False)
            refresh_functional_potentials(fields,providers,out,base/'full.npy')
            assert all((out/name).read_bytes()==data for name,data in before.items())
            refreshed=pd.read_parquet(out/'functional_potentials.parquet')
            assert refreshed.field_costs_unbounded.all() and refreshed.computational_tail_upper.eq(0).all()
            wrong=pd.DataFrame({'source_record_id':r.source_record_id[::-1].to_list(),'destination_index':range(3)})
            wrong.to_parquet(base/'wrong_axis.parquet',index=False)
            with self.assertRaisesRegex(ValueError,'identity order'):
                load_full_field_costs(base/'full.npy',r,pd.read_parquet(fields/'destinations.parquet'),destination_axis=base/'wrong_axis.parquet')

    def test_branch_locality_improves_choice_without_assignment_training(self):
        source=pd.DataFrame([{'source_record_id':'branch','service_code':'school_general',
            'provider_id':'doc-branch','source_id':'official','eligible_np_presence_proxy':True}])
        cost=np.array([[0,5,40],[5,0,35],[40,35,0]], dtype=float)
        cat, options, proxies=documented_campus_proxies(roster(),presence(),source,cost,catalogue(),candidates())
        assert len(proxies)==1 and proxies.iloc[0].anchor_precision=='settlement_point_not_building'
        links,_=select_functional_links(roster(),presence(),options,cat)
        selected=links[(links.origin_id=='village')&(links.family=='school')].iloc[0]
        assert selected.provider_settlement_id=='branch' and selected.cost_minutes==5
        assert selected.observed_flow==False
        original,_=select_functional_links(roster(),presence(),candidates(),catalogue())
        assert original[(original.origin_id=='village')&(original.family=='school')].iloc[0].provider_settlement_id=='city'


    def test_equal_alternatives_do_not_create_unique_parent(self):
        cat=pd.concat([catalogue(),catalogue().assign(catalog_id='branch-school',correctsource_record_id='branch')])
        opts=pd.concat([candidates(),candidates().assign(catalog_id='branch-school',destination_group_key='np:branch')])
        links,members=select_functional_links(roster(),presence(),opts,cat)
        v=links[(links.origin_id=='village')&(links.family=='school')].iloc[0]
        assert v.primary_destination_tie_count==2 and not v.is_primary and v.ambiguous_primary
        assert len(members[(members.origin_id=='village')&(members.family=='school')])==2
        assert links[(links.origin_id=='village')&(links.family=='medical_basic')].iloc[0].local_supply_state=='unknown_not_absent'


    def test_national_presence_field_uses_all_offers_not_topthree_or_capacity(self):
        r=roster().iloc[:1]
        dest=pd.DataFrame({'source_record_id':['village','a','b','c','d'], 'destination_index':range(5)})
        p=pd.concat([presence().assign(source_record_id=x) for x in ['a','b','c','d']])
        costs=csr_matrix((np.array([0.,10.,10.,10.,10.]),np.arange(5),np.array([0,5])),shape=(1,5))
        links,_=select_functional_links(r,p,candidates(),catalogue())
        f=functional_potentials(r,dest,costs,p,links,half_times=(10.,))
        x=f[(f.family=='school')&(f.kernel=='exponential')].iloc[0]
        assert x.known_np_offer_potential==2 and x.external_known_np_offer_potential_lower==2
        assert x.known_np_function_offer_count==4


    def test_child_education_is_eligible_but_checked_operation_is_not_verified(self):
        f=pd.DataFrame({'provider_id':['school','clinic'], 'source_record_id':['x','x'],
            'service_code':['school_general','medical_basic_primary'], 'supply_status':['observed']*2,
            'named_child_only_contingent':[True]*2,'actual_operational_status_checked':[True]*2,
            'site_lat':[1.,1.], 'site_lon':[2.,2.]})
        x=normalize_offers(f,'sites','test')
        assert x.admitted_general_population_offer.tolist()==[True,False]
        assert not x.operation_verified.any()

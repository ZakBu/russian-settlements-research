import unittest

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from scripts.sgrt_saratov.regional_context import (
    PROTECTED, PRIMARY2010_QUALITY, annualized_change_percent, apply_primary2010_evidence, aggregate_systems, aggregate_configurations, aggregate_unit_economic_context, aggregate_basic_centres, agriculture_demographic_context, audit_worker_potential, attach_worker_source_identity, build_np_context,
    observation_class, territory_agriculture, territory_workforce, worker_potential,
)


def fixture():
    rows=[]
    for sid,kind,pop in [('c','город',(100.,110.,120.)),('r','село',(10.,8.,5.)),('m','село',(np.nan,2.,4.))]:
        row={'source_record_id':sid,'root':'chain:'+sid,'name':sid,
            'settlement_type_2021':kind,'budget_population_credit':True}
        for year,value in zip((2002,2010,2021),pop):
            row.update({f'population_{year}':value,f'credit_{year}':True,
                f'source_record_id_{year}':str(year)+':'+sid,
                f'population_value_quality_{year}':'direct_published_census_value'})
        rows.append(row)
    roster=pd.DataFrame(rows)
    agriculture=pd.DataFrame([{'source_record_id':sid,'agri_municipality_code':'mun',
        'parent_relation_rule':'explicit','agri_parent_match_status':'matched',
        'historical_boundary_equivalence_proven':False,
        'agri_sown_area_ha_2021_municipal_context':100.} for sid in roster.source_record_id])
    workers=pd.DataFrame([{'source_record_id':sid,'ordinary_spatial_2021':True,
        'partial_organisation_workforce_2025':50. if sid=='c' else np.nan,
        'partial_workforce_status':'observed_partial_organisation_workforce' if sid=='c' else 'source_suppressed',
        'total_settlement_jobs':np.nan} for sid in roster.source_record_id])
    crosswalk=pd.DataFrame([{'source_record_id':sid,'matched_2021_parent_code':'mun',
        'parent_scope_basis':'explicit'} for sid in roster.source_record_id])
    return roster,agriculture,workers,crosswalk


def worker_fixture():
    origins=pd.DataFrame({'row_index':[0,1,2],'source_record_id':['o','p','q'],
        'route_row_status':['accepted','accepted','origin_endpoint_unavailable']})
    destinations=pd.DataFrame({'destination_index':[0,1],'source_record_id':['o','p'],
        'ordinary_spatial_2021':[True,True]})
    workforce=pd.DataFrame({'source_record_id':['o','p','q','w'],
        'ordinary_spatial_2021':[True]*4,'partial_organisation_workforce_2025':[10.,np.nan,20.,40.],
        'partial_workforce_status':['observed_partial_organisation_workforce',
            'unknown_no_verified_geographic_observation','observed_partial_organisation_workforce',
            'observed_partial_organisation_workforce']})
    costs=csr_matrix((np.asarray([0.,10.,10.,0.]),([0,0,1,1],[0,1,0,1])),shape=(3,2))
    return costs,origins,destinations,workforce


class PopulationEvidence(unittest.TestCase):
    def test_confidential_value_is_not_imputed(self):
        roster,agri,workers,cross=fixture()
        roster.loc[0,'population_value_quality_2010']=PROTECTED
        out=build_np_context(roster,agri,workers,cross).set_index('source_record_id')
        self.assertEqual(out.loc['c','population_observation_class_2010'],
            'secondary_confidentiality_value_scope_unverified')
        self.assertFalse(out.loc['c','population_eligible_2010_strict'])
        self.assertTrue(out.loc['c','population_eligible_2010_accepted'])
        self.assertEqual(out.loc['c','demographic_direction_2002_2021_strict'],'growth')

    def test_missing_middle_year_preserves_endpoint_comparison(self):
        roster,agri,workers,cross=fixture()
        roster.loc[0,'population_2010']=np.nan
        out=build_np_context(roster,agri,workers,cross).set_index('source_record_id')
        self.assertEqual(out.loc['c','demographic_trajectory_2002_2010_2021_strict'],'unknown')
        self.assertEqual(out.loc['c','demographic_direction_2002_2021_strict'],'growth')

    def test_zero_baseline_is_known_growth_but_not_rate(self):
        roster,agri,workers,cross=fixture();roster.loc[0,'population_2002']=0.
        out=build_np_context(roster,agri,workers,cross).set_index('source_record_id')
        self.assertEqual(out.loc['c','demographic_direction_2002_2021_strict'],'growth')
        self.assertTrue(pd.isna(out.loc['c','population_change_percent_2002_2021_strict']))

    def test_unknown_type_and_duplicates_not_silently_resolved(self):
        roster,agri,workers,cross=fixture();roster.loc[0,'settlement_type_2021']='населённый пункт'
        out=build_np_context(roster,agri,workers,cross).set_index('source_record_id')
        self.assertEqual(out.loc['c','settlement_class'],'type_unknown')
        with self.assertRaises(ValueError):build_np_context(roster,pd.concat([agri,agri.iloc[[0]]]),workers,cross)

    def test_complete_jobs_cannot_be_filled_from_partial_workers(self):
        roster,agri,workers,cross=fixture();workers.loc[0,'total_settlement_jobs']=50.
        with self.assertRaises(ValueError):build_np_context(roster,agri,workers,cross)

    def test_incomplete_rural_component_does_not_get_partial_direction(self):
        context=build_np_context(*fixture())
        links=pd.DataFrame({'system_id':['s']*3,'origin_id':['c','r','m'],
            'provider_settlement_id':['c']*3,'family':['school']*3,'is_primary':[True]*3})
        components,classes=aggregate_systems(links,context)
        row=components[(components.component=='rural_external')&(components.start_year==2002)&(components.end_year==2021)
            &(components.evidence_mode=='strict')].iloc[0]
        self.assertEqual(row.paired_eligible_records,1)
        self.assertEqual(row.paired_known_population_end,5.)
        self.assertEqual(row.direction,'unknown')
        self.assertEqual(classes.iloc[0].descriptive_dynamic_type,'incomplete_population_evidence')

    def test_unit_economy_keeps_unknown_jobs_and_unique_municipality_keys(self):
        roster,agri,workers,cross=fixture();ctx=build_np_context(roster,agri,workers,cross)
        links=pd.DataFrame({'system_id':['s']*3,'origin_id':['c','r','m'],
            'provider_settlement_id':['c']*3,'family':['school']*3,'is_primary':[True]*3})
        out=aggregate_unit_economic_context(links,None,ctx,workers,agri)
        centre=out[out.component.eq('centre_union')].iloc[0]
        rural=out[out.component.eq('rural_external')].iloc[0]
        self.assertEqual(centre.known_subset_partial_organisation_workers_2025,50.)
        self.assertFalse(centre.complete_jobs_or_resident_employment_known)
        self.assertEqual(rural.source_suppressed_worker_records,2)
        self.assertTrue(pd.isna(rural.known_subset_partial_organisation_workers_2025))
        self.assertEqual(rural.distinct_agriculture_context_territories,1)
        self.assertFalse(rural.municipal_values_allocated_or_summed)

    def test_equal_nearest_candidates_get_separate_qualified_types(self):
        context=build_np_context(*fixture())
        links=pd.DataFrame([{'system_id':'arbitrary','origin_id':'m',
            'provider_settlement_id':'c','family':'school','is_primary':False,
            'ambiguous_primary':True,'coequal_primary_keys_json':'["np:c", "np:r"]'}])
        _,classes=aggregate_systems(links,context)
        self.assertEqual(len(classes),2)
        self.assertEqual(set(classes.centre_id),{'c','r'})
        self.assertTrue(classes.ambiguous_candidate_member_records.eq(1).all())
        self.assertTrue(classes.descriptive_dynamic_type.str.startswith('ambiguous_candidate_membership__').all())
        self.assertFalse(classes.all_model_memberships_unique.any())

    def test_worker_source_geographic_fallback_is_retained(self):
        context=build_np_context(*fixture())
        evidence=pd.DataFrame([{'source_record_id':'c','match_status':'matched',
            'column_semantics_verified':True,'observation_year':2025,'value_status':'observed',
            'value':50.,'match_method':'exact_normalized_name_region','source_oktmo':'newcode',
            'source_file':'book.xlsx','source_sheet':'workers','source_excel_row':10}])
        out=attach_worker_source_identity(context,evidence).set_index('source_record_id')
        self.assertEqual(out.loc['c','partial_worker_geographic_match_precision'],
            'unique_name_region_with_different_or_missing_code')
        self.assertEqual(out.loc['c','partial_organisation_workforce_2025'],50.)
        self.assertEqual(out.loc['r','partial_worker_geographic_match_precision'],'no_numeric_observation')
        evidence.loc[0,'column_semantics_verified']=False
        with self.assertRaises(ValueError):attach_worker_source_identity(context,evidence)

    def test_basic_np_union_counts_one_village_once_across_functions(self):
        context=build_np_context(*fixture())
        profiles=pd.DataFrame([{'centre_id':'c','evidence_scenario':'all_dated_known',
            'inventory_scenario':'test','centre_in_regional_roster':True,
            'known_own_basic_function_count':3,'external_positive_origin_count':1}])
        members=pd.DataFrame([{'centre_id':'c','origin_id':'r','evidence_scenario':'all_dated_known',
            'any_ambiguous_primary':True,'contributing_families_json':'["school","medical_basic"]'}])
        comp,types,quality,_=aggregate_basic_centres(profiles,members,context,context)
        self.assertEqual(len(types),1)
        row=comp[(comp.component=='rural_external')&(comp.start_year==2002)&(comp.end_year==2021)&(comp.evidence_mode=='strict')].iloc[0]
        self.assertEqual(row.records,1)
        self.assertEqual(row.paired_known_population_end,5.)
        self.assertEqual(types.iloc[0].ambiguous_candidate_member_records,1)
        self.assertEqual(quality.iloc[0].external_rural_unique_origin_records,1)
        self.assertTrue(types.iloc[0].population_may_not_be_summed_across_centres)
        with self.assertRaises(ValueError):aggregate_basic_centres(profiles,pd.concat([members,members]),context,context)

    def test_annualization_compares_eight_and_eleven_years_fairly(self):
        a,status=annualized_change_percent(100.,100.*1.02**8,8)
        b,_=annualized_change_percent(100.,100.*1.02**11,11)
        self.assertAlmostEqual(a,2.,places=12)
        self.assertAlmostEqual(b,2.,places=12)
        self.assertEqual(status,'defined_positive_endpoints')

    def test_annualization_keeps_zero_timing_and_missing_pairs_undefined(self):
        for a,b,status in [(10,0,'depopulation_to_zero_timing_unknown'),
                (0,10,'appearance_from_zero_baseline_timing_unknown'),
                (0,0,'both_published_zero_without_positive_baseline')]:
            value,actual=annualized_change_percent(a,b,11)
            self.assertTrue(pd.isna(value));self.assertEqual(actual,status)
        self.assertTrue(pd.isna(annualized_change_percent(10,12,8,complete=False)[0]))
        with self.assertRaises(ValueError):annualized_change_percent(10,12,0)

    def test_primary2010_is_a_separate_variant_not_a_frozen_base_rewrite(self):
        roster=fixture()[0];original=roster.copy(deep=True)
        evidence=pd.DataFrame([{'source_record_id_2010':'2010:r',
            'identity_match_status':'unique_original_2010_type_name_both_province_frames',
            'legacy_population_2010':8.,'primary_population_2010':9.,
            'primary_value_admissible_in_separate_derived_variant':True}])
        out=apply_primary2010_evidence(roster,evidence).set_index('source_record_id')
        self.assertEqual(out.loc['r','population_2010'],9.)
        self.assertEqual(out.loc['r','foundation_population_2010_before_primary_evidence'],8.)
        self.assertEqual(out.loc['r','population_value_quality_2010'],PRIMARY2010_QUALITY)
        self.assertFalse(out.loc['c','primary2010_derived_evidence_applied'])
        pd.testing.assert_frame_equal(roster,original)
        evidence.loc[0,'legacy_population_2010']=7.
        with self.assertRaises(ValueError):apply_primary2010_evidence(roster,evidence)

    def test_repeated_municipal_value_not_multiplied(self):
        roster,agri,workers,cross=fixture();context=build_np_context(roster,agri,workers,cross)
        snapshots=pd.DataFrame({'municipality_code':['mun'],'value':[100.]})
        territories,_=territory_agriculture(context,agri,snapshots)
        self.assertEqual(len(territories),1)
        self.assertEqual(territories.iloc[0].agri_sown_area_ha_2021_municipal_context,100.)
        self.assertNotIn('agri_sown_area_ha_2021_municipal_context',context)
        agri.loc[1,'agri_sown_area_ha_2021_municipal_context']=101.
        with self.assertRaises(ValueError):territory_agriculture(context,agri,snapshots)

    def test_municipality_agriculture_and_demography_keep_their_own_denominators(self):
        context=build_np_context(*fixture())
        territories=pd.DataFrame({'municipality_code':['mun'],
            'agri_output_nominal_thousand_rub_2021_municipal_context':[100.],
            'agri_crop_output_nominal_thousand_rub_2021_municipal_context':[80.],
            'agri_livestock_output_nominal_thousand_rub_2021_municipal_context':[20.]})
        out=agriculture_demographic_context(context,territories).iloc[0]
        self.assertEqual(out.current_rural_np_records,2)
        self.assertEqual(out.current_rural_np_with_strict_reported_2002_2021_comparison,1)
        self.assertEqual(out.rural_np_decline_share_among_known_record_comparisons,1.)
        self.assertEqual(out.crop_share_of_published_agriculture_output_2021,.8)
        self.assertFalse(out.agricultural_mass_allocated_to_settlement)

    def test_cyrillic_sector_A_has_same_scope_denominator(self):
        context=build_np_context(*fixture())
        raw=pd.DataFrame({'oktmo':['mun']*2,'year':[2025]*2,
            'indicator_code':['Y48423005']*2,'indicator_period':['Январь-декабрь']*2,
            'indicator_unit':['Человек']*2,'municipality':['муниципалитет']*2,
            'okved2':['Всего по обследуемым видам экономической деятельности',
                'Раздел А Сельское, лесное хозяйство, охота, рыболовство и рыбоводство'],
            'indicator_value':[100.,20.]})
        summary,_=territory_workforce(context,raw)
        self.assertEqual(summary.iloc[0].section_A_share_of_partial_workers,.2)
        with self.assertRaises(ValueError):territory_workforce(context,pd.concat([raw,raw.iloc[[0]]]))

    def test_multiple_anchors_are_not_counted_twice(self):
        roster,agri,workers,cross=fixture();roster.loc[roster.source_record_id.eq('m'),'population_2002']=1.
        context=build_np_context(roster,agri,workers,cross)
        groups=pd.DataFrame({'origin_id':['c','r','m'],'basic_configuration_id':['g']*3})
        links=pd.DataFrame([{'origin_id':sid,'family':family,'provider_settlement_id':target,
            'is_primary':True} for sid in ['c','r','m']
            for family,target in [('school','c'),('medical_basic','r'),('grocery','c')]])
        components,classes=aggregate_configurations(groups,links,context)
        row=components[(components.component=='centre_union')&(components.start_year==2002)&(components.end_year==2021)
            &(components.evidence_mode=='strict')].iloc[0]
        self.assertEqual(row.records,2)
        self.assertEqual(row.paired_known_population_end,125.)
        self.assertEqual(classes.iloc[0].descriptive_configuration_type,'multiple_known_np__primary_reported__growth__growth')
        links.loc[(links.origin_id=='m')&(links.family=='grocery'),'provider_settlement_id']='r'
        with self.assertRaises(ValueError):aggregate_configurations(groups,links,context)

    def test_unresolved_configuration_keeps_explicit_origin_status(self):
        context=build_np_context(*fixture())
        groups=pd.DataFrame({'origin_id':['c','r','m'],'basic_configuration_id':[None]*3})
        links=pd.DataFrame(columns=['origin_id','family','provider_settlement_id','is_primary'])
        _,classes=aggregate_configurations(groups,links,context)
        self.assertEqual(len(classes),3)
        self.assertTrue(classes.descriptive_configuration_type.eq('basic_functional_directions_incomplete').all())
        self.assertTrue(classes.unit_kind.eq('unresolved_origin_record').all())


class PartialWorkerField(unittest.TestCase):
    def test_unknown_worker_value_is_not_job_zero(self):
        costs,origins,destinations,workforce=worker_fixture()
        fields,axis,unmatched,facts=worker_potential(costs,origins,destinations,workforce)
        row=fields[(fields.row_index==1)&(fields.kernel=='exponential')&(fields.half_time_minutes==10.)].iloc[0]
        self.assertEqual(row.known_partial_worker_potential_with_self,5.)
        self.assertTrue(pd.isna(row.own_partial_worker_observation))
        self.assertFalse(row.own_worker_observation_known)
        self.assertTrue(pd.isna(axis.loc[axis.source_record_id=='p','partial_organisation_workforce_2025'].iloc[0]))
        self.assertEqual(facts['national_current_np_numeric_worker_observations'],3)
        self.assertEqual(facts['known_partial_workers_without_routable_destination'],60.)
        self.assertIsNone(row.all_workplaces_or_all_workers_potential_upper)
        audit=audit_worker_potential(fields,costs,origins,axis,unmatched)
        self.assertEqual(audit['scenario_rows_checked'],16)

    def test_missing_origin_and_zero_cost_have_different_meanings(self):
        costs,origins,destinations,workforce=worker_fixture()
        fields,_,_,_=worker_potential(costs,origins,destinations,workforce)
        missing=fields[fields.row_index==2]
        self.assertTrue(missing.known_partial_worker_potential_with_self.isna().all())
        self.assertTrue(missing.own_partial_worker_observation.eq(20.).all())
        self.assertTrue(fields[fields.row_index==0].known_partial_worker_potential_external.eq(0.).all())
        costs.eliminate_zeros()
        with self.assertRaises(ValueError):worker_potential(costs,origins,destinations,workforce)

    def test_suppressed_numeric_contradiction_rejected(self):
        costs,origins,destinations,workforce=worker_fixture()
        workforce.loc[0,'partial_workforce_status']='source_suppressed'
        with self.assertRaises(ValueError):worker_potential(costs,origins,destinations,workforce)


if __name__=='__main__':unittest.main()

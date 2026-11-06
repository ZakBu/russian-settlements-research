import unittest

import pandas as pd

from scripts.sgrt_saratov.system_economy import build_economic_context, build_demographic_context


class ExplicitSystemEconomy(unittest.TestCase):
    def data(self):
        context = pd.DataFrame([
            dict(source_record_id='c', partial_organisation_workforce_2025=10.,
                 partial_workforce_status='observed_partial_organisation_workforce',
                 settlement_class='rural', agri_municipality_code='001',
                 partial_worker_geographic_match_precision='exact_2021_np_oktmo11_region_name'),
            dict(source_record_id='x', partial_organisation_workforce_2025=None,
                 partial_workforce_status='source_suppressed',
                 settlement_class='rural', agri_municipality_code='001'),
            dict(source_record_id='y', partial_organisation_workforce_2025=3.,
                 partial_workforce_status='observed_partial_organisation_workforce',
                 settlement_class='rural', agri_municipality_code='001',
                 partial_worker_geographic_match_precision='unique_name_region_with_different_or_missing_code'),
        ])
        farms = pd.DataFrame([dict(municipality_code='001', published_crop_area=123.)])
        members = pd.DataFrame([dict(system_id='s1',source_record_id=s,role=r)
                                for s,r in [('c','core'),('x','external'),('y','external')]] +
                               [dict(system_id='s2',source_record_id='c',role='core')])
        return members, context, farms

    def test_actual_membership_changes_components_without_filling_hidden_cells_or_multiplying_farm_output(self):
        members, context, farms = self.data()
        components, municipal, summary = build_economic_context(members, context, farms)
        x = components.set_index(['system_id','component'])
        self.assertEqual(x.loc[('s1','external'),'known_subset_partial_organisation_workers_2025'],3.)
        self.assertEqual(x.loc[('s1','external'),'source_suppressed_worker_records'],1)
        self.assertFalse(x.loc[('s1','external'),'all_partial_source_cells_numeric'])
        self.assertEqual(x.loc[('s1','external'),'numeric_worker_records_with_name_region_fallback'],1)
        self.assertTrue(pd.isna(x.loc[('s1','external'),'known_subset_workers_with_exact_np_identity_2025']))
        row = municipal[(municipal.system_id=='s1') & (municipal.component=='external')]
        self.assertEqual(len(row),1)
        self.assertEqual(row.iloc[0].published_crop_area,123.)
        self.assertEqual(row.iloc[0].member_records_in_municipality,2)
        self.assertEqual(summary['self_only_units'],1)
        self.assertFalse(components.complete_jobs_or_resident_employment_known.any())
        # Removing an external member recomputes its source coverage, rather
        # than copying the old candidate system's economic context.
        changed = members[~((members.system_id=='s1') & (members.source_record_id=='y'))]
        changed_components, _, _ = build_economic_context(changed,context,farms)
        e = changed_components[(changed_components.system_id=='s1') & (changed_components.component=='external')].iloc[0]
        self.assertTrue(pd.isna(e.known_subset_partial_organisation_workers_2025))
        self.assertEqual(e.source_suppressed_worker_records,1)

    def test_duplicate_membership_or_municipal_context_cannot_silently_double_count(self):
        members, context, farms = self.data()
        with self.assertRaises(ValueError):
            build_economic_context(pd.concat([members,members.iloc[:1]],ignore_index=True),context,farms)
        with self.assertRaises(ValueError):
            build_economic_context(members,context,pd.concat([farms,farms],ignore_index=True))

    def test_demography_does_not_exclude_a_depopulated_member_or_assign_a_type_to_incomplete_population(self):
        members, context, _ = self.data()
        members['membership_basis'] = 'documented_school_assignment_2025'
        context['budget_population_credit'] = [True,True,False]
        for year, values in [(2002,[100.,10.,20.]),(2010,[80.,5.,10.]),(2021,[60.,0.,5.])]:
            context['population_'+str(year)] = values
            context['credit_'+str(year)] = True
            context['source_record_id_'+str(year)] = context.source_record_id + ':' + str(year)
            context['population_value_quality_'+str(year)] = 'direct_published_census_value'
        components, profiles = build_demographic_context(members,context)
        q = components[(components.system_id=='s1') & (components.component=='rural_external')
                       & (components.start_year==2002) & (components.end_year==2021)
                       & (components.evidence_mode=='strict')].iloc[0]
        self.assertEqual(q.records,2)
        self.assertEqual(q.paired_eligible_records,1)
        self.assertFalse(q.complete_component)
        self.assertEqual(q.direction,'unknown')
        self.assertEqual(q.paired_known_population_end,0.)
        reduced = members[~((members.system_id=='s1') & (members.source_record_id=='y'))]
        components, profiles = build_demographic_context(reduced,context)
        q = components[(components.system_id=='s1') & (components.component=='rural_external')
                       & (components.start_year==2002) & (components.end_year==2021)
                       & (components.evidence_mode=='strict')].iloc[0]
        self.assertTrue(q.complete_component)
        self.assertEqual(q.direction,'decline')
        self.assertEqual(q.annualized_population_change_status,'depopulation_to_zero_timing_unknown')

    def test_complete_census_subset_does_not_make_incompletely_geocoded_document_complete(self):
        members, context, farms = self.data()
        members = members[members.source_record_id.ne('y')].copy()
        members['membership_basis'] = 'documented_school_assignment_2025'
        members['documented_membership_complete'] = members.system_id.ne('s1')
        members['documented_held_relation_rows'] = members.system_id.eq('s1').astype(int)
        context['budget_population_credit'] = True
        for year, values in [(2002,[100.,10.,20.]),(2010,[80.,5.,10.]),(2021,[60.,0.,5.])]:
            context['population_'+str(year)] = values
            context['credit_'+str(year)] = True
            context['source_record_id_'+str(year)] = context.source_record_id + ':' + str(year)
            context['population_value_quality_'+str(year)] = 'direct_published_census_value'
        components, profiles = build_demographic_context(members,context)
        p = profiles.set_index('system_id').loc['s1']
        self.assertEqual(p.accepted_subset_joint_centre_rural_2002_2021_strict,'decline__decline')
        self.assertFalse(p.classifiable_full_documented_system)
        self.assertEqual(p.full_documented_system_dynamic_type_2002_2021_strict,'document_geography_incomplete')
        e, _, _ = build_economic_context(members,context,farms)
        self.assertTrue(e[e.system_id.eq('s1')].summary_describes_accepted_geocoded_subset.all())
        # Only resolving the missing document identity changes coverage; it
        # does not require editing any census value or inherited joint type.
        members['documented_membership_complete'] = True
        members['documented_held_relation_rows'] = 0
        _, profiles = build_demographic_context(members,context)
        self.assertTrue(profiles.set_index('system_id').loc['s1','classifiable_full_documented_system'])


if __name__ == '__main__':
    unittest.main()

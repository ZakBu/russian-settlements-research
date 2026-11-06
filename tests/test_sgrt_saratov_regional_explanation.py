import unittest
import pandas as pd
import numpy as np
from scripts.sgrt_saratov.regional_explanation import group_summary, transport_associations, describe_population_basins, basin_temporal_sensitivity


class RegionalContrasts(unittest.TestCase):
    def cohort(self):
        rows=[]
        for pop,worker,status in [(1000,0.,'observed_partial_organisation_workforce'),(10,np.nan,'source_suppressed'),(10,np.nan,'unknown_no_verified_geographic_observation')]:
            rows.append(dict(population_2021=pop,partial_organisation_workforce_2025=worker,
                partial_workforce_status=status,population_eligible_2002_strict=True,
                population_eligible_2021_strict=True,population_2002=pop,model_lat=50.,
                school_known_local_supply_preferred=False,
                medical_basic_known_local_supply_preferred=False,
                grocery_known_local_supply_preferred=False))
        return pd.DataFrame(rows)

    def test_zero_observation_suppression_and_population_coverage_are_distinct(self):
        s=group_summary(self.cohort())
        self.assertEqual(s['numeric_partial_worker_records'],1)
        self.assertEqual(s['numeric_zero_worker_records'],1)
        self.assertEqual(s['source_suppressed_worker_records'],1)
        self.assertEqual(s['unknown_worker_records'],1)
        self.assertEqual(s['known_subset_partial_organisation_workers_2025'],0.)
        self.assertAlmostEqual(s['worker_np_coverage_share'],1/3)
        self.assertAlmostEqual(s['worker_population_coverage_share'],1000/1020)
        self.assertFalse(s['worker_statistic_is_resident_employment_or_complete_jobs'])

    def test_incomplete_surroundings_do_not_become_a_complete_dynamic_type(self):
        x=self.cohort()
        x['source_record_id']=['core','a','b']
        x['settlement_class']=['urban','rural','rural']
        x['agri_municipality_code']=['m','m','m']
        x.loc[2,'population_eligible_2002_strict']=False
        x.loc[2,'population_2002']=np.nan
        membership=pd.DataFrame([dict(scenario_id='s',basin_id='b',source_record_id=i,
            core_id='core',kernel='exponential',half_time=10,neighbour_count=6,
            topology='local',status='resolved_regional_peak',assignment_unique=True)
            for i in x.source_record_id])
        components,profiles=describe_population_basins(x,membership)
        surroundings=components[components.component.eq('rural_external')].iloc[0]
        self.assertEqual(surroundings.records,2)
        self.assertEqual(surroundings.paired_numeric_records,1)
        self.assertEqual(surroundings.paired_known_subset_population_change_percent,0.)
        self.assertTrue(pd.isna(surroundings.full_component_population_change_percent))
        self.assertEqual(surroundings.reported_direction_2002_2021,'unknown')
        self.assertEqual(profiles.iloc[0].core_rural_reported_record_pair_type,'unknown')
        self.assertFalse(components.proves_functional_settlement_system.any())

    def test_unknown_type_surroundings_prevent_a_complete_rural_scope(self):
        x=self.cohort();x['source_record_id']=['core','a','b']
        x['settlement_class']=['urban','rural','unknown']
        x['population_2010']=x.population_2021
        for y in [2002,2010,2021]:
            for mode in ['strict','accepted']:x[f'population_eligible_{y}_{mode}']=True
        membership=pd.DataFrame([dict(scenario_id='s',basin_id='b',source_record_id=i,
            core_id='core',status='resolved_regional_peak',assignment_unique=True) for i in x.source_record_id])
        components,profiles=basin_temporal_sensitivity(x,membership,'foundation')
        rural=components[components.component.eq('rural_external')]
        self.assertTrue(rural.records.eq(1).all())
        self.assertTrue(rural.paired_eligible_records.eq(1).all())
        self.assertFalse(rural.complete_component.any())
        self.assertTrue(profiles.joint_core_rural_reported_type.eq('unknown').all())

    def test_missing_transport_input_keeps_the_full_roster(self):
        x=self.cohort()
        result,stats=transport_associations(x,None)
        self.assertEqual(len(result),3)
        self.assertTrue(stats.empty)
        self.assertIn('spearman_rank_correlation',stats)


if __name__=='__main__':unittest.main()

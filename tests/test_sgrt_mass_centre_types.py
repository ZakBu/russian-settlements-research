import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

FILE=Path(__file__).resolve().parents[1]/'scripts/sgrt_mass/centre_types.py'
spec=importlib.util.spec_from_file_location('centre_types',FILE)
types=importlib.util.module_from_spec(spec);spec.loader.exec_module(types)


def reference(ids,populations,*,roles=None,credits=None):
    return pd.DataFrame({'source_record_id':ids,'name':ids,'region':['test']*len(ids),
        'population_2021':populations,'credit_2021':credits if credits is not None else [True]*len(ids),
        'population_role':roles if roles is not None else ['ordinary_settlement_record']*len(ids)})


class CentreTypeTests(unittest.TestCase):
    def test_overlapping_services_do_not_double_external_population(self):
        units=pd.DataFrame({'unit_id':['u1','u2'],'center_source_record_id':['2021:a','2021:a'],
            'service_code':['medical_basic_primary','school_general'],'external_population_2021':[100.,80.],
            'n_populated_external':[3,2]})
        p=types.build_profiles(units,reference(['2021:a'],[50]))
        self.assertEqual(len(p),1)
        self.assertEqual(p.max_single_function_external_population.iloc[0],100)
        self.assertEqual(p.known_sector_count.iloc[0],2)

    def test_medical_orders_are_one_sector_not_four_institutions(self):
        units=pd.DataFrame({'unit_id':['u1','u2','u3'],'center_source_record_id':['2021:a']*3,
            'service_code':['medical_basic_primary','medical_physician_primary','medical_inpatient'],
            'external_population_2021':[10,20,30]})
        p=types.build_profiles(units,reference(['2021:a'],[50]))
        self.assertEqual(p.known_sector_count.iloc[0],1)
        self.assertEqual(p.known_service_count.iloc[0],3)
        self.assertEqual(p.known_function_count.iloc[0],3)

    def test_old_binary_sector_count_is_not_accepted_as_service_complexity(self):
        units=pd.DataFrame({'unit_id':['u1','u2','u3'],'center_source_record_id':['2021:a']*3,
            'service_code':['medical_basic_primary','medical_physician_primary','medical_inpatient'],
            'known_function_count':[1,1,1],'external_population_2021':[10,20,30]})
        with self.assertRaises(ValueError):types.build_profiles(units,reference(['2021:a'],[50]))

    def test_two_dated_preschool_sources_do_not_invent_two_functions(self):
        units=pd.DataFrame({'unit_id':['u1','u2'],'center_source_record_id':['2021:a']*2,
            'service_code':['preschool','preschool_official'],'known_function_count':[1,1],
            'external_population_2021':[100,150]})
        p=types.build_profiles(units,reference(['2021:a'],[50]))
        self.assertEqual(p.known_function_count.iloc[0],1)
        self.assertEqual(p.known_service_count.iloc[0],2)

    def test_federal_population_never_becomes_an_ordinary_centre_feature(self):
        units=pd.DataFrame({'unit_id':['u1'],'center_source_record_id':['2021:moscow'],
            'service_code':['school_general'],'external_population_2021':[100.]})
        p=types.build_profiles(units,reference(['2021:moscow'],[13000000],roles=['external_context_nonadditive'],credits=[False]))
        self.assertFalse(p.clustering_feature_complete.iloc[0])
        self.assertTrue(pd.isna(p.centre_population_2021.iloc[0]))
        self.assertEqual(p.data_completeness.iloc[0],'external_context_nonadditive')

    def test_unknown_np_identity_does_not_borrow_nearest_population(self):
        units=pd.DataFrame({'unit_id':['u1'],'center_source_record_id':[None],'provider_id':['osm:node:123'],
            'centrepop2021':[500000],'service_code':['school_general'],'external_population_2021':[100.]})
        p=types.build_profiles(units,reference(['2021:a'],[50]))
        self.assertTrue(pd.isna(p.centre_population_2021.iloc[0]))
        self.assertEqual(p.data_completeness.iloc[0],'unknown_centre_np_identity')

    def test_no_silent_mixing_of_access_scenarios(self):
        units=pd.DataFrame({'unit_id':['u1','u2'],'center_source_record_id':['2021:a']*2,
            'scenario':['15minutes','30minutes'],'service_code':['school_general']*2,'external_population_2021':[100,500]})
        with self.assertRaises(ValueError):types.build_profiles(units,reference(['2021:a'],[50]))
        p=types.build_profiles(units,reference(['2021:a'],[50]),scenario='15minutes')
        self.assertEqual(p.max_single_function_external_population.iloc[0],100)

    def test_complementary_source_geometry_can_be_combined_only_explicitly(self):
        units=pd.DataFrame({'unit_id':['u1','u2'],'center_source_record_id':['2021:a']*2,
            'scenario':['registry_or_address_np','physical_sites'],
            'service_code':['medical_basic_primary','school_general'],'external_population_2021':[100,500]})
        with self.assertRaises(ValueError):types.build_profiles(units,reference(['2021:a'],[50]))
        p=types.build_profiles(units,reference(['2021:a'],[50]),combine_source_layers=True)
        self.assertEqual(p.known_sector_count.iloc[0],2)
        self.assertEqual(p.max_single_function_external_population.iloc[0],500)
        units['scenario']=['strict15','planning30']
        with self.assertRaises(ValueError):types.build_profiles(units,reference(['2021:a'],[50]),combine_source_layers=True)

    def test_zero_is_known_but_uncredited_population_is_missing(self):
        units=pd.DataFrame({'unit_id':['u1','u2'],'center_source_record_id':['2021:a','2021:b'],
            'service_code':['school_general']*2,'external_population_2021':[10,20]})
        p=types.build_profiles(units,reference(['2021:a','2021:b'],[0,999],credits=[True,False]))
        self.assertEqual(p.centre_population_2021.iloc[0],0)
        self.assertTrue(p.clustering_feature_complete.iloc[0])
        self.assertTrue(pd.isna(p.centre_population_2021.iloc[1]))

    def test_total_membership_is_not_mislabelled_external_population(self):
        units=pd.DataFrame({'unit_id':['u1'],'center_source_record_id':['2021:a'],
            'service_code':['school_general'],'memberspop':[500]})
        p=types.build_profiles(units,reference(['2021:a'],[50]))
        self.assertEqual(p.data_completeness.iloc[0],'missing_external_demographic_support')

    def test_k_diagnostics_and_labels_are_reproducible_without_population_cutoffs(self):
        # Deliberately overlapping population ranges: sector/support structure
        # changes the feature space, without any 10k/50k/500k size thresholds.
        p=pd.DataFrame({'centre_key':['a','b','c','d','e','f','g','h'],
            'centre_population_2021':[10,12,11,13,1000,1100,1050,1200],
            'max_single_function_external_population':[20,25,22,18,100,120,110,105],
            'known_sector_count':[1,1,1,1,2,2,2,2],
            'known_function_count':[1,1,1,1,3,3,3,3],
            'data_completeness':['features_available_source_network_incomplete']*8,
            'clustering_feature_complete':[True]*8})
        p['log_population_2021']=np.log1p(p.centre_population_2021)
        p['log_max_single_function_external_population']=np.log1p(p.max_single_function_external_population)
        a,m,s,summary=types.classify(p,max_k=4,silhouette_sample=8)
        b,m2,s2,summary2=types.classify(p,max_k=4,silhouette_sample=8)
        pd.testing.assert_frame_equal(a,b)
        self.assertEqual(set(m.k),{1,2,3,4})
        self.assertEqual(set(m.variant),set(types.MODELS))
        self.assertTrue(m[m.k.ge(2)].silhouette.notna().all())
        self.assertEqual(summary['selected_k'],2)
        self.assertFalse(a.scale_type_is_spatial_hierarchy_level.any())
        self.assertEqual(len(s),6)
        self.assertTrue(a.elbow_type_population_only.notna().all())
        self.assertTrue(a.profile_cluster_population_only_k4.notna().all())
        ordered=a.groupby('scale_type_index').centre_population_2021.median()
        self.assertTrue(ordered.is_monotonic_increasing)

    def test_identical_profiles_do_not_force_multiple_clusters(self):
        p=pd.DataFrame({'centre_population_2021':[10,10,10],
            'known_sector_count':[1,1,1],'max_single_function_external_population':[20,20,20],
            'known_function_count':[1,1,1],
            'log_population_2021':np.log1p([10,10,10]),
            'log_max_single_function_external_population':np.log1p([20,20,20])})
        result,metrics=types.fit_variant(p,types.MODELS['population_functions_and_support'])
        self.assertEqual(result['selected_k'],1)
        self.assertEqual(set(result['labels']),{0})
        self.assertTrue(metrics.silhouette.isna().all())


if __name__=='__main__':unittest.main()

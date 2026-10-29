import copy
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.sgrt_saratov import preserved_numeric_comparison as comparison


class PreservedNumericComparisonTests(unittest.TestCase):
    def fixture(self,root,mutation=None,reference_mutation=None):
        reference_zip=root/'reference.zip';fresh_zip=root/'fresh.zip'
        expected={'schema':'sgrt.saratov.regional_control.v1','numeric_decimal_places':8,
            'tables':{},'matrices':{str(i):{'sha256':str(i)} for i in range(6)},
            'geojson':{str(i):{'sha256':str(i)} for i in range(19)},
            'scientific_summaries':{str(i):{'count':i} for i in range(26)}}
        actual=copy.deepcopy(expected)
        with zipfile.ZipFile(reference_zip,'w') as old,zipfile.ZipFile(fresh_zip,'w') as new:
            for index,name in enumerate(comparison.SIX_TABLES):
                frame=pd.DataFrame({'source_record_id':['a','b'],'kernel':['exponential']*2,
                    'half_time':[10.,10.],'include_self':[True,True],
                    'value':[1.0000000049999,2.], 'integer_count':np.array([3,4],dtype='int64'),
                    'label':['known','unknown'],'special':[np.nan,np.inf]})
                if name.startswith('context/'):
                    frame=frame.rename(columns={'half_time':'half_time_minutes'}).drop(columns='include_self')
                if name.startswith('organisation/'):
                    frame['neighbour_count']=3
                    frame['sampled_point_maximum']=[True,False]
                fresh=frame.copy(deep=True);fresh.loc[0,'value']=1.0000000050001
                before_file=root/f'before_{index}.parquet';frame.to_parquet(before_file,index=False)
                expected['tables'][name]=comparison.table_control(before_file)
                if reference_mutation:reference_mutation(name,frame)
                frame.to_parquet(before_file,index=False)
                old.writestr('results/'+name,before_file.read_bytes())
                if mutation:mutation(name,fresh)
                after_file=root/f'after_{index}.parquet';fresh.to_parquet(after_file,index=False)
                actual['tables'][name]=comparison.table_control(after_file)
                new.writestr('results/'+name,after_file.read_bytes())
            # Unrelated ZIP members are checked by the caller, not this API.
            new.writestr('UNPUBLISHED.txt','Original source controls remain unequal.')
        for i in range(233):
            entry={'rows':1,'columns':['id'],'hash_method':'opaque-other-result-control','sha256':hashlib.sha256(str(i).encode()).hexdigest()}
            expected['tables'][f'other/table_{i}.parquet']=entry
            actual['tables'][f'other/table_{i}.parquet']=copy.deepcopy(entry)
        return fresh_zip,reference_zip,expected,actual

    def invoke(self,args):
        reference=args[1]
        with patch.object(comparison,'REFERENCE_V1_BYTES',reference.stat().st_size),patch.object(comparison,'REFERENCE_V1_SHA256',comparison.sha(reference)):
            return comparison.compare_preserved(*args)

    def test_tiny_boundary_crossings_preserve_failed_controls_and_compare_values(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory));expected=copy.deepcopy(args[2]);actual=copy.deepcopy(args[3])
            proof=self.invoke(args)
            self.assertFalse(proof['strict_control_equal'])
            self.assertTrue(proof['scientific_results_reproduce_with_existing_arithmetic_tolerance'])
            self.assertEqual(proof['six_table_hash_differences'],6)
            self.assertEqual(proof['round8_different_cells'],6)
            self.assertFalse(proof['floating_difference_cause_established'])
            self.assertEqual(args[2],expected);self.assertEqual(args[3],actual)
            self.assertEqual(self.invoke(args),proof)

    def test_real_numeric_change_exceeding_existing_criterion_is_rejected(self):
        def mutate(name,frame):
            if name=='fields/fields.parquet':frame.loc[0,'value']+=.01
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'arithmetic tolerance exceeded'):
                self.invoke(self.fixture(Path(directory),mutate))

    def test_peak_classification_change_is_rejected_even_with_equal_counts(self):
        def mutate(name,frame):
            if name.startswith('organisation/'):
                frame['sampled_point_maximum']=[False,True]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'classification differs'):
                self.invoke(self.fixture(Path(directory),mutate))

    def test_na_mask_change_is_rejected(self):
        def mutate(name,frame):
            if name=='fields/fields.parquet':frame.loc[0,'special']=0.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'Missing-value mask differs'):
                self.invoke(self.fixture(Path(directory),mutate))

    def test_infinity_sign_change_is_rejected(self):
        def mutate(name,frame):
            if name=='fields/fields.parquet':frame.loc[1,'special']=-np.inf
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'Infinity signs'):
                self.invoke(self.fixture(Path(directory),mutate))

    def test_key_change_is_rejected(self):
        def mutate(name,frame):
            if name=='fields/fields.parquet':frame.loc[0,'source_record_id']='another'
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'row identities differ'):
                self.invoke(self.fixture(Path(directory),mutate))

    def test_numeric_dtype_change_is_rejected(self):
        def mutate(name,frame):
            if name=='fields/fields.parquet':frame['integer_count']=frame.integer_count.astype(float)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'Data type differs'):
                self.invoke(self.fixture(Path(directory),mutate))

    def test_seventh_control_difference_is_not_silently_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory));args[3]['tables']['other/table_0.parquet']['sha256']='unreviewed'
            with self.assertRaisesRegex(ValueError,'exactly the six'):
                self.invoke(args)

    def test_changed_geometry_control_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory));args[3]['geojson']['0']={'sha256':'changed'}
            with self.assertRaisesRegex(ValueError,'Additional scientific differences'):
                self.invoke(args)

    def test_actual_table_is_recomputed_instead_of_trusting_control_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory));args[3]['tables']['fields/fields.parquet']['sha256']='forged'
            with self.assertRaisesRegex(ValueError,'preserved actual control'):
                self.invoke(args)

    def test_reference_table_must_really_equal_the_expected_unchanged_baseline(self):
        def mutate(name,frame):
            if name=='fields/fields.parquet':frame.loc[0,'value']+=.1
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'unchanged expected baseline'):
                self.invoke(self.fixture(Path(directory),reference_mutation=mutate))

    def test_published_reference_archive_pin_cannot_be_bypassed(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory))
            with self.assertRaisesRegex(ValueError,'archive byte size differs'):
                comparison.compare_preserved(*args)
            with patch.object(comparison,'REFERENCE_V1_BYTES',args[1].stat().st_size):
                with self.assertRaisesRegex(ValueError,'archive SHA256 differs'):
                    comparison.compare_preserved(*args)


if __name__=='__main__':unittest.main()

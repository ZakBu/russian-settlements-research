"""Guards against changing data or pretending that original hashes are equal."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from scripts.sgrt_saratov import finalize_v2_regional_research as f


class PreservedV2Guards(unittest.TestCase):
    def controls(self):
        expected={'tables':{name:{'sha256':'local','rows':2,'columns':['id','value']} for name in f.NUMERIC_TABLES},
            'matrices':{'m':{'sha256':'same'}},'geojson':{},'scientific_summaries':{}}
        actual=copy.deepcopy(expected)
        for row in actual['tables'].values():row['sha256']='fresh'
        return expected,actual

    def test_only_six_original_hash_differences_allowed(self):
        a,b=self.controls();self.assertEqual(set(f.verify_control_difference(a,b)),f.NUMERIC_TABLES)
        for mutation in ['metadata','extra','matrix','equal']:
            c=copy.deepcopy(b);name=next(iter(f.NUMERIC_TABLES))
            if mutation=='metadata':c['tables'][name]['rows']=3
            elif mutation=='extra':c['tables']['another.parquet']={'sha256':'bad'}
            elif mutation=='matrix':c['matrices']['m']['sha256']='bad'
            else:c['tables'][name]=copy.deepcopy(a['tables'][name])
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):f.verify_control_difference(a,c)

    def test_numeric_proof_must_explicitly_confirm_reproduction_and_unequal_hashes(self):
        valid={'scientific_results_reproduce_with_existing_arithmetic_tolerance':True,'strict_control_equal':False}
        f.verify_numeric_proof(valid)
        for bad in [{},{**valid,'strict_control_equal':True},{**valid,'strict_control_equal':0},
                    {**valid,'scientific_results_reproduce_with_existing_arithmetic_tolerance':1}]:
            with self.subTest(proof=bad),self.assertRaises(ValueError):f.verify_numeric_proof(bad)

    def test_protected_math_inputs_expected_and_frontend_are_forbidden(self):
        for p in ['scripts/sgrt_saratov/cloud_regional_research.py','scripts/sgrt_saratov/functional_fields.py',f.EXPECTED_PATH,
                  'requirements-saratov-fields.txt','sgrt/saratov/documented_school_sites_20261029.csv',
                  'web/src/components/MapWorkspace.tsx','data/catalog.json']:
            with self.subTest(path=p):self.assertFalse(f.allowed_assembly_change(p))
        self.assertTrue(f.allowed_assembly_change(f.WORKFLOW_PATH))
        self.assertTrue(f.allowed_assembly_change('scripts/sgrt_saratov/register_release.py'))

    def test_source_guard_rejects_changed_math_before_any_assembly(self):
        with patch.object(f.subprocess,'check_output',return_value='scripts/sgrt_saratov/population_mass_scope.py\n'):
            with self.assertRaisesRegex(ValueError,'Protected scientific'):f.verify_scientific_source('a'*40)

    def test_workflow_reproduction_is_exact_git_blob_and_cannot_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/f.WORKFLOW_PATH;source.parent.mkdir(parents=True);source.write_bytes(b'workflow\n')
            built=root/'built';built.mkdir();archive=built/'data.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('data','unaltered')
            (built/'manifest.json').write_text(json.dumps({'archive':{'asset':'data.zip'},'files':[]}))
            with patch.object(f,'REPO',root),patch.object(f.subprocess,'check_output',return_value=b'workflow\n'):
                m=f.add_assembly_workflow(built,'a'*40)
                self.assertEqual(m['files'][0]['path'],'reproduction/'+f.WORKFLOW_PATH)
                self.assertEqual(m['archive']['bytes'],archive.stat().st_size)
                with zipfile.ZipFile(archive) as z:self.assertEqual(z.read('data'),b'unaltered')
                with self.assertRaisesRegex(ValueError,'Duplicate'):f.add_assembly_workflow(built,'a'*40)
            with patch.object(f,'REPO',root),patch.object(f.subprocess,'check_output',return_value=b'changed'):
                with self.assertRaisesRegex(ValueError,'differs'):f.add_assembly_workflow(built,'a'*40)


if __name__=='__main__':unittest.main()

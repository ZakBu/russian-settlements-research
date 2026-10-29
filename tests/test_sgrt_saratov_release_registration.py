import unittest
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zipfile
from scripts.sgrt_saratov.register_release import safe_member, verify_scientific_controls

class PortablePaths(unittest.TestCase):
 def test_traversal_and_noncanonical_paths_rejected(self):
  for name in ['../data','/etc/passwd','results/../../file','results//file','./file']:
   with self.subTest(name=name),self.assertRaises(ValueError):safe_member(name)
 def test_expected_scientific_path_preserved(self):
  self.assertEqual(str(safe_member('results/physical_official/functional_links.parquet')),'results/physical_official/functional_links.parquet')

class ScientificControlTrustBoundary(unittest.TestCase):
 def write_archive(self,root,expected,actual,certificate=None):
  path=Path(root)/'data.zip'
  with zipfile.ZipFile(path,'w') as z:
   for name,data in [('controls/expected_control.json',expected),('controls/actual_control.json',actual)]:
    z.writestr(name,json.dumps(data))
   if certificate is not None:z.writestr('checks/preserved_numeric_comparison.json',json.dumps(certificate))
  return path
 def test_exact_legacy_controls_need_no_numeric_reference(self):
  with tempfile.TemporaryDirectory() as root:
   path=self.write_archive(root,{'hash':'same'},{'hash':'same'})
   self.assertTrue(verify_scientific_controls(path)['strict_control_equal'])
 def test_differing_hashes_cannot_pass_without_reference_or_certificate(self):
  with tempfile.TemporaryDirectory() as root:
   path=self.write_archive(root,{'hash':'old'},{'hash':'new'})
   with self.assertRaisesRegex(ValueError,'independently replayable'):
    verify_scientific_controls(path)
   with self.assertRaisesRegex(ValueError,'independently replayable'):
    verify_scientific_controls(path,Path(root)/'reference.zip')
 def test_forged_archived_numeric_certificate_is_not_trusted(self):
  proof={'strict_control_equal':False,'scientific_results_reproduce_with_existing_arithmetic_tolerance':True,'changed_cells':5}
  forged={**proof,'changed_cells':0}
  module=SimpleNamespace(compare_preserved=lambda *args:proof)
  with tempfile.TemporaryDirectory() as root,patch.dict('sys.modules',{'scripts.sgrt_saratov.preserved_numeric_comparison':module}):
   path=self.write_archive(root,{'hash':'old'},{'hash':'new'},forged)
   with self.assertRaisesRegex(ValueError,'independent all-cell replay'):
    verify_scientific_controls(path,Path(root)/'reference.zip')
 def test_replayed_numeric_comparison_never_claims_exact_hash_equality(self):
  proof={'strict_control_equal':False,'scientific_results_reproduce_with_existing_arithmetic_tolerance':True,'changed_cells':5}
  module=SimpleNamespace(compare_preserved=lambda *args:proof)
  with tempfile.TemporaryDirectory() as root,patch.dict('sys.modules',{'scripts.sgrt_saratov.preserved_numeric_comparison':module}):
   path=self.write_archive(root,{'hash':'old'},{'hash':'new'},proof)
   observed=verify_scientific_controls(path,Path(root)/'reference.zip')
   self.assertFalse(observed['strict_control_equal'])
   self.assertTrue(observed['scientific_results_reproduce_with_existing_arithmetic_tolerance'])

if __name__=='__main__':unittest.main()

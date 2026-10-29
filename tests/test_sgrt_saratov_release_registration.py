import unittest
from scripts.sgrt_saratov.register_release import safe_member

class PortablePaths(unittest.TestCase):
 def test_traversal_and_noncanonical_paths_rejected(self):
  for name in ['../data','/etc/passwd','results/../../file','results//file','./file']:
   with self.subTest(name=name),self.assertRaises(ValueError):safe_member(name)
 def test_expected_scientific_path_preserved(self):
  self.assertEqual(str(safe_member('results/physical_official/functional_links.parquet')),'results/physical_official/functional_links.parquet')

if __name__=='__main__':unittest.main()

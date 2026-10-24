"""The optimized reducer must work as a package from outside the script folder."""
from pathlib import Path
import os,subprocess,sys,tempfile,unittest

class PackageImportTests(unittest.TestCase):
 def test_higher_drivers_import_as_packages_without_script_path(self):
  root=Path(__file__).resolve().parents[1]
  code='''
from scripts.sgrt_zero.upward import prepare_stage_edges
from scripts.sgrt_zero.extended import decide
from scripts.sgrt_zero.run_scenarios import main
assert callable(prepare_stage_edges) and callable(decide) and callable(main)
'''
  environment=os.environ.copy()
  dependency_paths=[p for p in environment.get('PYTHONPATH','').split(os.pathsep)
                    if p and Path(p).resolve()!=(root/'scripts/sgrt_zero').resolve()]
  environment['PYTHONPATH']=os.pathsep.join([str(root),*dependency_paths])
  with tempfile.TemporaryDirectory() as outside:
   result=subprocess.run([sys.executable,'-c',code],cwd=outside,env=environment,text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr)

 def test_canonical_candidates_with_only_repository_on_pythonpath(self):
  root=Path(__file__).resolve().parents[1]
  code='''
import pandas as pd
from scripts.sgrt_zero.hierarchy import higher_candidates
members=pd.DataFrame({'unit_id':['u'],'origin_id':['a'],'scenario_id':['s']})
edges=pd.DataFrame({'origin_id':['a'],'service_family':['f'],'provider_settlement_id':['p'],
 'provider_site_id':['physical-p'],'cost_minutes':[5.],'higher_admitted':[True],
 'admission_limit_minutes':[30.],'admission_basis':['explicit_test'],'territorial_merge_admitted':[True]})
reference=pd.DataFrame({'source_record_id':['a','p']})
result=higher_candidates(members,edges,reference)
assert len(result)==1 and result.territorial_merge_admitted_for_all_child_members.iloc[0]
'''
  environment=os.environ.copy();environment['PYTHONPATH']=str(root)
  with tempfile.TemporaryDirectory() as outside:
   result=subprocess.run([sys.executable,'-c',code],cwd=outside,env=environment,text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()

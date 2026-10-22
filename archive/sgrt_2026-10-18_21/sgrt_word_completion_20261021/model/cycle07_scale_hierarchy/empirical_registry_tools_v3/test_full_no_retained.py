"""FULL sourcebound CLI K=0 export and downstream standard consumer fixture."""
from pathlib import Path
import tempfile,subprocess,json,shutil
import pandas as pd,pyarrow.parquet as pq
from build_registry import sha,HERE
with tempfile.TemporaryDirectory()as td:
 root=Path(td);source=root/'source';source.mkdir();out=root/'registry';caps=[30,45,60,90,120]
 bp=source/'pre_execution_binding.json';bp.write_text(json.dumps({'protocol':{'extent':{'candidate_caps_minutes':caps}}}));(source/'run_receipt.json').write_text(json.dumps({'status':'GENERATED_DATA_FIXTURE_ONLY_COMPUTED50'}))
 files={}
 for cap in caps:
  u=pd.DataFrame({'unit_id':['u_a','u_b'],'n_members':[1,1],'partition_role':'candidate_knee_or_fallback'});m=pd.DataFrame({'id':['a','b'],'unit_id':['u_a','u_b'],'partition_role':'candidate_knee_or_fallback'})
  for kind,df in [('units',u),('memberships',m)]:
   p=source/f'cap_{cap:03}_raw_{kind}.parquet';df.to_parquet(p,index=False);files[str(p)]=sha(p)
 ledger=source/'all_50_bootstrap_ledger.parquet';pd.DataFrame([{'replicate_id':r,'candidate_cap':c,'assessable':False,'ari':None}for r in range(50)for c in caps]).to_parquet(ledger,index=False)
 summary=source/'retained_resolution_stability.csv';pd.DataFrame({'candidate_cap':caps,'accepted':False,'n_valid':0,'n_total':50}).to_csv(summary,index=False)
 base=root/'baseline_fixture_admission.json';base.write_text(json.dumps({'all_checks_passed':True,'accepted_source_binding_sha256':sha(bp),'accepted_unit_membership_files_sha256':files}))
 stable=root/'stability_fixture_admission.json';stable.write_text(json.dumps({'all_checks_passed':True,'accepted_all50_ledger_sha256':sha(ledger),'accepted_stability_summary_sha256':sha(summary)}))
 cmd=['python',str(HERE/'build_registry.py'),'--source',str(source),'--output',str(out),'--baseline-admission',str(base),'--stability-admission',str(stable)]
 subprocess.run(cmd+['--prepare-only'],check=True,capture_output=True)
 admit=root/'registry_fixture_admission.json';admit.write_text(json.dumps({'all_checks_passed':True,'accepted_pre_execution_binding_sha256':sha(out/'pre_execution_binding.json')}));subprocess.run(cmd+['--admission',str(admit)],check=True,capture_output=True)
 registry=pd.read_csv(out/'empirical_level_registry.csv');decisions=pd.read_csv(out/'registry_decisions.csv');parent=pq.read_table(out/'geographic_parent_links.parquet');receipt=json.loads((out/'registry_receipt.json').read_text())
 assert registry.empty and 'empirical_level'in registry and 'partition_membership_sha256'in registry
 assert len(decisions)==5 and not decisions.promoted.any() and receipt['n_empirical_levels']==0
 assert parent.num_rows==0 and str(parent.schema.field('unit_id_lower').type)=='string' and str(parent.schema.field('n_shared_atoms').type)=='int64'
 assert not (out/'all_empirical_raw_units.parquet').exists() and receipt['all_promoted_units_require_normalization_typing_maps']
 copy=root/'different_source_copy';shutil.copytree(source,copy)
 positive=['python',str(HERE/'build_registry.py'),'--source',str(copy),'--output',str(root/'samebytes_copy_prepare'),'--baseline-admission',str(base),'--stability-admission',str(stable),'--prepare-only'];subprocess.run(positive,check=True,capture_output=True)
 bad=copy/'cap_030_raw_units.parquet';tampered=pd.read_parquet(bad);tampered.loc[0,'n_members']=99;tampered.to_parquet(bad,index=False)
 badcmd=['python',str(HERE/'build_registry.py'),'--source',str(copy),'--output',str(root/'must_not_prepare'),'--baseline-admission',str(base),'--stability-admission',str(stable),'--prepare-only'];result=subprocess.run(badcmd,capture_output=True,text=True);assert result.returncode!=0 and 'ACTUAL loaded raw source differs' in result.stderr
 print('FULL K0 prepare+signedCLIexport→pandas CSV/Arrow typed-parent/receipt consumers +tamperedalternate-source rejection PASS; no fake levels')

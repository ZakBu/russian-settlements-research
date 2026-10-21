from pathlib import Path
import hashlib,json,importlib.util,ast
import pandas as pd
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');O=B/'reviews/cycle07_partition_analysis_adapter_independent';P=B/'analysis/cycle07_tools/new_adapter_partition.py';C=B/'analysis/cycle07_tools/newsource_empirical_input_contract_v1.json';c=json.loads(C.read_text());checks=[]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for z in iter(lambda:f.read(8388608),b''):h.update(z)
 return h.hexdigest()
def path(x):return Path(x)if Path(x).is_absolute()else (B.parents[1]/x if Path(x).parts[0]=='research' else B/x)
def ck(k,v):checks.append({'check':k,'passed':bool(v)});assert v,k
ck('exact_adapter',sha(P)=='a27c4c117590870732b101e577058aa153974d3a8421c06441bbc4e7301083a1');ck('exact_contract',sha(C)=='100b8b72282e37056cca4bd7e73829bd27c781660d639514b0cab65f2c2a14fa')
spec=importlib.util.spec_from_file_location('adapter',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for k,v in m.self_test().items():ck('rerun_'+k,v)
a=ast.parse(P.read_text());old=ast.parse((B/'analysis/cycle07_tools/new_adapter_source477.py').read_text());oldf={n.name:ast.dump(n,include_attributes=False)for n in old.body if isinstance(n,ast.FunctionDef)}
for n in a.body:
 if isinstance(n,ast.FunctionDef)and n.name!='prepare':ck('unchanged_source_recipe_'+n.name,ast.dump(n,include_attributes=False)==oldf[n.name])
for x,h in c['expected_sha256'].items():ck('exact_bound_'+x,sha(path(x))==h)
pairs=pd.read_parquet(path(c['direct_focal_pairs']['path']),columns=['candidate_cap','partition_role','unit_id','id','core_id']);ck('full_pairs_unique',not pairs.duplicated(['candidate_cap','unit_id','id']).any());ck('explicit_partition',c['partition_role']=='candidate_knee_or_fallback')
for v in c['views']:
 cap=v['candidate_cap'];pfx=str(cap)+'_';u=pd.read_parquet(path(v['raw_units'])).set_index('unit_id');mem=pd.read_parquet(path(v['raw_memberships']),columns=['unit_id','id','partition_role']);ou=pd.read_parquet(path(v['pair_binding_original_raw_units']));ou=ou[ou.partition_role.eq(c['partition_role'])].set_index('unit_id');om=pd.read_parquet(path(v['pair_binding_original_raw_memberships']),columns=['unit_id','id','partition_role']);om=om[om.partition_role.eq(c['partition_role'])];pp=pairs[pairs.candidate_cap.eq(cap)];norm=pd.read_parquet(path(v['normalized_units']),columns=['unit_id','center_id']).set_index('unit_id')
 ck(pfx+'unique_complete173858members',len(mem)==173858 and mem.id.is_unique);ck(pfx+'exact_original_units',set(u.index)==set(ou.index));ck(pfx+'exact_original_members',set(zip(mem.unit_id,mem.id))==set(zip(om.unit_id,om.id)));ck(pfx+'exact_direct_pair_cohort',set(zip(mem.unit_id,mem.id))==set(zip(pp.unit_id,pp.id)));ck(pfx+'pair_partition',pp.partition_role.eq(c['partition_role']).all());ck(pfx+'exact_norm_ids',set(norm.index)==set(u.index))
 for field in ['core_id','candidate_cap','kind','unit_role','original_provider_seed_ids','region','name','lat','lon']:
  ck(pfx+'actual_raw_bridge_'+field,m.same(u.loc[ou.index,field],ou[field]).all())
 ck(pfx+'normalized_focal_is_actual_core',m.same(norm.loc[u.index,'center_id'],u.core_id).all());ck(pfx+'all_pair_core_ids_actual',m.same(pp.core_id.reset_index(drop=True),pp.unit_id.map(u.core_id).reset_index(drop=True)).all())
rec={'status':'ACCEPTED_PROSPECTIVE_SOURCE_PREPARATION','all_checks_passed':all(z['passed']for z in checks),'n_checks':len(checks),'n_failed':sum(not z['passed']for z in checks),'accepted_adapter_sha256':sha(P),'accepted_source_contract_sha256':sha(C),'checks':checks,'scope':'Exact partition adapter and four actual source bindings admitted for source-only preparation. All unchanged aggregation recipes AST-equal to previously admitted forest adapter;19 fixtures rerun; actual registry/original raw memberships and focal/seed/source metadata and all direct-pair cohorts independently matched. Empirical level metadata is not a regressor. No aggregation outcomes or fits admitted by this prospective check. Actual four source aggregates and exact preregistration require separate independent review before fits.'};(O/'admission.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');print(rec['status'],len(checks),sha(O/'admission.json'))

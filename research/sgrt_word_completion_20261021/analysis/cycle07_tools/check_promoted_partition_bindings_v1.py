"""Author source-only preflight; does not constitute independent admission."""
import hashlib,json,pathlib
import pandas as pd

BASE=pathlib.Path(__file__).resolve().parents[1].parent
ROOT=BASE.parents[1]
def resolve(s):
 p=pathlib.Path(s)
 return p if p.is_absolute() else (ROOT/p if s.startswith('research/') else BASE/p)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 contract=BASE/'analysis/cycle07_tools/newsource_empirical_input_contract_v1.json'
 c=json.loads(contract.read_text());checks={};pins={str(contract):digest(contract),str(pathlib.Path(__file__)):digest(pathlib.Path(__file__))}
 for s,h in c['expected_sha256'].items():
  p=resolve(s);assert digest(p)==h,(s,'changed');pins[str(p)]=h
 pairs=pd.read_parquet(resolve(c['direct_focal_pairs']['path']),columns=['candidate_cap','unit_id','id','core_id','partition_role'])
 for v in c['views']:
  cap=v['candidate_cap'];scope=c['partition_role'];u=pd.read_parquet(resolve(v['raw_units']));u=u[u.partition_role.eq(scope)].set_index('unit_id');m=pd.read_parquet(resolve(v['raw_memberships']));m=m[m.partition_role.eq(scope)]
  ou=pd.read_parquet(resolve(v['pair_binding_original_raw_units']));ou=ou[ou.partition_role.eq(scope)].set_index('unit_id');om=pd.read_parquet(resolve(v['pair_binding_original_raw_memberships']));om=om[om.partition_role.eq(scope)];pp=pairs[pairs.candidate_cap.eq(cap)]
  checks[f'{cap}_unit_cohort']=set(u.index)==set(ou.index)
  checks[f'{cap}_member_cohort']=set(zip(m.unit_id,m.id))==set(zip(om.unit_id,om.id))==set(zip(pp.unit_id,pp.id))
  checks[f'{cap}_pair_partition']=bool(pp.partition_role.eq(scope).all())
  for f in ['core_id','candidate_cap','kind','unit_role']:
   checks[f'{cap}_{f}']=u.loc[ou.index,f].fillna('<NA>').astype(str).equals(ou[f].fillna('<NA>').astype(str))
  adm=json.loads(resolve(v['normalization_admission']).read_text());checks[f'{cap}_normalized_admitted']=adm['all_checks_passed'] is True and adm['accepted_units_sha256']==digest(resolve(v['normalized_units']))
 assert all(checks.values()),checks
 out=BASE/'analysis/cycle07_promoted_partition_bindings_author_preflight_v1.json';assert not out.exists()
 out.write_text(json.dumps({'status':'AUTHOR_SOURCE_BINDING_PREFLIGHT_NOT_INDEPENDENT_ADMISSION','no_regression_metrics_read_or_computed':True,'checks':checks,'all_checks_passed':True,'source_sha256':pins},indent=2)+'\n');print(json.dumps({'checks':len(checks),'receipt_sha256':digest(out)}))
if __name__=='__main__':main()

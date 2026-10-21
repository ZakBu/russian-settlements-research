"""Promote only independently admitted stable DISTINCT NESTED full partitions."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def signature(ids):
 h=hashlib.sha256()
 for uid in sorted(map(str,ids)):h.update(uid.encode());h.update(b'\0')
 return h.hexdigest()
def relation(lower,upper):
 """Return exact refinement and bijection; independent of unit label spelling."""
 if lower.id.duplicated().any() or upper.id.duplicated().any():raise ValueError('duplicate source atom in partition')
 x=lower[['id','unit_id']].merge(upper[['id','unit_id']],on='id',how='outer',indicator=True,suffixes=('_lower','_upper'),validate='one_to_one')
 if not x._merge.eq('both').all():raise ValueError('partition atom axes differ')
 nested=x.groupby('unit_id_lower').unit_id_upper.nunique().eq(1).all()
 equivalent=nested and x.groupby('unit_id_upper').unit_id_lower.nunique().eq(1).all()
 return bool(nested),bool(equivalent),x.drop(columns='_merge')
def choose(partitions,stability):
 kept=[];decisions=[];previous=None
 for cap in sorted(partitions):
  m=partitions[cap];row=stability.loc[cap];raw=row['accepted'];accepted=raw is True or isinstance(raw,(bool,np.bool_)) and bool(raw)
  d={'candidate_cap':int(cap),'stability_accepted':accepted,'promoted':False,'empirical_level':None,'reason':'stability_not_admitted'}
  if accepted:
   nested,equivalent=(True,False) if previous is None else relation(previous,m)[:2]
   if not nested:d['reason']='not_exact_whole_child_coarsening'
   elif equivalent:d['reason']='equivalent_partition_earliest_eligible_cut_retained'
   else:
    d.update(promoted=True,empirical_level=len(kept),reason='distinct_nested_stable_cut');kept.append(cap);previous=m
  decisions.append(d)
 return kept,decisions

def binding(a):
 source=a.source;bp=source/'pre_execution_binding.json';base=json.loads(a.baseline_admission.read_text());stable=json.loads(a.stability_admission.read_text())
 if base.get('all_checks_passed') is not True or stable.get('all_checks_passed') is not True:raise ValueError('baseline/stability independent admission required')
 if base.get('accepted_source_binding_sha256')!=sha(bp):raise ValueError('baseline admission source binding mismatch')
 if stable.get('accepted_all50_ledger_sha256')!=sha(source/'all_50_bootstrap_ledger.parquet') or stable.get('accepted_stability_summary_sha256')!=sha(source/'retained_resolution_stability.csv'):raise ValueError('independent50 numeric admission bytes mismatch')
 paths=[bp,source/'run_receipt.json',source/'all_50_bootstrap_ledger.parquet',source/'retained_resolution_stability.csv',a.baseline_admission,a.stability_admission,HERE/'PROTOCOL.json',Path(__file__)]
 for p,h in base['accepted_unit_membership_files_sha256'].items():
  if sha(Path(p))!=h:raise ValueError('independently accepted raw membership changed')
  paths.append(Path(p))
 return {'code_sha256':sha(Path(__file__)),'protocol_sha256':sha(HERE/'PROTOCOL.json'),'inputs':{str(p.resolve()):sha(p)for p in paths},'source_binding_sha256':sha(bp)}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--baseline-admission',type=Path,required=True);ap.add_argument('--stability-admission',type=Path,required=True);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--admission',type=Path);a=ap.parse_args();now=binding(a);out=a.output
 if a.prepare_only:
  if out.exists():raise ValueError('fresh registry directory required')
  out.mkdir(parents=True);(out/'pre_execution_binding.json').write_text(json.dumps(now,indent=2));return
 old=json.loads((out/'pre_execution_binding.json').read_text())
 if now!=old:raise ValueError('registry source/code admission binding changed')
 admit=json.loads(a.admission.read_text())
 if admit.get('all_checks_passed') is not True or admit.get('accepted_pre_execution_binding_sha256')!=sha(out/'pre_execution_binding.json'):raise ValueError('independent exact registry execution admission required')
 if (out/'registry_receipt.json').exists():raise ValueError('completed registry immutable')
 protocol=json.loads((a.source/'pre_execution_binding.json').read_text())['protocol'];caps=protocol['extent']['candidate_caps_minutes'];stability=pd.read_csv(a.source/'retained_resolution_stability.csv').set_index('candidate_cap');partitions={};units={};axis=None
 for cap in caps:
  m=pd.read_parquet(a.source/f'cap_{cap:03}_raw_memberships.parquet');u=pd.read_parquet(a.source/f'cap_{cap:03}_raw_units.parquet');m=m.loc[m.partition_role.eq('candidate_knee_or_fallback')].copy();u=u.loc[u.partition_role.eq('candidate_knee_or_fallback')].copy()
  if m.id.duplicated().any() or u.unit_id.duplicated().any() or set(m.unit_id)!=set(u.unit_id):raise ValueError('nonexclusive/untyped raw source keys')
  if axis is None:axis=set(m.id)
  if set(m.id)!=axis:raise ValueError('candidate source axes differ')
  expected=m.groupby('unit_id').size();actual=u.set_index('unit_id').n_members.loc[expected.index]
  if not np.array_equal(expected,actual):raise ValueError('raw unit membership counts differ')
  partitions[cap]=m;units[cap]=u
 kept,decisions=choose(partitions,stability);parents=[];registry=[];allunits=[];allmembers=[]
 for level,cap in enumerate(kept):
  u=units[cap].copy();m=partitions[cap].copy();hashes=m.groupby('unit_id').id.apply(signature);u['unit_membership_sha256']=u.unit_id.map(hashes)
  for frame in [u,m]:frame['empirical_level']=level;frame['level']=level;frame['resolution_index']=level;frame['resolution_label']=f'empirical_level_{level}'
  if level+1<len(kept):
   nested,equivalent,links=relation(m,partitions[kept[level+1]])
   if not nested or equivalent:raise AssertionError('promoted cuts must be distinct exactnested')
   links=links.groupby(['unit_id_lower','unit_id_upper']).size().reset_index(name='n_shared_atoms');links['lower_empirical_level']=level;links['upper_empirical_level']=level+1;parents.append(links);u['parent_unit_id']=u.unit_id.map(links.set_index('unit_id_lower').unit_id_upper)
  else:u['parent_unit_id']=None
  u.to_parquet(out/f'level_{level:03}_raw_units.parquet',index=False);m.to_parquet(out/f'level_{level:03}_raw_memberships.parquet',index=False);allunits.append(u);allmembers.append(m)
  territorial=u.unit_role.eq('territorial_unit');pop=pd.to_numeric(u.loc[territorial,'core_population_2021'],errors='coerce');mass=pd.to_numeric(u.loc[territorial,'core_fixed_own_mass'],errors='coerce')
  registry.append({'empirical_level':level,'candidate_cap':cap,'source_partition_role':'candidate_knee_or_fallback','n_units':len(u),'n_territorial_units':int(territorial.sum()),'n_protected_carry':int((~territorial).sum()),'n_members':len(m),'partition_membership_sha256':signature(hashes.tolist()),'n_territorial_core_P_known':int(pop.notna().sum()),'n_territorial_core_P_unknown':int(pop.isna().sum()),'core_P_median':pop.median(),'core_P_p10':pop.quantile(.1),'core_P_p90':pop.quantile(.9),'core_fixed_Mi_min':mass.min(),'core_fixed_Mi_max':mass.max(),'population_bins_used_for_selection':False})
 pd.DataFrame(decisions).to_csv(out/'registry_decisions.csv',index=False);pd.DataFrame(registry).to_csv(out/'empirical_level_registry.csv',index=False)
 pd.concat(parents,ignore_index=True).to_parquet(out/'geographic_parent_links.parquet',index=False) if parents else pd.DataFrame(columns=['unit_id_lower','unit_id_upper','n_shared_atoms','lower_empirical_level','upper_empirical_level']).to_parquet(out/'geographic_parent_links.parquet',index=False)
 if allunits:pd.concat(allunits,ignore_index=True).to_parquet(out/'all_empirical_raw_units.parquet',index=False);pd.concat(allmembers,ignore_index=True).to_parquet(out/'all_empirical_raw_memberships.parquet',index=False)
 if binding(a)!=old:raise ValueError('source/code bytes changed during registry construction')
 receipt={'status':'EMPIRICAL_DISTINCT_NESTED_STABLE_CUT_REGISTRY_COMPUTED_PENDING_RESULT_REVIEW','n_empirical_levels':len(kept),'retained_candidate_caps':kept,'exact_atom_axis_count':len(axis),'source_binding_sha256':now['source_binding_sha256'],'pre_execution_binding_sha256':sha(out/'pre_execution_binding.json'),'independent_design_admission_sha256':sha(a.admission),'all_promoted_units_require_normalization_typing_maps':True,'operational_caps_are_not_levels':True,'observational_horizon_minutes':180,'outside_horizon_is_unobserved_not_no_links':True,'files':{p.name:sha(p)for p in out.iterdir()if p.is_file()}}
 (out/'registry_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()

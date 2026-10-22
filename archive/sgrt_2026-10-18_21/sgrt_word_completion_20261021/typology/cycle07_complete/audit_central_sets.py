"""Independent membership/native-population readback for a normalized unit table.
This audit is not a scientific admission of the hierarchy's linkage mechanism.
"""
import argparse,hashlib,json
from pathlib import Path
import pandas as pd
from classify_complete import truth,number

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate_core_members(ids,core,atomic,external_exception,unit_role,additive_ids):
 if atomic: assert len(ids)==1 and core==ids,'Atomic source member and core must be identical singleton'
 external=set(core)-set(ids)
 if external:
  assert external_exception is True and unit_role=='context_overlay','External focal core not explicitly admitted'
  assert not(external & set(additive_ids)),'Additive focal core outside unit members'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();c=json.loads(Path(a.contract).read_text());out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh audit output required')
 paths={k:Path(c[k]) for k in ('units_path','memberships_path','nodes_path')}
 for k,p in paths.items():assert sha(p)==c[k.replace('_path','_sha256')]
 u=pd.read_parquet(paths['units_path']);m=pd.read_parquet(paths['memberships_path']);n=pd.read_parquet(paths['nodes_path'])
 uid=c['unit_id_column'];nid=c['node_id_column'];assert u[uid].is_unique and n[nid].is_unique
 assert not m.duplicated([c['membership_unit_column'],c['membership_node_column']]).any(),'Repeated member inside unit'
 assert set(m[c['membership_unit_column']])==set(u[uid]),'Units/member coverage differs'
 assert set(m[c['membership_node_column']])<=set(n[nid]),'Unknown member source ID'
 n=n.set_index(nid,drop=False);groups=m.groupby(c['membership_unit_column'],sort=False)[c['membership_node_column']].agg(list).to_dict();checks=[]
 def check(unit,field,actual,expected):
  good=(pd.isna(actual) and pd.isna(expected)) or (not pd.isna(actual) and not pd.isna(expected) and actual==expected)
  checks.append({'unit_id':unit,'field':field,'actual':str(actual),'expected':str(expected),'passed':bool(good)})
 for _,r in u.iterrows():
  unit=r[uid];ids=groups[unit];core=json.loads(r[c['central_object_ids_column']]);definition=r[c['central_object_definition_column']]
  assert len(core)==len(set(core)) and set(core)<=set(n.index),'Bad core set'
  if definition in ('one_focal_core','own_atomic'): assert len(core)==1
  elif definition=='all_supported_cores':assert core
  elif definition=='not_applicable':assert not core
  else:raise ValueError(definition)
  raw=n.loc[ids];popmask=raw[c['population_axis_column']].map(lambda v:truth(v) is True)
  whole=raw.loc[popmask];outside=whole.loc[~whole.index.isin(core)]
  roles=outside[c['rural_role_column']].map(truth);rural=outside.loc[roles.map(lambda x:x is True)]
  unknown=int(roles.isna().sum());check(unit,c['rural_member_count_column'],r[c['rural_member_count_column']],len(rural));check(unit,c['unknown_role_member_count_column'],r[c['unknown_role_member_count_column']],unknown)
  focal=n.loc[core] if core else n.iloc[:0]
  atomic=r[c['kind_column']]=='atomic_settlement'
  exception_column=c.get('nonadditive_external_central_exception_column')
  exception=truth(r[exception_column]) if exception_column else False
  validate_core_members(ids,core,atomic,exception,r[c['unit_role_column']],{x for x in core if truth(n.loc[x,c['population_axis_column']]) is True})
  for obj,data in [('own',focal),('center',focal),('rural',rural),('system',whole)]:
   if (atomic and obj!='own') or (not atomic and obj=='own'):continue
   spec=c['objects'][obj]
   for year in ('2002','2010','2021'):
    vals=pd.to_numeric(data[c['node_population_columns'][year]],errors='coerce');valid=vals.map(lambda v:number(v) is not None)
    complete=bool(len(data)>0 and valid.all()) if obj in ('own','center','system') else bool(valid.all())
    if obj=='rural':complete=complete and unknown==0
    if obj=='system' and any(truth(n.loc[x,c['population_axis_column']]) is not True for x in core):complete=False
    if obj in ('rural','system'):expected=float(vals.loc[valid].sum()) if valid.any() else 0. if obj=='rural' and len(data)==0 else float('nan')
    else:expected=float(vals.sum()) if complete else float('nan')
    check(unit,spec['population'][year],r[spec['population'][year]],expected)
    check(unit,spec['complete'][year],truth(r[spec['complete'][year]]),complete)
 out.mkdir(parents=True);d=pd.DataFrame(checks);d.to_parquet(out/'all_readbacks.parquet',index=False);d.loc[~d.passed].to_csv(out/'failures.csv',index=False)
 ok=bool(d.passed.all());receipt={'status':'ACCEPTED_CENTRAL_SET_MEMBERSHIP_AND_POPULATION_READBACK' if ok else 'REJECTED','all_checks_passed':ok,'checks':len(d),'n_failures':int((~d.passed).sum()),'units_sha256':sha(paths['units_path']),'memberships_sha256':sha(paths['memberships_path']),'nodes_sha256':sha(paths['nodes_path']),'rural_excludes_exact_central_set':ok,'whole_members_counted_once':ok,'hierarchy_mechanism_scientifically_admitted_by_this_audit':False,'code_sha256':sha(__file__),'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
 for k,p in paths.items():assert sha(p)==c[k.replace('_path','_sha256')]
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False));assert ok
if __name__=='__main__':main()

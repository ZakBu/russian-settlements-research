#!/usr/bin/env python3
"""Source-pinned compact map/report views. No hierarchy/type/geometry inference."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def path(p):
 p=Path(p);return p if p.is_absolute() else ROOT/p
def load(s,watch):
 p=path(s['path']);assert sha(p)==s['sha256'],str(p);watch[str(p)]=s['sha256'];return pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
def spec(p):return {'path':str(p.resolve()),'sha256':sha(p)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();cp=Path(a.contract);c=json.loads(cp.read_text());out=Path(a.output);assert not out.exists(),'Fresh compact source binding required';watch={str(cp.resolve()):sha(cp)}
 assert c['family']=='cycle07_bottomup' and c['scope_status']=='BASELINE_CHECKPOINT_NOT_FINAL477_INTEGRATED'
 assert c['component_integration_status'] and c['population_frame_scope']
 ns=load(c['nodes'],watch);required=['id','name','lat','lon','population_2021','source_record_id_2021','source2021_effective_settlement_type','source2021_role_has_dated_source','is_additive_source_unit'];assert set(required)<=set(ns)
 nodes=ns[required[:6]].copy();nodes['formal_city2021']=ns.source2021_effective_settlement_type.eq('город')&ns.source2021_role_has_dated_source.eq(True)&ns.source_record_id_2021.notna()&ns.is_additive_source_unit.eq(True)
 assert nodes.id.is_unique;units=[];types=[];members=[];events=[];views={};sourcepin={}
 keep=['unit_id','operational_view_id','display_retained','empirical_resolution_supported','candidate_cap','partition_role','kind','unit_role','core_id','center_id','name','unit_name','region','lat','lon','n_children','children_semantic_ids','parent_unit_id','ancestry_depth','ancestry_depth_is_functional_rank','central_object_definition','central_object_ids','center_scope','n_members','max_member_direct_minutes','max_member_geodesic_km','extent_complete','n_member_direct_known','n_member_direct_unknown','core_fixed_own_mass','primary2010_population_share','protected_secondary2010_population_share','population2010_known_denominator','2010_missing_population_count','population_quality_share_denominator_scope','unknown_nonadditive_central_population_slots2010']
 for v in c['views']:
  u=load(v['units'],watch);ty=load(v['types'],watch);m=load(v['memberships'],watch);ev=load(v['trajectory'],watch)
  assert u.unit_id.is_unique and ty.unit_id.is_unique and set(u.unit_id)==set(ty.unit_id)
  assert u.operational_view_id.nunique()==1;vid=str(u.operational_view_id.iloc[0]);assert vid==v['view_id'] and vid not in views
  assert u.partition_role.nunique()==1 and u.partition_role.iloc[0]==v['partition_role'];assert u.display_retained.eq(v['display_retained']).all()
  assert set(m.unit_id)==set(u.unit_id) and not m.duplicated(['unit_id','id']).any();assert not m.is_overlay_membership.any();assert not m.id.duplicated().any(),'Primary partition must contain every sourceNP once';assert set(m.id)<=set(nodes.id)
  if 'kind' not in u:raise ValueError('Raw kind must be retained')
  if 'unit_name' not in u and 'name' in u:u['unit_name']=u['name']
  f=u[[x for x in keep if x in u]].copy();f['level']=vid;units.append(f);types.append(ty);members.append(m[['unit_id','id','is_overlay_membership']]);events.append(ev);views[vid]=v['semantics']
  for key in ['units','types','memberships','trajectory']:sourcepin[vid+'__'+key]=v[key]
 allu=pd.concat(units,ignore_index=True);allt=pd.concat(types,ignore_index=True);allm=pd.concat(members,ignore_index=True);alle=pd.concat(events,ignore_index=True)
 assert allu.unit_id.is_unique and allt.unit_id.is_unique and set(allu.unit_id)==set(allt.unit_id);assert c['primary_view_id'] in views
 display=allu.loc[allu.display_retained.eq(True),'unit_id'];du=allu[allu.unit_id.isin(display)].copy();dt=allt[allt.unit_id.isin(display)].copy();dm=allm[allm.unit_id.isin(display)].copy();retained=du.level.unique().tolist();assert c['primary_view_id'] in retained
 partition_n=dm.groupby(dm.unit_id.map(du.set_index('unit_id').level)).id.nunique();assert partition_n.eq(c['population_frame_scope']['geographic_partition_rows']).all()
 merge=load(c['merge_diagnostics'],watch);knee=load(c['knee_diagnostics'],watch);boot=load(c['bootstrap_diagnostics'],watch)
 assert set(merge.candidate_cap)==set(knee.candidate_cap)==set(boot.candidate_cap);assert boot.groupby('candidate_cap').size().eq(50).all(),'Wait for actual complete ledger, never manufacture missing replicas';assert not boot.duplicated(['candidate_cap','replicate_id']).any()
 assert {'knee_status','retained'}<=set(knee),'Actual controller decision must provide reviewed knee/retention fields; no default false or stable inference'
 out.mkdir(parents=True);tables={'nodes':nodes,'units':du,'types':dt,'memberships':dm,'all_units':allu,'all_types':allt,'all_trajectory':alle,'merge_diagnostics':merge,'knee_diagnostics':knee,'bootstrap_diagnostics':boot}
 sources={}
 for key,d in tables.items():p=out/(key+'.parquet');d.to_parquet(p,index=False,compression='zstd');sources[key]=spec(p)
 sources.update({'rawsource__'+k:v for k,v in sourcepin.items()})
 if c.get('coastline'):sources['coastline']=c['coastline'];loadcheck=path(c['coastline']['path']);assert sha(loadcheck)==c['coastline']['sha256'];watch[str(loadcheck)]=c['coastline']['sha256']
 for v in c['independent_admissions']:
  p=path(v['path']);assert sha(p)==v['sha256'];r=json.loads(p.read_text())
  for k in v['status_pointer']:r=r[k]
  assert r==v['expected_status'] and 'ACCEPT' in str(r).upper();watch[str(p)]=v['sha256']
 cfg={'family':'cycle07_bottomup','status':'ACTUAL_BASELINE_CHECKPOINT_SOURCE_BOUND','retained_resolutions':retained,'zoom_resolution':c['primary_view_id'],'view_metadata':views,'external_context_anchor_ids':['ctx:RU-FED-MOW','ctx:RU-FED-SPB'],'dpi':c.get('dpi',125),'sources':sources,'independent_admissions':c['independent_admissions'],'component_integration_status':c['component_integration_status'],'population_frame_scope':c['population_frame_scope'],'structural_display_aliases':c.get('structural_display_aliases',{})}
 (out/'map_config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
 assert all(sha(p)==s for p,s in watch.items()),'Source bytes changed during binding'
 receipt={'status':'ACTUAL_COMPACT_VIEW_BINDING_PENDING_INDEPENDENT_REVIEW','source_contract_sha256':sha(cp),'code_sha256':sha(__file__),'watched_sources':watch,'all_view_unit_counts':allu.groupby('level').size().to_dict(),'displayed_partition_counts':partition_n.to_dict(),'classification_changed':False,'coordinate_or_geometry_changed':False,'source_integration_status':c['component_integration_status'],'files':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
 (out/'binding_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(out),'views':list(views),'displayed':retained},ensure_ascii=False))
if __name__=='__main__':main()

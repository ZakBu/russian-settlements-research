#!/usr/bin/env python3
"""Independent readback checks for Graph20's Solnechny identity/point split."""
import hashlib,json,math
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/settlements-work/continuation_20261004')
G=ROOT/'accepted_graph20_solnechny_20261005/accepted_identity_edges.parquet'; P=ROOT/'accepted_graph20_solnechny_20261005/accepted_point_uses.parquet'; A=ROOT/'accepted_graph20_solnechny_20261005/receipt.json'; C=ROOT/'accepted_graph20_solnechny_20261005/coverage.json'; S=ROOT/'coverage_graph20_solnechny_20261005/scoped_joint_coverage.json'; B=Path(__file__).resolve().parents[1]/'evidence/mass_joint_20261004/graph20_solnechny/blocked_targets_graph20.json'; L=ROOT/'root/long_graph20_solnechny_patch_20261005/settlements_long_refreshed.parquet'; LR=ROOT/'root/long_graph20_solnechny_patch_20261005/refresh_receipt.json'
IDS=['2002:1_TOM_01_04.xls:0:8707','ROSSTAT2010:T5:p178:l51','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:49262']; POP=[10809,10384,8428]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
a=json.loads(A.read_text()); c=json.loads(C.read_text()); s=json.loads(S.read_text()); lr=json.loads(LR.read_text()); blocked=json.loads(B.read_text())['blocked_target_source_record_ids']
assert a['new_identity_rows']==2 and a['new_direct_point_uses']==1 and a['new_continuity_point_uses']==0
e=pd.read_parquet(G);pairs={(IDS[0],IDS[1]),(IDS[1],IDS[2])};sub=e[e.from_source_record_id.astype(str).isin(IDS)&e.to_source_record_id.astype(str).isin(IDS)];assert {(str(r.from_source_record_id),str(r.to_source_record_id)) for r in sub.itertuples()}==pairs
p=pd.read_parquet(P);q=p[p.target_source_record_id.astype(str).isin(IDS)];assert q.target_source_record_id.astype(str).tolist()==[IDS[2]];assert (float(q.iloc[0].latitude),float(q.iloc[0].longitude))==(55.2799566,89.825436)
assert set(IDS[:2]).issubset(set(blocked))
l=pd.read_parquet(L);q=l[l.observation_id.astype(str).isin(['census:'+x for x in IDS])].set_index('observation_id');assert len(q)==3
for i,pop in zip(IDS,POP):
 r=q.loc['census:'+i];assert int(r.population_value)==pop and bool(r.census_full_chain) and str(r.entity_id).endswith(IDS[2])
for i in IDS[:2]: assert pd.isna(q.loc['census:'+i].latitude) and pd.isna(q.loc['census:'+i].longitude)
r=q.loc['census:'+IDS[2]];assert (float(r.latitude),float(r.longitude))==(55.2799566,89.825436)
assert lr['final_rows']==865395 and lr['census_rows']==465800 and int(lr['selected_census_population_sum'])==434700152 and lr['population_values_modified'] is False
base_s=json.load(open('/workspace/settlements-work/continuation_20261004/coverage_graph19_lokot_20261005/scoped_joint_coverage.json')); axes={}
for y,add in [('2002',0),('2010',0),('2021',8428)]:
 now=s['results'][y];old=base_s['results'][y];assert now['available_scope_joint_population']-old['available_scope_joint_population']==add; assert now['remaining_population_to_99']==max(0,math.ceil(now['control_population']*.99)-now['available_scope_joint_population']);axes[y]={'available_scope_joint_population':now['available_scope_joint_population'],'available_scope_joint_percent':now['available_scope_joint_percent'],'added_vs_graph19':add,'remaining_to_99':now['remaining_population_to_99'],'strict_NP_joint_population':now['strict_NP_joint_population'],'strict_NP_joint_fraction':now['strict_NP_joint_population']/now['control_population']}
res={'status':'independent_graph20_solnechny_readback_passed','identity_edges':2,'direct_current_points':1,'historical_point_uses':0,'historical_point_targets_explicitly_blocked':IDS[:2],'full_chain_rows':3,'coordinate_rows':1,'population_values_retained':dict(zip(['2002','2010','2021'],POP)),'full_long_rows':lr['final_rows'],'full_long_census_rows':lr['census_rows'],'full_long_census_population_sum':int(lr['selected_census_population_sum']),'axes':axes,'sha256':{str(x):sha(x) for x in [A,G,P,C,S,L,LR]}}
out=Path(__file__).resolve().parents[1]/'evidence/mass_joint_20261004/graph20_solnechny/independent_readback.json';out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n');print(json.dumps(res,ensure_ascii=False,indent=2))

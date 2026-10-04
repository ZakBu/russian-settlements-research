#!/usr/bin/env python3
"""Scoped point-choice quarantine audit; candidate-only, no baseline mutation."""
from __future__ import annotations
import hashlib,json,math,sys
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/settlements-work');BASE=ROOT/'continuation_20261004'
OUT=BASE/'R4/point_quarantine_scope_recovery_20261004'
REPO=Path('/workspace/russian-settlements-research')
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
GRAPH=BASE/'accepted_mass_rule_corrections_origin_corrected/accepted_identity_edges.parquet'
POINTS=BASE/'accepted_mass_rule_corrections_origin_corrected/accepted_point_uses.parquet'
COVERAGE=BASE/'accepted_mass_rule_corrections_origin_corrected/coverage.json'
GNLEDGER=BASE/'R4/current_full_chain_native_geonames_points_20261004/point_candidate_ledger.jsonl'
GNPOINTS=BASE/'R4/current_full_chain_native_geonames_points_20261004/staged_point_uses.csv'
WIDE=ROOT/'wikidata/wide_v5/wide_point_bindings.parquet'
WDREVIEW=Path('/workspace/settlements-work/coordinates/independent_review_v1/review.json')
BLOCKED=Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')
CITY='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'
TARGETS={CITY+'25288':'Усть-Кут',CITY+'155218':'Покачи',CITY+'149473':'Межгорье'}
YEARS=(2002,2010,2021)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def compact(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def hav(a,b):
 p1,p2=map(math.radians,a);q1,q2=map(math.radians,b);dp=q1-p1;dl=q2-p2
 z=math.sin(dp/2)**2+math.cos(p1)*math.cos(q1)*math.sin(dl/2)**2
 return 6371.0088*2*math.asin(math.sqrt(z))
class DSU:
 def __init__(self,f):
  self.ids=f.source_record_id.astype(str).tolist();self.ix={s:i for i,s in enumerate(self.ids)};self.p=list(range(len(self.ids)));self.r=[0]*len(self.ids);self.m=[{2002:1,2010:2,2021:4}[int(y)] for y in f.census_year]
 def find(self,x):
  if isinstance(x,str):x=self.ix[x]
  while self.p[x]!=x:self.p[x]=self.p[self.p[x]];x=self.p[x]
  return x
 def union(self,a,b):
  x,y=self.find(a),self.find(b)
  if x==y:return
  if self.m[x]&self.m[y]:raise ValueError('same-year graph collision')
  if self.r[x]<self.r[y]:x,y=y,x
  self.p[y]=x;self.m[x]|=self.m[y]
  if self.r[x]==self.r[y]:self.r[x]+=1

def main():
 if OUT.exists():raise SystemExit(f'refusing to overwrite {OUT}')
 OUT.mkdir(parents=True)
 source=pd.read_parquet(SEL,columns=['source_record_id','census_year','settlement_name','settlement_type','region_raw','population','okato','oktmo','source_native_id'])
 source.source_record_id=source.source_record_id.astype(str);source.census_year=source.census_year.astype(int)
 ids={str(k):v for k,v in TARGETS.items()}
 gnrows=[json.loads(x) for x in GNLEDGER.read_text(encoding='utf-8').splitlines()]
 gn_by={x['source_record_id']:x for x in gnrows}
 wide=pd.read_parquet(WIDE)
 wide=wide[wide.source_record_id.astype(str).isin(ids)].copy()
 wide_by={str(r.source_record_id):r for r in wide.itertuples(index=False)}
 review=json.loads(WDREVIEW.read_text(encoding='utf-8'))
 held_facts={x['source_record_id']:x for x in review.get('unresolved_provider_point_comparisons',[])}
 # Source rows and direct point-use rule state are taken from the frozen GN candidate ledger.
 blocked=set(json.loads(BLOCKED.read_text())['blocked_target_source_record_ids'])
 dispositions=[]
 for sid,name in ids.items():
  g=gn_by[sid];w=wide_by[sid];s=source[source.source_record_id.eq(sid)].iloc[0]
  qid=str(w.wikidata_qid);p625=json.loads(w.wikidata_truthy_p625_claims_json or '[]')
  aliases=g['whole_adm1_gn_aliases'];hist=g.get('historical_witness')
  histpt=(hist['lat_2011_raw'],hist['lon_2011_raw']) if hist else None
  for x in aliases:
   x['distance_historical_to_gn_km']=hav(histpt,(x['latitude'],x['longitude'])) if histpt else None
   x['distance_wikidata_P625_to_gn_km']=min((hav((p['latitude'],p['longitude']),(x['latitude'],x['longitude'])) for p in p625),default=None)
  qcoords=[(p['latitude'],p['longitude']) for p in p625 if p.get('wgs84_valid',True)]
  spread=max((hav(a,b) for i,a in enumerate(qcoords) for b in qcoords[i+1:]),default=0)
  name=name
  if sid.endswith(':25288'):
   disposition='candidate_scoped_new_GN_point_resolves_old_provider_distance_lead'
   reasons=['old hold was point-choice-only: exact-code/current-label physical-city QID has one P625 5.763 km from raw Tochno point; prior reviewer held because no exact same-OKATO 2011 point was available. New route uses a different coordinate origin: unique whole-ADM1 GN PPLA2 point plus exact unique named typed 2009/2011 city point; GN is 3.248 km from historical, 3.143 km from raw Tochno, and 2.857 km from exact-code Wikidata P625. Current atomic source row has exact unique OKTMO/native identifier and exact name/type/region/population. Historic OKATO differs from current OKATO; no same-code claim.']
   selected=aliases[0] if aliases else None
   ready=bool(selected and hist and w.wikidata_truthy_exact_p764_match and w.wikidata_name_exact_label and not w.entity_competition_across_tsv_or_truthy and len(p625)==1 and selected['feature_code']=='PPLA2' and selected['distance_historical_to_gn_km']<=5)
   if not ready:disposition='hold_candidate_route_failed';reasons.append('one_or_more scoped source/GN/history/current QID conditions missing')
  elif sid.endswith(':155218'):
   disposition='hold_true_unresolved_multi_P625_choice'
   reasons=['existing quarantine is coordinate-choice-only (not a finding that current source row is aggregate or nonphysical). Exact current code/name QID has two valid P625 points 11.811 km apart; one matches the unique exact whole-ADM1 GeoNames PPL point. No unique typed 2009/2011 historic point exists to adjudicate which point represents the locality. Keep both P625 claims and hold this point selection.']
   selected=None;ready=False
  else:
   disposition='hold_true_historic_vs_current_point_conflict'
   reasons=['existing quarantine is coordinate-choice-only. Exact current source code/name city QID has P625 near one GN PPL alias; raw 2011 exact-code/name/city-type point is 22.571 km away and independently aligns within 0.614 km to a different GN PPLA2 exact-name city candidate. This is a real physical-place choice conflict; do not blanket-release. Current source row identity/grain is not discredited, but candidate point remains held pending independent locality geometry/official location evidence.']
   selected=None;ready=False
  oldfact=held_facts.get(sid,{})
  rec={'source_record_id':sid,'name':name,'population_2021':int(s.population),'source_native_id':str(s.source_native_id),'source_OKATO_current':str(s.okato),'source_OKTMO_current':str(s.oktmo),'source_type':str(s.settlement_type),'source_region':str(s.region_raw),
   'prior_GN_candidate_disposition':g['candidate_status'],'prior_V7_hold_memberships':g.get('existing_v7_point_hold_memberships',[]),'legacy_point_quarantine_membership':sid in blocked,
   'hold_scope':'coordinate_or_provider_point_choice_only; no identity, population grain, native source code, or provider-identifier binding conclusion is inherited',
   'previous_independent_review_hold_fact':oldfact,'source_raw_current_primary_evidence':{'checks_json':g['current_source_raw_checks_json'],'payload_json':g['current_source_raw_payload_json'],'payload_sha256':g['current_source_raw_payload_sha256'],'row_1based':g['current_source_raw_row_1based']},
   'current_QID_code_and_class_evidence':{'qid':qid,'exact_P764_source_OKTMO':bool(w.wikidata_truthy_exact_p764_match),'exact_Russian_label':bool(w.wikidata_name_exact_label),'physical_P31_or_P279_path_in_reviewed_wide':bool(json.loads(w.wikidata_truthy_p31_claims_json or '[]')),'P131_claims_json':w.wikidata_truthy_p131_claims_json,'P625_claims_json':w.wikidata_truthy_p625_claims_json,'source_code_competition':bool(w.entity_competition_across_tsv_or_truthy),'historic_classifier_point_distance_to_P625_km':min((hav(histpt,(p['latitude'],p['longitude'])) for p in p625),default=None) if histpt else None,'P625_pairwise_spread_km':spread},
   'historical_exact_typed_point_witness':hist,'whole_ADM1_GN_physical_aliases_and_distances':aliases,
   'candidate_only':bool(ready),'coordinate_admission':False,'provider_identifier_binding_asserted':False,'wikidata_P764_provenance_independence_asserted':False,'GN_upstream_measurement_independence_proven':False,
   'proposed_point':{'geonameid':selected['geonameid'],'feature_code':selected['feature_code'],'latitude':selected['latitude'],'longitude':selected['longitude'],'raw_RU_line_1based':selected['source_line_1based'],'raw_RU_byte_start':selected['byte_start'],'raw_RU_byte_end':selected['byte_end'],'raw_RU_line_sha256':selected['line_sha256']} if ready and selected else None,
   'rule_status':disposition,'reasoning':reasons}
  dispositions.append(rec)
 # Exact conditional gain for only the one newly supportable scoped point.
 sys.path.insert(0,str(REPO))
 from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES,ACCEPTED_PROJECTION_STATUSES
 allsel=source[source.census_year.isin(YEARS)].copy().reset_index(drop=True)
 edges=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','relation','decision_status','selection_projection_status'])
 points=pd.read_parquet(POINTS,columns=['target_source_record_id','coordinate_admission_status'])
 if not edges.decision_status.astype(str).isin(ACCEPTED_EDGE_STATUSES).all() or not edges.selection_projection_status.astype(str).isin(ACCEPTED_PROJECTION_STATUSES).all() or not edges.relation.eq('same_place').all():raise RuntimeError('bad canonical graph')
 if not points.coordinate_admission_status.astype(str).isin(ACCEPTED_COORDINATE_STATUSES).all():raise RuntimeError('bad canonical point ledger')
 dsu=DSU(allsel);allids=set(dsu.ix)
 for e in edges.itertuples(index=False):
  if str(e.from_source_record_id) not in allids or str(e.to_source_record_id) not in allids:raise RuntimeError('graph endpoint not selected')
  dsu.union(str(e.from_source_record_id),str(e.to_source_record_id))
 targets=set(points.target_source_record_id.astype(str));comp=dsu.find(CITY+'25288');members=[x for x in dsu.ix if dsu.find(x)==comp]
 if any(x in targets for x in members):raise RuntimeError('target full-chain component already has accepted point')
 memberrows=allsel[allsel.source_record_id.isin(members)]
 if set(memberrows.census_year.astype(int))!=set(YEARS):raise RuntimeError('Ust-Kut is not a full three-census component')
 increment={str(y):{'rows':int((memberrows.census_year==y).sum()),'population':int(memberrows.loc[memberrows.census_year.eq(y),'population'].fillna(0).sum())} for y in YEARS}
 base=json.loads(COVERAGE.read_text())
 gains=[]
 for m in base['census_metrics']:
  y=int(m['year']);joint=m['axes']['joint_admitted_coordinate_and_full_chain']
  inc=increment[str(y)]
  gains.append({'year':y,'conditional_added_rows':inc['rows'],'conditional_added_population':inc['population'],'baseline_joint_rows':int(joint['rows']),'baseline_joint_population':int(joint['known_population']),'after_joint_rows':int(joint['rows'])+inc['rows'],'after_joint_population':int(joint['known_population'])+inc['population'],'interpretation':'one candidate seed propagated only through already accepted full-chain identity component; candidate-only, no census-date coordinate claim'})
 proof={'status':'candidate_only_scoped_resolution_no_admissions','candidate_points':[r for r in dispositions if r['candidate_only']],'hold_audit':[r for r in dispositions if not r['candidate_only']],'conditional_joint_gain':gains,
  'input_hashes':{str(p):sha(p) for p in [SEL,GRAPH,POINTS,COVERAGE,GNLEDGER,GNPOINTS,WIDE,WDREVIEW,BLOCKED]},
  'scope':'Separates prior provider/coordinate-choice quarantine from current primary source identity. Only Ust-Kut receives a new candidate-only point proposal: whole-ADM1 unique GN PPLA2 point is supported by a same-name/same-city-type unique 2009/2011 historic physical point and falls in the same ~3km cluster as current Tochno and exact-code Wikidata P625. Historic OKATO differs from current OKATO, so no historic code-continuity claim. Pokachi multi-P625 choice and Mezhgorye competing current-vs-historic physical-place evidence remain holds.',
  'claims_not_made':['no identity changes','no source population changes','no FIAS/provider-ID binding','no P764 provenance independence','no GN upstream measurement independence','no exact census-date coordinate or precision claim'],
  'outputs':{}}
 (OUT/'scoped_quarantine_dispositions.jsonl').write_text(''.join(compact(r)+'\n' for r in dispositions),encoding='utf-8')
 candidate=[r for r in dispositions if r['candidate_only']]
 (OUT/'staged_scoped_point_uses.json').write_text(json.dumps([{'point_use_id':'GNQ-'+hashlib.sha256((r['source_record_id']+'|'+str(r['proposed_point']['geonameid'])).encode()).hexdigest()[:18],'target_source_record_id':r['source_record_id'],'target_year':2021,'latitude':r['proposed_point']['latitude'],'longitude':r['proposed_point']['longitude'],'coordinate_source':'GeoNames RU PPLA2; uniquely supported by raw named typed 2009/2011 physical point and current exact source/QID locality context','coordinate_admission_status':'candidate_only_pending_independent_review','candidate_only':True,'provider_identifier_binding_asserted':False,'census_date_measurement_proven':False,'historical_OKATO_equals_current_OKATO':False} for r in candidate],ensure_ascii=False,indent=2),encoding='utf-8')
 proof['candidate_count']=len(candidate);proof['hold_count']=len(dispositions)-len(candidate)
 proof['outputs']={n:{'sha256':sha(OUT/n),'bytes':(OUT/n).stat().st_size} for n in ['scoped_quarantine_dispositions.jsonl','staged_scoped_point_uses.json']}
 (OUT/'receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 print(json.dumps({'candidate_count':len(candidate),'hold_count':proof['hold_count'],'increment':increment,'gain':gains,'candidate':candidate[0]['name'] if candidate else None},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

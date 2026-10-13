#!/usr/bin/env python3
"""Candidate-only export and reproducible fixed large-settlement pilot sample."""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

F=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
W=Path('/workspace/settlements-work/wikidata/wide_v5')
OUT=Path(__file__).resolve().parent
SEED=2026100301
N_DRAWS=300
HOLDS={
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:149473':'Mezhgorye: unresolved city point-choice conflict',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:25288':'Ust-Kut: unresolved city point-choice conflict',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:155218':'Pokachi: multiple distinct eligible P625 coordinates',
'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:50511':'Feodosia: multiple distinct eligible P625 coordinates',
}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def js(v):
 if v is None or pd.isna(v) or v=='': return []
 try: return json.loads(v)
 except Exception: return []

def ids(xs): return {str(x.get('value_qid')) for x in xs if x.get('value_qid')}

def pband(p):
 if pd.isna(p): return 'unknown'
 p=float(p)
 return '<2,000' if p<2000 else '2,000–9,999' if p<10000 else '10,000–49,999' if p<50000 else '50,000+'

def tband(x):
 s=str(x or '').casefold()
 if re.search(r'город|\bcity\b',s): return 'city'
 if re.search(r'пгт|пос[её]лок городского типа|рабочий пос[её]лок|курортный пос[её]лок',s): return 'urban-type settlement'
 if re.search(r'село|деревн|пос[её]лок|хутор|станиц|аул|сельцо|слобод|\bvillage\b',s): return 'rural settlement'
 return 'other/unclassified'

def stats(df, groupcols):
 if df.empty: return []
 g=(df.assign(population=pd.to_numeric(df.population,errors='coerce'))
    .groupby(groupcols,dropna=False,sort=True).agg(rows=('source_record_id','nunique'),population=('population','sum')).reset_index())
 return g.to_dict('records')

def main():
 selected=pd.read_parquet(F/'selected_observations.parquet')
 selected=selected.loc[selected.census_year.eq(2021)&selected.is_additive_settlement_record.fillna(False)&selected.population_scope.eq('settlement')].copy()
 uses=pd.read_parquet(F/'accepted_point_uses.parquet',columns=['target_year','target_source_record_id'])
 accepted=set(uses.loc[uses.target_year.eq(2021),'target_source_record_id'].astype(str))
 selected['source_record_id']=selected.source_record_id.astype(str)
 targets=selected.loc[~selected.source_record_id.isin(accepted)].copy()
 phys=pd.read_parquet(W/'provider_code_candidate_screen.parquet',columns=['source_record_id','source_is_physical_np'])
 phys['source_record_id']=phys.source_record_id.astype(str)
 targets=targets.merge(phys,on='source_record_id',how='left',validate='one_to_one')
 targets=targets.loc[targets.source_is_physical_np.fillna(False).astype(bool)].copy()
 wide=pd.read_parquet(W/'wide_point_bindings.parquet')
 wide['source_record_id']=wide.source_record_id.astype(str)
 wide=wide.loc[wide.source_record_id.isin(set(targets.source_record_id))].copy()
 for col,src in [('p31','wikidata_truthy_p31_claims_json'),('p625','wikidata_truthy_p625_claims_json'),('p131','wikidata_truthy_p131_claims_json'),('p764','wikidata_truthy_exact_p764_claims_json')]: wide[col]=wide[src].map(js)
 wide['p31ids']=wide.p31.map(ids)
 sys.path.insert(0,'/workspace/russian-settlements-research')
 from research_rebuild.mass_linkage.coordinate_validation_packet import wikidata_type_lineage,_load_region_geometries,_point_inside_source_region
 anc_path=Path('/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json')
 ancestry=json.loads(anc_path.read_text()); prof=wikidata_type_lineage(ancestry)
 entities=ancestry.get('entities',{})
 geometries,region_iso=_load_region_geometries()
 region_screen=pd.read_parquet('/workspace/settlements-work/coordinates/region_screen_v1/region_point_screen.parquet',columns=['source_record_id','geometry_iso'])
 geom_by={str(k):v for k,v in region_screen.set_index('source_record_id').geometry_iso.to_dict().items()}
 for qids in wide.p31ids:
  pass
 wide['physical_lineage']=wide.p31ids.map(lambda qs:any(prof.get(q,{}).get('physical_settlement_lineage') for q in qs))
 wide['admin_lineage']=wide.p31ids.map(lambda qs:any(prof.get(q,{}).get('admin_only_lineage_without_physical_settlement') for q in qs))
 wide['mixed_lineage']=wide.physical_lineage & wide.admin_lineage
 def valid_points(r):
  pts=[]
  for x in r.p625:
   if x.get('wgs84_valid') and x.get('latitude') is not None and x.get('longitude') is not None:
    try: pts.append((float(x['latitude']),float(x['longitude'])))
    except (TypeError,ValueError): pass
  return sorted(set(pts))
 wide['point_coords']=wide.apply(valid_points,axis=1)
 wide['exact_code']=wide.wikidata_truthy_exact_p764_match.fillna(False).astype(bool)
 wide['exact_name']=wide.wikidata_name_exact_label.fillna(False).astype(bool)
 wide['admin_context']=wide.p131.map(bool)
 wide['p17_russia']=wide.wikidata_truthy_p17_claims_json.map(lambda x:'Q159' in ids(js(x)))
 target_by=targets.set_index('source_record_id')
 def distance(row):
  pts=row.point_coords
  tgt=target_by.loc[row.source_record_id]
  if not pts or pd.isna(tgt.latitude) or pd.isna(tgt.longitude): return None
  import math
  def hav(pt):
   lat,lon=pt; lat1,lon1,lat2,lon2=map(math.radians,[float(tgt.latitude),float(tgt.longitude),lat,lon])
   a=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
   return 6371.0088*2*math.asin(math.sqrt(a))
  return min(map(hav,pts))
 wide['nearest_source_distance_km']=wide.apply(distance,axis=1)
 wide['inside_expected_adm1']=wide.apply(lambda r:len(r.point_coords)==1 and _point_inside_source_region(r.point_coords[0][0],r.point_coords[0][1],geom_by.get(r.source_record_id),geometries,region_iso)[0],axis=1)
 wide['source_row_region_name_type_exact']=wide.apply(lambda r:(str(r.source_name or '').casefold()==str(target_by.loc[r.source_record_id].settlement_name or '').casefold() and str(r.source_type or '').casefold()==str(target_by.loc[r.source_record_id].settlement_type or '').casefold() and str(r.source_region or '').casefold()==str(target_by.loc[r.source_record_id].region_raw or '').casefold()),axis=1)
 flags=wide.groupby('source_record_id',sort=False).agg(
  exact_code=('exact_code','max'), exact_name=('exact_name','max'),valid_point=('point_coords',lambda xs:any(bool(x) for x in xs)),physical=('physical_lineage','max'),admin=('admin_lineage','max'),mixed=('mixed_lineage','max'),admin_context=('admin_context','max'),p17_russia=('p17_russia','max'),inside_adm1=('inside_expected_adm1','max'),
  nearest_source_distance_km=('nearest_source_distance_km','min'),multi_qid=('wikidata_qid',lambda x:x.nunique()>1),qids=('wikidata_qid',lambda x:sorted(set(map(str,x)))),competing_qid=('entity_competition_across_tsv_or_truthy','max'),source_code_competition=('source_observation_competition_for_exact_oktmo','max'),multi_point=('point_coords',lambda xs:any(len(x)>1 for x in xs)),
 ).reset_index()
 targets=targets.merge(flags,on='source_record_id',how='left',validate='one_to_one')
 for c in ['exact_code','exact_name','valid_point','physical','admin','mixed','admin_context','p17_russia','inside_adm1','multi_qid','competing_qid','source_code_competition','multi_point']:
  targets[c]=targets[c].fillna(False).astype(bool)
 core=(targets.exact_code&targets.exact_name&targets.valid_point&targets.physical&~targets.multi_qid&~targets.competing_qid.fillna(False).astype(bool)&~targets.source_code_competition.fillna(False).astype(bool)&~targets.multi_point&targets.inside_adm1)
 targets['known_hold_reason']=targets.source_record_id.map(HOLDS)
 pre=targets.loc[core].copy()
 held=pre.loc[pre.known_hold_reason.notna()].copy()
 candidates=pre.loc[pre.known_hold_reason.isna()].copy()
 # Candidate-level raw evidence and risk/provenance fields, one selected QID per core target.
 wide_sha=sha(W/'wide_point_bindings.parquet')
 manifest_sha=sha(W/'manifest.json')
 out=[]
 for r in candidates.itertuples(index=False):
  sid=r.source_record_id; wg=wide.loc[wide.source_record_id.eq(sid)]
  if len(wg)!=1: raise ValueError(f'core target does not resolve to one WIDE QID: {sid}, rows={len(wg)}')
  q=wg.iloc[0]; pts=q.point_coords
  if len(pts)!=1: raise ValueError(f'core candidate does not have one distinct P625: {sid}')
  lat,lon=pts[0]
  p31path=[]
  for claim in q.p31:
   cq=claim.get('value_qid')
   if not cq: continue
   profile=prof.get(cq,{})
   ent=entities.get(cq,{})
   label=(ent.get('labels') or {}).get('ru',{}).get('value')
   p31path.append({'p31_qid':cq,'p31_label_ru':label,'physical_settlement_lineage':profile.get('physical_settlement_lineage',False),'physical_anchor_qids':profile.get('physical_settlement_anchors',[]),'admin_only_lineage_without_physical':profile.get('admin_only_lineage_without_physical_settlement',False),'admin_anchor_qids':profile.get('admin_only_anchors',[]),'lineage_unresolved':profile.get('lineage_unknown_or_unresolved',True)})
  pointloc=[{'source_file':x.get('source_file'),'line_number':x.get('line_number'),'locator':f"{x.get('source_file')}#line={x.get('line_number')}",'value_raw':x.get('value_raw'),'retrieved_at_utc':x.get('retrieved_at_utc')} for x in q.p625 if x.get('wgs84_valid') and x.get('latitude') is not None and x.get('longitude') is not None and (float(x['latitude']),float(x['longitude']))==(lat,lon)]
  p31loc=[{'source_file':x.get('source_file'),'line_number':x.get('line_number'),'locator':f"{x.get('source_file')}#line={x.get('line_number')}",'value_qid':x.get('value_qid')} for x in q.p31]
  p764loc=[{'source_file':x.get('source_file'),'line_number':x.get('line_number'),'locator':f"{x.get('source_file')}#line={x.get('line_number')}",'value_raw':x.get('value_raw')} for x in q.p764]
  d=q.nearest_source_distance_km
  risk={
   'selected_source_point_available':pd.notna(r.latitude) and pd.notna(r.longitude),
   'P625_selected_source_distance_over_1km':pd.notna(d) and float(d)>1,
   'P625_selected_source_distance_over_5km':pd.notna(d) and float(d)>5,
   'P625_selected_source_distance_over_10km':pd.notna(d) and float(d)>10,
   'mixed_physical_admin_P31_lineage':bool(q.mixed_lineage),
   'admin_context_P131_present':bool(q.admin_context),
   'source_row_region_name_type_equality_is_copied_context':bool(q.source_row_region_name_type_exact),
   'source_P31_class_path_is_Wikidata_family_only':True,
  }
  out.append({
   'source_record_id':sid,'current_population':int(r.population) if pd.notna(r.population) else None,'population_band':pband(r.population),'settlement_type':r.settlement_type,'type_band':tband(r.settlement_type),
   'current_name':r.settlement_name,'current_region':r.region_raw,'current_oktmo_raw':r.oktmo,'current_oktmo_exact_digits':q.source_oktmo_exact_digits,
   'wikidata_qid':q.wikidata_qid,'wikidata_p764_exact_claims_json':json.dumps(q.p764,ensure_ascii=False,sort_keys=True),'P625_latitude':lat,'P625_longitude':lon,'P625_raw_claim_locators_json':json.dumps(pointloc,ensure_ascii=False,sort_keys=True),'P31_claims_and_ancestry_anchors_json':json.dumps(p31path,ensure_ascii=False,sort_keys=True),'P31_raw_claim_locators_json':json.dumps(p31loc,ensure_ascii=False,sort_keys=True),'P131_admin_context_claims_json':json.dumps(q.p131,ensure_ascii=False,sort_keys=True),
   'expected_ADM1_geometry_iso':geom_by.get(sid),'source_selected_latitude':r.latitude,'source_selected_longitude':r.longitude,'nearest_P625_to_source_point_km':d,
   'risk_flags_json':json.dumps(risk,ensure_ascii=False,sort_keys=True),'identity_candidate_gates_json':json.dumps({'exact_P764':bool(q.exact_code),'exact_Russian_label':bool(q.exact_name),'unique_QID':not bool(r.multi_qid),'no_entity_competition':not bool(r.competing_qid),'no_source_code_competition':not bool(r.source_code_competition),'physical_P31_lineage':bool(q.physical_lineage),'single_distinct_valid_P625':len(pts)==1,'inside_expected_ADM1':bool(q.inside_expected_adm1)},ensure_ascii=False,sort_keys=True),
   'evidence_file':'wide_point_bindings.parquet','evidence_file_sha256':wide_sha,'wide_manifest_sha256':manifest_sha,'target_source_file':r.source_file,'target_source_sha256':r.source_sha256,'target_source_locator':r.source_locator or f'{r.source_file}#row={r.source_row}','candidate_status':'candidate_only_not_independently_reviewed_or_admitted'
  })
 cand=pd.DataFrame(out)
 cand.to_parquet(OUT/'wikidata_primary_core_candidates.parquet',index=False)
 # Current large-only fixed PPS sample. The PPS portion retains draw multiplicity.
 large=cand.loc[pd.to_numeric(cand.current_population,errors='coerce').ge(2000)].copy().reset_index(drop=True)
 if len(large)<=N_DRAWS:
  draw_ids=np.arange(len(large)); probs=None; draws=np.arange(len(large)); actual_draws=len(large)
 else:
  weights=pd.to_numeric(large.current_population,errors='coerce').to_numpy(float)
  probs=weights/weights.sum(); rng=np.random.default_rng(SEED); draws=rng.choice(len(large),size=N_DRAWS,replace=True,p=probs); actual_draws=N_DRAWS
 pps=large.iloc[draws].copy().reset_index(drop=True)
 pps.insert(0,'sample_kind','PPS_with_replacement')
 pps.insert(1,'pps_draw_index',np.arange(1,actual_draws+1))
 pps['pps_draw_probability']=probs[draws] if probs is not None else (1/len(large) if len(large) else None)
 pps['pps_draw_multiplicity_preserved']=True
 # Targeted diagnostic strata: each is purposefully selected, not part of the PPS estimator.
 targeted={}
 def topk(mask,sortcol,k=20,ascending=False):
  part=large.loc[mask].copy()
  if sortcol not in part or part.empty: return
  for _,row in part.sort_values([sortcol,'source_record_id'],ascending=[ascending,True],na_position='last').head(k).iterrows():
   targeted.setdefault(row.source_record_id,set()).add('top20_'+sortcol)
 topk(pd.Series(True,index=large.index),'current_population')
 topk(large.nearest_P625_to_source_point_km.gt(5),'nearest_P625_to_source_point_km')
 risk_json=large.risk_flags_json.map(json.loads)
 mixed=pd.Series([x.get('mixed_physical_admin_P31_lineage',False) for x in risk_json],index=large.index)
 missing=pd.Series([not x.get('selected_source_point_available',False) for x in risk_json],index=large.index)
 topk(mixed,'current_population');
 topk(missing,'current_population')
 # Join draw multiplicity and targeted flags into unique candidate-only union.
 mult=pd.Series(pps.source_record_id.value_counts())
 idx_by_id=defaultdict(list)
 for i,row in pps.iterrows(): idx_by_id[row.source_record_id].append(int(row.pps_draw_index))
 union_ids=set(pps.source_record_id)|set(targeted)
 union=large.loc[large.source_record_id.isin(union_ids)].copy()
 union['pps_draw_multiplicity']=union.source_record_id.map(lambda s:int(mult.get(s,0)))
 union['pps_draw_indices_json']=union.source_record_id.map(lambda s:json.dumps(idx_by_id.get(s,[])))
 union['targeted_strata_json']=union.source_record_id.map(lambda s:json.dumps(sorted(targeted.get(s,set()))))
 union.insert(0,'sample_status','candidate_only_sample_not_independently_reviewed')
 union.to_csv(OUT/'large_pilot_sample_union.csv',index=False)
 pps.to_csv(OUT/'large_pilot_pps_draws.csv',index=False)
 # Separate small/large and source-type summaries for universe, pre-hold core, and post-hold core.
 for frame in (targets,pre,candidates):
  frame['population_band']=frame.population.map(pband)
  frame['type_band']=frame.settlement_type.map(tband)
  frame['current_size_scope']=pd.to_numeric(frame.population,errors='coerce').ge(2000).map({True:'>=2,000',False:'<2,000'})
 summary={
  'status':'candidate_inventory_and_fixed_pilot_sample_only_no_independent_review_no_admissions',
  'scope':'2021 additive physical settlement observations with no frozen accepted point use; core follows profile_cached_wikidata.py; all four known current city holds excluded from exported core, including the two multiple-P625 cases already outside pre-hold core.',
  'known_holds':{'excluded_ids':HOLDS,'all_four_rows':4,'two_inside_prehold_core_rows':int(len(held)),'two_inside_prehold_core_population':int(pd.to_numeric(held.population).sum()),'posthold_core_rows':int(len(candidates)),'posthold_core_population':int(pd.to_numeric(candidates.population).sum())},
  'counts_population_by_population_band_and_type':{'unpointed_universe':stats(targets,['population_band','type_band']),'pre_hold_core':stats(pre,['population_band','type_band']),'post_hold_core':stats(candidates,['population_band','type_band'])},
  'counts_population_by_current_size_scope_and_type':{'unpointed_universe':stats(targets,['current_size_scope','type_band']),'pre_hold_core':stats(pre,['current_size_scope','type_band']),'post_hold_core':stats(candidates,['current_size_scope','type_band'])},
  'posthold_core_rows':int(len(candidates)),'posthold_core_population':int(pd.to_numeric(candidates.population).sum()),
  'large_current_candidate_pool':{'rows':int(len(large)),'population':int(pd.to_numeric(large.current_population).sum()),'PPS_draws':actual_draws,'seed':SEED,'with_replacement':len(large)>N_DRAWS,'PPS_weight':'current source population, equal probability per population unit; repeated row draws retained in large_pilot_pps_draws.csv','targeted_selection':'union of top 20 population, top 20 provider-distance >5 km, top 20 mixed physical/admin lineage by population, and top 20 lacking selected source point; these are purposive risk/high-mass diagnostics, not part of a precision estimator','unique_candidates_in_PPS_or_targeted_union':int(union.source_record_id.nunique()),'targeted_unique_candidates':int(len(targeted))},
  'sample_limits':['No independent review has been performed on this sample.','The sample is not a 99% precision certificate and produces no global precision estimate.','PPS with replacement draw multiplicities are retained. Targeted cases are marked separately.','Known holds remain excluded; this does not make the remaining candidates admitted.','The sample is restricted to current population >=2,000; smaller settlement exceptions remain protected and untouched.'],
  'provenance_sha256':{str(p):sha(p) for p in [F/'selected_observations.parquet',F/'accepted_point_uses.parquet',W/'wide_point_bindings.parquet',W/'provider_code_candidate_screen.parquet',W/'manifest.json',anc_path,Path('/workspace/settlements-work/coordinates/region_screen_v1/region_point_screen.parquet'),Path('/workspace/settlements-work/sources/region_geometry/RUS_ADM1_simplified.geojson')]},
  'outputs':{name:sha(OUT/name) for name in ['wikidata_primary_core_candidates.parquet','large_pilot_pps_draws.csv','large_pilot_sample_union.csv']}
 }
 (OUT/'wikidata_primary_pilot_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='provenance_sha256'},ensure_ascii=False,indent=2))
if __name__=='__main__': main()

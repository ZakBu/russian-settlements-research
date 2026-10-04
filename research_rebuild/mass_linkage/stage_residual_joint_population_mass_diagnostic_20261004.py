#!/usr/bin/env python3
"""Reclassify 2021 accepted-point/non-full-chain residual on canonical v3.

Candidate tables and legacy crosswalk metadata are diagnostic only. This stage
replays no source decisions and admits no identity, point, or population.
"""
from __future__ import annotations
import hashlib,json,re
from collections import Counter,defaultdict
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF,metrics
from research_rebuild.mass_linkage.stage_wide_qid_homonym_fetch_candidates_20261004 import norm,typ
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_PROJECTION_STATUSES,ACCEPTED_COORDINATE_STATUSES

W=Path('/workspace');C=W/'settlements-work/continuation_20261004';R4=C/'R4';F=W/'settlements-delivery/continuation-consolidated-20261003'
SEL=F/'selected_observations.parquet';EVID=F/'source_evidence.parquet';CORE=R4/'final_long_preparation/fifth_canonical_long_v2/source_preserving_core.parquet'
G=C/'accepted_mass_fifth_canonical_v3/accepted_identity_edges.parquet';P=C/'accepted_mass_fifth_canonical_v3/accepted_point_uses.parquet';COV=C/'accepted_mass_fifth_canonical_v3/coverage.json';CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'
WIDE=W/'settlements-work/wikidata/wide_v5/wide_point_bindings.parquet'
POINT_BINDINGS=W/'settlements-work/wikidata/point_bindings.parquet';CLAIMS=W/'settlements-work/wikidata/claims.parquet'
ROUTES={
 'legacy_spatial_homonym':R4/'legacy_spatial_homonym_reserve/legacy_spatial_homonym_candidate_register.csv',
 'district_context':R4/'source_district_context_physical_identity_recovery_20261004_v1/candidate_edges.csv',
 'district_annotation':R4/'source_district_annotation_recovery_20261004/candidate_edges.csv',
 'native_point_absent':R4/'native_point_absent_unique_sourcekey_recovery_20261004/candidate_endpoint_ledger.csv',
 'typed_native_vertex':R4/'typed_native_physical_corridor_v2_rerunfinal/residual_year_vertex_candidates.csv',
 'top200_prior_diagnostic':R4/'top_population_joint_recovery/top200_residual_by_year_scope.csv',
 'remaining_joint_funnel':R4/'remaining_joint_rule_funnel_20261004/top811_rows_with_exact_crossyear_funnel.csv',
}
OUT=R4/'residual_joint_population_mass_diagnostic_20261004'
YEARS=(2002,2010,2021)
PHYSICAL={'город','пгт','поселок','деревня','село','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко'}

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def dig(x):return re.sub(r'\D','',str(x or ''))
def j(v,default=None):
 if v is None:return default
 if isinstance(v,(dict,list,bool,int,float)):return v
 try:return json.loads(str(v))
 except Exception:return default
def b(v):return v is True or str(v).casefold() in {'true','1','t','yes'}

def load_direct_ids(path,kind):
 if not path.exists():return set()
 df=pd.read_csv(path,low_memory=False,dtype=str)
 cols=[]
 if kind=='legacy_spatial':cols=['direct_2021_source_record_id']
 elif kind in {'district','district_annotation'}:cols=['from_source_record_id','to_source_record_id','point_witness_2021_source_record_id']
 elif kind=='native_point_absent':cols=['source_record_id_current','target_source_record_id']
 elif kind=='typed_native_vertex':cols=['current_direct_source_record_id']
 else:cols=[]
 out=set()
 for col in cols:
  if col in df:
   out.update(x for x in df[col].dropna().astype(str) if x.startswith('2021:'))
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if any(OUT.iterdir()):raise SystemExit('diagnostic output directory is nonempty; refusing to overwrite')
 # Immutable fifth canonical snapshot, intentionally independent of the mutable
 # promoted joint config that may advance while this diagnostic is running.
 graph=G;points=P;cov=COV
 input_paths=[SEL,EVID,CORE,graph,points,cov,WIDE,POINT_BINDINGS,CLAIMS,*ROUTES.values()]
 pins={str(x):{'sha256':sha(x),'bytes':x.stat().st_size} for x in input_paths if x.exists()}
 if pins[str(graph)]['sha256']!='dd6ba7df48155941a3061490e2d208d1723bacda720b1ddd6e3fcb889cb70c29' or pins[str(points)]['sha256']!='d4cbdd0dff5360392f3ed0aa03158c7a47a6f75b7f239ccad3971fbe201b15ca':raise SystemExit('canonical fifth graph/point input pin mismatch')
 corecols=['observation_id','record_type','entity_category','source_record_id','observation_year','population_value','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population_scope','census_full_chain','census_2002_status','census_2010_status','census_2021_status','coordinate_admission_status','coordinate_source','source_path','source_sheet','source_row','source_native_id','source_sha256','source_locator','oktmo_native_raw','oktmo_current_observed_2021']
 core=pd.read_parquet(CORE,columns=corecols)
 accepted=core.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)
 residual=core[(core.record_type=='census')&(core.entity_category=='settlement')&(core.observation_year==2021)&(core.population_scope=='settlement')&accepted&(~core.census_full_chain.fillna(False))].copy()
 if len(residual)!=34692 or int(residual.population_value.sum())!=7464467:raise SystemExit('final-core residual definition changed from pinned 34,692 / 7,464,467')
 residual['outside_old_coverage']=residual.census_2002_status.eq('outside_russian_census_scope')|residual.census_2010_status.eq('outside_russian_census_scope')
 ordinary=residual[~residual.outside_old_coverage].copy()
 ordinary['cohort']=np.select([
   ordinary.census_2002_status.eq('observed')&ordinary.census_2010_status.eq('unknown_no_record'),
   ordinary.census_2002_status.eq('unknown_no_record')&ordinary.census_2010_status.eq('observed'),
   ordinary.census_2002_status.eq('unknown_no_record')&ordinary.census_2010_status.eq('unknown_no_record')],
   ['missing_2010__2002_2021_present','missing_2002__2010_2021_present','current_only__both_old_years_missing'],default='other_status_pattern')
 ordinary['current_name_key']=ordinary.settlement_name.map(norm);ordinary['current_type_key']=ordinary.settlement_type.map(typ);ordinary['current_region_key']=ordinary.region_raw.map(region_key)
 ordinary['key']=list(zip(ordinary.current_name_key,ordinary.current_type_key,ordinary.current_region_key))
 selected=pd.read_parquet(SEL,columns=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','okato','oktmo','fias_id','source_sha256','source_locator','source_raw_line','population_value_quality'])
 selected.source_record_id=selected.source_record_id.astype(str);selected.census_year=selected.census_year.astype(int)
 selected['name_key']=selected.settlement_name.map(norm);selected['type_key']=selected.settlement_type.map(typ);selected['region_key']=selected.region_raw.map(region_key);selected['key']=list(zip(selected.name_key,selected.type_key,selected.region_key));selected['code_okato_digits']=selected.okato.map(dig);selected['code_oktmo_digits']=selected.oktmo.map(dig)
 all_selected=selected.copy()
 selected=selected[selected.is_additive_settlement_record.fillna(False)&selected.type_key.isin(PHYSICAL)&selected.name_key.ne('')&selected.region_key.ne('')].copy()
 current=all_selected[all_selected.census_year.eq(2021)].copy()
 if current.source_record_id.duplicated().any():raise SystemExit('duplicate selected 2021 source ID')
 current_by_id=current.set_index('source_record_id',drop=False)
 key_current=selected[selected.census_year.eq(2021)].groupby('key').source_record_id.nunique().to_dict()
 oldbyyear={y:{k:g.to_dict('records') for k,g in x.groupby('key',sort=False)} for y,x in ((y,selected[selected.census_year.eq(y)]) for y in (2002,2010))}
 key_counts={y:{k:len(v) for k,v in m.items()} for y,m in oldbyyear.items()}
 # Build exact old-source-row candidates for each residual endpoint without
 # using the old numeric/ordinal source IDs as linkage evidence.
 match_rows=[];candidate_ids=set(ordinary.source_record_id.astype(str));needed_old_ids=set()
 for r in ordinary.itertuples(index=False):
  row=current_by_id.loc[str(r.source_record_id)]
  missing=[2010] if r.cohort=='missing_2010__2002_2021_present' else ([2002] if r.cohort=='missing_2002__2010_2021_present' else ([2002,2010] if r.cohort=='current_only__both_old_years_missing' else []))
  for y in missing:
   matches=oldbyyear[y].get(row.key,[]);needed_old_ids.update(str(x['source_record_id']) for x in matches)
   for m in matches:
    match_rows.append({'current_source_record_id':str(r.source_record_id),'cohort':r.cohort,'current_population':int(r.population_value),'current_source_key_count_2021':int(key_current.get(row.key,0)),'candidate_historical_source_record_id':str(m['source_record_id']),'candidate_historical_year':y,'candidate_historical_source_name_raw':m['source_name_raw'],'candidate_historical_name':m['settlement_name'],'candidate_historical_type':m['settlement_type'],'candidate_historical_region_raw':m['region_raw'],'candidate_historical_district_raw':m['district_raw'],'candidate_historical_municipality_raw':m['municipality_raw'],'candidate_historical_population':m['population'],'candidate_historical_population_scope':m['population_scope'],'candidate_historical_source_file':m['source_file'],'candidate_historical_source_sheet':m['source_sheet'],'candidate_historical_source_row':m['source_row'],'candidate_historical_source_native_id_opaque':m['source_native_id'],'candidate_historical_source_sha256':m['source_sha256'],'candidate_historical_source_locator':m['source_locator'],'candidate_historical_source_okato_raw':m['okato'],'candidate_historical_source_oktmo_raw':m['oktmo'],'candidate_historical_source_fias_id':m['fias_id'],'candidate_historical_type_key_count':int(key_counts[y].get(row.key,0)),'same_current_okato_digits':bool(dig(m['okato']) and dig(m['okato'])==dig(row.okato)),'same_current_oktmo_digits':bool(dig(m['oktmo']) and dig(m['oktmo'])==dig(row.oktmo)),'same_current_fias_literal':bool(m['fias_id'] and row.fias_id and str(m['fias_id'])==str(row.fias_id))})
 matchdf=pd.DataFrame(match_rows)
 # Only the source-evidence JSON for the scoped current + old candidates is
 # read here; candidate_only/legacy statuses are retained as descriptive fields.
 evidence_ids=sorted(candidate_ids|needed_old_ids);idframe=pd.DataFrame({'source_record_id':evidence_ids})
 db=duckdb.connect();db.register('scoped_ids',idframe)
 evid=db.execute(f"""SELECT e.source_record_id,
  json_extract_string(e.source_evidence_json,'$.legacy_matched_to_source_record_id') AS legacy_matched_to_source_record_id,
  json_extract_string(e.source_evidence_json,'$.legacy_identity_status') AS legacy_identity_status,
  json_extract_string(e.source_evidence_json,'$.legacy_identity_reasons') AS legacy_identity_reasons,
  json_extract_string(e.source_evidence_json,'$.legacy_identity_conflict') AS legacy_identity_conflict,
  json_extract_string(e.source_evidence_json,'$.legacy_identity_certified') AS legacy_identity_certified,
  json_extract_string(e.source_evidence_json,'$.legacy_ordinal_route_present') AS legacy_ordinal_route_present,
  json_extract_string(e.source_evidence_json,'$.legacy_same_year_collision') AS legacy_same_year_collision,
  json_extract_string(e.source_evidence_json,'$.legacy_match_method') AS legacy_match_method,
  json_extract_string(e.source_evidence_json,'$.legacy_route_is_acceptance_signal') AS legacy_route_is_acceptance_signal,
  json_extract_string(e.source_evidence_json,'$.legacy_source_file') AS legacy_source_file,
  json_extract_string(e.source_evidence_json,'$.legacy_source_row') AS legacy_source_row,
  json_extract_string(e.source_evidence_json,'$.legacy_source_sheet') AS legacy_source_sheet,
  json_extract_string(e.source_evidence_json,'$.legacy_population_scope') AS legacy_population_scope,
  json_extract_string(e.source_evidence_json,'$.legacy_population') AS legacy_population,
  json_extract_string(e.source_evidence_json,'$.legacy_quality_flag') AS legacy_quality_flag,
  json_extract_string(e.source_evidence_json,'$.legacy_quality_join_status') AS legacy_quality_join_status,
  json_extract_string(e.source_evidence_json,'$.legacy_is_federal_aggregate') AS legacy_is_federal_aggregate,
  json_extract_string(e.source_evidence_json,'$.legacy_event_or_boundary_conflict') AS legacy_event_or_boundary_conflict
 FROM read_parquet('{EVID}') e JOIN scoped_ids s USING(source_record_id)""").df()
 evidence={str(r.source_record_id):r._asdict() for r in evid.itertuples(index=False)}
 # Reconstruct current accepted UF and verify coverage before candidate outcomes.
 # The accepted graph and official metrics cover every selected record, including
 # aggregates and nonphysical grains. Keep this full universe for UF replay;
 # the exact-name/type candidate indexes below remain scoped to additive physical
 # settlement observations.
 allsel=all_selected[['source_record_id','census_year','population']].copy();uf=YearUF(allsel.source_record_id.astype(str).tolist(),allsel.census_year.astype(int).tolist());yearmap=dict(zip(allsel.source_record_id.astype(str),allsel.census_year.astype(int)))
 graph_df=pd.read_parquet(graph,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(graph_df.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(graph_df.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES):raise SystemExit('current canonical graph status guard failed')
 for edge in graph_df.itertuples(index=False):
  a,bid=str(edge.from_source_record_id),str(edge.to_source_record_id)
  if edge.relation!='same_place' or yearmap[a]!=int(edge.from_year) or yearmap[bid]!=int(edge.to_year) or uf.union_ids(a,bid)=='year_constrained_collision':raise SystemExit('accepted edge relation/year/collision guard failed')
 accepted_points=pd.read_parquet(points,columns=['target_source_record_id','target_year','coordinate_admission_status']);accepted_points=accepted_points[accepted_points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 if accepted_points.target_source_record_id.astype(str).duplicated().any():raise SystemExit('duplicate accepted coordinate target')
 point_ids=set(accepted_points.target_source_record_id.astype(str));baseline=metrics(allsel.assign(source_record_id=allsel.source_record_id.astype(str)),uf,point_ids);covobj=json.loads(cov.read_text());axes={str(x['year']):x['axes'] for x in covobj['census_metrics']}
 for y in ('2002','2010','2021'):
  if baseline[y]['full_chain']!={'rows':int(axes[y]['full_census_chain']['rows']),'population':int(axes[y]['full_census_chain']['known_population'])} or baseline[y]['joint_point_full_chain']!={'rows':int(axes[y]['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(axes[y]['joint_admitted_coordinate_and_full_chain']['known_population'])}:raise SystemExit('canonical v3 metric reproduction failed')
 # Complete legacy evidence annotations for exact candidate endpoints.
 if len(matchdf):
  for prefix,col in [('legacy_current','current_source_record_id'),('legacy_candidate','candidate_historical_source_record_id')]:
   keys=['legacy_matched_to_source_record_id','legacy_identity_status','legacy_identity_reasons','legacy_identity_conflict','legacy_identity_certified','legacy_ordinal_route_present','legacy_same_year_collision','legacy_match_method','legacy_route_is_acceptance_signal','legacy_quality_flag','legacy_quality_join_status']
   vals={k:[] for k in keys}
   for x in matchdf[col].astype(str):
    ev=evidence.get(x,{})
    for k in keys:vals[k].append(ev.get(k))
   for k,v in vals.items():matchdf[f'{prefix}_{k}']=v
  matchdf['legacy_pointer_exact_candidate']=matchdf.apply(lambda r:str(r.legacy_candidate_legacy_matched_to_source_record_id or '')==str(r.current_source_record_id),axis=1)
  matchdf['legacy_pointer_to_other_source']=matchdf.apply(lambda r:bool(r.legacy_candidate_legacy_matched_to_source_record_id) and not r.legacy_pointer_exact_candidate,axis=1)
  # Independent per-edge year-constrained outcome against the frozen baseline;
  # do not mutate UF or assume candidate batches are mutually safe.
  outcomes=[]
  for r in matchdf.itertuples(index=False):
   a=uf.find(uf.idx[str(r.current_source_record_id)]);bb=uf.find(uf.idx[str(r.candidate_historical_source_record_id)])
   outcomes.append('already_connected' if a==bb else ('year_constrained_collision' if uf.mask[a]&uf.mask[bb] else 'year_constrained_merge_possible'))
  matchdf['conditional_baseline_uf_outcome']=outcomes
  matchdf['current_source_raw_key_unique']=matchdf.current_source_key_count_2021.eq(1)
  matchdf['candidate_source_raw_key_unique']=matchdf.candidate_historical_type_key_count.eq(1)
  matchdf['exact_typed_region_key_candidate_only']=matchdf.current_source_raw_key_unique&matchdf.candidate_source_raw_key_unique
  matchdf['candidate_identity_admitted']=False
 # Current selected native/provider codes and accepted points from the canonical point-use ledger.
 ids=pd.DataFrame({'source_record_id':ordinary.source_record_id.astype(str).unique()});db.register('residual_ids',ids)
 pcols=['target_source_record_id','coordinate_provider','coordinate_provider_id','coordinate_source','coordinate_source_record_id','source_okato_raw','source_oktmo_raw','provider_binding_status','provider_fias_binding_status','coordinate_source_sha256','coordinate_source_locator','point_origin_kind']
 pframe=pd.read_parquet(points,columns=pcols);pframe=pframe[pframe.target_source_record_id.astype(str).isin(set(ids.source_record_id))]
 psummary={}
 for sid,g in pframe.groupby(pframe.target_source_record_id.astype(str)):
  psummary[sid]={'accepted_point_provider_families_json':json.dumps(sorted(set(g.coordinate_provider.astype(str))),ensure_ascii=False),'point_source_okato_values_json':json.dumps(sorted(set(x for x in g.source_okato_raw.dropna().astype(str) if x)),ensure_ascii=False),'point_source_oktmo_values_json':json.dumps(sorted(set(x for x in g.source_oktmo_raw.dropna().astype(str) if x)),ensure_ascii=False),'point_provider_binding_statuses_json':json.dumps(sorted(set(g.provider_binding_status.dropna().astype(str))),ensure_ascii=False),'point_provider_fias_statuses_json':json.dumps(sorted(set(g.provider_fias_binding_status.dropna().astype(str))),ensure_ascii=False),'point_origin_locators_json':json.dumps([{'file':r.coordinate_source,'sha256':r.coordinate_source_sha256,'locator':r.coordinate_source_locator,'kind':r.point_origin_kind} for r in g.itertuples(index=False)],ensure_ascii=False)}
 wcols=['source_record_id','wikidata_qid','source_oktmo_exact_digits','source_okato_projection_exact_digits','wikidata_truthy_exact_p764_match','wikidata_truthy_exact_p721_projection_match_same_qid','wikidata_name_exact_label','entity_competition_across_tsv_or_truthy','source_observation_competition_for_exact_oktmo','wikidata_truthy_p31_claims_json','candidate_status']
 wframe=pd.read_parquet(WIDE,columns=wcols);wframe=wframe[wframe.source_record_id.astype(str).isin(set(ids.source_record_id))]
 wsummary={}
 for sid,g in wframe.groupby(wframe.source_record_id.astype(str)):
  wsummary[sid]={'wide_qids_json':json.dumps(sorted(set(g.wikidata_qid.dropna().astype(str))),ensure_ascii=False),'wide_p764_codes_json':json.dumps(sorted(set(x for x in g.source_oktmo_exact_digits.dropna().astype(str) if x)),ensure_ascii=False),'wide_p721_projection_codes_json':json.dumps(sorted(set(x for x in g.source_okato_projection_exact_digits.dropna().astype(str) if x)),ensure_ascii=False),'wide_exact_p764_match_any':bool(g.wikidata_truthy_exact_p764_match.fillna(False).any()),'wide_same_qid_p721_projection_match_any':bool(g.wikidata_truthy_exact_p721_projection_match_same_qid.fillna(False).any()),'wide_label_exact_any':bool(g.wikidata_name_exact_label.fillna(False).any()),'wide_entity_competition_any':bool(g.entity_competition_across_tsv_or_truthy.fillna(False).any()),'wide_source_competition_any':bool(g.source_observation_competition_for_exact_oktmo.fillna(False).any()),'wide_p31_claims_json':json.dumps(sorted(set(g.wikidata_truthy_p31_claims_json.dropna().astype(str))),ensure_ascii=False)}
 # Project exact cross-year and native-source evidence on every in-scope residual.
 keycountall={}
 for y in YEARS:
  keycountall[y]=selected[selected.census_year.eq(y)].groupby('key').source_record_id.nunique().to_dict()
 residual_rows=[]
 for r in ordinary.to_dict('records'):
  sid=str(r['source_record_id']);srow=current_by_id.loc[sid];expected_missing=[2010] if r['cohort']=='missing_2010__2002_2021_present' else ([2002] if r['cohort']=='missing_2002__2010_2021_present' else [2002,2010])
  counts={y:int(keycountall[y].get(srow.key,0)) for y in (2002,2010,2021)}
  matchlist=matchdf[matchdf.current_source_record_id.eq(sid)] if len(matchdf) else pd.DataFrame()
  missing_counts={y:counts[y] for y in expected_missing}
  status=('unique_counterpart_for_all_missing_years' if all(v==1 for v in missing_counts.values()) else ('homonymous_counterpart_for_any_missing_year' if any(v>1 for v in missing_counts.values()) else ('no_exact_typed_region_counterpart_for_any_missing_year' if any(v==0 for v in missing_counts.values()) else 'other')))
  pointer_exact=bool(len(matchlist) and matchlist.legacy_pointer_exact_candidate.any())
  old_unique_keys=bool(all(missing_counts[y]==1 for y in expected_missing))
  edgeout=sorted(set(matchlist.conditional_baseline_uf_outcome.astype(str))) if len(matchlist) else []
  old_curr_code_match=bool(len(matchlist) and (matchlist.same_current_okato_digits|matchlist.same_current_oktmo_digits|matchlist.same_current_fias_literal).any())
  pinfo=psummary.get(sid,{});winfo=wsummary.get(sid,{})
  current_o=dig(srow.oktmo);current_a=dig(srow.okato)
  residual_rows.append({'source_record_id':sid,'cohort':r['cohort'],'current_population':int(r['population_value']),'current_name_raw':r['settlement_name'],'current_type_raw':r['settlement_type'],'current_region_raw':r['region_raw'],'current_district_raw':r['district_raw'],'current_municipality_raw':r['municipality_raw'],'source_path':r['source_path'],'source_sheet':r['source_sheet'],'source_row':r['source_row'],'source_native_id_opaque':r['source_native_id'],'source_sha256':r['source_sha256'],'source_locator':r['source_locator'],'census_2002_status':r['census_2002_status'],'census_2010_status':r['census_2010_status'],'selected_current_oktmo_raw':srow.oktmo,'selected_current_oktmo_digits':current_o,'selected_current_oktmo_width':len(current_o),'selected_current_okato_raw':srow.okato,'selected_current_okato_digits':current_a,'selected_current_okato_width':len(current_a),'current_fias_id':srow.fias_id,'current_exact_typed_region_key_count_2021':counts[2021],'exact_typed_region_key_candidate_counts_json':json.dumps({str(y):counts[y] for y in (2002,2010,2021)}),'expected_missing_years_json':json.dumps(expected_missing),'exact_key_candidate_status':status,'all_missing_year_source_keys_unique':old_unique_keys,'exact_key_candidate_source_ids_json':json.dumps(matchlist[['candidate_historical_year','candidate_historical_source_record_id']].to_dict('records'),ensure_ascii=False) if len(matchlist) else '[]','exact_key_legacy_pointer_exact_target_exists':pointer_exact,'exact_key_old_current_identifier_match_any':old_curr_code_match,'exact_key_conditional_baseline_uf_outcomes_json':json.dumps(edgeout),'accepted_point_provider_families_json':pinfo.get('accepted_point_provider_families_json'),'point_source_okato_values_json':pinfo.get('point_source_okato_values_json'),'point_source_oktmo_values_json':pinfo.get('point_source_oktmo_values_json'),'point_provider_binding_statuses_json':pinfo.get('point_provider_binding_statuses_json'),'point_provider_fias_statuses_json':pinfo.get('point_provider_fias_statuses_json'),'point_origin_locators_json':pinfo.get('point_origin_locators_json'),'wide_qids_json':winfo.get('wide_qids_json'),'wide_p764_codes_json':winfo.get('wide_p764_codes_json'),'wide_p721_projection_codes_json':winfo.get('wide_p721_projection_codes_json'),'wide_exact_p764_match_any':winfo.get('wide_exact_p764_match_any',False),'wide_same_qid_p721_projection_match_any':winfo.get('wide_same_qid_p721_projection_match_any',False),'wide_label_exact_any':winfo.get('wide_label_exact_any',False),'wide_entity_competition_any':winfo.get('wide_entity_competition_any',False),'wide_source_competition_any':winfo.get('wide_source_competition_any',False),'current_place_qid_p31_claims_json':winfo.get('wide_p31_claims_json'),'legacy_optional_current_identity_status':evidence.get(sid,{}).get('legacy_identity_status'),'legacy_optional_current_identity_reasons':evidence.get(sid,{}).get('legacy_identity_reasons'),'legacy_optional_current_match_method':evidence.get(sid,{}).get('legacy_match_method'),'legacy_optional_current_crosswalk_pointer':evidence.get(sid,{}).get('legacy_matched_to_source_record_id'),'current_source_evidence_status_preserved_only':evidence.get(sid,{}).get('legacy_quality_flag'),'candidate_identity_admitted':False})
 full=pd.DataFrame(residual_rows)
 # Existing candidate-table presence is a diagnostic route flag, not a gate.
 route_sets={k:load_direct_ids(v,k) for k,v in [('legacy_spatial',ROUTES['legacy_spatial_homonym']),('district',ROUTES['district_context']),('district_annotation',ROUTES['district_annotation']),('native_point_absent',ROUTES['native_point_absent']),('typed_native_vertex',ROUTES['typed_native_vertex'])]}
 mapcols={'legacy_spatial':'legacy_spatial_homonym_candidate_table_row_exists','district':'district_context_candidate_table_row_exists','district_annotation':'district_annotation_candidate_table_row_exists','native_point_absent':'native_point_absent_candidate_table_row_exists','typed_native_vertex':'typed_native_vertex_candidate_table_row_exists'}
 for k,cname in mapcols.items():full[cname]=full.source_record_id.astype(str).isin(route_sets[k])
 full['any_prior_candidate_table_reference']=full[list(mapcols.values())].any(axis=1)
 full['rejection_or_route_family']=full.exact_key_candidate_status
 # Existing source evidence candidateOnly/ordinal flags do not control these counts;
 # they are surfaced only in the matched-row/top200 details below.
 full.to_csv(OUT/'all_in_scope_residual_route_classification.csv',index=False)
 # Shortlisted top 200 overall and per each of the three partial-year patterns.
 top_all=full.sort_values(['current_population','source_record_id'],ascending=[False,True]).head(200).copy();top_all['sample_stratum']='top200_all_ordinary_residual'
 top_strata=[]
 for cohort,g in full.groupby('cohort',sort=True):
  x=g.sort_values(['current_population','source_record_id'],ascending=[False,True]).head(200).copy();x['sample_stratum']=f'top200_{cohort}';top_strata.append(x)
 tops=pd.concat([top_all,*top_strata],ignore_index=True).drop_duplicates(['source_record_id','sample_stratum'])
 tops.to_csv(OUT/'top200_residual_overall_and_by_period_pattern.csv',index=False)
 # Full raw candidate source rows for all top200 overall plus 200 per status cohort.
 chosen=set(tops.source_record_id.astype(str));topmatches=matchdf[matchdf.current_source_record_id.astype(str).isin(chosen)].copy() if len(matchdf) else pd.DataFrame()
 if len(topmatches):topmatches.to_csv(OUT/'top200_candidate_historical_source_rows.csv',index=False)
 # Candidate table rows for these top cases retain preexisting disposition text and optional flags as metadata.
 existing=[]
 for kind,path in ROUTES.items():
  if not path.exists() or path.suffix.lower()!='.csv':continue
  d=pd.read_csv(path,low_memory=False,dtype=str)
  relevant=set()
  for col in ['direct_2021_source_record_id','point_witness_2021_source_record_id','from_source_record_id','to_source_record_id','source_record_id_current','target_source_record_id','current_direct_source_record_id']:
   if col in d:relevant.update(x for x in d[col].dropna().astype(str) if x in chosen)
  if not relevant:continue
  # Keep matching whole rows but only for the fixed top stratum IDs.
  mask=False
  for col in ['direct_2021_source_record_id','point_witness_2021_source_record_id','from_source_record_id','to_source_record_id','source_record_id_current','target_source_record_id','current_direct_source_record_id']:
   if col in d:mask=mask|d[col].astype(str).isin(chosen)
  d=d[mask].copy();d.insert(0,'prior_candidate_table_family',kind);existing.extend(d.to_dict('records'))
 if existing:pd.DataFrame(existing).to_csv(OUT/'top200_existing_candidate_table_rows_unfiltered.csv',index=False)
 # Coverage and candidate route population summaries, with current source-row
 # population only. Old candidate populations remain separate.
 cohort=full.groupby('cohort',dropna=False).agg(rows=('source_record_id','size'),current_population=('current_population','sum')).reset_index()
 cohort.to_csv(OUT/'cohort_counts_population.csv',index=False)
 funnel=[]
 for name,mask in [
  ('all_ordinary_residual',pd.Series(True,index=full.index)),
  ('unique_old_key_for_all_missing_years',full.all_missing_year_source_keys_unique),
  ('unique_key_and_any_exact_legacy_pointer',full.all_missing_year_source_keys_unique&full.exact_key_legacy_pointer_exact_target_exists),
  ('unique_key_and_old_current_identifier_match',full.all_missing_year_source_keys_unique&full.exact_key_old_current_identifier_match_any),
  ('unique_key_and_exact_current_WIDE_P764_binding',full.all_missing_year_source_keys_unique&full.wide_exact_p764_match_any),
  ('unique_key_and_any_prior_candidate_table_reference',full.all_missing_year_source_keys_unique&full.any_prior_candidate_table_reference),
  ('not_current_key_unique',~full.current_exact_typed_region_key_count_2021.eq(1)),
  ('ambiguous_old_counterpart',full.exact_key_candidate_status.eq('homonymous_counterpart_for_any_missing_year')),
  ('no_exact_old_counterpart',full.exact_key_candidate_status.eq('no_exact_typed_region_counterpart_for_any_missing_year'))]:
  z=full[mask];funnel.append({'route_or_rejection_family':name,'rows':len(z),'current_population_sum':int(z.current_population.sum()),'missing_2010_rows':int(z.cohort.eq('missing_2010__2002_2021_present').sum()),'missing_2002_rows':int(z.cohort.eq('missing_2002__2010_2021_present').sum()),'current_only_rows':int(z.cohort.eq('current_only__both_old_years_missing').sum())})
 pd.DataFrame(funnel).to_csv(OUT/'source_route_rejection_weighted_funnel.csv',index=False)
 # Exact source-code coverage/mismatch classes by cohort.
 idf=[]
 for cohort_name,g in full.groupby('cohort'):
  for field,role in [('selected_current_oktmo_digits','selected source OKTMO field'),('selected_current_okato_digits','selected OKATO helper field')]:
   s=g[field].fillna('').astype(str);idf.append({'cohort':cohort_name,'identifier_role':role,'rows':len(g),'present_rows':int(s.ne('').sum()),'missing_rows':int(s.eq('').sum()),'width_8':int(s.str.len().eq(8).sum()),'width_10':int(s.str.len().eq(10).sum()),'width_11':int(s.str.len().eq(11).sum()),'population_with_identifier':int(g.loc[s.ne(''),'current_population'].sum())})
  for field in ['wide_exact_p764_match_any','wide_same_qid_p721_projection_match_any','wide_label_exact_any','wide_entity_competition_any','wide_source_competition_any','exact_key_legacy_pointer_exact_target_exists','exact_key_old_current_identifier_match_any','any_prior_candidate_table_reference']:
   z=g[g[field].fillna(False)];idf.append({'cohort':cohort_name,'identifier_role':field,'rows':len(z),'present_rows':len(z),'missing_rows':len(g)-len(z),'population_with_identifier':int(z.current_population.sum())})
 pd.DataFrame(idf).to_csv(OUT/'current_identifier_route_inventory_by_cohort.csv',index=False)
 # Source evidence only for top cases: retain raw old source rows and crosswalk identifiers.
 topmatches.to_csv(OUT/'top200_candidate_historical_source_rows.csv',index=False)
 summary={'status':'read_only_current_joint_residual_route_diagnostic_no_admissions','residual_definition':'2021 selected settlement-scope census row with canonical accepted point and no full 2002-2010-2021 UF chain; exact final canonical long-v2 statuses; ordinary excludes 2002/2010 outside_russian_census_scope','residual_all_count':len(residual),'residual_all_population':int(residual.population_value.sum()),'outside_old_coverage_count':int(residual.outside_old_coverage.sum()),'outside_old_coverage_population':int(residual.loc[residual.outside_old_coverage,'population_value'].sum()),'ordinary_count':len(full),'ordinary_current_population':int(full.current_population.sum()),'period_pattern_counts':cohort.to_dict('records'),'top_review_set_definition':'highest current population: overall top200 plus top200 within each of three missing-period patterns; rows may repeat across sample strata','top_review_rows':len(tops),'all_source_route_funnel':funnel,'baseline_graph_sha256':pins[str(graph)]['sha256'],'baseline_point_sha256':pins[str(points)]['sha256'],'baseline_coverage_reproduced':True,'inputs':pins,'outputs':{f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(OUT.iterdir()) if f.is_file()}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'receipt.json').write_text(json.dumps({'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{f.name:sha(f) for f in sorted(OUT.iterdir()) if f.is_file() and f.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

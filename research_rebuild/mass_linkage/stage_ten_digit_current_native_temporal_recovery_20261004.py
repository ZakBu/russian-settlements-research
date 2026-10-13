#!/usr/bin/env python3
"""Fetch 17 non-overlapping ten-digit-code QIDs and stage exact-key histories.

The source's ten-digit literal is never rewritten. A literal external 11-digit
P764, proper physical P31, exact typed name/province uniqueness, and an
accepted current source point form candidate evidence only. Historical P1082
is corroboration, not a prerequisite and never replaces census counts.
"""
from __future__ import annotations
import csv,hashlib,json,re,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF,metrics
from research_rebuild.mass_linkage.stage_wide_qid_homonym_fetch_candidates_20261004 import norm,typ
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_PROJECTION_STATUSES,ACCEPTED_COORDINATE_STATUSES

W=Path('/workspace');BASE=W/'settlements-work/continuation_20261004';R4=BASE/'R4'
F=W/'settlements-delivery/continuation-consolidated-20261003';SEL=F/'selected_observations.parquet';EVID=F/'source_evidence.parquet'
POINT_SCREEN=R4/'ten_digit_oktmo_format_relation_20261004/ten_digit_format_relation_candidates.csv'
G=W/'settlements-work/continuation_20261004/accepted_mass_fifth_canonical_v3/accepted_identity_edges.parquet'
P=W/'settlements-work/continuation_20261004/accepted_mass_fifth_canonical_v3/accepted_point_uses.parquet'
COV=W/'settlements-work/continuation_20261004/accepted_mass_fifth_canonical_v3/coverage.json'
CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'
HIST=W/'settlements-work/continuation_20261004/federal_and_history/wikidata_secondary_working_series.parquet'
OUT=R4/'ten_digit_oktmo_temporal_recovery_20261004'
PHYS={'город','пгт','поселок','деревня','село','хутор','станица','аул','слобода','кишлак','местечко','починок','выселок'}
P31={ 'город':'Q7930989','пгт':'Q15078955','поселок':'Q2514025','деревня':'Q532','село':'Q532','хутор':'Q2023000','станица':'Q748331','аул':'Q532','слобода':'Q532','кишлак':'Q532','местечко':'Q532','починок':'Q532','выселок':'Q532' }

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def digits(v):return re.sub(r'\D','',str(v or ''))
def json_value(v,default=None):
 if v is None:return default
 if isinstance(v,(dict,list,bool,int,float)):return v
 try:return json.loads(str(v))
 except Exception:return default
def year_p1082(st):
 sn=st.get('mainsnak',{});val=sn.get('datavalue',{}).get('value',{}) if sn.get('snaktype')=='value' else {}
 amount=val.get('amount');unit=val.get('unit');qs=st.get('qualifiers',{}).get('P585',[]);year=None;rawtime=None;precision=None
 if len(qs)==1 and qs[0].get('snaktype')=='value':
  qv=qs[0].get('datavalue',{}).get('value',{});rawtime=qv.get('time');precision=qv.get('precision')
  m=re.fullmatch(r'\+(\d{4})-00-00T00:00:00Z',str(rawtime))
  if m and precision==9:year=int(m.group(1))
 try: pop=int(str(amount).lstrip('+'))
 except Exception:pop=None
 if unit not in ('1','http://www.wikidata.org/entity/Q199'):pop=None
 return {'year':year,'time_raw':rawtime,'precision':precision,'population_raw':amount,'population':pop,'unit_raw':unit,'rank':st.get('rank'),'statement_id':st.get('id'),'raw_json':json.dumps(st,ensure_ascii=False,separators=(',',':'))}

def fetch(qids):
 params={'action':'wbgetentities','ids':'|'.join(qids),'props':'claims|labels|descriptions','languages':'ru|en','format':'json','formatversion':'2'}
 url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':'RussianSettlementsResearch/1.0 (open research data reconciliation)'})
 with urllib.request.urlopen(req,timeout=45) as res:
  body=res.read();final=res.geturl();status=res.status
 if status!=200 or not final.startswith('https://www.wikidata.org/'):raise RuntimeError(f'Wikidata API response invalid: {status} {final}')
 return url,final,status,body

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 cfg=json.loads(CONFIG.read_text());graph=Path(cfg['working_identity_graph']);points=Path(cfg['working_point_uses']);cov=Path(cfg['working_coverage'])
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SEL,EVID,POINT_SCREEN,graph,points,cov,CONFIG,HIST]}
 req=pd.read_csv(POINT_SCREEN,dtype={'wikidata_qid':str,'source_record_id':str,'source_oktmo_raw':str,'source_oktmo_digits':str,'external_p764_raw':str,'external_p764_digits':str})
 qids=sorted(req.wikidata_qid.astype(str).unique())
 prior=pd.read_csv(R4/'wide_qid_homonym_full_entity_retrieval_20261004_v2/entity_fetch_request_top500.csv',dtype={'wikidata_qid':str})
 if set(qids)&set(prior.wikidata_qid.astype(str)):raise SystemExit('ten-digit request overlaps previous 431; do not re-fetch those QIDs')
 t0=datetime.now(timezone.utc).isoformat();rawpath=OUT/'raw_entity_batch_01.json';rawreceipt=OUT/'raw_entity_fetch_receipt.json'
 if rawpath.exists() and rawreceipt.exists():
  oldreceipt=json.loads(rawreceipt.read_text())
  if oldreceipt.get('request_qids')!=qids:raise SystemExit('existing raw batch QID roster mismatch; preserving bytes')
  body=rawpath.read_bytes();url=oldreceipt['request_url'];final=oldreceipt['final_url'];status=oldreceipt['http_status'];t0=oldreceipt['requested_at_utc'];retrieved=oldreceipt['retrieved_at_utc']
 else:
  url,final,status,body=fetch(qids);retrieved=datetime.now(timezone.utc).isoformat();rawpath.write_bytes(body)
 rawsha=sha(rawpath);payload=json.loads(body.decode('utf-8'));entities=payload.get('entities',{})
 if set(entities)!=set(qids):raise SystemExit(f'full entity response QID mismatch missing={set(qids)-set(entities)} extra={set(entities)-set(qids)}')
 if not rawreceipt.exists():rawreceipt.write_text(json.dumps({'request_url':url,'final_url':final,'http_status':status,'request_qids':qids,'retrieved_at_utc':retrieved,'requested_at_utc':t0,'response_bytes':len(body),'response_sha256':rawsha,'raw_file':rawpath.name,'reused_prior_entity_count':0,'prior_431_overlap':0},ensure_ascii=False,indent=2)+'\n')
 selected=pd.read_parquet(SEL,columns=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','source_sha256','source_locator','population_value_quality','latitude','longitude'])
 evidence=pd.read_parquet(EVID,columns=['source_record_id','source_evidence_json']);evidence.source_record_id=evidence.source_record_id.astype(str);ev=dict(zip(evidence.source_record_id,evidence.source_evidence_json))
 selected.source_record_id=selected.source_record_id.astype(str);selected.census_year=selected.census_year.astype(int);selected['nk']=selected.settlement_name.map(norm);selected['tk']=selected.settlement_type.map(typ);selected['rk']=selected.region_raw.map(region_key);selected['key']=list(zip(selected.nk,selected.tk,selected.rk))
 selected=selected[selected.is_additive_settlement_record.fillna(False)&selected.tk.isin(PHYS)&selected.nk.ne('')&selected.rk.ne('')].copy()
 year_key_counts=selected.groupby(['census_year','key']).source_record_id.nunique().to_dict()
 points_df=pd.read_parquet(points,columns=['target_source_record_id','target_year','coordinate_admission_status']);points_df=points_df[points_df.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)];point_ids=set(points_df.target_source_record_id.astype(str))
 selected21=selected[selected.census_year.eq(2021)].copy()
 candidates=[];qrows=[];p1082rows=[]
 for rr in req.to_dict('records'):
  qid=str(rr['wikidata_qid']);entity=entities[qid];sourceid=str(rr['source_record_id']);cur=selected21[selected21.source_record_id.eq(sourceid)].iloc[0];claim=entity.get('claims',{})
  p764=[];p31=[];p1082=[]
  for st in claim.get('P764',[]):
   if st.get('rank')=='deprecated':continue
   sn=st.get('mainsnak',{});v=sn.get('datavalue',{}).get('value') if sn.get('snaktype')=='value' else None
   p764.append({'raw':str(v),'digits':digits(v),'statement_id':st.get('id'),'rank':st.get('rank')})
  for st in claim.get('P31',[]):
   if st.get('rank')=='deprecated':continue
   sn=st.get('mainsnak',{});v=sn.get('datavalue',{}).get('value') if sn.get('snaktype')=='value' else None
   if isinstance(v,dict) and v.get('id'):p31.append(str(v['id']))
  for st in claim.get('P1082',[]):
   x=year_p1082(st);x.update({'wikidata_qid':qid,'entity_lastrevid':entity.get('lastrevid'),'entity_modified':entity.get('modified'),'raw_entity_file':rawpath.name,'raw_entity_sha256':rawsha,'retrieved_at_utc':retrieved});p1082rows.append(x);p1082.append(x)
  label=entity.get('labels',{}).get('ru',{}).get('value');expected=P31.get(typ(cur.settlement_type));expected_code=digits(rr['external_p764_raw']);native_code=digits(rr['source_oktmo_raw'])
  code_relation=any(x['digits']==expected_code and len(x['digits'])==11 and x['digits'].lstrip('0')==native_code.lstrip('0') for x in p764)
  p764_unique=len(p764)==1 and code_relation;physical=bool(expected and expected in set(p31));label_ok=bool(label) and re.sub(r'\s*-\s*','-',norm(label))==re.sub(r'\s*-\s*','-',norm(cur.settlement_name))
  qrows.append({'wikidata_qid':qid,'source_record_id':sourceid,'source_oktmo_raw':rr['source_oktmo_raw'],'source_oktmo_digits':native_code,'external_p764_claims_json':json.dumps(p764,ensure_ascii=False),'external_p764_unique_full_literal_matches_11_digit_candidate':p764_unique,'full_entity_p31_qids_json':json.dumps(sorted(set(p31))),'expected_physical_p31_qid':expected,'physical_p31_present':physical,'entity_label_ru':label,'source_name':cur.settlement_name,'normalized_label_matches_source_name':label_ok,'current_type':cur.settlement_type,'current_region':cur.region_raw,'current_source_key_counts':year_key_counts.get((2021,cur.key),0),'current_source_point_accepted':sourceid in point_ids,'entity_lastrevid':entity.get('lastrevid'),'entity_modified':entity.get('modified'),'raw_entity_file':rawpath.name,'raw_entity_sha256':rawsha,'candidate_current_identity_binding_gate':p764_unique and physical and label_ok and sourceid in point_ids and year_key_counts.get((2021,cur.key),0)==1,'identity_admitted':False})
  if not (p764_unique and physical and label_ok and sourceid in point_ids and year_key_counts.get((2021,cur.key),0)==1):continue
  key=cur.key
  oldbyyear={}
  for yr in (2002,2010):
   old=selected[(selected.census_year==yr)&(selected.key==key)]
   if len(old)==1:oldbyyear[yr]=old.iloc[0]
  for yr,row in oldbyyear.items():
   evj=json_value(ev.get(str(row.source_record_id),'{}'),{}) or {};reasons=json_value(evj.get('legacy_identity_reasons'),[]) or []
   nonadmin=set(reasons)-{'administrative_conflict','ordinal_historical_identifier_hypothesis'}
   grain=str(evj.get('entity_grain_status') or row.entity_grain_status or '')
   aggregate=bool(evj.get('is_federal_aggregate')) or str(evj.get('legacy_population_scope') or '').casefold() in {'federal_city_region','federal_city_aggregate','regional_total'}
   collision=bool(evj.get('legacy_same_year_collision')) or int(year_key_counts.get((yr,key),0))!=1
   observed_event=json_value(evj.get('observed_status_event_json'),[]) or []
   event=bool(observed_event) or 'event' in str(evj.get('legacy_quality_flag') or '').casefold()
   qidclaim=next((x for x in p1082 if x.get('year')==yr and x.get('rank')!='deprecated'),None)
   pdelta=(qidclaim.get('population')-int(row.population)) if qidclaim and qidclaim.get('population') is not None and pd.notna(row.population) else None
   candidates.append({'wikidata_qid':qid,'from_source_record_id':str(row.source_record_id),'from_year':yr,'to_source_record_id':sourceid,'to_year':2021,'relation':'same_place','candidate_rule':'exact_unique_typed_name_type_province_across_source_years_plus_current_literal_external_P764_physical_P31_and_accepted_source_point','source_name_raw':row.source_name_raw,'source_name':row.settlement_name,'source_type':row.settlement_type,'source_region_raw':row.region_raw,'source_district_raw':row.district_raw,'source_municipality_raw':row.municipality_raw,'source_population':int(row.population) if pd.notna(row.population) else None,'source_scope_raw':evj.get('legacy_population_scope') or row.population_scope,'source_file':row.source_file,'source_sheet':row.source_sheet,'source_row':row.source_row,'source_native_id_opaque':row.source_native_id,'source_sha256':row.source_sha256,'source_locator':row.source_locator,'selected_additive':bool(row.is_additive_settlement_record),'source_evidence_json':ev.get(str(row.source_record_id)),'source_identity_reasons':json.dumps(reasons,ensure_ascii=False),'nonadministrative_identity_conflict_hold':bool(nonadmin),'same_year_collision_hold':collision,'event_hold':event,'aggregate_hold':aggregate,'whole_source_year_typed_key_count':int(year_key_counts.get((yr,key),0)),'matching_single_year_precision_P1082_claim':bool(qidclaim),'p1082_population_raw':qidclaim.get('population_raw') if qidclaim else None,'p1082_population_delta_vs_source':pdelta,'p1082_population_secondary_conflict_over10':pdelta is not None and abs(pdelta)>10,'p1082_population_used_for_identity':False,'p1082_statement_id':qidclaim.get('statement_id') if qidclaim else None,'p1082_time_raw':qidclaim.get('time_raw') if qidclaim else None,'p1082_precision':qidclaim.get('precision') if qidclaim else None,'identity_admitted':False})
 edgefile=OUT/'candidate_temporal_edges_all.csv';pairdf=pd.DataFrame(candidates)
 if len(pairdf):
  valid=pairdf[~pairdf.nonadministrative_identity_conflict_hold&~pairdf.same_year_collision_hold&~pairdf.event_hold&~pairdf.aggregate_hold].copy()
 else:valid=pairdf.copy()
 pairdf.to_csv(edgefile,index=False);pd.DataFrame(qrows).to_csv(OUT/'full_entity_current_binding_review.csv',index=False);pd.DataFrame(p1082rows).to_csv(OUT/'full_entity_all_P1082_statements.csv',index=False)
 # Conditional graph replay uses only unique exact typed keys, no collision/event/aggregate, and no non-administrative conflict.
 selcols=['source_record_id','census_year','population'];allsel=pd.read_parquet(SEL,columns=selcols);allsel.source_record_id=allsel.source_record_id.astype(str);allsel.census_year=allsel.census_year.astype(int)
 uf=YearUF(allsel.source_record_id.tolist(),allsel.census_year.tolist());yearmap=dict(zip(allsel.source_record_id,allsel.census_year));g=pd.read_parquet(graph,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES):raise SystemExit('base edge status guard failed')
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if yearmap[a]!=int(e.from_year) or yearmap[b]!=int(e.to_year) or uf.union_ids(a,b)=='year_constrained_collision':raise SystemExit('base year constrained union failure')
 pointdf=pd.read_parquet(points,columns=['target_source_record_id','coordinate_admission_status']);pointdf=pointdf[pointdf.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)];pointids=set(pointdf.target_source_record_id.astype(str));base=metrics(allsel,uf,pointids);covobj=json.loads(cov.read_text());axes={str(x['year']):x['axes'] for x in covobj['census_metrics']}
 for y in ('2002','2010','2021'):
  if base[y]['full_chain']!={'rows':int(axes[y]['full_census_chain']['rows']),'population':int(axes[y]['full_census_chain']['known_population'])} or base[y]['joint_point_full_chain']!={'rows':int(axes[y]['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(axes[y]['joint_admitted_coordinate_and_full_chain']['known_population'])}:raise SystemExit('baseline coverage mismatch')
 outcomes=[]
 for r in valid.sort_values(['wikidata_qid','from_year']).itertuples(index=False):outcomes.append(uf.union_ids(str(r.from_source_record_id),str(r.to_source_record_id)))
 if len(valid):valid['union_outcome']=outcomes;valid.to_csv(OUT/'conditional_eligible_temporal_edges.csv',index=False)
 after=metrics(allsel,uf,pointids);delta={y:{ax:{m:after[y][ax][m]-base[y][ax][m] for m in ('rows','population')} for ax in ('full_chain','joint_point_full_chain')} for y in base}
 stats={'candidate_current_source_rows':len(qrows),'candidate_current_qids':len(qrows),'current_entity_binding_gate_pass':sum(bool(x['candidate_current_identity_binding_gate']) for x in qrows),'current_qid_label_hold_count':sum(not bool(x['normalized_label_matches_source_name']) for x in qrows),'current_accepted_points':sum(bool(x['current_source_point_accepted']) for x in qrows),'unique_historical_typed_key_rows':len(pairdf),'candidate_temporal_edges_pre_source_holds':len(pairdf),'candidate_edges_after_source_holds':len(valid),'unique_historical_endpoints':int(valid.from_source_record_id.nunique()) if len(valid) else 0,'single_year_precision_P1082_statements_all_years':sum(1 for r in p1082rows if r.get('year') in (2002,2010) and r.get('rank')!='deprecated'),'P1082_source_endpoint_comparisons':len(valid),'P1082_population_exact_source_matches':sum(pd.notna(x) and int(x)==0 for x in valid.p1082_population_delta_vs_source) if len(valid) else 0,'P1082_population_source_differences_over10':sum(bool(x) for x in valid.p1082_population_secondary_conflict_over10) if len(valid) else 0,'conditional_union_outcomes':{x:outcomes.count(x) for x in sorted(set(outcomes))},'conditional_metric_delta':delta}
 summary={'status':'full_raw_entity_fetch_and_exact_typed_key_temporal_candidates_only_no_admissions','counts':stats,'current_code_route':'external literal 11-digit P764 was fetched as published and compared to the unchanged 10-digit source literal only after removing leading zeroes; no padded source code or source ID was created','identity_rule':'a current physical source row is linked only as candidate to the single selected additive row in a historical year sharing its normalized physical name/type/canonical province, with whole-selected-year uniqueness; exact 2002 and/or 2010 P1082 statements are optional corroboration, never accepted population','district_treatment':'raw old district/municipality preserved as context; no boundary/legal continuity or population comparability claimed','no_history_result':'full API response inspected all P1082 claims; absence of 2002/2010 claim is not used as negative identity evidence','inputs':pins,'api':{'request_url':url,'final_url':final,'status':status,'request_qids':qids,'requested_at_utc':t0,'retrieved_at_utc':retrieved,'raw_entity_sha256':rawsha},'outputs':{f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(OUT.iterdir()) if f.is_file()}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'receipt.json').write_text(json.dumps({'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{f.name:sha(f) for f in sorted(OUT.iterdir()) if f.is_file() and f.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':summary['status'],'counts':stats,'raw_entity_sha256':rawsha},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

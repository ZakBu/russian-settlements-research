#!/usr/bin/env python3
"""Stage 2002→2021 physical-place candidates with different administrative contexts.

Administrative labels are preserved as conflicting/unresolved context. They are
not normalized, interpreted as a rename, or used to assert comparable populations.
"""
from __future__ import annotations
import csv,hashlib,json,math,random,re,sys
from collections import Counter
from pathlib import Path
import pandas as pd
sys.path.insert(0,'/workspace/russian-settlements-research/research_rebuild/mass_linkage')
from build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES
from stage_source_district_annotation_recovery_20261004 import dist_km,sha,writecsv,UF,county_core,RawHierarchy
ROOT=Path('/workspace'); REPO=ROOT/'russian-settlements-research'
BASE=ROOT/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected'
FREEZE=ROOT/'settlements-work/continuation_20261004/R4/stable_type_corridor_mass/review_freeze_v2'
SELECTED=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EVIDENCE=ROOT/'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
OUT=ROOT/'settlements-work/continuation_20261004/R4/source_district_context_physical_identity_recovery_20261004_v1'
CONFIG=REPO/'config/mass_joint_20261004.json'; SEED=20261004

def boolv(x): return str(x).strip().casefold() in {'true','1','yes'}
def region_key(x):
 s=re.sub(r'\s+',' ',str(x or '').casefold().replace('ё','е')).strip(' .,:;')
 for q in (' автономный округ',' автономная область',' область',' край',' республика',' ао'):
  if s.endswith(q): return s[:-len(q)].strip()
 return s
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 cfg=json.loads(CONFIG.read_text()); cov=json.loads((BASE/'coverage.json').read_text())
 if sha(BASE/'accepted_identity_edges.parquet')!=cfg['working_identity_graph_sha256'] or sha(BASE/'accepted_point_uses.parquet')!=cfg['working_point_uses_sha256']: raise RuntimeError('base pin mismatch')
 if sha(SELECTED)!='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657' or sha(EVIDENCE)!='e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327': raise RuntimeError('selected/evidence pin mismatch')
 cols=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_type','region_raw','district_raw','population','latitude','longitude','source_sha256','source_locator','population_scope','is_additive_settlement_record','entity_grain_status','population_value_quality']
 sdf=pd.read_parquet(SELECTED,columns=cols); smap={str(x['source_record_id']):x for x in sdf.to_dict('records')}; years={str(x['source_record_id']):int(x['census_year']) for x in sdf[['source_record_id','census_year']].to_dict('records')}
 ev=pd.read_parquet(EVIDENCE,columns=['source_record_id','source_evidence_json']); emap={str(x.source_record_id):json.loads(x.source_evidence_json) for x in ev.itertuples(index=False)}
 pts=pd.read_parquet(BASE/'accepted_point_uses.parquet',columns=['target_source_record_id','target_year','coordinate_admission_status','coordinate_source_record_id','latitude','longitude','point_origin_kind','source_name','source_type','source_region','source_okato_raw','source_oktmo_raw'])
 pts=pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]; point_ids=set(pts.target_source_record_id.astype(str))
 direct={str(r['target_source_record_id']):r for r in pts.to_dict('records') if int(r['target_year'])==2021 and str(r.get('coordinate_source_record_id'))==str(r['target_source_record_id'])}
 with open(FREEZE/'all_candidate_dispositions.csv',encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
 def admin_label(s):
  return re.sub(r'\s+',' ',str(s or '').casefold().replace('ё','е')).strip(' .,:;')
 staged=[]; funnel=Counter(); funnel_pop=Counter(); all_diff=[]
 for r in rows:
  if r['from_year']!='2002' or r['to_year']!='2021': continue
  a,b=admin_label(r['district_from_raw']),admin_label(r['district_to_raw'])
  if not a or not b or a==b: continue
  ca,_,ta=county_core(a); cb,_,tb=county_core(b)
  # Keep the new family distinct from exact same-parent suffix/case normalization already audited.
  if ca and ca==cb and ta in {'district','municipal_district','bare'} and tb in {'district','municipal_district','bare'}: continue
  all_diff.append(r); funnel['different_nonblank_nonalias_admin_context']+=1
  oldid,newid=r['from_source_record_id'],r['to_source_record_id']; pt=direct.get(newid)
  if not pt: continue
  # Independent named physical 2011 point, exactly parsed to selected locality/type/region and unique in its source.
  oldname=re.sub(r'\s+',' ',str(r['name_exact_norm']).casefold())
  historic=(r.get('historical_geokladr_row_1based','')!='' and r.get('historical_geokladr_raw_latitude','')!='' and r.get('historical_geokladr_raw_longitude','')!='' and r.get('historical_name_type_region_match_count')=='1' and r.get('classifier_to_geokladr_code_bridge') in {'exact_11_digit','literal_8_digit_plus_000'} and re.sub(r'\s+',' ',str(r.get('historical_classifier_name_parsed','')).casefold())==oldname and re.sub(r'\s+',' ',str(r.get('historical_named_object_name_parsed_2009','')).casefold())==oldname and re.sub(r'\s+',' ',str(r.get('historical_classifier_type_raw','')).casefold())==re.sub(r'\s+',' ',str(r['type_from_raw']).casefold())==re.sub(r'\s+',' ',str(r['type_to_raw']).casefold()) and str(r.get('historical_geokladr_region_raw','')).casefold()==str(r.get('region_from_raw','')).casefold())
  if not historic: continue
  d=dist_km(r['historical_geokladr_raw_latitude'],r['historical_geokladr_raw_longitude'],pt['latitude'],pt['longitude'])
  if d>1.0: continue
  # Whole-frame all-type name uniqueness, stable observed type, additive nonfederal source values.
  if not all(boolv(r.get(f'whole_region_exact_name_unique_across_types_{side}')) for side in ('from','to')): continue
  oldev,new_ev=emap.get(oldid,{}),emap.get(newid,{})
  flags=[]; hard=[]
  for lab,e in [('from',oldev),('to',new_ev)]:
   if not bool(e.get('is_additive_settlement_record')): hard.append(lab+':not_additive_or_unrecorded')
   if bool(e.get('is_federal_aggregate')): hard.append(lab+':federal_aggregate')
   if bool(e.get('legacy_same_year_collision')): hard.append(lab+':same_year_collision')
   if e.get('legacy_verified_successor_settlement_id'): hard.append(lab+':successor_event')
   if e.get('legacy_identity_reasons'):
    try: reasons=json.loads(e['legacy_identity_reasons']) if isinstance(e['legacy_identity_reasons'],str) else e['legacy_identity_reasons']
    except: reasons=[str(e['legacy_identity_reasons'])]
    flags.extend(lab+':legacy_'+str(x) for x in reasons)
   if e.get('legacy_identity_conflict'): flags.append(lab+':legacy_conflict_preserved')
  if hard: continue
  # Modern point is attached directly to the current selected source row; binding claim remains separate.
  if pt.get('coordinate_source_record_id')!=newid: continue
  # Require source metadata for names/types/region to match selected endpoint. Do not read admin label as identity.
  to=smap[newid]; fromr=smap[oldid]
  norm=lambda x:re.sub(r'[^а-яa-z0-9]+',' ',str(x or '').casefold().replace('ё','е')).strip()
  if norm(to['settlement_type'])!=norm(fromr['settlement_type']) or region_key(to['region_raw'])!=region_key(fromr['region_raw']): continue
  out=dict(r)
  out.update({'rule_family':'distinct_admin_context_exact_name_type_region_unique_historic_nativepoint_to_direct_current_point_le_1km','administrative_context_status':'raw district strings preserved; older selected metadata is not used as source-publisher identity evidence; current district hierarchy retained separately; no mapping/rename/boundary claim','historic_2011_to_current_accepted_direct_point_km':round(d,4),'current_point_target_exact':newid,'current_point_coordinate_source_record_id':pt['coordinate_source_record_id'],'current_point_origin_kind':pt.get('point_origin_kind'),'current_provider_identifier_binding_asserted':False,'current_native_OKATO_raw':to.get('okato') or r.get('to_okato_raw'),'current_native_OKTMO_raw':to.get('oktmo') or r.get('to_oktmo_raw'),'source_flags_preserved_json':json.dumps(flags,ensure_ascii=False),'legacy_flag_hardholds':json.dumps(hard,ensure_ascii=False),'source_additive_nonfederal_both':True,'observed_type_stable':True,'whole_region_exact_name_all_type_unique_both':True,'identity_admitted':False,'candidate_only':True,'population_boundary_comparability_asserted':False,'administrative_boundary_continuity_asserted':False})
  staged.append(out); funnel['all_context_and_point_candidates']+=1
  funnel_pop['old_population']+=int(float(r['from_population'] or 0)); funnel_pop['current_population']+=int(float(r['to_population'] or 0))
 # Graph safety and true joint conditional gain against exact pinned current graph.
 graph=pd.read_parquet(BASE/'accepted_identity_edges.parquet',columns=['from_source_record_id','to_source_record_id','decision_status'])
 if set(graph.decision_status.dropna().astype(str))-ACCEPTED_EDGE_STATUSES: raise RuntimeError('unknown graph statuses')
 uf=UF(years)
 for g in graph.to_dict('records'):
  stat=uf.union_disjoint(str(g['from_source_record_id']),str(g['to_source_record_id']))
  if stat=='same_year_component_collision': raise RuntimeError('baseline graph contains duplicate-year component')
 cov_year={x['year']:x['axes']['joint_admitted_coordinate_and_full_chain'] for x in json.loads((BASE/'coverage.json').read_text())['census_metrics']}
 base_rows={y:0 for y in (2002,2010,2021)};base_pop={y:0 for y in base_rows}
 def accum(uf,rr,pp):
  for row in sdf.to_dict('records'):
   sid=str(row['source_record_id']); y=int(row['census_year'])
   if sid in point_ids and uf.m[uf.find(sid)]==((1<<2002)|(1<<2010)|(1<<2021)):
    rr[y]+=1;pp[y]+=int(float(row['population'] or 0))
 accum(uf,base_rows,base_pop)
 for y in base_rows:
  if (base_rows[y],base_pop[y])!=(cov_year[y]['rows'],cov_year[y]['known_population']): raise RuntimeError(f'baseline mismatch {y}')
 applied=[]; already=[]; collided=[]
 for x in sorted(staged,key=lambda r:(-int(float(r['from_population'] or 0)),-int(float(r['to_population'] or 0)),r['edge_id'])):
  stat=uf.union_disjoint(x['from_source_record_id'],x['to_source_record_id']); x['graph_resolution']=stat
  (applied if stat=='merged' else already if stat=='already_connected' else collided).append(x)
 after_rows={y:0 for y in base_rows};after_pop={y:0 for y in base_rows};accum(uf,after_rows,after_pop)
 gain={str(y):{'rows':after_rows[y]-base_rows[y],'population':after_pop[y]-base_pop[y]} for y in base_rows}
 # Raw fixed sample top 20 + seeded random 20; audit original source names/types/regions and hierarchy labels.
 sample={x['edge_id']:'top20_mass' for x in sorted(staged,key=lambda z:-int(float(z['from_population'] or 0)))[:20]}; rest=[x for x in staged if x['edge_id'] not in sample]; random.Random(SEED).shuffle(rest)
 for x in rest[:20]:sample[x['edge_id']]='seeded_random20'
 raw=RawHierarchy(); review=[]
 for x in staged:
  if x['edge_id'] not in sample:continue
  for side,sid in [('from',x['from_source_record_id']),('to',x['to_source_record_id'])]:
   rec=smap[sid]; result,status,witness=raw.verify(rec,rec.get('district_raw'))
   review.append({'edge_id':x['edge_id'],'sample_stratum':sample[x['edge_id']],'side':side,'source_record_id':sid,'year':rec['census_year'],'source_file':rec['source_file'],'source_locator':rec.get('source_locator'),'source_name_raw':rec.get('source_name_raw'),'source_type_raw':rec.get('settlement_type'),'source_region_raw':rec.get('region_raw'),'source_district_context_raw_preserved':rec.get('district_raw'),'district_hierarchy_literal_or_context_found':result,'district_hierarchy_review_status':status,'raw_context_witness_json':witness})
 writecsv(OUT/'candidate_edges.csv',staged);writecsv(OUT/'graph_safe_new_link_candidates.csv',applied);writecsv(OUT/'already_connected_redundant_candidates.csv',already);writecsv(OUT/'graph_collision_holds.csv',collided);writecsv(OUT/'fixed_40_raw_source_review.csv',review);writecsv(OUT/'raw_source_hashes.csv',list(raw.hashes.values()))
 summary={'status':'candidate_only_distinct_admin_context_physical_identity_rule_no_admissions','rule':'unique whole-province exact name+stable type; exact unique historical native named typed point within 1 km of directly accepted coordinate on exact 2021 source row; additive nonfederal source records; no same-year/event/federal hard conflict. Older selected district metadata is retained but does not assert source-publisher county membership; current raw district hierarchy is preserved separately. No district mapping, rename, legal continuity, or population boundary comparability is claimed.','pins':{str(CONFIG):sha(CONFIG),str(SELECTED):sha(SELECTED),str(EVIDENCE):sha(EVIDENCE),str(BASE/'accepted_identity_edges.parquet'):sha(BASE/'accepted_identity_edges.parquet'),str(BASE/'accepted_point_uses.parquet'):sha(BASE/'accepted_point_uses.parquet'),str(BASE/'coverage.json'):sha(BASE/'coverage.json'),str(FREEZE/'all_candidate_dispositions.csv'):sha(FREEZE/'all_candidate_dispositions.csv')},'source_conflict_funnel':dict(funnel),'candidate_endpoint_population_diagnostic_not_gain':funnel_pop,'current_baseline_joint_full_chain':{str(y):{'rows':base_rows[y],'population':base_pop[y]} for y in base_rows},'source_hierarchy_fixed_sample':{'edges':len(sample),'endpoint_rows':len(review),'raw_files':len(raw.hashes),'older_selected_district_label_not_found_in_raw_hierarchy':sum(x['side']=='from' and not x['district_hierarchy_literal_or_context_found'] for x in review),'current_selected_district_literal_in_2021_hierarchy':sum(x['side']=='to' and x['district_hierarchy_literal_or_context_found'] for x in review)},'candidate_rows':len(staged),'graph_safe_new_link_candidates':len(applied),'already_connected':len(already),'same_year_graph_collision_holds':len(collided),'conditional_joint_gain_after_graph_safe_batch':gain,'no_identity_or_population_admissions':True,'historical_point_to_current_point_cutoff_km':1.0,'script_sha256':sha(Path(__file__))}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 rec={'status':summary['status'],'input_pins':summary['pins'],'script':str(Path(__file__)),'script_sha256':sha(Path(__file__)),'outputs':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.name!='receipt.json'}}
 (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

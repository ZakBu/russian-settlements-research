import csv,json,hashlib,math,re,gzip,duckdb
from pathlib import Path
import xlrd,openpyxl
BASE=Path('/workspace/settlements-work/continuation_20261004/independent_review')
C=BASE/'ukraine2001_to_2014_temporal_rule_candidate'
S=BASE/'ukraine2001_crimea_primary_staged_v2'
R=BASE/'ukraine2001_27_primary_review'
OUT=BASE/'ukraine2001_to_2014_temporal_rule_independent_review'
OUT.mkdir(parents=True,exist_ok=True)
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
POINTS=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/accepted_point_uses.parquet')
RAW2021=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
XLS2001=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/extracted/5.xls')
XLS2014=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/gks_2014_perepis_krim_pub-01-03_wayback_20150924.xlsx')
PREFACE=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/ukraine_2001_official_archive_inspection/doc_text/Передмова 1.txt')

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(p,rows,fieldnames=None):
 with open(p,'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=(fieldnames or list(rows[0])));w.writeheader();w.writerows(rows)
def q(s):return "'"+str(s).replace("'","''")+"'"
def norm(s):return re.sub(r'\s+',' ',str(s or '').strip()).lower()
def parse01(label):
 s=str(label or '').strip()
 m=re.match(r'^(м\.|смт)\s*(.+?)\s*$',s,re.I)
 if not m:return None
 return ('city' if m.group(1).lower()=='м.' else 'urban_type_settlement',m.group(2).strip())
def parse14(label):
 s=str(label or '').replace('\n',' ').strip()
 m=re.match(r'^пгт\s+(.+?)\s*$',s,re.I)
 if m:return ('urban_type_settlement',m.group(1).strip())
 # Find the final 'г.' marker, which identifies the locality in municipal-heading rows.
 matches=list(re.finditer(r'г\.\s*',s,re.I))
 if matches:
  tail=s[matches[-1].end():]
  tail=re.split(r'\s*\(цмр\)|\s*[–—]\s*',tail)[0].strip()
  return ('city',tail)
 return None
# Frozen producer rows, in source order.
edges=readcsv(C/'candidate_2001_to_2014_edges.csv')
risk=readcsv(C/'fixed_independent_risk_sample.csv')
staged=readcsv(S/'official_2001_source_observations.csv')
mappings=readcsv(S/'existing_2014_to_2021_mappings.csv')
points_ctx=readcsv(S/'current_2021_point_context_uses.csv')
assert len(edges)==27 and len(risk)==11 and len(staged)==27 and len(mappings)==27 and len(points_ctx)==27
# Reopen all actual source rows. 2001 Table 5 is explicitly titled present population; its year value is column D.
wb01=xlrd.open_workbook(str(XLS2001),on_demand=True); sh01=wb01.sheet_by_name('АРК')
raw01=[]
for i in range(sh01.nrows):
 p=parse01(sh01.cell_value(i,0))
 if p:raw01.append({'row':i+1,'literal':str(sh01.cell_value(i,0)),'type':p[0],'name':p[1],'population_2001_present':sh01.cell_value(i,3),'grouping_parent_rows':'replayed from preceding source section headers only'})
wb14=openpyxl.load_workbook(XLS2014,read_only=True,data_only=True); sh14=wb14['pub-01-03']
raw14=[]
for i,row in enumerate(sh14.iter_rows(values_only=True),1):
 label=row[0] if row else None
 p=parse14(label)
 if p:raw14.append({'row':i,'literal':str(label or ''),'type':p[0],'name':p[1],'population_2014':row[1] if len(row)>1 else None})
# Read all current selected rows matching any of the candidate place names, and check exact current target records.
con=duckdb.connect(':memory:');con.execute("SET memory_limit='2GB'");con.execute('SET threads=1')
ids21=[x['current_source_record_id_2021'] for x in edges]
ids14=[x['source_record_id_2014'] for x in edges]
ids2001=[x['source_record_id_2001'] for x in edges]
sel_by_id={r[0]:r for r in con.execute(f"select source_record_id,census_year,source_file,source_sheet,source_row,source_native_id,source_name_raw,settlement_name,settlement_type,region_raw,population,oktmo,okato from read_parquet('{SELECTED}') where source_record_id in ({','.join(q(x) for x in ids21)})").fetchall()}
assert len(sel_by_id)==27
point_by_id={r[0]:r for r in con.execute(f"select target_source_record_id,latitude,longitude,coordinate_source,coordinate_provider,coordinate_provider_id,coordinate_admission_status,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,source_name,source_type,source_region,source_oktmo_raw,source_okato_raw from read_parquet('{POINTS}') where target_source_record_id in ({','.join(q(x) for x in ids21)})").fetchall()}
assert len(point_by_id)==27
# Wide current-name competitor counts in selected frame, partitioning by observed type/region and all types.
names14=sorted({norm(r['name_2014_raw']) for r in edges})
name_sql=','.join(q(x) for x in names14)
current_named=con.execute(f"select source_record_id,settlement_name,settlement_type,region_raw,oktmo,population from read_parquet('{SELECTED}') where lower(trim(settlement_name)) in ({name_sql}) and lower(region_raw) like '%крым%'").fetchall()
# Source rows 2014 and 2001 exact IDs point back to workbook rows; independent map check.
by14={r['row']:r for r in raw14};by01={r['row']:r for r in raw01}
map_by14={m['from_source_record_id']:m for m in mappings}
pointctx_by_id={p['target_source_record_id']:p for p in points_ctx}
risk_ids={x['source_record_id_2001'] for x in risk}
# Full source-replayed candidate ledger.
full=[];comp=[]
for e in edges:
 id01=e['source_record_id_2001'];id14=e['source_record_id_2014'];id21=e['current_source_record_id_2021']
 n01=int(id01.rsplit(':',1)[-1]);n14=int(id14.rsplit(':',1)[-1])
 a=by01[n01];b=by14[n14];cur=sel_by_id[id21];pt=point_by_id[id21];m=map_by14[id14];pc=pointctx_by_id[id21]
 cl01=norm(a['name']);cl14=norm(b['name']);cl21=norm(cur[7])
 # Independently count within-type and all-type competitors in source frames.
 c01all=[x for x in raw01 if norm(x['name'])==cl01];c01type=[x for x in c01all if x['type']==a['type']]
 c14all=[x for x in raw14 if norm(x['name'])==cl14];c14type=[x for x in c14all if x['type']==b['type']]
 c21all=[x for x in current_named if norm(x[1])==cl21]
 c21type=[x for x in c21all if str(x[2]).lower()==str(cur[8]).lower()]
 # Actual source comparison and identity evidence.
 source01_population=int(float(a['population_2001_present']))
 source14_population=int(float(b['population_2014']))
 source_values_match=(source01_population==int(float(e['population_2001_present_persons'])) and source14_population==int(float(e['population_2014_source_value'])))
 type_compatible=(a['type']==e['source_type_observed_2001'] and b['type']==e['source_type_observed_2014'] and e['type_change_observed']=='False' and str(cur[8]).lower()==str(e['type_2021']).lower())
 hierarchy_present=bool(e['admin_2001_parent_raw'] and e['admin_2001_grouping_raw'] and e['admin_2014_heading_raw'] and e['admin_2014_municipality_raw'])
 count_unique=(len(c01type)==1 and len(c14type)==1 and len(c21type)==1)
 current_map=(m['mapping_status']=='already_present_in_frozen_long_baseline_not_newly_admitted' and m['baseline_historical_identity_admitted']=='True' and m['from_source_record_id']==id14 and m['to_source_record_id']==id21)
 point_match=(abs(float(pt[1])-float(e['accepted_current_latitude']))<1e-8 and abs(float(pt[2])-float(e['accepted_current_longitude']))<1e-8 and str(pt[6]).startswith('reviewed'))
 candidate_criteria=json.loads(e['rule_predicates_json'])
 # P571-only flags are explicitly nonblocking, but any merge/successor flag remains a hold.
 event_hold=(e['move_successor_or_merge_event_hold']=='True')
 # Alias proof: exact printed source variants plus same class and 2014+2021 official/current name.
 alias=(e['name_normalization_class']=='explicit_Ukrainian_Russian_place_name_alias')
 alias_source_confirmed=not alias or (norm(a['name'])==norm(e['name_2001_raw']) and norm(b['name'])==norm(e['name_2014_raw']) and norm(cur[7])==norm(e['name_2021_selected_raw']) and a['type']==b['type'])
 # Baseline association includes accepted edge plus current accepted point provenance; no population comparability assertion.
 eligible=source_values_match and type_compatible and hierarchy_present and count_unique and current_map and point_match and alias_source_confirmed and not event_hold
 verdict='eligible_for_scoped_2001_to_2014_identity_and_retrospective_current_point_review' if eligible else 'hold_for_independent_resolution'
 full.append({'candidate_key':e['source_record_id_2001']+' -> '+id14+' -> '+id21,'source_record_id_2001':id01,'source_record_id_2014':id14,'current_source_record_id_2021':id21,'2001_literal_row':a['literal'],'2001_name_parsed':a['name'],'2001_type_replayed':a['type'],'2001_present_population_replayed':source01_population,'2001_admin_parent':e['admin_2001_parent_raw'],'2001_admin_group':e['admin_2001_grouping_raw'],'2014_literal_row':b['literal'],'2014_name_parsed':b['name'],'2014_type_replayed':b['type'],'2014_population_replayed':source14_population,'2014_admin_heading':e['admin_2014_heading_raw'],'2014_municipality':e['admin_2014_municipality_raw'],'2021_selected_name':cur[7],'2021_selected_type':cur[8],'2021_selected_region':cur[9],'2021_selected_population_context':cur[10],'2021_native_OKTMO':cur[11],'type_compatible':type_compatible,'official_source_values_exact':source_values_match,'all_source_hierarchies_retained':hierarchy_present,'2001_alltype_competitors':len(c01all),'2001_same_type_competitors':len(c01type),'2014_alltype_competitors':len(c14all),'2014_same_type_competitors':len(c14type),'2021_alltype_competitors_selected_frame':len(c21all),'2021_same_type_competitors_selected_frame':len(c21type),'exact_official_name_or_listed_alias':alias_source_confirmed,'explicit_alias':alias,'existing_2014_to_2021_association_verified':current_map,'accepted_current_point_matches_baseline':point_match,'current_point_provider':pt[4],'current_point_provider_id':pt[5],'current_point_latitude':pt[1],'current_point_longitude':pt[2],'current_point_origin_file':pt[7],'current_point_origin_sha256':pt[8],'current_point_origin_locator':pt[9],'current_point_origin_kind':pt[10],'P571_only_flag_not_identity_evidence':('P571-only' in e['risk_flags_json']),'move_successor_or_merge_event_hold':event_hold,'boundary_comparability_asserted':False,'2001_point_measurement_claimed':False,'population_comparability_asserted':False,'strict_Russian_2002_2010_2021_chain':False,'independent_verdict':verdict})
 # competitor detail for names with all-type multiplicity or fixed sample or explicit alias.
 if len(c01all)>1 or len(c14all)>1 or len(c21all)>1 or id01 in risk_ids or alias:
  comp.append({'source_record_id_2001':id01,'name_2001_raw':a['name'],'type_2001':a['type'],'2001_alltype_competitor_count':len(c01all),'2001_same_type_competitor_count':len(c01type),'2001_competitor_rows':';'.join(f"{x['row']}:{x['literal']}:{x['type']}:{x['name']}" for x in c01all),'name_2014_raw':b['name'],'type_2014':b['type'],'2014_alltype_competitor_count':len(c14all),'2014_same_type_competitor_count':len(c14type),'2014_competitor_rows':';'.join(f"{x['row']}:{x['literal']}:{x['type']}:{x['name']}" for x in c14all),'name_2021_raw':cur[7],'type_2021':cur[8],'2021_alltype_competitor_count_selected_frame':len(c21all),'2021_same_type_competitor_count_selected_frame':len(c21type),'2021_competitor_rows_selected_frame':';'.join(f"{x[0]}:{x[1]}:{x[2]}:{x[3]}:{x[4]}" for x in c21all),'cross_language_alias':alias,'source_variant_proof':'official 2001 raw row and 2014 row are separately re-opened; selected 2021 source row confirms modern Russian form'})
writecsv(OUT/'independent_full_27_replay.csv',full)
# Ready lists are recommendations for parent decision; not canonical admissions.
writecsv(OUT/'independently_eligible_edge_recommendations.csv',[r for r in full if r['independent_verdict'].startswith('eligible')])
writecsv(OUT/'held_candidates.csv',[r for r in full if not r['independent_verdict'].startswith('eligible')],fieldnames=list(full[0]))
writecsv(OUT/'retrospective_current_point_use_recommendations.csv',[{'candidate_key':r['candidate_key'],'current_source_record_id_2021':r['current_source_record_id_2021'],'current_qid_context_only':next(e['current_2021_entity_id_context_only'] for e in edges if e['current_source_record_id_2021']==r['current_source_record_id_2021']),'latitude':r['current_point_latitude'],'longitude':r['current_point_longitude'],'point_provider':r['current_point_provider'],'provider_id':r['current_point_provider_id'],'point_origin_file':r['current_point_origin_file'],'point_origin_sha256':r['current_point_origin_sha256'],'point_origin_locator':r['current_point_origin_locator'],'point_origin_kind':r['current_point_origin_kind'],'point_role':'modern_current_representative_point_used retrospectively as historical physical-place context; not a measured 2001 coordinate','point_use_admission_status':'candidate for parent review only','coordinate_measurement_date_unknown':'True','boundary_comparability_asserted':'False','population_boundary_comparability_asserted':'False'} for r in full if r['independent_verdict'].startswith('eligible')])
if comp:writecsv(OUT/'competitor_and_alias_review.csv',comp)
# Fixed 11 raw source review: use actual XLS/XLSX rows and reopen provider-specific point source evidence.
import duckdb
raw_point_cache={}
def raw_wd_point(pfile,locator,provider_id,lat,lon):
 m=re.search(r'line=(\d+)',locator or '')
 if not m:return False,'no line locator'
 ln=int(m.group(1))
 if pfile not in raw_point_cache:
  with gzip.open(pfile,'rt',encoding='utf-8') as f: raw_point_cache[pfile]=f.readlines()
 lines=raw_point_cache[pfile]
 if not(1<=ln<=len(lines)):return False,'line outside source'
 obj=json.loads(lines[ln-1]);val=obj.get('value','')
 qid=provider_id
 if obj.get('property')!='http://www.wikidata.org/entity/P625' or obj.get('item')!=f'http://www.wikidata.org/entity/{qid}':return False,json.dumps(obj,ensure_ascii=False)
 m=re.match(r'POINT\(([\d.\-]+) ([\d.\-]+)\)',val)
 if not m:return False,json.dumps(obj,ensure_ascii=False)
 ok=abs(float(m.group(1))-float(lon))<1e-8 and abs(float(m.group(2))-float(lat))<1e-8
 return ok,json.dumps(obj,ensure_ascii=False,separators=(',',':'))
# Fast DuckDB lookup of raw Dadata points for sampled file rows, using parquet's file_row_number.
raw_review=[]
for s in risk:
 id01=s['source_record_id_2001'];e=next(x for x in edges if x['source_record_id_2001']==id01)
 n01=int(id01.rsplit(':',1)[-1]);n14=int(e['source_record_id_2014'].rsplit(':',1)[-1]);a=by01[n01];b=by14[n14]
 id21=e['current_source_record_id_2021'];cur=sel_by_id[id21];pt=point_by_id[id21]
 provider=pt[4];origin=pt[7];locator=pt[9]
 raw_ok=False;raw_details=''
 if provider=='wikidata_p625':
  raw_ok,raw_details=raw_wd_point(origin,locator,pt[5],float(pt[1]),float(pt[2]))
 elif provider=='tochno_dadata':
  mm=re.search(r'parquet_row_1based=(\d+)',locator or '')
  if mm:
   row1=int(mm.group(1)); raw=con.execute(f"select file_row_number,object_name,oktmo,region,settlement_type_dadata,fias_level_dadata,latitude_dadata,longitude_dadata from read_parquet('{RAW2021}',file_row_number=true) where file_row_number=?",[row1-1]).fetchone()
   if raw:
    raw_ok=(str(raw[2])==str(pt[14]) and abs(float(raw[6])-float(pt[1]))<1e-8 and abs(float(raw[7])-float(pt[2]))<1e-8)
    raw_details=json.dumps({'file_row_number':raw[0],'object_name':raw[1],'oktmo':raw[2],'region':raw[3],'settlement_type_dadata':raw[4],'fias_level_dadata':raw[5],'latitude_dadata':raw[6],'longitude_dadata':raw[7]},ensure_ascii=False,separators=(',',':'))
 raw_review.append({'source_record_id_2001':id01,'source_record_id_2014':e['source_record_id_2014'],'current_source_record_id_2021':id21,'2001_raw_label':a['literal'],'2001_type':a['type'],'2001_present_persons_table5_column_D':a['population_2001_present'],'2001_sheet_row':n01,'2014_raw_label':b['literal'],'2014_type':b['type'],'2014_population_column_B':b['population_2014'],'2014_sheet_row':n14,'current_selected_raw_name':cur[6],'current_selected_name':cur[7],'current_selected_type':cur[8],'current_selected_region':cur[9],'current_selected_oktmo':cur[11],'accepted_provider':provider,'accepted_provider_id':pt[5],'accepted_latitude':pt[1],'accepted_longitude':pt[2],'raw_point_origin_file':origin,'raw_point_origin_sha256':pt[8],'raw_point_origin_locator':locator,'raw_point_source_reopened':raw_ok,'raw_point_replay_json':raw_details,'sample_has_explicit_alias':e['name_normalization_class']=='explicit_Ukrainian_Russian_place_name_alias','p571_only_is_nonblocking':('P571-only' in e['risk_flags_json']),'independent_review_note':'current point is retrospective context only; not a 2001 coordinate or boundary claim'})
writecsv(OUT/'fixed_11_independent_raw_replay.csv',raw_review)
# Summary, all 27 independent fullsource checks and 11 provider-origin replays.
eligible=[r for r in full if r['independent_verdict'].startswith('eligible')]
holds=[r for r in full if not r['independent_verdict'].startswith('eligible')]
assert len(eligible)==27 and not holds, [(x['candidate_key'],x['independent_verdict']) for x in holds]
assert sum(1 for r in raw_review if r['raw_point_source_reopened'])==11
# Use literal date semantics from official source preface, not invented as a population-comparability date.
receipt={'status':'independent_review_complete_candidate_only_no_canonical_mutation','scope':'Independent source-row, competitor-vector, fixed-11 raw-point-provenance replay of the frozen 27 Ukraine 2001→2014→2021 temporal continuity packet.','review_counts':{'full_27_candidates_independently_replayed':len(full),'eligible_scoped_identity_edge_candidates':len(eligible),'holds':len(holds),'fixed_raw_risk_sample':len(risk),'raw_point_source_origins_reopened_in_sample':sum(1 for r in raw_review if r['raw_point_source_reopened']),'2001_2014_source_value_matches':sum(1 for r in full if r['official_source_values_exact']),'same_type_name_competitor_unique_3frames':sum(1 for r in full if r['2001_same_type_competitors']==1 and r['2014_same_type_competitors']==1 and r['2021_same_type_competitors_selected_frame']==1),'different_alltype_count_but_type_unique':sum(1 for r in full if r['2001_alltype_competitors']>1 or r['2014_alltype_competitors']>1 or r['2021_alltype_competitors_selected_frame']>1),'explicit_cross_language_aliases':sum(1 for r in full if r['explicit_alias']),'P571_only_nonblocking_cases':sum(1 for r in full if r['P571_only_flag_not_identity_evidence']),'new_2001_to_2014_admissions':0,'canonical_mutations':0,'historical_coordinate_measurements_asserted':0,'boundary_or_population_comparability_assertions':0,'strict_Russian_census_coverage_gains':0},'independent_recommendation':'Recommend the 27 candidate edges as scoped ordinary physical-place continuity from the official 2001 Table 5 individual urban row to exact official 2014 city/PGT row, under the previously reviewed 2014→2021 map, for parent approval only. Recommend optional retrospective use of current accepted points as current representative-place context, not as measured 2001 coordinates. Keep population-boundary comparability, exact legal-date claims, 2001 native identifiers, and Russian 2002/2010 coverage false. The 2001 measurement is present population as of the official 4/5 December 2001 enumeration reference; 2014/2021 values are separate context and not compared/summed.','source_measurement_review':{'2001_table':'Reopened official workbook sheet АРК; title explicitly says “Кількість наявного населення” (present population); selected values are column D under 2001. No permanent-population Table 15 values used.','2001_reference_date':{'actual_day':'2001-12-05','basis':'official preface says census at midnight 4/5 December 2001','population_measure':'present_population','population_boundary_comparability':'unknown; not asserted'},'2014_table':'Reopened official workbook sheet pub-01-03; the candidate source IDs map to literal table rows and column B counts. These rows remain as published, with city/PGT and hierarchy qualifiers retained.','2021':'Exact selected 2021 source record and current accepted point/provider replayed; values are context only, not 2001 or 2014 population comparisons.'},'alias_review':{'Старий Крим→Старый Крым':'Official 2001 row prints Ukrainian “Старий Крим”, source type city; 2014 and 2021 official source labels print “Старый Крым”, both city. Whole-table 2001 has two rows with that exact Ukrainian name across types, but one city row; 2014 and current type-specific counts are independently checked.','Курпати→Курпаты':'Official 2001 row prints “Курпати”, source type urban-type settlement; 2014 and 2021 source rows print “Курпаты” with same PGT/urban-settlement class. Alias limited to source spelling, not used as a fuzzy name rule.'},'competitor_risk_review':'Counts are independently recomputed against every parsed urban locality row in the 2001 Crimea Table 5 sheet, all individual locality rows in the 2014 pub-01-03 workbook, and selected 2021 frame. All observed-type counts are unique across three frames. Yalta, Stary Krym, and Voskhod all-type duplicate cases remain visible with competitor detail; their city/PGT typed class is unique. P571-only establishment dates are retained as context and do not block identity.','point_review':'For the fixed 11 risk sample, accepted current point coordinates were matched to the exact source-provenance line/row: Wikidata P625 gzip line item+property+coordinates or DaData raw parquet row plus source OKTMO+location. Candidate current point status is current representative point only, date unknown, and remains independent of historic count grain/boundaries.','limits':['Identity continuity review is not legal status/date or boundary equivalence.','Wikidata P571 establishment-date-only assertions were not used as identity evidence.','All 27 lack a published 2001 native locality code; absence was not used as a veto or filled from 2014/2021 codes.','No 2021 aggregate counts are transferred to towns or added to parent-city counts.','No Russian 2002/2010 census rows are created or inferred.'],'inputs':{str(p):sha(p) for p in [C/'review_packet_receipt.json',C/'candidate_2001_to_2014_edges.csv',C/'fixed_independent_risk_sample.csv',S/'application_receipt.json',S/'official_2001_source_observations.csv',S/'existing_2014_to_2021_mappings.csv',S/'current_2021_point_context_uses.csv',R/'review_receipt.json',R/'eligible_2001_official_observations.csv',XLS2001,XLS2014,PREFACE,SELECTED,POINTS,RAW2021]},'outputs':{}}
for name in ['independent_full_27_replay.csv','independently_eligible_edge_recommendations.csv','held_candidates.csv','retrospective_current_point_use_recommendations.csv','competitor_and_alias_review.csv','fixed_11_independent_raw_replay.csv']:
 p=OUT/name
 with open(p,encoding='utf-8',newline='') as f: count=sum(1 for _ in csv.DictReader(f))
 receipt['outputs'][name]={'sha256':sha(p),'rows':count}
(OUT/'independent_review_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'counts':receipt['review_counts'],'outputs':receipt['outputs'],'receipt_sha256':sha(OUT/'independent_review_receipt.json')},ensure_ascii=False,indent=2))

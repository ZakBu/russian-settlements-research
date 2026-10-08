import sys,json,gzip,csv,re,hashlib,math
from pathlib import Path
from collections import Counter,defaultdict
import pandas as pd,xlrd
from bs4 import BeautifulSoup
import openpyxl,subprocess
from docx import Document
Z=Path(__file__).resolve().parent;E=Z.parent;sys.path.insert(0,str(E.parent/'mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def code(v):
 try:return str(int(float(v))) if pd.notna(v) and str(v).strip() else ''
 except:return str(v).strip('"').lstrip('0')
def name(v):
 v=normalize(v);return re.sub(r'\s+(?:рп|дп)$','',v)
def rawname(v):return name(re.sub(r'^(?:пос[её]лок городского типа|рабочий пос[её]лок|дачный пос[её]лок|пос[её]лок|деревня|село|пгт|город|хутор|станица|аул|слобода|местечко|починок)\s+','',str(v),flags=re.I))
D=pd.read_csv(Z/'all377_extreme_histories.csv',keep_default_na=False);O=pd.read_csv(Z/'native_extreme_observations.csv.gz',keep_default_na=False).set_index('source_record_id');P=json.loads((Z/'active_extreme_point_claims.json').read_text());pins=json.loads((Z/'source_state58_input_pins.json').read_text())
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');TSV=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');CLS=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');GEO=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
raw=pd.read_parquet(RAW,columns=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population','oktmo_dadata','okato_dadata','fias_id_dadata','latitude_dadata','longitude_dadata']);raw['row_1based']=range(1,len(raw)+1);raw['own_code']=raw.oktmo.map(code);raw['provider_code']=raw.oktmo_dadata.map(code);raw['name_key']=raw.object_name.map(rawname);raw['observed_typed_NP']=raw.object_level.eq('Населенный пункт')&raw.object_name.str.match(r'^(?:село|деревня|пос[её]лок|хутор|станица|аул|город|пгт|станция|слобода|местечко|починок)\s+',case=False,na=False)&~raw.object_name.str.contains(r'\(часть\s*\d+\)',case=False,regex=True,na=False);NP=raw[raw.observed_typed_NP];counts=Counter(NP.own_code)
qfiles=[E/'native_mass_raw_roster_point_corrections_20261008/explicit_other_published_NP_point_binding_candidates.csv.gz',E/'baseline_fullraw_point_code_conflict_scan_20261008/seven_full3_current_carrier_binding_conflicts.csv',E/'corrected_ownpoint_cached_history_followup_20261008/corrected_carrier_component_inventory.csv.gz']
exclude=set()
qfiles.append(E/'baseline_fullraw_point_code_conflict_scan_20261008/explicit_other_published_NP_point_binding_candidates.csv.gz')
qfiles.append(E/'corrected_ownpoint_cached_history_followup_20261008/new_Geo_rule_carrier_scope.csv.gz')
for p in [*qfiles[:2],qfiles[3]]:exclude.update(pd.read_csv(p,keep_default_na=False).source_record_id)
ex97=pd.read_csv(qfiles[4],keep_default_na=False)
for column in ['carrier_source_record_id','source_record_id','current_source_record_id']:
 if column in ex97:exclude.update(ex97[column]);break
inv=pd.read_csv(qfiles[2],keep_default_na=False);print('INV',inv.columns.tolist(),flush=True)
# The whole corrected-carrier inventory is excluded conservatively, including all 149 recovered carriers / new97 Geo carriers.
for column in ['carrier_source_record_id','source_record_id','current_source_record_id']:
 if column in inv:exclude.update(inv[column]);break
geo=pd.read_parquet('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet').set_index('record_number_1based');cl=pd.read_parquet('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet').set_index('historical_okato');sql=CLS.read_text().splitlines();wanted_codes={code(raw.iloc[int(sid.rsplit(':',1)[1])-1].oktmo) for sid in D.source_record_id_2021};tsv=defaultdict(list)
with TSV.open() as stream:
 for n,r in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  c=code(r['?oktmo'])
  if c in wanted_codes:tsv[c].append((n,r))
for p in [RAW,TSV,CLS,GEO,*qfiles,Z/'all377_extreme_histories.csv',Z/'native_extreme_observations.csv.gz',Z/'active_extreme_point_claims.json']:pins[str(p)]=sha(p)
geoprops=json.loads((Z/'cached_geonames_properties.json').read_text());geozip=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');pins[str(geozip)]=sha(geozip)
rejections=[];points=[];witness=[];holds=[];rivals=[];rank=[];books={};raw_geo=GEO.open('rb');accepted=[]
for r in D.to_dict('records'):
 sid=r['source_record_id_2021'];current=O.loc[sid];own=raw.iloc[int(sid.rsplit(':',1)[1])-1];oldids=[r['source_record_id_2002'],r['source_record_id_2010']];old=[O.loc[x] for x in oldids];reason='';anchor=None;anchorproof={};modern=(float(P[sid]['latitude']),float(P[sid]['longitude']))
 if sid in exclude:reason='excluded_current_provider_conflict_or_new149_recovery_component_or_Geo97_quarantine'
 elif not own.observed_typed_NP or name(current.settlement_name)!=own.name_key or float(current.population)!=float(own.population):reason='current_actual_published_typed_native_NP_binding_not_exact'
 elif counts[own.own_code]!=1 or not own.own_code:reason='current_own_code_has_multiple_actual_published_NP_competitors_or_blank'
 elif any(name(x.settlement_name)!=name(current.settlement_name) for x in old):reason='accepted_identity_name_change_requires_separate_physical_continuity_review'

 else:
  if own.own_code==own.provider_code and pd.notna(own.latitude_dadata) and pd.notna(own.longitude_dadata):
   proposed=(float(own.latitude_dadata),float(own.longitude_dadata))
   if distance_km(proposed,modern)<=5:
    anchor=proposed;anchorproof=dict(anchor_rule='actual_fullraw2021_exact_own_native_OKTMO_equals_Dadata_code_with_typed_NP_name_region_and_unique_published_native_code',anchor_origin_file=str(RAW),anchor_origin_sha256=pins[str(RAW)],anchor_origin_locator='parquet row 1-based='+str(own.row_1based)+'; native oktmo, typed object_name, mun_upper, mun_lower, oktmo_dadata, latitude_dadata, longitude_dadata',anchor_code=own.own_code,actual_raw_current_row={k:own[k] for k in ['row_1based','object_level','object_name','oktmo','region','mun_upper','mun_lower','population','oktmo_dadata','okato_dadata','latitude_dadata','longitude_dadata']})
  if anchor is None:
   choices=[]
   for line,t in tsv[own.own_code]:
    match=re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',t['?coord']);okato=t['?okato'].strip('"').zfill(11);c=cl.loc[okato] if okato in cl.index else None
    if match and c is not None and c.is_settlement_raw=='t' and name(c['name'])==name(current.settlement_name):
     proposed=(float(match[2]),float(match[1]));admin=normalize(t['?adminLabel'].replace('@ru','').strip('"'));parish=normalize(own.mun_lower)
     if admin and (admin in parish or parish in admin) and distance_km(proposed,modern)<=5:choices.append((proposed,line,t,c))
   distinct={x[0] for x in choices};qids={x[2]['?item'] for x in choices}
   if len(distinct)==1 and len(qids)==1:
    anchor,line,t,c=choices[0];anchorproof=dict(anchor_rule='cached_literal_Wikimedia_own_P764_native_code_plus_own_P721_true_physical_NP_classifier_and_current_parish_with_own_point',anchor_origin_file=str(TSV),anchor_origin_sha256=pins[str(TSV)],anchor_origin_locator='literal TSV line '+str(line),anchor_code=own.own_code,literal_TSV_row=t,own_OKATO=c.name,own_classifier_line=int(c.source_line_1based),own_classifier_literal=sql[int(c.source_line_1based)-1],actual_raw_current_row={k:own[k] for k in ['row_1based','object_level','object_name','oktmo','region','mun_upper','mun_lower','population']})
  if anchor is None and sid in geoprops['points']:
   entity=geoprops['points'][sid];gp=entity['row'];region_entity=geoprops['adm1'].get(gp[10]);aliases=[name(x) for x in [gp[1],gp[2],*gp[3].split(',')]];regional=NP[NP.region.eq(own.region)&NP.name_key.eq(own.name_key)]
   region_aliases=[normalize(x) for x in [region_entity[1],region_entity[2],*region_entity[3].split(',')]] if region_entity else []
   if gp[6]=='P' and gp[7] in ['PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLC'] and gp[8]=='RU' and name(current.settlement_name) in aliases and normalize(own.region) in region_aliases and len(regional)==1 and (float(gp[4]),float(gp[5]))==modern:
    anchor=modern;anchorproof=dict(anchor_rule='independent_raw_GeoNames_physical_PPL_exact_Cyrillic_ownname_correct_ADM1_and_unique_fullraw_alltype_NP_across_entire_region',anchor_origin_file=str(geozip),anchor_origin_sha256=pins[str(geozip)],anchor_origin_locator='RU.txt literal line '+str(entity['line'])+'; geonameid='+gp[0],anchor_code=own.own_code,modern_official_code_asserted=False,external_admin2='UNKNOWN' if not gp[11] else gp[11],literal_GeoNames_point_fields=gp,literal_GeoNames_ADM1_fields=region_entity,fullraw_current_name_region_NP_rivals=1,actual_raw_current_row={k:own[k] for k in ['row_1based','object_level','object_name','oktmo','region','mun_upper','mun_lower','population']})
  if anchor is None:reason='no_independently_bound_modern_physical_point_or_ambiguous_regionwide_GeoNames_name'
 # Current full actual raw name-region competitors retained, including all subordinate contexts / types.
 competitors=NP[NP.region.eq(own.region)&NP.name_key.eq(own.name_key)]
 for rival in competitors.to_dict('records'):rivals.append(dict(carrier_source_record_id=sid,raw_source_record_id='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(rival['row_1based']),native_code=rival['own_code'],literal_label=rival['object_name'],literal_region=rival['region'],literal_county=rival['mun_upper'],literal_subordinate=rival['mun_lower'],population=rival['population'],is_own_row=rival['row_1based']==own.row_1based))
 bad=[];proof=[]
 if not reason:
  for target in oldids:
   p=P[target];isgeo='geokladr' in str(p.get('point_origin_file','')).lower();dist=distance_km((float(p['latitude']),float(p['longitude'])),anchor)
   if not isgeo or dist<=100:continue
   loc=str(p.get('point_origin_locator',''));m=re.search(r'(?:raw_dbf_record_number_1based|DBF_record_1based|DBFrecord)\s*=\s*(\d+)',loc)
   if not m: reason='old_Geo_actual_record_locator_not_resolved';break
   g=geo.loc[int(m[1])];gc=str(g.historical_okato);cc=gc if gc in cl.index else gc[:-3] if gc.endswith('000') and gc[:-3] in cl.index else '';c=cl.loc[cc] if cc else None
   if c is not None and c.is_settlement_raw!='t' and gc.endswith('000') and gc[:-3] in cl.index:cc=gc[:-3];c=cl.loc[cc]
   if c is None or c.is_settlement_raw!='t' or name(c['name'])!=name(O.loc[target].settlement_name) or g.is_deleted:reason='old_Geo_own_classifier_name_type_physical_binding_not_exact';break
   raw_geo.seek(int(g.record_byte_offset_0based));payload=raw_geo.read(395);assert payload[0:1]==b' ' and g.name_raw.strip() in payload.decode('cp1251')
   assert (float(g.latitude_from_lat),float(g.longitude_from_long))==(float(p['latitude']),float(p['longitude']));assert gc in sql[int(c.source_line_1based)-1] or cc in sql[int(c.source_line_1based)-1]
   # Reopen the native old census row as a separate observation witness; no count/quality interpretation changes.
   obs=O.loc[target];native_path=Path(str(obs.source_path)) if str(obs.source_path).startswith('/workspace/') else Path('/workspace/settlements-raw')/str(obs.source_file);sheet=target.rsplit(':',2)[1];rowtext=target.rsplit(':',1)[1];rown=int(rowtext) if rowtext.isdigit() else 0;rawrow=None;native_count_grade='literal_native_numeric_count_reopened'
   if rown and native_path.exists() and native_path.suffix.lower()=='.xls':
    if str(native_path) not in books:books[str(native_path)]=xlrd.open_workbook(str(native_path),on_demand=True)
    try:rawrow=(books[str(native_path)].sheet_by_name(sheet) if sheet in books[str(native_path)].sheet_names() else books[str(native_path)].sheet_by_index(int(sheet))).row_values(rown-1)
    except (xlrd.XLRDError,IndexError):rawrow=None
   if rawrow is None and target.startswith('ARK2010:'):
    native_path=Path('/workspace/settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html');htmlkey=str(native_path)
    if htmlkey not in books:books[htmlkey]=BeautifulSoup(native_path.read_bytes(),'html.parser').find_all('table')
    index=int(re.search(r'tr(\d+)',target)[1]);candidates=[]
    for tableindex,tab in enumerate(books[htmlkey]):
     rowshtml=tab.find_all('tr')
     if index<len(rowshtml):
      cells=[c.get_text(' ',strip=True) for c in rowshtml[index].find_all(['td','th'])]
      if any(name(obs.settlement_name) in name(v) for v in cells):candidates.append((tableindex,index,cells))
    if len(candidates)==1:tableindex,index,rawrow=candidates[0];sheet='HTMLtable'+str(tableindex);rown=index+1
   if rawrow is None and target.startswith('KAL2010:'):
    native_path=Path('/workspace/settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx');key=str(native_path)
    if key not in books:books[key]=openpyxl.load_workbook(native_path,read_only=True,data_only=True)
    rown=int(target.rsplit(':R',1)[1]);sheet='4';rawrow=list(next(books[key][sheet].iter_rows(min_row=rown,max_row=rown,values_only=True)))
   if rawrow is None and target.startswith('ROSSTAT2010:T5:'):
    locator=json.loads(obs.source_locator);page=int(locator['pdf_page_1based']);start=int(locator['text_line_start_1based']);key=str(native_path)+':pdf:'+str(page)
    if key not in books:books[key]=subprocess.check_output(['pdftotext','-layout','-f',str(page),'-l',str(page),str(native_path),'-'],text=True).splitlines()
    line=books[key][start-1] if start<=len(books[key]) else '';matched=[(idx+1,text) for idx,text in enumerate(books[key]) if name(obs.settlement_name) in name(text)]
    if name(obs.settlement_name) not in name(line) and len(matched)==1:start,line=matched[0]
    rawrow=[line,*re.findall(r'(?<!\d)\d+(?:[ \u00a0]\d{3})?(?!\d)',line)];sheet='PDFpage'+str(page);rown=start
   if rawrow is None and target.startswith('ROSSTAT2010KARELIA:'):
    native_path=Path('/workspace/settlements-karelia-inputs/build/evidence/ingestion/source/karelia_2010_rural_settlements.docx');key=str(native_path)
    if key not in books:books[key]=Document(native_path)
    table,rowindex=map(int,re.search(r':t(\d+):r(\d+)',target).groups());rawrow=[c.text for c in books[key].tables[table].rows[rowindex].cells];sheet='DOCXtable'+str(table);rown=rowindex
    if float(obs.population)==0 and rawrow[1].strip()=='-':native_count_grade='already_accepted_native_zero_quality_preserved_literal_dash_not_reinterpreted_or_new_count_created'
   if rawrow is None or not any(name(obs.settlement_name) in name(v) for v in rawrow if isinstance(v,str)):
    if False:pass
    else:reason='native_old_literal_row_name_witness_not_reopened';break
   if native_count_grade=='literal_native_numeric_count_reopened' and float(obs.population) not in [float(str(v).replace(' ','').replace('\u00a0','').replace(',','.')) for v in rawrow if re.fullmatch(r'[\d\s.,]+',str(v).strip())]:reason='native_old_literal_population_not_exact';break
   pins[str(native_path)]=sha(native_path) if str(native_path) not in pins else pins[str(native_path)]
   proof.append(dict(target_source_record_id=target,own_historical_OKATO=gc,classifier_code=cc,classifier_literal_name=c.name_raw,classifier_literal_status=c.status,classifier_literal_line=int(c.source_line_1based),classifier_literal_raw=sql[int(c.source_line_1based)-1],Geo_record_1based=int(g.name),Geo_byte_offset=int(g.record_byte_offset_0based),Geo_literal_name=g.name_raw,Geo_literal_latitude=float(g.latitude_from_lat),Geo_literal_longitude=float(g.longitude_from_long),native_file=str(native_path),native_sha256=pins[str(native_path)],native_sheet=sheet,native_row_1based=rown,native_literal_row=rawrow,native_original_count=float(obs.population),native_original_quality=obs.population_value_quality,native_count_check_grade=native_count_grade,accepted_component_identity_preserved=True));bad.append(target)
  if not bad and not reason:reason='no_historical_Geo_claim_more_than100km_from_verified_anchor'
 if reason:
  holds.append(dict(carrier_source_record_id=sid,name=current.settlement_name,region=current.region_norm,reason=reason,max_interyear_distance_km=r['max_interyear_distance_km'],population_2002=r['population_2002'],population_2010=r['population_2010'],population_2021=r['population_2021']));rank.append(dict(carrier_source_record_id=sid,status='HOLD',reason=reason));continue
 # Also supersede a clone on another old year if it exactly copied a contradicted Geo point.
 badgeopoints={(float(P[t]['latitude']),float(P[t]['longitude'])) for t in bad}
 for target in oldids:
  if target not in bad and (float(P[target]['latitude']),float(P[target]['longitude'])) in badgeopoints:bad.append(target)
 for target in bad:
  p=P[target];ledger=Path(p['point_ledger_path']);pins[str(ledger)]=sha(ledger) if str(ledger) not in pins else pins[str(ledger)];rejections.append(dict(target_source_record_id=target,rejection_status='reviewed_superseded_representative_point_only',old_latitude=p['latitude'],old_longitude=p['longitude'],origin_ledger=str(ledger),origin_ledger_sha256=pins[str(ledger)],old_point_origin_file=p.get('point_origin_file',''),old_point_origin_sha256=p.get('point_origin_sha256',''),old_point_origin_locator=p.get('point_origin_locator',''),carrier_source_record_id=sid,rejection_reason='Representative inherited Geo coordinate or exact cloned Geo coordinate superseded on existing accepted identity, independently owncoded modern physical locality anchor and native old observation checked; no population/identity rejection.'));points.append(dict(target_source_record_id=target,latitude=anchor[0],longitude=anchor[1],coordinate_admission_status='reviewed_extension_rule_accepted',point_origin_file=anchorproof['anchor_origin_file'],point_origin_sha256=anchorproof['anchor_origin_sha256'],point_origin_locator=anchorproof['anchor_origin_locator'],point_origin_kind='explicit_retrospective_continuity_from_independently_owncoded_current_NP_point',coordinate_source_record_id=sid,own_native_current_code=own.own_code,modern_anchor_official_code_asserted=anchorproof.get('modern_official_code_asserted',True),external_admin2=anchorproof.get('external_admin2','not_applicable'),historical_coordinate_accuracy='UNKNOWN',historical_point_grade='retrospective_representative_continuity_inference_not_historical_measurement',censusday_point_measured_exactly=False,population_or_quality_modified=False,identity_changes=False))
 witness.append(dict(carrier_source_record_id=sid,name=current.settlement_name,region=current.region_norm,anchor_latitude=anchor[0],anchor_longitude=anchor[1],anchor_to_existing_current_point_km=distance_km(anchor,modern),current_native_code_unique_in_full_published_NP_roster=True,current_name_region_rivals=len(competitors),anchor_proof=anchorproof,old_native_and_classifier_proofs=proof,corrected_source_record_ids=bad,native_types_by_year={str(y):O.loc[r['source_record_id_'+str(y)]].settlement_type for y in [2002,2010,2021]},native_type_change_date='UNKNOWN' if len({normalize(x.settlement_type) for x in [*old,current]})!=1 else 'not_applicable',stable_continuity_rule='Already accepted three-census native identity, unchanged normalized own name; administrative NP type fields preserved, no physical relocation inferred, owncoded typed modern locality + independently literal native historical observation and dated own physical NP classifier; no new identity or boundary assertion.',population_2002=r['population_2002'],population_2010=r['population_2010'],population_2021=r['population_2021'],current_point_unchanged=True));accepted.append(r);rank.append(dict(carrier_source_record_id=sid,status='accepted_point_recovery_only',reason=anchorproof['anchor_rule']))
for fname,frame in [('point_use_rejections.csv.gz',rejections),('accepted_point_use_delta.csv.gz',points),('held_candidates.csv.gz',holds),('all_current_name_region_rivals.csv.gz',rivals),('ranked_rule_results.csv.gz',rank)]:pd.DataFrame(frame).to_csv(Z/fname,index=False,compression={'method':'gzip','mtime':0})
with gzip.GzipFile(filename=str(Z/'native_ownpoint_recovery_witnesses.json.gz'),mode='wb',mtime=0) as out:out.write(json.dumps(witness,ensure_ascii=False,default=str).encode())
(Z/'correction_input_pins.json').write_text(json.dumps(pins,indent=2)+'\n');summary=dict(status='bounded_all377_rule_review_finished',total_histories=377,recovered_histories=len(accepted),corrected_old_point_uses=len(points),held_histories=len(holds),recovered_gross_population_by_year={str(y):int(sum(r['population_'+str(y)] for r in accepted)) for y in [2002,2010,2021]},held_reasons=dict(Counter(r['reason'] for r in holds)),new_identity_edges=0,current_point_targets_changed=0,excluded_current_carriers=len(exclude),builder_sha256=sha(Path(__file__)));(Z/'rule_review_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))

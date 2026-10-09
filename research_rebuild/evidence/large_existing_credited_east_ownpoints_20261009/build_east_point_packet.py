from __future__ import annotations
import csv, hashlib, json, re, sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

OUT = Path(__file__).resolve().parent
REPO = Path('/workspace/russian-settlements-research')
RAW = Path('/workspace/settlements-raw')
ROSTER = REPO / 'research_rebuild/evidence/large_existing_credit_missing_ownpoint_20261009/east_exact_roster.csv'
OSM_JSON = OUT / 'osm_nominatim_raw_witnesses.json'
GEO_DBF = RAW / 'data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
GEO_SHA = 'd1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650'
SCOPE_FILE = REPO / 'research_rebuild/evidence/over1000_south_other_completion_20261009/batch3_two_wrong_object_scopes/accepted_typed_native_scope_corrections.csv'

# OSM feature IDs are pinned by exact cached Nominatim response objects in osm_nominatim_raw_witnesses.json.
OSM_PICK = {
 ('челябинская','шершни'):('node',1579397574),
 ('челябинская','смолинский'):('node',3777132458),
 ('челябинская','сосновка'):('relation',17870093),
 ('бурятия','тулунжа'):('relation',16737657),
 ('бурятия','исток'):('way',1374372998),
 ('бурятия','солдатский'):('way',1374371607),
 ('бурятия','забайкальский'):('relation',11909986),
 ('самарская','береза'):('way',862745731),
 ('самарская','прибрежный'):('way',1488892857),
 ('самарская','поволжский'):('node',2293933839),
 ('челябинская','новосинеглазовский'):('relation',13296173),
 ('челябинская','федоровка'):('node',5878538663),
 ('челябинская','бажово'):('node',1036713905),
 ('челябинская','вахрушево'):('relation',14649213),
 ('челябинская','горняк'):('way',630837764),
 ('челябинская','железнодорожный'):('way',327535499),
 ('челябинская','октябрьский'):('relation',20811295),
 ('челябинская','потанино'):('relation',14649212),
 ('челябинская','старокамышинск'):('way',196911562),
 ('бурятия','заречный'):('way',431067940),
 ('бурятия','сокол'):('way',104254583),
 ('алтайский','затон'):('node',4483224730),
 ('алтайский','новосиликатный'):('way',220428436),
 ('алтайский','белоярск'):('node',281429286),
 ('алтайский','новогорский'):('way',167658428),
 ('кемеровская','кедровка'):('node',907463494),
 ('кемеровская','пионер'):('node',907463105),
 ('кемеровская','промышленновский'):('node',1216995392),
 ('кемеровская','ягуновский'):('node',907463598),
 ('кемеровская','листвяги'):('way',76844500),
 ('кемеровская','притомский'):('node',221188934),
}
# Raw 2011 GeoKLADR/OKATO DBF records: exact own-place name/type and region, independently
# corroborated by exact OSM names or the accepted same-locality source hierarchy.
GEO_PICK = {
 ('башкортостан','бижбуляк'):132837,
 ('оренбургская','плешаново'):84661,
 ('самарская','сергиевск'):62011,
 ('самарская','кинель-черкассы'):61511,
 ('самарская','федоровка'):61141,
 ('бурятия','бичура'):136424,
 ('алтайский','солонешное'):1090,
 ('алтайский','лесной'):1580,
 ('алтайский','красногорское'):464,
 ('алтайский','пригородный'):1582,
 ('кемеровская','боровой'):53231,
}
WIKIPEDIA = {
 ('кемеровская','абагур'):{
  'source_url':'https://ru.wikipedia.org/w/index.php?title=Абагур&oldid=154893355',
  'article_title':'Абагур','revision_id':'154893355','latitude':53.7372222222,'longitude':87.2630555556,
  'coordinate_literal':'53°44′14″ N, 87°15′47″ E',
  'coordinate_locator':'article infobox coordinate link; page render line 124; identity/history lines 149-166; 2002 population line 143',
  'source_binding_note':'Own article identifies Абагур / Абагур-Лесной, former pgt included in Novokuznetsk in 2004; 2002 population 6,696.',
 },
 ('челябинская','сосновка'):{
  'source_url':'https://ru.wikipedia.org/w/index.php?title=Сосновка_(Челябинск)&oldid=150477622',
  'article_title':'Сосновка (Челябинск)','revision_id':'150477622','latitude':55.0711111111,'longitude':61.2661111111,
  'coordinate_literal':'55°04′16″ N, 61°15′58″ E',
  'coordinate_locator':'article infobox coordinate link; page render line 119; history/context lines 141, 151-153; 2002 population lines 135/161',
  'source_binding_note':'Own article identifies the former village in Chelyabinsk; same 2002 population 1,784, transfer to city in 1978 and removal from settlement register in 2004. The article categorizes it in Central District.',
 },
}
REGION_RU={'алтайский':'Алтайский край','челябинская':'Челябинская область','бурятия':'Республика Бурятия','самарская':'Самарская область','кемеровская':'Кемеровская область','башкортостан':'Республика Башкортостан','хакасия':'Республика Хакасия','оренбургская':'Оренбургская область'}

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def norm(s):
 return re.sub(r'[^a-zа-яё0-9]+',' ',str(s or '').lower().replace('ё','е')).strip()
def base_name(s):
 return re.sub(r'\s*\(\s*часть\s*\d+\s*\)\s*','',str(s),flags=re.I).strip()
def csv_write(path,rows,fields):
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

roster=list(csv.DictReader(ROSTER.open(encoding='utf-8-sig',newline='')))
osm=json.load(OSM_JSON.open(encoding='utf-8'))
osm_by_key={(x['region_norm'],norm(x['query_name'])):x for x in osm}
# Parse the canonical original DBF bytes using the repository's raw-byte verifier.
sys.path.insert(0,str(REPO/'research_rebuild/mass_linkage'))
from verify_geokladr_snapshot import parse_dbf_records
meta,grecs=parse_dbf_records(GEO_DBF)
if sha(GEO_DBF)!=GEO_SHA: raise SystemExit('2011 GeoKLADR raw DBF SHA mismatch')
grec_by_no={r['record_number_1based']:r for r in grecs}
# Point source witness map per locality.
choices={}
for rawkey,recno in GEO_PICK.items():
 key=(rawkey[0],norm(rawkey[1]))
 r=grec_by_no[recno]
 choices[key]={'kind':'geokladr','record':r}
for rawkey,(ot,oid) in OSM_PICK.items():
 key=(rawkey[0],norm(rawkey[1]))
 group=osm_by_key[key]
 matches=[r for r in group['results'] if r.get('osm_type')==ot and int(r.get('osm_id'))==oid]
 if len(matches)!=1: raise SystemExit(f'OSM picked object missing/nonunique: {key} {ot}/{oid}')
 choices[key]={'kind':'osm','group':group,'record':matches[0]}

# Raw source workbook witnesses pin the original record and its immediate hierarchy context.
workbooks={}
source_witness=[]
source_files={}
for x in roster:
 uid=x['source_record_id']; name=base_name(x['settlement_name']); key=(x['region_norm'],norm(name))
 if 'сельсовет' in norm(x['settlement_name']):
  continue
 if key not in choices and key!=('кемеровская','абагур'):
  raise SystemExit(f'No reviewed ownpoint source choice for {uid}: {key}')
 rel=x['source_file']
 fpath=RAW/rel
 if not fpath.exists():
  # Older 2002 urban Tom 1 uses the official Tom 1 subdirectory.
  fpath=RAW/'data/raw/2002_official_tom1/1_TOM_01_04.xls'
 if not fpath.exists(): raise SystemExit(f'missing raw source {fpath}')
 source_files[str(fpath)]={'sha256':sha(fpath),'size_bytes':fpath.stat().st_size,'path':str(fpath)}
 m=re.search(r':([^:]+):(\d+)$',uid)
 if not m: raise SystemExit(f'Cannot parse source row UID {uid}')
 sheet,rowtxt=m.group(1),m.group(2); rownum=int(rowtxt)
 cache=(str(fpath),sheet)
 if cache not in workbooks:
  sheet_name=0 if sheet=='0' else sheet
  df=pd.read_excel(fpath,sheet_name=sheet_name,header=None,dtype=object)
  workbooks[cache]=df
 df=workbooks[cache]
 # Source row locators are 1-based for Sheet1/Sib and official TOM's row number (the row ID).
 idx=rownum-1
 if idx<0 or idx>=len(df): raise SystemExit(f'row outside workbook {uid} len={len(df)}')
 rawrow=[None if pd.isna(v) else str(v) for v in df.iloc[idx].tolist()]
 # Capture the nearest nonempty rows above it, preserving all cells and order.
 prior=[]
 for j in range(idx-1,max(-1,idx-31),-1):
  vals=[None if pd.isna(v) else str(v) for v in df.iloc[j].tolist()]
  if any(v and v.strip() for v in vals):
   prior.append({'row_1based':j+1,'cells':vals})
   if len(prior)>=8: break
 prior.reverse()
 source_witness.append({
  'source_record_id':uid,'census_year':x['census_year'],'settlement_name_raw':x['settlement_name'],
  'settlement_type_raw':x['settlement_type'],'region_norm':x['region_norm'],'district_raw':x['district_raw'],
  'population_raw_preserved':x['population'],'population_value_quality':x['population_value_quality'],
  'source_file':rel,'source_path':str(fpath),'source_sha256':source_files[str(fpath)]['sha256'],
  'source_sheet':sheet,'source_row_1based':rownum,'raw_row_cells_json':json.dumps(rawrow,ensure_ascii=False),
  'preceding_hierarchy_witness_rows_json':json.dumps(prior,ensure_ascii=False),
 })

# Emit all raw GeoKLADR exact-name candidates for in-scope locality names; selected rows are marked.
region_ter={'алтайский':'01','челябинская':'75','бурятия':'81','самарская':'36','кемеровская':'32','башкортостан':'80','оренбургская':'53'}
name_region={(x['region_norm'],norm(base_name(x['settlement_name']))) for x in roster if x['region_norm']!='хакасия'}
geowit=[]
for r in grecs:
 if r['is_deleted'] or r.get('latitude_from_lat') is None or r.get('longitude_from_long') is None: continue
 rawname=norm(r.get('name_raw'))
 rawname=re.sub(r'^(с|п|д|х|ст|станция|ж д рзд)\s+','',rawname)
 for region,nm in name_region:
  if r.get('ter_value')==region_ter.get(region) and rawname==nm:
   geowit.append({
    'region_norm':region,'normalized_target_name':nm,'dbf_record_number_1based':r['record_number_1based'],
    'dbf_byte_offset_0based':r['record_byte_offset_0based'],'okato_raw':r['historical_okato'],
    'name_raw':r['name_raw'],'settlement_type_raw':r['settlement_type_raw'],'kladr_raw':r['kladr'],
    'latitude':r['latitude_from_lat'],'longitude':r['longitude_from_long'],
    'source_status_raw':r['source_status_value'],'selected_as_point_origin':r['record_number_1based']==GEO_PICK.get((region,nm)),
    'raw_source_file':str(GEO_DBF),'raw_source_sha256':GEO_SHA,
   })

point_rows=[]; decision_rows=[]
for x in roster:
 uid=x['source_record_id']; name=x['settlement_name']; base=base_name(name); region=x['region_norm']; key=(region,norm(base))
 is_scope='сельсовет' in norm(name)
 if is_scope:
  decision_rows.append({
   'target_source_record_id':uid,'census_year':x['census_year'],'settlement_name_raw':name,
   'settlement_type_raw':x['settlement_type'],'region_norm':region,'district_raw':x['district_raw'],
   'native_population_preserved':x['population'],'disposition':'scope_exempt_no_own_NP_point',
   'point_source_record_id':'','latitude':'','longitude':'',
   'source_support':'research_rebuild/evidence/over1000_south_other_completion_20261009/batch3_two_wrong_object_scopes/accepted_typed_native_scope_corrections.csv row source_record_id='+uid,
   'decision_reason':'Accepted source-scope packet classifies the 1,042 row as municipal council aggregate Sелосонский сельсовет, subtotal 724+205+113; no council centre assigned.',
  });
  continue
 part=bool(re.search(r'\(\s*часть\s*\d+\s*\)',name,re.I))
 if key in WIKIPEDIA:
  wiki=WIKIPEDIA[key]
  srcid=f"WIKIPEDIA:ruwiki:{wiki['article_title']}:rev{wiki['revision_id']}"; lat=wiki['latitude']; lon=wiki['longitude']
  origin='independent_own_article_coordinate_former_locality'
  origin_file=wiki['source_url']; origin_sha=''; locator=wiki['coordinate_locator']+'; '+wiki['coordinate_literal']
  binding='accepted baseline same-locality lineage plus own article exact former-locality name/region and original source context'
  source_note=wiki['source_binding_note']
 elif choices[key]['kind']=='geokladr':
  r=choices[key]['record']; lat=r['latitude_from_lat'];lon=r['longitude_from_long']
  srcid=f"GEOKLADR:2011:okato.dbf:record:{r['record_number_1based']}"
  origin='direct_2011_GeoKLADR_OKATO_named_settlement_coordinate'
  origin_file=str(GEO_DBF);origin_sha=GEO_SHA
  locator=f"raw_dbf_record_number_1based={r['record_number_1based']};byte_offset_0based={r['record_byte_offset_0based']};OKATO={r['historical_okato']};NAME1={r['name_raw']};SCOKATO={r['settlement_type_raw']}"
  binding='accepted baseline same-locality lineage plus exact-name/type 2011 GeoKLADR physical settlement row and original source hierarchy'
  source_note=f"GeoKLADR exact named place/type row; selected record {r['record_number_1based']} has OKATO {r['historical_okato']}."
 else:
  g=choices[key]['group'];r=choices[key]['record'];lat=float(r['lat']);lon=float(r['lon'])
  srcid=f"OSM:{r['osm_type']}:{r['osm_id']}"
  origin='direct_OSM_named_locality_or_neighborhood_representative_point'
  origin_file=str(OSM_JSON);origin_sha=sha(OSM_JSON)
  locator=f"{r['osm_type']}/{r['osm_id']}; https://www.openstreetmap.org/{r['osm_type']}/{r['osm_id']}; Nominatim query={g['query_url']}"
  binding='accepted baseline same-locality lineage plus exact OSM named locality/neighborhood and original census hierarchy; OSM object identity not asserted as a census-provider ID'
  source_note=f"OSM exact named {r.get('category')}:{r.get('type')} object; address context: {r.get('display_name')}"
 inference=(f"Retrospective representative point for {x['census_year']} source UID {uid}; no census-date coordinate or population-boundary comparability asserted. "
            +('This literal census part uses the whole locality own point only as coarse joint location support; no part-specific centre is claimed. ' if part else '')
            +'Coordinate is a locality/neighborhood point, not a municipal parent point.')
 point_rows.append({
  'target_source_record_id':uid,'latitude':lat,'longitude':lon,'coordinate_admission_status':'reviewed_extension_rule_accepted',
  'coordinate_source_record_id':srcid,'point_origin_file':origin_file,'point_origin_sha256':origin_sha,
  'point_origin_locator':locator,'point_origin_kind':origin,'coordinate_binding_rule':binding,
  'point_use_inference':inference,'historical_census_coordinate_asserted':'False',
  'population_boundary_comparability_asserted':'False','external_provider_ID_binding_asserted':'False',
  'current_carrier_source_record_id':'',
 })
 decision_rows.append({
  'target_source_record_id':uid,'census_year':x['census_year'],'settlement_name_raw':name,
  'settlement_type_raw':x['settlement_type'],'region_norm':region,'district_raw':x['district_raw'],
  'native_population_preserved':x['population'],'disposition':'accepted_coarse_joint_point_use' if part else 'accepted_own_locality_point',
  'point_source_record_id':srcid,'point_source_kind':origin,'latitude':lat,'longitude':lon,
  'source_locator':locator,'source_context_and_point_reason':source_note,
  'population_quality_or_value_modified':'False','historical_coordinate_claimed':'False',
 })

point_fields=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_binding_rule','point_use_inference','historical_census_coordinate_asserted','population_boundary_comparability_asserted','external_provider_ID_binding_asserted','current_carrier_source_record_id']
csv_write(OUT/'accepted_point_use_delta.csv',point_rows,point_fields)
csv_write(OUT/'point_dispositions.csv',decision_rows,list(dict.fromkeys(k for r in decision_rows for k in r)))
csv_write(OUT/'native_source_row_witnesses.csv',source_witness,list(dict.fromkeys(k for r in source_witness for k in r)))
csv_write(OUT/'geokladr_2011_exact_name_candidate_witnesses.csv',geowit,list(dict.fromkeys(k for r in geowit for k in r)))
csv_write(OUT/'source_file_manifest.csv',[{'path':v['path'],'sha256':v['sha256'],'size_bytes':v['size_bytes']} for v in source_files.values()]+[{'path':str(GEO_DBF),'sha256':GEO_SHA,'size_bytes':GEO_DBF.stat().st_size},{'path':str(ROSTER),'sha256':sha(ROSTER),'size_bytes':ROSTER.stat().st_size},{'path':str(OSM_JSON),'sha256':sha(OSM_JSON),'size_bytes':OSM_JSON.stat().st_size},{'path':str(SCOPE_FILE),'sha256':sha(SCOPE_FILE),'size_bytes':SCOPE_FILE.stat().st_size}],['path','sha256','size_bytes'])
(OUT/'wikipedia_article_point_witnesses.json').write_text(json.dumps([{'region_norm':k[0],'normalized_name':k[1],**v} for k,v in WIKIPEDIA.items()],ensure_ascii=False,indent=2)+'\n',encoding='utf8')

# Independent assertions: full assigned UID roster, every actual locality pointed, scope row exempt.
expected={x['source_record_id'] for x in roster}
point_targets={r['target_source_record_id'] for r in point_rows}
exempt_targets={r['target_source_record_id'] for r in decision_rows if r['disposition']=='scope_exempt_no_own_NP_point'}
if point_targets & exempt_targets or point_targets | exempt_targets != expected: raise SystemExit('incomplete/overlapping exact roster coverage')
if len(point_rows)!=52 or len(exempt_targets)!=1: raise SystemExit(f'unexpected assignment sizes points={len(point_rows)} exempt={len(exempt_targets)}')
for r in point_rows:
 if not (-90<=float(r['latitude'])<=90 and -180<=float(r['longitude'])<=180): raise SystemExit('invalid coordinates')
# Manifest after outputs exist; pin all artifacts except manifest itself.
artifacts=[]
for p in sorted(OUT.iterdir()):
 if p.is_file() and p.name not in {'manifest.json','run_receipt.json'}:
  artifacts.append({'path':p.name,'sha256':sha(p),'size_bytes':p.stat().st_size})
manifest={'zone':'large_existing_credited_east_ownpoints_20261009','created_at_utc':datetime.now(timezone.utc).isoformat(),
 'assignment_input':str(ROSTER),'assignment_input_sha256':sha(ROSTER),'assigned_UIDs':len(expected),
 'accepted_locality_point_uses':len(point_rows),'accepted_nonlocal_scope_exemptions':len(exempt_targets),
 'point_policy':'Use only proper named locality/neighborhood coordinates; literal census parts share a whole-locality point as coarse joint support, never as a part centroid. No population or historical-coordinate claims.',
 'source_hashes':{'GeoKLADR_2011_OKATO_DBF':GEO_SHA,'raw_OSM_Nominatim_witnesses':sha(OSM_JSON)},
 'artifacts':artifacts}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
receipt={'status':'pass','uid_count':len(expected),'point_uses':len(point_rows),'scope_exemptions':len(exempt_targets),'point_use_sha256':sha(OUT/'accepted_point_use_delta.csv'),'point_dispositions_sha256':sha(OUT/'point_dispositions.csv'),'manifest_sha256':sha(OUT/'manifest.json'),'validation':'53/53 exact east-roster UIDs partitioned into 52 valid own-locality point uses and 1 previously accepted aggregate-scope exemption; no count fields mutated.'}
(OUT/'run_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(receipt,ensure_ascii=False,indent=2))

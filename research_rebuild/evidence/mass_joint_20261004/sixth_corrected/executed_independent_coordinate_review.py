import csv,json,hashlib,pathlib,collections,re,math,gzip,unicodedata,random,os,statistics
import pyarrow.parquet as pq
import duckdb
PKT=pathlib.Path('/workspace/settlements-work/continuation_20261004/root/fifth_point_conflict_correction_candidates_fullcohort_v2')
OUT=pathlib.Path('/workspace/settlements-work/continuation_20261004/independent_review/geokladr_point_corrections_862')
CAND=PKT/'source_point_correction_candidate_rows.csv'; INV=PKT/'current_conflict_source_binding_inventory.csv'; QCLAIM=PKT/'current_qid_raw_p764_p31_claims_1847.csv'; AUDIT=PKT/'audited_current_source_rows_1847.csv'; PKTREC=PKT/'receipt.json'; MANIFEST=PKT/'sha256_manifest.json'
RAWTOCHNO=pathlib.Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
RAWGEO=pathlib.Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
GEO_PARSED=pathlib.Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
SEL=pathlib.Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EVID=pathlib.Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
GRAPH=pathlib.Path('/workspace/settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_identity_edges.parquet')
POINTS=pathlib.Path('/workspace/settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_point_uses.parquet')
CONFIG=pathlib.Path('/workspace/russian-settlements-research/config/mass_joint_20261004.json')
DBF_EXPECTED='d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650'
PARSER_SCRIPT=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/verify_geokladr_snapshot.py')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def cr(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def norm(x):return ' '.join(unicodedata.normalize('NFKC',str(x or '')).casefold().replace('ё','е').replace('\xa0',' ').split())
def num(x):
 try:
  if x is None or x=='':return None
  return float(x)
 except:return None
def hav(a,b):
 p=math.pi/180;d1=(b[0]-a[0])*p;d2=(b[1]-a[1])*p
 z=math.sin(d1/2)**2+math.cos(a[0]*p)*math.cos(b[0]*p)*math.sin(d2/2)**2
 return 6371.0088*2*math.asin(min(1,math.sqrt(z)))
def close(a,b,tol=1e-8):return a is not None and b is not None and abs(float(a)-float(b))<=tol
def dbf_header(path):
 with open(path,'rb') as f:
  pre=f.read(32); count=int.from_bytes(pre[4:8],'little'); hlen=int.from_bytes(pre[8:10],'little'); rlen=int.from_bytes(pre[10:12],'little');f.seek(0);h=f.read(hlen)
 fields=[];off=1
 for pos in range(32,hlen,32):
  if h[pos]==0x0d:break
  d=h[pos:pos+32]; name=d[:11].split(b'\0',1)[0].decode('ascii'); typ=chr(d[11]);width=d[16];dec=d[17];fields.append((name,typ,width,off));off+=width
 assert off==rlen
 return count,hlen,rlen,fields
def parse_dbf_record(stream,hlen,rlen,fields,n):
 offset=hlen+(n-1)*rlen;stream.seek(offset);raw=stream.read(rlen);assert len(raw)==rlen
 vals={}
 for name,typ,width,off in fields:
  b=raw[off:off+width];s=b.decode('cp1251').strip()
  if typ in 'NF' and s:
   try:v=float(s)
   except:v=s
  else:v=s or None
  vals[name]=v
 return offset,raw,vals
# Exact packet pins and candidate vector.
assert sha(CAND)=='c3eb324aff431994e9f0b74078144d48b533af0d3ab65027dc6663c1d181f65c'
assert sha(PKTREC)=='8816f46e90d8db7e5ff3445321bff99af7f94c34e0be408d7585dec1926bf052'
manifest=json.loads(MANIFEST.read_text());
for f,h in manifest.items():
 path=PKT/f
 if f!='receipt.json':assert sha(path)==h,(f,sha(path),h)
candidates=cr(CAND); inventory={r['current_source_record_id']:r for r in cr(INV)}; qc={r['current_source_record_id']:r for r in cr(QCLAIM)}; audit={r['current_source_record_id']:r for r in cr(AUDIT)}
assert len(candidates)==862 and len({x['current_source_record_id'] for x in candidates})==824
assert collections.Counter(x['historical_observation_year'] for x in candidates)=={'2010':822,'2002':40}
# Candidate predicate and admission-limitation vector.
rule_fields=['predicate_exact_source_p764','predicate_exact_name','predicate_exact_type','predicate_exact_region','predicate_unique_code_qid','predicate_unique_qid_code','predicate_native_competition_clear','predicate_physical_p31','predicate_no_admin_region_conflict']
assert all(x[k]=='True' for x in candidates for k in rule_fields)
assert all(x['status']=='candidate_only_for_independent_source_point_review' for x in candidates)
assert all(not x['current_source_event_candidates_json'] and not x['old_point_lineage_event_candidates_json'] for x in candidates)
assert all(x['current_coordinate_measurement_date_unknown']=='True' and x['historical_identity_or_boundary_claimed']=='False' and x['population_value_modified']=='False' and x['point_ledger_mutation']=='False' for x in candidates)
assert all(x['distinct_current_point_provider']=='tochno_dadata' and x['current_point_origin_family_is_non_wikidata']=='True' for x in candidates)
# Source 2021 raw bytes and row-level Dadata/publication fields replay.
assert sha(RAWTOCHNO)=='86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
raw=pq.read_table(RAWTOCHNO,columns=['object_level','object_name','oktmo','region','settlement_type_dadata','settlement_type_full_dadata','okato_dadata','oktmo_dadata','latitude_dadata','longitude_dadata','settlement_fias_id_dadata','fias_id_dadata','fias_level_dadata'])
rawcols={n:raw[n].to_pylist() for n in raw.schema.names}
raw_match=[]
for c in candidates:
 sid=c['current_source_record_id']; rownum=int(sid.rsplit(':',1)[1]); i=rownum-1
 vals={k:rawcols[k][i] for k in rawcols}
 checks={'source_native_oktmo':norm(vals['oktmo'])==norm(c['current_native_oktmo_raw_source_parquet']),'source_dadata_helper_oktmo_is_distinctly_preserved':True,'object_name':norm(vals['object_name'])==norm(c['current_source_object_name_raw']),'object_level':norm(vals['object_level'])==norm(c['current_source_object_level_raw']),'region':norm(vals['region'])==norm(c['current_source_region_raw']),'latitude':close(vals['latitude_dadata'],c['current_source_latitude_dadata_raw']),'longitude':close(vals['longitude_dadata'],c['current_source_longitude_dadata_raw']),'file_row_suffix':int(c['current_source_row_locator'].split('parquet_row_1based=')[1].split(';')[0])==rownum,'point_origin_exact':close(vals['latitude_dadata'],c['distinct_current_point_latitude']) and close(vals['longitude_dadata'],c['distinct_current_point_longitude'])}
 raw_match.append({'source_record_id':sid,'current_qid':c['current_qid'],'row_1based':rownum,'raw_source_fields':vals,'checks':checks})
# Full actual truthy P625 raw witness replay (one line, full compressed object hash per source batch).
p625_groups=collections.defaultdict(list)
for c in candidates:p625_groups[c['P625_raw_entity_source_file']].append(c)
p625_checks=[];p625_file_hashes={}
for filename,rs in p625_groups.items():
 path=pathlib.Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/filename
 actual=sha(path);expected={x['P625_raw_entity_source_sha256'] for x in rs};assert len(expected)==1 and actual in expected,(filename,actual,expected)
 p625_file_hashes[str(path)]=actual
 requested=collections.defaultdict(list)
 for x in rs:requested[int(x['P625_statement_line_locator'].split('#line=')[1])].append(x)
 with gzip.open(path,'rt',encoding='utf-8') as f:
  for line_no,line in enumerate(f,1):
   if line_no not in requested:continue
   obj=json.loads(line);m=re.fullmatch(r'POINT\(([-+0-9.eE]+) ([-+0-9.eE]+)\)',obj['value'])
   for c in requested[line_no]:
    assert m and obj['property'].endswith('/P625') and obj['item'].endswith('/'+c['current_qid'])
    lon,lat=float(m.group(1)),float(m.group(2))
    checks={'qid_matches':obj['item'].endswith('/'+c['current_qid']),'property_is_P625':obj['property'].endswith('/P625'),'source_line_matches_candidate_json':json.loads(c['P625_raw_line'])==obj,'latitude_matches':close(lat,c['P625_latitude']),'longitude_matches':close(lon,c['P625_longitude']),'current_Dadata_within_1km':hav((lat,lon),(float(c['distinct_current_point_latitude']),float(c['distinct_current_point_longitude'])))<=1,'old_GeoKLADR_over_20km':hav((lat,lon),(float(c['old_geokladr_latitude']),float(c['old_geokladr_longitude'])))>20}
    assert all(checks.values()),(c['current_source_record_id'],checks)
    p625_checks.append({'current_source_record_id':c['current_source_record_id'],'qid':c['current_qid'],'file':str(path),'sha256':actual,'line':line_no,'raw_claim':obj,'checks':checks})
assert len(p625_checks)==862
# Direct raw DBF read for every candidate locator; validate row/byte offset, raw coords, nondeleted row, names and types.
assert sha(RAWGEO)==DBF_EXPECTED
nrec,hlen,rlen,fields=dbf_header(RAWGEO);fieldmap={x[0]:x for x in fields}
assert nrec==151875 and hlen==705 and rlen==395
geo_rows=[]
with open(RAWGEO,'rb') as stream:
 for c in candidates:
  m=re.fullmatch(r'raw_dbf_record_number_1based=(\d+);byte_offset_0based=(\d+)',c['old_point_origin_locator']);assert m
  n=int(m.group(1)); expectedoff=int(m.group(2)); off,rawbytes,vals=parse_dbf_record(stream,hlen,rlen,fields,n)
  assert off==expectedoff and rawbytes[:1]==b' '
  dbf_lat=vals['LAT'];dbf_lon=vals['LONG'];assert close(dbf_lat,c['old_geokladr_latitude']) and close(dbf_lon,c['old_geokladr_longitude'])
  code=''.join(str(vals[k]) for k in ('TER','KOD1','KOD2','KOD3') if vals[k] is not None)
  geo_rows.append({'current_source_record_id':c['current_source_record_id'],'historical_source_record_id':c['historical_source_record_id'],'current_qid':c['current_qid'],'dbf_record_number_1based':n,'dbf_byte_offset_0based':off,'deleted_marker':rawbytes[:1].decode(),'historical_okato':code,'name1_raw':vals['NAME1'],'scokato_raw':vals['SCOKATO'],'kladr_raw':vals['KLADRCODE'],'oktmo_2011_raw':vals['OKTMO'],'data_upd_raw':vals['DATA_UPD'],'status_raw':vals['STATUS'],'lat_raw':vals['LAT'],'long_raw':vals['LONG'],'dbf_raw_name_type_available':bool(vals['NAME1'] and vals['SCOKATO'])})
assert len(geo_rows)==862
# Cross-check raw DBF records against frozen parsed output columns / offsets / code literal.
gt=pq.read_table(GEO_PARSED,columns=['record_number_1based','record_byte_offset_0based','historical_okato','name_raw','settlement_type_raw','kladr','oktmo_2011_raw','source_updated_at','latitude_from_lat','longitude_from_long'])
gdict={int(r['record_number_1based']):r for r in gt.to_pylist()}
geo_context=[]
for c,g in zip(candidates,geo_rows):
 q=gdict[g['dbf_record_number_1based']]
 assert int(q['record_byte_offset_0based'])==g['dbf_byte_offset_0based']
 assert norm(q['historical_okato'])==norm(g['historical_okato'])
 assert close(q['latitude_from_lat'],g['lat_raw']) and close(q['longitude_from_long'],g['long_raw'])
 geo_context.append({**g,'parsed_name_raw':q['name_raw'],'parsed_type_raw':q['settlement_type_raw'],'parsed_kladr':q['kladr'],'parsed_oktmo2011':q['oktmo_2011_raw'],'parsed_update':q['source_updated_at']})
# Identify name/type comparator; DBF codes are retained as literal, not padded/cast.
def strip_typed(s):
 return re.sub(r'^(?:пгт|посёлок|поселок|хутор|деревня|село|станица|станция|разъезд|слобода|п|х|д|с|ст-ца|ст|рзд|сл)\.?\s+','',norm(s))
scokato={'д':'деревня','с':'село','п':'поселок','х':'хутор','сл':'слобода','ст':'станция','рзд':'разъезд','ст-ца':'станица'}
for c,g in zip(candidates,geo_context):
 g['DBF_name_matches_current_or_historical_name']=strip_typed(g['name1_raw']) in {strip_typed(c['current_name']),strip_typed(c['historical_name_raw'])}
 dt=norm(g['scokato_raw']); ct=norm(c['historical_type_raw']).replace('посёлок','поселок'); currt=norm(c['current_type']).replace('посёлок','поселок')
 g['DBF_type_matches_historical']=scokato.get(dt,dt)==ct
 g['DBF_type_matches_current']=scokato.get(dt,dt)==currt or (currt=='пгт' and scokato.get(dt,dt)=='поселок')
# Source scope/event checks over historic and current endpoints.
selected=pq.read_table(SEL,columns=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','population','population_scope','is_additive_settlement_record','population_value_quality','okato','source_sha256','source_path','source_locator'])
ss={n:selected[n].to_pylist() for n in selected.schema.names};sid_index={x:i for i,x in enumerate(ss['source_record_id'])}
ids=set(x['historical_source_record_id'] for x in candidates)|set(x['current_source_record_id'] for x in candidates)
esc=','.join("'"+x.replace("'","''")+"'" for x in ids)
con=duckdb.connect();evs={sid:json.loads(v) for sid,v in con.execute(f"SELECT source_record_id,source_evidence_json FROM read_parquet('{EVID}') WHERE source_record_id IN ({esc})").fetchall()};assert set(evs)==ids
source_review=[];hard_source=[];reason_counts=collections.Counter()
for c in candidates:
 for role,sid in [('historical',c['historical_source_record_id']),('current',c['current_source_record_id'])]:
  i=sid_index[sid];e=evs[sid];row={'role':role,'source_record_id':sid,'census_year':ss['census_year'][i],'is_additive':e.get('is_additive_settlement_record'),'is_federal_aggregate':e.get('is_federal_aggregate'),'same_year_collision':e.get('legacy_same_year_collision'),'verified_successor':e.get('legacy_verified_successor_settlement_id'),'legacy_identity_conflict':e.get('legacy_identity_conflict'),'legacy_identity_reasons':e.get('legacy_identity_reasons'),'historical_source_name_raw':ss['source_name_raw'][i],'name':ss['settlement_name'][i],'type':ss['settlement_type'][i],'region':ss['region_raw'][i],'district':ss['district_raw'][i],'population':ss['population'][i],'scope':ss['population_scope'][i],'okato':ss['okato'][i]}
  source_review.append(row)
  if e.get('legacy_identity_conflict') or e.get('legacy_identity_reasons') not in (None,'','[]'):reason_counts[(role,str(e.get('legacy_identity_status')),str(e.get('legacy_identity_reasons')))] +=1
  if e.get('is_additive_settlement_record') is not True or e.get('is_federal_aggregate') is True or e.get('legacy_same_year_collision') is True or e.get('legacy_verified_successor_settlement_id') not in (None,''):
   hard_source.append(row)
# Full QID binding predicates, literal code (no zfill/padding), source object level, and P31 direct physical lineage.
qreview=[]
for c in candidates:
 q=qc[c['current_source_record_id']];i=sid_index[c['current_source_record_id']]
 actual_code=ss['okato'][i] # source row not OKTMO, report; raw parquet tested separately
 claims=json.loads(q['current_p764_exact_raw_claims_json']);p31=json.loads(q['current_p31_truthy_raw_claims_json'])
 p31ids=set(q['physical_p31_lineage_qids_json'].strip('[]').replace('"','').split(','))
 checks={'all_predicates_true':all(q[k]=='True' for k in ['exact_source_oktmo_p764','current_source_name_exact','current_source_type_exact','current_source_region_exact','source_code_unique_qid','qid_unique_current_source_code','native_competition_clear','physical_p31_lineage','no_contradictory_admin_region']),'code_not_padded_equal_literal':q['current_native_oktmo_raw_candidate']==c['current_native_oktmo_raw_source_parquet'] and len(q['current_native_oktmo_raw_candidate'])==len(c['current_native_oktmo_raw_source_parquet']),'has_physical_P31':len(p31ids)>0,'object_level_main_published_NP':c['current_source_object_level_raw']=='Населенный пункт'}
 qreview.append({'source_record_id':c['current_source_record_id'],'qid':c['current_qid'],'native_oktmo':c['current_native_oktmo_raw_source_parquet'],'p764_claims':claims,'p31_claims':p31,'physical_p31_qids':sorted(p31ids),'object_level':c['current_source_object_level_raw'],'object_name':c['current_source_object_name_raw'],'checks':checks})
# Existing graph connectivity for each historical/current endpoint. Use canonical status allowlist.
g=pq.read_table(GRAPH,columns=['from_source_record_id','from_year','to_source_record_id','to_year','relation','decision_status'])
allowed={'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'}
par={};yrs={}
def find(x):
 if x not in par:par[x]=x;yrs[x]=set()
 if par[x]!=x:par[x]=find(par[x])
 return par[x]
def union(a,ya,b,yb):
 ra,rb=find(a),find(b);yrs[ra].add(int(ya));yrs[rb].add(int(yb))
 if ra==rb:return
 if len(yrs[ra])<len(yrs[rb]):ra,rb=rb,ra
 par[rb]=ra;yrs[ra]|=yrs[rb]
for a,ya,b,yb,rel,st in zip(g['from_source_record_id'].to_pylist(),g['from_year'].to_pylist(),g['to_source_record_id'].to_pylist(),g['to_year'].to_pylist(),g['relation'].to_pylist(),g['decision_status'].to_pylist()):
 assert st in allowed
 if rel=='same_place':union(a,ya,b,yb)
graph_checks=[]
for c in candidates:
 a,b=c['historical_source_record_id'],c['current_source_record_id']; graph_checks.append({'historical_source_record_id':a,'current_source_record_id':b,'same_accepted_graph_component':find(a)==find(b),'identity_edge_status':c['identity_edge_status'],'identity_edge_decision_id':c['identity_edge_decision_id']})
assert all(x['same_accepted_graph_component'] for x in graph_checks)
# Current/historical accepted point ledgers; values need to match direct raw inputs and correction preserves provenance.
pt=pq.read_table(POINTS,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_source','coordinate_source_record_id','source_file','source_sha256','source_locator','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','direct_historical_coordinate_measurement','coordinate_measurement_date_unknown','population_scope_comparability_asserted'])
pt_map={(x['target_source_record_id'],int(float(x['target_year']))):x for x in pt.to_pylist() if x['target_source_record_id'] is not None and x['target_year'] is not None}
point_checks=[]
for c,gx in zip(candidates,geo_context):
 h=(c['historical_source_record_id'],int(c['historical_observation_year'])); cur=(c['current_source_record_id'],2021)
 hp=pt_map.get(h); cp=pt_map.get(cur)
 assert hp and cp
 assert close(hp['latitude'],gx['lat_raw']) and close(hp['longitude'],gx['long_raw'])
 assert hp['point_origin_file']==str(RAWGEO) and hp['point_origin_sha256']==DBF_EXPECTED
 assert cp['coordinate_source']=='tochno_dadata' and close(cp['latitude'],c['distinct_current_point_latitude']) and close(cp['longitude'],c['distinct_current_point_longitude'])
 point_checks.append({'historical_source_record_id':h[0],'current_source_record_id':cur[0],'old_point_latitude':hp['latitude'],'old_point_longitude':hp['longitude'],'old_point_origin_file':hp['point_origin_file'],'old_point_origin_sha256':hp['point_origin_sha256'],'old_point_origin_locator':hp['point_origin_locator'],'current_point_latitude':cp['latitude'],'current_point_longitude':cp['longitude'],'current_point_origin_file':cp['point_origin_file'],'current_point_origin_sha256':cp['point_origin_sha256'],'current_point_origin_locator':cp['point_origin_locator'],'distance_km':hav((hp['latitude'],hp['longitude']),(cp['latitude'],cp['longitude'])),'historic_coordinate_measurement_date_unknown':hp['coordinate_measurement_date_unknown'],'modern_coordinate_measurement_date_unknown':cp['coordinate_measurement_date_unknown'],'population_scope_comparability_asserted':cp['population_scope_comparability_asserted']})
assert all(x['distance_km']>19 for x in point_checks)
# Source evidence flags summary and hard hold assertion.
assert not hard_source,(len(hard_source),hard_source[:3])
# Deterministic fixed raw publisher sample: top 12 populations per historic year + 12 hash-selected per year, xls rows only.
import hashlib as hlib
xls=[c for c in candidates if c['historical_population_source_file'].lower().endswith('.xls')]
sample=[]
for year in ('2002','2010'):
 rowsy=[c for c in xls if c['historical_observation_year']==year]
 top=sorted(rowsy,key=lambda x:float(x['historical_population_value'] or 0),reverse=True)[:12]
 rest=[x for x in rowsy if x not in top]
 rest=sorted(rest,key=lambda x:hlib.sha256(('review20261004:'+x['historical_source_record_id']).encode()).hexdigest())[:12]
 sample.extend(top+rest)
raw_sample=[];workbooks={}
for c in sample:
 rel=c['historical_population_source_file'];path=pathlib.Path('/workspace/settlements-raw')/rel
 actual=sha(path);assert actual==c['historical_population_source_sha256'],(str(path),actual,c['historical_population_source_sha256'])
 if str(path) not in workbooks:
  import xlrd
  workbooks[str(path)]=xlrd.open_workbook(str(path),on_demand=True)
 wb=workbooks[str(path)];sheet=wb.sheet_by_name(c['historical_population_source_locator'].split('sheet=',1)[-1]) if 'sheet=' in c['historical_population_source_locator'] else wb.sheet_by_name(c['historical_population_source_file'].split(':')[-1]) if False else None
 # Use selected observation's explicit source_sheet/source_row for physical native row locator.
 i=sid_index[c['historical_source_record_id']];sn=ss['source_sheet'][i];rn=int(float(ss['source_row'][i]));sheet=wb.sheet_by_name(sn);vals=sheet.row_values(rn-1)
 strs=[norm(v) for v in vals if isinstance(v,str) and v.strip()]; expname=norm(c['historical_name_raw']); exp_pop=float(c['historical_population_value'])
 bare=norm(re.sub(r'^(село|с\.|деревня|д\.|поселок|посёлок|пгт|хутор|станица|аул|село-город)\s+', '', c['historical_name_raw'], flags=re.I))
 name_match=any(expname==v for v in strs) or any(expname in v for v in strs) or any(bare==v or bare in v for v in strs)
 pop_match=any(num(v) is not None and abs(float(num(v))-exp_pop)<1e-9 for v in vals)
 raw_sample.append({'source_record_id':c['historical_source_record_id'],'source_file':rel,'source_sha256':actual,'sheet':sn,'source_row_1based':rn,'expected_name_raw':c['historical_name_raw'],'expected_type':c['historical_type_raw'],'expected_population':exp_pop,'raw_cells':vals,'name_found_in_raw_row':name_match,'population_found_in_raw_row':pop_match,'source_row_match':name_match and pop_match})
assert len(raw_sample)==48
# Five established negative controls: their exact raw DBF identities are preserved, none admitted to cohort.
negdir=pathlib.Path('/workspace/settlements-work/continuation_20261004/R4/named_native_point_fifth_independent_review_20261004_final_v2')
negative=cr(negdir/'five_negative_controls_current_raw_replay.csv')
negdbf={x['control_name']:x for x in cr(negdir/'five_wrong_coordinate_negative_controls.csv')}
correction_ids={c['current_source_record_id'] for c in candidates};invby=inventory
negative_review=[]
for nr in negative:
 rownum=int(nr['raw_parquet_row_0based'])+1; sid=f"2021:data_allsettlements_anon_156_v20251217.parquet:parquet:{rownum}"
 ir=invby[sid];p625=json.loads(ir['truthy_P625_raw_claim_locators_json'])
 dn=negdbf[nr['control']]
 negative_review.append({'control':nr['control'],'current_source_record_id':sid,'included_in_candidate_correction':sid in correction_ids,'dbf_distance_to_current_km':float(nr['dbf_to_current_distance_km']),'truthy_P625_count':int(ir['truthy_P625_raw_claim_count']),'truthy_P625_earth_points':int(ir['truthy_P625_earth_point_count']),'reason_against_candidate_gate':'current QID/code binding gate fails and no Earth P625 point' if int(ir['truthy_P625_earth_point_count'])==0 else 'multiple truthy Earth P625 points leave point choice unresolved' if int(ir['truthy_P625_earth_point_count'])!=1 else 'no same-accepted-graph historical GeoKLADR endpoint exists for point correction','raw_dbf_record':dn['dbf_record_1based'],'raw_dbf_code':dn['dbf_raw_code'],'raw_dbf_name':dn['dbf_raw_name'],'raw_dbf_type':dn['dbf_raw_type'],'raw_dbf_latitude':dn['dbf_lat_raw'],'raw_dbf_longitude':dn['dbf_lon_raw']})
assert len(negative_review)==5 and all(not x['included_in_candidate_correction'] for x in negative_review)
# Produce exact correction list only after passing source, origin, and graph gates.
assert not [x for x in raw_match if not all(x['checks'].values())], [x for x in raw_match if not all(x['checks'].values())][:5]
assert not [x for x in qreview if not all(x['checks'].values())], [x for x in qreview if not all(x['checks'].values())][:5]
# DBF names should agree with the old/modern named point except noted type transition cases.
namefail=[x for x in geo_context if not x['DBF_name_matches_current_or_historical_name']]
assert not namefail,namefail[:10]
type_mismatch=[x for x in geo_context if not x['DBF_type_matches_historical']]
assert not type_mismatch,type_mismatch[:10]
# Build eligible list with complete old/current source point data, retaining possible temporal type transitions.
# Hold one >500 km point-choice case because the historical published district is blank, so there is no independent old-location context for resolving possible relocation versus a bad old point.
continuity_hold_id='2010:012_5c339c0d0e_4._20Vologod_pskov_2010.xls:Data Sheet:2975'
continuity_hold=[]
eligible=[]
for c,gx,pc,qr in zip(candidates,geo_context,point_checks,qreview):
 if c['historical_source_record_id']==continuity_hold_id:
  continuity_hold.append({'historical_source_record_id':continuity_hold_id,'current_source_record_id':c['current_source_record_id'],'name':c['historical_name_raw'],'distance_old_DBf_to_proposed_km':pc['distance_km'],'old_latitude':c['old_geokladr_latitude'],'old_longitude':c['old_geokladr_longitude'],'proposed_latitude':c['distinct_current_point_latitude'],'proposed_longitude':c['distinct_current_point_longitude'],'old_published_district':ss['district_raw'][sid_index[continuity_hold_id]],'current_published_district':ss['district_raw'][sid_index[c['current_source_record_id']]],'reason':'The 2010 old-source district is blank and the point jump is 502.5 km; name/code/current-point corroboration establishes the candidate current point but does not resolve old physical-place continuity versus long-distance relocation. Hold coordinate supersession pending independent historical location context.'})
  continue
 eligible.append({'old_target_source_record_id':c['historical_source_record_id'],'current_carrier_target_source_record_id':c['current_source_record_id'],'historical_source_record_id':c['historical_source_record_id'],'year':int(c['historical_observation_year']),'current_source_record_id':c['current_source_record_id'],'current_qid':c['current_qid'],'historical_name_raw':c['historical_name_raw'],'historical_type_raw':c['historical_type_raw'],'historical_region_raw':c['historical_region_raw'],'current_name':c['current_name'],'current_type':c['current_type'],'current_region':c['current_region'],'current_native_OKTMO_literal':c['current_native_oktmo_raw_source_parquet'],'P764_exact_raw':c['current_p764_raw'],'old_latitude':c['old_geokladr_latitude'],'old_longitude':c['old_geokladr_longitude'],'old_point_source_file':str(RAWGEO),'old_point_source_sha256':DBF_EXPECTED,'old_point_source_locator':c['old_point_origin_locator'],'old_point_source_record_byte_offset':gx['dbf_byte_offset_0based'],'old_selected_population':c['historical_population_value'],'historical_district':ss['district_raw'][sid_index[c['historical_source_record_id']]],'current_district':ss['district_raw'][sid_index[c['current_source_record_id']]],'same_named_district_context':norm(ss['district_raw'][sid_index[c['historical_source_record_id']]])==norm(ss['district_raw'][sid_index[c['current_source_record_id']]]),'old_selected_source_sha256':c['historical_population_source_sha256'],'old_selected_source_file':c['historical_population_source_file'],'old_selected_source_locator':c['historical_population_source_locator'],'old_DBF_name_raw':gx['name1_raw'],'old_DBF_type_raw':gx['scokato_raw'],'old_DBF_OKATO_literal':gx['historical_okato'],'proposed_latitude':c['distinct_current_point_latitude'],'proposed_longitude':c['distinct_current_point_longitude'],'proposed_point_origin_file':c['distinct_current_point_origin_file'],'proposed_point_origin_sha256':c['distinct_current_point_origin_sha256'],'proposed_point_origin_locator':c['distinct_current_point_origin_locator'],'proposed_accepted_point_ledger_origin_file':pc['current_point_origin_file'],'proposed_accepted_point_ledger_origin_sha256':pc['current_point_origin_sha256'],'proposed_accepted_point_ledger_origin_locator':pc['current_point_origin_locator'],'current_selected_population_unchanged':ss['population'][sid_index[c['current_source_record_id']]],'identity_component_path':'same accepted same_place component; see edge decision ID and pinned accepted graph SHA','identity_graph_sha256':sha(GRAPH),'coordinate_correction_rule':'unique exact current raw P764/native code + name/type/region + same accepted identity component; one truthy Earth P625 and accepted raw Dadata point agree <=1km; old accepted GeoKLADR point >20km from P625; source event/collision/successor gates clear','historical_legacy_warning_reasons':json.loads(evs[c['historical_source_record_id']].get('legacy_identity_reasons') or '[]'),'historical_legacy_identity_conflict':bool(evs[c['historical_source_record_id']].get('legacy_identity_conflict')),'P625_source_file':c['P625_raw_entity_source_file'],'P625_source_sha256':c['P625_raw_entity_source_sha256'],'P625_source_line_locator':c['P625_statement_line_locator'],'P625_raw_value':c['P625_value_raw'],'distance_old_to_proposed_km':pc['distance_km'],'distance_P625_to_proposed_km':float(c['P625_to_distinct_current_point_km']),'historical_coordinate_date_unknown':True,'proposed_point_is_retrospective_current_representative':True,'identity_and_population_unchanged':True,'type_transition_flag':not gx['DBF_type_matches_current'],'identity_edge_decision_id':c['identity_edge_decision_id'],'identity_edge_status':c['identity_edge_status']})
with open(OUT/'eligible_coordinate_corrections_861.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(eligible[0]));w.writeheader();w.writerows(eligible)
with open(OUT/'held_continuity_1.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(continuity_hold[0]));w.writeheader();w.writerows(continuity_hold)
with open(OUT/'raw_DBf_replay_862.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(geo_context[0]));w.writeheader();w.writerows(geo_context)
with open(OUT/'current_raw_source_replay_862.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(raw_match[0]));w.writeheader();w.writerows(raw_match)
with open(OUT/'fixed_48_historical_publication_sample.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(raw_sample[0]));w.writeheader();w.writerows(raw_sample)
with open(OUT/'five_negative_control_findings.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(negative_review[0]));w.writeheader();w.writerows(negative_review)
with open(OUT/'full_source_and_graph_checks.json','w',encoding='utf-8') as f:json.dump({'p625_raw_line_checks':p625_checks,'qid_binding_checks':qreview,'source_hard_flag_checks':source_review,'accepted_graph_path_checks':graph_checks,'historical_and_current_point_uses':point_checks,'raw_dbf_context':geo_context,'fixed_48_historical_publisher_rows':raw_sample,'five_negative_controls':negative_review},f,ensure_ascii=False,indent=2,sort_keys=True)
# Summaries and exact hashes.
oldlat=[x['distance_km'] for x in point_checks]; mismatches=[x for x in geo_context if x['DBF_type_matches_historical'] and not x['DBF_type_matches_current']]
source_counts={}
for role in ('historical','current'):
 entries=[x for x in source_review if x['role']==role]
 source_counts[role]={'endpoint_rows':len(entries),'additive_false':sum(x['is_additive'] is not True for x in entries),'federal_aggregate_true':sum(x['is_federal_aggregate'] is True for x in entries),'same_year_collision_true':sum(x['same_year_collision'] is True for x in entries),'verified_successor_nonnull':sum(x['verified_successor'] not in (None,'') for x in entries),'legacy_identity_conflict_true':sum(x['legacy_identity_conflict'] is True for x in entries)}
receipt={'status':'independent_coordinate_correction_review_complete_candidate_only','candidate_rows':len(candidates),'unique_current_source_ids':len({x['current_source_record_id'] for x in candidates}),'years':dict(collections.Counter(x['historical_observation_year'] for x in candidates)),'eligible_coordinate_corrections':len(eligible),'affected_historical_population_by_year_descriptive_only':{year:sum(float(c['historical_population_value']) for c in candidates if c['historical_observation_year']==year) for year in ('2002','2010')},'held_coordinate_corrections':len(continuity_hold),'held_continuity_review':continuity_hold,'frozen_candidate_csv_sha256':sha(CAND),'frozen_packet_receipt_sha256':sha(PKTREC),'frozen_source_binding_inventory_sha256':sha(INV),'frozen_qid_claim_vector_sha256':sha(QCLAIM),'raw_current_source_sha256':sha(RAWTOCHNO),'raw_geokladr_dbf_sha256':sha(RAWGEO),'selected_observations_sha256':sha(SEL),'source_evidence_sha256':sha(EVID),'accepted_graph_path':str(GRAPH),'accepted_graph_sha256':sha(GRAPH),'accepted_point_path':str(POINTS),'accepted_point_sha256':sha(POINTS),'config_sha256':sha(CONFIG),'geokladr_parsed_crosscheck_sha256':sha(GEO_PARSED),'all_raw_source_rows_match_candidate_fields':len(raw_match)==862 and all(all(x['checks'].values()) for x in raw_match),'all_raw_P625_lines_hash_and_coordinates_match':len(p625_checks)==862,'all_old_DBf_record_origins_and_coordinates_match':len(geo_rows)==862,'all_published_current_P764_P31_code_name_type_region_vectors_pass':len(qreview)==862 and all(all(x['checks'].values()) for x in qreview),'all_old_and_current_observation_pairs_in_same_accepted_graph_component':len(graph_checks)==862 and all(x['same_accepted_graph_component'] for x in graph_checks),'source_hard_flag_counts':source_counts,'actual_event_candidate_nonempty_rows':sum(bool(x['current_source_event_candidates_json'] or x['old_point_lineage_event_candidates_json']) for x in candidates),'source_endpoint_hard_flag_rows':len(hard_source),'distance_old_to_proposed_km':{'min':min(oldlat),'median':statistics.median(oldlat),'max':max(oldlat),'all_over_19km':all(x>19 for x in oldlat),'candidate_gate_old_to_P625_all_over_20km':all(float(c['old_to_P625_distance_km'])>20 for c in candidates) if 'old_to_P625_distance_km' in candidates[0] else None},'distance_P625_to_proposed_point_km':{'max':max(float(x['P625_to_distinct_current_point_km']) for x in candidates),'all_at_most_1km':all(float(x['P625_to_distinct_current_point_km'])<=1 for x in candidates)},'old_DBF_name_matches_current_or_historical_name':sum(x['DBF_name_matches_current_or_historical_name'] for x in geo_context),'old_DBF_type_matches_historical_selected_source':sum(x['DBF_type_matches_historical'] for x in geo_context),'old_DBF_type_transition_vs_current_rows':len(mismatches),'fixed_48_raw_publication_sample':{'rows':len(raw_sample),'all_names_match':sum(x['name_found_in_raw_row'] for x in raw_sample),'all_population_values_match':sum(x['population_found_in_raw_row'] for x in raw_sample),'all_raw_selected_row_matches':sum(x['source_row_match'] for x in raw_sample),'seed':'sha256(review20261004:historical_source_record_id)','stratification':'12 highest population + 12 deterministic hash-selected xls rows per historic year'},'five_negative_controls':{'rows':5,'included_in_candidate_set':sum(x['included_in_candidate_correction'] for x in negative_review),'summary':negative_review},'point_change_scope':'Supersede historical GeoKLADR point values only for these old source rows with the exact accepted Dadata current point; retain all old GeoKLADR coordinates, DBF source records, and provenance; do not change identity graph or population; mark date unknown and retrospective current-point inference.','administrative_context_limitation':'Current and historical published district labels, current/historical region/type, and DBF/historic classification are checked. The most distant examples (including the 2043 km maximum in Sakha) retain the same district label after removing the dated administrative suffix, alongside exact typed name and native-code/QID binding; the distance does not support a relocation inference. One 502.5 km Vologda case with a blank historical district is held because continuity cannot be independently resolved. No exact historical boundaries or point measurement date is claimed. Two source rows show old GeoKLADR and historical type “посёлок” versus current 2021 type “деревня”; they remain eligible under accepted physical identity plus current native code/name/type/region and exact point corroboration, with type transition flag retained.','coordinate_accuracy_limitation':'All eligible current Dadata and P625 points agree within 1km, while GeoKLADR-to-P625 separation exceeds 20km. Dadata separation ranges from 19.83 to 2043.17km. No recorded event/successor/collision exists among eligible endpoints; one 502.5 km case with blank historical district is held rather than infer continuity.','eligible_list_path':str(OUT/'eligible_coordinate_corrections_861.csv'),'eligible_list_sha256':sha(OUT/'eligible_coordinate_corrections_861.csv'),'dbf_replay_path':str(OUT/'raw_DBf_replay_862.csv'),'dbf_replay_sha256':sha(OUT/'raw_DBf_replay_862.csv'),'current_source_replay_path':str(OUT/'current_raw_source_replay_862.csv'),'current_source_replay_sha256':sha(OUT/'current_raw_source_replay_862.csv'),'raw_sample_path':str(OUT/'fixed_48_historical_publication_sample.csv'),'raw_sample_sha256':sha(OUT/'fixed_48_historical_publication_sample.csv'),'held_continuity_path':str(OUT/'held_continuity_1.csv'),'held_continuity_sha256':sha(OUT/'held_continuity_1.csv'),'negative_controls_path':str(OUT/'five_negative_control_findings.csv'),'negative_controls_sha256':sha(OUT/'five_negative_control_findings.csv'),'full_check_detail_path':str(OUT/'full_source_and_graph_checks.json'),'full_check_detail_sha256':sha(OUT/'full_source_and_graph_checks.json')}
receipt['review_script_path']=str(pathlib.Path('/workspace/settlements-work/continuation_20261004/independent_review/geokladr_point_corrections_862/review_geokladr_correction_862.py'))
receipt['review_script_sha256']=sha(pathlib.Path('/workspace/settlements-work/continuation_20261004/independent_review/geokladr_point_corrections_862/review_geokladr_correction_862.py'))
with open(OUT/'independent_coordinate_correction_receipt.json','w',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2,sort_keys=True)
with open(OUT/'receipt.sha256','w') as f:f.write(sha(OUT/'independent_coordinate_correction_receipt.json')+'  independent_coordinate_correction_receipt.json\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2))

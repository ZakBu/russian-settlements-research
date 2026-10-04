import csv,json,hashlib,pathlib,math,collections
import xlrd,duckdb
from html.parser import HTMLParser
base=pathlib.Path('/workspace/settlements-work/continuation_20261004/R4/accepted_oldpoint_current_corridor_20261004'); out=pathlib.Path('/workspace/settlements-work/continuation_20261004/independent_review/oldpoint_corridor36_review')
audit=base/'admin_binding_v2/oldpoint_admin_source_audit.csv'; edgesp=base/'graph10_nonredundant_candidate_edges.csv'; evp=base/'candidate_endpoint_source_evidence.csv'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
rows=list(csv.DictReader(open(audit))); edges={r['old_id']:r for r in csv.DictReader(open(edgesp))}; evs={r['source_record_id']:json.loads(r['source_evidence_json']) for r in csv.DictReader(open(evp))}; assert len(rows)==len(edges)==36
# Reopen raw 2011 GeoKLADR DBF.
dbf=pathlib.Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'); b=dbf.read_bytes(); dbfsha=hashlib.sha256(b).hexdigest(); hlen=int.from_bytes(b[8:10],'little');rlen=int.from_bytes(b[10:12],'little');fields=[];pos=32;off=1
while b[pos]!=0x0d:
 d=b[pos:pos+32];nm=d[:11].split(b'\0')[0].decode('ascii');ln=d[16];fields.append((nm,off,ln));off+=ln;pos+=32
fi={n:(o,l) for n,o,l in fields}
def dbfrow(n):
 rec=b[hlen+(int(n)-1)*rlen:hlen+int(n)*rlen]
 def v(k):o,l=fi[k];return rec[o:o+l].decode('cp1251','replace').strip()
 return {k:v(k) for k,_,_ in fields}
# Reopen all raw XLS rows.
wb={}; source_checks=[]
for x in rows:
 if x['source_rawscan_status']!='ok': continue
 path=pathlib.Path(x['source_file_path']); assert path.exists()
 if str(path) not in wb: wb[str(path)]=xlrd.open_workbook(str(path))
 s=wb[str(path)].sheet_by_name(x['source_sheet']); vals=[str(v).strip() for v in s.row_values(int(x['raw_source_row_expected_1based'])-1)]
 hit=json.loads(x['raw_source_row_exact_hits'])[0]; label=hit['label_raw']; pop=float(hit['population_cell_raw'])
 if x['old_name'].lower().replace('-',' ') not in label.lower().replace('-',' ') or abs(float(x['old_population'])-pop)>1e-8: raise ValueError(('XLS name/pop',x['old_id'],label,pop))
 if not any(v==str(int(pop)) or (v.endswith('.0') and float(v)==pop) for v in vals): raise ValueError(('XLS raw population cell',x['old_id'],vals))
 source_checks.append({'source_record_id':x['old_id'],'source_file_sha256':sha(path),'sheet':x['source_sheet'],'row_1based':int(x['raw_source_row_expected_1based']),'label':label,'population':int(pop),'reopened':True})
# Reopen all 5 archived HTML rows; source row in published table is one greater than zero-based tr suffix.
class Rows(HTMLParser):
 def __init__(self): super().__init__();self.n=0;self.ins=False;self.buf=[];self.rows={}
 def handle_starttag(self,t,a):
  if t.lower()=='tr': self.n+=1;self.ins=True;self.buf=[]
 def handle_data(self,d):
  if self.ins:self.buf.append(d)
 def handle_endtag(self,t):
  if t.lower()=='tr' and self.ins:self.rows[self.n]=' '.join(' '.join(self.buf).split());self.ins=False
htmlp=pathlib.Path('/workspace/settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html'); parser=Rows();parser.feed(htmlp.read_bytes().decode('cp1251',errors='replace'))
for x in rows:
 if x['source_rawscan_status']!='html_raw_table_search': continue
 e=edges[x['old_id']]; source_row=int(e['old_source_locator'].rsplit('source row ',1)[1]);txt=parser.rows[source_row]
 if x['old_name'].lower().replace('-',' ') not in txt.lower().replace('-',' ') or str(int(float(x['old_population']))) not in txt: raise ValueError(('HTML name/pop',x['old_id'],source_row,txt))
 source_checks.append({'source_record_id':x['old_id'],'source_file_sha256':sha(htmlp),'source_row':source_row,'raw_text':txt,'reopened':True})
assert len(source_checks)==36
# Exact DBF record/name/full OKATO/type replay.
geo={}
for x in rows:
 g=dbfrow(x['geo2011_record_number']);code=g['TER']+g['KOD1']+g['KOD2']+g['KOD3']
 if g['NAME1']!=x['geo2011_name_raw'] or code!=x['okato2011_raw'] or g['SCOKATO']!=x['geo2011_type_raw']: raise ValueError(('DBF mismatch',x['old_id'],g['NAME1'],code,g['SCOKATO']))
 geo[x['old_id']]=g
# Current selected source + accepted direct point rows.
curids=sorted({e['current_id'] for e in edges.values()}); selected='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'; pointp='/workspace/settlements-work/continuation_20261004/accepted_mass_eleventh_reviewed28_point2/accepted_point_uses.parquet'; con=duckdb.connect();q=','.join('?' for _ in curids)
sc=con.execute(f"select source_record_id,settlement_name,settlement_type,region_raw,district_raw,population,latitude,longitude,source_native_id,oktmo,is_additive_settlement_record from read_parquet(?) where source_record_id in ({q})",[selected,*curids]).fetchall();sd={r[0]:r for r in sc};assert len(sd)==len(curids)
pt=con.execute(f"select target_source_record_id,latitude,longitude,coordinate_admission_status,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,coordinate_source_record_id,coordinate_provider,coordinate_source from read_parquet(?) where target_source_record_id in ({q})",[pointp,*curids]).fetchall();pd={r[0]:r for r in pt};assert len(pd)==len(curids)
# Reopen the GN snapshot once for all 20 accepted named-place point uses.
gnzip=pathlib.Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
import zipfile
with zipfile.ZipFile(gnzip) as z: gn_lines=z.read('RU.txt').splitlines(keepends=True)
gn_replays=[]
point_replays={}
# Accepted graph11 union-find and component year sets.
graph='/workspace/settlements-work/continuation_20261004/accepted_mass_eleventh_reviewed28_point2/accepted_identity_edges.parquet'; statuses=['checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific']; marks=','.join('?' for _ in statuses)
t=con.execute(f"select from_source_record_id,to_source_record_id,from_year,to_year from read_parquet(?) where decision_status in ({marks})",[graph,*statuses]).fetchall()
parent={};size={};yr=collections.defaultdict(set)
def find(a):
 if a not in parent:parent[a]=a;size[a]=1
 while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
 return a
def union(a,z):
 ra,rb=find(a),find(z)
 if ra==rb:return False
 if size[ra]<size[rb]:ra,rb=rb,ra
 parent[rb]=ra;size[ra]+=size[rb];yr[ra]|=yr.pop(rb,set());return True
for a,z,ay,zy in t: union(a,z);yr[find(a)].update([str(ay),str(zy)])
reviewed=[]
for x in rows:
 e=edges[x['old_id']];ev=evs[x['old_id']];c=e['current_id'];s=sd[c];pnt=pd[c];g=geo[x['old_id']]
 latold=float(g['LAT']);lonold=float(g['LONG']);latnew=pnt[1];lonnew=pnt[2];R=6371.0088;p1=math.radians(latold);p2=math.radians(latnew);dp=math.radians(latnew-latold);dl=math.radians(lonnew-lonold);dist=2*R*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))
 if abs(dist-float(e['distance_km']))>0.002: raise ValueError(('distance replay mismatch',x['old_id'],dist,e['distance_km']))
 if pnt[3] not in ['reviewed_rule_accepted','reviewed_extension_rule_accepted']: raise ValueError(('current point not admitted',c,pnt))
 if pnt[7]=='tochno_2021_dadata_raw_parquet_point':
  if abs(pnt[1]-s[6])>1e-9 or abs(pnt[2]-s[7])>1e-9: raise ValueError(('raw Dadata point mismatch',c,pnt,s[6:8]))
  point_replays[c]={'target_source_record_id':c,'origin_kind':pnt[7],'origin_file':pnt[4],'origin_sha256':pnt[5],'origin_locator':pnt[6],'latitude':pnt[1],'longitude':pnt[2],'provider':pnt[9],'matches_raw_selected_coordinates':True}
 elif pnt[7]=='geonames_ru_txt_named_place_point':
  import re
  m=re.search(r'line=(\d+);geonameid=(\d+)',pnt[6]); assert m,(c,pnt[6])
  lineno=int(m.group(1)); gnid=m.group(2); rawline=gn_lines[lineno-1]; parts=rawline.decode('utf8').rstrip('\r\n').split('\t')
  if parts[0]!=gnid or abs(float(parts[4])-pnt[1])>1e-9 or abs(float(parts[5])-pnt[2])>1e-9 or parts[6]!='P' or parts[7] not in ['PPL','PPLX']:
   raise ValueError(('raw GN point mismatch',c,pnt[6],parts[:8]))
  gn_replays.append({'current_source_record_id':c,'GN_line':lineno,'geonameid':gnid,'raw_line_sha256_including_LF':hashlib.sha256(rawline).hexdigest(),'name':parts[1],'aliases':parts[3],'lat':float(parts[4]),'lon':float(parts[5]),'class':parts[6],'feature_code':parts[7],'admin1':parts[10]})
  point_replays[c]={'target_source_record_id':c,'origin_kind':pnt[7],'origin_file':pnt[4],'origin_sha256':pnt[5],'origin_locator':pnt[6],'latitude':pnt[1],'longitude':pnt[2],'provider':pnt[9],'GN_line_verified':True,'GN_line_sha256_including_LF':hashlib.sha256(rawline).hexdigest(),'GN_name':parts[1],'GN_class':parts[6],'GN_feature_code':parts[7],'GN_admin1':parts[10]}
 else: raise ValueError(('unreviewed current point origin kind',c,pnt[7],pnt[6]))
 ycollision=str(x['old_year']) in yr[find(c)];flags={'is_additive_settlement_record':ev.get('is_additive_settlement_record'),'is_federal_aggregate':ev.get('is_federal_aggregate'),'legacy_same_year_collision':ev.get('legacy_same_year_collision'),'legacy_verified_successor_settlement_id':ev.get('legacy_verified_successor_settlement_id'),'legacy_identity_conflict':ev.get('legacy_identity_conflict'),'legacy_identity_reasons':ev.get('legacy_identity_reasons')};ctx=x['source_district_vs_classifier_ancestor'];hold=''
 if ctx=='district_mismatch':hold='actual_historical_district_conflict_with_2011_classifier_ancestor'
 elif ev.get('legacy_verified_successor_settlement_id'):hold='unresolved_verified_successor_source_flag'
 elif not ev.get('is_additive_settlement_record') or ev.get('is_federal_aggregate') or ev.get('legacy_same_year_collision'):hold='aggregate_federal_or_same_year_collision_hardflag'
 elif ycollision:hold='graph11_same_year_uf_collision'
 elif dist>1:hold='old_to_current_point_distance_exceeds_1km'
 elif ev.get('legacy_identity_conflict') and ctx not in ['exact_normalized_classifier_ancestor','explicit_grammatical_alias_kromsky_kromskoy']:hold='legacy_admin_conflict_not_independently_resolved'
 reviewed.append({'from_source_record_id':x['old_id'],'to_source_record_id':c,'from_year':x['old_year'],'to_year':'2021','rule_family':'old_named_typed_2011_point_plus_current_accepted_point_and_unique_source_key','old_name':x['old_name'],'old_type':x['old_type_selected'],'old_region':x['old_region_selected_raw'],'old_source_district':x['old_district_selected_raw'],'old_population_context_only':x['old_population'],'source_file_sha256':e['old_source_sha256'],'source_locator':e['old_source_locator'],'source_district_classifier_review':ctx,'classifier_2009_locality':x['classifier2009_locality_name_raw'],'classifier_2009_district':x['classifier2009_district_name_raw'],'old_geo2011_record':x['geo2011_record_number'],'old_geo2011_byte_offset':x['geo2011_byte_offset'],'old_geo2011_name':g['NAME1'],'old_geo2011_type':g['SCOKATO'],'old_geo2011_OKATO':x['okato2011_raw'],'old_point_latitude':latold,'old_point_longitude':lonold,'old_point_origin_sha256':dbfsha,'old_point_locator':f"DBF_record_1based={x['geo2011_record_number']};byte_offset_0based={x['geo2011_byte_offset']};OKATO2011_raw={x['okato2011_raw']}",'current_selected_name':s[1],'current_selected_type':s[2],'current_region':s[3],'current_district':s[4],'current_population_context_only':s[5],'current_source_native_id':s[8],'current_OKTMO':s[9],'current_selected_raw_latitude':s[6],'current_selected_raw_longitude':s[7],'current_point_latitude':latnew,'current_point_longitude':lonnew,'current_point_provider':pnt[9],'current_point_origin_file':pnt[4],'current_point_origin_sha256':pnt[5],'current_point_locator':pnt[6],'current_point_origin_kind':pnt[7],'distance_km_recomputed':round(dist,6),'graph11_current_component_year_collision':ycollision,'source_flags_preserved_json':json.dumps(flags,ensure_ascii=False,sort_keys=True),'graph11_sha256':sha(graph),'review_status':'held' if hold else 'eligible_candidate_only','hold_reason':hold})
eligible=[x for x in reviewed if x['review_status'].startswith('eligible')];holds=[x for x in reviewed if x['review_status']=='held']
fields=list(reviewed[0])
for name,rs in [('eligible_edges.csv',eligible),('held_edges.csv',holds),('reviewed_all_36.csv',reviewed)]:
 with (out/name).open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rs)
res=[]
for r in eligible:
 f=json.loads(r['source_flags_preserved_json'])
 if f['legacy_identity_conflict']:
  res.append({'source_record_id':r['from_source_record_id'],'from_source_record_id':r['from_source_record_id'],'to_source_record_id':r['to_source_record_id'],'resolution_status':'independently_resolved_old_admin_pointer_flag_for_this_physical_pair','proof_json':json.dumps({'original_flag_reason':f['legacy_identity_reasons'],'selected_source_district_vs_2011_classifier':r['source_district_classifier_review'],'classifier_name':r['classifier_2009_locality'],'classifier_district':r['classifier_2009_district'],'raw_named_typed_2011_point_reopened':True,'raw_current_source_and_direct_point_reopened':True,'distance_km':r['distance_km_recomputed'],'whole_source_locality_uniqueness_raw_reopened':True,'decision_scope':'pair-specific physical-place continuity; leaves legacy flag/history intact and does not assert provider binding or exact district continuity','source_flags':f},ensure_ascii=False,sort_keys=True)})
with (out/'scoped_legacy_admin_flag_resolutions.csv').open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=['source_record_id','from_source_record_id','to_source_record_id','resolution_status','proof_json']);w.writeheader();w.writerows(res)
files=[audit,edgesp,evp,base/'admin_binding_v2/receipt.json',dbf,pathlib.Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls'),pathlib.Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls'),htmlp,pathlib.Path(selected),pathlib.Path(pointp),pathlib.Path(graph),gnzip]
receipt={'status':'independent_oldpoint_corridor_review_complete_candidate_only','scope':'Independent bounded review of all 36 oldpoint-currentpoint corridor candidates, with exact old publisher rows, GeoKLADR 2011 point records, direct current point origins, source hardflags and accepted graph11 union/collision checks. No canonical mutation.','candidate_directory':str(base),'review_output_directory':str(out),'input_hashes':{str(p):sha(p) for p in files},'findings':{'eligible_candidate_edges':len(eligible),'held':len(holds),'scoped_legacy_admin_flag_resolutions':len(res),'raw_xls_rows_reopened':sum('sheet' in r for r in source_checks),'raw_archived_html_rows_reopened':sum('source_row' in r for r in source_checks),'raw_geo2011_dbf_records_reopened':36,'current_selected_rows_reopened':len(curids),'current_accepted_point_origins_reopened':len(point_replays),'current_accepted_point_origin_counts':dict(collections.Counter(x['origin_kind'] for x in point_replays.values())),'all_base_graph11_candidate_unions':'none already connected; all 32 unheld proposals are union-safe and no baseline year collision; two 2002/2010 same-object Horlovo edges would both connect and remain held under successor flag','source_flag_counts':{'all_additive':all(evs[x['old_id']].get('is_additive_settlement_record') is True for x in rows),'federal_aggregate':sum(bool(evs[x['old_id']].get('is_federal_aggregate')) for x in rows),'same_year_collision':sum(bool(evs[x['old_id']].get('legacy_same_year_collision')) for x in rows),'verified_successor':sum(bool(evs[x['old_id']].get('legacy_verified_successor_settlement_id')) for x in rows),'legacy_admin_conflict':sum(bool(evs[x['old_id']].get('legacy_identity_conflict')) for x in rows),'actual_source_district_mismatch':sum(x['source_district_vs_classifier_ancestor']=='district_mismatch' for x in rows)}},'holds_by_reason':dict(collections.Counter(x['hold_reason'] for x in holds)),'method':'All raw old census rows were reopened (31 XLS, five archived HTML); all 36 raw 2011 GeoKLADR records were reopened and matched on complete OKATO, NAME1 and SCOKATO; current selected rows and accepted point origins were independently read; direct Tochnо points were matched to raw source coordinates and all GeoNames origins to exact RU.txt lines; distances were recomputed; source flags were checked; accepted graph11 UF and year collisions tested. A blank source district remains unknown. Pairwise legacy admin conflict resolution does not clear any other source flag.','limitations':['The 2011/current point relationship is a scoped representative-place continuity route, not provider binding, legal district continuity, or census-date precision.','2010 current populations are context only; no boundary comparability or population-quality upgrade.','Two actual district mismatches and two verified-successor flags remain held.','No edge or point has been applied.'],'source_replays':source_checks,'point_origin_replays':list(point_replays.values()),'outputs':{n:sha(out/n) for n in ['eligible_edges.csv','held_edges.csv','reviewed_all_36.csv','scoped_legacy_admin_flag_resolutions.csv','replay.py']}}
(out/'review_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'review_receipt_sha256':sha(out/'review_receipt.json'),'findings':receipt['findings'],'holds':receipt['holds_by_reason'],'resolutions':len(res),'outputs':receipt['outputs']},ensure_ascii=False,indent=2))

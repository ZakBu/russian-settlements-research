from pathlib import Path
import sys,json,hashlib,csv,struct
import pandas as pd
import xlrd
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load()
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,rows,columns=None):
 pd.DataFrame(rows,columns=columns).to_csv(OUT/name,index=False)
manifest=[{'path':str(p),'sha256':sha(p)} for p in s.inputs]
(OUT/'input_manifest.json').write_text(json.dumps(manifest,indent=2))
ids={k:'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(n) for k,n in [('vlasikha',70219),('mikhaylovka',148666),('achaluki',23210),('svetly',118410),('plievo',23149),('novoivan',68674)]}
a='2010:017_68e0e4537e_9._20Basq_Mari_Mord_Tatar_Udm_Chuv_2010.xls:!!!:3854'
b='ROSSTAT2010:T5:p143:l47'
reasons={a:'2002 Ufimsky rayon selo Mikhaylovka row5950 already linked to 2021 Ufimsky row148666. 2010 typed selo row3854 lies between Milovka/Lesnoy/Nachapkino and Vavilovo/Mudarisovo/Surovka/Nikolaevka. Independent official T5:p112:l32 names selo Mikhaylovka in Ufimsky rayon (5384), distinct from selected secondary 5367; identity only; retain population precision discrepancy.',b:'2002 official urban pgt row7066 is separately indented at regional level after Engels rural subtotal (not Engels subordination). 2010 official pgt rowp143:l47 same separate regional urban object. Historical2011 DBF record108548 urban pgt, CITY13180 VILLAGE0, OKATO63575000000 and OKTMO63775000; current2021 Svetly ZATO explicit county/OKTMO63775000101 extends same municipal code. Reject erroneous historical DBF coordinates, retain native urban object/code binding. 2021 generic poselok type is publisher type variation, not proof of physical relocation.'}
edges=[]
for old,key in [(a,'mikhaylovka'),(b,'svetly')]:
 new=ids[key];x,y=s.by_id.loc[old],s.by_id.loc[new]
 edges.append(dict(from_source_record_id=old,to_source_record_id=new,from_year=int(x.census_year),to_year=2021,relation='same_place',decision_status='case_review_accepted',selection_projection_status='active_endpoints_selected',identity_evidence=reasons[old],from_source_locator=x.source_locator,to_source_locator=y.source_locator,from_source_sha256=x.source_sha256,to_source_sha256=y.source_sha256,population_comparability_asserted=False,boundary_comparability_asserted=False,protected_2010_precision_flag=True,from_population=x.population,to_population=y.population))
write('candidate_identity_edges.csv',[{**e,'decision_status':'candidate_only'} for e in edges])
write('accepted_identity_edge_delta.csv',edges)
base=s.metrics();changes=[]
for e in edges:
 changed=s.union(e['from_source_record_id'],e['to_source_record_id']);changes.append({'to_source_record_id':e['to_source_record_id'],'new_graph_union':changed})
points=[];supersessions=[]
for old,key in [(a,'mikhaylovka'),('2002:041_4b428edd23_Bashkiria_new.xls:Sheet1:5950','mikhaylovka'),(b,'svetly'),('2002:1_TOM_01_04.xls:0:7066','svetly')]:
 if old in s.point_rows and key!='svetly':continue
 carrier=s.point_rows[ids[key]];target=s.by_id.loc[old]
 r={**carrier,'target_source_record_id':old,'target_year':int(target.census_year),'coordinate_admission_status':'reviewed_case_accepted','coordinate_source_record_id':ids[key],'source_sha256':target.source_sha256,'source_locator':target.source_locator,'application_inference_kind':'modern_point_reuse_explicit_physical_continuity','direct_historical_coordinate_measurement':False,'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False}
 r.pop('point_ledger_path',None)
 if key=='svetly':
  prev=s.point_rows[old];r.update(point_supersession_kind='historical_provider_coordinate_error_modern_continuity_transfer',point_supersession_old_latitude=prev['latitude'],point_supersession_old_longitude=prev['longitude'],point_supersession_old_origin_locator=prev['point_origin_locator'],point_supersession_old_origin_sha256=prev['point_origin_sha256'],point_supersession_predecessor_ledger_sha256=sha(prev['point_ledger_path']))
  supersessions.append(r)
 else:points.append(r)
write('accepted_point_use_delta.csv',points,['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','source_sha256','source_locator','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','application_inference_kind','direct_historical_coordinate_measurement','population_scope_comparability_asserted','boundary_comparability_asserted'])
write('reviewed_point_supersession_delta.csv',supersessions)
write('point_rejections.csv',[{'target_source_record_id':r['target_source_record_id'],'rejection_status':'reviewed_rejected_coordinate_claim_only','old_latitude':r['point_supersession_old_latitude'],'old_longitude':r['point_supersession_old_longitude'],'point_origin_file':s.point_rows[r['target_source_record_id']]['point_origin_file'],'point_origin_sha256':r['point_supersession_old_origin_sha256'],'point_origin_locator':r['point_supersession_old_origin_locator'],'origin_ledger':s.point_rows[r['target_source_record_id']]['point_ledger_path'],'origin_ledger_sha256':r['point_supersession_predecessor_ledger_sha256'],'rejection_reason':'GeoKLADR urban code/object binding retained; coordinate approximately225km from own current ZATO point and instead near distinct rural Svetly Краснопартизанский. Explicit coordinateclaim rejection and supersession; frozen ledger preserved.'} for r in supersessions])
# Actual raw observation excluded by parser because type prefix absent.
p=Path('/workspace/settlements-raw/data/raw/2010/002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls');sh=xlrd.open_workbook(p).sheet_by_name('СК'); raw=sh.row_values(854)[:7]
assert raw[5]=='Верхние Ачалуки' and raw[6]==7470
assert not s.obs.source_record_id.eq('2010:'+p.name+':СК:855').any()
alias=s.obs[(s.obs.census_year.eq(2010))&(s.obs.name_norm.str.contains('ачал',case=False,regex=False))]
write('achaluki_selected_alias_scan.csv',alias[['source_record_id','settlement_name','settlement_type','region_norm','population']].to_dict('records'))
aux={'source_record_id':'2010:'+p.name+':СК:855','census_year':2010,'settlement_name':'Верхние Ачалуки','settlement_type_raw':'','settlement_type_inferred':'село','population':7470,'population_value_quality':'direct_raw_published_secondary_value','source_path':str(p),'source_sha256':sha(p),'source_locator':'СК:row_1based=855;population_cell_G855;name_cell_F855','raw_first_seven_cells':json.dumps(raw,ensure_ascii=False),'historical_type_inference':'2002 named selo row32 and2021 named selo row23210;2010 untyped rawname within Ingushetia village list. No population inference.','observation_admission_status':'reviewed_auxiliary_observation_not_selected','same_place_2002_source_record_id':'2002:030_ae13fa30f2_02c_Ingushetia.xls:Sheet1:32','same_place_2021_source_record_id':ids['achaluki'],'selected_2010_credit_allowed':False,'population_credit_condition':'requires selected-region reconciliation and no duplicate counted vertex; unknown vertex not unioned'}
write('reviewed_genuine_auxiliary_observation.csv',[aux])
# Bounded provenance replay.
raws=[]
for path,sheet,rr in [(p,'СК',[855,857,858,859,860,861,862,863,864,865,866]),(Path('/workspace/settlements-raw/data/raw/2010/017_68e0e4537e_9._20Basq_Mari_Mord_Tatar_Udm_Chuv_2010.xls'),'!!!',list(range(3851,3859))),(Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls'),0,list(range(7061,7068)))]:
 book=xlrd.open_workbook(path);tab=book.sheet_by_index(sheet) if isinstance(sheet,int) else book.sheet_by_name(sheet)
 for n in rr:raws.append({'source_path':str(path),'source_sha256':sha(path),'source_locator':str(sheet)+':row_1based='+str(n),'cells':tab.row_values(n-1)[:7]})
(OUT/'raw_source_replay.json').write_text(json.dumps(raws,ensure_ascii=False,indent=2))
(OUT/'review.json').write_text(json.dumps({'baseline_metrics':base,'post_edges_and_nonconflicting_points_metrics':s.metrics(extra_point_ids=[r['target_source_record_id'] for r in points]),'identity_union_effects':changes,'svetly_coordinate_gate':'Historical provider coordinates wrong despite correct urban object code. Supersession mandatory before joint coverage assertion. Do not call normal State.add_deltas on >5km correction.','held_cases':[{'name':'Власиха','disposition':'no own selected2002 record;retain2010precisionflag;do not fabricate2002'},{'name':'Плиево','disposition':'no own selected2002 name;event/status origin requires auxiliary administrative district research'},{'name':'Новоивановское','disposition':'2002 village712 only one contributor;existing typed merger/absorption hold;no ordinarysameplace2002edge'}],'auxiliary2010_population_added_to_selected':0,'all_selected_population_values_unchanged':True},ensure_ascii=False,indent=2))
print(json.dumps({'edges':len(edges),'points':len(points),'supersessions':len(supersessions),'changes':changes,'aux_population':7470},ensure_ascii=False))
dbf=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
with dbf.open('rb') as f:
 h=f.read(32); hl,rl=struct.unpack('<HH',h[8:12]); fields=[]
 while True:
  block=f.read(32)
  if block[0]==13:break
  fields.append((block[:11].split(b'\0')[0].decode(),block[16]))
 f.seek(hl+108547*rl); data=f.read(rl);offset=1;decoded={}
 for name,n in fields:
  decoded[name]=data[offset:offset+n].decode('cp1251').strip();offset+=n
assert decoded['OKTMO']=='63775000' and decoded['CITY']=='13180' and decoded['VILLAGE']=='0'
(OUT/'svetly_historical_classifier_replay.json').write_text(json.dumps({'source_path':str(dbf),'source_sha256':sha(dbf),'source_locator':'DBF_record_1based=108548;DBF_byte_offset_0based='+str(hl+108547*rl),'raw_fields':decoded,'review':'Keep correct historical urban code/object binding; reject coordinate claim only. municipal OKTMO63775000 matches2021municipalprefix63775000.'},ensure_ascii=False,indent=2))

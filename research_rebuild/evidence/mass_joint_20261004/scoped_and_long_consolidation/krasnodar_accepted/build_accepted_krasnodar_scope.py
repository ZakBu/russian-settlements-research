#!/usr/bin/env python3
"""Materialize root-approved secondary-reported Krasnodar inclusion scope."""
from __future__ import annotations
import csv, hashlib, json, pathlib
import pyarrow as pa
import pyarrow.parquet as pq
import xlrd

OUT=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/workspace/settlements-work/continuation_20261004')
REVIEW=BASE/'independent_review/krasnodar_included_places_review'
CAND=BASE/'federal_and_history/krasnodar_large_included_places'
WD=CAND/'wikidata_Kalinino_Pashkovsky_wbgetentities.json'
SELECTED=pathlib.Path('/workspace/settlements-delivery/mass-joint-sixth-point-corrected-20261004/selected_observations.parquet')
XLS=pathlib.Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')
GN=pathlib.Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
APPROVAL_SHA='f9740680d1a26dbe0d1eea2537d785a6620b29947955e6a93c854c8a37b5b1c1'
XLS_SHA='745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3'
GN_SHA='9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'
WD_SHA='5515b62b4ba7a64095b3e5deba78920f00d2c3c9957dee0b4d8060cfed9978b3'
SELECTED_SHA='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'

OBS_FIELDS=['observation_id','observation_year','observation_year_precision','population','population_raw','population_unit','source_status','source_id_status','source_record_id','source_id_for_loader','source_name_raw','source_type_raw','region_raw','source_file','source_sha256','source_locator','men','women','population_scope_grain','wikidata_claim_subject_qid','wikidata_claim_guid','wikidata_claim_rank','wikidata_P585_raw','wikidata_P585_precision','wikidata_P248_reference_item','wikidata_P1082_raw_statement_json','parent_partition_key','parent_population_contains_child','parent_partition_values_json','nested_norilsk_city_population','is_parent_additive','national_additive','observation_grain_comparability','boundary_comparability','current_entity_id','current_native_code_binding','ordinary_NP_same_grain_identity','scope_note']
POINT_FIELDS=['point_use_id','target_observation_id','target_source_record_id','target_year','subject_physical_place_qid','latitude','longitude','point_provider','provider_id','point_origin_file','point_origin_sha256','point_origin_member','point_origin_locator','point_origin_line_sha256','point_claim_locator','point_claim_file_sha256','coordinate_use','direct_historical_coordinate_measurement','provider_identifier_binding_asserted','native_current_settlement_id_binding','measurement_date','boundary_comparability','point_status']
EDGE_FIELDS=['edge_id','from_observation_id','to_observation_id','from_year','to_year','from_source_record_id','to_source_record_id','relation_type','decision_status','root_approval_status','root_approval_basis_receipt_sha256','wikidata_claim_subject_qid','point_use_id_from','point_use_id_to','evidence_summary','date_precision_and_boundary_limit','nonclaims','ordinary_NP_same_grain_identity','population_comparability_asserted','parent_population_transfer']

def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def readcsv(p):
 with pathlib.Path(p).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def writecsv(name,fields,rows):
 p=OUT/name
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise',lineterminator='\n');w.writeheader();w.writerows(rows)
 with p.open(encoding='utf-8',newline='') as f:
  r=csv.DictReader(f);assert r.fieldnames==fields;rr=list(r)
 assert len(rr)==len(rows)
 return rr

def main():
 assert sha(REVIEW/'review_receipt.json')==APPROVAL_SHA
 assert sha(WD)==WD_SHA and sha(XLS)==XLS_SHA and sha(GN)==GN_SHA and sha(SELECTED)==SELECTED_SHA
 # Match exact selected old and current whole-city parent rows in the frozen selected source snapshot.
 import duckdb
 con=duckdb.connect(':memory:')
 selected_rows=con.execute("SELECT source_record_id,census_year,source_name_raw,settlement_name,settlement_type,population,source_file,source_sheet,source_row,source_native_id,oktmo,is_additive_settlement_record FROM read_parquet(?) WHERE source_record_id IN (?,?) ORDER BY census_year",[str(SELECTED),'2002:1_TOM_01_04.xls:0:4113','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46712']).fetchall()
 assert len(selected_rows)==2
 old_city=next(r for r in selected_rows if r[1]==2002); current_city=next(r for r in selected_rows if r[1]==2021)
 assert (old_city[0],old_city[5],old_city[4],old_city[11])==('2002:1_TOM_01_04.xls:0:4113',646175.0,'город',True)
 assert (current_city[0],current_city[5],current_city[4],current_city[11])==('2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46712',1099344.0,'город',True)
 # Re-read raw 2002 worksheet headers and exact source rows, including sex arithmetic.
 wb=xlrd.open_workbook(str(XLS),on_demand=True);ws=wb.sheet_by_index(0)
 assert int(ws.cell_value(4118,1))==34152 and int(ws.cell_value(4118,2))==16368 and int(ws.cell_value(4118,3))==17784
 assert int(ws.cell_value(4119,1))==43077 and int(ws.cell_value(4119,2))==19861 and int(ws.cell_value(4119,3))==23216
 assert 'Калинино' in ws.cell_value(4118,0) and 'Пашковский' in ws.cell_value(4119,0)
 api=json.loads(WD.read_text(encoding='utf-8'))
 src=[
  {'place':'Калинино','id':'2002:1_TOM_01_04.xls:0:4119','qid':'Q4209579','pop':34152,'male':16368,'female':17784,'guid':'Q4209579$7169E076-C4EF-4EA7-BD3B-7663A537C2DC','ref_url':'http://www.lingvarium.org/russia/BD/02c_Krasnodarski-krai.xls','source_row':4119,'source_locator':'Official 2002 Tom 1, Table 4, sheet 0, row 4119; literal row пгт Калинино','point':(45.1025,38.934583333333),'pointguid':'Q4209579$39490560-44b8-21a1-5b40-638dbfb0aef8','provider':'Wikidata P625','provider_id':'','provider_binding':False,'point_file':str(WD),'point_sha':WD_SHA,'point_locator':'entities.Q4209579.claims.P625[Q4209579$39490560-44b8-21a1-5b40-638dbfb0aef8]','point_origin_member':'','point_origin_line_sha':'','point_role':'Wikidata P625 named-locality point selected for scoped historic-place context; GN point is independent name/ADM1 corroboration only, no P1566 binding.'},
  {'place':'Пашковский','id':'2002:1_TOM_01_04.xls:0:4120','qid':'Q4347629','pop':43077,'male':19861,'female':23216,'guid':'Q4347629$80308532-4f34-b404-60f2-64ae8b036a4a','ref_url':'http://demoscope.ru/weekly/ssp/rus02_reg2.php','source_row':4120,'source_locator':'Official 2002 Tom 1, Table 4, sheet 0, row 4120; literal row пгт Пашковский','point':(45.02366,39.10436),'pointguid':'Q4347629$A3DB1ACC-B32A-438C-BE78-DF239BB962DE','provider':'GeoNames RU dump','provider_id':'512382','provider_binding':True,'point_file':str(GN),'point_sha':GN_SHA,'point_locator':'RU.txt line 51725; byte_start 7411730','point_origin_member':'RU.txt','point_origin_line_sha':'36047f2c2dfbefce24c03096ec7f7e153c304ed2970e2981b8bd513db36196f3','point_role':'GeoNames named physical PPLX point selected by exact QID P1566=512382 for historical PGT/current microdistrict context.'}]
 obs=[];claimmap={}
 for x in src:
  e=api['entities'][x['qid']]
  matches=[s for s in e['claims']['P1082'] if s.get('id')==x['guid']]
  assert len(matches)==1
  st=matches[0];assert int(st['mainsnak']['datavalue']['value']['amount'])==x['pop']
  p585=st['qualifiers']['P585'][0]['datavalue']['value'];assert p585['precision']==9 and p585['time']=='+2002-00-00T00:00:00Z'
  refs=';'.join(sn['datavalue']['value'] for r in st.get('references',[]) for sn in r.get('snaks',{}).get('P854',[]))
  assert x['ref_url'] in refs
  claimmap[x['qid']]=st
  obs.append(dict(observation_id=x['id'],observation_year=2002,observation_year_precision='year_only_precision_9',population=x['pop'],population_raw=str(x['pop']),population_unit='persons',source_status='official_primary_source_observation',source_id_status='selected_atomic_source_record_id',source_record_id=x['id'],source_id_for_loader=x['id'],source_name_raw='пгт '+x['place'],source_type_raw='пгт',region_raw='Краснодарский край',source_file=str(XLS),source_sha256=XLS_SHA,source_locator=x['source_locator'],men=x['male'],women=x['female'],population_scope_grain='Official 2002 Table 4 separate urban settlement row; pgt settlement; not a child of selected Krasnodar city row',wikidata_claim_subject_qid=x['qid'],wikidata_claim_guid=x['guid'],wikidata_claim_rank=st.get('rank','normal'),wikidata_P585_raw=p585['time'],wikidata_P585_precision=9,wikidata_P248_reference_item='',wikidata_P1082_raw_statement_json=json.dumps(st,ensure_ascii=False,separators=(',',':')),parent_partition_key='No aggregate parent assignment asserted for this separate 2002 PGT row',parent_population_contains_child=None,parent_partition_values_json='{}',nested_norilsk_city_population=None,is_parent_additive=False,national_additive=False,observation_grain_comparability='unknown',boundary_comparability='unknown',current_entity_id=None,current_native_code_binding=False,ordinary_NP_same_grain_identity=False,scope_note='Scoped historical source row only. The 2002 selected Krasnodar city row is 646175 and is a separate source unit; neither old PGT value is transferred to that row or to current Krasnodar. The 2021 Krasnodar total is parent context only, not an inherited local observation.'))
 obs=writecsv('scoped_primary_observations.csv',OBS_FIELDS,obs)
 points=[]
 for x in src:
  points.append(dict(point_use_id=x['id']+':scoped_point',target_observation_id=x['id'],target_source_record_id=x['id'],target_year=2002,subject_physical_place_qid=x['qid'],latitude=x['point'][0],longitude=x['point'][1],point_provider=x['provider'],provider_id=x['provider_id'],point_origin_file=x['point_file'],point_origin_sha256=x['point_sha'],point_origin_member=x['point_origin_member'],point_origin_locator=x['point_locator'],point_origin_line_sha256=x['point_origin_line_sha'],point_claim_locator=f"entities.{x['qid']}.claims.{ 'P1566' if x['provider_id'] else 'P625' }[{x['pointguid']}]",point_claim_file_sha256=WD_SHA,coordinate_use=x['point_role'],direct_historical_coordinate_measurement=False,provider_identifier_binding_asserted=x['provider_binding'],native_current_settlement_id_binding=False,measurement_date='',boundary_comparability='unknown',point_status='accepted_scoped_named_place_point_use'))
 points=writecsv('scoped_point_uses.csv',POINT_FIELDS,points)
 context_id='current-parent-context:2021:2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46712'
 rels=[]
 for x in src:
  rels.append(dict(edge_id=x['place'].lower()+'_2002_to_current_krasnodar_parent_secondary_inclusion',from_observation_id=x['id'],to_observation_id=context_id,from_year=2002,to_year=2021,from_source_record_id=x['id'],to_source_record_id=None,relation_type='secondary_reported_inclusion_in_current_city_territory',decision_status='accepted_secondary_reported_inclusion_scope',root_approval_status='approved_with_limits',root_approval_basis_receipt_sha256=APPROVAL_SHA,wikidata_claim_subject_qid=x['qid'],point_use_id_from=x['id']+':scoped_point',point_use_id_to=None,evidence_summary=f"The exact official 2002 PGT row is retained as its own observation. Russian Wikipedia page revision for {x['place']} reports inclusion into Krasnodar city limits/microdistrict status in 2003 and cites Assembly resolution 155-P dated 2003-04-24; cited legal text was not independently verified. Current receiving context is Q3646 Krasnodar whole-city selected row only.",date_precision_and_boundary_limit='Secondary source reports 2003; exact legal effective date is not verified. Historic/current territorial boundary comparability is unknown.',nonclaims='No verified legal act/effective date; no current child population; no child QID/native-code binding; no same-grain census identity; no inherited 2021 Krasnodar population; no population transfer.',ordinary_NP_same_grain_identity=False,population_comparability_asserted=False,parent_population_transfer=False))
 edges=writecsv('accepted_typed_scope_edges.csv',EDGE_FIELDS,rels)
 # Use exact Talnakh parquet column names/types so the generic reader can safely inspect the files.
 tal=pathlib.Path('/workspace/settlements-work/continuation_20261004/root/accepted_talnakh_typed_scope')
 for csvname,pqname in [('scoped_primary_observations.csv','scoped_primary_observations.parquet'),('scoped_point_uses.csv','scoped_point_uses.parquet'),('accepted_typed_scope_edges.csv','accepted_typed_scope_edges.parquet')]:
  rows=readcsv(OUT/csvname); schema=pq.read_schema(tal/pqname).remove_metadata(); arrays=[]
  for field in schema:
   vals=[]
   for row in rows:
    v=row[field.name]
    if v=='':v=None
    elif pa.types.is_integer(field.type):v=int(v)
    elif pa.types.is_boolean(field.type):v=v.lower()=='true'
    elif pa.types.is_floating(field.type):v=float(v)
    vals.append(v)
   arrays.append(pa.array(vals,type=field.type))
  pq.write_table(pa.Table.from_arrays(arrays,schema=schema),OUT/pqname,compression='zstd')
  assert pq.read_schema(OUT/pqname).remove_metadata()==schema
 # Evidence sidecars preserve raw headers, quoted article content and external current-parent references.
 headers={'source_file':str(XLS),'source_sha256':XLS_SHA,'sheet_index':0,'sheet_name':ws.name,'table_title_raw':ws.cell_value(0,0),'header_cells_raw':[ws.cell_value(1,c) for c in range(4)],'subheader_cells_raw':[ws.cell_value(2,c) for c in range(4)],'source_rows':[{'source_record_id':x['id'],'excel_row_1based':x['source_row'],'cells_raw':[ws.cell_value(x['source_row']-1,c) for c in range(4)]} for x in src]}
 (OUT/'source_headers_and_rows.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 articles={}
 for key,file,needle in [('kalinino','wikipedia_kalinino_article_revision.json','В 2003'),('pashkovsky','wikipedia_pashkovsky_article_revision.json','В 2003')]:
  data=json.loads((CAND/file).read_text(encoding='utf-8'));page=data['query']['pages'][0];rev=page['revisions'][0];content=rev['slots']['main']['content']
  lines=[line for line in content.splitlines() if needle in line and 'включён' in line]
  assert lines and 'включён' in lines[0] and '155-П' in content
  articles[key]={'input_file':str(CAND/file),'file_sha256':sha(CAND/file),'page_title':page['title'],'pageid':page['pageid'],'revision_id':rev['revid'],'timestamp':rev['timestamp'],'raw_wikitext_quote':lines[0], 'quoted_claim':'В 2003 году посёлок городского типа '+('Калинино' if key=='kalinino' else 'Пашковский')+' был включён в городскую черту Краснодара; статья характеризует его как микрорайон.', 'citation_title':'Постановление Законодательного Собрания Краснодарского края от 24 апреля 2003 г. N 155-П «О включении отдельных населённых пунктов в состав города Краснодара»','citation_url':'https://base.garant.ru/23944414/','verification':'secondary article only; the official act URL request timed out with zero document bytes; no legal text or effective date is claimed verified'}
 (OUT/'secondary_article_evidence.json').write_text(json.dumps(articles,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 context=[
  {'context_id':'old-parent-context:2002:2002:1_TOM_01_04.xls:0:4113','context_role':'separate_selected_Krasnodar_city_source_row','year':2002,'source_record_id':'2002:1_TOM_01_04.xls:0:4113','population':646175,'name':'г. Краснодар','type':'город','source_file':'/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls','source_sha256':XLS_SHA,'source_locator':'2002 Table 4 sheet 0 row 4113','relationship_limit':'This selected city observation is a separate source unit; it is not treated as the parent total containing the separate PGT rows.'},
  {'context_id':context_id,'context_role':'current_receiving_city_parent_reference_only','wikidata_city_qid':'Q3646','year':2021,'source_record_id':'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46712','population':1099344,'name':'г. Краснодар','type':'город','oktmo':'3701000001','source_snapshot_path':str(SELECTED),'source_snapshot_sha256':sha(SELECTED),'relationship_limit':'Whole-city parent context; no inherited Pashkovsky/Kalinino 2021 observation or population transfer.'}]
 with (OUT/'current_parent_context_references.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['context_id','context_role','wikidata_city_qid','year','source_record_id','population','name','type','oktmo','source_file','source_sha256','source_locator','source_snapshot_path','source_snapshot_sha256','relationship_limit'],extrasaction='raise',lineterminator='\n');w.writeheader()
  for c in context:w.writerow(c)
 schema={'schema_version':'talnakh_scoped_layer_v1','layer':'accepted_krasnodar_inclusion_scope','files':{'observations':'scoped_primary_observations.parquet','point_uses':'scoped_point_uses.parquet','scope_edges':'accepted_typed_scope_edges.parquet'},'join_keys':{'observations':'observation_id','points':'target_observation_id','edges':['from_observation_id','to_observation_id']},'edge_destination_context':{'context_file':'current_parent_context_references.csv','context_key':'context_id','note':'The edge to_observation_id points to a context reference, not a fabricated population observation; join to_source_record_id to the existing current whole-city row only through this sidecar.'},'old_2002_union_hooks':[{'source_record_id':x['id'],'action':'join to existing selected canonical 2002 source row by exact source_record_id; do not append a duplicate population observation','old_primary_value':x['pop']} for x in src],'current_parent_context':{'source_record_id':context[1]['source_record_id'],'population':1099344,'action':'display context only; never assign parent value to either former PGT/microdistrict'},'guards':{'all_observations_national_additive':False,'point_is_historical_measurement':False,'current_child_entity_ids_created':False,'ordinary_NP3_claimed':False,'boundary_comparability_asserted':False,'population_parent_transfers':False,'inclusion_is_secondary_reported_not_legal_act_verified':True}}
 (OUT/'loader_schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('built observations=2 points=2 links=2 parent references=2')
if __name__=='__main__':main()

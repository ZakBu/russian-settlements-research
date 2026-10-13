#!/usr/bin/env python3
"""Materialize the root-approved, isolated Kayerkan typed-scope layer."""
from __future__ import annotations
import csv, hashlib, json, pathlib
import pyarrow as pa
import pyarrow.parquet as pq

OUT = pathlib.Path(__file__).resolve().parent
BASE = pathlib.Path('/workspace/settlements-work/continuation_20261004')
REVIEW = BASE / 'independent_review/kayerkan_scope_review'
RAW_ENTITY = BASE / 'federal_and_history/kayerkan_verified_scope_candidate/wikidata_Q1020918_wbgetentities.json'
ROOT_RECEIPT_SHA = '86f5322cde458d983567941dd7fa4dde56eff65847d1a10f67440c6678ba5584'
QID = 'Q1020918'
GEO_ZIP = '/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip'
GEO_SHA = '9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'
GEO_LINE_SHA = '7cd052d79ccbccd1b9fba6c274883d6bbc02258502cf2985caba6c5a95f34b0e'
WD_ENTITY_SHA = '3a0902f401edffb29e7e82ed19eba789593b12f647bd8cb99ddbb5fd84514366'

OBS_FIELDS = ['observation_id','observation_year','observation_year_precision','population','population_raw','population_unit','source_status','source_id_status','source_record_id','source_id_for_loader','source_name_raw','source_type_raw','region_raw','source_file','source_sha256','source_locator','men','women','population_scope_grain','wikidata_claim_subject_qid','wikidata_claim_guid','wikidata_claim_rank','wikidata_P585_raw','wikidata_P585_precision','wikidata_P248_reference_item','wikidata_P1082_raw_statement_json','parent_partition_key','parent_population_contains_child','parent_partition_values_json','nested_norilsk_city_population','is_parent_additive','national_additive','observation_grain_comparability','boundary_comparability','current_entity_id','current_native_code_binding','ordinary_NP_same_grain_identity','scope_note']
POINT_FIELDS = ['point_use_id','target_observation_id','target_source_record_id','target_year','subject_physical_place_qid','latitude','longitude','point_provider','provider_id','point_origin_file','point_origin_sha256','point_origin_member','point_origin_locator','point_origin_line_sha256','point_claim_locator','point_claim_file_sha256','coordinate_use','direct_historical_coordinate_measurement','provider_identifier_binding_asserted','native_current_settlement_id_binding','measurement_date','boundary_comparability','point_status']
EDGE_FIELDS = ['edge_id','from_observation_id','to_observation_id','from_year','to_year','from_source_record_id','to_source_record_id','relation_type','decision_status','root_approval_status','root_approval_basis_receipt_sha256','wikidata_claim_subject_qid','point_use_id_from','point_use_id_to','evidence_summary','date_precision_and_boundary_limit','nonclaims','ordinary_NP_same_grain_identity','population_comparability_asserted','parent_population_transfer']

def readcsv(path):
    with path.open(encoding='utf-8', newline='') as f: return list(csv.DictReader(f))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def write_csv(name, fields, rows):
    p=OUT/name
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise',lineterminator='\n')
        w.writeheader(); w.writerows(rows)
    with p.open(encoding='utf-8',newline='') as f:
        r=csv.DictReader(f); assert r.fieldnames==fields, (name,r.fieldnames); reread=list(r)
    assert len(reread)==len(rows), (name,len(reread),len(rows))
    return reread

def main():
    reviewed_obs=readcsv(REVIEW/'eligible_scoped_observations.csv')
    reviewed_points=readcsv(REVIEW/'eligible_point_use.csv')
    reviewed_edges=readcsv(REVIEW/'eligible_typed_relations.csv')
    assert len(reviewed_obs)==3 and len(reviewed_points)==1 and len(reviewed_edges)==2
    assert sha(REVIEW/'review_receipt.json')==ROOT_RECEIPT_SHA
    assert sha(RAW_ENTITY)==WD_ENTITY_SHA
    api=json.loads(RAW_ENTITY.read_text(encoding='utf-8'))
    entity=api['entities'][QID]
    claim_guids={2002:'Q1020918$8C86F1AE-3840-4328-A87E-50198610DEFF',2010:'Q1020918$78A5AC67-E32B-4659-8E5B-2E5485DB2B08',2021:'Q1020918$11DCC3FE-45C6-498A-BE0B-44787EC75ACE'}
    refids={2002:'Q126687602',2010:'Q127158401',2021:'Q126684906'}
    statements={}
    for year,guid in claim_guids.items():
        matches=[s for s in entity['claims']['P1082'] if s.get('id')==guid]
        assert len(matches)==1, (year,guid,len(matches))
        st=matches[0]
        amount=st['mainsnak']['datavalue']['value']['amount'].lstrip('+')
        assert int(amount)==int(next(x['population'] for x in reviewed_obs if int(x['year'])==year))
        time=st['qualifiers']['P585'][0]['datavalue']['value']
        assert time['precision']==9 and time['time']==f'+{year}-00-00T00:00:00Z'
        refs=[sn['datavalue']['value']['id'] for ref in st.get('references',[]) for sn in ref.get('snaks',{}).get('P248',[])]
        assert refids[year] in refs, (year,refs)
        statements[year]=st
    aux_ids={2010:'event_scope:kayerkan:2010:ROSSTAT_T5:pdf_p178',2021:'event_scope:kayerkan:2021:ROSSTAT_T5:sheet_tab5_row22435'}
    sources={2002:{'file':'/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls','locator':'worksheet 01-04; Excel row 8696','name':'г. Кайеркан','type':'город','region':'Красноярский край','men':13741,'women':13375,'grain':'Norilsk parent Table 4 city-population partition; separate named city settlement row'},
             2010:{'file':'/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf','locator':'2010 Table 1.5, printed p.177 / PDF p.178, Norilsk intracity-district rows','name':'Кайеркан','type':'район (внутригородской район)','region':'Красноярский край','men':11345,'women':10993,'grain':'Norilsk selected city partition; auxiliary named intracity district row'},
             2021:{'file':'/workspace/settlements-raw/data/raw/rosstat_2021/Tom1_tab-5_VPN-2020.xlsx','locator':'2021 Table 5, sheet таб. 5 row 22435; Norilsk intracity-district rows','name':'район Кайеркан','type':'район (внутригородской район)','region':'Красноярский край','men':10468,'women':10725,'grain':'Norilsk selected city partition; auxiliary named intracity district row'}}
    source_sha={2002:'745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3',2010:'42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3',2021:'0b232b3d2ab5daa231568acc719ac6fda4fb0979a01a0da6bacc69be6f252474'}
    pop_by_year={int(r['year']):int(r['population']) for r in reviewed_obs}
    obs=[]
    for y in (2002,2010,2021):
        r=next(x for x in reviewed_obs if int(x['year'])==y); s=sources[y]
        canonical=(y==2002); oid=r['observation_id']; parentvals={2002:{'Норильск':134832,'Кайеркан':27116,'Талнах':58654,'Снежногорск':1306},2010:{'Кайеркан':22338,'Талнах':47307,'Центральный':105720},2021:{'район Кайеркан':21193,'район Талнах':47216,'Центральный район':106044}}[y]
        parenttotal={2002:221908,2010:175365,2021:174453}[y]
        # Bind actual Wikidata statement payload, including references, rank, and qualifiers.
        stmt=statements[y]
        ref=refids[y]
        oldid=r['source_record_id'] if canonical else ''
        loaderid=r['source_record_id']
        obs.append(dict(observation_id=oid,observation_year=y,observation_year_precision='year_only_precision_9',population=int(r['population']),population_raw=r['population'],population_unit='persons',source_status='official_primary_source_observation',source_id_status='selected_atomic_source_record_id' if canonical else 'auxiliary_scoped_source_id_not_canonical',source_record_id=oldid,source_id_for_loader=loaderid,source_name_raw=s['name'],source_type_raw=s['type'],region_raw=s['region'],source_file=s['file'],source_sha256=source_sha[y],source_locator=s['locator'],men=s['men'],women=s['women'],population_scope_grain=s['grain'],wikidata_claim_subject_qid=QID,wikidata_claim_guid=stmt['id'],wikidata_claim_rank=stmt.get('rank','normal'),wikidata_P585_raw=stmt['qualifiers']['P585'][0]['datavalue']['value']['time'],wikidata_P585_precision=9,wikidata_P248_reference_item=ref,wikidata_P1082_raw_statement_json=json.dumps(stmt,ensure_ascii=False,separators=(',',':')),parent_partition_key={2002:'Norilsk 2002 Table 4 subordinate-city-group urban population',2010:'Norilsk 2010 Table 5 city partition urban population',2021:'Norilsk 2021 Table 5 city partition urban population'}[y],parent_population_contains_child=parenttotal,parent_partition_values_json=json.dumps(parentvals,ensure_ascii=False,separators=(',',':')),nested_norilsk_city_population=134832 if y==2002 else parenttotal,is_parent_additive=False,national_additive=False,observation_grain_comparability='unknown',boundary_comparability='unknown',current_entity_id='',current_native_code_binding=False,ordinary_NP_same_grain_identity=False,scope_note={2002:'2002 separate-city population row occurs inside Norilsk subordinate-city-group total 221908; union this source record once only. Norilsk physical city population 134832 is separate and not a recipient.',2010:'2010 district value is nested within the selected Norilsk city partition 175365; auxiliary scope row only, never add to parent.',2021:'2021 district value is nested within the selected Norilsk city partition 174453; auxiliary scope row only, never add to parent.'}[y]))
        assert sum(parentvals.values())==parenttotal if y==2002 else True
        if y==2002: assert 134832+27116+58654+1306==parenttotal
        else: assert sum(parentvals.values())==parenttotal
    obs=write_csv('scoped_primary_observations.csv',OBS_FIELDS,obs)
    # Three dated observation contexts use one accepted representative point; this is not a historical measurement.
    points=[]
    for o in obs:
        y=int(o['observation_year']); oid=o['observation_id']; targetrec=o['source_record_id']
        points.append(dict(point_use_id=f'{oid}:kayerkan_gn_ppl_point',target_observation_id=oid,target_source_record_id=targetrec,target_year=y,subject_physical_place_qid=QID,latitude=69.37861,longitude=87.74389,point_provider='GeoNames RU dump',provider_id='1504139',point_origin_file=GEO_ZIP,point_origin_sha256=GEO_SHA,point_origin_member='RU.txt',point_origin_locator='line 179037; byte_start 26427554',point_origin_line_sha256=GEO_LINE_SHA,point_claim_locator='entities.Q1020918.claims.P1566[Q1020918$439919CD-A0E4-407F-A937-7D71D1DAB564]',point_claim_file_sha256=WD_ENTITY_SHA,coordinate_use='named physical-place representative point; retrospective scoped context only',direct_historical_coordinate_measurement=False,provider_identifier_binding_asserted=False,native_current_settlement_id_binding=False,measurement_date='',boundary_comparability='unknown',point_status='accepted_scoped_named_place_point_use'))
    points=write_csv('scoped_point_uses.csv',POINT_FIELDS,points)
    relations=[
        dict(relation_id='kayerkan:2002city-to-2010district',from_observation_id='kayerkan:2002:city',to_observation_id='kayerkan:2010:intracity_district',relation_type='typed_place_continuity_across_published_scope_change',evidence='Official 2002 source labels Kayerkan as a separate city row; official 2010 Table 5 lists it as a Norilsk intracity district. Same named physical locality and same Q1020918 statement subject; independent review approved this typed relation.',decision='eligible_typed_relation_candidate_only',effective_date='unknown; bounded by official observations after 2002 and by 2010',boundary_comparability='false / unestablished',population_transfer_to_parent='not asserted'),
        dict(relation_id='kayerkan:2010district-to-2021district',from_observation_id='kayerkan:2010:intracity_district',to_observation_id='kayerkan:2021:intracity_district',relation_type='typed_same_named_intracity_district_continuity',evidence='Both official Table 5 sources identify the named Kayerkan intracity district; same Q1020918 subject has actual-year P1082 statements. Relation is scoped to these typed observations.',decision='eligible_typed_relation_candidate_only',effective_date='not applicable to this observed relation',boundary_comparability='false / unestablished',population_transfer_to_parent='not asserted')]
    edges=[]
    for rel in relations:
        a=next(x for x in obs if x['observation_id']==rel['from_observation_id']); b=next(x for x in obs if x['observation_id']==rel['to_observation_id'])
        pa_id=f"{a['observation_id']}:kayerkan_gn_ppl_point"; pb_id=f"{b['observation_id']}:kayerkan_gn_ppl_point"
        edges.append(dict(edge_id=rel['relation_id'],from_observation_id=a['observation_id'],to_observation_id=b['observation_id'],from_year=int(a['observation_year']),to_year=int(b['observation_year']),from_source_record_id=a['source_record_id'],to_source_record_id=b['source_record_id'],relation_type=rel['relation_type'],decision_status='accepted_scoped_typed_physical_place_relation',root_approval_status='approved_for_separate_scoped_layer',root_approval_basis_receipt_sha256=ROOT_RECEIPT_SHA,wikidata_claim_subject_qid=QID,point_use_id_from=pa_id,point_use_id_to=pb_id,evidence_summary=rel['evidence'],date_precision_and_boundary_limit=rel['effective_date']+'; '+rel['boundary_comparability'],nonclaims='No ordinary same-grain census identity; no exact legal date; no boundary equality; no current native-code/QID binding; no Norilsk parent population transfer.',ordinary_NP_same_grain_identity=False,population_comparability_asserted=False,parent_population_transfer=False))
    edges=write_csv('accepted_typed_scope_edges.csv',EDGE_FIELDS,edges)
    # Type columns exactly as in the accepted Talnakh loader layer, avoiding inference drift.
    tal=pathlib.Path('/workspace/settlements-work/continuation_20261004/root/accepted_talnakh_typed_scope')
    for csvname,pqname in [('scoped_primary_observations.csv','scoped_primary_observations.parquet'),('scoped_point_uses.csv','scoped_point_uses.parquet'),('accepted_typed_scope_edges.csv','accepted_typed_scope_edges.parquet')]:
        rows=readcsv(OUT/csvname)
        ref_schema=pq.read_schema(tal/pqname).remove_metadata()
        arrays=[]
        for field in ref_schema:
            vals=[]
            for row in rows:
                v=row[field.name]
                if v=='': v=None if pa.types.is_null(field.type) else None
                elif pa.types.is_integer(field.type): v=int(v)
                elif pa.types.is_boolean(field.type): v=(v.lower()=='true')
                elif pa.types.is_floating(field.type): v=float(v)
                vals.append(v)
            arrays.append(pa.array(vals,type=field.type))
        table=pa.Table.from_arrays(arrays,schema=ref_schema)
        pq.write_table(table,OUT/pqname,compression='zstd')
        assert pq.read_schema(OUT/pqname).remove_metadata()==ref_schema
        assert pq.read_table(OUT/pqname).num_rows==len(rows)
    loader={
      'schema_version':'talnakh_scoped_layer_v1', 'layer':'accepted_kayerkan_typed_scope',
      'files':{'observations':'scoped_primary_observations.parquet','point_uses':'scoped_point_uses.parquet','scope_edges':'accepted_typed_scope_edges.parquet'},
      'join_keys':{'observations':'observation_id','points':'target_observation_id','edges':['from_observation_id','to_observation_id']},
      'old_2002_union_hook':{'source_record_id':'2002:1_TOM_01_04.xls:0:8696','action':'join to existing canonical old census row by exact source_record_id; do not append a duplicate population observation','old_primary_value':27116,'add_point_context_from':'scoped_point_uses.parquet','identity_edge_from':'accepted_typed_scope_edges.parquet'},
      '2010_2021_auxiliary_rows':{'source_record_id':None,'action':'keep in auxiliary scoped observation layer; do not fabricate canonical settlement source IDs or current IDs; child district counts are already inside the Norilsk city parent rows','auxiliary_observation_ids':[aux_ids[2010],aux_ids[2021]]},
      'guards':{'all_observations_national_additive':False,'point_is_historical_measurement':False,'current_entity_id_created':False,'ordinary_NP3_claimed':False,'boundary_comparability_asserted':False,'population_parent_transfers':False}}
    (OUT/'loader_schema.json').write_text(json.dumps(loader,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    parents={'status':'nonadditive_partition_context_only','observations':[
      {'year':2002,'parent':'г. Норильск с подчиненными его администрации населенными пунктами — городское население','parent_total':221908,'children_sum':221908,'Kayerkan':27116,'separate_Norilsk_city':134832,'Talnakh':58654,'Snezhnogorsk':1306,'source_locator':'2002 Table 4 worksheet 01-04 rows 8694-8698','action':'Kayerkan is included exactly once in the parent partition. The separate Norilsk physical-city row is 134832; no population transfer.'},
      {'year':2010,'parent':'г. Норильск; selected city partition','parent_total':175365,'Norilsk_city_partition':175365,'districts':{'Кайеркан':22338,'Талнах':47307,'Центральный':105720},'source_locator':'2010 Table 1.5 printed p.177 / PDF p.178','action':'Kayerkan intracity district is a child inside the selected parent; do not add child to parent.'},
      {'year':2021,'parent':'selected city row for Norilsk','parent_total':174453,'Norilsk_city_partition':174453,'districts':{'район Кайеркан':21193,'район Талнах':47216,'Центральный район':106044},'source_locator':'2021 Table 5 sheet таб.5; Kayerkan row 22435','action':'Kayerkan intracity district is a child inside the selected parent; do not add child to parent.'}]}
    assert parents['observations'][0]['children_sum']==sum([27116,134832,58654,1306])
    assert sum(parents['observations'][1]['districts'].values())==175365
    assert sum(parents['observations'][2]['districts'].values())==174453
    (OUT/'nonadditive_parent_partition_context.json').write_text(json.dumps(parents,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('materialized rows: observations=3 points=3 edges=2')

if __name__=='__main__': main()

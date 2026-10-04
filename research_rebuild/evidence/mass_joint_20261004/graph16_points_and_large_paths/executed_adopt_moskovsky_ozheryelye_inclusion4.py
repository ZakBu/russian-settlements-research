import json,hashlib
from pathlib import Path
import duckdb,xlrd
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
C=Path('/workspace/settlements-work/continuation_20261004');F=C/'independent_review/large2010_four_priority_review_v1';O=C/'root/accepted_moskovsky_ozheryelye_inclusion4_scope';assert not O.exists()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
review=json.loads((F/'review_receipt.json').read_text())
for p,h in review['output_sha256'].items():assert sha(F/p)==h,p
pins=json.loads((F/'source_pin_manifest.json').read_text())['pins']
for p in pins:assert sha(p['path'])==p['sha256'],p['path']
refs=json.loads((F/'accepted_scoped_inclusion_references.json').read_text());assert len(refs)==4
cfgpath=Path('/workspace/russian-settlements-research/config/mass_joint_20261004.json');cfg=json.loads(cfgpath.read_text());selected=cfg['working_population_layer'];graph=cfg['working_identity_graph'];points=cfg['working_point_uses']
ids=sorted({r[k] for r in refs for k in ['source_record_id','current_2021_receiver_source_record_id']})
db=duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
sel={r['source_record_id']:r for r in db.execute('select source_record_id,census_year,settlement_name,settlement_type,population,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))',[selected,ids]).fetch_arrow_table().to_pylist()};assert len(sel)==6
ev={sid:json.loads(e) for sid,e in db.execute('select source_record_id,source_evidence_json from read_parquet(?) where source_record_id in(select unnest(?))',['/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet',ids]).fetchall()}
sheet=xlrd.open_workbook('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls').sheet_by_index(0)
mosraw=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls');mosbook=xlrd.open_workbook(mosraw).sheet_by_name('Sheet1');newpoints=[]
for r in refs:
    sid=r['source_record_id'];s=sel[sid];receiver=r['current_2021_receiver_source_record_id'];p=r['point_row'];q=p['historical_place_qid']
    assert s['census_year']==int(r['year']) and s['population']==int(r['population']) and s['settlement_type']==r['source_type']
    assert s['is_additive_settlement_record'] and ev[sid]['is_additive_settlement_record'] and not ev[sid].get('is_federal_aggregate')
    assert q in {'Q159261','Q175752'} and not any(r[k] for k in ['population_additive','ordinary_same_place_claim','current_child_population_asserted'])
    if s['census_year']==2002:
        rownum=int(sid.rsplit(':',1)[1]);raw=(mosbook if q=='Q159261' else sheet).row_values(rownum-1)
        assert any(s['settlement_name'] in str(v) for v in raw)
        value=raw[2] if q=='Q159261' else raw[1]
        assert str(value).strip() in {str(int(s['population'])),str(float(s['population']))}
    assert sha(p['point_origin_file'])==p['point_origin_sha256']
    entity=json.loads(Path(p['point_origin_file']).read_text())['entities'][q]
    matches=[]
    for c in entity['claims']['P625']:
        if c.get('rank')=='deprecated' or 'datavalue' not in c['mainsnak']:continue
        v=c['mainsnak']['datavalue']['value']
        if v['globe']=='http://www.wikidata.org/entity/Q2' and abs(v['latitude']-float(p['latitude']))<1e-9 and abs(v['longitude']-float(p['longitude']))<1e-9:matches.append(c)
    assert len(matches)==1
    p['source_point_locator_before_root_binding']=p['point_origin_locator'];p['wikidata_point_claim_guid']=matches[0]['id'];p['point_origin_locator']=f"entity={q}; claim={matches[0]['id']}";p['latitude']=float(p['latitude']);p['longitude']=float(p['longitude']);p['point_precision_raw']=matches[0]['mainsnak']['datavalue']['value'].get('precision')
    p['coordinate_admission_status']='reviewed_case_accepted';p['point_use_status']='approved_scoped_retrospective_context_only';newpoints.append(p)
    r['standalone_historical_settlement_reference']=True;r['independent_source_grain_kind']='individual_named_locality'
    if q=='Q175752':
        assert s['settlement_type']=='город';r['standalone_historical_city_reference']=True;r['current_receiver_grain']='city_proper'
        actual=db.execute('select coordinate_admission_status from read_parquet(?) where target_source_record_id=?',[points,receiver]).fetchall();assert len(actual)==1 and actual[0][0] in ACCEPTED_COORDINATE_STATUSES
        assert sel[receiver]['settlement_type']=='город' and sel[receiver]['population_scope']=='settlement' and not ev[receiver].get('is_federal_aggregate')
    else:
        assert s['settlement_type'] in {'посёлок','город'};r['current_receiver_grain']='federal_territory'
        assert ev[receiver]['is_federal_aggregate'] and sel[receiver]['census_year']==2021
        chain=db.execute("select * from read_parquet(?) where city='Москва'",[cfg['federal_city_continuity']]).fetchall()
        assert len(chain)==1 and receiver in str(chain[0])
        assert db.execute("select count(*) from read_parquet(?) where city_name='Москва' and census_year='2021' and selected_source_record_id=?",[cfg['federal_points'],receiver]).fetchone()[0]==1
    r['current_receiver_population_context_only']=int(sel[receiver]['population']);r['root_independent_review_receipt_sha256']=sha(F/'review_receipt.json')
O.mkdir();outputs={'accepted_scoped_inclusion_references.json':refs,'accepted_scoped_point_uses.json':newpoints}
for n,data in outputs.items():(O/n).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
receipt={'status':'applied_reviewed_secondary_reported_large_inclusion_references','observation_references':4,'new_scoped_point_uses':4,'ordinary_NP3_admission':False,'source_population_values_modified':False,'current_child_population_asserted':False,'parent_population_transfer':False,'modern_boundary_harmonized':False,'legal_acts_independently_verified':False,'inputs':{str(F/'review_receipt.json'):sha(F/'review_receipt.json'),selected:sha(selected),graph:sha(graph),points:sha(points),str(mosraw):sha(mosraw),cfg['federal_city_continuity']:sha(cfg['federal_city_continuity']),cfg['federal_points']:sha(cfg['federal_points'])},'frozen_review_pins':pins,'outputs':{n:sha(O/n) for n in outputs},'script_sha256':sha(__file__)}
(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print({'status':receipt['status'],'refs':4,'old2002_population':sum(r['population'] for r in refs if r['year']==2002),'old2010_population':sum(r['population'] for r in refs if r['year']==2010)})

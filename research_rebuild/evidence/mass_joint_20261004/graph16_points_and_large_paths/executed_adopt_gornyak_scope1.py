import json,hashlib,xml.etree.ElementTree as ET
from pathlib import Path
import duckdb,xlrd
from research_rebuild.mass_linkage.load_reviewed_inclusion_scope_20261004 import load_scoped_inclusion_references
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES

C=Path('/workspace/settlements-work/continuation_20261004');F=C/'independent_review/gornyak_inclusion1_review_v1';O=C/'root/accepted_gornyak_inclusion1_scope'
assert not O.exists()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
review=json.loads((F/'review_receipt.json').read_text());assert review['status']=='frozen_independent_scope_review_candidate_ready_for_root_application'
for p,h in review['input_pins'].items():assert sha(p)==h['sha256'],p
for p,h in review['output_pins'].items():assert sha(F/p)==h['sha256'],p
refs=json.loads((F/'accepted_scoped_inclusion_references.json').read_text());assert len(refs)==1
r=refs[0];assert r['source_record_id']=='2002:1_TOM_01_04.xls:0:7999' and r['population']==14048
cfgpath=Path('/workspace/russian-settlements-research/config/mass_joint_20261004.json');cfg=json.loads(cfgpath.read_text());points=cfg['working_point_uses'];graph=cfg['working_identity_graph'];selected=cfg['working_population_layer']
ids=[r[k] for k in ['source_record_id','old_same_year_city_proper_source_record_id','current_2021_receiver_source_record_id']]
db=duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
rows=db.execute('select source_record_id,census_year,population,settlement_name,settlement_type,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))',[selected,ids]).fetch_arrow_table().to_pylist();assert len(rows)==3
byid={s['source_record_id']:dict(s,type_raw=s['settlement_type']) for s in rows}
sheet=xlrd.open_workbook('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls').sheet_by_index(0)
for s in rows:
    assert s['population_scope']=='settlement' and s['is_additive_settlement_record']
    if s['census_year']==2002:
        raw=sheet.row_values(int(s['source_record_id'].rsplit(':',1)[1])-1)
        assert int(raw[1])==int(s['population']) and int(raw[2])+int(raw[3])==int(raw[1])
        assert s['settlement_name'] in raw[0]
receiver=ids[2];current=db.execute('select latitude,longitude,coordinate_admission_status from read_parquet(?) where target_source_record_id=?',[points,receiver]).fetchall();assert len(current)==1 and current[0][2] in ACCEPTED_COORDINATE_STATUSES
assert db.execute('select count(*) from read_parquet(?) where from_source_record_id=? and to_source_record_id=?',[graph,ids[1],receiver]).fetchone()[0]>0
assert byid[ids[1]]['settlement_type']==byid[receiver]['settlement_type']=='город'
assert byid[receiver]['population']==r['current_receiver_population_context_only']==147806
p=r['point_row'];validated=load_scoped_inclusion_references(F,byid,{ids[0]:p},include_zheleznodorozhny=False);assert len(validated)==1 and validated[0]['population']==14048
# Replay the named-map containment as physical-place corroboration, not a legal boundary.
way=Path('/workspace/settlements-work/continuation_20261004/newregions/don_gornyak_hold_resolution_v1/raw_osm/gornyak_suburb_way_630837764.osm');root=ET.parse(way).getroot();nodes={n.attrib['id']:(float(n.attrib['lon']),float(n.attrib['lat'])) for n in root.findall('node')};w=next(x for x in root.findall('way') if x.attrib['id']=='630837764');tags={t.attrib['k']:t.attrib['v'] for t in w.findall('tag')};assert tags['name']=='Горняк' and tags['place']=='suburb'
polygon=[nodes[n.attrib['ref']] for n in w.findall('nd')];x,y=p['longitude'],p['latitude'];inside=False
for (a,b),(c,d) in zip(polygon,polygon[1:]+polygon[:1]):
    if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:inside=not inside
assert inside
assert not any(r[k] for k in ['population_additive','ordinary_same_place_claim','current_child_population_asserted'])
r['root_independent_review_receipt_sha256']=sha(F/'review_receipt.json')
O.mkdir();outputs={'accepted_scoped_inclusion_references.json':refs,'accepted_scoped_point_uses.json':[p]}
for n,data in outputs.items():(O/n).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
receipt={'status':'applied_reviewed_secondary_reported_large_inclusion_references','observation_references':1,'new_scoped_point_uses':1,'old2002_existing_population_reference_sum':14048,'ordinary_NP3_admission':False,'source_population_values_modified':False,'current_child_population_asserted':False,'parent_population_transfer':False,'modern_boundary_harmonized':False,'legal_acts_independently_verified':False,'inputs':{str(F/'review_receipt.json'):sha(F/'review_receipt.json'),selected:sha(selected),points:sha(points),graph:sha(graph),str(way):sha(way)},'frozen_review_pins':review['input_pins'],'outputs':{n:sha(O/n) for n in outputs},'script_sha256':sha(__file__)}
(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print({'status':receipt['status'],'old2002_population':14048})

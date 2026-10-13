import csv,json,hashlib,zipfile,shutil
from pathlib import Path
from datetime import datetime,timezone
import duckdb,xlrd
C=Path('/workspace/settlements-work/continuation_20261004');F=C/'independent_review/large2010_four_priority_review_v1';O=C/'root/large4_point4952_manifest_preparation';assert not O.exists() or not any(O.iterdir());O.mkdir(exist_ok=True)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return {'path':str(p),'sha256':sha(p)}
review=json.loads((F/'review_receipt.json').read_text());assert review['status']=='candidate_only_not_applied'
for p,h in review['output_sha256'].items():assert sha(F/p)==h,p
for h in json.loads((F/'source_pin_manifest.json').read_text())['pins']:assert sha(h['path'])==h['sha256'],h['path']
m=json.loads((C/'root/current_point4952_manifest_preparation/application_manifest.json').read_text())
edges=list(csv.DictReader((F/'independently_eligible_identity_edges.csv').open(encoding='utf-8-sig')));assert len(edges)==4
db=duckdb.connect(config={'threads':1,'memory_limit':'256MB'});ids=sorted({e[k] for e in edges for k in ['from_source_record_id','to_source_record_id']})
ss=db.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,population,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))',[m['frozen']['selected']['path'],ids]).fetch_arrow_table().to_pylist();selected={r['source_record_id']:r for r in ss};assert len(selected)==6
expected={'2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:341':13787,'ROSSTAT2010:T5:p76:l42':16107,'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46748':15593,'2002:1_TOM_01_04.xls:0:2033':9098,'ROSSTAT2010:T5:p51:l35':9171,'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:152606':8652}
assert set(expected)==set(selected)
for sid,s in selected.items():
    assert s['population']==expected[sid] and s['is_additive_settlement_record']
    assert s['population_scope']=='settlement' or (sid=='2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:341' and s['population_scope'] is None)
    if s['census_year']==2010:
        n=db.execute('select count(*) from read_parquet(?) where census_year=2010 and settlement_name=? and settlement_type=? and region_norm=?',[m['frozen']['selected']['path'],s['settlement_name'],s['settlement_type'],s['region_norm']]).fetchone()[0];assert n==1,(sid,n)
ev={sid:json.loads(e) for sid,e in db.execute('select source_record_id,source_evidence_json from read_parquet(?) where source_record_id in(select unnest(?))',[m['frozen']['source_evidence']['path'],ids]).fetchall()}
for sid,e in ev.items():assert e['is_additive_settlement_record'] and not e.get('is_federal_aggregate') and not e.get('legacy_same_year_collision') and not e.get('legacy_verified_successor_settlement_id'),sid
# The older regional source lacks convenience population_scope metadata;
# literal row grain and authoritative additive/aggregate evidence decide it.
anap02raw=Path('/workspace/settlements-raw/data/raw/2002/036_81b258bc42_02c_Krasnodarski-krai.xls')
literal=xlrd.open_workbook(anap02raw).sheet_by_name('11').row_values(340)
assert literal[1].strip()=='станица Анапская' and int(literal[2])==13787
rows=[]
for r in edges:
    a,b=r['from_source_record_id'],r['to_source_record_id'];family='primary_exact_typed_historical_classified_own_place_'+r['case']
    rows.append({'decision_id':'large-primary-'+hashlib.sha256((a+'\x1f'+b+'\x1f'+family).encode()).hexdigest()[:24],'from_source_record_id':a,'to_source_record_id':b,'from_year':selected[a]['census_year'],'to_year':selected[b]['census_year'],'integration_rule_family':family,'integration_layer':'staged_candidate_pending_independent_review','relation':'same_place','same_year_collision':False,'verified_successor_event':False,'global_block':False,'boundary_comparability_asserted':False,'population_comparability_asserted':False,'native_identifier_continuity_asserted':False,'reviewed_original_row_json':json.dumps(r,ensure_ascii=False),'independent_review_sha256':sha(F/'review_receipt.json')})
def writecsv(p,rows):
    with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
p=O/'large4_adapter.csv';k=O/'large4_eligible.csv';writecsv(p,rows);writecsv(k,[{v:r[v] for v in ['from_source_record_id','to_source_record_id','integration_rule_family']} for r in rows])
spec=json.loads((C/'root/primary22_manifest_preparation/application_manifest.json').read_text())['identity_sources'][0];spec.update(candidate=pin(p),eligible=pin(k),review_receipt=pin(F/'review_receipt.json'));spec['eligible_columns']={'from':'from_source_record_id','to':'to_source_record_id','family':'integration_rule_family'};m['identity_sources']=[spec]
# Only Anapskaya needs a direct point; the 2010 Plekhanovo point follows the accepted graph.
point=next(r for r in csv.DictReader((F/'point_use_candidates.csv').open(encoding='utf-8-sig')) if r['case']=='Анапская');assert point['target_source_record_id'].endswith(':46748')
assert sha(point['point_origin_file'])==point['point_origin_sha256'];found=False
with zipfile.ZipFile(point['point_origin_file']) as z:
    with z.open('RU.txt') as f:
        for num,line in enumerate(f,1):
            if not line.startswith(b'582181\t'):continue
            assert num==121094;cols=line.decode().rstrip('\r\n').split('\t');assert cols[6:9]==['P','PPL','RU'] and 'Анапская' in cols[3]
            assert (float(cols[4]),float(cols[5]))==(float(point['latitude']),float(point['longitude']))
            hraw=hashlib.sha256(line).hexdigest();htrim=hashlib.sha256(line.rstrip(b'\r\n')).hexdigest();assert point['point_origin_line_sha256'] in {hraw,htrim}
            point['point_origin_rawline_sha256']=hraw;point['point_origin_trimmed_line_sha256']=htrim;found=True;break
assert found
point['coordinate_source']='GeoNames';point['coordinate_provider']='GeoNames';point['coordinate_provider_id']='582181';point['source_year_current_carrier_id']=point['target_source_record_id'];point['coordinate_quality']='automatically_accepted_checked_rule';point['target_year']=2021
pp=O/'anapskaya_own_point1.csv';writecsv(pp,[point]);cols={'target':'target_source_record_id','latitude':'latitude','longitude':'longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'}
m['point_sources'].append({'candidate':pin(pp),'approved':pin(pp),'review_receipt':pin(F/'review_receipt.json'),'origin':pin(point['point_origin_file']),'candidate_columns':cols,'approved_columns':cols,'output_columns':{'coordinate_source_record_id':'source_year_current_carrier_id'},'output_values':{'coordinate_admission_rule':'independent_Anapskaya_exact_native_typed_history_GeoNames_Wikidata_RCSI_named_place_rule_20261004','point_origin_kind':'geonames_raw_named_PPL','direct_historical_coordinate_measurement':False,'census_date_point_measurement_proven':False,'boundary_comparability_asserted':False,'coordinate_measurement_date_unknown':True,'native_id_binding_asserted':False,'coordinate_provenance':'Undated proper named-locality point corroborated by independent named sources; current DaData city-centered point is excluded. P764 normalization pads the publisher-native literal to the fixed 11-digit code without editing that literal.'}})
m['manifest_version']='primary_large4_point4952_on_graph15';m['reviewed_at_utc']=datetime.now(timezone.utc).isoformat();m['application_scope']+=' Four primary edges for Anapskaya/Plekhanovo and independently sourced Anapskaya own-locality point. No current city-centered Anapa point accepted.'
script=Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/apply_reviewed_mass_extensions_20261004.py');shutil.copyfile(script,O/script.name);m['review_context_inputs'] += [pin(F/'review_receipt.json'),pin(F/'source_pin_manifest.json'),pin(anap02raw),pin(__file__),pin(O/script.name)]
(O/'application_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print({'new_identity_edges':4,'direct_point_candidates':4953,'manifest_sha256':sha(O/'application_manifest.json')})

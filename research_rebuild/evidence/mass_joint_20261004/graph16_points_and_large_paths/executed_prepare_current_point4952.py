import csv,json,hashlib,shutil
from pathlib import Path
from datetime import datetime,timezone
import duckdb
C=Path('/workspace/settlements-work/continuation_20261004');P=C/'regions/current_residual_own_locality_points_v1';F=C/'independent_review/current_point4984_review_v1';O=C/'root/current_point4952_manifest_preparation';assert not O.exists();O.mkdir()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return {'path':str(p),'sha256':sha(p)}
review=json.loads((F/'receipt.json').read_text());assert review['status']=='frozen_independent_current_point_candidate_review_no_application'
for p,h in review['review_artifacts'].items():assert sha(F/p)==h['sha256'],p
sources=json.loads((F/'verified_source_pins.json').read_text())
for p,h in sources.items():assert sha(p)==h['sha256'],p
summary=json.loads((F/'review_summary.json').read_text());assert summary['candidate_count']==summary['replay_hard_gate_passes']==4984 and summary['eligible_after_source_and_collision_review']==4953
eligible={r['source_record_id'] for r in csv.DictReader((F/'eligible_candidate_rows.csv').open(encoding='utf-8-sig'))};assert len(eligible)==4953
rows=[r for r in csv.DictReader((P/'current_point_candidates.csv').open(encoding='utf-8-sig')) if r['source_record_id'] in eligible];assert len(rows)==4953
m=json.loads((C/'root/point879_manifest_preparation/application_manifest.json').read_text());cfgpath=Path('/workspace/russian-settlements-research/config/mass_joint_20261004.json');cfg=json.loads(cfgpath.read_text());m['base']={k:pin(cfg[key]) for k,key in [('graph','working_identity_graph'),('points','working_point_uses')]};m['identity_sources']=[]
db=duckdb.connect(config={'threads':1,'memory_limit':'256MB'});ids=sorted(eligible)
ev={sid:json.loads(e) for sid,e in db.execute('select source_record_id,source_evidence_json from read_parquet(?) where source_record_id in(select unnest(?))',[m['frozen']['source_evidence']['path'],ids]).fetchall()};assert len(ev)==4953
holds=[];clear=[]
for r in rows:
    sid=r['source_record_id'];e=ev[sid]
    assert e['is_additive_settlement_record'] and not e.get('is_federal_aggregate') and not e.get('legacy_same_year_collision'),sid
    if e.get('legacy_verified_successor_settlement_id'):
        holds.append({'source_record_id':sid,'name':r['settlement_name'],'population_context':r['population'],'hold':'Source successor flag requires scoped interpretation; point proof alone does not waive it','successor':e['legacy_verified_successor_settlement_id']});continue
    r['point_origin_locator']=f"parquet row 1-based={r['point_origin_row_1based']}; fields=latitude_dadata,longitude_dadata; native_OKTMO={r['source_native_oktmo']}"
    r['target_year']=2021;r['coordinate_source']='DaData';r['coordinate_provider']='DaData';r['coordinate_provider_id']=r['source_raw_fias_id'];r['provider_binding_status']='verified_current_FIAS_level6_same_ID; publisher_native_OKTMO_exact_row_binding; provider_OKTMO_context_only'
    r['coordinate_quality']='automatically_accepted_checked_rule';r['coordinate_measurement_date_unknown']=True;r['direct_historical_coordinate_measurement']=False;r['census_date_point_measurement_proven']=False;r['boundary_comparability_asserted']=False
    r['source_native_id']=r['source_native_oktmo'];r['source_year_current_carrier_id']=sid
    clear.append(r)
assert len(clear)==4952 and len(holds)==1 and holds[0]['source_record_id'].endswith(':108423')
raw=m['point_sources'][0]['origin']['path'];selected=m['frozen']['selected']['path'];ids=[r['source_record_id'] for r in clear]
ss=db.execute('select source_record_id,source_native_id,census_year,population,region_raw,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))',[selected,ids]).fetch_arrow_table().to_pylist();sel={s['source_record_id']:s for s in ss};assert len(sel)==4952
rr=db.execute('select oktmo,region,population,latitude_dadata,longitude_dadata,fias_level_dadata,settlement_fias_id_dadata,fias_id_dadata,object_level from read_parquet(?) where oktmo in(select unnest(?)) and object_level=?',[raw,[s['source_native_id'] for s in ss],'Населенный пункт']).fetch_arrow_table().to_pylist();rm={r['oktmo']:r for r in rr};assert len(rm)==len(rr)==4952
for r in clear:
    s=sel[r['source_record_id']];a=rm[s['source_native_id']]
    assert s['census_year']==2021 and s['population_scope']=='settlement' and s['is_additive_settlement_record']
    assert s['population']==a['population'] and s['region_raw']==a['region'] and s['source_native_id']==r['source_native_oktmo']
    assert (a['latitude_dadata'],a['longitude_dadata'])==(float(r['current_point_latitude']),float(r['current_point_longitude']))
    assert str(a['fias_level_dadata']) in ['6','6.0'] and a['settlement_fias_id_dadata']==a['fias_id_dadata']==r['source_raw_fias_id'] and a['fias_id_dadata']
p=O/'current_point4952.csv'
with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(clear[0]),lineterminator='\n');w.writeheader();w.writerows(clear)
(O/'additional_source_flag_hold.json').write_text(json.dumps(holds,ensure_ascii=False,indent=2)+'\n')
cols={'target':'source_record_id','latitude':'current_point_latitude','longitude':'current_point_longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'}
m['point_sources']=[{'candidate':pin(p),'approved':pin(p),'review_receipt':pin(F/'receipt.json'),'origin':pin(raw),'candidate_columns':cols,'approved_columns':cols,'output_columns':{'coordinate_source_record_id':'source_year_current_carrier_id'},'output_values':{'coordinate_admission_rule':'independent_own_raw_named_FIAS6_same_UUID_publisher_native_row_rule_with_current_collisions_held_20261004','point_origin_kind':'tochno_2021_dadata_raw_parquet_point','coordinate_provenance':'Own named FIAS6 locality point, exact publisher-native row; independent all-row replay and fixed40 plus separate top15. Not a historical census-date measurement.','direct_historical_coordinate_measurement':False,'census_date_point_measurement_proven':False,'native_id_binding_asserted':False}}]
m['blocked_targets']=json.loads((C/'root/eao71_point879_manifest_preparation/application_manifest.json').read_text())['blocked_targets']
m['manifest_version']='current_point4952_on_graph15';m['reviewed_at_utc']=datetime.now(timezone.utc).isoformat();m['application_scope']='4952 own current locality points; 31 coincident current-object points and one successor-flag target held. Existing scientific fields preserved, retrospective use only along already accepted graph; no population/identity inference from QC or proximity.'
script=Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/apply_reviewed_mass_extensions_20261004.py');shutil.copyfile(script,O/script.name)
shutil.copyfile(cfgpath,O/'frozen_application_config.json')
m['review_context_inputs']=[pin(F/name) for name in ['receipt.json','review_summary.json','fixed40_independent_replay.csv','top15_independent_replay.csv','same_year_point_collisions_31.csv']]+[pin(P/'receipt.json'),pin(O/'additional_source_flag_hold.json'),pin(__file__),pin(O/script.name),pin(O/'frozen_application_config.json')]
(O/'application_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print({'ready_current_points':4952,'additional_source_holds':1,'manifest_sha256':sha(O/'application_manifest.json')})

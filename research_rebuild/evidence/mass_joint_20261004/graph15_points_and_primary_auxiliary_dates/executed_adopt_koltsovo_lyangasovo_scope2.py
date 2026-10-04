import json,hashlib,zipfile,re
from pathlib import Path
import duckdb,xlrd
from research_rebuild.mass_linkage.apply_reviewed_large_inclusion_scope_20261004 import sha, SELECTED, SELECTED_SHA
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
C=Path('/workspace/settlements-work/continuation_20261004');F=C/'independent_review/koltsovo_lyangasovo_scope2_review_v1';O=C/'root/accepted_koltsovo_lyangasovo_scope2';assert not O.exists()
review=json.loads((F/'receipt.json').read_text());assert review['status']=='frozen_independent_scope_review_candidate'
review['source_pins']={p:h['sha256'] for p,h in json.loads((F/'source_pins.json').read_text()).items()}
review['output_sha256']={p:h['sha256'] for p,h in review['artifacts'].items()}
for p,h in review['source_pins'].items():assert sha(p)==h,p
for p,h in review['output_sha256'].items():assert sha(F/p)==h,p
assert sha(SELECTED)==SELECTED_SHA
refs=json.loads((F/'accepted_scoped_inclusion_references.json').read_text());aux=[r for r in refs if r['source_record_id'].startswith('ROSSTAT2010:')];refs=[r for r in refs if r not in aux]
assert len(refs)==2 and not aux
cfg=json.loads(Path('/workspace/russian-settlements-research/config/mass_joint_20261004.json').read_text());points=cfg['working_point_uses'];graph=cfg['working_identity_graph'];db=duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
ids=sorted({r[k] for r in refs for k in ['source_record_id','old_same_year_city_proper_source_record_id','current_2021_receiver_source_record_id']})
selected={r['source_record_id']:r for r in db.execute('select source_record_id,census_year,settlement_name,settlement_type,population,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))',[str(SELECTED),ids]).fetch_arrow_table().to_pylist()}
sheet=xlrd.open_workbook('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls').sheet_by_index(0)
# Stream only seven named provider rows, retaining source bytes and line numbers.
gnpoints=[r['point_row'] for r in refs if r['point_row']['provider_feature_id']];wanted={p['provider_feature_id']:p for p in gnpoints};seen=set()
with zipfile.ZipFile(gnpoints[0]['point_origin_file']) as z:
 with z.open('RU.txt') as f:
  for i,line in enumerate(f,1):
   cols=line.decode().rstrip('\r\n').split('\t');gid=cols[0]
   if gid not in wanted:continue
   p=wanted[gid];assert gid not in seen;seen.add(gid)
   assert hashlib.sha256(line.rstrip(b'\r\n')).hexdigest()==p['point_origin_line_sha256']
   p['point_origin_line_sha256_basis']='UTF-8 provider line without CR/LF'
   p['point_origin_rawline_sha256']=hashlib.sha256(line).hexdigest()
   assert f'RU.txt:line={i};geonameid={gid}'==p['point_origin_locator']
   assert cols[6]=='P' and cols[7].startswith('PPL') and cols[8]=='RU'
   assert (float(cols[4]),float(cols[5]))==(float(p['latitude']),float(p['longitude']))
assert seen==set(wanted)
for r in refs:
 sid=r['source_record_id'];s=selected[sid];p=r['point_row'];parent=selected[r['old_same_year_city_proper_source_record_id']];receiver=selected[r['current_2021_receiver_source_record_id']]
 assert (s['census_year'],s['settlement_type'],int(s['population']))==(2002,'пгт',r['population'])
 assert s['population_scope']=='settlement' and s['is_additive_settlement_record']
 raw=sheet.row_values(int(sid.rsplit(':',1)[1])-1);assert raw[0].strip()=='пгт '+s['settlement_name'] and int(raw[1])==r['population']
 assert parent['census_year']==2002 and parent['settlement_type']=='город' and parent['is_additive_settlement_record'] and parent['population_scope']=='settlement'
 assert receiver['census_year']==2021 and receiver['settlement_type']=='город' and receiver['is_additive_settlement_record'] and receiver['population_scope']=='settlement'
 assert int(receiver['population'])==r['current_receiver_population_context_only']
 use=db.execute('select latitude,longitude,coordinate_admission_status from read_parquet(?) where target_source_record_id=?',[points,receiver['source_record_id']]).fetchall();assert len(use)==1 and use[0][2] in ACCEPTED_COORDINATE_STATUSES
 assert db.execute('select count(*) from read_parquet(?) where from_source_record_id=? and to_source_record_id=?',[graph,parent['source_record_id'],receiver['source_record_id']]).fetchone()[0]>0
 assert r['status']=='secondary_reported_inclusion_context_only' and not r['population_additive'] and not r['ordinary_same_place_claim'] and not r['current_child_population_asserted']
 assert sha(p['point_origin_file'])==p['point_origin_sha256']
 if not p['provider_feature_id']:
  entity=json.loads(Path(p['point_origin_file']).read_text())['entities'][p['historical_place_qid']];claims=[x for x in entity['claims']['P625'] if x.get('rank')!='deprecated' and x['id']==p['wikidata_point_claim_guid']];assert len(claims)==1
  value=claims[0]['mainsnak']['datavalue']['value'];assert value['globe']=='http://www.wikidata.org/entity/Q2'
  # Prior handoff serialized this point to eight decimal places.
  assert abs(value['latitude']-float(p['latitude']))<=1e-7 and abs(value['longitude']-float(p['longitude']))<=1e-7
 r['evidence_pins']['independent_review_receipt_sha256']=sha(F/'receipt.json');r['evidence_pins']['legal_acts_independently_verified']=False

O.mkdir();outputs={'accepted_scoped_inclusion_references.json':refs,'accepted_scoped_point_uses.json':[r['point_row'] for r in refs],'accepted_auxiliary_observations_no_national_credit.json':aux}
for name,data in outputs.items():(O/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
receipt={'status':'applied_reviewed_secondary_reported_large_inclusion_references','observation_references':2,'new_scoped_point_uses':2,'old2002_existing_population_reference_sum':sum(r['population'] for r in refs),'ordinary_NP3_admission':False,'source_population_values_modified':False,'current_child_population_asserted':False,'parent_population_transfer':False,'modern_boundary_harmonized':False,'legal_acts_independently_verified':False,'auxiliary2010_observations_not_nationally_added':0,'inputs':{str(F/'receipt.json'):sha(F/'receipt.json'),str(SELECTED):SELECTED_SHA,points:sha(points),graph:sha(graph)},'frozen_review_pins':review['source_pins'],'outputs':{name:sha(O/name) for name in outputs},'script_sha256':sha(__file__)}
(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in receipt.items() if k not in ['inputs','outputs','frozen_review_pins']})

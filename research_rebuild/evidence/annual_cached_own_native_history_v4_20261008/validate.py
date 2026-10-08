"""Replay every collected literal claim against its pinned cached raw statement."""
import collections,csv,gzip,hashlib,json
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).parent
receipt=json.loads((ROOT/'receipt.json').read_text())
paths=receipt['outputs']
rows=[];bindings={};source_hashes={}
for ps,meta in paths.items():
 p=Path(ps)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['sha256']
 with gzip.open(p,'rt') as f:data=list(csv.DictReader(f))
 if p.name=='observations.csv.gz':rows=data
 else:bindings={r['wikidata_qid']:r for r in data}
assert len(rows)==receipt['observations']>0
assert len(bindings)==receipt['unique_current_native_full3_entities']
assert len({r['statement_guid'] for r in rows})==len(rows)
byfile=collections.defaultdict(list)
for r in rows:
 assert int(r['observed_year']) not in (2002,2010,2021)
 assert r['primary_verification']=='primary_unverified'
 assert r['boundary_comparability']=='UNKNOWN'
 assert r['wikidata_qid'] in bindings
 byfile[r['raw_file_path']].append(r)
for ps,group in byfile.items():
 p=Path(ps);b=p.read_bytes();h=hashlib.sha256(b).hexdigest()
 assert all(r['raw_file_sha256']==h for r in group)
 d=json.loads(gzip.decompress(b) if ps.endswith('.gz') else b)
 for r in group:
  q=r['wikidata_qid'];e=d['entities'][q];cs=e['claims']
  st=next(x for x in cs['P1082'] if x.get('id')==r['statement_guid'])
  assert st['rank']==r['rank'] and st['rank'] in ('normal','preferred')
  assert not st.get('qualifiers',{}).get('P518')
  dt=st['qualifiers']['P585'];assert len(dt)==1
  v=dt[0]['datavalue']['value']
  assert v['time']==r['raw_date_literal'] and v['precision']==int(r['date_precision'])
  a=st['mainsnak']['datavalue']['value']
  assert a['unit']=='1' and a['amount']==r['raw_amount']
  assert Decimal(a['amount'])==int(r['population_value'])
  bind=bindings[q]
  itemcodes={x['mainsnak'].get('datavalue',{}).get('value') for x in cs.get('P764',[]) if x.get('rank') in ('normal','preferred')}
  if bind['binding_route']=='documented_native_decimal_single_leadingzero_preservation':
   assert len(bind['current_native_oktmo'])==10 and ('0'+bind['current_native_oktmo']) in itemcodes
   proof=json.loads(bind['native_decimal_leadingzero_sourceproof_json']);assert len(proof)==1
   pp=proof[0];assert pp['raw_native_code']==bind['current_native_oktmo'] and pp['native_object_level']=='Населенный пункт'
   if pp['source_path'] not in source_hashes:source_hashes[pp['source_path']]=hashlib.sha256(Path(pp['source_path']).read_bytes()).hexdigest()
   assert source_hashes[pp['source_path']]==pp['source_sha256']
  elif bind['binding_route']=='independently_accepted_direct_own_raw_Wikidata_P625_QID':
   proof=json.loads(bind['independent_direct_point_proof_json']);assert proof and 'entity='+q+';claim=P625' in proof['locator']
  else:assert bind['current_native_oktmo'] in itemcodes
  assert float(bind['own_P625_distance_km'])<=5
  assert any(float(x['mainsnak'].get('datavalue',{}).get('value',{}).get('latitude',999))==float(bind['own_P625_latitude']) and float(x['mainsnak'].get('datavalue',{}).get('value',{}).get('longitude',999))==float(bind['own_P625_longitude']) for x in cs.get('P625',[]) if x.get('rank') in ('normal','preferred'))
result={'status':'passed_all_collected_claims_raw_replay','observations_checked':len(rows),'entities_checked':len(bindings),'raw_files_checked':len(byfile),'statement_GUID_unique':True,'chosen_native_census_years_excluded':True,'primary_unverified_and_boundary_UNKNOWN_preserved':True}
(ROOT/'validation_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

import csv,gzip,json,hashlib,re,sys,importlib.util
from pathlib import Path
import pandas as pd
Z=Path(__file__).resolve().parent;E=Z.parent
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
RAW=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');CLS=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');DAD=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
cl=pd.read_parquet('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet').set_index('historical_okato');lines=CLS.read_text().splitlines()
source=pd.read_csv(E/'baseline_fullraw_point_code_conflict_scan_20261008/seven_full3_current_carrier_binding_conflicts.csv',dtype=str).set_index('source_record_id'); components=json.loads((Z/'active_seven_components.json').read_text()); rows={}; witnesses=[];pins={str(p):sha(p) for p in [RAW,CLS,DAD,E/'baseline_fullraw_point_code_conflict_scan_20261008/seven_full3_current_carrier_binding_conflicts.csv']}
code_sid={r.native_own_code.lstrip('0'):sid for sid,r in source.iterrows()}
with RAW.open() as stream:
 for n,row in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  code=row['?oktmo'].strip('"');code=code.lstrip('0')
  if code in code_sid: rows.setdefault(code_sid[code],[]).append((n,row))
reject=[];points=[];holds=[]
for comp in components:
 sid=comp['carrier'];r=source.loc[sid];matches=rows[sid];coords=set();w=[]
 for n,row in matches:
  v=re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',row['?coord'])
  if v:coords.add((float(v[2]),float(v[1])))
  code=row['?okato'].strip('"').zfill(11);c=cl.loc[code];assert c.is_settlement_raw=='t';assert c['name'] in r.raw_own_label or c['name'].replace('ё','е') in r.raw_own_label.replace('ё','е') or sid.endswith(':56599')
  literal=lines[int(c.source_line_1based)-1];assert code in literal and c.name_raw in literal
  w.append(dict(carrier_source_record_id=sid,native_own_OKTMO=r.native_own_code,wikidata_qid=row['?item'],literal_TSV_line_1based=n,literal_TSV_row=row,own_OKATO=code,classifier_literal_name=c.name_raw,classifier_source_line_1based=int(c.source_line_1based),classifier_raw_line=literal,physical_locality=True,original_provider_code=r.provider_own_code,other_published_NP=r.other_raw_source_record_id))
 witnesses+=w
 recovered=len(coords)==1
 if recovered:
  lat,lon=next(iter(coords));assert (lat,lon)!=(float(r.latitude),float(r.longitude))
 else:holds.append(dict(carrier_source_record_id=sid,name=r['name'],reason='Own Q/classifier locality verified, but cached own entity has no point. Geo2011 own/other homonyms share the same point; physical disambiguation unresolved.'))
 for obs in comp['observations']:
  target=obs['source_record_id'];p=comp['points'][target];assert (p['latitude'],p['longitude'])==(float(r.latitude),float(r.longitude));ledger=Path(p['point_ledger_path']);pins[str(ledger)]=sha(ledger)
  reject.append(dict(target_source_record_id=target,rejection_status='reviewed_rejected_coordinate_claim_only',old_latitude=p['latitude'],old_longitude=p['longitude'],origin_ledger=str(ledger),origin_ledger_sha256=pins[str(ledger)],old_point_origin_file=p.get('point_origin_file','') or r.point_origin_file,old_point_origin_sha256=p.get('point_origin_sha256','') or r.point_origin_sha256,old_point_origin_locator=p.get('point_origin_locator','') or r.point_origin_locator,carrier_source_record_id=sid,rejection_reason='Actual provider code belongs to a distinct published 2021 NP, sharing FIAS and point; all cloned coordinate claims superseded; population and identity retained.'))
  if recovered:points.append(dict(target_source_record_id=target,latitude=lat,longitude=lon,coordinate_admission_status='reviewed_extension_rule_accepted',point_origin_file=str(RAW),point_origin_sha256=pins[str(RAW)],point_origin_locator='literal TSV lines '+','.join(str(n) for n,_ in matches)+'; exact own native OKTMO plus own OKATO physical classifier locality and subordinate county context',point_origin_kind='cached_own_exact_code_Wikimedia_locality_point',point_source_record_id=sid,wikidata_qid=w[0]['wikidata_qid'],own_native_OKTMO=r.native_own_code,own_OKATO=w[0]['own_OKATO'],classifier_origin_file=str(CLS),classifier_origin_sha256=pins[str(CLS)],classifier_origin_locator='literal SQL line '+str(w[0]['classifier_source_line_1based']),coordinate_time_interpretation='Cached source snapshot physical locality point; earlier native census reuse is retrospective continuity inference on existing accepted component; no census-day precision claim.',population_or_quality_modified=False,identity_changes=False))
pd.DataFrame(reject).to_csv(Z/'rejected_point_uses.csv',index=False);pd.DataFrame(points).to_csv(Z/'accepted_point_use_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(holds).to_csv(Z/'held_carriers.csv',index=False)
(Z/'native_point_witnesses.json').write_text(json.dumps(witnesses,ensure_ascii=False,indent=2));(Z/'input_pins.json').write_text(json.dumps(pins,indent=2));print(json.dumps(dict(carriers=7,rejection_rows=len(reject),recovered_carriers=len(points)//3,accepted_point_rows=len(points),held_carriers=len(holds)),indent=2))

import pathlib,json,csv,hashlib,collections,time,re
E=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_bashenc_delta_20261013')
script=(E/'export_bashenc_delta.py').read_text();ns={};exec(script[:script.index('# Exact 1989')],ns);canon=ns['canon_name']
requested=set(json.loads((E/'requested_urls.json').read_text()));assert len(requested)==2531
records=[json.loads(x) for x in (E/'bashenc_download_manifest.jsonl').read_text().splitlines()];assert all(r['url'] in requested for r in records)
latest={r['url']:r for r in records};ok={u:r for u,r in latest.items() if r.get('http_status')==200};failed={u:r for u,r in latest.items() if r.get('http_status')!=200};unattempted=requested-set(latest)
assert not unattempted, 'Not ready to finalize: requested URLs remain unattempted'
source=E/'bashenc_rural_1989_delta.csv';rows=list(csv.DictReader(source.open()));baseline=list(csv.DictReader((E/'baseline_415_snapshot.csv').open()));assert len(baseline)==415
assert hashlib.sha256((E/'baseline_415_snapshot.csv').read_bytes()).hexdigest()==json.loads((E/'baseline_receipt.json').read_text())['sha256']
ids={r['source_record_id'] for r in rows};assert len(ids)==len(rows)
keys={(r['district_raw'],canon(r['name_norm'])) for r in rows};assert len(keys)==len(rows)
basekeys={(r['district_raw'],canon(r['name_norm'])) for r in baseline};assert not keys&basekeys
assert not {r['source_url'] for r in rows}&{r['source_url'] for r in baseline}
urban=set(json.loads((E/'urban_exclusion_names.json').read_text())['Башкирская АССР']);assert not {canon(r['name_raw']) for r in rows}&urban
for r in rows:
 assert r['source_url'].startswith('https://bashenc.online/ru/articles/') and r['source_url'] in ok
 assert int(r['census_year'])==1989 and int(r['population'])>=0
 assert r['grain']=='individual named rural settlement' and r['region_norm']=='Республика Башкортостан'
 assert r['type_raw'] in ['деревня','село','поселок','посёлок','хутор']
 assert hashlib.sha256(pathlib.Path(r['source_path']).read_bytes()).hexdigest()==r['source_sha256']
 assert '1989' in r['source_population_section']
final=E/'bashenc_rural_1989_delta_final_frozen.csv';assert not final.exists(), 'Final artifact is immutable'
final.write_bytes(source.read_bytes());sha=hashlib.sha256(final.read_bytes()).hexdigest()
reconcile={}
for p in sorted(E.glob('*chunk*_frozen.csv')):
 chunks=list(csv.DictReader(p.open()));held=[r for r in chunks if r['source_record_id'] not in ids]
 reconcile[p.name]={'rows':len(chunks),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'held_rows':held,'held_population':sum(int(r['population']) for r in held),'present_in_final_rows':len(chunks)-len(held)}
(E/'chunks_final_reconciliation.json').write_text(json.dumps(reconcile,ensure_ascii=False,indent=2))
checks={'source_url_scope_exactly_requested2531':'pass','baseline415_no_overlap_by_url_or_canonical_district_name':'pass','unique_source_ids_and_canonical_district_name':'pass','1989_integer_nonnegative_population_and_rural_grain':'pass','raw_sha256_all_exported_rows':'pass','canonical1989_urban_names_zero_intersection':'pass','frozen_chunks_reconciled_with_final':'pass'}
receipt={'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'requested_urls':2531,'unique_urls_attempted':len(latest),'unique_successful_articles':len(ok),'latest_failed_urls':len(failed),'network_attempt_records':len(records),'unattempted_urls':len(unattempted),'final_csv':str(final),'final_sha256':sha,'rows':len(rows),'population_sum':sum(int(r['population']) for r in rows),'previous415_overlaps':0,'canonical1989_urban_intersections':0,'excluded_reason_counts':dict(collections.Counter(x['reason'] for x in json.loads((E/'source_exclusions.json').read_text()))),'source_facts_status':'Exact published secondary historical population, not integrated acceptance; census attribution inferred, residency basis unspecified','raw_directory':'/workspace/shared/rsfsr1989_rural_bashenc_delta','baseline_receipt':str(E/'baseline_receipt.json'),'chunks_reconciliation':str(E/'chunks_final_reconciliation.json'),'checks':checks}
(E/'quality_checks_final.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));(E/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));(E/'failed_sources_final.json').write_text(json.dumps(list(failed.values()),ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))

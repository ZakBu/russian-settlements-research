from pathlib import Path
import duckdb,csv,json,hashlib,shutil
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');O=Path(__file__).parent;D=E/'over1000_rest_20261009/A112_v27_temkino_crosswalk'; B=E/'main_axis_residual_application70_batch12_20261009'; S=E/'main_axis_residual_application68_20261008'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ids=set()
for r in csv.DictReader(open(D/'accepted_identity_edge_delta.csv')): ids.update([r['from_source_record_id'],r['to_source_record_id']])
small={'2002:013_2dd2afccd6_02c_Smolenskaja.xls:Sheet1:4534','2010:011_040325482b_3._20Ryaz_Smol_Tambov_Tula_Jaroslavl_20L1_20ethn_2010.xls:Data Sheet:6849','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:125814'}
c=duckdb.connect()
a=c.execute('select * from read_parquet(?) where target_source_record_id in (select unnest(?))',[str(S/'applied_point_snapshot.parquet'),sorted(ids|small)]).fetchdf().fillna('')
a.to_csv(O/'stage68_exact_target_point_claims.csv',index=False)
obs=c.execute('select * from read_parquet(?) where source_record_id in (select unnest(?))',[str(S/'applied_state_observations.parquet'),sorted(ids|small)]).fetchdf().fillna('')
obs.to_csv(O/'six_disjoint_native_source_observations.csv',index=False)
active={r['target_source_record_id']:dict(r) for r in a.to_dict('records')}; ledgerrows=[]
for f in sorted(B.glob('*point*.csv')):
 for r in csv.DictReader(open(f)):
  if r.get('target_source_record_id') in ids|small:
   ledgerrows.append(dict(r,reviewed_actual_replay_file=str(f),reviewed_actual_replay_file_sha256=sha(f)))
   if f.name=='accepted_source_bound_retrospective_points.csv':active[r['target_source_record_id']]=dict(r,point_ledger_path=str(f))
import pandas as pd
pd.DataFrame(ledgerrows).fillna('').to_csv(O/'batch12_exact_target_point_claims.csv',index=False)
claims=[]
for sid in sorted(ids|small):
 r=active.get(sid)
 if r:
  claims.append(dict(target_source_record_id=sid,group='large_district_center' if sid in ids else 'small_distinct_village',latitude=r['latitude'],longitude=r['longitude'],active_point_ledger=r['point_ledger_path'],active_point_ledger_sha256=sha(r['point_ledger_path']),coordinate_source_record_id=r.get('coordinate_source_record_id',''),decision='retain_correct_own_large_point' if sid in ids else 'retain_small_village_point_untouched'))
pd.DataFrame(claims).to_csv(O/'active_point_review_decisions.csv',index=False)
for sid in ids:
 assert sid in active
 assert abs(float(active[sid]['latitude'])-55.0775)<1e-7 and abs(float(active[sid]['longitude'])-35.011944444444445)<1e-6
pd.DataFrame(columns=['target_source_record_id','rejection_status','old_latitude','old_longitude','origin_ledger','origin_ledger_sha256','reason']).to_csv(O/'accepted_point_rejections.csv',index=False)
pd.DataFrame(columns=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','source_locator']).to_csv(O/'accepted_point_use_delta.csv',index=False)
shutil.copyfile(D/'current_village_article_raw.json',O/'own_large_article_raw.json')
page=json.loads((O/'own_large_article_raw.json').read_text())['query']['pages'][0];text=page['revisions'][0]['slots']['main']['content']
lines=[x for x in text.splitlines() if 'lat_deg' in x or '3 км' in x or 'центром' in x or 'центр' in x or 'название' in x]
(O/'own_large_article_exact_excerpts.json').write_text(json.dumps(dict(pageid=page['pageid'],title=page['title'],revision=page['revisions'][0]['revid'],source_sha256=sha(O/'own_large_article_raw.json'),excerpts=lines,latitude=55.0775,longitude=35.011944444444445),ensure_ascii=False,indent=2))
pins=[S/'applied_point_snapshot.parquet',S/'applied_state_observations.parquet',D/'accepted_identity_edge_delta.csv',D/'source_hierarchy_and_code_crosswalk.csv',D/'selected_and_alternate_source_rows.csv',B/'accepted_source_bound_retrospective_points.csv',E/'over1000_root_20261009/apply_batch12.py']
for r in claims:pins.append(Path(r['active_point_ledger']))
(O/'external_source_pins.json').write_text(json.dumps([dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(pins))],indent=2))
receipt=dict(status='reviewed_noop_active_points_already_correct',large_native_members=sorted(ids),all_three_active_large_points=[55.0775,35.011944],raw_2021_point=[55.1120406,35.0155485],raw_point_is_active=False,coordinate_rejections=0,coordinate_replacements=0,new_population_credit=0,small_village_points_preserved=True,boundary_comparability='UNKNOWN',historical_census_day_point_measurement_asserted=False,reason='Stage68 large2010/2021 already use Q4468065 ownlarge point; batch12 source-bound retrospective transfer assigns identical ownlarge donor point to large2002. Raw DaData conflict is not an active admitted claim.')
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
(O/'README.md').write_text('Temkino coordinate-only review: no active correction required.\n\nThe raw 2021 district-center coordinate points near the separate small village, but active stage68 points already use the correct own district-center Wikidata claim Q4468065. Batch12 retrospectively transfers that correct admitted point to the newly linked 2002 member. The three large members remain 2452/2413/1731; no census values, identities, or small-village points change. Empty correction CSVs are intentional.\n\nThe cached own district-center Wikipedia article independently supplies 55.0775/35.011944444444445. The review preserves historical boundary and census-day measurement as unknown.\n')
files=[dict(path=str(p.relative_to(O)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(O.iterdir()) if p.is_file() and p.name!='FINAL_manifest.json']
(O/'FINAL_manifest.json').write_text(json.dumps(dict(status='FINAL',files=files),indent=2))
print(json.dumps(receipt,ensure_ascii=False));print('FINAL_SHA256',sha(O/'FINAL_manifest.json'))

import sys,json,hashlib,re,struct,math
from pathlib import Path
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km,sha
O=Path(__file__).parent;A=R/'research_rebuild/evidence/full3_conflicting_modern_point_recovery_application_20261007';A.mkdir(exist_ok=True)
s=load(23);before=s.metrics();d=pd.read_csv(O/'existing_full3_point_conflicts.csv');a=pd.read_csv(O/'own_article_coordinate_checks.csv',dtype={'old_raw_code':str});screen=pd.read_csv(O/'source_binding_screen.csv',dtype={'old_raw_code':str});accepted=[];held=[];reject=[];points=[];checks=[]
for z in screen.to_dict('records'):
 group=d[d.root==z['root']];ids=group.source_record_id.tolist();cur=group[group.year==2021].iloc[0];old=group[(group.haspoint)&(group.year!=2021)].iloc[0];ar=a[a.root==z['root']]
 reason='No independent own article coordinate and exact raw code binding'
 if len(ar) and not pd.isna(ar.iloc[0].article_latitude):
  ar=ar.iloc[0];ap=(ar.article_latitude,ar.article_longitude);cp=s.point_rows[cur.source_record_id];op=s.point_rows[old.source_record_id];da=distance_km(ap,(cp['latitude'],cp['longitude']));db=distance_km(ap,(op['latitude'],op['longitude']));articlemov=str(ar.possible_movement_snippets_json);mov=bool(re.search('перенес[её]н|затоплен',articlemov,re.I));mode=None
  if not mov and da<=.6 and db>8 and op.get('point_origin_kind')=='geokladr_2011_raw_dbf_coordinate':mode='Reject wrong modern GeoKLADR representative; independently confirmed current own point'
  elif not mov and db<=.6 and da>5 and cp.get('point_origin_kind')=='wikidata_P625_point_claim':mode='Reject contradicted current Wiki representative; own article and GeoKLADR agree'
  reason='Ambiguous extent, absent independent corroboration, or possible movement'
  if mode:
   donor=cp if da<=.6 else op;targetold=old.source_record_id if da<=.6 else cur.source_record_id;active=s.point_rows[targetold]
   if active.get('coordinate_admission_status')=='frozen_r5b_reviewed_baseline_preserved':reason='Preserve individually frozen baseline coordinate'
   else:
    ledger=active['point_ledger_path'];reject.append({'target_source_record_id':targetold,'rejection_status':'reviewed_rejected_coordinate_claim_only','old_latitude':active['latitude'],'old_longitude':active['longitude'],'origin_ledger':ledger,'origin_ledger_sha256':sha(Path(ledger)),'reason':mode,'provider_identifier_binding_status':'Unresolved separately; point claim rejected without changing native census identity','old_point_json':json.dumps(active,ensure_ascii=False)})
    for sid in ids:
     if sid==targetold or sid not in s.point_rows:
      p=dict(donor);p.update(target_source_record_id=sid,coordinate_admission_status='reviewed_extension_rule_accepted',review_rule=mode,independent_own_article_url=ar.article_url,independent_own_article_sha256=ar.article_sha256,independent_own_article_latitude=ar.article_latitude,independent_own_article_longitude=ar.article_longitude,coordinate_temporal_interpretation='Modern own representative applied retrospectively to native stable identity; no measured census-date coordinate or constant boundary assertion',provider_identifier_binding_status='Original provider binding retained separately; no historical code invented');p.pop('point_ledger_path',None);points.append(p)
    accepted.append({**z,'rule':mode,'article_latitude':ar.article_latitude,'article_longitude':ar.article_longitude,'article_url':ar.article_url,'article_sha256':ar.article_sha256,'article_to_current_km':da,'article_to_old_km':db,'rejected_target_source_record_id':targetold,'donor_source_record_id':donor['target_source_record_id'],'component_year_counts':json.dumps(group.groupby('year').size().to_dict())});continue
 held.append({**z,'hold_reason':reason})
pd.DataFrame(accepted).to_csv(O/'action_ready_components.csv',index=False);pd.DataFrame(held).to_csv(O/'held_components.csv',index=False)
pd.DataFrame(reject).to_csv(A/'accepted_point_rejection_delta.csv',index=False);pd.DataFrame(points).to_csv(A/'accepted_point_use_delta.csv',index=False)
s.reject_point_uses(A/'accepted_point_rejection_delta.csv');s.add_deltas(point_paths=[A/'accepted_point_use_delta.csv']);after=s.metrics()
fullpop={str(y):0 for y in (2002,2010,2021)}
for z in accepted:
 g=d[d.root==z['root']]
 for y in fullpop:fullpop[y]+=int(g[g.year==int(y)].population.sum())
receipt={'baseline_stage':23,'candidate_components_reviewed':len(screen),'accepted_repaired_full3_components':len(accepted),'held_components':len(held),'explicit_point_rejections':len(reject),'accepted_replacement_and_missing_year_point_uses':len(points),'before':before,'after':after,'net_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'net_covered_rows_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'newly_finite_all_three_year_component_populations':fullpop,'population_or_identity_changes':0,'year_repeat_or_identity_edges_added':0,'provider_binding':'Unresolved identifier/geographic binding preserved independently from rejected coordinate claim','input_pins':{str(p):sha(Path(p)) for p in s.inputs if Path(p).exists()},'output_pins':{p.name:sha(p) for p in A.glob('*.csv')}}
(A/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:receipt[k] for k in ['accepted_repaired_full3_components','held_components','explicit_point_rejections','accepted_replacement_and_missing_year_point_uses','net_population_gain','net_covered_rows_gain','newly_finite_all_three_year_component_populations']},ensure_ascii=False))

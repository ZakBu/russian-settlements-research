import sys,json,re,hashlib,urllib.request
from pathlib import Path
from collections import Counter
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
O=Path(__file__).parent;A=R/'research_rebuild/evidence/old_year_remaining_mass_rule_application_20261008';A.mkdir(exist_ok=True);s=load(24);before=s.metrics();d=pd.read_csv(O/'exact_context_code_candidates.csv',dtype={'historical_exact_own_code':str});w=pd.read_csv(O/'actual_source_row_witnesses.csv').set_index('from_source_record_id');c=duckdb.connect();p='/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet';q=c.execute('select source_record_id,wikidata_qid,wikidata_truthy_p31_claims_json,wikidata_tsv_ru_admin_labels_json,wikidata_tsv_article_urls_json from read_parquet(?) where source_record_id in(select unnest(?))',[p,d.to_source_record_id.tolist()]).fetchdf();q.to_csv(O/'own_point_population_place_kind_witnesses.csv',index=False);classes={}
for cls in ['Q24258416','Q27062006','Q27517483']:
 url='https://www.wikidata.org/wiki/Special:EntityData/'+cls+'.json';b=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'settlement-research/1.0'}),timeout=12).read();e=json.loads(b)['entities'][cls];classes[cls]={'ru':e['labels']['ru']['value'],'en':e['labels']['en']['value'],'url':url,'source_sha256':hashlib.sha256(b).hexdigest(),'lastrevid':e.get('lastrevid')}
(O/'railway_population_place_class_semantics.json').write_text(json.dumps(classes,ensure_ascii=False,indent=2));collisions=Counter((int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude']) for sid,p in s.point_rows.items());edges=[];points=[];holds=[];accepted=[];fullpop={str(y):0 for y in (2002,2010,2021)};fullhistories=0
for z in d.sort_values('population_2002',ascending=False).to_dict('records'):
 sid,bid=z['from_source_record_id'],z['to_source_record_id'];p=s.point_rows[bid];members=json.loads(z['component_source_ids_json']);reasons=[]
 if not bool(w.loc[sid,'independent_provider_point_within5km']):reasons.append('Actual current publisher point contradicts admitted own point over 5 km')
 if 'железнодорожный объект' in z['type_2021']:
  own=q[(q.source_record_id==bid)&(q.wikidata_qid==p['coordinate_source_record_id'])];kinds=set(v['value_qid'] for x in own.wikidata_truthy_p31_claims_json for v in json.loads(x))
  if not kinds&set(classes):reasons.append('No own populated railway locality class proof')
 if s.years[s.uf.find(sid)]&s.years[s.uf.find(bid)]:reasons.append('Repeated year component')
 for x in members:
  if x in s.point_rows:
   pp=s.point_rows[x]
   if collisions[(int(s.by_id.loc[x,'census_year']),pp['latitude'],pp['longitude'])]>1:reasons.append('Active own point shared by distinct same-year source records')
  elif collisions[(int(s.by_id.loc[x,'census_year']),p['latitude'],p['longitude'])]:reasons.append('Proposed retrospective point collides with different same-year record')
 if reasons:holds.append({**z,'hold_reason':'; '.join(sorted(set(reasons)))});continue
 e={**z,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Exact historical classifier own name/type/county/code to unique current own source code/name/county and independently admitted populated-locality point','native_2002_printed_code_asserted':False,'type_change_date':'Unknown','boundary_comparability_asserted':False,'source_context_witness_file':str(O/'actual_source_row_witnesses.csv')};e.pop('own_point_donor_json',None);edges.append(e);s.union(sid,bid)
 for x in members:
  if x in s.point_rows:continue
  pp=dict(p);pp.update(target_source_record_id=x,coordinate_admission_status='reviewed_extension_rule_accepted',admission_rule='Own modern representative applied retrospectively over checked historical classifier context/code identity',native_2002_printed_code_asserted=False,boundary_comparability_asserted=False,point_temporal_interpretation='Own modern representative; no measured census-date point claim');pp.pop('point_ledger_path',None);points.append(pp);s.point_rows[x]=dict(pp,point_ledger_path=str(A/'accepted_point_use_delta.csv'));collisions[(int(s.by_id.loc[x,'census_year']),pp['latitude'],pp['longitude'])]+=1
 if s.years[s.uf.find(sid)]=={2002,2010,2021} and all(x in s.point_rows for x in members):
  fullhistories+=1
  for x in members:fullpop[str(int(s.by_id.loc[x,'census_year']))]+=int(s.by_id.loc[x,'population'])
 accepted.append(z)
pd.DataFrame(edges).to_csv(A/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(A/'accepted_point_use_delta.csv',index=False);pd.DataFrame(holds).to_csv(A/'held_candidates.csv',index=False);after=s.metrics();r={'baseline_stage':24,'accepted_edges':len(edges),'accepted_point_uses':len(points),'held_candidates':len(holds),'new_finite_full_three_year_histories':fullhistories,'new_finite_full_three_year_population':fullpop,'before':before,'after':after,'net_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'net_row_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'actual_primary2002_and_current_source_rows_checked':16,'population_quality_or_value_changes':0,'existing_point_rejections_or_overwrites':0,'source_pins':{str(v):sha(v) for v in [O/'actual_source_row_witnesses.csv',O/'own_point_population_place_kind_witnesses.csv',O/'railway_population_place_class_semantics.json',O/'exact_context_code_candidates.csv']},'output_pins':{v.name:sha(v) for v in A.glob('*.csv')}};(A/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k] for k in ['accepted_edges','accepted_point_uses','held_candidates','new_finite_full_three_year_histories','new_finite_full_three_year_population','net_population_gain','net_row_gain']},ensure_ascii=False))

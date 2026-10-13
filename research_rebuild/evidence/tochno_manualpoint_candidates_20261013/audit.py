import duckdb,csv,json,hashlib,math,collections
from pathlib import Path
O=Path(__file__).parent;P=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');Q=P.parent/'applied_core_point_snapshot.parquet';A=Path('/workspace/scratch/tochno-np-attach-20261013/native_np_latest_all_attributes.parquet');PDF=Path('/workspace/shared/tochno-20261013/allsettlements_v20260925/description_allsettlements_156_v20260925.pdf')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
c=duckdb.connect();c.execute('set threads=2');c.execute("create view d as select * from read_parquet('"+str(P)+"')")
c.execute("create table roots as select root,count(*) n,count(distinct census_year) ny,bool_and(is_additive_settlement_record and effective_population is not null and isfinite(effective_population)) ordinary,count(*) filter(where accepted_point_present) np from d group by root")
q="""select d.* from d join roots using(root) where n=3 and ny=3 and ordinary and np between 1 and 2 and region_norm not in ('москва','санкт петербург','севастополь','крым') order by root,census_year"""
cur=c.execute(q);rows=[dict(zip([t[0] for t in cur.description],r)) for r in cur.fetchall()];groups=collections.defaultdict(list)
for r in rows:groups[r['root']].append(r)
print('candidate_roots',len(groups),'rows',len(rows),flush=True)
cur=c.execute('select p.* from read_parquet(?) p join d using(source_record_id) join roots using(root) where n=3 and ny=3 and ordinary and np between 1 and 2',[str(Q)]);pts={r[0]:dict(zip([t[0] for t in cur.description],r)) for r in cur.fetchall()}
collisions=collections.Counter(c.execute('select census_year,accepted_latitude,accepted_longitude from d where accepted_point_present').fetchall());inputs={str(x):sha(x) for x in [P,Q,A,PDF]}
eventids=set()
for p in O.parent.rglob('*.csv'):
 if not any(x in p.name for x in ('event','inclusion','included_in')) or not any(x in p.name for x in ('accepted','applied')):continue
 try:
  with p.open() as f:
   for r in csv.DictReader(f):
    for k,v in r.items():
     if v and ('source_record_id' in k or k in ('source_id','target_id')):eventids.add(v)
  inputs[str(p)]=sha(p)
 except (UnicodeDecodeError,csv.Error):pass

def distance(a,b):
 x,y,u,v=map(math.radians,[*a,*b]);return 12742*math.asin(min(1,math.sqrt(math.sin((u-x)/2)**2+math.cos(x)*math.cos(u)*math.sin((v-y)/2)**2)))
def valid(a):return all(isinstance(x,(int,float)) and math.isfinite(x) for x in a) and -90<=a[0]<=90 and -180<=a[1]<=180 and a!=(0,0)
accepted=[];held=[];witness=[];newcredit=[]
for root,rs in groups.items():
 donors=[r for r in rs if r['accepted_point_present']];donor=donors[-1];dp=pts.get(donor['source_record_id']);reason=None
 if not dp:reason='accepted_snapshot_missing'
 if any(r['source_record_id'] in eventids for r in rs):reason='accepted_event_endpoint'
 if any('(часть' in (r['settlement_name'] or '').lower() or 'часть' in (r['population_scope'] or '').lower() or r['population_value_quality'] in ('aggregate','duplicate') for r in rs):reason='part_scope_or_aggregate'
 if any(r['name_norm']!=donor['name_norm'] or r['region_norm']!=donor['region_norm'] for r in rs):reason='accepted_name_change_requires_separate_scope_review'
 if not reason:
  xy=dp['latitude'],dp['longitude']
  for r in rs:
   if r['accepted_point_present']:
    acceptedxy=r['accepted_latitude'],r['accepted_longitude']
    if distance(xy,acceptedxy)>5:reason='accepted_point_disagreement'
    if collisions[(r['census_year'],*acceptedxy)]>1:reason='shared_existing_point'
   else:
    if collisions[(r['census_year'],*xy)]>0:reason='target_year_coordinate_collision'
   rawxy=r['latitude'],r['longitude']
   if valid(rawxy) and distance(xy,rawxy)>5:reason='raw_point_contradiction'
 if reason:
  held.append({'root':root,'reason':reason});continue
 for r in rs:
  if r['accepted_point_present']:continue
  row={'target_source_record_id':r['source_record_id'],'target_year':r['census_year'],'latitude':dp['latitude'],'longitude':dp['longitude'],'coordinate_source_record_id':donor['source_record_id'],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_origin_ledger':str(Q),'coordinate_origin_ledger_sha256':inputs[str(Q)],'coordinate_origin_ledger_locator':'source_record_id='+donor['source_record_id'],'admission_rule':'representative_point_continuity_existing_accepted_ordinary_exact_name_region_three_year_component_no_conflicts','direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'boundary_comparability_asserted':False,'point_origin_file':dp['point_origin_file'],'point_origin_sha256':dp['point_origin_sha256'],'point_origin_locator':dp['point_origin_locator']}
  accepted.append(row);witness.append({**row,'root':root,'settlement_name':r['settlement_name'],'type_norm':r['type_norm'],'region_norm':r['region_norm'],'district_raw':r['district_raw'],'witness':'Existing accepted same-place component; exactly3 finite additive source rows, unique2002/2010/2021; unchanged normalized name/region; accepted donors agree; no raw point contradiction, event endpoint, part/scope artifact or target-year point collision.'})
 for r in rs:
  if not r['working_credit_present']:newcredit.append({'source_record_id':r['source_record_id'],'census_year':r['census_year'],'population':r['effective_population']})
# Routes from verified native2021 attachment within already accepted full roots.
cur=c.execute("select d.source_record_id,d.root,d.population,d.settlement_name,d.region_norm,d.latitude prior_candidate_latitude,d.longitude prior_candidate_longitude,a.tochno_latest__qc_geo_dadata qc_geo_dadata,a.tochno_latest__settlement_dadata provider_settlement_name,a.latest_row_1based,a.source_version_rule,a.tochno_latest__latitude latitude,a.tochno_latest__longitude longitude,a.tochno_latest__yandex_maps yandex_maps,a.tochno_latest__object_name object_name,a.tochno_latest__oktmo oktmo,a.tochno_latest__population source_population from d join roots using(root) join read_parquet(?) a using(source_record_id) where n=3 and ny=3 and ordinary and d.census_year=2021 and not d.accepted_point_present and d.region_norm not in ('москва','санкт петербург','севастополь','крым')",[str(A)])
routes=[dict(zip([t[0] for t in cur.description],r)) for r in cur.fetchall()]
for r in routes:
 r['prior_candidate_finite']=valid((r['prior_candidate_latitude'],r['prior_candidate_longitude']))
 r['latest_distance_from_prior_candidate_km']=distance((r['latitude'],r['longitude']),(r['prior_candidate_latitude'],r['prior_candidate_longitude'])) if r['prior_candidate_finite'] and valid((r['latitude'],r['longitude'])) else None
 r['point_origin_admission']='held_no_manual_provenance_yandex_coordinate_viewport_is_not_entity_binding';r['evidence_file']=str(A);r['evidence_sha256']=inputs[str(A)]
def write(name,rs,cols):
 with (O/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]) if rs else cols);w.writeheader();w.writerows(rs)
write('accepted_point_use_delta.csv',accepted,['target_source_record_id','coordinate_admission_status','latitude','longitude'])
write('point_continuity_witnesses.csv',witness,['target_source_record_id','witness'])
write('held_components.csv',held,['root','reason'])
write('latest_native_coordinate_routes.csv',routes,['source_record_id','point_origin_admission'])
write('projected_new_credits.csv',newcredit,['source_record_id','census_year','population'])
gain=collections.Counter();pop=collections.Counter()
for r in newcredit:gain[r['census_year']]+=1;pop[r['census_year']]+=r['population']
receipt={'existing_accepted_partial_point_roots':len(groups),'existing_accepted_missing_point_rows':sum(not r['accepted_point_present'] for r in rows),'proposed_existing_identity_continuity_points':len(accepted),'held_existing_components':held,'native2021_missingpoint_routes':len(routes),'latest_coordinate_routes_finite':sum(valid((r['latitude'],r['longitude'])) for r in routes),'latest_finite_previously_missing_raw_coordinate_routes':sum(valid((r['latitude'],r['longitude'])) and not r['prior_candidate_finite'] for r in routes),'latest_coordinates_over5km_from_prior_candidate':sum((r['latest_distance_from_prior_candidate_km'] or 0)>5 for r in routes),'source_explicitly_manual_verified_routes':0,'proposed_new_manual_provider_points':0,'projected_unique_new_credits':dict(gain),'projected_credit_population':dict(pop),'inputs':inputs,'source_semantics':'PDF lists DaData/Wikipedia/FIAS/manual enrichment; no per-row manual-origin flag; yandex_maps sample viewport links contain only consolidated coordinates. Never infer manual origin.','national_application_performed':False,'outputs':{p.name:sha(p) for p in O.glob('*.csv')}}
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ('inputs','outputs')},ensure_ascii=False),flush=True)

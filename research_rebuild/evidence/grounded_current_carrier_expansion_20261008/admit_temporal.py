from pathlib import Path
import sys,json,re,math,collections
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');APP=R/'research_rebuild/evidence/main_axis_residual_application63_20261008';P=APP/'applied_point_snapshot.parquet';C=APP/'applied_component_snapshot.csv.gz';F=APP/'applied_remaining_primary.csv.gz'
c=duckdb.connect();f=c.execute('select * from read_parquet(?)',[str(S)]).fetchdf();p=c.execute('select target_source_record_id as source_record_id,latitude,longitude,coordinate_admission_status,coordinate_source_record_id,source_sha256,source_locator,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,point_ledger_path from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('source_record_id').to_dict('index');c.close();b=f.set_index('source_record_id');cs=pd.read_csv(C,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);cand=pd.concat([pd.read_csv(O/'geometry_candidate_identity_pairs.csv.gz',dtype=str,keep_default_na=False).assign(admission_method='positive_named_geometry_closed_aliases'),pd.read_csv(O/'parish_candidate_identity_pairs.csv.gz',dtype=str,keep_default_na=False).assign(admission_method='positive_printed_parish_or_three_source_anchors')],ignore_index=True).fillna('');books={};rawparquet={};checks={};pins={str(q):sha(q) for q in [S,P,C,F,O/'geometry_candidate_identity_pairs.csv.gz',APP/'application_receipt.json']};raw=[];holds=[];accepted=[];edges=[];points=[];uf=UnionFind(cs);members=collections.defaultdict(list)
for sid,z in cs.items():members[z['root']].append(sid)
for ids in members.values():
 for sid in ids[1:]:uf.union(ids[0],sid)
def path(row):
 q=Path('/workspace/settlements-raw')/str(row.source_file)
 return q if q.is_file() else Path(str(row.source_path))
def check(sid):
 if sid in checks:return checks[sid]
 row=b.loc[sid];q=path(row);label=normalize(row.source_name_raw);record={'source_record_id':sid,'year':int(row.census_year),'protected_native_name':row.settlement_name,'protected_native_type':row.settlement_type,'protected_native_population':row.population,'protected_native_quality':row.population_value_quality,'source_file':str(q),'source_locator':row.source_locator,'raw_name':row.source_name_raw,'literal_label_population_passed':False,'actual_printed_county':'','actual_county_key':'','source_row1based':row.source_row,'source_sheet':row.source_sheet}
 if not q.is_file():record['held_reason']='Original native source missing';checks[sid]=record;return record
 if str(q) not in pins:pins[str(q)]=sha(q)
 record['source_sha256']=pins[str(q)]
 if q.suffix=='.xls':
  if str(q) not in books:books[str(q)]=xlrd.open_workbook(str(q),on_demand=True)
  book=books[str(q)];sn=str(row.source_sheet);sh=book.sheet_by_name(sn) if sn in book.sheet_names() else book.sheet_by_index(int(sn));rn=int(row.source_row)-1;vals=sh.row_values(rn);pos=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(v)==label];pos += [i+1 for i in range(len(vals)-1) if isinstance(vals[i],str) and isinstance(vals[i+1],str) and normalize(vals[i]+' '+vals[i+1])==label]
  nums=[v for v in vals[min(pos)+1:] if isinstance(v,(int,float)) or(isinstance(v,str) and re.fullmatch(r'[0-9]+',v.strip()))] if pos else []
  record['literal_label_population_passed']=bool(pos and any(float(v)==float(row.population) for v in nums));record['raw_row_cells_json']=json.dumps(vals,ensure_ascii=False)
  # Independently reopen the nearest printed district heading, retaining its actual cells.
  for nr in (range(rn-1,max(-1,rn-4000),-1) if int(row.census_year)==2002 else []):
   vs=sh.row_values(nr);ss=[v for v in vs if isinstance(v,str) and re.search(r'\bрайон(?:а)?\b',normalize(v)) and not re.search(r'муниципальн|в том числе',normalize(v))]
   if ss:
    caption=ss[0];k=county_key(caption);k=re.sub(r'^(?:сельсоветы|сс)\s+','',k);k=re.sub(r'ского$','ский',k);record.update(actual_printed_county=caption,actual_county_key=k,actual_county_locator=f'sheet={sh.name};row1based={nr+1}');break
 elif q.suffix=='.parquet':
  # Source UID/locator and actual publisher native fields are immutable; current raw parquet control is pinned.
  if str(q) not in rawparquet:
   con=duckdb.connect();rf=con.execute('select object_name,population,mun_upper from read_parquet(?)',[str(q)]).fetchdf();con.close();rawparquet[str(q)]=rf
  rr=rawparquet[str(q)].iloc[int(row.source_row)-1];record['raw_parquet_object_name']=rr.object_name;record['raw_parquet_population']=int(rr.population);record['literal_label_population_passed']=bool(normalize(rr.object_name)==label and float(rr.population)==float(row.population));record['actual_printed_county']=str(rr.mun_upper);record['actual_county_key']=county_key(row.district_raw);record['native_source_kind']='pinned_raw_publisher_parquet_native_UID'
 else:record['held_reason']='Unsupported native source format'
 if re.search('сельсовет|сельское поселение|все население|всего|городское население|сельское население',label):record['literal_label_population_passed']=False;record['held_reason']='Native source object is aggregate'
 raw.append(record);checks[sid]=record;return record

EXTRA=O/'accepted_current_point_delta.csv.gz';LIVE=R/'research_rebuild/evidence/current_live_named_residual_sources_20261008/accepted_point_use_delta.csv.gz'
for q in [EXTRA,LIVE]:
 for z in pd.read_csv(q,dtype=str,keep_default_na=False).to_dict('records'):
  sid=z['target_source_record_id'];assert int(b.loc[sid,'census_year'])==2021 and z['coordinate_admission_status']=='reviewed_extension_rule_accepted'
  if sid not in p:p[sid]={**z,'source_record_id':sid}
for q in [O/'parish_candidate_receipt.json',O/'parish_actual_native_context_witnesses.csv.gz',EXTRA,LIVE,LIVE.parent/'final_handoff_receipt.json',O/'current_admission_receipt.json',O/'geometry_candidate_receipt.json',R/'research_rebuild/evidence/temporal_after_new_current_points_20261008/candidate_geometry_resolver_receipt.json']:
 pins[str(q)]=sha(q)
for k,v in json.loads((R/'research_rebuild/evidence/temporal_after_new_current_points_20261008/candidate_geometry_resolver_receipt.json').read_text()).get('input_pins',{}).items():pins[k]=v
for k,v in json.loads((O/'parish_candidate_receipt.json').read_text()).get('input_pins',{}).items():pins[k]=v
parish_witness=pd.read_csv(O/'parish_actual_native_context_witnesses.csv.gz',dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index')
# Reuse the already checked native rows; no repeat source audit of the first accepted cohort.
oldchecks=pd.read_csv(R/'research_rebuild/evidence/temporal_after_new_current_points_20261008/actual_native_raw_source_checks.csv.gz',dtype=str,keep_default_na=False)
for z in oldchecks.to_dict('records'):
 z['literal_label_population_passed']=z['literal_label_population_passed']=='True';z['year']=int(z['year']);checks[z['source_record_id']]=z;raw.append(z)
 if z.get('source_sha256'):pins[z['source_file']]=z['source_sha256']
event=set(pd.read_csv(R/'research_rebuild/evidence/remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv',usecols=['source_record_id']).source_record_id)
for n in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=R/'research_rebuild/evidence/working_full_chain_20261007'/n
 if q.exists():pins[str(q)]=sha(q);event.update(pd.read_csv(q,usecols=['source_record_id']).source_record_id)
bad=set(json.loads((R/'research_rebuild/evidence/temporal_residual_mass_20261008/state_snapshot_receipt.json').read_text())['conflicting_point_targets'])
occupied=collections.defaultdict(set)
for i,z in p.items():occupied[(int(b.loc[i,'census_year']),round(float(z['latitude']),7),round(float(z['longitude']),7))].add(i)
def groups():
 g=collections.defaultdict(list)
 for i in cs:g[uf.find(i)].append(i)
 return g
mg=groups()
def coord(z):return (float(z['latitude']),float(z['longitude']))
def years(ids):return [int(b.loc[i,'census_year']) for i in ids]
def eligible(ids):return len(ids)==3 and set(years(ids))=={2002,2010,2021} and all(i in p and pd.notna(b.loc[i,'population']) and bool(b.loc[i,'is_additive_settlement_record']) for i in ids)
base_plus_current=set(i for ids in mg.values() if eligible(ids) for i in ids)
def common_checks(ids):
 reason=[];current=[i for i in ids if int(b.loc[i,'census_year'])==2021 and i in p]
 if len(current)!=1:return ['no unique independently source-admitted current carrier'],None,None
 cur=current[0];cp=p[cur];pr=[check(i) for i in ids]
 if len(set(years(ids)))!=len(ids):reason.append('actual same-year component repetition')
 if any(i in event for i in ids):reason.append('published nonordinary lifecycle scope')
 if any(i in bad for i in ids):reason.append('active accepted ownpoint conflict')
 if any(pd.isna(b.loc[i,'population']) for i in ids):reason.append('protected unknown native population')
 if not all(x['literal_label_population_passed'] for x in pr):reason.append('literal original native own label/count check failed')
 if any(i in p and distance_km(coord(p[i]),coord(cp))>5 for i in ids):reason.append('actual accepted ownpoint exceeds5km from current carrier')
 for i in ids:
  key=(int(b.loc[i,'census_year']),round(float(cp['latitude']),7),round(float(cp['longitude']),7))
  if i not in p and occupied[key]-set(ids):reason.append('same-year accepted ownpoint collision')
  if i in p:
   ownkey=(int(b.loc[i,'census_year']),round(float(p[i]['latitude']),7),round(float(p[i]['longitude']),7))
   if occupied[ownkey]-set(ids):reason.append('accepted ownpoint shared by separate same-year native record')
 return reason,cur,cp
def point_admit(ids,cur,cp,method):
 for i in ids:
  if i in p:continue
  pp={k:v for k,v in cp.items() if k not in ['root','conflicting_point_target','point_ledger_path','source_record_id','target_source_record_id']}
  pp.update(target_source_record_id=i,latitude=float(cp['latitude']),longitude=float(cp['longitude']),coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='explicit_modern_ownpoint_continuity_for_'+method,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,coordinate_binding_rule='Grounded independently admitted current ownpoint; accepted native physical identity path and reopened own named leaf/count; no relocation or published inclusion scope; actual accepted points agree within5km; same-year point collisions excluded; current representative reused explicitly, not a historical measurement')
  points.append(pp);p[i]=pp;occupied[(int(b.loc[i,'census_year']),round(float(cp['latitude']),7),round(float(cp['longitude']),7))].add(i)
# Existing accepted UF identity components need no invented new identity edge.
propagation=[]
for root,ids in sorted(mg.items(),key=lambda kv:-sum(float(b.loc[i,'population']) for i in kv[1] if pd.notna(b.loc[i,'population']))):
 if not any(i in remaining for i in ids) or not any(i not in p for i in ids) or not any(int(b.loc[i,'census_year'])==2021 and i in p for i in ids):continue
 reason,cur,cp=common_checks(ids)
 if reason:holds.append({'admission_method':'accepted_component_continuity','component_source_ids_json':json.dumps(ids),'held_reason':'; '.join(sorted(set(reason)))});continue
 point_admit(ids,cur,cp,'already_accepted_native_identity_component');propagation.append({'component_root':root,'component_source_ids_json':json.dumps(ids),'current_ownpoint_carrier_source_record_id':cur,'admission_method':'accepted_component_continuity'})
for z in cand.to_dict('records'):
 sid,bid=z['from_source_record_id'],z['to_source_record_id'];a,d=uf.find(sid),uf.find(bid)
 if a==d:holds.append({**z,'held_reason':'already joined by previous admitted branch'});continue
 ids=list(dict.fromkeys(mg[a]+mg[d]));reason,cur,cp=common_checks(ids);method=z['admission_method']
 if method=='literal_county':
  dc=county_key(b.loc[cur,'district_raw']) if cur else ''
  for i in ids:
   if int(b.loc[i,'census_year'])==2021:continue
   x=check(i);selected=county_key(b.loc[i,'district_raw']);actual=x.get('actual_county_key','').removesuffix(' муниципальный').strip()
   if actual and selected and actual!=selected and not actual.endswith(' '+selected):reason.append('actual historic district contradicts selected county')
   if selected and dc and selected!=dc:reason.append('literal sourcecounty/current mismatch without transfer proof')
 if method=='source_context':
  for key in ['from_county_binding_json','to_county_binding_json']:
   w=json.loads(z[key]);aa=json.loads(w.get('anchors_json','[]'))
   if aa:
    if len(aa)!=2 or len({v['anchor_name'] for v in aa})!=2:reason.append('source county context lacks two distinct physical anchors')
    for v in aa:
     ai=v['anchor_source_record_id'];ci=v['anchor_current_source_record_id'];target=w['source_record_id']
     if not check(ai)['literal_label_population_passed'] or not check(ci)['literal_label_population_passed']:reason.append('flanking native/current literal ownsource check failed')
     if b.loc[ai,'source_file']!=b.loc[target,'source_file'] or str(b.loc[ai,'source_sheet'])!=str(b.loc[target,'source_sheet']) or abs(int(b.loc[ai,'source_row'])-int(b.loc[target,'source_row']))>20:reason.append('flanking source county anchor locator mismatch')
 if method=='positive_printed_parish_or_three_source_anchors':
  for i in ids:
   if int(b.loc[i,'census_year'])==2021:continue
   pw=parish_witness.get(i)
   if not pw:reason.append('actual parish source witness missing');continue
   if pw['parish_role']=='literal_previous_own_native_rural_subunit_caption':
    mt=re.fullmatch(r'sheet=(.*);row1based=(\d+)',pw['parish_source_locator'])
    if not mt or not Path(pw['parish_source_file']).is_file():reason.append('parish caption exact publisher workbook locator unavailable');continue
    if pw['parish_source_file'] not in books:books[pw['parish_source_file']]=xlrd.open_workbook(pw['parish_source_file'],on_demand=True)
    sh=books[pw['parish_source_file']].sheet_by_name(mt.group(1));rn=int(mt.group(2));vals=sh.row_values(rn-1)
    if not any(isinstance(v,str) and normalize(v)==normalize(pw['parish_caption']) for v in vals) or not 0<int(b.loc[i,'source_row'])-rn<=400:reason.append('actual parish caption bytes/source scope do not match')
   elif pw['parish_role']=='three_distinct_accepted_full3_physical_NP_anchors_flanking_exact_native_row_within20':
    aa=json.loads(pw['positive_context_anchor_source_IDs_json']);offsets=[]
    if len(aa)!=3 or len({v['source_record_id'] for v in aa})!=3:reason.append('parish context lacks three distinct accepted source anchors')
    for v in aa:
     ai,ci=v['source_record_id'],v['current_source_record_id'];offset=int(b.loc[ai,'source_row'])-int(b.loc[i,'source_row']);offsets.append(offset)
     if not check(ai)['literal_label_population_passed'] or not check(ci)['literal_label_population_passed']:reason.append('source parish anchor ownleaf/count check failed')
     if b.loc[ai,'source_file']!=b.loc[i,'source_file'] or str(b.loc[ai,'source_sheet'])!=str(b.loc[i,'source_sheet']) or not 0<abs(offset)<=20:reason.append('source parish anchor physical row locator mismatch')
     if cs[ai]['root']!=cs[ci]['root']:reason.append('source parish anchor is not a baseline accepted identity component')
    if not offsets or min(offsets)>=0 or max(offsets)<=0:reason.append('source parish anchors do not flank actual row')
   else:reason.append('unsupported positive parish witness role')
 if reason:holds.append({**z,'held_reason':'; '.join(sorted(set(reason)))});continue
 rule='Source-positive ordinary same physical settlement: literal native leaf name/type and region; independently admitted current coded/article ownpoint; all native same-year namesake and geometry rivals screened before graph joins; positive actual named source geometry or pinned literal/flanking sourcecounty context; no aggregate, lifecycle, duplicate census year, active accepted point contradiction or same-year collision; historic continuity point explicitly uses modern representative, no historic coordinate measurement or population boundary equivalence asserted'
 edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':rule,'admission_method':method,'source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;geometry_all_native_namesake_competitors.csv.gz;parish_all_native_namesake_competitors.csv.gz;parish_actual_native_context_witnesses.csv.gz;parish_candidate_receipt.json','population_boundary_comparability_asserted':False})
 uf.union(sid,bid);mg[uf.find(sid)]=ids;point_admit(ids,cur,cp,method)
 accepted.append({**z,'native_literal_source_IDs_json':json.dumps(ids),'current_ownpoint_carrier_source_record_id':cur,'current_ownpoint_origin_file':cp['point_origin_file'],'current_ownpoint_origin_sha256':cp['point_origin_sha256'],'current_ownpoint_origin_locator':cp['point_origin_locator']})
newids=set(i for ids in groups().values() if eligible(ids) for i in ids)&remaining
conditional=newids-base_plus_current
gain=[{'source_record_id':i,'year':int(b.loc[i,'census_year']),'population':int(b.loc[i,'population']),'name':b.loc[i,'settlement_name'],'population_quality':b.loc[i,'population_value_quality'],'temporal_conditional_after81_current_points':i in conditional} for i in sorted(newids)]
for name,rows,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_native_source_witnesses.csv.gz',accepted,['source_record_id']),('accepted_existing_component_continuity.csv.gz',propagation,['component_root']),('actual_native_raw_source_checks.csv.gz',raw,['source_record_id']),('admission_holds.csv.gz',holds,['source_record_id']),('exact_net_primary_source_ID_union_gain.csv.gz',gain,['source_record_id','year','population'])]:
 (pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)).to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
for q in O.glob('*candidate_identity_pairs.csv.gz'):pins[str(q)]=sha(q)
receipt={'baseline_stage':63,'no_State_load':True,'status':'sourcebound_temporal_admission_packet_ready_for_canonical_root_replay','candidate_pairs':len(cand),'accepted_edges':len(edges),'accepted_continuity_point_uses':len(points),'accepted_existing_component_propagations':len(propagation),'held_admission_pairs':len(holds),'actual_formation_plus_direct_native_UID_delta':{str(y):{'source_records':sum(z['year']==y for z in gain),'population':sum(z['population'] for z in gain if z['year']==y)} for y in [2002,2010,2021]},'conditional_temporal_gain_after81_current_points':{str(y):{'source_records':sum(z['year']==y and z['temporal_conditional_after81_current_points'] for z in gain),'population':sum(z['population'] for z in gain if z['year']==y and z['temporal_conditional_after81_current_points'])} for y in [2002,2010,2021]},'joint_current_point_packets':[str(EXTRA),str(LIVE)],'canonical_root_application_required':True,'native_population_modified':False,'historical_census_coordinates_asserted':False,'boundary_comparability_asserted':False,'input_pins':pins,'output_pins':{q.name:sha(q) for q in O.glob('*.csv.gz')}}
(O/'admission_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))

from pathlib import Path
import pandas as pd,sys,json,hashlib,re,math,xlrd,collections
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;S=Path('/dev/shm/settlements-stage71-20261009');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from apply_unique_county_name_bridge_20261007 import county_key
from current_chain_state_20261007 import normalize,distance_km
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
f=pd.read_parquet(S/'applied_state_observations.parquet').fillna('');b=f.set_index('source_record_id');pt=pd.read_parquet(S/'applied_point_snapshot.parquet',columns=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','own_locality_point','decision_status','scope_id']).fillna('');p=pt.drop_duplicates('target_source_record_id').set_index('target_source_record_id').to_dict('index');a=pd.read_csv(O/'assignment.csv').fillna('');sel=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');m=pd.read_parquet(sel).fillna('').set_index('source_record_id');pins={str(q):sha(q) for q in [sel,S/'applied_state_observations.parquet',S/'applied_point_snapshot.parquet',S/'applied_component_snapshot.csv.gz',O/'assignment.csv']};groups={k:g.source_record_id.tolist() for k,g in f.groupby('root')};books={};checks={};rawpar={};context={};edges=[];points=[];closures=[];holds=[];accepted=set()
def check(sid):
 if sid in checks:return checks[sid]
 z=b.loc[sid];out={'source_record_id':sid,'native_name':z.settlement_name,'native_type':z.settlement_type,'native_population':z.population,'native_population_quality':z.population_value_quality,'literal_label_population_passed':False}
 if sid not in m.index:checks[sid]=out;return out
 v=m.loc[sid]
 if not str(v.source_row).replace('.','').isdigit():checks[sid]=out;return out
 q=Path('/workspace/settlements-raw')/v.source_file
 if not q.is_file():q=Path(v.source_path)
 if not q.is_file():checks[sid]=out;return out
 pins[str(q)]=pins.get(str(q)) or sha(q);out.update(source_file=str(q),source_sha256=pins[str(q)],source_row=v.source_row,source_sheet=v.source_sheet)
 if q.suffix=='.xls':
  if str(q) not in books:books[str(q)]=xlrd.open_workbook(str(q),on_demand=True)
  bk=books[str(q)];sh=bk.sheet_by_name(str(v.source_sheet)) if str(v.source_sheet) in bk.sheet_names() else bk.sheet_by_index(int(v.source_sheet));rn=int(v.source_row)-1;vals=sh.row_values(rn);label=normalize(v.source_name_raw);positions=[i for i,x in enumerate(vals) if isinstance(x,str) and normalize(x)==label];positions += [i+1 for i in range(len(vals)-1) if isinstance(vals[i],str) and isinstance(vals[i+1],str) and normalize(vals[i]+' '+vals[i+1])==label];out['literal_label_population_passed']=bool(positions and any(str(x).strip().isdigit() and float(x)==float(z.population) or isinstance(x,(float,int)) and float(x)==float(z.population) for x in vals[min(positions)+1:])) if positions else False;out['raw_row_cells_json']=json.dumps(vals,ensure_ascii=False)
  if int(z.census_year)==2002:
   for nr in range(rn-1,max(-1,rn-4000),-1):
    vs=sh.row_values(nr);ss=[x for x in vs if isinstance(x,str) and re.search(r'\bрайон(?:а)?\b',normalize(x)) and not re.search(r'муниципальн|в том числе',normalize(x))]
    if ss:
     caption=ss[0];actual=county_key(caption);actual=re.sub(r'^(?:сельсоветы|сс)\s+','',actual);actual=re.sub(r'ского$','ский',actual);out.update(actual_printed_county=caption,actual_county_locator=f'{sh.name}:{nr+1}',actual_county_key=actual);out['literal_label_population_passed']=out['literal_label_population_passed'] and (not county_key(z.district_raw) or actual==county_key(z.district_raw) or actual.endswith(' '+county_key(z.district_raw)) or actual.startswith(county_key(z.district_raw)+' все '));break
 elif q.suffix=='.parquet':
  if str(q) not in rawpar:rawpar[str(q)]=pd.read_parquet(q,columns=['object_name','population','mun_upper'])
  rr=rawpar[str(q)].iloc[int(v.source_row)-1];out.update(raw_row_cells_json=json.dumps(rr.to_dict(),ensure_ascii=False,default=str),literal_label_population_passed=normalize(rr.object_name)==normalize(v.source_name_raw) and float(rr.population)==float(z.population))
 checks[sid]=out;return out
# Native 2010 context: two different named accepted full3 anchors, strictly flanking within20 physical rows.
anchors=collections.defaultdict(list)
for root,ids in groups.items():
 if len(ids)!=3 or any(str(b.loc[i,'census_year']) not in ['2002','2010','2021','2002.0','2010.0','2021.0'] for i in ids) or {int(b.loc[i,'census_year']) for i in ids}!={2002,2010,2021} or not all(i in p for i in ids):continue
 old=next(i for i in ids if int(b.loc[i,'census_year'])==2002);mid=next(i for i in ids if int(b.loc[i,'census_year'])==2010);cur=next(i for i in ids if int(b.loc[i,'census_year'])==2021)
 if mid not in m.index or not str(m.loc[mid,'source_row']).replace('.','').isdigit():continue
 ck=county_key(b.loc[old,'district_raw'])
 if ck and len({b.loc[i,'name_norm'] for i in ids})==1 and max(distance_km((float(p[i]['latitude']),float(p[i]['longitude'])),(float(p[cur]['latitude']),float(p[cur]['longitude']))) for i in ids)<=5:
  v=m.loc[mid];anchors[(v.source_file,str(v.source_sheet),b.loc[mid,'region_norm'])].append((int(v.source_row),ck,mid,old,cur,b.loc[mid,'name_norm']))
def county(sid):
 z=b.loc[sid];literal=county_key(z.district_raw)
 if literal:return literal
 if int(z.census_year)!=2010 or sid not in m.index:return ''
 if sid in context:return context[sid].get('county','')
 v=m.loc[sid]
 if not str(v.source_row).replace('.','').isdigit():context[sid]={};return ''
 rn=int(v.source_row);aa=anchors[(v.source_file,str(v.source_sheet),z.region_norm)];lo=sorted([x for x in aa if rn-20<=x[0]<rn],reverse=True);hi=sorted([x for x in aa if rn<x[0]<=rn+20]);out={}
 if lo and hi and lo[0][1]==hi[0][1] and lo[0][-1]!=hi[0][-1] and all(check(i)['literal_label_population_passed'] for x in [lo[0],hi[0]] for i in x[2:5]):out={'county':lo[0][1],'lower_anchor_json':json.dumps(lo[0],ensure_ascii=False),'upper_anchor_json':json.dumps(hi[0],ensure_ascii=False),'rule':'Two distinct native named full3 ownpoint anchors strictly flanking physical source row within20; old native printed district of both agrees'}
 context[sid]=out;return out.get('county','')
# Namesake county contexts are recovered independently before checking uniqueness.
keys=set(zip(a.region_norm,a.name_norm));pool=f[[ (z.region_norm,z.name_norm) in keys for z in f.itertuples() ]]
for sid in pool.source_record_id:county(sid)
occupied=collections.defaultdict(set)
for sid,pp in p.items():
 if sid in b.index and str(b.loc[sid,'census_year']) in ['2002','2010','2021','2002.0','2010.0','2021.0']:occupied[(int(b.loc[sid,'census_year']),round(float(pp['latitude']),7),round(float(pp['longitude']),7))].add(sid)
def admit(ids,scope):
 ys=[int(b.loc[i,'census_year']) for i in ids];current=[i for i in ids if int(b.loc[i,'census_year'])==2021 and i in p];reason=[]
 if len(current)!=1:reason.append('no unique accepted own current carrier')
 if len(set(ys))!=len(ys):reason.append('same-year record repetition')
 if len({b.loc[i,'name_norm'] for i in ids})!=1 or len({b.loc[i,'type_norm'] for i in ids})!=1:reason.append('name/type differs; separate typed review required')
 if not all(bool(b.loc[i,'is_additive_settlement_record']) and check(i)['literal_label_population_passed'] for i in ids):reason.append('original native own label/count not passed')
 if reason:return reason
 cur=current[0];cp=p[cur];coord=(float(cp['latitude']),float(cp['longitude']))
 for i in ids:
  if i in p and distance_km(coord,(float(p[i]['latitude']),float(p[i]['longitude'])))>5:reason.append('accepted own point spatial contradiction >5km')
  if i not in p and occupied[(int(b.loc[i,'census_year']),round(coord[0],7),round(coord[1],7))]-set(ids):reason.append('sameyear point collision')
 if reason:return reason
 for i in ids:
  if i not in p:
   pp={k:cp.get(k,'') for k in ['point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_source_record_id']};pp.update(target_source_record_id=i,latitude=coord[0],longitude=coord[1],coordinate_admission_status='reviewed_extension_rule_accepted',decision_status='checked_rule_accepted',admission_allowed=True,own_locality_point=True,recipient_point_assigned_to_child=False,source_sha256=check(i)['source_sha256'],source_locator=f"{check(i)['source_sheet']}:{check(i)['source_row']}",admission_rule='Independently accepted native own identity component or explicit exact name/type/region + two distinct flanking native county anchors; sameyear rivals screened, own leaf native counts reopened. Accepted current representative reused by continuity inference.',point_temporal_interpretation='Modern own locality representative reused retrospectively by explicit continuity inference; censusday measurement and population boundary equivalence unknown.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,current_ownpoint_carrier_source_record_id=cur,scope_id=scope);points.append(pp);p[i]=pp
  accepted.add(i)
 closures.append({'scope_id':scope,'component_source_ids_json':json.dumps(ids),'available_connected_years':','.join(map(str,sorted(ys))),'missing_census_year_status':'UNKNOWN_NOT_ZERO_NOT_ADJUDICATED' if len(ys)<3 else 'none','all_available_native_source_records_found':False,'three_census_complete':len(ys)==3,'decision_status':'checked_rule_accepted','quality_axis':'ordinary_full3' if len(ys)==3 else 'accepted_connected_incomplete_available_year_series','source_counts_changed':False})
 return []
# Proposed exact typed pair joins; no same-year duplicates, no uncertain aliases.
seen=set()
for z in a.itertuples():
 ids=groups[z.root];ck=county(z.source_record_id)
 if not ck:continue
 same=pool[(pool.region_norm==z.region_norm)&(pool.name_norm==z.name_norm)]
 for yr,g in same.groupby('census_year'):
  rivals=[i for i in g.source_record_id if county(i)==ck]
  if len(rivals)!=1:continue
  other=rivals[0];rt=b.loc[other,'root']
  if rt==z.root or b.loc[other,'type_norm']!=z.type_norm:continue
  key=tuple(sorted([z.root,rt]))
  if key in seen:continue
  seen.add(key);join=list(dict.fromkeys(ids+groups[rt]))
  if any(len([i for i in same[same.census_year==int(b.loc[j,'census_year'])].source_record_id if county(i)==ck])>1 for j in join):continue
  why=admit(join,'north_'+str(len(closures)))
  if why:holds.append({'target_source_record_id':z.source_record_id,'other_source_record_id':other,'reason':';'.join(why)});continue
  # Both sides full-region all-type same-name county uniqueness already checked independently.
  if any(len([i for i in same[same.census_year==int(b.loc[j,'census_year'])].source_record_id if county(i)==ck])>1 for j in join):raise AssertionError('rival escaped')
  edges.append({'from_source_record_id':z.source_record_id,'to_source_record_id':other,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Exact native normalized name/type/region; unique all-type same-name native record per sourceyear in independently recovered county; native original own labels/counts reopened; two distinct strictly flanking accepted full3 sourcecounty anchors when 2010 county absent; no repeated year, point contradiction, or point collision. Censusday measurement/boundary equivalence not asserted.','source_context_witness_file':str(O/'native_county_context.csv'),'population_boundary_comparability_asserted':False})
for root in sorted(set(a.root)):
 ids=groups[root]
 if len(ids)>1 and not any(i in accepted for i in ids):
  why=admit(ids,'north_existing_'+str(len(closures)))
  if why:holds.append({'target_source_record_id':ids[0],'reason':';'.join(why)})
for n,rows,cols in [('accepted_identity_edge_delta.csv',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_connected_series.csv',closures,['scope_id']),('admission_holds.csv',holds,['target_source_record_id','reason']),('native_source_reopen_checks.csv',list(checks.values()),['source_record_id']),('native_county_context.csv',[{'source_record_id':i,**v} for i,v in context.items()],['source_record_id']),('native_namesake_rival_screen.csv',[{'source_record_id':i,'name':b.loc[i,'settlement_name'],'type':b.loc[i,'settlement_type'],'year':b.loc[i,'census_year'],'region':b.loc[i,'region_norm'],'county':county(i),'root':b.loc[i,'root']} for i in pool.source_record_id],['source_record_id'])]:pd.DataFrame(rows,columns=None if rows else cols).to_csv(O/n,index=False)
disp=[]
for z in a.to_dict('records'):
 sid=z['source_record_id'];z.update(disposition='accepted_connected_series_see_axis' if sid in accepted else 'held_unknown_requires_source_or_lifecycle_binding',point_newly_admitted=sid in {x['target_source_record_id'] for x in points},population_or_quality_modified=False);disp.append(z)
pd.DataFrame(disp).to_csv(O/'per_record_dispositions.csv',index=False)
receipt={'status':'accepted_packet_for_root_replay','baseline_stage':71,'edges':len(edges),'point_uses':len(points),'connected_series':len(closures),'assigned_residual_UIDs':len(a),'accepted_assigned_UIDs':sum(i in accepted for i in a.source_record_id),'ordinary_full3_claims':sum(z['three_census_complete'] for z in closures),'incomplete_series_do_not_credit_full3':True,'input_pins':pins,'output_pins':{str(q):sha(q) for q in O.glob('*.csv')},'population_or_quality_modified':False}
(O/'manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print({k:v for k,v in receipt.items() if 'pins' not in k})

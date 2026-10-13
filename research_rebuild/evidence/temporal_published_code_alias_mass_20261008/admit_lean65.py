from pathlib import Path
import sys,ast,json,re,collections
import pandas as pd,duckdb,xlrd
O=Path(__file__).parent;R=O.parents[2];A=O.parent/'main_axis_residual_application65_20261008';B=O.parent/'grounded_current_carrier_expansion_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
exec(compile(ast.Module(body=[n for n in ast.parse((B/'discover_closed_geometry.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ['nm','ty']],type_ignores=[]),'names','exec'))
OBS=A/'applied_state_observations.parquet';P=A/'applied_point_snapshot.parquet';S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');G=O.parent/'temporal_after_new_current_points_20261008/resolved_candidate_geometry.parquet';cand=pd.read_csv(O/'candidate_identity_pairs.csv.gz',keep_default_na=False);pins=json.loads((O/'candidate_receipt.json').read_text())['input_pins'];pins[str(O/'candidate_receipt.json')]=sha(O/'candidate_receipt.json');pins[str(O/'candidate_identity_pairs.csv.gz')]=sha(O/'candidate_identity_pairs.csv.gz');c=duckdb.connect();c.execute("set memory_limit='512MB'");c.execute('set threads=1');c.create_function('closednm',nm,return_type='VARCHAR');roots=set(cand.old_root)|set(cand.current_root);c.register('roots',pd.DataFrame({'root':list(roots)}));f=c.execute('select o.* from read_parquet(?) o join roots r using(root)',[str(OBS)]).fetchdf();keys=f[['census_year','region_norm','settlement_name']].copy();keys['k']=keys.settlement_name.map(nm);keys=keys[['census_year','region_norm','k']].drop_duplicates();c.register('keys',keys);riv=c.execute('select o.* from read_parquet(?) o join keys k on o.census_year=k.census_year and o.region_norm=k.region_norm and closednm(o.settlement_name)=k.k',[str(OBS)]).fetchdf();ids=set(f.source_record_id)|set(riv.source_record_id);c.register('ids',pd.DataFrame({'source_record_id':list(ids)}));p=c.execute('select p.* from read_parquet(?) p join ids i on p.target_source_record_id=i.source_record_id',[str(P)]).fetchdf().fillna('').set_index('target_source_record_id').to_dict('index');gc=c.execute('select g.* from read_parquet(?) g join ids i using(source_record_id)',[str(G)]).fetchdf().fillna('').set_index('source_record_id').to_dict('index');meta=c.execute('select s.* from read_parquet(?) s join ids i using(source_record_id)',[str(S)]).fetchdf().set_index('source_record_id');rd=pd.concat([f,riv]).drop_duplicates('source_record_id').set_index('source_record_id').to_dict('index');b=pd.DataFrame.from_dict(rd,orient='index');
for col in ['source_name_raw','source_sheet','source_row']:b[col]=b.index.map(meta[col].to_dict())
for q in [O.parent/'original_2002_population_control_residual_20261008/finalized_stage64_source100/accepted_source_observation_metadata_100.csv',O.parent/'residual_source_followup_20261008/finalized_Tver28_source_addon/accepted_Tver28_source_metadata.csv']:
 mm=pd.read_csv(q,keep_default_na=False).set_index('source_record_id');
 for col in ['source_name_raw','source_sheet','source_row']:
  for i,v in mm[col].items():
   if i in b.index:b.at[i,col]=v
coords=pd.DataFrame([{'lat':round(float(z['latitude']),7),'lon':round(float(z['longitude']),7)} for z in p.values()]).drop_duplicates();c.register('coords',coords);occ=c.execute('select o.census_year,round(cast(p.latitude as double),7) lat,round(cast(p.longitude as double),7) lon,p.target_source_record_id from read_parquet(?) p join coords x on round(cast(p.latitude as double),7)=x.lat and round(cast(p.longitude as double),7)=x.lon join read_parquet(?) o on o.source_record_id=p.target_source_record_id',[str(P),str(OBS)]).fetchdf();c.close();occupied=collections.defaultdict(set)
for z in occ.to_dict('records'):occupied[(int(z['census_year']),z['lat'],z['lon'])].add(z['target_source_record_id'])
remaining=set(pd.read_csv(A/'applied_remaining_primary.csv.gz',usecols=['source_record_id']).source_record_id);uf=UnionFind(f.source_record_id);mg=collections.defaultdict(list)
for z in f.to_dict('records'):mg[z['root']].append(z['source_record_id'])
for vv in mg.values():
 for i in vv[1:]:uf.union(vv[0],i)
mg={uf.find(v[0]):v for v in mg.values()};native=collections.defaultdict(list)
for i,z in rd.items():native[(int(z['census_year']),z['region_norm'],nm(z['settlement_name']))].append(i)
checks={};books={};raw=[]
for folder in ['grounded_current_carrier_expansion_20261008','temporal_after_new_current_points_20261008','temporal_source_alias_reserve_20261008','temporal_new30_existing_history65_20261008','temporal_current_carrier_addon65_20261008']:
 q=O.parent/folder/'actual_native_raw_source_checks.csv.gz'
 if q.exists():
  pins[str(q)]=sha(q)
  for z in pd.read_csv(q,keep_default_na=False).to_dict('records'):
   if z['source_record_id'] in ids:checks[z['source_record_id']]=z
# Validate first printed numeric total, including cached witness rows.
def check(i):
 row=b.loc[i];old=checks.get(i);q=Path('/workspace/settlements-raw')/str(row.source_file)
 if not q.is_file():q=Path(str(row.source_path))
 if not q.is_file() and (R/q).is_file():q=R/q
 label=normalize(row.source_name_raw);z={'source_record_id':i,'source_file':str(q),'source_locator':row.source_locator,'raw_name':row.source_name_raw,'protected_native_population':row.population,'literal_label_population_passed':False}
 if not q.is_file():checks[i]=z;return z
 if old and old.get('raw_row_cells_json'):
  vals=json.loads(old['raw_row_cells_json'])
 elif q.suffix=='.xls':
  if str(q) not in books:books[str(q)]=xlrd.open_workbook(str(q),on_demand=True)
  bk=books[str(q)];sn=str(row.source_sheet);sh=bk.sheet_by_name(sn) if sn in bk.sheet_names() else bk.sheet_by_index(int(sn));vals=sh.row_values(int(row.source_row)-1)
 elif q.suffix=='.parquet':
  co=duckdb.connect();rr=co.execute('select object_name,population from read_parquet(?) limit 1 offset ?',[str(q),int(row.source_row)-1]).fetchone();co.close();z.update(raw_parquet_object_name=rr[0],raw_parquet_population=rr[1]);z['literal_label_population_passed']=normalize(rr[0])==label and float(rr[1])==float(row.population);vals=None
 else:vals=[]
 if vals is not None:
  pos=[j for j,v in enumerate(vals) if isinstance(v,str) and normalize(v)==label]+[j+1 for j in range(len(vals)-1) if isinstance(vals[j],str) and isinstance(vals[j+1],str) and normalize(vals[j]+' '+vals[j+1])==label];nums=[v for v in vals[min(pos)+1:] if isinstance(v,(int,float)) or isinstance(v,str) and re.fullmatch(r'[0-9]+',v.strip())] if pos else [];z['literal_label_population_passed']=bool(nums and float(nums[0])==float(row.population));z['raw_row_cells_json']=json.dumps(vals,ensure_ascii=False)
 if str(q) not in pins:pins[str(q)]=sha(q)
 z['source_sha256']=pins[str(q)];checks[i]=z;return z
def printed_county(i):
 row=b.loc[i];q=Path('/workspace/settlements-raw')/str(row.source_file)
 if not q.is_file():q=Path(str(row.source_path))
 if not q.is_file() and (R/q).is_file():q=R/q
 if q.suffix!='.xls':return ''
 if str(q) not in books:books[str(q)]=xlrd.open_workbook(str(q),on_demand=True)
 bk=books[str(q)];sn=str(row.source_sheet);sh=bk.sheet_by_name(sn) if sn in bk.sheet_names() else bk.sheet_by_index(int(sn));rn=int(row.source_row)-1
 for nr in range(rn-1,max(-1,rn-4000),-1):
  for v in sh.row_values(nr):
   if isinstance(v,str) and re.search(r'\bрайон(?:а)?\b',normalize(v)) and not re.search('в том числе|сельсовет|поселение',normalize(v)):
    k=county_key(v);k=re.sub(r'^(?:сельсоветы|сс)\s+','',k);k=re.sub(r'ского$','ский',k)
    checks[i].update(actual_printed_county=v,actual_county_key=k,actual_county_locator=f'sheet={sh.name};row1based={nr+1}');return k
 return ''
edges=[];points=[];held=[];proof=[];rivals=[];seen=set()
def geom(i):
 z=p.get(i,gc.get(i));return (float(z['latitude']),float(z['longitude'])) if z else None
for z in cand.sort_values('from_population',ascending=False).to_dict('records'):
 sid,bid=z['from_source_record_id'],z['to_source_record_id']
 if (sid,bid) in seen:continue
 seen.add((sid,bid));a,d=uf.find(sid),uf.find(bid)
 if a==d:continue
 group=mg[a]+mg[d];cp=p[bid];cg=geom(bid);reason=[]
 if cand[cand.from_source_record_id==sid].to_source_record_id.nunique()!=1:reason.append('multiple actual current owncode counterparts')
 physical={'город','пгт','село','деревня','поселок','хутор','станица','аул','слобода','станция','разъезд','железнодорожный объект','железнодорожная станция','железнодорожный разъезд','аал','арбан','починок','заимка','кордон','участок','местечко'}
 if any(ty(rd[i]['settlement_type']) not in physical for i in group):reason.append('unsupported proper wholeNP type')
 if any(re.search(r'\b(?:часть|части|частью|всего|население)\b',normalize(b.loc[i,'source_name_raw'])) for i in group):reason.append('explicit native statisticalpart/aggregate caption')
 if len({int(rd[i]['census_year']) for i in group})!=len(group):reason.append('actual sameyear component repetition')
 if any(pd.isna(rd[i]['population']) for i in group):reason.append('protected unknown population')
 if any(i in p and distance_km(geom(i),cg)>5 for i in group):reason.append('actual accepted historical ownpoint contradiction')
 for i in group:
  row=rd[i];key=(int(row['census_year']),round(cg[0],7),round(cg[1],7))
  if occupied[key]-set(group):reason.append('sameyear accepted ownpoint collision')
  own=geom(i)
  if i in p and occupied[(int(row['census_year']),round(own[0],7),round(own[1],7))]-set(group):reason.append('accepted ownpoint shared with separate sameyear source')
  if int(row['census_year'])==2021:continue
  for ri in native[(int(row['census_year']),row['region_norm'],nm(row['settlement_name']))]:
   rg=geom(ri);unresolved=ri!=i and (rg is not None and distance_km(rg,cg)<=5 or rg is None and (not county_key(row['district_raw']) or not county_key(rd[ri]['district_raw']) or county_key(row['district_raw'])==county_key(rd[ri]['district_raw'])))
   rivals.append({'target_source_record_id':i,'rival_source_record_id':ri,'native_name':rd[ri]['settlement_name'],'native_type':rd[ri]['settlement_type'],'county':rd[ri]['district_raw'],'geometry_accepted':ri in p,'unresolved':unresolved})
   if unresolved:reason.append('actual sameyear named rival unresolved')
  ca=str(row['okato']).removesuffix('.0');cb=str(rd[bid]['okato']).removesuffix('.0')
  if ca not in ['','None','nan'] and cb not in ['','None','nan'] and ca!=cb and ca+'000'!=cb and cb+'000'!=ca:reason.append('actual native OKATO contradiction')
 if not reason:
  for i in group:
   if not check(i)['literal_label_population_passed']:reason.append('literal native first total/count failed')
  if z['old_far_unaccepted_geometry_not_hard_contradiction'] and printed_county(sid)!=county_key(rd[bid]['district_raw']):reason.append('far oldcandidate lacks literal printed owncounty header')
 if reason:held.append({**z,'held_reason':'; '.join(sorted(set(reason)))});continue
 edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_method':'typed_published_ownNP_code_and_sourcebound_modern_carrier','admission_rule':'Published proper named wholeNP source object own typed OKTMO/OKATO bound to unique independently accepted current ownNP carrier; literal original native leaf and first population total; positive candidate geometry or printed historical county; actual allraw rivals/UFyear/acceptedpoint/nativecode/event/scope guards; explicit modern continuity inference, no historical code or coordinate assertion','population_boundary_comparability_asserted':False});proof.append({**z,'component_source_ids_json':json.dumps(group)})
 for i in group:
  if i not in p:
   pp={k:v for k,v in cp.items() if k not in ['root','source_record_id','target_source_record_id']};pp.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='explicit_modern_ownpoint_continuity_for_typed_published_ownNP_code',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False);points.append(pp);p[i]=pp;occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))].add(i)
 uf.union(sid,bid);mg[uf.find(sid)]=group
final=collections.defaultdict(list)
for i in f.source_record_id:final[uf.find(i)].append(i)
gains=[]
for vv in final.values():
 if len(vv)==3 and {int(rd[i]['census_year']) for i in vv}=={2002,2010,2021} and all(i in p and pd.notna(rd[i]['population']) for i in vv):
  for i in vv:
   z=rd[i]
   if i in remaining and z['is_additive_settlement_record'] and z['region_norm'] not in ['москва','санкт петербург','севастополь'] and not(int(z['census_year'])==2021 and z['region_norm']=='крым'):gains.append({'source_record_id':i,'census_year':int(z['census_year']),'population':z['population']})
used={i for z in proof for i in json.loads(z['component_source_ids_json'])}
for n,xx,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('admission_holds.csv.gz',held,['from_source_record_id','held_reason']),('accepted_native_source_witnesses.csv.gz',proof,['from_source_record_id']),('actual_native_raw_source_checks.csv.gz',[checks[i] for i in used],['source_record_id']),('all_native_namesake_competitors.csv.gz',rivals,['target_source_record_id','rival_source_record_id']),('projected_main_native_gain_UIDs.csv.gz',gains,['source_record_id','census_year','population'])]:pd.DataFrame(xx,columns=None if xx else cols).to_csv(O/n,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':65,'status':'ready_not_canonical_applied','accepted_edges':len(edges),'accepted_points':len(points),'held_pairs':len(held),'main_native_population_gain_by_year':{str(y):sum(float(z['population']) for z in gains if z['census_year']==y) for y in [2002,2010,2021]},'main_native_UID_gain_by_year':{str(y):sum(z['census_year']==y for z in gains) for y in [2002,2010,2021]},'held_reason_counts':dict(collections.Counter(z['held_reason'] for z in held)),'all_actual128_sourceobs_included':True,'no_State_load':True,'input_pins':pins,'output_pins':{q.name:sha(q) for q in O.glob('*.csv.gz')}};(O/'admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))

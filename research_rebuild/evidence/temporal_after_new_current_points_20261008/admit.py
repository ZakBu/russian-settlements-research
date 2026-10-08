from pathlib import Path
import sys,json,re,math,collections
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');APP=R/'research_rebuild/evidence/primary_residual_mass_application_20261008';P=APP/'applied_point_snapshot.parquet';C=APP/'applied_component_snapshot.csv.gz';F=APP/'applied_remaining_primary.csv.gz'
c=duckdb.connect();f=c.execute('select * from read_parquet(?)',[str(S)]).fetchdf();p=c.execute('select source_record_id,latitude,longitude,coordinate_admission_status,coordinate_source_record_id,source_sha256,source_locator,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,point_ledger_path from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('source_record_id').to_dict('index');c.close();b=f.set_index('source_record_id');cs=pd.read_csv(C,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);cand=pd.read_csv(O/'continuity_candidate_identity_pairs.csv.gz',dtype=str,keep_default_na=False);books={};rawparquet={};checks={};pins={str(q):sha(q) for q in [S,P,C,F,O/'continuity_candidate_identity_pairs.csv.gz',APP/'application_receipt.json']};raw=[];holds=[];accepted=[];edges=[];points=[];uf=UnionFind(cs);members=collections.defaultdict(list)
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
for z in cand.to_dict('records'):
 sid,bid=z['from_source_record_id'],z['to_source_record_id'];ids=json.loads(z['component_source_ids_json']);reason=[];proof=[check(i) for i in ids]
 if not all(x['literal_label_population_passed'] for x in proof):reason.append('literal original native ownlabel/count check failed')
 current=[i for i in ids if int(b.loc[i,'census_year'])==2021 and i in p]
 if len(current)!=1:reason.append('no unique accepted current ownpoint carrier')
 cp=p[current[0]] if len(current)==1 else None;dc=county_key(b.loc[current[0],'district_raw']) if current else ''
 # For every noncurrent endpoint, physical same place needs independently native county support when article/source rosters show namesakes.
 for x in proof:
  if x['year']==2021:continue
  selected=county_key(b.loc[x['source_record_id'],'district_raw']);actual=x['actual_county_key'];actual=actual.removesuffix(' муниципальный').strip()
  if actual and selected and actual!=selected and not actual.endswith(' '+selected):reason.append('actual nearest historical district heading contradicts selected caption')
  if actual and dc and actual!=dc and not actual.endswith(' '+dc):reason.append('actual historic/current district mismatch; no dated county transfer proof')
  if x['year']==2002 and not actual and not selected:reason.append('historic2002 own source has no independent printed county witness')
  if selected and dc and selected!=dc:reason.append('selected historic/current district mismatch; no dated county transfer proof')
 # Uncaptioned2010 ordinary bindings are admitted only through the retained all-year physical namesake screen and literal ownlabel/count; distant urban headings are not district evidence.
 if uf.find(sid)==uf.find(bid):reason.append('already sequentially joined')
 if reason:holds.append({**z,'held_reason':'; '.join(sorted(set(reason)))});continue
 rule='Native own label and literal published population reopened; exact name or already accepted component-name alias; rural physical class changes allowed; independent printed2002/current district same; uncaptioned2010 native rows use retained all-regional physical/sourcecounty namesake screen plus accepted other-census district context, distanturban headings are not district evidence; all same-year regional compatible physical competitors retained before graph filtering; unresolved namesakes/duplicate census years/active point conflicts/known lifecycle scope blocked; existing accepted component points agree within5km; missing historical own point is explicit modern representative continuity inference, no measured historical coordinates or boundary comparability claimed'
 edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':rule,'source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;continuity_all_native_namesake_competitors.csv.gz','population_boundary_comparability_asserted':False});uf.union(sid,bid)
 for i in ids:
  if i in p:continue
  pp={k:v for k,v in cp.items() if k not in ['root','conflicting_point_target','point_ledger_path','source_record_id']};pp.update(target_source_record_id=i,latitude=float(cp['latitude']),longitude=float(cp['longitude']),coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='modern_own_representative_point_reused_through_sourcecounty_native_identity',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,coordinate_binding_rule=rule);points.append(pp);p[i]=dict(pp)
 accepted.append({**z,'current_ownpoint_carrier_source_record_id':current[0],'current_ownpoint_origin_file':cp['point_origin_file'],'current_ownpoint_origin_sha256':cp['point_origin_sha256'],'current_ownpoint_origin_locator':cp['point_origin_locator'],'native_literal_source_IDs_json':json.dumps(ids,ensure_ascii=False)})
# Exact candidate finite full3 union delta against actual formation+direct residual; never count partial histories.
newids=set();groups=collections.defaultdict(list)
for sid in cs:groups[uf.find(sid)].append(sid)
for ids in groups.values():
 if set(int(b.loc[i,'census_year']) for i in ids)!={2002,2010,2021}:continue
 if any(i not in p or pd.isna(b.loc[i,'population']) for i in ids):continue
 newids.update(set(ids)&remaining)
gain=[{'source_record_id':i,'year':int(b.loc[i,'census_year']),'population':int(b.loc[i,'population']),'name':b.loc[i,'settlement_name'],'population_quality':b.loc[i,'population_value_quality']} for i in sorted(newids)]
for name,rows,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_native_source_witnesses.csv.gz',accepted,['source_record_id']),('actual_native_raw_source_checks.csv.gz',raw,['source_record_id']),('admission_holds.csv.gz',holds,['source_record_id']),('exact_net_primary_source_ID_union_gain.csv.gz',gain,['source_record_id','year','population'])]:
 (pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)).to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
receipt={'baseline_stage':62,'no_State_load':True,'status':'sourcebound_temporal_admission_packet_ready_for_canonical_root_replay','candidate_pairs':len(cand),'accepted_edges':len(edges),'accepted_continuity_point_uses':len(points),'held_admission_pairs':len(holds),'actual_formation_plus_direct_native_UID_delta':{str(y):{'source_records':sum(z['year']==y for z in gain),'population':sum(z['population'] for z in gain if z['year']==y)} for y in [2002,2010,2021]},'canonical_root_application_required':True,'native_population_modified':False,'historical_census_coordinates_asserted':False,'boundary_comparability_asserted':False,'input_pins':pins,'output_pins':{q.name:sha(q) for q in O.glob('*.csv.gz') if not q.name.startswith('SHARED')}};(O/'admission_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))

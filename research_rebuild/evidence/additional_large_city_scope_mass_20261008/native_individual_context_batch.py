from pathlib import Path
import sys,json,re,pandas as pd,pyarrow.parquet as pq,xlrd,hashlib,math
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(stage=30);meta=pq.read_table(s.inputs[0],columns=['source_record_id','source_sheet','source_row','source_name_raw']).to_pandas();o=s.obs.merge(meta,on='source_record_id');print('loaded30',flush=True)
hashcache={}
def h(p):
 p=Path(p)
 if str(p) not in hashcache:hashcache[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 return hashcache[str(p)]
rawpath=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');raw=pq.read_table(rawpath,columns=['object_level','object_name','region','mun_upper','mun_lower','settlement','population','oktmo']).to_pandas();regional=o[o.region_norm.eq('московская')].copy();regional['root']=regional.source_record_id.map(s.uf.find);rootids=o.groupby(o.source_record_id.map(s.uf.find)).source_record_id.agg(set).to_dict()
# Only individual own NP links: entire-regional exact name+type uniqueness before any point/population filter.
counts=regional.groupby(['census_year','name_norm','type_norm']).size().to_dict();by={(int(y),n,t):g for (y,n,t),g in regional.groupby(['census_year','name_norm','type_norm'])};edges=[];points=[];triples=[];bindings=[];held=[];headers=[];books={};competitors=[];existing_ids=set()
for folder in ['large_absorbed_city_closed_scope_application_20261008','remaining_absorbed_city_published_closures_application_20261008','nakhoda_complete_published_scope_aux5_application_20261008','city_territory_mass_followup_application_20261008','city_territory_mass_final_two_application_20261008']:existing_ids.update(pd.read_csv(E/folder/'accepted_constituent_credit_union.csv').source_record_id)
for folder in ['complete_transferred_municipal_scope_application_20261008','moscow_complete_scope_mass_application_20261008']:existing_ids.update(pd.read_csv(E/folder/'accepted_native_scope_constituents.csv').source_record_id)
for name in ['complete_publisher_partition_members.csv','qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv']:existing_ids.update(pd.read_csv(E/'working_full_chain_20261007'/name).source_record_id)
f=o.assign(root=o.source_record_id.map(s.uf.find),point=o.source_record_id.isin(s.point_rows),finite=o.population.notna());ag=f.groupby('root').agg(years=('census_year','nunique'),point=('point','all'),finite=('finite','all'));fullroots=set(ag.index[(ag.years==3)&ag.point&ag.finite]);existing_ids.update(f.loc[f.root.isin(fullroots),'source_record_id'])
P02=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls');B02=xlrd.open_workbook(str(P02));S02=B02.sheet_by_index(0);P10=Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls');B10=xlrd.open_workbook(str(P10));S10=B10.sheet_by_name('Data Sheet')
config=[('Клинский район','Клин',2076,2365,9924,10188,'Городской округ Клин'),('Дмитровский район','Дмитров',443,870,8424,8824,'Дмитровский городской округ'),('Волоколамский район','Волоколамск',48,347,8072,8340,'Волоколамский городской округ')]
# Independently alreadyaccepted individual identity components provide sourcecounty anchors, before any point filter.
old_county={};last=''
for n in range(S02.nrows):
 label=str(S02.cell_value(n,1));match=re.match(r'^\s{3}(.+?район)\s*-\s*все сельское население',label,re.I)
 if match:last=match.group(1).strip()
 old_county[n+1]=last
root_old={}
for root,frame in o[o.census_year.eq(2002)&o.source_file.eq('data/raw/2002/'+P02.name)].groupby(o[o.census_year.eq(2002)&o.source_file.eq('data/raw/2002/'+P02.name)].source_record_id.map(s.uf.find)):
 if len(frame)==1:root_old[root]=frame.iloc[0]
anchors={};direct={}
for z in regional[regional.census_year.eq(2010)&regional.source_file.eq('data/raw/2010/'+P10.name)].itertuples():
 old=root_old.get(z.root)
 if old is None:continue
 countyname=old_county.get(int(old.source_row),'')
 if not countyname:continue
 direct[z.source_record_id]={'county':countyname,'basis':'existingacceptedindividual2002_2010sameplace_component_and_original2002printedcounty','old_id':old.source_record_id,'old_source_row':int(old.source_row),'anchor2010_id':z.source_record_id,'anchor2010_row':int(z.source_row)}
 anchors[int(z.source_row)]=direct[z.source_record_id]
anchor_rows=sorted(anchors)
import bisect
bindings_county={}
for z in regional[regional.census_year.eq(2010)].itertuples():
 if z.source_record_id in direct:bindings_county[z.source_record_id]=direct[z.source_record_id];continue
 if z.source_file!='data/raw/2010/'+P10.name:continue
 row=int(z.source_row);ix=bisect.bisect_left(anchor_rows,row)
 if ix==0 or ix==len(anchor_rows):continue
 left,right=anchor_rows[ix-1],anchor_rows[ix]
 if row-left>5 or right-row>5 or anchors[left]['county']!=anchors[right]['county']:continue
 bindings_county[z.source_record_id]={'county':anchors[left]['county'],'basis':'two_nearest_independent_alreadyaccepted_native2010_sourcecounty_anchors_before_anypointfilter','left':anchors[left],'right':anchors[right]}
for county,city,a,b,c,d,municip in config:
 assert county in S02.cell_value(a-1,1);headers.append({'county':county,'2002_file':str(P02),'2002_sha256':h(P02),'2002_sheet':S02.name,'2002_header_row':a,'2002_header_raw_json':json.dumps(S02.row_values(a-1),ensure_ascii=False),'2002_end':b,'2002_next_header_json':json.dumps(S02.row_values(b),ensure_ascii=False),'2010_file':str(P10),'2010_sha256':h(P10),'2010_sheet':'Data Sheet','2010_anchor_first_row':c,'2010_first_anchor_json':json.dumps(S10.row_values(c-1)[:6],ensure_ascii=False),'2010_anchor_next_row':d+1,'2010_next_anchor_json':json.dumps(S10.row_values(d)[:6],ensure_ascii=False),'2010_block_role':'source-order support only; entire-region uniqueness independently required before pointfilter','2021_municip_literal':municip,'2021_file':str(rawpath),'2021_sha256':h(rawpath),'county_receiving_point_projected_to_children':False})
 seed=regional[regional.census_year.eq(2010)&regional.source_file.eq('data/raw/2010/'+P10.name)&regional.source_row.between(c,d)&~regional.source_record_id.isin(existing_ids)]
 for z in seed.itertuples():
  key=(z.name_norm,z.type_norm);ns={year:int(counts.get((year,*key),0)) for year in [2002,2010,2021]}
  pools={year:by.get((year,*key),regional.iloc[:0]) for year in [2002,2010,2021]};ownold=pools[2002][pools[2002].source_file.eq('data/raw/2002/'+P02.name)&pools[2002].source_row.between(a,b)]
  current_pool=pools[2021];current_county=current_pool[[raw.iloc[int(n)-1].mun_upper==municip for n in current_pool.source_row]] if len(current_pool) else current_pool
  unknown10=[r.source_record_id for r in pools[2010].itertuples() if r.source_record_id not in bindings_county]
  own10=pools[2010][pools[2010].source_record_id.map(lambda sid:bindings_county.get(sid,{}).get('county')==county)]
  for yr,pool in pools.items():
   for cr in pool.itertuples():competitors.append({'case':'individual_sourcecounty_unique_'+z.source_record_id,'target_county':county,'year':yr,'source_record_id':cr.source_record_id,'name_norm':cr.name_norm,'type_norm':cr.type_norm,'county_context_proof_json':json.dumps(bindings_county.get(cr.source_record_id,{}),ensure_ascii=False) if yr==2010 else json.dumps({'printed2002county':old_county.get(int(cr.source_row),'')} if yr==2002 and cr.source_file=='data/raw/2002/'+P02.name else {'current_literal_municipality':raw.iloc[int(cr.source_row)-1].mun_upper} if yr==2021 else {},ensure_ascii=False),'point_filter_applied':False})
  if unknown10 or len(ownold)!=1 or len(own10)!=1 or len(current_county)!=1 or own10.iloc[0].source_record_id!=z.source_record_id:
   held.append({'county':county,'source_record_id':z.source_record_id,'reason':'countycontext competitor missing/ambiguous beforepointfilter','counts_json':json.dumps(ns),'context_counts_json':json.dumps({'2002':len(ownold),'2010':len(own10),'2021':len(current_county),'unresolved2010_competitor_IDs':unknown10})});continue
  rr={2002:ownold.iloc[0],2010:own10.iloc[0],2021:current_county.iloc[0]};old=rr[2002];cur=rr[2021]
  rawcur=raw.iloc[int(cur.source_row)-1]
  if rawcur.mun_upper!=municip or rawcur.object_level!='Населенный пункт':held.append({'county':county,'source_record_id':z.source_record_id,'reason':'unique2021native not ownNP inside exact publishedmunicip'});continue
  if cur.source_record_id not in s.point_rows:held.append({'county':county,'source_record_id':z.source_record_id,'reason':'uniquecurrentindividualNP lacks alreadyadmittedownpoint'});continue
  if any(pd.isna(r.population) or not math.isfinite(float(r.population)) for r in rr.values()):held.append({'county':county,'source_record_id':z.source_record_id,'reason':'actual nativepopulationunknown; noimputation'});continue
  ids={r.source_record_id for r in rr.values()};component_ids=set().union(*(rootids[s.uf.find(sid)] for sid in ids))
  if component_ids!=ids:held.append({'county':county,'source_record_id':z.source_record_id,'reason':'existing component has another native source observation competitor','component_ids_json':json.dumps(sorted(component_ids))});continue
  p=dict(s.point_rows[cur.source_record_id]);origin=p.get('point_origin_file') or p['point_ledger_path'];originsha=p.get('point_origin_sha256') or h(origin);assert h(origin)==originsha
  case='individual_sourcecounty_unique_'+z.source_record_id
  for year in [2002,2010]:
   sid=rr[year].source_record_id
   if s.uf.find(sid)!=s.uf.find(cur.source_record_id):edges.append({'from_source_record_id':sid,'to_source_record_id':cur.source_record_id,'relation':'same_place','decision_status':'candidate_only','case':case,'admission_rule':'All same-region typed name competitors enumerated beforepointfilter; every2010homonym sourcecounty bound independently by accepted2002component or two adjacent native anchors; unique own name/type within exact2002county/2010sourcecounty/currentownmunicip; existing individual ownpoint only','source_binding_proof':'individual_triplet_source_bindings.csv;sourcecounty_headers_and_urban_anchors.csv;all_regional_homonym_sourcecounty_competitors.csv.gz;individual_unique_three_year_candidates.csv','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
   if sid not in s.point_rows:
    q=dict(p);q.update(target_source_record_id=sid,coordinate_source_record_id=cur.source_record_id,coordinate_admission_status='candidate_only',point_origin_file=origin,point_origin_sha256=originsha,case=case,coordinate_binding_rule='Individual exactsource-bound NP; allregionalhomonyms independently sourcecounty-resolved beforepointfilter; unique name/type within printedcounty/currentownmunicip; individual NP ownpoint only',population_boundary_comparability_asserted=False,point_use_inference='modern_own_representative_point_on_source_bound_same_locality',county_receiving_point_projected_to_children=False);points.append(q)
  for year,r in rr.items():
   path=Path('/workspace/settlements-raw')/r.source_file;row=int(r.source_row);sheet=str(r.source_sheet);rawvalue=None;label=''
   if year==2002:rowraw=S02.row_values(row-1);label=str(rowraw[1]);rawvalue=int(float(rowraw[2]));locator='Sheet1!row_1based='+str(row);assert rawvalue==r.population
   elif year==2010:rowraw=S10.row_values(row-1);label=str(rowraw[3]);rawvalue=int(float(rowraw[4]));locator='Data Sheet!row_1based='+str(row);assert rawvalue==r.population
   else:rowraw=raw.iloc[row-1].to_dict();label=str(rowraw['object_name']);rawvalue=int(rowraw['population']);locator='parquet_row_1based='+str(row);assert rawvalue==r.population
   bindings.append({'case':case,'county':county,'year':year,'source_record_id':r.source_record_id,'own_settlement_name':r.settlement_name,'own_settlement_type':r.settlement_type,'population':int(r.population),'native_population_quality':r.population_value_quality,'source_file':str(path),'source_sha256':h(path),'source_locator':locator,'raw_own_label':label,'raw_population':rawvalue,'source_values_unmodified':True,'raw_original_core_json':json.dumps(rowraw[:6] if isinstance(rowraw,list) else rowraw,ensure_ascii=False),'current_own_point_source_record_id':cur.source_record_id,'current_own_point_origin_file':origin,'current_own_point_origin_sha256':originsha,'point_provenance_json':json.dumps(p,ensure_ascii=False) if year==2021 else '{}','current_own_oktmo':rawcur.oktmo,'boundary_comparability_asserted':False})
  triples.append({'case':case,'county':county,'name_norm':z.name_norm,'type_norm':z.type_norm,'id2002':old.source_record_id,'id2010':z.source_record_id,'id2021':cur.source_record_id,'population2002':int(old.population),'population2010':int(z.population),'population2021':int(cur.population),'all_regional_competitor_counts_json':json.dumps(ns),'target2010_county_binding_proof_json':json.dumps(bindings_county[z.source_record_id],ensure_ascii=False),'individual_own_point_only':True,'no_receiving_county_city_point_projection':True,'potential_new_population2002':0 if old.source_record_id in existing_ids else int(old.population),'potential_new_population2010':int(z.population),'potential_new_population2021':0 if cur.source_record_id in existing_ids else int(cur.population),'point_provenance_json':json.dumps(p,ensure_ascii=False)})
  print('triplet',county,z.settlement_name,int(z.population),flush=True)
for name,frame in [('candidate_identity_edge_delta',edges),('candidate_point_use_delta',points),('individual_triplet_source_bindings',bindings),('individual_unique_three_year_candidates',triples),('sourcecounty_headers_and_urban_anchors',headers),('all_regional_homonym_sourcecounty_competitors',competitors),('held_individual_candidates',held)]:pd.DataFrame(frame).to_csv(O/(name+'.csv'),index=False)
pd.DataFrame([{'case':z['case'],'county':z['county'],'name_norm':z['name_norm'],'type_norm':z['type_norm'],'before_point_or_population_filter_counts_json':z['all_regional_competitor_counts_json'],'regional_candidates2002':z['id2002'],'regional_candidates2010':z['id2010'],'regional_candidates2021':z['id2021']} for z in triples]).to_csv(O/'all_region_competitor_counts.csv',index=False)
r={'status':'candidate_only_individual_sourcecounty_unique_native_triplets','triplets':len(triples),'edges':len(edges),'point_uses':len(points),'potential_net_population_by_year':{year:sum(z['potential_new_population'+str(year)] for z in triples) for year in [2002,2010,2021]},'no_county_or_city_receiving_point_projected_to_childNP':True,'source_population_values_and_qualities_unmodified':True,'unknown_population_never_zero_or_imputed':True,'all_regional_competitors_enumerated_before_point_filter':True,'all2010_homonym_sourcecounty_bindings_independently_resolved_beforepointfilter':True,'source_manifest':hashcache,'baseline_stage':30,'baseline_report_hashes_not_current_witnesses':True,'outputs':{p.name:h(p) for p in O.glob('*.csv')}};(O/'candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['source_manifest','outputs']},ensure_ascii=False),flush=True)

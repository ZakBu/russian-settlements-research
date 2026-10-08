from pathlib import Path
import sys,json,re,collections
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=O/'SHARED_points_compact_stage61.parquet';C=O/'SHARED_component_snapshot_stage61.csv.gz';F=R/'research_rebuild/evidence/main_axis_residual_registry_20261008/primary_axis_remaining_source_records.csv.gz'
c=duckdb.connect();f=c.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,is_additive_settlement_record,source_path,source_file,source_sheet,source_row,source_name_raw,source_sha256,source_locator,okato,oktmo,population_value_quality from read_parquet(?)',[str(S)]).fetchdf();c.close();p=duckdb.connect().execute('select * from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('source_record_id').to_dict('index');components=pd.read_csv(C,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);f['root']=f.source_record_id.map(lambda x:components[x]['root']);b=f.set_index('source_record_id');members=f.groupby('root').source_record_id.agg(list).to_dict();years={r:set(map(int,components[v[0]]['component_years'].split(','))) for r,v in members.items()};bad=set(sid for sid,z in p.items() if z['conflicting_point_target']=='True');uf=UnionFind(members)
def nm(v):
 x=normalize(v);x=re.sub(r'^(?:поселок|село|деревня|хутор|пгт|рп|п\.|с\.|д\.)\s+','',x);x=re.sub(r'\s+(?:п\.|с\.|д\.|пгт|рп)$','',x);x=re.sub(r'\bим\.\s*','имени ',x);x=re.sub(r'^(?:свх\.?|совхоз)\s+','совхоза ',x);return ' '.join(re.sub(r'["«»]','',x).split())
def ty(v):
 x=normalize(v);return {'поселок городского типа':'пгт','рабочий поселок':'пгт','рп':'пгт','посёлок':'поселок'}.get(x,x)
rural={'село','деревня','поселок','хутор','станица','аул','слобода'}
def compat(a,b):return a==b or (a in rural and b in rural)
def pt(sid):return (float(p[sid]['latitude']),float(p[sid]['longitude']))
idx=collections.defaultdict(list);ownidx=collections.defaultdict(list);occupied=collections.defaultdict(set)
for z in f[f.is_additive_settlement_record.fillna(False)].itertuples():
 idx[(int(z.census_year),z.region_norm,nm(z.settlement_name))].append(z.source_record_id)
 if z.source_record_id in p:
  ownidx[(z.region_norm,nm(z.settlement_name))].append(z.source_record_id);occupied[(int(z.census_year),pt(z.source_record_id))].add(z.source_record_id)
event=set()
for name in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=R/'research_rebuild/evidence/working_full_chain_20261007'/name
 if q.exists():event.update(pd.read_csv(q,usecols=['source_record_id']).source_record_id)
candidates=[];holds=[];rivals=[];seen=set();counts=collections.Counter()
# Accepted component names are source-backed aliases; expose every component alias in ownpoint index.
for root,ids in members.items():
 names={nm(b.loc[i,'settlement_name']) for i in ids}
 for sid in ids:
  if sid not in p:continue
  for alias in names:
   key=(b.loc[sid,'region_norm'],alias)
   if sid not in ownidx[key]:ownidx[key].append(sid)
for sid in sorted(remaining,key=lambda i:-(float(b.loc[i,'population']) if pd.notna(b.loc[i,'population']) else 0)):
 if sid not in p:continue
 a=b.loc[sid];ar=components[sid]['root'];name=nm(a.settlement_name)
 for bid in ownidx[(a.region_norm,name)]:
  if sid==bid or int(a.census_year)==int(b.loc[bid,'census_year']):continue
  pair=tuple(sorted([sid,bid]))
  if pair in seen:continue
  seen.add(pair);z=b.loc[bid];br=components[bid]['root']
  if ar==br:continue
  if not compat(ty(a.settlement_type),ty(z.settlement_type)):counts['incompatible physical class']+=1;continue
  distance=distance_km(pt(sid),pt(bid))
  if distance>5:counts['existing ownpoint >5km']+=1;continue
  reasons=[];ids=list(dict.fromkeys(members[ar]+members[br]));ra,rb=uf.find(ar),uf.find(br)
  if ra==rb:continue
  if years[ra]&years[rb]:reasons.append('repeated native census year component')
  if any(x in bad for x in ids):reasons.append('active point conflict')
  if any(x in event for x in ids):reasons.append('known qualified lifecycle or territory scope')
  if any(pd.isna(b.loc[x,'population']) for x in ids):reasons.append('protected unknown native population')
  if any(x not in p for x in ids):reasons.append('component lacks existing ownpoint; other worker owns point')
  if any(x in p and distance_km(pt(x),pt(bid))>5 for x in ids):reasons.append('component ownpoints disagree >5km')
  if any(len(occupied[(int(b.loc[x,'census_year']),pt(x))])>1 for x in ids if x in p):reasons.append('same-year admitted coordinate shared by native rival')
  for x in ids:
   if x not in p:continue
   row=b.loc[x];same=idx[(int(row.census_year),row.region_norm,nm(row.settlement_name))];dc=county_key(row.district_raw)
   sameclass=[i for i in same if compat(ty(row.settlement_type),ty(b.loc[i,'settlement_type']))];potential=[]
   for i in sameclass:
    ic=county_key(b.loc[i,'district_raw']);near=i in p and distance_km(pt(i),pt(x))<=5
    if i==x or near or (i not in p and (not dc or not ic or dc==ic)):potential.append(i)
   for i in same:rivals.append({'target_source_record_id':x,'rival_source_record_id':i,'year':int(row.census_year),'name':b.loc[i,'settlement_name'],'type':b.loc[i,'settlement_type'],'county':b.loc[i,'district_raw'],'has_accepted_point':i in p,'distance_from_target_km':distance_km(pt(i),pt(x)) if i in p else '', 'compatible_class':i in sameclass,'unresolved_context_or_near':i in potential})
   if potential!=[x]:reasons.append('unresolved same-year physical/sourcecounty namesake')
  out={'from_source_record_id':sid,'to_source_record_id':bid,'from_year':int(a.census_year),'to_year':int(z.census_year),'name':a.settlement_name,'region':a.region_norm,'from_type':a.settlement_type,'to_type':z.settlement_type,'from_county':a.district_raw,'to_county':z.district_raw,'from_population':a.population,'to_population':z.population,'distance_km':distance,'component_source_ids_json':json.dumps(ids,ensure_ascii=False),'old_component_years':','.join(map(str,sorted(years[ra]))),'other_component_years':','.join(map(str,sorted(years[rb])))}
  if reasons:out['held_reason']='; '.join(sorted(set(reasons)));holds.append(out);counts.update(set(reasons));continue
  candidates.append(out);newyears=years[ra]|years[rb];newmembers=list(dict.fromkeys(members[ra]+members[rb]));uf.union(ra,rb);root=uf.find(ra);years[root]=newyears;members[root]=newmembers;counts['sourcepositive candidate']+=1
for name,rows in [('candidate_identity_pairs.csv.gz',candidates),('held_identity_pairs.csv.gz',holds),('all_native_namesake_competitors.csv.gz',rivals)]:pd.DataFrame(rows).to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':61,'candidate_generation_not_admission':True,'candidate_pairs':len(candidates),'held_pairs':len(holds),'outcomes':dict(counts),'input_pins':{str(q):sha(q) for q in [S,P,C,F]},'output_pins':{q.name:sha(q) for q in O.glob('*pairs.csv.gz')}};(O/'candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))

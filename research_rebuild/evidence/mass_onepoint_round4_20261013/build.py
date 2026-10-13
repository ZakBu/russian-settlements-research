import duckdb,csv,re,math,json,hashlib,collections
from pathlib import Path
O=Path(__file__).parent
P=Path('/workspace/scratch/residual-round2-20261013/final/integrated_spatial_temporal_records.parquet')
Q=P.parent/'applied_core_point_snapshot.parquet'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs={str(P):sha(P),str(Q):sha(Q)}
c=duckdb.connect();c.execute('set threads=2');c.execute("create view raw as select * from read_parquet('"+str(P)+"')")
def norm(s):
 s=(s or '').lower().replace('ё','е');s=re.sub(r'\b(муниципальн\w*|городск\w*|район\w*|округ\w*|город\w*|р\s*н|г)\b',' ',s);return ' '.join(re.sub('[^а-яa-z0-9]+',' ',s).split())
county=[(s,norm(s)) for (s,) in c.execute("select distinct coalesce(district_raw,'') from raw").fetchall()]
c.execute('create table counties(raw varchar,k varchar)');c.executemany('insert into counties values (?,?)',county)
c.execute("create table d as select r.*,c.k from raw r join counties c on coalesce(r.district_raw,'')=c.raw")
# Uniqueness across all types blocks same-name typed siblings, including Уташ.
c.execute("create table u as select *,count(*) over(partition by census_year,name_norm,region_norm,k) key_count from d where name_norm is not null")
cols=['source_record_id','census_year','root','name_norm','type_norm','region_norm','k','district_raw','latitude','longitude','accepted_point_present','accepted_latitude','accepted_longitude','population','okato','oktmo','settlement_name']
select=','.join('a.'+x+' a_'+x+',b.'+x+' b_'+x for x in cols)
cur=c.execute('select '+select+" from u a join u b on a.name_norm=b.name_norm and a.type_norm=b.type_norm and a.region_norm=b.region_norm and a.k=b.k where a.census_year<b.census_year and a.root!=b.root and a.key_count=1 and b.key_count=1 and a.k!='' and a.type_norm!='' and a.is_additive_settlement_record and b.is_additive_settlement_record and (not a.working_credit_present or not b.working_credit_present) and (a.accepted_point_present or b.accepted_point_present) order by greatest(coalesce(a.population,0),coalesce(b.population,0)) desc")
pairs=[dict(zip([x[0] for x in cur.description],r)) for r in cur.fetchall()]
meta=c.execute('select source_record_id,root,census_year,working_credit_present,accepted_point_present,effective_population,is_additive_settlement_record,accepted_latitude,accepted_longitude from d').fetchall()
parent={};years=collections.defaultdict(set); members=collections.defaultdict(list); point_collisions=collections.Counter()
for sid,root,yr,credit,point,pop,add,lat,lon in meta:
 parent[root]=root;years[root].add(yr);members[root].append(sid)
 if point:point_collisions[(yr,lat,lon)]+=1
byid={r[0]:r for r in meta}
cur=c.execute('select * from read_parquet(?)',[str(Q)]);point_rows={r[0]:dict(zip([x[0] for x in cur.description],r)) for r in cur.fetchall()}
def find(r):
 while parent[r]!=r:r=parent[r]
 return r
def distance(a,b):
 x,y,u,v=map(math.radians,[a[0],a[1],b[0],b[1]]);return 12742*math.asin(min(1,math.sqrt(math.sin((u-x)/2)**2+math.cos(x)*math.cos(u)*math.sin((v-y)/2)**2)))
def finite(v):return isinstance(v,(float,int)) and math.isfinite(v)
def valid(lat,lon):return finite(lat) and finite(lon) and -90<=lat<=90 and -180<=lon<=180 and (lat,lon)!=(0,0)
# Pin all existing accepted event/inclusion CSVs and block any source-record endpoint.
E=O.parent;eventids=set();eventfiles=[]
for p in E.rglob('*.csv'):
 if p==O/'accepted_identity_edge_delta.csv' or not any(t in p.name for t in ('event','inclusion','included_in')) or not ('accepted' in p.name or 'applied' in p.name):continue
 try:
  with p.open() as f:
   for row in csv.DictReader(f):
    for k,v in row.items():
     if v and ('source_record_id' in k or k in ('source_id','target_id')):eventids.add(v)
  eventfiles.append(p)
 except (UnicodeDecodeError,csv.Error):pass
for p in eventfiles:inputs[str(p)]=sha(p)
blockedroots={byid[s][1] for s in eventids if s in byid}
edges=[];points=[];witness=[];holds=[];touched=set()
for r in pairs:
 aid,bid=r['a_source_record_id'],r['b_source_record_id'];ra,rb=find(r['a_root']),find(r['b_root'])
 if ra==rb:continue
 reason=None
 if years[ra]&years[rb]:reason='component_year_overlap'
 elif r['a_root'] in blockedroots or r['b_root'] in blockedroots:reason='accepted_event_endpoint_component'
 elif '(часть' in r['a_settlement_name'].lower() or '(часть' in r['b_settlement_name'].lower():reason='part_record'
 donor=aid if r['a_accepted_point_present'] else bid
 dp=point_rows.get(donor)
 if not dp:reason='donor_missing_accepted_snapshot'
 if not reason:
  donorxy=(dp['latitude'],dp['longitude'])
  for side in ('a','b'):
   sid=r[side+'_source_record_id'];yr=r[side+'_census_year']
   if r[side+'_accepted_point_present']:
    xy=r[side+'_accepted_latitude'],r[side+'_accepted_longitude']
    if point_collisions[(yr,*xy)]>1:reason='accepted_point_shared_same_year'
    if distance(xy,donorxy)>5:reason='accepted_point_conflict'
   if not r[side+'_accepted_point_present'] and point_collisions[(yr,*donorxy)]>0:reason='donor_point_shared_in_target_year'
   xy=r[side+'_latitude'],r[side+'_longitude']
   if valid(*xy) and distance(xy,donorxy)>5:reason='raw_coordinate_conflict'
  # No inherited component point may disagree with accepted donor.
  for sid in members[ra]+members[rb]:
   t=point_rows.get(sid)
   if t and distance((t['latitude'],t['longitude']),donorxy)>5:reason='component_point_conflict'
 if reason:
  holds.append({'from_source_record_id':aid,'to_source_record_id':bid,'reason':reason});continue
 parent[rb]=ra;years[ra]|=years[rb];members[ra]+=members[rb];touched.update([r['a_root'],r['b_root']])
 edge={'from_source_record_id':aid,'to_source_record_id':bid,'from_year':r['a_census_year'],'to_year':r['b_census_year'],'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'unique_alltype_exact_name_region_explicit_county_matching_type_one_accepted_point_no_conflicts_v1','name_norm':r['a_name_norm'],'type_norm':r['a_type_norm'],'region_norm':r['a_region_norm'],'county_key':r['a_k'],'evidence_file':str(P),'evidence_sha256':inputs[str(P)],'population_comparability':'not_asserted','boundary_comparability_asserted':False}
 edges.append(edge)
 witness.append({**edge,'from_district_raw':r['a_district_raw'],'to_district_raw':r['b_district_raw'],'from_okato':r['a_okato'],'to_okato':r['b_okato'],'from_oktmo':r['a_oktmo'],'to_oktmo':r['b_oktmo'],'donor_source_record_id':donor,'witness':'Exact source name/region/county and type; single named row regardless type in each year; accepted own point donor; no raw/component coordinate conflict, accepted event endpoint, shared same-year point or component year overlap.'})
 for sid in (aid,bid):
  if sid in point_rows:continue
  row={'target_source_record_id':sid,'target_year':byid[sid][2],'latitude':dp['latitude'],'longitude':dp['longitude'],'coordinate_source_record_id':donor,'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_origin_ledger':str(Q),'coordinate_origin_ledger_sha256':inputs[str(Q)],'coordinate_origin_ledger_locator':'source_record_id='+donor,'point_origin_file':dp['point_origin_file'],'point_origin_sha256':dp['point_origin_sha256'],'point_origin_locator':dp['point_origin_locator'],'admission_rule':'explicit_representative_point_continuity_over_accepted_unique_county_name_type_identity','direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'boundary_comparability_asserted':False,'evidence_file':str(P),'evidence_sha256':inputs[str(P)]}
  points.append(row);point_rows[sid]={**dp,'source_record_id':sid};point_collisions[(byid[sid][2],dp['latitude'],dp['longitude'])]+=1
# Count only newly affected full-three-year components and additive original rows.
affected={find(r) for r in touched};gains=collections.Counter();pops=collections.Counter();newids=[]
for sid,root,yr,credit,point,pop,add,lat,lon in meta:
 fr=find(root)
 if not credit and add and fr in affected and years[fr]=={2002,2010,2021} and sid in point_rows and finite(pop):gains[yr]+=1;pops[yr]+=pop;newids.append(sid)
def write(name,rows,headers):
 with (O/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else headers);w.writeheader();w.writerows(rows)
write('accepted_identity_edge_delta.csv',edges,['from_source_record_id','to_source_record_id','decision_status','admission_rule'])
write('accepted_point_use_delta.csv',points,['target_source_record_id','coordinate_admission_status','latitude','longitude'])
write('witnesses.csv',witness,['from_source_record_id','to_source_record_id','witness'])
write('held_pairs.csv',holds,['from_source_record_id','to_source_record_id','reason'])
write('projected_new_credits.csv',[{'source_record_id':s,'census_year':byid[s][2],'population':byid[s][5]} for s in newids],['source_record_id','census_year','population'])
receipt={'candidate_pairs':len(pairs),'accepted_identity_edges':len(edges),'new_point_uses':len(points),'holds':dict(collections.Counter(r['reason'] for r in holds)),'projected_unique_new_credits':dict(gains),'projected_credit_population':dict(pops),'inputs':inputs,'national_application_performed':False,'raw_population_codes_unknowns_modified':False,'outputs':{p.name:sha(p) for p in O.glob('*.csv')}}
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ('inputs','outputs')},ensure_ascii=False),flush=True)

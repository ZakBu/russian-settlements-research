from pathlib import Path
import pandas as pd,json,re,math,hashlib,xlrd
O=Path(__file__).parent; R=O.parents[2]; B=Path('/workspace/scratch/residual-20261013/base15')
f=pd.read_parquet(B/'applied_state_observations.parquet').fillna(''); b=f.set_index('source_record_id'); groups=f.groupby('root').source_record_id.apply(list).to_dict()
pdpoint=pd.read_parquet(B/'applied_point_snapshot.parquet');p={}
c=pd.read_csv(R/'research_rebuild/evidence/residual_root_20261013/missing_year_exact_name_candidates.csv').fillna('')
regions=['мордовия','чувашская','смоленская','тамбовская','пермский','краснодарский','самарская','башкортостан','волгоградская','дагестан','пензенская','саратовская','северная осетия алания','ставропольский','татарстан','удмуртская','ульяновская','адыгея']
c=c[c.region.isin(regions)&pd.to_numeric(c.distance_km,errors='coerce').le(5)&c.no_component_year_overlap.eq(True)]
def sha(q):return hashlib.sha256(Path(q).read_bytes()).hexdigest()
def dist(a,z):
 try:la,lo,za,zo=map(math.radians,map(float,[a['latitude'],a['longitude'],z['latitude'],z['longitude']]))
 except(ValueError,KeyError,TypeError):return None
 return 12742*math.asin(min(1,math.sqrt(math.sin((za-la)/2)**2+math.cos(la)*math.cos(za)*math.sin((zo-lo)/2)**2)))
def norm(s):return ' '.join(re.sub('[^а-яa-z0-9]+',' ',str(s).lower().replace('ё','е')).split())
def county(s):return ' '.join(re.sub(r'\b(муниципальный|городской|район|округ|город|р н)\b',' ',norm(s)).split())
raw={};witness={}
def wit(sid):
 if sid in witness:return witness[sid]
 v=b.loc[sid].to_dict();pt={k:x for k,x in p.get(sid,{}).items() if str(x) not in ('','nan','None')};w={'source_record_id':sid,'native_observation_json':json.dumps(v,ensure_ascii=False),'accepted_point_provenance_json':json.dumps(pt,ensure_ascii=False),'county':v['district_raw']}
 m=re.match(r'(2002|2010):([^:]+\.xls):(.+):(\d+)$',sid)
 if m:
  yr,fn,sh,rr=m.groups();q=Path('/workspace/settlements-raw/data/raw')/yr/fn
  if q.exists():
   if str(q) not in raw:raw[str(q)]=(xlrd.open_workbook(str(q)),sha(q))
   bk,h=raw[str(q)];s=bk.sheet_by_name(sh) if sh in bk.sheet_names() else bk.sheet_by_index(int(sh));row=int(rr)-1;cells=s.row_values(row);ctx=[]
   for i in range(max(0,row-8),min(s.nrows,row+9)):ctx.append({'row_1based':i+1,'cells':s.row_values(i)[:12]})
   cw=[]
   for i in range(row,-1,-1):
    vals=s.row_values(i)[:8]
    hits=[x for x in vals if isinstance(x,str) and ('район' in x.lower() or 'подчинен' in x.lower())]
    if hits:cw={'row_1based':i+1,'cells':vals,'literal':hits};break
   w.update(raw_file=str(q),raw_sha256=h,raw_locator=f'{sh}!row={rr}',raw_cells_json=json.dumps(cells,ensure_ascii=False),raw_context_json=json.dumps(ctx,ensure_ascii=False),prior_county_heading_json=json.dumps(cw,ensure_ascii=False))
   if not w['county'] and cw:w['county']=cw['literal'][0]
 witness[sid]=w;return w
cn=set(c['name'].map(norm));needed=set(f[f.region_norm.isin(regions)&f.name_norm.isin(cn)].source_record_id);p=pdpoint[pdpoint.target_source_record_id.isin(needed)].fillna('').drop_duplicates('target_source_record_id').set_index('target_source_record_id').to_dict('index');del pdpoint
parent={}
def root(x):
 parent.setdefault(x,x)
 if parent[x]!=x:parent[x]=root(parent[x])
 return parent[x]
for v in c.to_dict('records'):
 aa,zz=b.loc[v['from_source_record_id'],'root'],b.loc[v['to_source_record_id'],'root'];parent[root(zz)]=root(aa)
components={}
for rr in parent:components.setdefault(root(rr),set()).update(groups[rr])
cases={}
for v in c.to_dict('records'):
 a,z=v['from_source_record_id'],v['to_source_record_id'];ids=sorted(components[root(b.loc[a,'root'])]);key=tuple(ids)
 cases.setdefault(key,[]).append(v)
reviews=[]; edges=[]
for ids,pairs in cases.items():
 v=pairs[0];a,z=v['from_source_record_id'],v['to_source_record_id'];name=b.loc[a,'name_norm'];reg=b.loc[a,'region_norm'];ty=b.loc[a,'type_norm'];ww=[wit(s) for s in ids];yrs=[int(b.loc[s,'census_year']) for s in ids]
 rivals=[]
 for x in f[f.region_norm.eq(reg)&f.name_norm.eq(name)].to_dict('records'):
  dd=dist(p.get(a,{}),p.get(x['source_record_id'],{}));rivals.append({'source_record_id':x['source_record_id'],'year':x['census_year'],'name':x['settlement_name'],'type':x['type_norm'],'county':x['district_raw'],'root':x['root'],'population':x['population'],'distance_km':dd,'candidate_member':x['source_record_id'] in ids})
 nearby=[x for x in rivals if not x['candidate_member'] and x['distance_km'] is not None and x['distance_km']<=5]
 counties=[county(w['county']) for w in ww];types={b.loc[s,'type_norm'] for s in ids};scopes=[b.loc[s,'population_scope'] for s in ids];full=set(yrs)=={2002,2010,2021} and len(yrs)==3
 status='hold_native_scope_or_county_review'
 if not full:status='hold_not_unique_full3'
 elif nearby:status='hold_nearby_namesake'
 elif len(types)>1:status='hold_native_type_variation'
 elif len(set(counties))==1 and all(counties):status='proposed_literal_county_rule'
 review={'case':reg+':'+v['name'],'status':status,'component_source_ids_json':json.dumps(ids),'years':','.join(map(str,yrs)),'counties_json':json.dumps(counties,ensure_ascii=False),'types_json':json.dumps(list(types),ensure_ascii=False),'scopes_json':json.dumps(scopes,ensure_ascii=False),'all_regional_namesakes_json':json.dumps(rivals,ensure_ascii=False),'nearby_competitors_json':json.dumps(nearby,ensure_ascii=False),'candidate_pairs_json':json.dumps(pairs,ensure_ascii=False)};reviews.append(review)
 for pair in pairs:
  aa,zz=sorted([pair['from_source_record_id'],pair['to_source_record_id']])
  if (aa,zz) in {(x['from_source_record_id'],x['to_source_record_id']) for x in edges}:continue
  edges.append({'from_source_record_id':aa,'to_source_record_id':zz,'relation':'same_place','decision_status':'proposed_root_review','case':review['case'],'screen_status':status,'source_context_witness_file':str(O/'source_witnesses.csv.gz'),'accepted_point_distance_km':pair['distance_km'],'admission_rule':'Actual native census leaf reopened with original count and type; frozen accepted ownpoint native binding provenance retained; full component and all same-region namesakes exposed; county/type/event/source-scope verification required before admission.','boundary_comparability_asserted':False,'historical_census_coordinate_asserted':False})
pd.DataFrame(reviews).to_csv(O/'reviews.csv',index=False);pd.DataFrame(edges).to_csv(O/'proposed_identity_edges.csv',index=False);pd.DataFrame(witness.values()).to_csv(O/'source_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0}); f[f.source_record_id.isin(witness)].to_csv(O/'frozen_observations.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(O/'manifest.json').write_text(json.dumps({'status':'screen_for_independent_root_review_not_admitted','cases':len(reviews),'candidate_edges':len(edges),'input_hashes':{str(B/x):sha(B/x) for x in ['applied_state_observations.parquet','applied_point_snapshot.parquet']},'raw_hashes':{q:h for q,(_,h) in raw.items()},'output_hashes':{str(q):sha(q) for q in O.glob('*.csv*')},'population_modified':False,'new_point_admission':False},ensure_ascii=False,indent=2));print(pd.DataFrame(reviews)[['case','status','counties_json','years']].to_string(index=False))

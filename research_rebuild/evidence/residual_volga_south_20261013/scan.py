import pandas as pd,numpy as np,json,hashlib,pathlib,re
Z=pathlib.Path(__file__).parent
A=pd.read_csv('research_rebuild/evidence/over500_root_20261009/applied_over500_working_checkpoint.csv.gz',low_memory=False)
D=pd.read_parquet('publication/stage71/applied_state_observations.parquet');P=pd.read_parquet('publication/stage71/applied_point_snapshot.parquet',columns=['target_source_record_id','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator']);P=P.drop_duplicates('target_source_record_id',keep='last').set_index('target_source_record_id');D=D.set_index('source_record_id',drop=False);D.loc[D.index.intersection(A.source_record_id),'root']=A.set_index('source_record_id').loc[D.index.intersection(A.source_record_id),'root'];T=pd.read_csv(Z/'assigned_targets.csv')
def county(s):
 s=str(s).lower().replace('ё','е');s=re.sub(r'городской округ|муниципальный|муниципальная|муниципальное|район|округ|город-курорт|город|р-н','',s);return re.sub(r'[^а-яa-z0-9]','',s)
D=D[D.region_norm.isin(T.region_norm.unique())];D['county']=D.district_raw.map(county)
C=D.groupby('root').county.apply(lambda a:sorted(set(x for x in a if x not in ['nan','none',''])))
def dist(a,b,c,d):
 x,y,z,w=map(lambda v:np.radians(float(v)),[a,b,c,d]);return 6371*2*np.arcsin(np.sqrt(np.sin((x-z)/2)**2+np.cos(x)*np.cos(z)*np.sin((y-w)/2)**2))
rows=[]
for t in T.itertuples():
 for y in set([2002,2010,2021])-set(map(int,str(t.component_years).split(','))):
  cs=D[(D.census_year==y)&(D.region_norm==t.region_norm)&(D.name_norm==t.name_norm)]
  for u in cs.itertuples():
   if u.source_record_id not in P.index:continue
   q=P.loc[u.source_record_id]
   if pd.isna(q.latitude) or pd.isna(q.longitude):continue
   km=dist(t.accepted_ownpoint_latitude,t.accepted_ownpoint_longitude,q.latitude,q.longitude)
   if km>5:continue
   ct=C.get(t.root,[]);cu=C.get(u.root,[]);same=bool(set(ct)&set(cu));rows.append(dict(left_source_record_id=t.source_record_id,right_source_record_id=u.source_record_id,left_root=t.root,right_root=u.root,name=t.settlement_name,region=t.region_norm,left_year=t.census_year,right_year=y,left_population=t.effective_population,right_population=u.population,left_counties='|'.join(ct),right_counties='|'.join(cu),county_match=same,distance_km=km,region_name_year_candidates=len(cs),point_origin_file=q.point_origin_file,point_origin_sha256=q.point_origin_sha256,point_origin_locator=q.point_origin_locator))
R=pd.DataFrame(rows).drop_duplicates(['left_root','right_root']);R.to_csv(Z/'exact_name_spatial_candidates.csv',index=False);print(R.to_string(index=False,max_colwidth=35));print(len(R))

import pandas as pd,json,pathlib
obs=pd.read_parquet('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet');n=pd.read_parquet('/dev/shm/over500-20261009/south_native_current.parquet').reset_index();z=obs[obs.census_year==2021].merge(n,on='source_record_id',suffixes=('','_native'));r=pd.read_csv('/dev/shm/over500-20261009/south_remaining.csv');a=pd.read_csv('research_rebuild/evidence/over500_south_remaining_points_20261009/accepted_point_use_delta.csv');r=r[~r.source_record_id.isin(a.target_source_record_id)];out=[]
for _,t in r.iterrows():
 prefix,num=t.source_record_id.rsplit(':',1);num=int(num);rows=obs[obs.source_record_id.isin([prefix+':'+str(k) for k in range(num-5,num+6)])];rows=rows.copy();rows['row']=rows.source_record_id.str.rsplit(':',n=1).str[-1].astype(int);rows=rows.sort_values('row');neighbors=[]
 for _,v in rows.iterrows():
  q=z[(z.region_norm==t.region_norm)&(z.name_norm==v.name_norm)&(z.type_norm==v.type_norm)];neighbors.append(dict(row=int(v.row),name=v.settlement_name,type=v.settlement_type,candidates=q[['source_record_id','settlement_name','mun_upper','mun_lower','oktmo_native']].to_dict('records')))
 out.append(dict(target_source_record_id=t.source_record_id,name=t.settlement_name,neighbors=neighbors))
pathlib.Path('/dev/shm/over500-20261009/south_remaining_roster_context.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));
for t in out:
 print('\nTARGET',t['name'],t['target_source_record_id']);
 for v in t['neighbors']:print(v['row'],v['name'],[(q['source_record_id'].rsplit(':',1)[-1],q['mun_upper'],q['mun_lower']) for q in v['candidates']])

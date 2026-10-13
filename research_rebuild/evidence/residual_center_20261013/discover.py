from pathlib import Path
import pandas as pd, re,json,math,hashlib
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent
f=pd.read_parquet(R/'publication/stage71/applied_state_observations.parquet').fillna('');d=pd.read_csv(R/'research_rebuild/evidence/over500_root_20261009/applied_over500_working_checkpoint.csv.gz',low_memory=False).fillna('');t=pd.read_csv(O/'targets.csv').fillna('');print('sizes',len(f),len(d))
# Current checkpoint supersedes stage71 observation/component fields when present.
f=f[~f.source_record_id.isin(d.source_record_id)]; f=pd.concat([f,d],ignore_index=True).fillna('');b=f.set_index('source_record_id');
from collections import defaultdict
groups=defaultdict(list)
for sid,root in zip(f.source_record_id,f.root):groups[root].append(sid)
print('grouped',flush=True)
print('read points',flush=True)
p=pd.read_parquet(R/'publication/stage71/applied_point_snapshot.parquet',columns=['target_source_record_id','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator']).drop_duplicates('target_source_record_id').set_index('target_source_record_id').to_dict('index')
for v in d[d.has_ownpoint.eq(True)].to_dict('records'):p[v['source_record_id']]={'latitude':v['accepted_ownpoint_latitude'],'longitude':v['accepted_ownpoint_longitude'],'point_origin_file':v['accepted_ownpoint_point_origin_file'],'point_origin_sha256':v['accepted_ownpoint_point_origin_sha256'],'point_origin_locator':v['accepted_ownpoint_point_origin_locator']}
def norm(s):return ' '.join(re.sub('[^а-яa-z0-9]+',' ',str(s).lower().replace('ё','е')).split())
def county(s):return ' '.join(re.sub(r'\b(муниципальн(?:ый|ого|ое|ая)|городск(?:ой|ого|ое)|район(?:а)?|округ(?:а)?|город(?:а)?|р\s*н)\b',' ',norm(s)).split())
def dist(a,b):
 
 try:la,lo=map(math.radians,map(float,[a['latitude'],a['longitude']]));lb,lob=map(math.radians,map(float,[b['latitude'],b['longitude']]))
 except (ValueError,TypeError):return None
 return 6371*2*math.asin(min(1,math.sqrt(math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lob-lo)/2)**2)))
f['county']=f.district_raw.map(county);n=pd.read_csv(O/'native.csv.gz').fillna('');nw=n.set_index('source_record_id').to_dict('index')
# literal native county witness overrides empty county only.
fallback=f.source_record_id.map({sid:county(v.get('actual_county_key','')) for sid,v in nw.items()}).fillna(''); f.loc[f.county.eq(''),'county']=fallback[f.county.eq('')]
import pickle
with open(O/'discovery_state.pkl','wb') as h:pickle.dump((f,d,t,p,groups,nw),h)
keys=['region_norm','name_norm'];out=[]
for a in t.to_dict('records'):
 ids=groups[a['root']];years={int(b.loc[i,'census_year']) for i in ids};ca=county(a['district_raw']);ca=ca or county(nw.get(a['source_record_id'],{}).get('actual_county_key',''))
 for z in f[(f.region_norm.eq(a['region_norm']))&f.name_norm.eq(a['name_norm'])&~f.census_year.isin(years)].to_dict('records'):
  if not z['is_additive_settlement_record']:continue
  zs=groups[z['root']];zy={int(b.loc[i,'census_year']) for i in zs};dc=dist(p[a['source_record_id']],p[z['source_record_id']]) if a['source_record_id'] in p and z['source_record_id'] in p else None
  out.append({'a':a['source_record_id'],'b':z['source_record_id'],'name':a['settlement_name'],'a_type':a['type_norm'],'b_type':z['type_norm'],'a_county':ca,'b_county':z['county'],'distance':dc,'a_years':','.join(map(str,sorted(years))),'b_years':','.join(map(str,sorted(zy))),'year_conflict':bool(years&zy),'full3':years|zy=={2002,2010,2021},'a_pop':a['population'],'b_pop':z['population']})
pd.DataFrame(out).to_csv(O/'candidate_pairs.csv',index=False);print(pd.DataFrame(out).query('distance<5').to_string(index=False))

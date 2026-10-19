#!/usr/bin/env python3
"""Independently enumerate every name-relaxed WB link; never infer catchments."""
from pathlib import Path
import re,unicodedata,json,hashlib
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/wb_relaxed';O.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xyz(lat,lon):
 a=np.deg2rad(lat);b=np.deg2rad(lon);return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def norm(s):return ' '.join(re.sub(r'[^\w\s-]',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).split())
def main():
 paths=[B/'anchor_research_20261019/data/point_axis.parquet',N/'services/wb_objects_crosswalk.parquet',N/'services/wb_type_relaxed_object_links.parquet',N/'services/wb_name_relaxed_features.parquet'];before={str(p):sha(p) for p in paths};axis=pd.read_parquet(paths[0]);d=pd.read_parquet(paths[1]);author=pd.read_parquet(paths[2]);features=pd.read_parquet(paths[3]).set_index('id').reindex(axis.id);checks=[]
 def ck(n,v,detail=None):checks.append({'name':n,'pass':bool(v),'detail':detail})
 vec=xyz(axis.lat,axis.lon);tree=cKDTree(vec);z=d[d.wb_location_quality.eq('nearest_coordinate_candidate')];names=axis.name.map(norm).to_numpy();patterns={n:re.compile(r'(?<!\w)'+re.escape(n)+r'(?!\w)') for n in set(names) if len(n)>=3};records=[];coords=xyz(z.latitude,z.longitude)
 neighbourhoods=tree.query_ball_point(coords,r=2*np.sin(10/(2*6371)))
 for (_,row),v,near in zip(z.iterrows(),coords,neighbourhoods):
  head=re.split(r'\b(?:улица|ул\.?|проспект|пр-кт|переулок|пер\.?|шоссе|бульвар|площадь|проезд|набережная)\b',norm(row.address),maxsplit=1)[0];matched=[k for k in near if names[k] in patterns and patterns[names[k]].search(head)]
  if not matched:continue
  width=max(len(names[k]) for k in matched);matched=[k for k in matched if len(names[k])==width]
  if len(matched)!=1:continue
  k=matched[0];distance=6371*np.arctan2(np.linalg.norm(np.cross(v,vec[k])),np.dot(v,vec[k]));records.append({'object_id':row.object_id,'candidate_id':axis.iloc[k].id,'distance_km':distance})
 r=pd.DataFrame(records);ck('unique_reconstructed_object_keys',r.object_id.is_unique);ck('all_object_candidate_pairs',set(map(tuple,r[['object_id','candidate_id']].to_numpy()))==set(map(tuple,author[['object_id','candidate_id']].to_numpy())));joined=r.merge(author,on=['object_id','candidate_id'],how='outer',suffixes=('_independent','_author'),indicator=True);ck('all_independent_distances',np.allclose(joined.distance_km_independent,joined.distance_km_author,rtol=0,atol=1e-8));ck('strict_baseline_never_replaced',not set(r.object_id)&set(d.loc[d.wb_strict_uid.notna(),'object_id']))
 all_links=d[['object_id','wb_strict_uid','typePoint']].merge(r[['object_id','candidate_id']],on='object_id',how='left',validate='one_to_one');all_links['id']=all_links.wb_strict_uid.fillna(all_links.candidate_id)
 for col in features:
  if col=='wb_name_relaxed_additional_locations':g=r.groupby('candidate_id').size()
  elif col=='wb_name_relaxed_inclusive_all_types_locations':g=all_links.groupby('id').size()
  elif '_type_' in col:
   typ=int(re.search(r'_type_(\d+)_',col).group(1));g=all_links.loc[all_links.typePoint.eq(typ)].groupby('id').size()
  elif col in ['wb_name_relaxed_inclusive_focus_locations','wb_name_relaxed_inclusive_expanded_locations']:
   types=[8,34] if '_focus_' in col else [8,34,28,53,54];g=all_links.loc[all_links.typePoint.isin(types)].groupby('id').size()
  else:raise ValueError('Unknown feature '+col)
  ck('every_settlement_'+col,np.array_equal(g.reindex(axis.id,fill_value=0).to_numpy(),features[col].to_numpy()))
 ck('inputs_stable',all(sha(Path(p))==v for p,v in before.items()));r.to_csv(O/'independent_relaxed_links.csv',index=False);summary={'reviewed_coordinate_only_objects':len(z),'additional_objects':len(r),'additional_UIDs':int(r.candidate_id.nunique()),'additional_UIDs_without_old_strict':len(set(r.candidate_id)-set(d.wb_strict_uid.dropna()))};result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'summary':summary,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'meaning':'Conditional name-coordinate geocoding with relaxed settlement type; it proves neither external service nor institutional catchments.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks',summary,flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

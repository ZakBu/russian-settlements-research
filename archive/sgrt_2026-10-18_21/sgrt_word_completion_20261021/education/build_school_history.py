#!/usr/bin/env python3
"""Dated OSM2021 education inventory; changes in assertions are not service openings."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,osmium
from build_school_features import ROOT,AXIS,link,dedup,school_group,sha
SOURCE=Path('/workspace/scratch/medical_mass/history2021/medical_reference_complete.osm.pbf')
class Handler(osmium.SimpleHandler):
 def __init__(self):super().__init__();self.rows=[]
 def emit(self,o,typ,lat,lon,role):
  tags=dict(o.tags)
  if tags.get('amenity') not in ['school','kindergarten','college','university']:return
  self.rows.append({'osm_type':typ,'osm_id':o.id,'lat':lat,'lon':lon,'geometry_role':role,'name':tags.get('name'),'amenity':tags.get('amenity'),'healthcare':tags.get('healthcare'),'tags_json':json.dumps(tags,ensure_ascii=False)})
 def node(self,n):
  if n.location.valid():self.emit(n,'node',n.location.lat,n.location.lon,'source_node')
 def way(self,w):
  if w.tags.get('amenity') not in ['school','kindergarten','college','university']:return
  a=[(n.lat,n.lon) for n in w.nodes if n.location.valid()]
  if a:self.emit(w,'way',float(np.mean([v[0] for v in a])),float(np.mean([v[1] for v in a])),'vertex_mean_not_interior_point')
def build():
 if not SOURCE.exists():raise RuntimeError('Shared reference-complete history PBF not ready')
 axis=pd.read_parquet(AXIS);h=Handler();h.apply_file(str(SOURCE),locations=True,idx='sparse_mem_array')
 d=pd.DataFrame(h.rows);d['site_id']='osm:'+d.osm_type+':'+d.osm_id.astype(str);d['education_group']=d.apply(school_group,axis=1)
 d['source_snapshot']='2021-01-01';d['source']='OpenStreetMap via Geofabrik Russia historical snapshot';d['source_license']='ODbL-1.0';d=dedup(link(d,axis))
 # Reference axis retained modern2021population units consistently between snapshots.
 d.to_parquet(ROOT/'education_objects_2021.parquet',index=False)
 features=axis[['id']].copy()
 for g in ['school','preschool','college','university','specialized_non_general_school']:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   z=d[d.education_group.eq(g)&d[key].notna()].drop_duplicates([key,'canonical_site_id'])
   features[f'education_osm2021_{g}_{mode}_count']=features.id.map(z.groupby(key).size()).fillna(0).astype('int32')
 features['education_history_comparison_scope']='OSM mapped object assertions; difference does not establish physical opening/closure or service change'
 features.to_parquet(ROOT/'settlement_features_2021_full_axis.parquet',index=False)
 current=pd.read_parquet(ROOT/'education_objects.parquet')
 c=current[['site_id','education_group','baseline_uid','candidate_uid']].copy();c.columns=['site_id','group2026','baseline_uid2026','candidate_uid2026']
 b=d[['site_id','education_group','baseline_uid','candidate_uid']].copy();b.columns=['site_id','group2021','baseline_uid2021','candidate_uid2021']
 comparison=c.merge(b,on='site_id',how='outer',indicator=True,validate='one_to_one');comparison['comparison_scope']='OSM identity observed in selected education tag snapshots; missing not proof of school closure'
 comparison.to_parquet(ROOT/'education_osm_identity_snapshot_comparison.parquet',index=False)
 school=d[d.education_group.eq('school')]
 receipt={'source_url':'https://download.geofabrik.de/russia-210101.osm.pbf','school_baseline_settlements':int(school.baseline_uid.nunique()),'school_candidate_settlements':int(school.candidate_uid.nunique()),'school_union_settlements':int(pd.concat([school.baseline_uid,school.candidate_uid]).dropna().nunique()),'status':'COMPLETE','source_snapshot':'2021-01-01','shared_filtered_path':str(SOURCE),'shared_filtered_bytes':SOURCE.stat().st_size,'shared_filtered_sha256':sha(SOURCE),'full_original_sha256':'1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe','rows':len(d),'groups':d.education_group.value_counts().to_dict(),'baseline_settlements':int(d.baseline_uid.nunique()),'candidate_settlements':int(d.candidate_uid.nunique()),'snapshot_identity_overlap':comparison['_merge'].value_counts().to_dict(),'axis_rows':len(features),'relation_geometry_not_extracted':True,'absence_not_physical_closure':True,'reference_axis':'current2021 additive units with coordinates for consistent comparison'}
 assert len(features)==173527 and features.id.is_unique and d.site_id.is_unique
 assert not(d.baseline_uid.notna()&d.candidate_uid.notna()).any()
 for g in d.education_group.unique():
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   z=d[d.education_group.eq(g)&d[key].notna()].drop_duplicates([key,'canonical_site_id']);assert features[f'education_osm2021_{g}_{mode}_count'].sum()==len(z)
 receipt['validation_status']='PASS'
 (ROOT/'history_build_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':build()

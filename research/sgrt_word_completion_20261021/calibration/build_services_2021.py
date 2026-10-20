#!/usr/bin/env python3
"""Dated trade/finance/government OSM assertions, with explicit/candidate links."""
from pathlib import Path
import sys
import json
import time
import hashlib
import osmium
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'education'))
from build_school_features import link, dedup
SOURCE=Path('/workspace/scratch/sgrt_transport/russia-210101.osm.pbf')
FILTERED=Path('/workspace/scratch/sgrt_validation/services2021_reference_complete.osm.pbf')
AMENITIES={'bank','atm','post_office','townhall','marketplace'}
def selected(tags):
    return bool(tags.get('shop')) or tags.get('amenity') in AMENITIES or tags.get('office')=='government'
def group(tags):
    if tags.get('amenity') in {'bank','atm'}:return tags.get('amenity')
    if tags.get('amenity')=='post_office':return 'post_office'
    if tags.get('office')=='government' or tags.get('amenity')=='townhall':return 'administration'
    if tags.get('amenity')=='marketplace':return 'market'
    if tags.get('shop') in {'supermarket','mall','department_store'}:return 'large_retail'
    return 'other_retail'
class Inventory(osmium.SimpleHandler):
    def __init__(self):super().__init__();self.rows=[]
    def emit(self,o,kind,lat,lon,geometry):
        tags=dict(o.tags)
        if not selected(tags):return
        if any(k.startswith(('disused:','abandoned:','demolished:')) for k in tags) and not selected({k:v for k,v in tags.items() if ':' not in k}):return
        self.rows.append({'osm_type':kind,'osm_id':o.id,'lat':lat,'lon':lon,'geometry_role':geometry,'name':tags.get('name'),'amenity':tags.get('amenity'),'tags_json':json.dumps(tags,ensure_ascii=False),'service_group':group(tags)})
    def node(self,o):
        if o.location.valid():self.emit(o,'node',o.location.lat,o.location.lon,'source_node')
    def way(self,o):
        if not selected(o.tags):return
        xy=[(n.lat,n.lon) for n in o.nodes if n.location.valid()]
        if xy:self.emit(o,'way',float(np.mean([v[0] for v in xy])),float(np.mean([v[1] for v in xy])),'vertex_mean_not_interior_point')
def main():
    started=time.time();n=0
    if not FILTERED.exists():
        with osmium.BackReferenceWriter(str(FILTERED),str(SOURCE),remove_tags=True,relation_depth=1) as writer:
            for obj in osmium.FileProcessor(str(SOURCE)).with_filter(osmium.filter.KeyFilter('shop','amenity','office')):
                if selected(obj.tags):writer.add(obj);n+=1
        print('Reference-complete selected assertions',n,flush=True)
    h=Inventory();h.apply_file(str(FILTERED),locations=True,idx='sparse_mem_array')
    d=pd.DataFrame(h.rows);d['site_id']='osm:'+d.osm_type+':'+d.osm_id.astype(str)
    axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet');d=link(d,axis)
    d['education_group']=d.service_group;d=dedup(d).drop(columns='education_group')
    d['snapshot']='2021-01-01T21:42:03Z';d['license']='ODbL-1.0'
    d.to_parquet(ROOT/'calibration/services_2021_objects.parquet',index=False)
    f=axis[['id']].copy()
    for g in sorted(d.service_group.unique()):
        for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
            z=d[d.service_group.eq(g)&d[key].notna()].drop_duplicates([key,'canonical_site_id'])
            f[f'services_osm2021_{g}_{mode}_count']=f.id.map(z.groupby(key).size()).fillna(0).astype('int32')
    f['service_absence_means_unknown']=True
    f.to_parquet(ROOT/'calibration/services_2021_settlement_features.parquet',index=False)
    receipt={'source_url':'https://download.geofabrik.de/russia-210101.osm.pbf','source_sha256':'1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe','snapshot':'2021-01-01T21:42:03Z','objects':len(d),'by_service':d.service_group.value_counts().to_dict(),'explicit_linked_settlements':d.baseline_uid.nunique(),'candidate_linked_settlements':d.candidate_uid.nunique(),'axis_rows':len(f),'relations_geometry_not_extracted':True,'absence_not_proof_of_service_absence':True,'travel_or_catchment_used_for_identity':False,'seconds':round(time.time()-started,1)}
    assert d.site_id.is_unique and f.id.is_unique and len(f)==len(axis)
    (ROOT/'calibration/services_2021_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()

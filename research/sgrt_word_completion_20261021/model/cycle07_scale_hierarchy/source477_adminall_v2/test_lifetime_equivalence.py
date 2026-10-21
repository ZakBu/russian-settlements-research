"""Memory lifetime changes must not alter frozen Forest outputs/stop/knees."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np,pandas as pd
from scipy import sparse
from route_field import RouteField
from forest import Forest

def field():
 ids=list('ABCDxy');x=np.array([0,1,2,3,.5,2.5]);t=np.abs(x[:,None]-x[:4]).astype('float32')
 r=sparse.coo_matrix((t.ravel(),(np.repeat(np.arange(6),4),np.tile(np.arange(4),6))),shape=(6,4)).tocsr()
 return RouteField(r,pd.DataFrame({'canonical_id':ids}),pd.DataFrame({'id':list('ABCD'),'population_2021':[10]*4}),np.ones(4))

def run():
 a=Forest(field(),list('ABCDxy'),'protocol',gamma=.1);b=Forest(field(),list('ABCDxy'),'protocol',gamma=.1)
 for cap in [1.,2.,3.]:
  x=a.one_cap(cap);y=b.one_cap(cap)
  assert np.array_equal(x['labels'],y['labels']) and x['objective_curve']==y['objective_curve'] and x['knee']==y['knee']
  assert {u.members for u in x['forest_units']}=={u.members for u in y['forest_units']}
  assert x['events']==y['events']
  b.member_masks.clear();b.attachment_events.clear();b.f.origin_mask_cache.clear();b.f.graph_cache.clear()
 print('Three-cap warmcache vs cacheeviction lifetime exact labels/Q/knees/events/partition equivalence PASS')
if __name__=='__main__':run()

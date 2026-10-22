import numpy as np,pandas as pd
from scipy import sparse
from route_field import RouteField,within_cap
from forest import Forest

def run():
 assert within_cap(np.asarray([180.00010681152344,180.00009155273438],dtype='float32'),180).tolist()==[False,True]
 ids=list('ABCDxy');positions=np.array([0,1,2,3,.5,2.5]);times=np.abs(positions[:,None]-positions[:4][None,:]).astype('float32')
 # Preserve explicit self0 entries as real source records.
 coo=sparse.coo_matrix((times.ravel(),(np.repeat(np.arange(6),4),np.tile(np.arange(4),6))),shape=(6,4))
 field=RouteField(coo.tocsr(),pd.DataFrame({'canonical_id':ids}),pd.DataFrame({'id':list('ABCD'),'population_2021':[10]*4}),np.ones(4))
 w,q,den=field.provider_graph(1.1)
 assert np.allclose(np.asarray(q.sum(axis=1)).ravel(),1.) and np.all(q.diagonal()==0)
 assert w[0,3]==0 and q[0,3]>0 # cap prunes support, NOT180 denominator
 f=Forest(field,ids,'synthetic-protocol',gamma=.1);s=f.one_cap(1.1)
 assert len(s['forest_units'])>1
 for u in s['forest_units']:
  core=f.selected_core(u.nuclei,f.mask(u,1.1));assert core is not None
  assert all(field.time(x,core)<=1.1+1e-4 for x in u.members)
 assert set.union(*[set(u.members) for u in s['forest_units']])==set(ids)
 assert sum(len(u.members) for u in s['forest_units'])==6
 assert not f.residuals
 assert len(f.attachment_events)==2
 assert all(e['uniform180_denominator']>0 and e['directed_choice_conditional_q']>0 for e in f.attachment_events)
 s2=f.one_cap(2.1)
 assert sum(len(u.members) for u in s2['forest_units'])==6
 for a in s['forest_units']:assert any(a.members<=b.members for b in s2['forest_units'])
 print('Actual sparse q/self/uniformdenominator, directchain, directedleaves, whole-child nextcap counterexamples PASS')
if __name__=='__main__':run()

"""Prospective estimand counterexamples: geometry cannot demote a source core."""
import numpy as np
import pandas as pd
from scipy import sparse
from forest import Forest,Territory
from route_field import RouteField

def fixture(times,mass=(1000.,10.)):
 providers=pd.DataFrame(dict(id=['city','town'],population_2021=[1000000.,1000.]))
 origins=pd.DataFrame(dict(canonical_id=['city','town','rural']))
 a=[];b=[];v=[]
 for i,row in enumerate(times):
  for j,t in enumerate(row):
   if t is not None:a.append(i);b.append(j);v.append(t)
 routes=sparse.coo_matrix((np.asarray(v,dtype='float32'),(a,b)),shape=(3,2)).tocsr()
 field=RouteField(routes,origins,providers,np.asarray(mass))
 return Forest(field,{'city','town','rural'},'fixture')

def main():
 # Town covers everybody at30, but source-metropolis cannot cover its child.
 f=fixture([[0,20],[70,0],[75,25]]);f.cap=30
 city=Territory('city',frozenset(['city']),frozenset([0]))
 town=Territory('town',frozenset(['town','rural']),frozenset([1]))
 feasible=f.mask(city,30)&f.mask(town,30)
 assert feasible==2 and f.selected_core({0,1},feasible) is None
 merged,why=f.envelope(city,town)
 assert merged is None and why['dominant_core_id']=='city' and why['weaker_feasible_core_not_substituted']
 # At90 the SAME children merge under city; child's members remain intact.
 f.cap=90;merged,w=f.envelope(city,town)
 assert merged.members==frozenset(['city','town','rural']) and w['core_id']=='city' and w['core_fixed_mass']==1000
 assert w['max_direct_minutes']==75
 # Actual missing strongest-core route is unknown, never a substitute town0.
 f=fixture([[0,20],[None,0],[None,25]]);f.cap=90
 assert f.envelope(city,town)[0] is None
 # EqualMi uses source ownpopulation before ID, even if another core feasible.
 f=fixture([[0,20],[70,0],[75,25]],mass=(10.,10.));f.cap=30
 assert f.selected_core({0,1},2) is None
 # Additional leaf does not demote a previously admitted dominant sourcecore.
 f=fixture([[0,20],[25,0],[75,25]]);f.cap=30
 parent,w=f.envelope(city,Territory('town',frozenset(['town']),frozenset([1])))
 assert parent is not None and w['core_id']=='city'
 assert f.envelope(parent,Territory('leaf',frozenset(['rural']),frozenset()))[0] is None
 print('Dominant-core demotion rejection, higher-cap acceptance, missing routes, ownP tie and leaf protection PASS')

if __name__=='__main__':main()

from dataclasses import dataclass
from aggregate_modularity import agglomerate
@dataclass(frozen=True)
class U:
 key:str
 members:frozenset

def run():
 us=[U(x,frozenset(x)) for x in 'ABCD']
 raw=[('A','B',2.,'AB'),('A','C',1.,'AC'),('B','C',3.,'BC'),('C','D',.1,'CD')]
 def allow(a,b):return U(''.join(sorted(a.members|b.members)),a.members|b.members),dict(actual_atomic_members=sorted(a.members|b.members))
 result,events,reject=agglomerate(us,raw,allow,gamma=.1)
 assert len(result)==1
 # Recompute each merge crossaffinity and each complete Q directly from ORIGINAL
 # atomic graph, independently of callback/cache/adjacency update implementation.
 groups={x:frozenset(x) for x in 'ABCD'}
 deg={x:sum(w for a,b,w,_ in raw if x in (a,b)) for x in 'ABCD'};S=sum(deg.values())
 for e in events:
  ga,gb=groups.pop(e['left']),groups.pop(e['right'])
  expected=sum(w for a,b,w,_ in raw if (a in ga and b in gb) or (b in ga and a in gb))
  assert abs(e['cross_affinity']-expected)<1e-12
  groups[e['parent']]=ga|gb
  q=sum(2*sum(w for a,b,w,_ in raw if a in g and b in g)/S-.1*(sum(deg[x] for x in g)/S)**2 for g in groups.values())
  assert abs(q-e['q'])<1e-12
 assert events[1]['cross_affinity']==3. and events[1]['left']=='A' # A-(BC) sums AB2+AC1, not one boundary edge
 def reject_all(a,b):return None,dict(reason='missing_native_member_direct_route')
 result,events,reject=agglomerate(us,raw,reject_all)
 assert len(result)==4 and not events and reject['envelope_rejected']>0
 # Starting a later resolution with an existing AB child must retain its internal
 # degree and affinity; dropping those would silently change the null graph.
 start=[U('AB',frozenset('AB')),U('C',frozenset('C')),U('D',frozenset('D'))]
 _,ev,_=agglomerate(start,[('AB','C',4.,'AB-C-original-twoedges'),('C','D',.1,'CD')],allow,.1,initial_original_degrees={'AB':8.,'C':4.1,'D':.1},initial_internal_unordered_weight={'AB':2.,'C':0.,'D':0.})
 assert abs(ev[0]['total_original_degree']-12.2)<1e-12
 assert abs(ev[0]['cross_affinity']-4)<1e-12
 print('Original-graph modularity, recomputed aggregate crossweights, carried-child original degrees and missing-envelope counterexamples PASS')
if __name__=='__main__':run()

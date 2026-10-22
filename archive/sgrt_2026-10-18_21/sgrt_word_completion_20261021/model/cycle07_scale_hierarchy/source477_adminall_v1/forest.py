"""Actual bottom-up bounded source-provider potential forest (prospective code)."""
from dataclasses import dataclass
import hashlib
import numpy as np
from scipy import sparse
from aggregate_modularity import agglomerate
from select_cuts import objective_knee
from route_field import within_cap

@dataclass(frozen=True)
class Territory:
 key:str
 members:frozenset
 nuclei:frozenset
 children:tuple=()
 ancestry_depth:int=0

class Forest:
 def __init__(self,field,native_ids,protocol_hash,tau=60.,gamma=1.,region_weights=None,symmetry='reciprocal'):
  self.f=field;self.native_ids=set(native_ids);self.protocol_hash=protocol_hash
  self.tau=tau;self.gamma=gamma;self.region_weights=region_weights;self.symmetry=symmetry
  self.np=len(field.providers);p=field.providers
  population=p.population_2021.to_numpy(float)
  self.priority=sorted(range(self.np),key=lambda i:(-field.mass[i],-population[i] if np.isfinite(population[i]) else float('inf'),str(p.id.iloc[i])))
  self.priority_rank={v:k for k,v in enumerate(self.priority)}
  self.nucleus_ids=p.id.astype(str).to_numpy()
  self.units=[Territory('seed:'+str(x),frozenset([str(x)]),frozenset([i])) for i,x in enumerate(p.id)]
  self.residuals=set(native_ids)-set(self.nucleus_ids)
  self.attachment_events=[];self.member_masks={};self.cap=None
 def identifier(self,members):
  h=hashlib.sha256();h.update(self.protocol_hash.encode())
  for x in sorted(members):h.update(b'\0');h.update(x.encode())
  return 'u:'+h.hexdigest()
 def rowmask(self,origin,cap):
  if not hasattr(self.f,'origin_mask_cache'):self.f.origin_mask_cache={}
  cachekey=(origin,float(cap))
  if cachekey in self.f.origin_mask_cache:return self.f.origin_mask_cache[cachekey]
  ids,t=self.f.row(origin);v=np.zeros(self.np,dtype='uint8');v[ids[within_cap(t,cap)]]=1
  # Source self attachment has time0; routes contain canonical self in normal case.
  k=self.f.provider_id_to_index.get(origin)
  if k is not None:v[k]=1
  result=int.from_bytes(np.packbits(v,bitorder='little').tobytes(),'little')
  self.f.origin_mask_cache[cachekey]=result
  return result
 def mask(self,u,cap):
  k=(u.key,cap)
  if k not in self.member_masks:
   mask=(1<<self.np)-1
   for origin in sorted(u.members):
    if origin in self.native_ids or origin in self.f.provider_id_to_index:
     mask &= self.rowmask(origin,cap)
     if not mask:break
   self.member_masks[k]=mask
  return self.member_masks[k]
 def selected_core(self,nuclei,feasible):
  if not nuclei:return None
  dominant=min(nuclei,key=self.priority_rank.get)
  return dominant if (feasible>>dominant)&1 else None
 def known_envelope_times(self,members,core):
  origins=[x for x in sorted(members) if x in self.native_ids or x in self.f.provider_id_to_index]
  rows=[self.f.origin_id_to_index.get(x,-1) for x in origins]
  if rows and min(rows)<0:raise AssertionError('affirmative feasible set contains unrouted origin')
  # Exact core bit already present in EVERY member route mask. Sparse0 fallback
  # therefore cannot manufacture an absent member/core pair here.
  values=np.asarray(self.f.routes[np.asarray(rows,dtype='int64'),np.full(len(rows),int(core),dtype='int64')]).ravel() if rows else np.empty(0)
  return values
 def envelope(self,a,b):
  members=a.members|b.members;nuclei=a.nuclei|b.nuclei
  feasible=self.mask(a,self.cap)&self.mask(b,self.cap)
  core=self.selected_core(nuclei,feasible)
  if core is None:
   dominant=min(nuclei,key=self.priority_rank.get) if nuclei else None
   return None,dict(reason='dominant_source_core_lacks_complete_member_direct_envelope',dominant_core_id=str(self.nucleus_ids[dominant]) if dominant is not None else None,dominant_fixed_mass=float(self.f.mass[dominant]) if dominant is not None else None,weaker_feasible_core_not_substituted=True)
  key=self.identifier(members);u=Territory(key,members,nuclei,(a.key,b.key),1+max(a.ancestry_depth,b.ancestry_depth));self.member_masks[(key,self.cap)]=feasible
  times=self.known_envelope_times(members,core)
  if not within_cap(times,self.cap).all():raise AssertionError('positive envelope violates raw directed member route')
  return u,dict(core_id=str(self.nucleus_ids[core]),core_index=int(core),core_fixed_mass=float(self.f.mass[core]),max_direct_minutes=float(np.max(times)) if len(times) else 0.,n_extent_members=len(times),n_historical_outside_extent=len(members)-len(times),cap_minutes=self.cap,central_object_definition='one_focal_core',core_selection='strongest_fixed_source_mass_before_feasibility_no_demotion')
 def attach_residuals(self,cap):
  bykey={u.key:u for u in self.units};provider_owner={i:u.key for u in self.units for i in u.nuclei}
  attached=[]
  for origin in sorted(self.residuals):
   idx,t=self.f.row(origin);denominator=float(np.sum(self.f.mass[idx]*np.exp(-t/self.tau)));keep=within_cap(t,cap)
   idx=idx[keep];t=t[keep]
   if not len(idx):continue
   g=self.f.mass[idx]*np.exp(-t/self.tau)
   order=np.lexsort((idx,-g));tried=set()
   for z in order:
    pidx=int(idx[z]);key=provider_owner[pidx]
    if key in tried:continue
    tried.add(key);parent=bykey[key]
    leaf=Territory('atom:'+origin,frozenset([origin]),frozenset())
    merged,witness=self.envelope(parent,leaf)
    if merged is None:continue
    bykey.pop(key);bykey[merged.key]=merged
    self.member_masks.pop((key,self.cap),None)
    self.member_masks.pop((leaf.key,self.cap),None)
    for j in merged.nuclei:provider_owner[j]=merged.key
    attached.append(origin)
    self.attachment_events.append(dict(origin_id=origin,original_directed_choice_provider=str(self.nucleus_ids[pidx]),directed_choice_minutes=float(t[z]),directed_choice_gravity=float(g[z]),directed_choice_conditional_q=float(g[z])/denominator if denominator else None,uniform180_denominator=denominator,previous_parent_unit=parent.key,new_unit=merged.key,cap_minutes=cap,**{'focal_'+k:v for k,v in witness.items()}))
    break
  self.residuals.difference_update(attached);self.units=list(bykey.values())
 def one_cap(self,cap):
  self.cap=float(cap);self.member_masks={}
  self.attach_residuals(cap)
  before=list(self.units);w,q,den=self.f.provider_graph(cap,self.tau,self.symmetry)
  if self.region_weights is not None:
   b=np.sqrt(np.asarray(self.region_weights,float));w=sparse.diags(b)@w@sparse.diags(b)
  # Aggregate original atomic graph to PREVIOUS whole units. Preserve internal
  # affinities and fixed original degree totals; no false graph renormalization.
  own={i:k for k,u in enumerate(before) for i in u.nuclei};keys=[u.key for u in before]
  labels=np.asarray([own[i] for i in range(self.np)],dtype='int32')
  upper=sparse.triu(w,k=1).tocoo();aa=labels[upper.row];bb=labels[upper.col];vv=upper.data
  internal=np.bincount(aa[aa==bb],weights=vv[aa==bb],minlength=len(before))
  degrees=np.bincount(labels,weights=np.asarray(w.sum(axis=1)).ravel(),minlength=len(before))
  mask=aa!=bb;lo=np.minimum(aa[mask],bb[mask]);hi=np.maximum(aa[mask],bb[mask])
  ag=sparse.coo_matrix((vv[mask],(lo,hi)),shape=(len(before),len(before))).tocsr().tocoo()
  edges=((keys[int(a)],keys[int(b)],float(v),'source_provider_edges:'+str(int(a))+':'+str(int(b))) for a,b,v in zip(ag.row,ag.col,ag.data))
  units,events,rejections=agglomerate(before,edges,self.envelope,self.gamma,initial_original_degrees={keys[i]:float(degrees[i]) for i in range(len(keys))},initial_internal_unordered_weight={keys[i]:float(internal[i]) for i in range(len(keys))})
  self.units=units
  if events:curve=[events[0]['initial_q']]+[x['q'] for x in events]
  else:
   S=degrees.sum();curve=[float(sum(2*internal/S-self.gamma*(degrees/S)**2)) if S else 0.]
  knee=objective_knee(curve)
  # Replay actual accepted events to recover the candidate knee partition.
  cut={u.key:u for u in before};registry={u.key:u for u in before}
  # Events have exact child IDs; regenerate membership without changing source.
  for e in events:
   a=registry[e['left']];b=registry[e['right']]
   registry[e['parent']]=Territory(e['parent'],a.members|b.members,a.nuclei|b.nuclei,(a.key,b.key),1+max(a.ancestry_depth,b.ancestry_depth))
  selected=knee.get('selected_merge')
  if selected is not None:
   for e in events[:selected]:cut.pop(e['left']);cut.pop(e['right']);cut[e['parent']]=registry[e['parent']]
  else:cut={u.key:u for u in units}
  label=np.empty(self.np,dtype='int32')
  for k,u in enumerate(sorted(cut.values(),key=lambda x:x.key)):
   for i in u.nuclei:label[i]=k
  return dict(cap=cap,units=list(cut.values()),forest_units=units,registry=registry,events=events,rejections=rejections,objective_curve=curve,knee=knee,labels=label,n_residuals=len(self.residuals),residual_ids=frozenset(self.residuals),n_zero_provider_denominators=int((den==0).sum()),q=q)

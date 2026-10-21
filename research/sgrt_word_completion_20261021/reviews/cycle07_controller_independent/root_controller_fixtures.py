import sys,json,math,pathlib,itertools
import numpy as np,pandas as pd
from scipy import sparse
repo=pathlib.Path('/workspace/russian-settlements-research');h=repo/'research/sgrt_word_completion_20261021/model/cycle07_scale_hierarchy';sys.path.insert(0,str(h))
from route_field import RouteField
from forest import Forest
from select_cuts import objective_knee,accept_stable_cut
ids=['A','B','C','D','x','y','z']; pids=ids[:4];mass=np.array([4.,3.,2.,1.]);pop=[400,300,200,100]
time=np.array([[0,12,48,np.nan],[15,0,35,80],[45,40,0,20],[95,70,23,0],[4,10,70,100],[100,75,5,10],[np.nan]*4],float)
a,b=np.where(np.isfinite(time));field=RouteField(sparse.coo_matrix((time[a,b].astype('float32'),(a,b)),shape=time.shape).tocsr(),pd.DataFrame({'canonical_id':ids}),pd.DataFrame({'id':pids,'population_2021':pop}),mass.copy());f=Forest(field,set(ids),'ROOT-INDEPENDENT-FIXTURE',gamma=.01)
checks=[]
def check(name,ok):
 assert ok,name
 checks.append(name)
def feasible(members,seeds,cap):
 return [i for i in seeds if all(np.isfinite(time[ids.index(x),i]) and time[ids.index(x),i]<=cap+1e-4 for x in members)]
prev=None
for cap in [30,60,120]:
 s=f.one_cap(cap);units=s['forest_units']; covered=set().union(*(u.members for u in units));check(f'{cap}_partition_conservation',covered|f.residuals==set(ids) and sum(len(u.members) for u in units)==len(covered));check(f'{cap}_unknown_route_stays_residual','z' in f.residuals)
 for u in units:
  possible=feasible(u.members,u.nuclei,cap);check(f'{cap}_{u.key}_complete_direct_envelope',bool(possible));expected=min(possible,key=lambda i:(-mass[i],-pop[i],pids[i]));check(f'{cap}_{u.key}_fixed_own_mass_focal',f.selected_core(u.nuclei,f.mask(u,cap))==expected)
 if prev is not None:check(f'{cap}_whole_previous_children',all(any(u.members<=v.members for v in units) for u in prev))
 prev=units
 # Reference q/graph/degree/Q computed from the ORIGINAL numeric source table.
 g=np.where(np.isfinite(time[:4]),mass[None,:]*np.exp(-np.nan_to_num(time[:4],nan=0)/60),0);np.fill_diagonal(g,0);q=g/g.sum(axis=1,keepdims=True);support=np.isfinite(time[:4])&(time[:4]<=cap+1e-4);w=np.sqrt(q*q.T)*support*support.T;np.fill_diagonal(w,0);deg=w.sum(axis=1);S=deg.sum()
 parents={e['parent'] for e in s['events']};groups={k:v for k,v in s['registry'].items() if k not in parents}
 def Q(us):
  return sum(w[np.ix_(list(u.nuclei),list(u.nuclei))].sum()/S-.01*(sum(deg[i] for i in u.nuclei)/S)**2 for u in us) if S else 0
 for e in s['events']:
  ua,ub=groups[e['left']],groups[e['right']];cross=w[np.ix_(list(ua.nuclei),list(ub.nuclei))].sum();check(f'{cap}_{e["merge_index"]}_all_original_crossweights',abs(cross-e['cross_affinity'])<1e-7);before=Q(groups.values());expected_gain=2*cross/S-2*.01*sum(deg[i] for i in ua.nuclei)*sum(deg[i] for i in ub.nuclei)/S**2;gains=[]
  for aa,bb in itertools.combinations(groups.values(),2):
   ww=w[np.ix_(list(aa.nuclei),list(bb.nuclei))].sum();delta=2*ww/S-2*.01*sum(deg[i] for i in aa.nuclei)*sum(deg[i] for i in bb.nuclei)/S**2
   if delta>0 and feasible(aa.members|bb.members,aa.nuclei|bb.nuclei,cap):gains.append(delta)
  check(f'{cap}_{e["merge_index"]}_greatest_admissible_gain',bool(gains) and abs(expected_gain-max(gains))<1e-7);groups.pop(e['left']);groups.pop(e['right']);groups[e['parent']]=s['registry'][e['parent']];after=Q(groups.values());check(f'{cap}_{e["merge_index"]}_independent_complete_Q',abs(after-e['q'])<1e-7 and abs(after-before-e['delta_q'])<1e-7)
 for aa,bb in itertools.combinations(groups.values(),2):
  ww=w[np.ix_(list(aa.nuclei),list(bb.nuclei))].sum();delta=2*ww/S-2*.01*sum(deg[i] for i in aa.nuclei)*sum(deg[i] for i in bb.nuclei)/S**2
  check(f'{cap}_final_no_skipped_positive_admissible_merge',delta<=1e-12 or not feasible(aa.members|bb.members,aa.nuclei|bb.nuclei,cap))
check('own_mass_not_recalibrated',np.array_equal(field.mass,mass));check('linear_path_no_knee',objective_knee(np.arange(101,dtype=float))['status']=='no_knee');check('forty_valid_cut_declared_not_fifty',accept_stable_cut([.95]*40+[np.nan]*10,[.3]*40+[np.nan]*10)['accepted']);check('thirtynine_valid_rejected',not accept_stable_cut([.95]*39+[np.nan]*11,[.3]*39+[np.nan]*11)['accepted'])
print(json.dumps({'status':'PASS','n_checks':len(checks),'checks':checks},indent=2))

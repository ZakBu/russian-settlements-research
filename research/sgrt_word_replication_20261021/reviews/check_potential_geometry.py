#!/usr/bin/env python3
"""Independent dense haversine comparison to the spatial-index gravity implementation."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
RUN=HERE.parent

def main():
 out=RUN/'results';p=out/'memberships.parquet';d=pd.concat([pd.read_parquet(p),pd.read_csv(out/'federal_context_assignments.csv')],ignore_index=True)
 candidate=np.flatnonzero(d.candidate_center.to_numpy(bool));lat=np.radians(d.lat.to_numpy(float));lon=np.radians(d.lon.to_numpy(float));mass=d.own_functional_mass.to_numpy(float);uid=d.id.to_numpy()
 # Every self-core, all unassigned, plus regularly spaced noncores and 256 most populous.
 selected=np.unique(np.r_[candidate,np.flatnonzero(d.center_index_l1.eq(-1)),np.arange(0,142570,127),np.argsort(-d.population_2021.to_numpy(float))[:256]])
 mismatch=[];max_distance_error=0.;weight_errors=[]
 for start in range(0,len(selected),128):
  ii=selected[start:start+128]
  a=np.sin((lat[ii,None]-lat[candidate][None,:])/2)**2+np.cos(lat[ii,None])*np.cos(lat[candidate][None,:])*np.sin((lon[ii,None]-lon[candidate][None,:])/2)**2
  dist=2*6371.0088*np.arcsin(np.sqrt(np.clip(a,0,1)))
  w=mass[candidate][None,:]*np.exp(-dist/15);w[dist>75]=0
  best=np.argmax(w,axis=1);total=w.sum(axis=1);found=total>0
  expected=np.where(found,candidate[best],-1)
  actual=d.loc[ii,'unconstrained_winner_id'].to_numpy()
  expectedids=np.array([uid[x] if x>=0 else None for x in expected],dtype=object)
  for k,u in enumerate(ii):
   a_id=actual[k] if pd.notna(actual[k]) else None
   if a_id!=expectedids[k]:mismatch.append({'index':int(u),'id':str(uid[u]),'expected':str(expectedids[k]),'actual':str(a_id)})
  normalized=np.divide(w[np.arange(len(ii)),best],total,out=np.zeros(len(ii)),where=found)
  weight_errors.extend(np.abs(normalized-d.loc[ii,'unconstrained_top_weight'].to_numpy(float)))
  # Distances published for forced cores are0; compare only assigned noncores.
  noncore=found&~d.loc[ii,'pinned'].to_numpy(bool)
  if noncore.any():max_distance_error=max(max_distance_error,float(np.abs(dist[np.arange(len(ii))[noncore],best[noncore]]-d.loc[ii[noncore],'distance'].to_numpy(float)).max()))
 h=pd.read_csv(out/'hierarchy.csv');hierarchy_mismatch=[]
 for lev,edge in h.groupby('level'):
  active=edge.child_index.to_numpy(int);threshold=float(edge.mass_threshold.iloc[0]);radius=float(edge.search_radius_km.iloc[0]);eligible=active[mass[active]>=threshold]
  for u,parent in zip(active,edge.parent_index):
   if mass[u]>=threshold:expected=u
   else:
    a=np.sin((lat[u]-lat[eligible])/2)**2+np.cos(lat[u])*np.cos(lat[eligible])*np.sin((lon[u]-lon[eligible])/2)**2
    dist=2*6371.0088*np.arcsin(np.sqrt(np.clip(a,0,1)))
    w=mass[eligible]*np.exp(-dist/(radius/3));w[(dist>radius)|(mass[eligible]<=mass[u])]=0
    expected=int(eligible[np.argmax(w)]) if len(w) and w.max()>0 else int(u)
   if expected!=parent:hierarchy_mismatch.append({'level':int(lev),'child_index':int(u),'expected':int(expected),'actual':int(parent)})
 checks={'all_selected_raw_winners_match':not mismatch,'raw_top_weight_matches':max(weight_errors)<1e-9,'noncore_distance_matches':max_distance_error<1e-7,'all_hierarchy_best_parents_match':not hierarchy_mismatch}
 checks={k:bool(v) for k,v in checks.items()}
 result={'independent_algorithm':'dense haversine, no author functions or spatial tree','selected_low_level_rows':len(selected),'all_core_rows_included':len(candidate),'all_unassigned_rows_included':int(d.center_index_l1.eq(-1).sum()),'hierarchy_edges_checked':len(h),'checks':checks,'all_pass':all(checks.values()),'low_level_mismatches':mismatch[:30],'hierarchy_mismatches':hierarchy_mismatch[:30],'max_normalized_weight_abs_error':float(max(weight_errors)),'max_noncore_distance_km_abs_error':max_distance_error,'source_memberships_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 (HERE/'independent_potential_geometry_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

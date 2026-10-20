#!/usr/bin/env python3
"""Fresh catalog sensitivity, function disagreement, postdevelopment documents and register history."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from run_model import ROOT,OLD,MASTER,GROUPS,LEGAL,counts,mass,assign,xyz,typology

def run():
 out=ROOT/'results';d=pd.read_parquet(MASTER);d['axis_kind']='ordinary'
 member=pd.read_parquet(out/'memberships.parquet');pts=xyz(d.lat.values,d.lon.values)
 frozen=counts(d);m,_=mass(frozen);anchors=(d.places_baseline_school_count>0)|(d.places_baseline_hospital_count>0)
 # Exact ordinary-axis modern catalog sensitivity; federal sources kept out of this auxiliary experiment.
 commerce=pd.read_parquet(ROOT/'commerce/settlement_features.parquet');assert commerce.id.equals(d.id)
 fresh=counts(d)
 # Replace only WB term, retaining same max-over-source rule and recorded own legal evidence.
 fresh['trade_access']=np.maximum.reduce([d.econ_native_2025_retail47_legal_entities.to_numpy(),(d.places_baseline_retail_store_count+d.places_baseline_market_count).to_numpy(),commerce.commerce_wb20261021_baseline_focus_count.to_numpy()])
 fm,_=mass(fresh);cand=(fresh.gt(0).sum(axis=1)>=2)|anchors
 ordinary_frozen=assign(pts,np.flatnonzero((frozen.gt(0).sum(axis=1)>=2)|anchors),m)
 r=assign(pts,np.flatnonzero(cand),fm)
 changed=d.id.to_numpy()[np.maximum(r['center'],0)]!=d.id.to_numpy()[np.maximum(ordinary_frozen['center'],0)]
 changed|=(r['center']<0)!=(ordinary_frozen['center']<0)
 fresh_rows=pd.DataFrame({'id':d.id,'frozen_ordinary_center_id':[d.id.iloc[x] if x>=0 else None for x in ordinary_frozen['center']],'fresh_wb_ordinary_center_id':[d.id.iloc[x] if x>=0 else None for x in r['center']],'changed':changed})
 fresh_rows.to_parquet(out/'fresh_wb_membership_sensitivity.parquet',index=False)
 # Dated legal witness histories: complete years, distinct from changes of physical functions.
 candidates=member.candidate_center.to_numpy();ix=np.flatnonzero(candidates);timeline=[]
 for y in range(2011,2026):
  arr=np.column_stack([d[f'econ_native_{y}_{c}_legal_entities'].to_numpy() for c in LEGAL.values()])
  for i in ix:timeline.append(dict(id=d.id.iloc[i],year=y,registered_function_diversity=int((arr[i]>0).sum()),registered_consumer_entities=int(arr[i].sum()),physical_service_opening_or_closure_asserted=False))
 pd.DataFrame(timeline).to_parquet(out/'candidate_legal_function_history_2011_2025.parquet',index=False)
 # Date-specific legal mass sensitivity. No modern physical anchors in this experiment.
 historical=[];previous=None;changed_counts=[]
 for y in [2011,2016,2021,2025]:
  arr=pd.DataFrame({g:d[f'econ_native_{y}_{LEGAL[g]}_legal_entities'] if g in LEGAL else np.zeros(len(d)) for g in GROUPS})
  mm,_=mass(arr);cc=np.flatnonzero(arr.gt(0).sum(axis=1)>=2)
  rr=assign(pts,cc,mm)
  for i in range(len(d)):historical.append(dict(id=d.id.iloc[i],year=y,potential_registered_center_id=d.id.iloc[rr['center'][i]] if rr['center'][i]>=0 else None,distance_km=rr['distance'][i],not_actual_historical_service_catchment=True))
  changed_counts.append(dict(year=y,candidates=len(cc),assigned=int((rr['center']>=0).sum()),changed_since_previous_scenario=None if previous is None else int((rr['center']!=previous).sum())))
  previous=rr['center']
 pd.DataFrame(historical).to_parquet(out/'registered_mass_year_scenarios.parquet',index=False);pd.DataFrame(changed_counts).to_csv(out/'registered_mass_year_scenario_summary.csv',index=False)
 # Compare documented pair/dates after model specification; no model is selected on this score.
 edges=pd.read_csv(ROOT/'education/validation_external_edges.csv');index=member.set_index('id')
 edges=edges[edges.origin_uid.isin(index.index)&edges.destination_uid.isin(index.index)].copy()
 edges['predicted_multifunction_center']=edges.origin_uid.map(index.center_id_l1)
 edges['predicted_education_provider']=edges.origin_uid.map(index.education_potential_provider_id)
 edges['multifunction_exact_match']=edges.predicted_multifunction_center.eq(edges.destination_uid)
 edges['education_provider_exact_match']=edges.predicted_education_provider.eq(edges.destination_uid)
 edges['documented_provider_is_model_candidate']=edges.destination_uid.map(index.candidate_center)
 edges['documented_provider_has_mass_education_witness']=edges.destination_uid.map(index.education_potential_provider_id).eq(edges.destination_uid)
 edges.to_csv(out/'documented_education_model_comparison.csv',index=False)
 doc_summary={'canonical_dated_assertions':len(edges),'unique_origin_destination_pairs':len(edges[['origin_uid','destination_uid']].drop_duplicates()),'origins':edges.origin_uid.nunique(),'providers':edges.destination_uid.nunique(),'multifunction_exact_match':int(edges.multifunction_exact_match.sum()),'education_provider_exact_match':int(edges.education_provider_exact_match.sum()),'documented_provider_in_model_candidates':int(edges.documented_provider_is_model_candidate.sum()),'scope':'post-development_document_check_not_blind_holdout; repeated years are not independent trials; not commuter validation'}
 fields=['education_potential_provider_id','healthcare_potential_provider_id','trade_access_potential_provider_id'];dis=[]
 for a,b in [(fields[0],fields[1]),(fields[0],fields[2]),(fields[1],fields[2])]:
  valid=member[a].notna()&member[b].notna();dis.append(dict(function_a=a,function_b=b,both_assigned=int(valid.sum()),different_providers=int((member.loc[valid,a]!=member.loc[valid,b]).sum())))
 pd.DataFrame(dis).to_csv(out/'function_provider_disagreement.csv',index=False)
 summary={'fresh_wb_model_sensitivity':{'changed_ordinary_assignments':int(changed.sum()),'federal_context_included':False,'comparison':'ordinary-only frozen19October vs fresh21October WB; other sources fixed'},'documented_education':doc_summary,'registered_history_scope':'frozen2021dictionary applied to dated legal source witnesses, not historical physical service coverage','registered_year_scenarios':changed_counts,'function_disagreement':dis}
 (out/'extended_check_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':run()

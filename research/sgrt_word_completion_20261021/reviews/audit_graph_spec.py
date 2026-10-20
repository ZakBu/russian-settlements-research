#!/usr/bin/env python3
"""Inspect actual graph structure and frozen modeling contract, not pending route pairs."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=H.parents[2]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
paths=['transport/routing_graph.npz','transport/graph_receipt.json','transport/yearround_profile_receipt.json','transport/access_repair_receipt.json','model/model_inputs_2021_restricted.json','model/model_inputs_2021_restricted_inclusive.json','model/run_word_model.py']
before={p:sha(ROOT/p) for p in paths};g=load_npz(ROOT/'transport/routing_graph.npz');r=json.loads((ROOT/'transport/graph_receipt.json').read_text());cfg=json.loads((ROOT/'model/model_inputs_2021_restricted.json').read_text());checks=[]
def check(name,condition):checks.append({'check':name,'pass':bool(condition)})
check('graph_shape_matches_reported_node_count',g.shape==(r['nodes'],r['nodes']));check('arcs_match_receipt',g.nnz==r['directed_arcs']);check('all_arc_minutes_finite_nonnegative',np.isfinite(g.data).all() and (g.data>=0).all());check('CSR_indices_in_range',g.indices.min()>=0 and g.indices.max()<g.shape[1]);check('CSR_indptr_monotone',np.diff(g.indptr).min()>=0 and g.indptr[-1]==g.nnz)
zeros=np.flatnonzero(g.data==0);zr=np.searchsorted(g.indptr,zeros,side='right')-1;zc=g.indices[zeros]
if len(zeros):
 needed=np.unique(np.r_[zr,zc]);coords=pd.read_parquet(ROOT/'transport/road_nodes.parquet',columns=['node_index','lat','lon'],filters=[('node_index','in',needed.tolist())]).set_index('node_index')
 check('zero_time_arcs_only_coincident_coordinate_vertices',np.allclose(coords.loc[zr,['lat','lon']],coords.loc[zc,['lat','lon']],rtol=0,atol=1e-12))
# Asymmetry witness establishes directed structure; not independent route validation.
positions=np.linspace(0,g.nnz-1,5000,dtype=np.int64);rows=np.searchsorted(g.indptr,positions,side='right')-1;cols=g.indices[positions];forward=g.data[positions];reverse=np.asarray(g[cols,rows]).ravel();asym=(reverse==0)|(~np.isclose(reverse,forward));check('sample_has_directed_asymmetry_witness',asym.any())
profile=ROOT/'transport/yearround_profile_receipt.json';check('graph_binds_actual_yearround_profile',r['yearround_profile_receipt_sha256']==sha(profile));check('primary_eligibility_restricted',cfg['center_eligibility']=='restricted_multifunctional_or_independent_seat');check('primary_assignment_lowest_order',cfg['initial_assignment_center_scope']=='lowest_empirical_order_only');check('primary_conditional_Huff_probability',cfg['model']['outside_mass']==0 and cfg['model']['minimum_choice_probability']==.35);check('2021mass_vs2010_2021_retrospective_dates',cfg['mass_reference_year']==2021 and cfg['dynamic_initial_year']==2010 and cfg['dynamic_final_year']==2021)
after={p:sha(ROOT/p) for p in paths};check('input_bytes_stable',before==after)
receipt={'status':'VERIFIED_GRAPH_STRUCTURE_AND_MODEL_SPEC' if all(x['pass'] for x in checks) else 'RETURN_TO_REPAIR_LOOP','n_checks':len(checks),'n_failed':sum(not x['pass'] for x in checks),'checks':checks,'nodes':g.shape[0],'arcs':g.nnz,'zero_time_arcs':len(zeros),'directed_asymmetry_witnesses_in5000sample':int(asym.sum()),'arc_time_minutes_min':float(g.data.min()),'arc_time_minutes_max':float(g.data.max()),'reviewed_sha256':before,'review_scope':'Actual graph structure and current specification only; no pending routing matrix read. Arc weights are speed-profile model minutes, not measured traffic. Turn restrictions and ferry routing not implemented.','scientific_final_allowed':False}
(H/'graph_spec_independent_audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['checks','reviewed_sha256']},ensure_ascii=False,indent=2))

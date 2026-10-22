"""Describe genuine unit changes versus persistence; NEVER assign functional order."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;REG=ROOT/'empirical_registry_source477_v1';MAIN=ROOT/'source477_adminall_v2/output_primary_v1'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
watch={str(p):sha(p)for p in [Path(__file__),REG/'registry_receipt.json',REG/'all_empirical_raw_units.parquet',REG/'all_empirical_raw_memberships.parquet',REG/'geographic_parent_links.parquet',MAIN/'pre_execution_binding.json',MAIN/'run_receipt.json',ROOT/'source477_adminall_v2/source_provider_pool/active_provider_pool.parquet']}
u=pd.read_parquet(REG/'all_empirical_raw_units.parquet');m=pd.read_parquet(REG/'all_empirical_raw_memberships.parquet');links=pd.read_parquet(REG/'geographic_parent_links.parquet');levels=sorted(u.empirical_level.unique());assert levels==list(range(len(levels)))
records=[]
for level in levels[1:]:
 lower=u[u.empirical_level.eq(level-1)].set_index('unit_id');upper=u[u.empirical_level.eq(level)].set_index('unit_id');edge=links[links.upper_empirical_level.eq(level)].copy();edge=edge.join(lower[['unit_role','n_provider_seeds','core_id','core_fixed_own_mass','unit_membership_sha256']],on='unit_id_lower')
 for uid,g in edge.groupby('unit_id_upper',sort=True):
  target=upper.loc[uid];n=len(g);territorial=int(g.unit_role.eq('territorial_unit').sum());provider=int(g.n_provider_seeds.gt(0).sum());atomic=int(g.n_provider_seeds.eq(0).sum());same=n==1 and g.unit_membership_sha256.iloc[0]==target.unit_membership_sha256
  if same:kind='persistent_identical_membership'
  elif territorial>=2:kind='union_of_at_least_two_lower_territorial_fields'
  elif provider>=2:kind='provider_bearing_children_join_without_two_prior_fields'
  elif provider==1 and atomic>=1:kind='direct_rural_or_residual_attachment_only'
  else:kind='other_nonprovider_or_carry_change'
  if n==1:assert same
  assert int(g.n_shared_atoms.sum())==int(target.n_members)
  mass=pd.to_numeric(g.core_fixed_own_mass,errors='coerce');parent=target.core_fixed_own_mass
  if mass.notna().any():assert np.isfinite(parent) and parent>=mass.max()-1e-12
  if same:assert target.core_id==g.core_id.iloc[0]
  records.append({'lower_resolution':int(level-1),'upper_resolution':int(level),'unit_id':uid,'membership_sha256':target.unit_membership_sha256,'change_kind':kind,'persistent_membership':same,'n_lower_children':n,'n_lower_territorial_fields':territorial,'n_lower_provider_bearing_children':provider,'n_lower_atomic_nonprovider_children':atomic,'n_lower_protected_carry':int(g.unit_role.ne('territorial_unit').sum()),'n_members':int(target.n_members),'core_id':target.core_id,'focal_matches_at_least_one_lower_focal':bool(g.core_id.eq(target.core_id).any()),'n_lower_territorial_focals_changed':int((g.unit_role.eq('territorial_unit')&g.core_id.ne(target.core_id)).sum()),'core_population2021':target.core_population_2021,'core_fixed_own_mass':parent,'max_member_direct_minutes':target.max_member_direct_minutes,'functional_order_assigned':False})
changes=pd.DataFrame(records);changes.to_parquet(HERE/'per_unit_resolution_transitions.parquet',index=False)
summary=[]
for (lo,hi,kind),g in changes.groupby(['lower_resolution','upper_resolution','change_kind']):
 p=pd.to_numeric(g.core_population2021,errors='coerce');mass=pd.to_numeric(g.core_fixed_own_mass,errors='coerce');summary.append({'lower_resolution':int(lo),'upper_resolution':int(hi),'change_kind':kind,'n_units':len(g),'n_members_sum':int(g.n_members.sum()),'n_focalP_known':int(p.notna().sum()),'n_focalP_unknown':int(p.isna().sum()),'focalP_median':p.median(),'focalP_p10':p.quantile(.1),'focalP_p90':p.quantile(.9),'fixedMi_median':mass.median(),'fixedMi_min':mass.min(),'fixedMi_max':mass.max(),'max_direct_minutes':g.max_member_direct_minutes.max(),'n_child_territorial_focals_replaced':int(g.n_lower_territorial_focals_changed.sum()),'population_bins_used':False})
pd.DataFrame(summary).to_csv(HERE/'transition_change_kind_summary.csv',index=False)
# SAME exact member set surviving multiple exported resolutions is ONE node.
nodes=[]
for key,g in u.groupby('unit_membership_sha256',sort=True):
 seen=sorted(g.empirical_level.tolist());assert seen==list(range(min(seen),max(seen)+1));assert g.semantic_unit_id.nunique()==1 and g.core_id.nunique()==1 and g.n_members.nunique()==1
 r=g.iloc[0];nodes.append({'membership_node_id':key,'semantic_source_unit_id':r.semantic_unit_id,'core_id':r.core_id,'unit_role':r.unit_role,'n_members':int(r.n_members),'n_provider_seeds':int(r.n_provider_seeds),'first_observed_resolution':min(seen),'last_observed_resolution':max(seen),'n_exported_views_seen':len(seen),'first_view_birth_left_censored':min(seen)==min(levels),'otherwise_birth_interval_censored':min(seen)>min(levels),'last_view_stop_right_censored':max(seen)==max(levels),'observed_resolution_indices_json':json.dumps(seen),'functional_order_status':'UNASSIGNED','calendar_birth_or_death_claim':False})
dedup=pd.DataFrame(nodes);dedup.to_parquet(HERE/'deduplicated_exported_membership_nodes.parquet',index=False)
# Actual accepted computational forest: provider unions + one-way leaf attachment.
providers=set(pd.read_parquet(ROOT/'source477_adminall_v2/source_provider_pool/active_provider_pool.parquet',columns=['id']).id)
base_ids=sorted(m.loc[m.empirical_level.eq(levels[0]),'id']);nodeinfo={('seed:'if uid in providers else'atom:')+uid:{'node_id':('seed:'if uid in providers else'atom:')+uid,'node_kind':'source_provider_seed_NOT_proven_co_center'if uid in providers else'atomic_source_record','n_members':1,'computational_creation_cap':None,'core_id':uid if uid in providers else None,'functional_order_status':'UNASSIGNED'}for uid in base_ids};edges=[];parentof={}
attachpath=MAIN/'directed_local_attachment_events.parquet';watch[str(attachpath)]=sha(attachpath);attach=pd.read_parquet(attachpath)
caps=json.loads((MAIN/'pre_execution_binding.json').read_text())['protocol']['extent']['candidate_caps_minutes']
def add(parent,children,kind,cap,core,delta=None):
 assert parent not in nodeinfo and len(set(children))==2
 assert all(child in nodeinfo for child in children)
 size=sum(nodeinfo[c]['n_members']for c in children);nodeinfo[parent]={'node_id':parent,'node_kind':kind,'n_members':size,'computational_creation_cap':cap,'core_id':core,'functional_order_status':'UNASSIGNED'}
 for child in children:
  assert child not in parentof;parentof[child]=parent;edges.append({'parent_node_id':parent,'child_node_id':child,'event_kind':kind,'source_event_cap':cap,'parent_member_count':size,'positive_modularity_delta_q':delta,'not_functional_order':True})
for cap in caps:
 for row in attach.loc[attach.cap_minutes.eq(cap)].itertuples():add(row.new_unit,[row.previous_parent_unit,'atom:'+row.origin_id],'directed_residual_leaf_attachment',cap,row.focal_core_id)
 p=MAIN/f'cap_{cap:03}_accepted_merge_events.parquet';watch[str(p)]=sha(p)
 for row in pd.read_parquet(p).sort_values('merge_index').itertuples():
  assert row.delta_q>0;add(row.parent,[row.left,row.right],'accepted_provider_unit_union',cap,row.core_id,row.delta_q)
computational_nodes=pd.DataFrame(nodeinfo.values());computational_edges=pd.DataFrame(edges);computational_nodes['has_computational_parent']=computational_nodes.node_id.isin(parentof);computational_nodes['right_censored_at_last_exported_cap']=~computational_nodes.has_computational_parent
computational_nodes.to_parquet(HERE/'actual_computational_forest_nodes.parquet',index=False);computational_edges.to_parquet(HERE/'actual_computational_forest_edges.parquet',index=False)
end=pd.read_parquet(MAIN/f'cap_{caps[-1]:03}_raw_units.parquet');end=end[end.partition_role.eq('supported_end_forest')];assert set(computational_nodes.loc[~computational_nodes.has_computational_parent,'node_id'])==set(end.semantic_unit_id)
assert sum(nodeinfo[x]['n_members']for x in computational_nodes.loc[~computational_nodes.has_computational_parent,'node_id'])==len(base_ids)
assert set(u.semantic_unit_id)<=set(nodeinfo)
assert all(sha(Path(p))==h for p,h in watch.items())
receipt={'status':'ACTUAL_UNIT_PERSISTENCE_AND_NEW_UNION_DIAGNOSTIC_NO_FUNCTIONAL_ORDER_ASSIGNED','resolution_views':len(levels),'exported_unit_rows':len(u),'deduplicated_observed_member_set_nodes':len(dedup),'n_nodes_persisting_multiple_views':int(dedup.n_exported_views_seen.gt(1).sum()),'n_computational_nodes':len(computational_nodes),'n_computational_edges':len(computational_edges),'n_computational_roots':int((~computational_nodes.has_computational_parent).sum()),'all_four_views_are_stable_nested_resolutions_NOT_intrinsic_functional_orders':True,'provider_seeds_NOT_proven_co_centers':True,'first_last_observation_only_not_calendar_birth_death':True,'observational_horizon_minutes':180,'outside_horizon_unknown_not_proof_no_more_links':True,'source_pins':watch,'outputs_sha256':{p.name:sha(p)for p in HERE.iterdir()if p.is_file()and p.name!='receipt.json'}};(HERE/'receipt.json').write_text(json.dumps(receipt,indent=2));print({k:v for k,v in receipt.items()if k not in ['source_pins','outputs_sha256']});print(pd.DataFrame(summary).to_string(index=False))

from pathlib import Path
import pandas as pd,json,hashlib
O=Path(__file__).parent;B=O.parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();d=pd.read_parquet('/dev/shm/over500-moscow-complete-batch3.parquet');sid='2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:8169';d.loc[d.source_record_id.eq(sid),'after_root']=sid;parent={x:x for x in d.after_root.unique()};years={x:set(z.census_year)for x,z in d.groupby('after_root')};rd=d.set_index('source_record_id').after_root.to_dict()
def find(x):
 while parent[x]!=x:x=parent[x]
 return x
for r in pd.read_csv(O/'accepted_identity_edge_delta.csv').itertuples():
 a,b=find(rd[r.from_source_record_id]),find(rd[r.to_source_record_id]);assert not years[a]&years[b],r.case;parent[a]=b;years[b]|=years[a]
d.after_root=d.after_root.map(find);d.to_parquet('/dev/shm/over500-moscow-complete-batch4.parquet',index=False);own=set(pd.read_parquet('/dev/shm/over500-moscow-points.parquet').target_source_record_id);events=set()
for dr in[B,B/'batch2_lifecycle_homonyms',B/'batch3_remaining',O,O/'timokhovsky']:
 own|=set(pd.read_csv(dr/'accepted_point_use_delta.csv').target_source_record_id)
 if(dr/'accepted_direct_event_native_credit_union.csv').exists():events|=set(pd.read_csv(dr/'accepted_direct_event_native_credit_union.csv').source_record_id)
a=pd.read_csv(B/'batch3_remaining/all111_dispositions_after_batch3.csv');g={x:z for x,z in d.groupby('after_root')};a.after_root=a.source_record_id.map(d.set_index('source_record_id').after_root);a.after_years=a.after_root.map(lambda x:','.join(map(str,sorted(set(g[x].census_year)))));a.after_ownpoint=a.source_record_id.isin(own);a.component_all_ownpoints=a.after_root.map(lambda x:set(g[x].source_record_id)<=own);a.component_member_UIDs=a.after_root.map(lambda x:'|'.join(g[x].source_record_id))
for i,r in a.iterrows():
 if r.after_years=='2002,2010,2021'and r.component_all_ownpoints:a.loc[i,'disposition']='accepted_ordinary_full3_route'
 elif r.source_record_id in events and r.after_ownpoint:a.loc[i,'disposition']='accepted_dated_inclusion_or_merger_available_native_route'
 elif ','in r.after_years and r.component_all_ownpoints:a.loc[i,'disposition']='accepted_available_two_year_series_missing_year_UNKNOWN'
a.to_csv(O/'all111_dispositions_after_batch4.csv',index=False);a[a.disposition.str.startswith('held')].to_csv(O/'remaining_assigned_holds.csv',index=False);a[~a.after_ownpoint].to_csv(O/'remaining_point_only_missing.csv',index=False)
statuses=[];obs=[]
for root in set(a[a.disposition.eq('accepted_available_two_year_series_missing_year_UNKNOWN')].after_root):
 z=g[root];scope='over500_moscow_available_'+root
 for y in[2002,2010,2021]:
  rr=z[z.census_year.eq(y)];statuses.append(dict(scope_id=scope,year=y,status='actual_own_published_observation_on_source_bound_same_place_component'if len(rr)else'UNKNOWN_missing_native_year_no_birth_or_disappearance_inferred',own_population=int(rr.population.iloc[0])if len(rr)else'',unknown_is_zero=False,recipient_population_assigned_to_child=False,boundary_comparability='UNKNOWN',component_member_UIDs='|'.join(z.source_record_id)))
 for r in z.itertuples():obs.append(dict(scope_id=scope,source_record_id=r.source_record_id,year=r.census_year,native_population=r.population,native_population_quality=r.population_value_quality,own_point=True,ordinary_three_census_same_place_claim=False,is_additive_to_original_final_mixed_census_axis=False,missing_year_population_fabricated=False))
pd.DataFrame(statuses).to_csv(O/'accepted_ordinary_available_year_statuses.csv',index=False);pd.DataFrame(obs).to_csv(O/'accepted_available_year_observations.csv',index=False);receipt=dict(status='batch4_frozen_reviewed_delta_ready_for_root_replay',identity_edges=len(pd.read_csv(O/'accepted_identity_edge_delta.csv')),point_rows=len(pd.read_csv(O/'accepted_point_use_delta.csv'))+len(pd.read_csv(O/'timokhovsky/accepted_point_use_delta.csv')),point_rejections=1,false_identity_pair_rejections=1,baseline71_exact_component_partition_corrections=1,own_current_code_points_admitted=2,existing_large_Zakharovo_point_independently_confirmed=1,new_dated_events=2,assigned111_dispositions=a.disposition.value_counts().to_dict(),point_only_missing=int((~a.after_ownpoint).sum()),sameyear_collision_gate_passed=True,native_values_quality_changed=0,unknown_as_zero=0,national_gain_not_claimed=True)
(O/'BATCH4_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));files=[p for p in O.rglob('*')if p.is_file()and not p.name.startswith('BATCH4_manifest')];(O/'BATCH4_manifest.json').write_text(json.dumps([dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)for p in sorted(files)],ensure_ascii=False,indent=2));(O/'BATCH4_manifest.sha256').write_text(sha(O/'BATCH4_manifest.json')+'\n');print(json.dumps(receipt,ensure_ascii=False));print(a[a.disposition.str.startswith('held')][['settlement_name','after_ownpoint']].to_string(index=False))

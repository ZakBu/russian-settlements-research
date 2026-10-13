from pathlib import Path
import pandas as pd,json,hashlib
O=Path(__file__).parent;d=pd.read_parquet('/dev/shm/over500-moscow-observations.parquet');p=pd.read_parquet('/dev/shm/over500-moscow-points.parquet').set_index('target_source_record_id');a=pd.read_csv(O/'assigned111.csv');edges=[];pts=[];rivals=[];holds=[];seen=set();parent={x:x for x in d.root.unique()};groups={x:g for x,g in d.groupby('root')};yrs={x:set(g.census_year)for x,g in groups.items()}
def find(x):
 while parent[x]!=x:x=parent[x]
 return x
for r in a.itertuples():
 x=d[d.source_record_id.eq(r.source_record_id)].iloc[0]
 if pd.isna(x.derived_oldcounty):continue
 cand=d[d.name_norm.eq(x.name_norm)&d.type_norm.eq(x.type_norm)&d.derived_oldcounty.eq(x.derived_oldcounty)]
 rivals.extend(cand.assign(target_UID=x.source_record_id).to_dict('records'))
 if cand.census_year.duplicated().any() or len(cand)<2:continue
 roots={find(z)for z in cand.root};key=tuple(sorted(roots))
 if key in seen or len(roots)<2:continue
 seen.add(key);full=d[d.root.map(find).isin(roots)]
 if full.census_year.duplicated().any():holds.append(dict(target_UID=x.source_record_id,reason='competing same-year accepted component member',members='|'.join(full.source_record_id)));continue
 donors=full[full.source_record_id.isin(p.index)]
 if donors.empty:continue
 donor=donors.sort_values('census_year').iloc[-1]; cp=p.loc[donor.source_record_id];case='moscow_exact_county_'+donor.source_record_id.rsplit(':',1)[-1]
 for z in cand.itertuples():
  if find(z.root)!=find(donor.root):
   edges.append(dict(from_source_record_id=z.source_record_id,to_source_record_id=donor.source_record_id,relation='same_place',decision_status='checked_rule_accepted',case=case,admission_rule='Literal native name and type unique per actual census year within independently source-bound original county; no same-year component competition; existing accepted own-locality point',source_binding_proof=str(O/'all_native_identity_rivals.csv.gz')+';/workspace/russian-settlements-research/research_rebuild/evidence/over1000_moscow_20261009/native_all_with_independent_county.csv.gz',population_boundary_comparability_asserted=False,municipal_event_date='UNKNOWN'))
   az,bz=find(z.root),find(donor.root);parent[az]=bz;yrs[bz]|=yrs[az]
 for z in full.itertuples():
  if z.source_record_id not in p.index:
   pts.append(dict(target_source_record_id=z.source_record_id,latitude=cp.latitude,longitude=cp.longitude,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=donor.source_record_id,source_sha256=cp.point_origin_sha256,source_locator=cp.point_origin_locator,point_origin_file=cp.point_origin_file,point_origin_sha256=cp.point_origin_sha256,point_origin_locator=cp.point_origin_locator,point_origin_kind=cp.point_origin_kind,case=case,coordinate_binding_rule='Unique literal native name/type and independently source-bound county; inherit own accepted physical locality point across reviewed same-place native identity',point_use_inference='own_modern_representative_point_on_source_bound_native_identity',population_boundary_comparability_asserted=False,historical_census_coordinate_asserted=False,secondary_population_not_substituted_for_native=True))
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(pts).drop_duplicates('target_source_record_id').to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(rivals).to_csv(O/'all_native_identity_rivals.csv.gz',index=False);pd.DataFrame(holds).to_csv(O/'component_collision_holds.csv',index=False)
d['after_root']=d.root.map(find);d.to_parquet('/dev/shm/over500-moscow-after.parquet',index=False);own=set(p.index)|{r['target_source_record_id']for r in pts};g={x:z for x,z in d.groupby('after_root')}; a['after_root']=a.source_record_id.map(d.set_index('source_record_id').after_root);a['after_years']=a.after_root.map(lambda x:','.join(map(str,sorted(set(g[x].census_year)))));a['after_ownpoint']=a.source_record_id.isin(own);a['component_all_ownpoints']=a.after_root.map(lambda x:set(g[x].source_record_id)<=own);a['disposition']=a.apply(lambda x:'accepted_ordinary_full3_route'if x.after_years=='2002,2010,2021'and x.component_all_ownpoints else'accepted_two_year_continuity_needs_available_year_or_lifecycle_route'if ','in x.after_years else'needs_source_bound_temporal_or_lifecycle_route',axis=1);a['component_member_UIDs']=a.after_root.map(lambda x:'|'.join(g[x].source_record_id));a.to_csv(O/'all111_dispositions.csv',index=False)
print('edges',len(edges),'points',len(pts));print(a.disposition.value_counts());print(a[a.disposition!='accepted_ordinary_full3_route'][['census_year','settlement_name','district_raw','after_years','after_ownpoint']].to_string(index=False))

from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
from scipy.spatial import cKDTree
B=Path(__file__).resolve().parent;R=B.parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def xyz(lat,lon):
 a=np.deg2rad(lat);b=np.deg2rad(lon);return np.c_[np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)]
def dist(chord):return 12742.0176*np.arcsin(np.clip(chord/2,0,1))
def same(a,b):return ((a==b)|(a.isna()&b.isna())).fillna(False)
axis=pd.read_parquet(B/'settlement_axis_2021_coordinate477.parquet');new=axis[axis.cycle07_coordinate477_applied];tree=cKDTree(xyz(new.lat,new.lon));summaries={};allchanges=[]
for fam in ['education','commerce','medical']:
 d=pd.read_parquet(B/fam/'source_objects_relinked.parquet');oldp=R/'model_inputs_cycle05/relinked_v4'/fam/'source_objects_relinked.parquet';old=pd.read_parquet(oldp);assert len(d)==len(old)and d[['osm_type','osm_id']].equals(old[['osm_type','osm_id']]);derived={'baseline_uid','conditional_uid','candidate_uid','coordinate_candidate_uid','link_status','linked_distance_km','nearest_uid_unaccepted','nearest_id_unaccepted','nearest_distance_km','second_nearest_distance_km','coordinate_tied_possible_uid_json','coordinate_nearest_distance_tie_ambiguous','baseline_changed_from_previous_axis'};checked=[]
 for c in old.columns:
  if c in derived or(c.startswith('count_')and(c.endswith('_uid')or c.endswith('_eligible'))):continue
  assert c in d and same(d[c],old[c]).all(),(fam,c);checked.append(c)
 for c in [c for c in d if c.startswith('cycle05_v4_')]:assert same(d[c],old[c.removeprefix('cycle05_v4_')]).all(),(fam,c)
 geom=np.isfinite(d.lat)&np.isfinite(d.lon)&d.lat.between(-90,90)&d.lon.between(-180,180);nd=np.full(len(d),np.nan);dd,j=tree.query(xyz(d.loc[geom,'lat'],d.loc[geom,'lon']),k=1);nd[geom]=dist(dd);radius=10 if fam=='medical'else 5;impact=geom&(nd<=np.maximum(radius,old.second_nearest_distance_km.fillna(0).to_numpy())+1e-7);canonical='count_canonical_site_id'if fam=='medical'else'canonical_site_id';closure=set(d.loc[impact,canonical]);inside=d[canonical].isin(closure);countcols=[c for c in d if c.startswith('count_')and c.endswith('_uid')];changed=np.zeros(len(d),bool)
 for c in countcols:changed|=~same(d[c],old[c]).to_numpy()
 assert not (changed&~inside).any(),fam
 rows=d.loc[changed,['osm_type','osm_id','name','lat','lon','tags_json',canonical,'source_address_locality','link_status','cycle05_v4_link_status']+countcols+['cycle05_v4_'+c for c in countcols]].copy();rows['nearest_new477_distance_km']=nd[changed];rows['within_own_new477_geometry_impact']=impact[changed];rows['within_canonical_geometry_impact_closure']=inside[changed];rows.to_parquet(B/fam/'all_changed_count_link_witnesses.parquet',index=False)
 f=pd.read_parquet(B/fam/'settlement_features_full_axis.parquet').set_index('id');oldf=pd.read_parquet(R/'model_inputs_cycle05/relinked_v4'/fam/'settlement_features_full_axis.parquet').set_index('id');features=pd.read_parquet(B/fam/'all_feature_changes_vs_v4.parquet');features['family']=fam;allchanges.append(features);newcounts={};newpositive={}
 for c in countcols:
  group=d.loc[d[c].isin(new.id)].drop_duplicates([c,canonical]);newcounts[c]=len(group);newpositive[c]=int(group[c].nunique())
 summary={'source_rows':len(d),'raw_source_columns_exactly_preserved':checked,'old_v4_link_columns_exactly_preserved':len([c for c in d if c.startswith('cycle05_v4_')]),'all_477_geometry_influence_raw_objects':int(impact.sum()),'count_link_changed_raw_objects':int(changed.sum()),'count_link_changes_outside_canonical_geometry_closure':int((changed&~inside).sum()),'strict_link_changed_raw_objects':int((~same(d.baseline_uid,old.baseline_uid)).sum()),'all_nearest_tie_raw_objects':int(d.coordinate_nearest_distance_tie_ambiguous.sum()),'new477_counted_canonical_sites_by_channel':newcounts,'new477_positiveNPs_by_channel':newpositive,'changed_function_feature_cells':len(features),'changed_function_feature_NPs':int(features.id.nunique()),'source_input_old_v4_sha256':sha(oldp)};summaries[fam]=summary
 features_only=[c for c in f if c.endswith('_count')or c.endswith('_sum')or c.endswith('_campuses')];baselinecols=[c for c in features_only if '_baseline_'in c];geo_cols=[c for c in features_only if '_candidate_'in c]
 summary['baseline_feature_changed_NPs']=int(((f[baselinecols]!=oldf[baselinecols])&~(f[baselinecols].isna()&oldf[baselinecols].isna())).any(axis=1).sum())if baselinecols else 0
 summary['geographic_feature_changed_NPs']=int(((f[geo_cols]!=oldf[geo_cols])&~(f[geo_cols].isna()&oldf[geo_cols].isna())).any(axis=1).sum())if geo_cols else 0
pd.concat(allchanges,ignore_index=True).to_parquet(B/'all_three_family_feature_changes.parquet',index=False)
r={'status':'AUTHOR_ACTUAL_SOURCE_READBACK_AND_FINITE_GEOMETRY_CLOSURE_PASS_PENDING_INDEPENDENT_ADMISSION','families':summaries,'changed_function_feature_NPs_union':int(pd.concat(allchanges).id.nunique()),'no_model_predictions_mass_or_agreement_scores_read':True,'Mi_provider_pool_change_status':'Function sourcefeatures changed; rootmustrecomputemass/viewundercurrentdeclaredpolicy; doNOTassumeunchangedMi.','source_inventory_incomplete_real_absence_unknown':True,'code_sha256':sha(Path(__file__))};(B/'finite_impact_readback_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))

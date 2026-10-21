from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,pyarrow.parquet as pq
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'model_inputs_cycle07/institutional_relink477_v1';O=B/'reviews/cycle07_institutional_relink477_independent';checks=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ck(k,v):checks.append(dict(check=k,pass_=bool(v)))
axis=pd.read_parquet(P/'settlement_axis_2021_coordinate477.parquet');base=pd.read_parquet(B/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');patch=pd.read_parquet(B/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet').set_index('id');mask=axis.id.isin(patch.index);ck('exact477ids_patched',mask.sum()==477)
for c in base:
 if c not in ['lat','lon']:ck('axis_source_allcells_'+c,axis[c].equals(base[c]))
 else:
  ck('axis_coordinate_unaffected_'+c,axis.loc[~mask,c].equals(base.loc[~mask,c]));ck('axis_coordinate477_source_exact_'+c,np.array_equal(axis.loc[mask,c],axis.loc[mask,'id'].map(patch['new_'+c])))
allchanges=[];nraw=0
for fam in ['education','commerce','medical']:
 p=P/fam/'source_objects_relinked.parquet';names=pq.ParquetFile(p).schema_arrow.names;cols=[x for x in names if x.startswith('cycle05_v4_')];origcols=[x[len('cycle05_v4_'):] for x in cols];d=pd.read_parquet(p,columns=cols+list(dict.fromkeys([x for x in names if x.startswith('count_') and x.endswith('_uid')])));v4=pd.read_parquet(B/'model_inputs_cycle05/relinked_v4'/fam/'source_objects_relinked.parquet',columns=origcols)
 for c,oldc in zip(cols,origcols):
  try:pd.testing.assert_series_equal(d[c],v4[oldc],check_names=False);ok=True
  except AssertionError:ok=False
  ck(fam+':all_oldV4_cells_preserved_'+oldc,ok)
 cc=[x for x in d if x.startswith('count_') and x.endswith('_uid')];changed=np.zeros(len(d),bool)
 for c in cc:changed|=d[c].fillna('').ne(d['cycle05_v4_'+c].fillna('')).to_numpy()
 nraw+=changed.sum();w=pd.read_parquet(P/fam/'all_changed_count_link_witnesses.parquet');ck(fam+':complete_changed_countlink_rows',len(w)==changed.sum());ck(fam+':changedcount_ownnewgeometry_or_canonicalclosure',w.within_canonical_geometry_impact_closure.fillna(False).all())
 old=pd.read_parquet(B/'model_inputs_cycle05/relinked_v4'/fam/'settlement_features_full_axis.parquet');new=pd.read_parquet(P/fam/'settlement_features_full_axis.parquet');fields=[x for x in old if x.startswith(('education_osm2021_','services_osm2021_','medical_osm_'))]
 for c in fields:
  a=old[c].to_numpy(dtype=float,na_value=np.nan);z=new[c].to_numpy(dtype=float,na_value=np.nan);diff=~np.isclose(a,z,atol=0,rtol=0,equal_nan=True)
  for j in np.flatnonzero(diff):allchanges.append(dict(id=old.id.iloc[j],field=c,old_value=a[j],new_value=z[j],is_new477=old.id.iloc[j] in patch.index,family=fam))
expect=pd.DataFrame(allchanges).sort_values(['family','field','id']).reset_index(drop=True);actual=pd.read_parquet(P/'all_three_family_feature_changes.parquet').sort_values(['family','field','id']).reset_index(drop=True);ck('all116_source_feature_changes_exact',len(expect)==len(actual)==116 and expect[['id','field','family','is_new477']].equals(actual[['id','field','family','is_new477']]) and all(np.array_equal(expect[c].to_numpy(float),pd.to_numeric(actual[c].replace({'<NA>':np.nan,'True':1.,'False':0.}),errors='raise').to_numpy(dtype=float,na_value=np.nan),equal_nan=True)for c in ['old_value','new_value']));ck('31distinct_changed_NPs_exact',expect.id.nunique()==31);ck('all42_changed_rawcountlinks_exact',nraw==42)
res=dict(status='ACCEPTED' if all(x['pass_']for x in checks) else 'REJECTED',all_checks_passed=all(x['pass_']for x in checks),n_checks=len(checks),n_failed=sum(not x['pass_']for x in checks),checks=checks,accepted_source_manifest_sha256=sha(P/'source_freeze_manifest.json'),scope='Fullaxis originalcolumn/477coordinate transformation; alloldV4 diagnostic/countlinkcells preserved; fullchanged42rawcountlinkclosure and116features/31NP independently enumerated. Source incomplete; newzero notabsence. SourceMi/providerpool MUST re-evaluate, notassumedunchanged.');(O/'delta_audit.json').write_text(json.dumps(res,indent=2)+'\n');print(res['status'],res['n_checks'],res['n_failed']);print([x for x in checks if not x['pass_']])

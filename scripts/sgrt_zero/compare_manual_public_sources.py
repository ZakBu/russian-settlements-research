"""Reconcile frozen source records by natural identifiers; retain every diagnosed metadata difference."""
from pathlib import Path
import json,argparse,numpy as np,pandas as pd
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manual',type=Path,required=True);parser.add_argument('--public',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();m=args.manual;b=args.public;out=args.output;reports=[];failures=[]
def role(*names):return next((m/n for n in names if (m/n).is_dir()),m/names[-1])
health=role('health/public_scope_complete_corrected','health/public_scope_corrected');edu=role('education_general_scope_corrected','education');clinical=role('federal_medical/functions_complete_scope_corrected','federal_medical/functions')
def series_equal(a,z):
 try:pd.testing.assert_series_equal(a,z,check_dtype=False,check_exact=True);return True
 except AssertionError:return False
def compare(label,x,y,keys,metadata_cols=()):
 assert not x.duplicated(keys).any() and not y.duplicated(keys).any(),(label,'nonunique key')
 x=x.sort_values(keys).reset_index(drop=True);y=y.sort_values(keys).reset_index(drop=True);r={'path':label,'rows_manual':len(x),'rows_public':len(y),'alignment_key':keys,'differences':[],'unexplained':[]}
 assert len(x)==len(y) and set(x)==set(y),(label,'schema/rowcount')
 for c in x:
  if series_equal(x[c],y[c]):continue
  same=x[c].eq(y[c])|x[c].isna()&y[c].isna();bad=~same.fillna(False);e={'column':c,'differing_values':int(bad.sum()),'examples':[{'key':{k:str(x.at[i,k]) for k in keys},'manual':str(x.at[i,c]),'public':str(y.at[i,c])} for i in np.flatnonzero(bad.to_numpy())[:4]]}
  if c in metadata_cols:e['category']='explicitly_diagnosed_nonassignment_metadata'
  elif pd.api.types.is_float_dtype(x[c]) and pd.api.types.is_float_dtype(y[c]):
   a=x[c].to_numpy(float,na_value=np.nan);z=y[c].to_numpy(float,na_value=np.nan);finite=np.isfinite(a)&np.isfinite(z);e['max_absolute_difference']=float(np.max(np.abs(a[finite]-z[finite]))) if finite.any() else None;e['within_1e_12']=bool(np.isclose(a,z,rtol=1e-12,atol=1e-12,equal_nan=True).all());e['category']='roundoff' if e['within_1e_12'] else 'unexplained';
  else:e['category']='unexplained'
  if e['category']=='unexplained':r['unexplained'].append(c);failures.append(label+':'+c)
  r['differences'].append(e)
 reports.append(r);print(label,'unexplained',r['unexplained'],flush=True)
 return x,y
# F034 retains its stable XML/source-row key even when joins permute output order.
cm=pd.read_parquet(clinical/'care_rows_classified.parquet');cp=pd.read_parquet(b/'federal_medical/functions/care_rows_classified.parquet')
compare('federal_medical/functions/care_rows_classified.parquet',cm,cp,['source_record_row'])
for label,manual,public in [('federal_medical/functions/service_evidence_by_care_address.parquet',clinical/'service_evidence_by_care_address.parquet',b/'federal_medical/functions/service_evidence_by_care_address.parquet'),('health/public_scope_corrected/federal_service_evidence_with_identity.parquet',health/'federal_service_evidence_with_identity.parquet',b/'health/public_scope_corrected/federal_service_evidence_with_identity.parquet')]:
 frames=[];mapping=[]
 for path,care in [(manual,cm),(public,cp)]:
  f=pd.read_parquet(path);idx=f.source_row_index.to_numpy(int);assert (idx>=0).all() and (idx<len(care)).all();back=care.iloc[idx].reset_index(drop=True)
  assert f.UIDSPMO.astype(str).reset_index(drop=True).equals(back.UIDSPMO.astype(str)) and f.IDADDRESS.astype(str).reset_index(drop=True).equals(back.IDADDRESS.astype(str)), 'ordinal must point to actual subdivision and care address'
  f['_stable_f034_source_record_row']=back.source_record_row.to_numpy();mapping.append({'rows':len(f),'ordinal_range':[int(idx.min()),int(idx.max())],'all_ordinal_rows_match_UIDSPMO_and_IDADDRESS':True});frames.append(f.drop(columns=['source_row_index']))
 compare(label,*frames,['_stable_f034_source_record_row','service_code']);reports[-1]['derived_ordinal_mapping_verification']=mapping;reports[-1]['ordinal_source_row_index_is_provenance_not_dropped_scientific_record']=True
for name in ['physical_sites.parquet','source_inventory_current.parquet']:
 x=pd.read_parquet(edu/name);y=pd.read_parquet(b/'education'/name)
 xx,yy=compare('education/'+name,x,y,['provider_id'],['census_population_role','nearest_reference_distance_km','nearest_reference_uses_derived_city_coordinate'])
 census_diff=xx.census_population_role.fillna('<unknown>').ne(yy.census_population_role.fillna('<unknown>'))
 assert xx.loc[census_diff,'population_role'].eq('external_context_nonadditive').all() and yy.loc[census_diff,'population_role'].eq('external_context_nonadditive').all()
 assert xx.loc[census_diff,'is_federal_city_context'].eq(True).all() and yy.loc[census_diff,'is_federal_city_context'].eq(True).all()
 assert xx.nearest_reference_is_identity.eq(False).all() and yy.nearest_reference_is_identity.eq(False).all()
 reports[-1]['metadata_scope_proof']={'changed_census_role_records':int(census_diff.sum()),'actual_population_role_nonadditive_in_both':True,'actual_federal_city_context_in_both':True,'nearest_reference_is_not_identity_in_both':True}
# Only inert summary coordinates differ: they are explicitly prohibited as external provider seeds.
x=pd.read_parquet(edu/'np_supply.parquet');y=pd.read_parquet(b/'education/np_supply.parquet')
keys=['source_record_id','service_code','source_id'];xx,yy=compare('education/np_supply.parquet',x,y,keys,['site_lat','site_lon','census_population_role'])
bad=(~(xx.site_lat.eq(yy.site_lat)|xx.site_lat.isna()&yy.site_lat.isna()))|(~(xx.site_lon.eq(yy.site_lon)|xx.site_lon.isna()&yy.site_lon.isna()))
assert xx.loc[bad,'default_external_seed_eligible'].eq(False).all() and yy.loc[bad,'default_external_seed_eligible'].eq(False).all();assert xx.loc[bad,'population_role'].eq('external_context_nonadditive').all() and yy.loc[bad,'population_role'].eq('external_context_nonadditive').all();reports[-1]['all_coordinate_differences_in_nonadditive_city_summary_rows_prohibited_external_seeds']=True
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'reports':reports,'declared_metadata_explanation':{'census_population_role':'Older manual census label differs from the full rebuild label; actual population_role and is_federal_city_context are checked exact and nonadditive in both. Counts and record keys are retained above.','education_nearest_reference':'diagnostic nearest reference, nearest_reference_is_identity=False; not accepted NP ownership or actual school coordinates','education_summary_coordinates':'three city contexts × four service families, no external seeds; public canonical reference coordinates replace stale/missing summary values'},'failures':failures},ensure_ascii=False,indent=2)+'\n');raise SystemExit(bool(failures))

"""Additional sidecar only: values never used for identity; no master or axis mutation."""
from pathlib import Path
import argparse,re,json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent;AXIS=ROOT.parent/'axis/full_settlement_axis.parquet'
def norm(s):
 if s is None or pd.isna(s):return ''
 return re.sub(r'[^а-яa-z0-9]+',' ',str(s).lower().replace('ё','е')).strip()
def context(s):
 s=norm(s)
 return ' '.join(t for t in s.split() if t not in {'муниципальный','муниципальное','муниципального','образование','образования','район','района','городской','городского','округ','округа','город','г','мо','мр','го'})
def run(folder):
 a=pd.read_parquet(AXIS);a=a[a.source_record_id_2010.notna()].copy();a['name_key']=a.name.map(norm);a['type_key']=a.type.map(norm);a['native_county_key']=a.district_raw_2010.map(context);a['current_county_key']=a.municipality_upper_2021.map(context)
 d=pd.read_parquet(folder/'primary_source_NP_inventory.parquet').copy();d['name_key']=d.settlement_name.map(norm);d['type_key']=d.settlement_type.map(norm);d['official_county_key']=d.official_county.map(context);d['source_row_grain']='literal_settlement_not_municipal_aggregate';d['strict_uid']=None;d['conditional_uid']=None;d['candidate_uids_json']='[]';d['link_status']='unmatched_literal_region_type_name';d['link_identity_uses_population']=False;d['baseline_original_secondary_population']=float('nan');d['baseline_original_quality']=None;d['axis_original_source_record_id_2010']=None;d['source_2010_boundary_equals2021_boundary_assumed']=False
 gg=a.groupby(['region','type_key','name_key']).indices
 sg=d.groupby(['region','type_key','name_key']).size();sc=d.groupby(['region','type_key','name_key','official_county_key']).size()
 for i,r in d.iterrows():
  key=(r.region,r.type_key,r.name_key);pos=gg.get(key,[]);cand=a.iloc[pos];d.at[i,'candidate_uids_json']=json.dumps(cand.id.tolist(),ensure_ascii=False);picked=None
  if len(cand)==1 and sg[key]==1:
   picked=cand.iloc[0];d.at[i,'strict_uid']=picked.id;d.at[i,'link_status']='unique_literal_region_type_name_in_both_2010_scopes'
  elif len(cand):
   county=r.official_county_key
   if county:
    source_n=sc.get((*key,county),0)
    native=cand[cand.native_county_key.eq(county)]
    if len(native)==1 and source_n==1:
     picked=native.iloc[0];d.at[i,'strict_uid']=picked.id;d.at[i,'link_status']='unique_literal_region_type_name_and_native2010_district_in_both_sources'
    else:
     same=cand[cand.current_county_key.eq(county)]
     if len(same)==1 and source_n==1:
      picked=same.iloc[0];d.at[i,'conditional_uid']=picked.id;d.at[i,'link_status']='literal_region_type_name_disambiguated_only_with2021_municipal_context_requires_review'
     else:d.at[i,'link_status']='homonym_or_duplicate_unresolved'
  if picked is not None:
   d.at[i,'baseline_original_secondary_population']=picked.population_2010;d.at[i,'baseline_original_quality']=picked.population_value_quality_2010;d.at[i,'axis_original_source_record_id_2010']=picked.source_record_id_2010
 d['primary_minus_original']=d.primary_population-d.baseline_original_secondary_population;d['value_disagrees_with_original']=d.primary_minus_original.ne(0)&d.baseline_original_secondary_population.notna();d['primary_value_verified_scope']='permanent_resident_settlement_census2010_20101014_source_publication';d['parent_root_review_required_before_model_override']=True
 assert d.source_record_id.is_unique
 for col in ['strict_uid','conditional_uid']:assert d[col].dropna().is_unique
 d.to_parquet(folder/'additional_primary2010_layer.parquet',index=False);d.to_csv(folder/'additional_primary2010_layer.csv.gz',index=False)
 strict_identity_count=int(d.strict_uid.notna().sum());strict=d[d.strict_uid.notna() & d.primary_population.notna()].copy();strict['id']=strict.strict_uid;strict.to_parquet(folder/'strict_additional_primary2010_by_id.parquet',index=False)
 report={'source_rows':len(d),'strict_identity_rows':strict_identity_count,'strict_population_rows':len(strict),'strict_identity_NULL_primary_count':strict_identity_count-len(strict),'conditional_municipal2021_context_rows':int(d.conditional_uid.notna().sum()),'unresolved_rows':int((d.strict_uid.isna()&d.conditional_uid.isna()).sum()),'strict_value_disagreements':int(strict.value_disagrees_with_original.sum()),'strict_primary_population_sum':int(strict.primary_population.sum()),'strict_original_population_sum':float(strict.baseline_original_secondary_population.sum()),'strict_delta_sum':float(strict.primary_minus_original.sum()),'link_status_counts':d.link_status.value_counts().to_dict(),'axis_sha256':hashlib.sha256(AXIS.read_bytes()).hexdigest(),'axis_modified':False,'values_used_for_identity':False,'conditional_promoted_to_strict':False,'strict_id_unique':strict.id.is_unique};(folder/'link_receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);args=p.parse_args();run(args.folder)

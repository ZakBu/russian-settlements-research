#!/usr/bin/env python3
"""Build explicit NP-point medical scenario from federal care-address evidence.

Exact F038 identity only. Physical sites remain byte-identical. Dated historic
rows survive; an exact current unit+address contradiction holds only that source.
"""
import argparse,hashlib,json,re,shutil,sys
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_zero.saratov_registry import historical_np_supply
from scripts.sgrt_zero.health import json_items,coverage

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text(v):return '' if v is None or pd.isna(v) else str(v)
def address_key(v):return re.sub(r'[^а-яa-z0-9]+','',text(v).lower().replace('ё','е'))
def oid(v):return text(v).replace(' ','')
def truth(v):return text(v).lower() in ['true','1']

def historical_time_audit(historical,classified):
 # IDADDRESS is version-specific; compare actual unit OID and exact address
 # literal or exact GAR UUID. A same-name NP never establishes time conflict.
 c=classified[['OID_SPMO','ADDR','ADDR_GAR','organization_oms_participation_ended_asof']].drop_duplicates().copy()
 c['unit_oid']=c.OID_SPMO.map(oid);c['address_key']=c.ADDR.map(address_key);c['gar_key']=c.ADDR_GAR.fillna('').str.lower()
 c['gar_unambiguous_literal']=c.gar_key.map(c.groupby('gar_key').address_key.nunique()).eq(1)
 units={key:g for key,g in c.groupby('unit_oid')};rows=[]
 for r in historical.to_dict('records'):
  u=oid(r['subdivision_oid']);g=units.get(u);status='no_exact_current_unit_evidence';exclude=False
  if g is not None:
   addr=address_key(r['activity_address']);gar=text(r.get('activity_address_id')).lower()
   matches=g[g.address_key.eq(addr)|(g.gar_key.eq(gar)&g.gar_unambiguous_literal&bool(gar))]
   if len(matches):
    ended=matches.organization_oms_participation_ended_asof.map(truth)
    exclude=bool(ended.all());status='exact_unit_address_current_OMS_ended_only' if exclude else 'exact_unit_address_has_current_nonended_record'
   elif g.organization_oms_participation_ended_asof.map(truth).any():status='same_unit_OID_ended_record_address_not_exact_uncertain'
   else:status='same_unit_OID_current_record_address_not_exact'
  rows.append({'object_id':r['object_id'],'subdivision_oid':u,'activity_address':r['activity_address'],'source_time_relation':status,'historical_offer_held_by_exact_current_evidence':exclude,'physical_closure_inferred':False})
 return pd.DataFrame(rows)

def federal_np_supply(evidence,identities,classified,reference):
 ids=identities.copy()
 if ids[['UIDSPMO','IDADDRESS']].duplicated().any():raise ValueError('Address identity pair is not unique')
 for x in [evidence,ids]:
  for k in ['UIDSPMO','IDADDRESS']:x[k]=x[k].astype(str)
 joined=evidence.merge(ids[['UIDSPMO','IDADDRESS','source_record_id']],on=['UIDSPMO','IDADDRESS'],how='left',validate='many_to_one')
 joined['np_identity_accepted']=joined.source_record_id.notna()
 matched=joined[joined.np_identity_accepted].copy();rows=[]
 for (sid,service),g in matched.groupby(['source_record_id','service_code']):
  scopes=sorted(set(g.medical_need_scope.dropna().astype(str)))
  rows.append(dict(provider_id='np-med:'+service+':'+sid,source_record_id=sid,service_code=service,supply_status='observed',source_id=json.dumps(['FEDERAL_F034_F038_20261023']),source_year=json.dumps(['2026']),evidence_quality='current_federal_OMS_registry_exact_care_address_NSI_role_not_verified_operation',source_records=len(g),has_official_registry=True,has_mapped_OSM=False,service_basis=json.dumps(sorted(g.service_basis.unique()),ensure_ascii=False),location_precision='settlement_point',np_identity_basis='exact_literal_care_address_not_legal_address',actual_operational_status_verified=False,observed_flow=False,capacity_total=np.nan,historical_source_only=False,historical_supply_proxy=False,restriction_scope_unknown=bool(g.restriction_scope_unknown.all()),local_supply_eligible=True,default_external_seed_eligible=True,default_external_seed_exclusion_reason='',medical_need_scope=json.dumps(scopes,ensure_ascii=False),general_adult_profile_evidence=bool(g.general_adult_profile_evidence.any()),named_child_only_contingent=bool(g.named_child_only_contingent.all()),has_child_specific_source=bool(g.named_child_only_contingent.any()),universal_hospital_suitability_verified=False,physical_coordinates_observed=False,external_seed_assumption='representative_NP_point_not_care_building'))
 out=pd.DataFrame(rows).merge(reference[reference.source_record_id.notna()][['source_record_id','name','region','lat','lon','population_role','ordinary_spatial_2021']],on='source_record_id',how='left',validate='many_to_one').rename(columns={'name':'provider_name','region':'context_region','lat':'site_lat','lon':'site_lon'})
 out['context_region_basis']='strict_settlement_identity';out['source_public_scope_check']='explicit_restrictions_and_ended_OMS_source_excluded_unknown_operator_scope_flagged'
 return out,joined

def combine_np_sources(frames):
 allrows=pd.concat(frames,ignore_index=True)
 flags=['historical_source_only','restriction_scope_unknown','named_child_only_contingent','general_adult_profile_evidence','has_child_specific_source']
 for flag in flags:
  if flag not in allrows:allrows[flag]=False
  allrows[flag]=allrows[flag].astype('boolean').fillna(False)
 groups={}
 for r in allrows.to_dict('records'):
  key=(r['source_record_id'],r['service_code']);historical=bool(r['historical_source_only'])
  sets={col:set(str(v) for v in json_items(r.get(col))) for col in ['source_id','source_year','service_basis','medical_need_scope']}
  federal=any('FEDERAL_F034_F038' in v for v in sets['source_id'])
  if key not in groups:
   item=r.copy();item['_sets']=sets;item['_observed']=r['supply_status']=='observed';item['saratov_historical_2021_evidence_present']=historical;item['federal_current_2026_evidence_present']=federal;groups[key]=item;continue
  item=groups[key]
  for col,values in sets.items():item['_sets'][col].update(values)
  item['source_records']+=r['source_records']
  for field in ['has_official_registry','has_mapped_OSM','general_adult_profile_evidence','has_child_specific_source']:item[field]=bool(item.get(field,False)) or bool(r.get(field,False))
  for field in ['historical_source_only','restriction_scope_unknown','named_child_only_contingent']:item[field]=bool(item.get(field,False)) and bool(r.get(field,False))
  item['_observed']|=r['supply_status']=='observed';item['saratov_historical_2021_evidence_present']|=historical;item['federal_current_2026_evidence_present']|=federal
 out=[]
 for key in sorted(groups):
  r=groups[key]
  for col,values in r.pop('_sets').items():r[col]=json.dumps(sorted(values),ensure_ascii=False)
  r['supply_status']='observed' if r.pop('_observed') else 'proxy';r['historical_supply_proxy']=bool(r['historical_source_only'])
  r['default_external_seed_eligible']=bool(r['has_official_registry']) and not bool(r['has_mapped_OSM']);r['default_external_seed_exclusion_reason']='mapped_site_used_instead_of_settlement_centroid' if r['has_mapped_OSM'] else ''
  r['universal_hospital_suitability_verified']=False;r['physical_coordinates_observed']=False;r['external_seed_assumption']='representative_NP_point_not_care_building'
  if r['federal_current_2026_evidence_present']:r['evidence_quality']='current_federal_registry_with_optional_dated_or_OSM_source_not_verified_operation'
  out.append(r)
 result=pd.DataFrame(out)
 missing=result.site_lat.isna()|result.site_lon.isna()
 result.loc[missing,'default_external_seed_eligible']=False
 result.loc[missing,'default_external_seed_exclusion_reason']='settlement_reference_coordinates_unavailable'
 result.loc[missing,'location_precision']='settlement_identity_coordinate_unavailable'
 return result


def main():
 p=argparse.ArgumentParser()
 for name in ['classified','evidence','addresses','reference','base-health','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--historical-supplement',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 c=pd.read_parquet(a.classified);e=pd.read_parquet(a.evidence);identities=pd.read_parquet(a.addresses);ref=pd.read_parquet(a.reference)
 base=pd.read_parquet(a.base_health/'np_supply.parquet');base['historical_source_only']=False;frames=[base]
 if a.historical_supplement:
  h=pd.read_parquet(a.historical_supplement/'sites_matched_or_held.parquet');he=pd.read_parquet(a.historical_supplement/'service_evidence.parquet')
  audit=historical_time_audit(h,c);audit.to_parquet(a.output/'historical_current_source_time_audit.parquet',index=False)
  held=set(audit.loc[audit.historical_offer_held_by_exact_current_evidence,'object_id']);filtered=he[~he.object_id.isin(held)].copy()
  he.assign(held_by_exact_current_source=he.object_id.isin(held)).to_parquet(a.output/'historical_evidence_with_time_status.parquet',index=False)
  frames.append(historical_np_supply(filtered,ref))
 f,ev=federal_np_supply(e,identities,c,ref);f.to_parquet(a.output/'federal_np_supply.parquet',index=False);ev.to_parquet(a.output/'federal_service_evidence_with_identity.parquet',index=False);frames.append(f)
 combined=combine_np_sources(frames);combined.to_parquet(a.output/'np_supply.parquet',index=False)
 for name in ['physical_sites.parquet','additional_functional_offers.parquet','official_functional_order_evidence.parquet']:
  if (a.base_health/name).exists():shutil.copyfile(a.base_health/name,a.output/name)
 cov=coverage(ref,combined,pd.read_parquet(a.output/'physical_sites.parquet'));cov.to_parquet(a.output/'coverage_region.parquet',index=False);cov.to_csv(a.output/'coverage_region.csv',index=False)
 summary={'federal_unique_np':int(f.source_record_id.nunique()),'federal_NP_service_rows':len(f),'federal_by_service':f.service_code.value_counts().to_dict(),'federal_regions':int(f.context_region.nunique()),'combined_NP_service_rows':len(combined),'np_supply_sha256':sha(a.output/'np_supply.parquet'),'physical_sites_sha256':sha(a.output/'physical_sites.parquet'),'physical_sites_byte_identical':sha(a.output/'physical_sites.parquet')==sha(a.base_health/'physical_sites.parquet'),'new_NP_point_is_explicit_coarse_assumption':True,'not_geocoded_care_building':True,'code_sha256':sha(Path(__file__)),'inputs_sha256':{str(x):sha(x) for x in [a.classified,a.evidence,a.addresses,a.reference,a.base_health/'np_supply.parquet']}}
 if a.historical_supplement:summary['historical_time_relations']=audit.source_time_relation.value_counts().to_dict()
 (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()

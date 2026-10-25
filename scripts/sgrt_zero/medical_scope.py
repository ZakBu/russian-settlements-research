#!/usr/bin/env python3
"""Rebuild legacy primary source support with unit-level cohort exclusions.

Published legacy modules/data remain untouched. Children's care survives in raw
and need-specific rows; only unsupported universal primary confirmations leave.
"""
import argparse,json,hashlib,sys,shutil
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_zero.health import combined_np_supply,explicit_restricted_scope,named_child_only_unit,higher_official_evidence,coverage,primary_unit_scope_flags,osm_explicit_nongeneral_primary_specialty
PRIMARY=['medical_basic_primary','medical_physician_primary']

def federal_child_unit_witnesses(active,care):
 """Exact unit OID AND literal care-address match, with coherent child VID.

 A generic name in an older extract must not erase the same unit's explicit
 federal child type. The extract source year must agree with the federal snapshot year; no
 historical backcast, fuzzy join, parent-title inference or cross-address
 transfer is allowed. Mixed adult/child types at the same key stay unresolved.
 """
 def literal(v):return ' '.join(str(v or '').casefold().split())
 f=care[care.record_validity_status.eq('valid_at_snapshot') & care.subdivision_exact_join & care.care_address_exact_pair_join].copy()
 f['_oid']=f.OID_SPMO.fillna('').astype(str).str.strip();f['_address']=f.ADDR.fillna('').map(literal)
 f['_child_type']=f.VID_SPMO.map(named_child_only_unit)
 f['_year']=pd.to_numeric(f.source_snapshot_date.fillna('').astype(str).str.extract(r'(20\d{2})',expand=False),errors='coerce')
 f=f[f._oid.ne('')&f._address.ne('')&f._year.notna()]
 coherent=f.groupby(['_oid','_address','_year'])._child_type.all()
 eligible=set(coherent[coherent].index)
 a=active.copy();a['_oid']=a.subdivision_oid.fillna('').astype(str).str.strip();a['_address']=a.activity_address.fillna('').map(literal)
 a['_year']=pd.to_numeric(a.source_year,errors='coerce')
 a=a[[k in eligible for k in zip(a._oid,a._address,a._year)]]
 return a[['object_id','subdivision_oid','activity_address','_oid','_address','_year']].merge(f[f._child_type][['_oid','_address','_year','NAM_SPMO','VID_SPMO','ADDR','source_record_row']].drop_duplicates(),on=['_oid','_address','_year'],how='inner').rename(columns={'_year':'scope_evidence_source_year'}).drop(columns=['_oid','_address'])


def correct(base_health,legacy_sites,legacy_supply,reference,output,federal_care_ledger=None):
 output.mkdir(parents=True,exist_ok=True);ref=pd.read_parquet(reference);allrows=pd.read_parquet(legacy_sites)
 shutil.copyfile(legacy_sites,output/'legacy_sites_all_rows.parquet')
 active=allrows[allrows.source_record_id.notna()&~allrows.registered_exclusion_present.fillna(False)&~allrows.source_year_conflict_with_inventory.fillna(False)].copy()
 active['explicit_restricted_scope']=[explicit_restricted_scope(a,b) for a,b in zip(active.subdivision_name,active.organization_name)]
 active['named_child_only_contingent']=active.subdivision_name.map(named_child_only_unit)
 active['exact_federal_child_unit_type_witness']=False
 if federal_care_ledger is not None:
  witnesses=federal_child_unit_witnesses(active,pd.read_parquet(federal_care_ledger))
  witnesses.to_parquet(output/'exact_federal_child_unit_type_witnesses.parquet',index=False)
  active['exact_federal_child_unit_type_witness']=active.object_id.isin(set(witnesses.object_id))
  active['named_child_only_contingent']|=active.exact_federal_child_unit_type_witness
 flags=pd.DataFrame([primary_unit_scope_flags(r) for r in active.to_dict('records')],index=active.index)
 active['new_unit_primary_scope_held']=flags[['restricted_access_signal','pediatric_only_signal','narrow_unit_name_ambiguity_signal']].any(axis=1)
 x=active.assign(service_code=active.service_codes.fillna('').str.split('|')).explode('service_code');x=x[x.service_code.ne('')].copy()
 primary=x.service_code.isin(PRIMARY);oldheld=x.restricted_access_signal.fillna(False)|x.pediatric_only_signal.fillna(False)|x.narrow_unit_name_ambiguity_signal.fillna(False)
 x['previous_public_eligible']=~x.explicit_restricted_scope&~(primary&oldheld)
 x['new_named_child_primary_held']=x.previous_public_eligible&primary&(x.named_child_only_contingent|x.new_unit_primary_scope_held)
 x['universal_primary_unit_scope_held']=x.new_named_child_primary_held
 x['universal_primary_scope_hold_reason']=x.apply(lambda r:'explicit_child_cohort' if r.new_named_child_primary_held and r.named_child_only_contingent else ('literal_narrow_or_school_unit_not_universal_primary' if r.new_named_child_primary_held else ''),axis=1)
 x['current_source_eligible']=x.previous_public_eligible&~x.new_named_child_primary_held
 x['child_care_absent_inferred']=False
 x.to_parquet(output/'legacy_source_evidence_with_scope.parquet',index=False)
 held=x[x.new_named_child_primary_held].copy();held.to_parquet(output/'child_primary_confirmations_held.parquet',index=False)
 accepted=x[x.current_source_eligible].copy()
 # Retain the existing literal high-tech source role, separately auditable.
 original,orders=higher_official_evidence(pd.read_parquet(legacy_supply),allrows)
 old_primary=original[original.service_code.isin(PRIMARY)]
 replacement=[]
 for (sid,service),g in accepted[accepted.service_code.isin(PRIMARY)].groupby(['source_record_id','service_code']):
  replacement.append(dict(provider_id='medical:'+service+':'+sid,source_record_id=sid,service_code=service,supply_status='observed',source_id=json.dumps(sorted(g.source_id.unique()),ensure_ascii=False),source_year=json.dumps(sorted(g.source_year.astype(str).unique())),service_basis='literal_registry_primary_after_unit_cohort_scope_audit',source_records=len(g),observed_flow=False,capacity_total=None))
 # For other roles preserve the previously corrected public provider pool.
 original_other=original[~original.service_code.isin(PRIMARY)].copy()
 allowed=set(zip(pd.read_parquet(base_health/'np_supply.parquet').source_record_id,pd.read_parquet(base_health/'np_supply.parquet').service_code))
 original_other=original_other[[key in allowed for key in zip(original_other.source_record_id,original_other.service_code)]]
 official=pd.concat([original_other,pd.DataFrame(replacement)],ignore_index=True)
 physical=pd.read_parquet(base_health/'physical_sites.parquet').copy();physical['named_child_only_contingent']=physical.source_name.map(named_child_only_unit)
 physical['supply_status_before_child_scope']=physical.supply_status
 physical_flags=[primary_unit_scope_flags({'subdivision_name':n}) for n in physical.source_name]
 specialties=physical.source_healthcare_speciality.fillna('').astype(str) if 'source_healthcare_speciality' in physical else pd.Series('',index=physical.index)
 physical['explicit_OSM_general_practice_specialty']=specialties.map(lambda s:bool(set(s.casefold().split(';'))&{'general','general_practice','family_medicine','family_practice'}))
 physical['explicit_OSM_nongeneral_primary_specialty']=specialties.map(osm_explicit_nongeneral_primary_specialty)
 physical['new_unit_primary_scope_held']=[f['restricted_access_signal'] or f['pediatric_only_signal'] or f['literal_narrow_primary_unit_scope'] or (f['universal_primary_unit_function_unknown'] and not tag_positive) for f,tag_positive in zip(physical_flags,physical.explicit_OSM_general_practice_specialty)]
 bad=physical.service_code.isin(PRIMARY)&(physical.named_child_only_contingent|physical.new_unit_primary_scope_held|physical.explicit_OSM_nongeneral_primary_specialty)&physical.supply_status.eq('proxy')
 physical.loc[bad,'supply_status']='excluded_unit_scope_not_universal_primary';physical['child_care_absent_inferred']=False
 combined,evidence=combined_np_supply(official,physical,ref)
 combined['source_public_scope_check']='explicit_restricted_child_school_and_narrow_units_excluded_from_universal_primary'
 combined.to_parquet(output/'np_supply.parquet',index=False)
 physical[['provider_id','source_object_id','service_code','named_child_only_contingent','supply_status_before_child_scope','supply_status','child_care_absent_inferred']].to_parquet(output/'physical_child_scope_audit.parquet',index=False)
 if bad.any():physical.to_parquet(output/'physical_sites.parquet',index=False)
 else:shutil.copyfile(base_health/'physical_sites.parquet',output/'physical_sites.parquet')
 evidence.to_parquet(output/'source_evidence.parquet',index=False)
 for filename in ['additional_functional_offers.parquet','official_functional_order_evidence.parquet']:
  if (base_health/filename).exists():shutil.copyfile(base_health/filename,output/filename)
 cov=coverage(ref,combined,physical);cov.to_parquet(output/'coverage_region.parquet',index=False)
 before=pd.read_parquet(base_health/'np_supply.parquet');a=set(zip(before.source_record_id,before.service_code));b=set(zip(combined.source_record_id,combined.service_code))
 pd.DataFrame([dict(source_record_id=sid,service_code=c,change='removed_only_child_legacy_support') for sid,c in sorted(a-b)]).to_parquet(output/'provider_pool_changes.parquet',index=False)
 summary={'previously_eligible_named_child_primary_rows':int(held.named_child_only_contingent.sum()),'previously_eligible_universal_primary_unit_rows_held':len(held),'held_physician_rows':int(held.service_code.eq('medical_physician_primary').sum()),'held_basic_rows':int(held.service_code.eq('medical_basic_primary').sum()),'affected_unique_np':int(held.source_record_id.nunique()),'legacy_only_NP_service_keys_removed':len(a-b),'new_primary_keys_added':len(b-a),'physical_primary_rows_newly_held':int(bad.sum()),'exact_same_year_federal_child_type_held_rows':int((held.exact_federal_child_unit_type_witness).sum()),'cross_source_child_type_not_historical_backcast':True,'all_raw_legacy_rows_retained':True,'published_old_baseline_unchanged':True,'np_sha256':hashlib.sha256((output/'np_supply.parquet').read_bytes()).hexdigest(),'physical_sha256':hashlib.sha256((output/'physical_sites.parquet').read_bytes()).hexdigest()}
 (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))

def main():
 p=argparse.ArgumentParser()
 for flag in ['base-health','legacy-sites','legacy-supply','reference','output']:p.add_argument('--'+flag,type=Path,required=True)
 p.add_argument('--federal-care-ledger',type=Path,help='Optional exact child-unit type corroboration; raw classified federal ledger')
 a=p.parse_args();correct(a.base_health,a.legacy_sites,a.legacy_supply,a.reference,a.output,a.federal_care_ledger)
if __name__=='__main__':main()

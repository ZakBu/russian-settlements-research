#!/usr/bin/env python3
"""Combine dated medical registries and mapped OSM evidence without inventing care.

OSM assertions are proxies, not licences or observed patient destinations. Real
site coordinates and proven census identity remain separate. Unspecified medical
objects do not become FAPs, GPs or universal providers.
"""
from __future__ import annotations
import argparse
from datetime import date
import calendar
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/sgrt_mass'))
from match import normalize_name, normalize_region
from education import osm_temporal_status
from site_geometry import sphere_xyz,chord_km

BASIC='medical_basic_primary'
PHYSICIAN='medical_physician_primary'
UNSPECIFIED='unspecified_healthcare'
OSM_SOURCE='OSM_GEOFABRIK_MEDICAL_20261019'
STRICT_LINK='exact_source_address_locality_unique_within10km_distance_le5km'
NARROW=re.compile(r'стомат|зубн|dental|dentist|лаборатор|инвитро|гемотест|helix|\bcmd\b|онкол|туберк|психиатр|наркол|кожно.?венер|диализ|женск.{0,12}консульт|родильн|роддом|детск|педиатр|несовершеннолетн',re.I)
RESTRICTED=re.compile(r'школьн|общеобразоват|\bсош\b|\bмбоу\b|\bмдоу\b|детск.{0,8}сад|дошкольн|предрейс|исправител|\bфсин\b|здравпункт.{0,50}(?:завод|предприят)',re.I)
HOSPITAL_CLASSES={'hospital_source_tag','central_district_hospital_name_assertion','district_local_hospital_name_assertion','regional_hospital_name_assertion'}


def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as s:
  for b in iter(lambda:s.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()


def clean(value):
 if value is None or value is pd.NA or isinstance(value,float) and np.isnan(value):return ''
 return str(value).strip()


def tags(value):
 if isinstance(value,dict):return value
 try:return json.loads(clean(value) or '{}')
 except (ValueError,TypeError):return {}


def lifecycle_reason(row):
 t=tags(row.get('tags_json'))
 reasons=[]
 if row.get('inactive_source_assertion') is True or isinstance(row.get('inactive_source_assertion'),np.bool_) and bool(row.get('inactive_source_assertion')):reasons.append('source_inactive_assertion')
 for key in ['disused','abandoned','demolished','razed','removed','ruins']:
  value=clean(t.get(key,row.get(key))).lower()
  if value in {'yes','true','1'}:reasons.append(key+'='+value)
 for key in ['disused:healthcare','abandoned:healthcare','demolished:healthcare','disused:amenity','abandoned:amenity','demolished:amenity']:
  if clean(t.get(key)):reasons.append(key+'='+clean(t[key]))
 return '|'.join(reasons)


def classify_osm(row):
 """Return literal-source service hypotheses; narrow/restricted care stays apart."""
 if clean(row.get('broad_function'))!='healthcare':return []
 name=' '.join([clean(row.get('name')),clean(row.get('name_ru'))])
 kind=clean(row.get('medical_class'))
 specialty=clean(row.get('healthcare_speciality')).lower()
 restricted=bool(RESTRICTED.search(name))
 narrow=bool(NARROW.search(name))
 services=[]
 if not restricted and not narrow:
  if kind=='fap_name_assertion':services.append((BASIC,'mapped_named_fap','explicit_OSM_name_FAP_not_licence'))
  elif kind=='ambulatory_name_assertion':
   services.append((BASIC,'mapped_named_ambulatory','explicit_OSM_name_ambulatory_not_verified_staffing'))
   if re.search(r'врачебн.{0,12}амбулат|амбулат.{0,12}врач',name,re.I):services.append((PHYSICIAN,'mapped_named_physician_ambulatory','explicit_OSM_name_physician_ambulatory'))
  elif kind=='polyclinic_name_assertion':
   services.extend([(BASIC,'mapped_named_general_polyclinic','explicit_OSM_polyclinic_name_not_licence'),(PHYSICIAN,'mapped_named_general_polyclinic','explicit_OSM_polyclinic_name_not_verified_general_practitioner')])
  elif re.search(r'(?:^|[;, ])(?:general|general_practice|general_medicine|family_medicine|family_practice)(?:$|[;, ])',specialty) or re.search(r'общ.{0,8}врачебн.{0,12}практик|семейн.{0,8}врач',name,re.I):
   services.extend([(BASIC,'mapped_explicit_general_practice','literal_OSM_general_practice_specialty_or_name'),(PHYSICIAN,'mapped_explicit_general_practice','literal_OSM_general_practice_specialty_or_name')])
 # A hospital category indicates a mapped hospital, not exact licensed services.
 if kind in HOSPITAL_CLASSES and not restricted:
  services.append(('mapped_hospital_service_unknown_level','mapped_hospital_category','OSM_hospital_category_not_verified_beds_or_licence'))
 if not any(s[0] in {BASIC,PHYSICIAN} for s in services) and not restricted:
  services.append((UNSPECIFIED,'mapped_unspecified_or_narrow_healthcare','mapped_medical_presence_without_proven_general_primary_function'))
 return services


def legacy_bridge(reference,legacy):
 ref=reference[reference.source_record_id.notna()][['root','source_record_id','name','region','lat','lon']]
 out=legacy[legacy.root.notna()&legacy.source_record_id_2021.notna()].merge(ref,left_on=['root','source_record_id_2021'],right_on=['root','source_record_id'],how='inner',validate='one_to_one',suffixes=('_legacy','_reference'))
 if not out.id.is_unique:raise ValueError('Legacy identity bridge not unique')
 return out[['id','source_record_id','name_reference','region_reference','lat_reference','lon_reference']]


def attach_osm(objects,reference,legacy):
 out=objects.copy()
 out=out.merge(legacy_bridge(reference,legacy),left_on='baseline_uid',right_on='id',how='left',validate='many_to_one')
 agrees=pd.Series([normalize_name(a)==normalize_name(b) and bool(normalize_name(a)) for a,b in zip(out.source_address_locality,out.name_reference)],index=out.index)
 strict=out.link_status.eq(STRICT_LINK)&agrees&out.source_record_id.notna()
 # baseline source IDs are accepted only under the original explicit-address
 # rule. No nearest-node/nearest-village identity is promoted to an accepted ID.
 out['source_record_id']=out.source_record_id.where(strict)
 out['np_identity_basis']=np.where(strict,'explicit_address_locality_and_exact_legacy_census_bridge','unresolved_settlement_identity')
 # Federal-city identities can be proven by an explicit unique address even
 # when the census source has no accepted point for the whole city.
 for city in ['москва','санкт петербург','севастополь']:
  candidates=reference[reference.source_record_id.notna()&reference.region.eq(city)&reference.name.map(normalize_region).eq(city)]
  if candidates.source_record_id.nunique()!=1:continue
  literal_city=out.addr_city.map(normalize_region).eq(city)
  literal_region=out.addr_region.map(normalize_region)
  choose=out.source_record_id.isna()&literal_city&literal_region.isin(['',city])
  if not choose.any():continue
  candidate=candidates.iloc[0]
  out.loc[choose,'source_record_id']=candidate.source_record_id
  out.loc[choose,'name_reference']=candidate['name']
  out.loc[choose,'region_reference']=city
  out.loc[choose,'np_identity_basis']='explicit_unique_federal_city_address_tag_not_proximity'
  strict.loc[choose]=True
 out['site_lat']=pd.to_numeric(out.lat,errors='coerce');out['site_lon']=pd.to_numeric(out.lon,errors='coerce')
 out['geometry_valid']=out.site_lat.between(-90,90)&out.site_lon.between(-180,180)
 out['lifecycle_exclusion_reason']=[lifecycle_reason(r) for r in out.to_dict('records')]
 out['temporal_status']=[osm_temporal_status(a,b,s) for a,b,s in zip(out.start_date,out.end_date,out.source_snapshot_date)]
 out['eligible_source_status']=out.lifecycle_exclusion_reason.eq('')&~out.temporal_status.isin(['ended_before_snapshot','started_after_snapshot'])&out.geometry_valid
 out['actual_operational_status_verified']=False
 out['observed_flow']=False
 # An approximate contextual region permits a national coverage diagnostic;
 # it is never used to assign the physical object to the nearest NP.
 points=reference[reference.source_record_id.notna()&reference.lat.notna()&reference.lon.notna()].copy()
 tree=cKDTree(sphere_xyz(points.lat,points.lon));valid=out.geometry_valid
 dist,ix=tree.query(sphere_xyz(out.loc[valid,'site_lat'],out.loc[valid,'site_lon']),k=1,workers=1)
 out['nearest_reference_source_record_id']=None;out['nearest_reference_distance_km']=np.nan;out['context_region']=None
 out.loc[valid,'nearest_reference_source_record_id']=points.iloc[ix].source_record_id.to_numpy()
 out.loc[valid,'nearest_reference_distance_km']=chord_km(dist)
 out.loc[valid,'context_region']=points.iloc[ix].region.to_numpy()
 out['context_region_basis']='nearest_reference_point_context_only'
 regions=set(reference.region.dropna())
 for idx,row in out.iterrows():
  if strict.loc[idx]:out.loc[idx,['context_region','context_region_basis']]=[row.region_reference,'strict_settlement_identity'];continue
  region=normalize_region(row.addr_region)
  city=normalize_region(row.addr_city)
  if region in regions:out.loc[idx,['context_region','context_region_basis']]=[region,'literal_OSM_region_tag']
  elif city in {'москва','санкт петербург','севастополь'}:out.loc[idx,['context_region','context_region_basis']]=[city,'literal_OSM_federal_city_tag']
 return out


def physical_offers(linked):
 rows=[]
 for r in linked.to_dict('records'):
  classified=classify_osm(r)
  for service,quality,basis in classified:
   accepted=bool(r['eligible_source_status'])
   rows.append({'provider_id':'osm-med:'+clean(r['object_id'])+':'+service,'source_record_id':r['source_record_id'],
    'service_code':service,'supply_status':'proxy' if accepted else 'excluded_source_status',
    'site_lat':r['site_lat'],'site_lon':r['site_lon'],'location_precision':'mapped_site',
    'source_id':OSM_SOURCE,'source_year':int(clean(r['source_snapshot_date'])[:4]),'source_snapshot_date':r['source_snapshot_date'],
    'evidence_quality':quality,'service_basis':basis,'source_object_id':r['object_id'],'provider_name':r['name'],
    'np_identity_basis':r['np_identity_basis'],'context_region':r['context_region'],'context_region_basis':r['context_region_basis'],
    'nearest_reference_source_record_id':r['nearest_reference_source_record_id'],'nearest_reference_distance_km':r['nearest_reference_distance_km'],
    'source_medical_class':r['medical_class'],'source_name':r['name'],'source_addr_full':r['addr_full'],
    'source_healthcare_speciality':r['healthcare_speciality'],'source_tags_json':r['tags_json'],
    'lifecycle_exclusion_reason':r['lifecycle_exclusion_reason'],'temporal_status':r['temporal_status'],
    'actual_operational_status_verified':False,'function_assignment_verified_by_licence':False,'observed_flow':False,'capacity_total':np.nan})
 return pd.DataFrame(rows)


def json_items(value):
 literal=clean(value)
 try:parsed=json.loads(literal)
 except (ValueError,TypeError):return [literal] if literal else []
 if isinstance(parsed,list):return [item for child in parsed for item in json_items(child)]
 return [str(parsed)] if parsed is not None else []


def higher_official_evidence(official,sites):
 active=sites[sites.source_record_id.notna()&~sites.registered_exclusion_present.fillna(False)&~sites.source_year_conflict_with_inventory.fillna(False)].copy()
 active['literal_hightech_licensed_profile']=active.care_type_literal.fillna('').str.contains('высокотехнолог',case=False)
 cols=['source_record_id','object_id','source_id','source_year','source_part','source_row','subdivision_name','activity_address','care_type_literal','care_conditions_literal','care_profile_literal','service_codes','literal_hightech_licensed_profile']
 rows=[]
 for sid,g in active[active.literal_hightech_licensed_profile].groupby('source_record_id'):
  rows.append({'provider_id':'registry-hightech:'+sid,'source_record_id':sid,'service_code':'medical_hightech_licensed',
   'supply_status':'observed','source_id':json.dumps(sorted(set(g.source_id.astype(str))),ensure_ascii=False),
   'source_year':json.dumps(sorted(set(g.source_year.astype(str))),ensure_ascii=False),
   'service_basis':'literal_high_technology_care_in_licensed_type_not_verified_actual_delivery'})
 return pd.concat([official,pd.DataFrame(rows)],ignore_index=True),active[cols]


def higher_mapped_offers(physical):
 result=[]
 for kind,service in [('central_district_hospital_name_assertion','mapped_district_hospital_named'),('district_local_hospital_name_assertion','mapped_district_hospital_named'),('regional_hospital_name_assertion','mapped_regional_hospital_named')]:
  frame=physical[physical.source_medical_class.eq(kind)&physical.service_code.eq('mapped_hospital_service_unknown_level')].copy()
  frame['service_code']=service
  frame['provider_id']=frame.source_object_id.map(lambda x:'osm-med:'+x+':'+service)
  frame['evidence_quality']='mapped_hospital_order_from_name_only'
  frame['service_basis']='literal_institution_name_not_verified_specialties_or_tertiary_order'
  frame['function_family']='hospital_facility_presence'
  frame['counts_as_independent_service_channel']=False
  result.append(frame)
 return pd.concat(result,ignore_index=True)


def combined_np_supply(official,physical,reference):
 """One NP×service row; institution counts do not increase attractiveness."""
 rows=[]
 for r in official.to_dict('records'):
  rows.append({'source_record_id':r['source_record_id'],'service_code':r['service_code'],'supply_status':'observed',
   'source_id':clean(r['source_id']),'source_year':clean(r['source_year']),'evidence_quality':'registry_licensed_profile','service_basis':clean(r['service_basis']),
   'provider_evidence_id':r['provider_id'],'source_kind':'official_registry','source_object_id':None})
 for r in physical[physical.source_record_id.notna()&physical.supply_status.eq('proxy')].to_dict('records'):
  rows.append({'source_record_id':r['source_record_id'],'service_code':r['service_code'],'supply_status':'proxy','source_id':r['source_id'],
   'source_year':str(r['source_year']),'evidence_quality':r['evidence_quality'],'service_basis':r['service_basis'],
   'provider_evidence_id':r['provider_id'],'source_kind':'OSM','source_object_id':r['source_object_id']})
 evidence=pd.DataFrame(rows)
 out=[]
 for (sid,service),group in evidence.groupby(['source_record_id','service_code']):
  official_present=group.source_kind.eq('official_registry').any()
  out.append({'provider_id':'np-med:'+service+':'+sid,'source_record_id':sid,'service_code':service,
   'supply_status':'observed' if official_present else 'proxy','source_id':json.dumps(sorted({item for value in group.source_id for item in json_items(value)}),ensure_ascii=False),
   'source_year':json.dumps(sorted({item for value in group.source_year for item in json_items(value)}),ensure_ascii=False),'evidence_quality':'registry_with_optional_OSM_confirmation' if official_present else 'OSM_explicit_address_only',
   'source_records':len(group),'has_official_registry':bool(official_present),'has_mapped_OSM':bool(group.source_kind.eq('OSM').any()),
   'service_basis':json.dumps(sorted({item for value in group.service_basis for item in json_items(value)}),ensure_ascii=False),'location_precision':'settlement_point',
   'np_identity_basis':'accepted_census_record','actual_operational_status_verified':False,'observed_flow':False,'capacity_total':np.nan})
 out=pd.DataFrame(out).merge(reference[reference.source_record_id.notna()][['source_record_id','name','region','lat','lon','population_role','ordinary_spatial_2021']],on='source_record_id',how='left',validate='many_to_one').rename(columns={'name':'provider_name','lat':'site_lat','lon':'site_lon','region':'context_region'})
 out['context_region_basis']='strict_settlement_identity'
 out['local_supply_eligible']=True
 out['default_external_seed_eligible']=out.has_official_registry&~out.has_mapped_OSM
 out['default_external_seed_exclusion_reason']=np.where(out.has_mapped_OSM,'mapped_site_used_instead_of_settlement_centroid',np.where(~out.has_official_registry,'OSM_NP_aggregate_is_local_presence_only',''))
 return out,evidence


def dedup_candidates(physical):
 """Preserve possible node/way duplicates; do not silently merge institutions."""
 p=physical[physical.supply_status.eq('proxy')].drop_duplicates('source_object_id').copy()
 p['normalized_name']=p.source_name.map(normalize_name)
 pairs=[]
 for name,g in p[p.normalized_name.str.len().ge(5)].groupby('normalized_name'):
  if len(g)<2:continue
  xyz=sphere_xyz(g.site_lat,g.site_lon);tree=cKDTree(xyz)
  for i,j in tree.query_pairs(0.03/6371.0088):
   a=g.iloc[i];b=g.iloc[j]
   if a.source_object_id.split(':')[1]==b.source_object_id.split(':')[1]:continue
   if a.source_medical_class!=b.source_medical_class:continue
   pairs.append({'source_object_id_a':a.source_object_id,'source_object_id_b':b.source_object_id,'normalized_name':name,
    'distance_km':float(chord_km(np.linalg.norm(xyz[i]-xyz[j]))),'address_literal_equal':bool(clean(a.source_addr_full) and clean(a.source_addr_full)==clean(b.source_addr_full)),
    'removed_from_main_supply':False,'meaning':'possible_node_way_duplicate_not_verified_institution_identity'})
 return pd.DataFrame(pairs,columns=['source_object_id_a','source_object_id_b','normalized_name','distance_km','address_literal_equal','removed_from_main_supply','meaning'])


def coverage(reference,np_supply,physical):
 rows=[]
 for region,g in reference.groupby('region'):
  sid=set(g.source_record_id.dropna());ns=np_supply[np_supply.source_record_id.isin(sid)]
  ps=physical[physical.context_region.eq(region)&physical.supply_status.eq('proxy')]
  row={'region':region,'ordinary_spatial_np':int(g.ordinary_spatial_2021.sum()),'reference_np_with2021_id':int(g.source_record_id.notna().sum()),
   'np_with_registry':ns.loc[ns.has_official_registry,'source_record_id'].nunique(),'np_with_OSM_explicit_address':ns.loc[ns.has_mapped_OSM,'source_record_id'].nunique(),
   'mapped_objects_context_region':ps.source_object_id.nunique(),'mapped_objects_region_by_literal_or_strict_id':ps.loc[~ps.context_region_basis.eq('nearest_reference_point_context_only'),'source_object_id'].nunique(),
   'mapped_objects_region_by_nearest_context_only':ps.loc[ps.context_region_basis.eq('nearest_reference_point_context_only'),'source_object_id'].nunique(),
   'coverage_is_completeness_or_accuracy':False}
  for service in [BASIC,PHYSICIAN,UNSPECIFIED,'medical_inpatient','mapped_hospital_service_unknown_level','medical_hightech_licensed']:
   row[service+'_np']=ns.loc[ns.service_code.eq(service),'source_record_id'].nunique()
   row[service+'_mapped_objects']=ps.loc[ps.service_code.eq(service),'source_object_id'].nunique()
  rows.append(row)
 return pd.DataFrame(rows)


def save(frame,path):
 path.parent.mkdir(parents=True,exist_ok=True);frame.to_parquet(path.with_suffix('.parquet'),index=False,compression='zstd')


def build(osm_current,osm_history,official_supply,reference_path,legacy_path,output):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 reference=pd.read_parquet(reference_path);current=pd.read_parquet(osm_current);history=pd.read_parquet(osm_history)
 if not current.object_id.is_unique or not history.object_id.is_unique:raise ValueError('Nonunique OSM object IDs within snapshot')
 if set(current.source_snapshot_date.astype(str))!={'2026-10-19'}:raise ValueError('Unexpected current OSM snapshot')
 if set(history.source_snapshot_date.astype(str))!={'2021-01-01'}:raise ValueError('Unexpected history OSM snapshot')
 linked=attach_osm(current,reference,pd.read_parquet(legacy_path));save(linked,out/'osm_sites_with_identity_and_status')
 physical=physical_offers(linked);save(physical,out/'physical_sites')
 extra=higher_mapped_offers(physical);save(extra,out/'additional_functional_offers')
 official_sites=Path(official_supply).with_name('sites_matched.parquet')
 official,orders=higher_official_evidence(pd.read_parquet(official_supply),pd.read_parquet(official_sites));save(orders,out/'official_functional_order_evidence')
 combined,evidence=combined_np_supply(official,physical,reference);save(combined,out/'np_supply');save(evidence,out/'source_evidence')
 cov=coverage(reference,combined,physical);save(cov,out/'coverage_region');cov.to_csv(out/'coverage_region.csv',index=False)
 duplicates=dedup_candidates(physical);save(duplicates,out/'possible_osm_duplicates');duplicates.to_csv(out/'possible_osm_duplicates.csv',index=False)
 change=history[['object_id','medical_class','source_snapshot_date','inactive_source_assertion']].merge(current[['object_id','medical_class','source_snapshot_date','inactive_source_assertion']],on='object_id',how='outer',suffixes=('_2021','_2026'),indicator=True)
 change['change_is_verified_opening_or_closure']=False;save(change,out/'osm_snapshot_comparison')
 active=physical[physical.supply_status.eq('proxy')]
 summary={'source_objects_2021':len(history),'source_objects_2026':len(current),'source_healthcare_objects_2026':int(current.broad_function.eq('healthcare').sum()),
  'eligible_mapped_healthcare_objects':int(active.source_object_id.nunique()),'eligible_mapped_object_service_rows':len(active),
  'mapped_general_primary_object_count':int(active.loc[active.service_code.eq(BASIC),'source_object_id'].nunique()),
  'mapped_general_physician_object_count':int(active.loc[active.service_code.eq(PHYSICIAN),'source_object_id'].nunique()),
  'np_service_rows':len(combined),'np_with_any_offer':int(combined.source_record_id.nunique()),
  'hightech_licensed_np':int(combined.loc[combined.service_code.eq('medical_hightech_licensed'),'source_record_id'].nunique()),
  'additional_name_order_proxy_rows':len(extra),
  'regions_reference':len(cov),'regions_with_official_registry':int(cov.np_with_registry.gt(0).sum()),
  'regions_with_any_mapped_object_context':int(cov.mapped_objects_context_region.gt(0).sum()),
  'regions_with_any_mapped_object_literal_or_strict_id':int(cov.mapped_objects_region_by_literal_or_strict_id.gt(0).sum()),
  'possible_node_way_duplicate_pairs_not_silently_merged':len(duplicates),
  'inactive_source_objects':int(linked.lifecycle_exclusion_reason.ne('').sum()),
  'temporal_source_conflict_objects':int(linked.temporal_status.isin(['ended_before_snapshot','started_after_snapshot']).sum()),
  'observed_patient_flows':False,'capacity_used_as_weight':False,'nearest_np_used_as_identity':False,
  'OSM2021_is_current_function_observation':False,
  'inputs_sha256':{str(p):digest(p) for p in [osm_current,osm_history,official_supply,official_sites,reference_path,legacy_path]},
  'code_sha256':digest(Path(__file__))}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2));return summary


PUBLIC_RESTRICTED_RE=re.compile(r'\bфсин\b|\bуфсин\b|федеральн.{0,80}служб.{0,80}исполнени.{0,12}наказан|исправительн.{0,40}(?:колони|учреж|центр)|следственн.{0,12}изолятор',re.I)


def explicit_restricted_scope(name,organization=''):
 # A street/settlement called Voinskaya is not proof of a closed institution.
 return bool(PUBLIC_RESTRICTED_RE.search(clean(name)+' '+clean(organization)))


def correct_public_scope(health_root,official_supply,official_sites,reference_path,output):
 root=Path(health_root);out=Path(output);out.mkdir(parents=True,exist_ok=True)
 original_np=pd.read_parquet(root/'np_supply.parquet')
 physical=pd.read_parquet(root/'physical_sites.parquet').copy()
 sites=pd.read_parquet(official_sites)
 active=sites[sites.source_record_id.notna()&~sites.registered_exclusion_present.fillna(False)&~sites.source_year_conflict_with_inventory.fillna(False)].copy()
 active['explicit_restricted_access_signal']=[explicit_restricted_scope(a,b) for a,b in zip(active.subdivision_name,active.organization_name)]
 active['restriction_evidence']='literal_FSIN_or_correctional_institution_in_unit_or_organization_name'
 exploded=active.assign(service_code=active.service_codes.fillna('').str.split('|')).explode('service_code')
 exploded=exploded[exploded.service_code.ne('')]
 # Retain the original primary-scope exclusions; only this independently
 # demonstrated access error is newly removed.
 primary=exploded.service_code.isin([BASIC,PHYSICIAN])
 old_exclusion=exploded.restricted_access_signal.fillna(False)|exploded.pediatric_only_signal.fillna(False)|exploded.narrow_unit_name_ambiguity_signal.fillna(False)
 previously_eligible=exploded[~(primary&old_exclusion)].copy()
 public=previously_eligible[~previously_eligible.explicit_restricted_access_signal]
 public_keys=set(zip(public.source_record_id,public.service_code))
 restricted=previously_eligible[previously_eligible.explicit_restricted_access_signal]
 restricted_keys=set(zip(restricted.source_record_id,restricted.service_code))
 official,orders=higher_official_evidence(pd.read_parquet(official_supply),sites)
 remove=official.apply(lambda r:(r.source_record_id,r.service_code) in restricted_keys and (r.source_record_id,r.service_code) not in public_keys,axis=1)
 held_official=official[remove].copy();held_official['exclusion_reason']='all_source_support_for_this_NP_service_is_explicitly_restricted'
 official=official[~remove].copy()
 def operator_literal(value):
  t=tags(value)
  return ' '.join(clean(t.get(k)) for k in ['operator','operator:short','operator:full','official_name','short_name'])
 physical['explicit_restricted_access_signal']=[explicit_restricted_scope(n,operator_literal(t)) for n,t in zip(physical.source_name,physical.source_tags_json)]
 physical['supply_status_before_public_scope_check']=physical.supply_status
 mask=physical.explicit_restricted_access_signal&physical.supply_status.eq('proxy')
 physical.loc[mask,'supply_status']='excluded_restricted_contingent'
 physical['public_scope_exclusion_reason']=np.where(physical.explicit_restricted_access_signal,'literal_FSIN_or_correctional_institution_name_or_operator','')
 combined,evidence=combined_np_supply(official,physical,pd.read_parquet(reference_path))
 combined['source_public_scope_check']='known_explicit_restrictions_excluded_not_proof_of_universal_access'
 save(combined,out/'np_supply');save(physical,out/'physical_sites');save(evidence,out/'source_evidence')
 save(held_official,out/'held_official_np_service_offers');save(active[active.explicit_restricted_access_signal],out/'restricted_registry_rows')
 save(physical[physical.explicit_restricted_access_signal],out/'restricted_mapped_rows');save(orders,out/'official_functional_order_evidence')
 extra=higher_mapped_offers(physical);save(extra,out/'additional_functional_offers')
 cov=coverage(pd.read_parquet(reference_path),combined,physical);save(cov,out/'coverage_region');cov.to_csv(out/'coverage_region.csv',index=False)
 check=[]
 for sid,service in sorted(restricted_keys):
  q=public[public.source_record_id.eq(sid)&public.service_code.eq(service)]
  check.append({'source_record_id':sid,'service_code':service,'other_nonrestricted_source_rows':len(q),'NP_offer_retained_by_other_source':bool(((combined.source_record_id==sid)&(combined.service_code==service)).any())})
 save(pd.DataFrame(check),out/'public_scope_support_comparison')
 def pool(d):return set(zip(d.loc[d.supply_status.isin(['observed','proxy']),'source_record_id'],d.loc[d.supply_status.isin(['observed','proxy']),'service_code']))
 removed_keys=sorted(pool(original_np)-pool(combined));added_keys=sorted(pool(combined)-pool(original_np))
 if added_keys:raise ValueError('Access correction unexpectedly added NP supply')
 before_phys=pd.read_parquet(root/'physical_sites.parquet')
 old_counts=before_phys[before_phys.supply_status.eq('proxy')].groupby('service_code').size();new_counts=physical[physical.supply_status.eq('proxy')].groupby('service_code').size()
 summary={'input_health_frozen_unchanged':True,'restricted_registry_rows':int(active.explicit_restricted_access_signal.sum()),
  'mapped_object_service_rows_newly_excluded':int(mask.sum()),'mapped_objects_newly_excluded':int(physical.loc[mask,'source_object_id'].nunique()),
  'np_service_keys_removed':[{'source_record_id':a,'service_code':b} for a,b in removed_keys],
  'removed_official_np_service_rows':len(held_official),'new_admitted_np_service_rows':len(combined),
  'mapped_before':old_counts.to_dict(),'mapped_after':new_counts.to_dict(),
  'clinical_population_scope_is_not_verified_for_every_other_site':True,
  'hightech_np_after':int(combined.loc[combined.service_code.eq('medical_hightech_licensed'),'source_record_id'].nunique()),
  'inputs_sha256':{str(p):digest(p) for p in [root/'np_supply.parquet',root/'physical_sites.parquet',official_supply,official_sites,reference_path]},'code_sha256':digest(Path(__file__))}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2));return summary


def main():
 if len(sys.argv)>1 and sys.argv[1]=='correct-public-scope':
  p=argparse.ArgumentParser(description='Exclude only explicit restricted medical institutions; preserve source evidence')
  for flag in ['health-root','official-supply','official-sites','reference','output']:p.add_argument('--'+flag,type=Path,required=True)
  a=p.parse_args(sys.argv[2:]);correct_public_scope(a.health_root,a.official_supply,a.official_sites,a.reference,a.output);return
 p=argparse.ArgumentParser(description=__doc__)
 for flag in ['osm-current','osm-history','official-supply','reference','legacy','output']:p.add_argument('--'+flag,type=Path,required=True)
 a=p.parse_args();build(a.osm_current,a.osm_history,a.official_supply,a.reference,a.legacy,a.output)


if __name__=='__main__':main()

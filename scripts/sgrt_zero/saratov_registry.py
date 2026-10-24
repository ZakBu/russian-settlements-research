#!/usr/bin/env python3
"""Extract the entire Saratov TFOMS2021 primary PDF as a dated supplement.

Never modifies national frozen providers. Annual programme expiry is retained
literally, not interpreted as physical facility closure or current operation.
"""
import argparse,hashlib,json,re,sys,shutil
import numpy as np
from pathlib import Path
import pandas as pd
import pdfplumber
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_mass.medical import classify
from scripts.sgrt_zero.health import primary_unit_scope_flags as primary_scope_flags
from scripts.sgrt_mass.match import match_addresses,normalize_name,normalize_district,normalize_region
from scripts.sgrt_zero.health import explicit_restricted_scope,named_child_only_unit
URL='http://www.sartfoms.ru/spravka/archives/2021/list/TERREESTRMO2021_31.12.2021.pdf'
FIELDS=['registry_sequence','region_code','unique_registry_number','gis_oms_number','medical_registry_number','organization_name','organization_short_name','inn','kpp','ogrn','organization_oid','organization_type_literal','legal_form_code','legal_form_literal','ownership_code','ownership_literal','founder_literal','legal_address','legal_address_id','telephone','email','activity_address','activity_address_id','subdivision_name','subdivision_oid','care_type_literal','care_conditions_literal','care_profile_literal','inclusion_date_literal','exclusion_date_literal','exclusion_reason_literal']
def clean(s):return re.sub(r'\s+',' ',re.sub(r'-\s*\n\s*','-',str(s or ''))).strip()
def extract(pdf):
 rows=[];carry={};pdfpages=[]
 with pdfplumber.open(pdf) as doc:
  for pn,page in enumerate(doc.pages,1):
   tables=page.extract_tables({'snap_tolerance':1,'join_tolerance':1,'intersection_tolerance':1,'text_x_tolerance':.2,'text_y_tolerance':.2})
   n=0
   for table in tables:
    for rn,cells in enumerate(table,1):
     if len(cells)==7:cells=[None]*21+cells+[None]*3
     if len(cells)!=31:continue
     # Headers do not resemble literal clinical service rows.
     if cells[23] and 'Наименование структурного' in cells[23]:continue
     if cells[0] and 'п/п' in cells[0]:continue
     r={k:clean(v) for k,v in zip(FIELDS,cells)}
     r['source_table_cells_json']=json.dumps(cells,ensure_ascii=False)
     r['care_fields_inherited']=False
     r['activity_address_inherited']=not bool(r['activity_address'])
     for k in FIELDS[28:]:r[k+'_literal_from_grid']=r[k]
     # Merged organization/address cells are explicit table inheritance.
     # New organizations reset inherited clinical address.
     if r['organization_name'] and r['organization_name']!=carry.get('organization_name'):
      carry={}
     for k in FIELDS[:23]+FIELDS[28:]:
      if r[k]:carry[k]=r[k]
      elif k in carry:r[k]=carry[k]
     if not r['subdivision_name'] or not r['care_type_literal']:continue
     if not re.match(r'^1\.2\.643\.',r['subdivision_oid']):continue
     for k in ['organization_oid','subdivision_oid']:r[k]=r[k].replace(' ','')
     r['organization_oid_consistent_with_subdivision']=r['subdivision_oid'].startswith(r['organization_oid']+'.') if r['organization_oid'] else False
     r.update(source_page=pn,source_table_row=rn,source_id='SARATOV_TFOMS_2021_1231',source_year=2021,source_region_literal='Саратовская область',source_url=URL,observed_flow=False,current_operation_verified=False,source_year_not_current_2026=True)
     r['object_id']='saratov2021:'+hashlib.sha256(f'{pn}:{rn}:{r["subdivision_oid"]}:{r["activity_address"]}'.encode()).hexdigest()[:24]
     r['programme_membership_expiry_not_facility_closure']=bool(re.search(r'истечение срока.*территориальн',r['exclusion_reason_literal'],re.I))
     r['other_registry_exclusion']=bool(r['exclusion_date_literal']) and not r['programme_membership_expiry_not_facility_closure']
     r.update(primary_scope_flags(r));classes=classify(r)
     r['service_codes']='|'.join(c for c,b in classes);r['service_bases_json']=json.dumps(dict(classes),ensure_ascii=False)
     rows.append(r);n+=1
   pdfpages.append({'page':pn,'extracted_clinical_rows':n})
 d=pd.DataFrame(rows)
 return repair_organizations(d),pdfpages

def repair_organizations(d):
 # Page-spanning merged organization cells may not be bounded by the page's
 # table grid. Recover only through exact clinical-parent OID identity.
 orgcols=FIELDS[:21]+FIELDS[28:]
 orgmap=d[d.organization_name.ne('')].drop_duplicates('organization_oid').set_index('organization_oid',drop=False)
 for i,r in d.iterrows():
  parent=r.subdivision_oid.split('.0.')[0]
  d.at[i,'organization_oid_extracted_carried']=r.organization_oid
  d.at[i,'organization_name_extracted_carried']=r.organization_name
  if parent in orgmap.index:
   for k in orgcols:d.at[i,k]=orgmap.at[parent,k]
   d.at[i,'organization_oid_consistent_with_subdivision']=True
   d.at[i,'organization_identity_basis']='exact_parent_oid_dictionary'
  else:
   for k in orgcols:d.at[i,k]=''
   d.at[i,'organization_oid']=parent
   d.at[i,'organization_identity_basis']='parent_oid_known_organization_text_unresolved'
   d.at[i,'organization_oid_consistent_with_subdivision']=False
 for i,r in d.iterrows():
  flags=primary_scope_flags(r)
  child_named=bool(re.search(r'детск|педиатр',clean(r.subdivision_name),re.I))
  adult_profile=bool(re.search(r'\bтерапии\b|общей врачебной практике|общей практике',clean(r.care_profile_literal),re.I))
  flags['named_child_only_without_adult_profile']=named_child_only_unit(r.subdivision_name)
  if flags['named_child_only_without_adult_profile']:flags['pediatric_only_signal']=True
  for k,v in flags.items():d.at[i,k]=v
  classes=classify(r);d.at[i,'service_codes']='|'.join(c for c,b in classes);d.at[i,'service_bases_json']=json.dumps(dict(classes),ensure_ascii=False)
 d['explicit_restricted_scope']=d.apply(lambda r:explicit_restricted_scope(r.subdivision_name,r.organization_name),axis=1)
 return d

TYPE_PATTERNS=[('rail',r'(?:ж[/. -]*д\s*(?:ст(?:анция)?|разъезд)|железнодорожная\s+станция|станция|ст\.)'),('village',r'(?:село|с\.)'),('hamlet',r'(?:деревня|дер\.|д\.)'),('town',r'(?:город|г\.)'),('urban_settlement',r'(?:р\.\s*п\.|рабочий\s+поселок|пгт)'),('settlement',r'(?:поселок|пос\.|п\.)'),('farm',r'(?:хутор|х\.)')]

def literal_type_name(address):
 # A place-type token must start an address component, preventing street
 # abbreviations (house d.) from being treated as place identity.
 for part in str(address).split(','):
  part=part.strip()
  for kind,pattern in TYPE_PATTERNS:
   m=re.match('^'+pattern+r'\s+(.+)$',part,re.I)
   if m and re.search('[А-Яа-яЁёA-Za-z]',m.group(1)):return kind,normalize_name(m.group(1))
 return None,None

def census_type(value):
 s=clean(value).lower()
 if 'железнодорож' in s or 'станция' in s or 'разъезд' in s:return 'rail'
 if s=='село':return 'village'
 if s=='деревня':return 'hamlet'
 if s=='город':return 'town'
 if 'городского типа' in s or 'рабочий' in s:return 'urban_settlement'
 if s=='поселок' or s=='посёлок':return 'settlement'
 if s=='хутор':return 'farm'
 return None

def refine_typed_addresses(matched,reference):
 out=matched.copy();ref=reference.copy()
 ref['_name']=ref.name.map(normalize_name);ref['_region']=ref.region.map(normalize_region);ref['_district']=ref.district.map(normalize_district);ref['_type']=ref.settlement_type_2021.map(census_type)
 out['typed_address_refinement_applied']=False
 for i,r in out[out.match_status.eq('ambiguous')].iterrows():
  kind,name=literal_type_name(r.activity_address)
  if not kind:continue
  region=normalize_region(r.source_region_literal)
  districtparts=[p for p in r.activity_address.split(',') if re.search(r'район|р-н',p,re.I)]
  district=normalize_district(districtparts[0]) if len(districtparts)==1 else None
  pool=ref[ref['_name'].eq(name)&ref['_region'].eq(region)]
  if district:pool=pool[pool['_district'].eq(district)]
  pool=pool[pool['_type'].eq(kind)&pool.source_record_id.notna()]
  if len(pool)!=1:continue
  out.at[i,'source_record_id']=pool.iloc[0].source_record_id
  out.at[i,'match_status']='matched';out.at[i,'match_method']='exact_literal_name_region_district_and_settlement_type'
  out.at[i,'match_reason']='unique_literal_type_disambiguation_no_proximity';out.at[i,'candidate_count']=1;out.at[i,'matched_region']=region
  out.at[i,'typed_address_refinement_applied']=True
 return out


def historical_np_supply(evidence,reference):
 rows=[]
 for (sid,code),g in evidence.groupby(['source_record_id','service_code']):
  rows.append(dict(provider_id='np-med:'+code+':'+sid,source_record_id=sid,service_code=code,supply_status='proxy',source_id=json.dumps(['SARATOV_TFOMS_2021_1231']),source_year=json.dumps(['2021']),evidence_quality='official_registry_2021_explicit_care_address_not_current_operation',source_records=len(g),has_official_registry=True,has_mapped_OSM=False,service_basis=json.dumps(sorted(g.service_basis.unique()),ensure_ascii=False),location_precision='settlement_point',np_identity_basis='exact_literal_address_with_optional_type',actual_operational_status_verified=False,observed_flow=False,capacity_total=np.nan,historical_source_only=True,historical_supply_proxy=True,restriction_scope_unknown=bool(g.restriction_scope_unknown.all()),local_supply_eligible=True,default_external_seed_eligible=True,default_external_seed_exclusion_reason=''))
 out=pd.DataFrame(rows).merge(reference[reference.source_record_id.notna()][['source_record_id','name','region','lat','lon','population_role','ordinary_spatial_2021']],on='source_record_id',how='left',validate='many_to_one').rename(columns={'name':'provider_name','region':'context_region','lat':'site_lat','lon':'site_lon'})
 out['context_region_basis']='strict_settlement_identity';out['source_public_scope_check']='explicit_restrictions_excluded_unresolved_operator_scope_flagged'
 return out


def integrate_variant(base,supplement,output):
 output.mkdir(parents=True,exist_ok=True);a=pd.read_parquet(base/'np_supply.parquet');b=pd.read_parquet(supplement/'np_supply.parquet');original=a.copy();a['historical_source_only']=False
 rows=[]
 def items(v):
  try:return json.loads(v)
  except (ValueError,TypeError):return [str(v)]
 for _,g in pd.concat([a,b],ignore_index=True).groupby(['source_record_id','service_code'],sort=True):
  r=g.iloc[0].to_dict();r['source_id']=json.dumps(sorted({str(x) for v in g.source_id for x in items(v)}),ensure_ascii=False);r['source_year']=json.dumps(sorted({str(x) for v in g.source_year for x in items(v)}))
  r['service_basis']=json.dumps(sorted({str(x) for v in g.service_basis for x in items(v)}),ensure_ascii=False)
  r['has_official_registry']=bool(g.has_official_registry.any());r['has_mapped_OSM']=bool(g.has_mapped_OSM.any());r['historical_source_only']=bool(g.historical_source_only.all())
  r['saratov_historical_2021_evidence_present']=bool(g.historical_source_only.any());r['historical_supply_proxy']=r['historical_source_only'];
  if r['saratov_historical_2021_evidence_present']:r['evidence_quality']='dated_official_registry_2021_with_optional_current_source_not_verified_operation'
  r['restriction_scope_unknown']=bool(g.restriction_scope_unknown.fillna(False).all())
  r['supply_status']='observed' if g.supply_status.eq('observed').any() else 'proxy';r['default_external_seed_eligible']=r['has_official_registry'] and not r['has_mapped_OSM']
  r['default_external_seed_exclusion_reason']='mapped_site_used_instead_of_settlement_centroid' if r['has_mapped_OSM'] else ''
  r['source_records']=int(g.source_records.sum());rows.append(r)
 combined=pd.DataFrame(rows);combined.to_parquet(output/'np_supply.parquet',index=False)
 for name in ['physical_sites.parquet','additional_functional_offers.parquet','official_functional_order_evidence.parquet']:
  if (base/name).exists():shutil.copyfile(base/name,output/name)
 before=set(zip(original.source_record_id,original.service_code));after=set(zip(combined.source_record_id,combined.service_code))
 changes=pd.DataFrame([{'source_record_id':sid,'service_code':code,'change':'added_historical_2021_NP_offer'} for sid,code in sorted(after-before)])
 changes.to_parquet(output/'provider_pool_changes.parquet',index=False)
 meta={'base_np_sha256':hashlib.sha256((base/'np_supply.parquet').read_bytes()).hexdigest(),'np_supply_sha256':hashlib.sha256((output/'np_supply.parquet').read_bytes()).hexdigest(),'physical_sites_sha256':hashlib.sha256((output/'physical_sites.parquet').read_bytes()).hexdigest(),'physical_sites_unchanged':True,'new_np_service_keys':len(changes),'changed_services':changes.service_code.value_counts().to_dict(),'all_years_preserved':True,'national_frozen_unchanged':True,'source_year2021_not_current2026':True}
 (output/'summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));return meta

def audit_subdivision_fields(d):
 out=d.copy();address_parent=None;flags=[]
 for _,r in out.iterrows():
  parent=r.subdivision_oid.split('.0.')[0]
  inherited=bool(r.get('activity_address_inherited',False))
  conflict=bool(inherited and address_parent is not None and address_parent!=parent)
  if not inherited:address_parent=parent
  flags.append(conflict)
 out['address_inheritance_parent_oid_conflict']=flags
 out['care_fields_inherited']=False
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--pdf',type=Path,required=True);p.add_argument('--extracted-rows',type=Path);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--base-health',type=Path);p.add_argument('--combined-output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if a.extracted_rows:
  cached=pd.read_parquet(a.extracted_rows);d=repair_organizations(cached);pages=[{'page':int(pn),'extracted_clinical_rows':len(g)} for pn,g in d.groupby('source_page')]
 else:d,pages=extract(a.pdf)
 d=audit_subdivision_fields(d);d.to_parquet(a.output/'source_rows.parquet',index=False)
 ref=pd.read_parquet(a.reference);m=refine_typed_addresses(match_addresses(d,ref,address_col='activity_address',region_col='source_region_literal'),ref);m.to_parquet(a.output/'sites_matched_or_held.parquet',index=False)
 ev=[]
 for r in m.to_dict('records'):
  if pd.isna(r['source_record_id']) or r['other_registry_exclusion'] or r['explicit_restricted_scope'] or r['address_inheritance_parent_oid_conflict']:continue
  for code in r['service_codes'].split('|'):
   if not code:continue
   if code in ['medical_basic_primary','medical_physician_primary'] and any(r[k] for k in ['restricted_access_signal','pediatric_only_signal','narrow_unit_name_ambiguity_signal']):continue
   ev.append({k:r[k] for k in ['source_record_id','object_id','subdivision_name','activity_address','source_page','source_table_row','source_id','source_year','subdivision_oid','programme_membership_expiry_not_facility_closure']}|{'service_code':code,'service_basis':json.loads(r['service_bases_json'])[code],'restriction_scope_unknown':not r['organization_oid_consistent_with_subdivision'],'organization_identity_basis':r['organization_identity_basis'],'evidence_status':'official_registry_2021_not_current_2026','observed_flow':False})
 e=pd.DataFrame(ev);e.to_parquet(a.output/'service_evidence.parquet',index=False);historical_np_supply(e,ref).to_parquet(a.output/'np_supply.parquet',index=False)
 summary={'source_url':URL,'source_sha256':hashlib.sha256(a.pdf.read_bytes()).hexdigest(),'source_year':2021,'pages':pages,'source_rows':len(d),'organizations':int(d.organization_oid.nunique()),'matched_source_rows':int(m.source_record_id.notna().sum()),'unique_matched_np':int(m.source_record_id.nunique()),'np_services':e[['source_record_id','service_code']].drop_duplicates().service_code.value_counts().to_dict(),'programme_expiry_rows':int(d.programme_membership_expiry_not_facility_closure.sum()),'other_registry_exclusion_rows':int(d.other_registry_exclusion.sum()),'address_parent_oid_conflict_rows':int(d.address_inheritance_parent_oid_conflict.sum()),'typed_address_refinement_rows':int(m.typed_address_refinement_applied.sum()),'organization_oid_disagreement_rows':int((~d.organization_oid_consistent_with_subdivision).sum()),'not_integrated_in_frozen_national_run':True,'not_evidence_of_current_2026_operation':True}
 (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
 if a.base_health and a.combined_output:print(json.dumps(integrate_variant(a.base_health,a.output,a.combined_output),ensure_ascii=False))
if __name__=='__main__':main()

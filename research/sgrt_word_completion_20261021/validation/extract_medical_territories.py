#!/usr/bin/env python3
"""Read every non-summary sheet of official LO attachment610-O, retaining unresolved rows."""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
SOURCE=Path('/workspace/scratch/sgrt_validation/medical2024territoriesxls.xls')
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def clean(x):return re.sub(r'\s+',' ',str(x)).strip()
TYPES={'д':'деревня','дер':'деревня','деревня':'деревня','с':'село','село':'село','г':'город','город':'город','п':'посёлок','пос':'посёлок','поселок':'посёлок','гп':'пгт','пгт':'пгт','ст':'станция','станция':'станция','городской поселок':'пгт','городской посёлок':'пгт','рабочий поселок':'пгт'}
def locality(s):
 s=clean(s).replace('ё','е')
 # Keep address slices in source; they are never full-population settlement assignments.
 m=re.match(r'^(гп|пгт|г|д|дер|с|п|пос|ст)\.?\s*([А-ЯЁ][А-ЯЁа-яё0-9 -]*?)(?=\s*\(|,|$)',s)
 if m:return m.group(2).strip(),TYPES[m.group(1)],bool(re.search(r'ул\.|улиц|корп|бульвар|проспект',s,re.I))
 m=re.match(r'^(.+?),\s*(деревня|село|городской поселок|рабочий поселок|город|поселок|пгт|станция)(?:\s|$)',s,re.I)
 if m:return m.group(1).strip(),TYPES.get(m.group(2).lower(),m.group(2).lower()),False
 return s.split('(')[0].strip(),None,bool(re.search(r'ул\.|улиц|корп',s,re.I))
def noun_case_variants(s):
 # Only used after explicit geographical type: г. Всеволожска is an inflected noun,
 # unlike an adjectival label such as Всеволожская больница.
 n=norm(s);out={n}
 if n.endswith(('а','у','е')):out.add(n[:-1])
 if n.endswith('ы'):out.add(n[:-1]+'а')
 if n.endswith('я'):out.add(n[:-1]+'ь')
 return out

def provider_localities(provider,a,districtstem):
 evidence=[];tokens=[]
 typed=r'(?:^|[\s(;])(гп|пгт|г|город|д|дер|деревня|с|село|п|пос|поселок|ст|станция)(?:\.\s*|\s+)([А-ЯЁ][А-ЯЁа-яё0-9 -]*?)(?=[,);\n]|$)'
 for m in re.finditer(typed,provider):tokens.append((m.group(2).strip(),TYPES[m.group(1)],'explicit_typed_locality',True))
 # A literal settlement noun follows the service name directly. A preceding
 # adjective (Анисимовский ФАП) is deliberately not interpreted as a place.
 bare=r'(?:^|;\s*)(?:ФАП|Поликлиника|Врачебная амбулатория|Амбулатория)\s+([А-ЯЁ][А-ЯЁа-яё0-9 -]*?)(?=\s*\(|,|;|$)'
 for m in re.finditer(bare,provider):
  token=m.group(1).strip()
  tokens.append((token,None,'explicit_literal_locality_after_service',False))
 for name,typ,rule,inflected in tokens:
  names=noun_case_variants(name) if inflected else {norm(name)}
  pp=a[a['_name'].isin(names)]
  if typ is not None:
   accepted_types={norm(typ)}
   if typ=='посёлок':accepted_types.add(norm('пгт')) # generic п. is also used for urban settlements
   pp=pp[pp['_type'].isin(accepted_types)]
  if len(pp)>1:
   dm=pp.municipality_upper_2021.fillna('').map(norm).str.contains(districtstem,regex=False)
   if dm.any():pp=pp[dm]
  if len(pp)==1:evidence.append({'uid':pp.id.iloc[0],'literal':name,'type':typ,'rule':rule,'matched_axis_name':pp.name.iloc[0]})
 return evidence

def run():
 axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet');a=axis[axis.region.fillna('').str.contains('ленинград',case=False)].copy();a['_name']=a.name.map(norm);a['_type']=a.type.map(norm)
 source=pd.ExcelFile(SOURCE);rows=[];sheets=[]
 for sheet in source.sheet_names:
  d=source.parse(sheet,header=None).fillna('');is_summary=norm(sheet)=='свод'
  headers=[]
  for i,row in d.head(8).iterrows():
   found=[j for j,v in enumerate(row) if re.search(r'населен+н?ы[йи]\s+пун?кт',norm(v))]
   if found:headers.append((i,found[0]))
  if not headers:
   sheets.append({'sheet':sheet,'status':'HEADER_NOT_FOUND','rows':len(d)});continue
  hr,oc=headers[0]
  header=d.iloc[hr];pc=next((j for j,v in enumerate(header) if 'структурн' in norm(v)),None)
  if is_summary:sheets.append({'sheet':sheet,'status':'SUMMARY_RETAINED_AS_CONTROL_NOT_ADDITIVE','rows':len(d)});continue
  if pc is None:sheets.append({'sheet':sheet,'status':'PROVIDER_HEADER_NOT_FOUND','rows':len(d)});continue
  number=next((j for j in range(oc+1,len(header)) if 'численност' in norm(header.iloc[j])),None)
  municipal=next((j for j,v in enumerate(header) if 'районы проживан' in norm(v)),None)
  distance_columns={}
  for _,bandrow in d.iloc[hr+1:hr+5].iterrows():
   for j,v in enumerate(bandrow):
    text=norm(v)
    if text=='до 5 км':distance_columns[j]=(0,5)
    elif text=='от 5 до 10 км':distance_columns[j]=(5,10)
    elif text=='от 10 до 20 км':distance_columns[j]=(10,20)
    elif text=='от 20 до 50 км':distance_columns[j]=(20,50)
    elif text in {'50 км','более 50 км'} or str(v).strip().startswith('> 50'):distance_columns[j]=(50,None)
  provider='';mun='';legal='';count=0
  for i in range(hr+1,len(d)):
   row=d.iloc[i]
   if clean(row.iloc[pc]):provider=clean(row.iloc[pc])
   if municipal is not None and clean(row.iloc[municipal]):mun=clean(row.iloc[municipal])
   if clean(row.iloc[0]):legal=clean(row.iloc[0])
   original=clean(row.iloc[oc])
   if not original or original.lower().startswith(('итого','всего','населен','на 01.','на01.')):continue
   pop=pd.to_numeric(pd.Series([row.iloc[number] if number is not None else None]),errors='coerce').iloc[0]
   if pd.isna(pop):continue
   name,typ,partial=locality(original)
   candidates=a[a['_name'].eq(norm(name))]
   if typ is not None:candidates=candidates[candidates['_type'].eq(norm(typ))]
   districtstem=norm(sheet.split()[0])[:7]
   if len(candidates)>1:
    context=candidates.municipality_upper_2021.fillna('').map(norm)
    districtmatch=context.str.contains(districtstem,regex=False)
    if districtmatch.any():candidates=candidates[districtmatch]
   origin_id=candidates.id.iloc[0] if len(candidates)==1 else None
   status='literal_name_type_region_unique' if origin_id else ('ambiguous' if len(candidates)>1 else 'not_found')
   # Provider locality only from explicit typed text. Adjectival hospital names are not enough.
   provider_evidence=provider_localities(provider,a,districtstem)
   provider_ids={e['uid'] for e in provider_evidence}
   destination_id=next(iter(provider_ids)) if len(provider_ids)==1 else None
   bands=[bounds for j,bounds in distance_columns.items() if str(row.iloc[j]).strip() in {'1','1.0'}]
   rows.append({'source_id':'LO_610O_20231129_attachment','document_date':'2023-11-29','sheet':sheet,'excel_row_1based':i+1,'legal_organization':legal,'provider_literal':provider,'municipal_context_literal':mun,'origin_literal':original,'origin_name':name,'origin_type':typ,'origin_id':origin_id,'origin_link_status':status,'origin_candidates':len(candidates),'origin_is_partial_address_scope':partial,'attached_population_as_published':float(pop),'destination_id':destination_id,'provider_explicit_named_locality_candidates':len(provider_ids),'provider_identity_status':'explicit_literal_provider_locality_unique' if destination_id else 'unresolved_provider_site','provider_locality_evidence_json':json.dumps(provider_evidence,ensure_ascii=False),'published_distance_band_min_km':bands[0][0] if len(bands)==1 else None,'published_distance_band_max_km':bands[0][1] if len(bands)==1 else None,'published_distance_band_selected_count':len(bands),'distance_band_is_normative_not_measured_trip':True,'service_relation':'normative_primary_care_attachment_not_observed_trip','external_relation':bool(origin_id and destination_id and origin_id!=destination_id),'counts_are_census_population':False})
   count+=1
  sheets.append({'sheet':sheet,'status':'READ_ALL_ROWS','extracted_attachment_rows':count,'source_rows':len(d)})
 result=pd.DataFrame(rows);result.to_parquet(ROOT/'validation/medical_territories_2024_all_rows.parquet',index=False);result.to_csv(ROOT/'validation/medical_territories_2024_all_rows.csv.gz',index=False)
 receipt={'source_url':'https://lofoms.spb.ru/files/reshenie_2023_15_pril3_1.xls?1','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_bytes':SOURCE.stat().st_size,'all_sheet_count':len(source.sheet_names),'sheets':sheets,'extracted_rows':len(result),'origin_linked_rows':int(result.origin_id.notna().sum()),'explicit_provider_linked_rows':int(result.destination_id.notna().sum()),'external_linked_rows':int(result.external_relation.sum()),'unique_origin_ids':result.origin_id.nunique(),'explicit_provider_ids':result.destination_id.nunique(),'partial_address_rows':int(result.origin_is_partial_address_scope.sum()),'repeated_service_levels_or_providers_not_summed_as_unique_population':True,'unresolved_rows_retained':True,'used_for_training':False,'provider_link_rules':['explicit typed locality with exact axis noun or limited case-ending normalization','exact literal settlement name following service name; no adjectival derivation','homonyms require matching district context and uniqueness'],'adjectival_hospital_names_used_as_settlement_evidence':False,'distance_band_selected_counts':{str(k):int(v) for k,v in result.published_distance_band_selected_count.value_counts().items()},'distance_bands_are_normative_not_observed_trips':True}
 (ROOT/'validation/medical_territories_extraction_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()

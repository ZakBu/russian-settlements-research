#!/usr/bin/env python3
"""Extract named physical FAPs from an official regional 2025 workbook; no opening dates inferred."""
from pathlib import Path
import pandas as pd,json,hashlib
from link_osm_medical import norm,AXIS
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/medical_mass/udmurt_fap_internet_2025.xlsx');OUT=ROOT/'udmurt_official_2025';OUT.mkdir(exist_ok=True)
axis=pd.read_parquet(AXIS);region=axis[axis.region.str.contains('Удмурт',case=False,na=False)].copy();region['n']=region.name.map(norm)
rows=[]
for sheet,d in pd.read_excel(RAW,sheet_name=None,header=None).items():
 for i,r in d.iterrows():
  if pd.isna(pd.to_numeric(r.iloc[0],errors='coerce')):continue
  if not isinstance(r.iloc[2],str):continue
  locality=str(r.iloc[3]) if pd.notna(r.iloc[3]) else None;candidates=region[region.n.eq(norm(locality))]
  status='unresolved_source_locality';uid=None
  if len(candidates)==1:uid=candidates.id.iloc[0];status='exact_locality_unique_in_source_region'
  elif len(candidates)>1:status='homonym_requires_district_evidence'
  rows.append({'record_id':f'RMIAC18:2025:{sheet}:{i+1}','sheet_parent_hospital_group':sheet,'excel_row':i+1,'parent_organization':r.iloc[1],'physical_site_name':r.iloc[2],'source_locality':locality,'baseline_uid':uid,'link_status':status,'candidate_uids_json':json.dumps(candidates.id.tolist(),ensure_ascii=False),'site_type':'FAP_source_workbook_assertion','document_catalogue_year':2025,'planning_target_year':2026,'source_document_title':'Перечень ФАП требующих подключения к сети Интернет в 2026 году','source_scope':'selected_FAP_requiring_internet_not_full_regional_registry','operating_status':'unknown_not_confirmed_open','actual_opening_or_closing_dates_known':False,'capacity_known':False,'source_site_coordinates_known':False})
d=pd.DataFrame(rows);d.to_parquet(OUT/'physical_fap_inventory.parquet',index=False);d.to_csv(OUT/'physical_fap_inventory.csv',index=False)
f=axis[['id']].copy();counts=d[d.baseline_uid.notna()].groupby('baseline_uid').size();f['medical_official_udmurt_2025_internet_planning_fap_source_count']=f.id.map(counts).fillna(0).astype('int16');f['medical_official_absence_not_service_absence']=True;f.to_parquet(OUT/'settlement_features.parquet',index=False)
r={'rows':len(d),'parent_hospital_sheets':d.sheet_parent_hospital_group.nunique(),'linked_records':int(d.baseline_uid.notna().sum()),'positive_settlements':int((f.iloc[:,1]>0).sum()),'unresolved_records':int(d.baseline_uid.isna().sum()),'source_raw_sha256':hashlib.sha256(RAW.read_bytes()).hexdigest(),'scope':'Official 2025 catalogue, worksheet requests planned internet connection in 2026; incomplete selected network, no actual operation dates or coordinates','baseline_link_rule':'exact normalized locality name unique within Udmurt Republic; homonyms and spelling variants retained unresolved'}
(OUT/'extraction_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2))

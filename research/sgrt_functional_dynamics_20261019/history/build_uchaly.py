"""Curated level-specific school attachments from signed Uchaly 2025 act.

Physical branch ambiguity is preserved, never resolved by institutional hierarchy.
"""
from pathlib import Path
import argparse, hashlib, json
import pandas as pd

ROOT=Path(__file__).resolve().parent
URL='https://uralsk1.ucoz.ru/Obrazovanie/2025_postanovlenie_territorii.pdf'
DATE='2025-03-12'
# original PDF pages are 1-based, printed page = PDF page minus two.
GROUPS=[
 ('Малоказаккулово','МБОУ ООШ д. Малоказаккулово','Советская,36','grades_1_9','Малоказаккулово|Калуево|Амангильдино',13,27,True,'physical_school_site_explicit'),
 ('Уральск','МБОУ СОШ имени Исхакова А.С. с.Уральск','Советская,4','grades_10_11','Амангильдино|Калуево|Малоказаккулово',13,25,True,'physical_school_site_explicit'),
 ('Курама','МБОУ ООШ д.Курама','Соловьиная,9','grades_1_9','Курама|Каримово',13,26,True,'physical_school_site_explicit'),
 ('Комсомольск','МБОУ СОШ с.Комсомольск','Школьная,28','grades_10_11','Курама|Каримово',10,15,True,'physical_school_site_explicit'),
 ('Кунакбаево','МБОУ СОШ с.Кунакбаево','Школьная,1','general_education_level_not_further_separated','Юлдашево',10,16,False,'territorial_head_organization_attachment_physical_site_unresolved'),
 ('Озерный','МБОУ СОШ с.Озерный','Школьная,31','general_education_level_not_further_separated','Аслаево|Батталово',11,20,False,'territorial_head_organization_attachment_branch_ambiguity'),
]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 panel=pd.read_parquet(ROOT.parents[1]/'anchor_research_20261019/data/point_axis.parquet')
 candidates=panel[panel.region.str.contains('баш',case=False)&panel.municipality_upper_2021.fillna('').str.contains('Учалин')]
 def link(name):
  x=candidates[candidates.name.str.replace('ё','е').str.casefold()==name.replace('ё','е').casefold()]
  return x.iloc[0] if len(x)==1 else None
 rows=[];providers=[]
 for place,school,address,level,origins,page,num,physical,status in GROUPS:
  dp=link(place)
  providers.append(dict(provider_settlement=place,provider_name=school,school_level=level,street_address_literal=address,address_date=DATE,destination_uid=dp.id if dp is not None else None,site_status=status,source_url=URL,source_date=DATE,pdf_page=page,source_row=num,complete_district_inventory=False))
  for origin in origins.split('|'):
   p=link(origin)
   rows.append(dict(relation_id='UCH_SCHOOL_'+str(len(rows)+1).zfill(3),origin=origin,destination=place,origin_name=origin,provider_settlement=place,origin_uid=p.id if p is not None else None,destination_uid=dp.id if dp is not None else None,origin_link_status='exact_name_region_native_municipality_unique' if p is not None else 'not_in_frozen_panel_exact_context',destination_link_status='exact_name_region_native_municipality_unique' if dp is not None else 'not_in_frozen_panel_exact_context',region='Республика Башкортостан',municipality='Учалинский муниципальный район',function_group='education',service_level=level,relation_kind='normative_school_attachment' if physical else 'normative_organizational_territory_physical_site_unresolved',evidence_level='E2_normative_link_not_observed_trip',year=2025,source_id='UCH2025_03224',source_document_date=DATE,source_url=URL,object_id=school,locator=f'PDF_page{page}_printed{page-2}_row{num}',physical_service_destination_accepted=physical,external_origin=origin!=place,assignment_exclusive=False,branch_location_ambiguity=not physical,not_observed_flow=True,source_transcription='manual_read_of_signed_original_scanned_PDF',**{f'population_{y}':p[f'population_{y}'] if p is not None else None for y in [2002,2010,2021]}))
 ed=pd.DataFrame(rows);ed.to_csv(a.out/'uchaly_school_relations_2025.csv',index=False)
 pd.DataFrame(providers).to_csv(a.out/'uchaly_school_provider_sites_2025.csv',index=False)
 unresolved=ed[(ed.origin_uid.isna())|(ed.destination_uid.isna())];unresolved.to_csv(a.out/'uchaly_school_unresolved_identities.csv',index=False)
 physical=ed[ed.physical_service_destination_accepted];physical.to_csv(a.out/'uchaly_school_physical_relations_2025.csv',index=False)
 cases=[]
 for origin in ['Калуево','Амангильдино','Малоказаккулово']:
  p=link(origin);young=physical[(physical.origin==origin)&(physical.service_level=='grades_1_9')];old=physical[(physical.origin==origin)&(physical.service_level=='grades_10_11')]
  cases.append(dict(origin=origin,origin_uid=p.id if p is not None else None,school_grades1_9=young.iloc[0].destination,school_grades10_11=old.iloc[0].destination,census_population_2021=p.population_2021 if p is not None else None,medical_FAP_destination='Малоказаккулово' if origin=='Калуево' else None,medical_evidence='existing_medical_provider_report' if origin=='Калуево' else 'not_established_by_this_school_module',multi_function_interpretation='same_basic_school_and_FAP_center_different_upper_school_center' if origin=='Калуево' else 'school_level_split_no_medical_assumption',medical_source_publication_date='2025-01-09' if origin=='Калуево' else None,medical_date_basis='official_hospital_category_publication_timestamp_not_opening_date' if origin=='Калуево' else None,time_comparability='school_act_2025_03_12_vs_medical_publication_2025_01_09_not_simultaneous_measurement'))
 pd.DataFrame(cases).to_csv(a.out/'uchaly_multilevel_school_cases.csv',index=False)
 audit={'status':'PASS','relation_rows':len(ed),'physical_provider_accepted_rows':len(physical),'physical_external_rows':int(physical.external_origin.sum()),'school_provider_records':len(providers),'unresolved_endpoint_rows':len(unresolved),'new_exact_linked_NP_names':sorted(set(ed.loc[ed.origin_uid.notna(),'origin'])|set(ed.loc[ed.destination_uid.notna(),'destination'])),'excluded_from_physical_graph':['Юлдашево→Кунакбаево: no exclusion of local filial site established','Аслаево/Батталово→Озерный: explicit physical Batталовский branch exists on undated official school page; destination for specific grades unresolved'],'partial_selection':'only target groups in complete signed27schoolact, no districtwide completeness claim','medical_joint_time_limit':'FAP article publication2025-01-09 from official category index, schoolact2025-03-12; publication not opening/service start and not simultaneous measurement','source_raw_sha256':hashlib.sha256((ROOT/'raw/BA2025_order03224.pdf').read_bytes()).hexdigest(),'input_panel_sha256':hashlib.sha256((ROOT.parents[1]/'anchor_research_20261019/data/point_axis.parquet').read_bytes()).hexdigest()}
 assert len(ed)==13 and len(physical)==10 and int(physical.external_origin.sum())==8
 assert physical[physical.origin=='Калуево'].set_index('service_level').destination.to_dict()=={'grades_1_9':'Малоказаккулово','grades_10_11':'Уральск'}
 (a.out/'UCHALY_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()

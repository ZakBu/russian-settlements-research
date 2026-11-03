#!/usr/bin/env python3
"""Compare named operation cases with two fixed Ozon tariff-geography lists.

This is presence in a source list, never programme participation, approval,
absence of pickup operation, opening/closure, or a causal assignment.
"""
import csv,hashlib,json,re,subprocess,unicodedata
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
WORK=ROOT/'work/ecommerce_operations_20261104'
SHA22='136f558365b6057335a209c2b6370527f049a2498e66e2f155cf620f66bb1150'
SHA23='2914616d3ca4874ad2e69b2ea31302147088559d02fb46f0f46b152ed2aa30f0'
def norm(s):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s).casefold().replace('ё','е')).strip()
def main():
 pdf22=ROOT/'work/ecommerce_next_20261103/identification/tariff_20221022001416.pdf'
 pdf23=WORK/'sources/tariff_20230906185652.pdf'
 assert hashlib.sha256(pdf22.read_bytes()).hexdigest()==SHA22
 assert hashlib.sha256(pdf23.read_bytes()).hexdigest()==SHA23
 WORK.mkdir(parents=True,exist_ok=True);txt=WORK/'tariff2022_for_case_check.txt'
 subprocess.run(['pdftotext','-layout',str(pdf22),str(txt)],check=True)
 old=[]
 for page_n,page in enumerate(txt.read_text().split('\f'),1):
  for line in page.splitlines():
   line=line.strip()
   if not line or 'Населённый пункт' in line:continue
   cells=re.split(r'\s{2,}',line);assert len(cells)==2
   old.append({'row':len(old)+1,'page':page_n,'region':cells[0],'name':cells[1]})
 assert len(old)==2502
 with (WORK/'ozon_tariff_geography2023_all.csv').open() as f:new=list(csv.DictReader(f))
 assert len(new)==22325
 # Existing operation evidence is read from the published case table. Its
 # quality label is preserved; secondary republication is never promoted.
 with (HERE/'actual_points.csv').open() as f:actual=list(csv.DictReader(f))
 specs=[]
 for r in actual:
  specs.append({'case_name':r['name'],'region':r['region'],'operator':'Ozon','org_id':r['yandex_org_id'],'source_url':r['source_url'],'evidence_status':r['evidence_class'],'date':r['operation_evidence_date'],'source_record':str((HERE/'actual_points.csv').relative_to(ROOT)),'case_address':r['address']})
 specs.extend([
 {'case_name':'Серебрянский','region':'Ленинградская область','operator':'Ozon','org_id':'132706536016','source_url':'https://yandex.com/maps/org/ozon/132706536016/reviews/','evidence_status':'primary_review_and_embedded_point_address_manually_read_not_operation_validated_by_this_script','date':'2023-12-26','source_record':str((HERE/'systematic_review_sources_len.json').relative_to(ROOT)),'case_address':'Совхозная улица, 8','case_card_postal':'188284'},
 {'case_name':'Верхняя Троица','region':'Тверская область','operator':'Ozon','org_id':'96580335216','source_url':'https://yandex.com/maps/org/ozon/96580335216/reviews/','evidence_status':'primary_reviews_manually_read_not_operation_validated_by_this_script','date':'2023-10-30','source_record':str((HERE/'systematic_review_positive_extracts_nn_tver.csv').relative_to(ROOT)),'case_address':'Центральная улица, 1'},
 {'case_name':'Толмачёво','region':'Ленинградская область','operator':'Wildberries','org_id':'46722379084','source_url':'https://yandex.ru/maps/org/wildberries/46722379084/reviews/','evidence_status':'primary_review_case_different_platform_from_Ozon_programme','date':'2024-07-29','source_record':str((HERE/'destination_change_sources.json').relative_to(ROOT)),'case_address':'улица Толмачёва, 7'},
 {'case_name':'Верхнепашино','region':'Красноярский край','operator':'Wildberries','org_id':'','source_url':'https://ngs24.ru/text/gorod/2025/10/20/76079580/','evidence_status':'operator_and_customer_reports_in_platform_advertisement_different_platform_from_Ozon_programme','date':'2025-10-20','source_record':str((HERE/'new_routes_sources.json').relative_to(ROOT)),'case_address':'почтовое отделение 663148'}])
 out=[]
 for s in specs:
  old_all=[r for r in old if norm(r['name'])==norm(s['case_name'])]
  new_all=[r for r in new if norm(r['name_without_type2023'])==norm(s['case_name'])]
  a=[r for r in old_all if norm(r['region'])==norm(s['region'])]
  b=[r for r in new_all if norm(r['region2023'])==norm(s['region'])]
  source=ROOT/s['source_record']
  out.append({'case_name':s['case_name'],'case_region':s['region'],'case_operator':s['operator'],'case_org_id':s['org_id'],'case_address':s['case_address'],'case_card_postal':s.get('case_card_postal',''),'operation_evidence_status':s['evidence_status'],'operation_evidence_date_kind':'dated_report_not_opening_date','operation_evidence_date':s['date'],'operation_source_url':s['source_url'],'operation_local_source':s['source_record'],'operation_local_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else '',
   'list2022_same_name_region_rows_n':len(a),'list2022_row_ids':'|'.join(str(r['row']) for r in a),'list2022_pages':'|'.join(str(r['page']) for r in a),'list2022_names':'|'.join(r['name'] for r in a),'list2022_type_or_index_available':False,
   'list2023_same_name_region_rows_n':len(b),'list2023_row_ids':'|'.join(r['row2023_n'] for r in b),'list2023_pages':'|'.join(r['pdf_page'] for r in b),'list2023_typed_names':'|'.join(r['name2023'] for r in b),'list2023_postal_indices':'|'.join(r['postal_index2023'] for r in b),'list2023_same_name_other_regions':'|'.join(sorted(set(r['region2023'] for r in new_all if r not in b))),
   'presence_meaning':'Exact region and normalized complete name after explicit leading-type removal in 2023; not platform participation or operation. No match means no matching source row, not no pickup.','crossyear_identity_proven_by_list_comparison':False,'tariff_participation_proven':False,'pdf2022_sha256':SHA22,'pdf2023_sha256':SHA23})
 with (HERE/'case_programme_presence.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(out[0]),lineterminator='\n');w.writeheader();w.writerows(out)
 print(json.dumps([{'case':r['case_name'],'operator':r['case_operator'],'rows2022':r['list2022_same_name_region_rows_n'],'rows2023':r['list2023_same_name_region_rows_n'],'postal2023':r['list2023_postal_indices']} for r in out],ensure_ascii=False,indent=2))
if __name__=='__main__':main()

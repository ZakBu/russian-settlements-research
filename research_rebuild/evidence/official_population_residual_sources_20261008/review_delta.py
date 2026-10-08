from pathlib import Path
import json,hashlib,subprocess,gzip,re
import pandas as pd,xlrd
O=Path(__file__).resolve().parent
P=O/'leningrad_2010_official_archived.pdf'
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
d=pd.read_csv(O/'explicit_primary_and_old_selected_mapping.csv.gz')
d=d[d.old_quality.fillna('').str.startswith('secondary_confidentiality')].copy()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).casefold().replace('ё','е').replace('ѐ','е')).strip()
allroster=pd.concat([pd.read_csv(O/'parsed/leningrad_2010_explicit_locality_values_ge100.csv.gz'),pd.read_csv(O/'parsed/leningrad_2010_named_localities_without_values.csv.gz')],ignore_index=True)
for page,line,name in [(41,28,'Ладожский трудпосёлок'),(65,15,'Большая Пустомержа'),(92,32,'Дом отдыха Живой Ручей')]:
 allroster.loc[(allroster.page==page)&(allroster.line==line),'name_raw']=name
T={'г.':'город','г.п.':'пгт','дер.':'деревня','с.':'село','пос.':'поселок','п.ст.':'поселок','хут.':'хутор','корд.':'кордон','мест.':'местечко'}
fullkeys=allroster.apply(lambda r:(T.get(r.type_raw,norm(r.type_raw)),norm(r.name_raw)),axis=1).value_counts()
for r in d.to_dict('records'):
 assert fullkeys[(T[r['type_raw']],norm(r['name_raw']))]==1

s=pd.read_parquet(S).set_index('source_record_id'); books={};witness=[]
for r in d.to_dict('records'):
 old=s.loc[r['old_source_record_id']];p=Path('/workspace/settlements-raw')/r['old_source_file']
 if p not in books:books[p]=xlrd.open_workbook(p)
 sh=books[p].sheet_by_name(r['old_source_sheet']); row=int(r['old_source_row']); vals=sh.row_values(row-1)
 assert str(vals[4]).strip()==str(old.source_name_raw).strip(),(row,vals[4],old.source_name_raw)
 assert float(vals[5])==float(r['old_population'])==float(old.population)
 assert old.census_year==2010 and old.region_raw=='ленинградская'
 assert r['official_all_roster_key_count']==r['selected_key_count']==1
 assert r['independent_poppler_count_match']
 assert int(r['population'])==int(r['men'])+int(r['women'])
 witness.append({'old_source_record_id':r['old_source_record_id'],'raw_source_path':str(p),'raw_source_sha256':sha(p),'source_sheet':r['old_source_sheet'],'one_based_row':row,'raw_caption':vals[4],'raw_population_cell':vals[5],'official_source_record_id':r['official_source_record_id'],'official_name':r['name_raw'],'official_type':r['type_raw'],'official_P':r['population'],'official_M':r['men'],'official_F':r['women'],'official_page':r['page'],'official_line':r['line'],'official_poppler_raw_line':r['independent_poppler_raw_line']})
# This review uses the full official roster (including presence-only rows), not only explicit-valued candidates.
d['decision_status']='accepted_population_publication_binding';d['population_admission_basis']='same2010_census_unique_name_type_region_in_full_official_roster_and_all_selected_competitors_independent_source_cell_readback';d['census_year']=2010;d['official_publication_year']=2012;d['new_population']=d.population;d['new_population_value_quality']='reviewed_primary_reported_value';d['old_source_values_retained']=True;d['application_status']='reviewed_delta_not_applied'
d.to_csv(O/'reviewed_primary_override_delta_512.csv.gz',index=False,compression='gzip');pd.DataFrame(witness).to_csv(O/'old_raw_workbook_cells_and_official_readback_512.csv.gz',index=False,compression='gzip')
title=subprocess.check_output(['pdftotext','-f','1','-l','2','-layout',str(P),'-']).decode();assert '14 октября 2010 года' in title and '100 и более человек' in title
(O/'source_census_year_and_publisher_context.txt').write_text(title)
# Preserve the known wrapped source names; these three fall outside the reviewed512 delta.
repairs=[{'page':41,'line':28,'parsed_name':'трудпосёлок','correct_complete_source_name':'Ладожский трудпосёлок','source_prefix_line':'Ладожский','reason':'PDF name wrapped on two extracted lines'}, {'page':65,'line':15,'parsed_name':'Пустомержа','correct_complete_source_name':'Большая Пустомержа','source_prefix_line':'Большая','reason':'PDF name wrapped on two extracted lines'}, {'page':92,'line':32,'parsed_name':'Ручей"','correct_complete_source_name':'Дом отдыха "Живой Ручей"','source_prefix_line':'Дом отдыха "Живой','reason':'PDF name wrapped on two extracted lines'}]
(O/'wrapped_source_names_corrections.json').write_text(json.dumps(repairs,ensure_ascii=False,indent=2)+'\n')
receipt={'status':'reviewed_512_primary_population_override_delta_ready_for_root_integration_no_selected_mutation','method': 'Unique normalized exact name + explicit type + census region across full2929 official locality roster including2241 NULL rows and all2945 selected2010 rows; 512 original XLS captions/population cells read independently by exact source ID/sheet/one-based row; all512 official P/M/F independently crossread from PDF via Poppler. Names/population equality alone were not used to prove scope: exact locality type,2010 source date,region grain and all-competitor uniqueness checked. Source municipal and settlement-group contexts retained. No future2012 census value used.', 'reviewed_rows':len(d),'old_population_sum':int(d.old_population.sum()),'new_primary_population_sum':int(d.population.sum()),'delta':int(d.official_minus_old_delta.sum()),'official_region_control':1716868,'current_region_selected_sum':int(s[(s.census_year==2010)&(s.region_raw=='ленинградская')].population.sum()),'projected_new_region_selected_sum':int(s[(s.census_year==2010)&(s.region_raw=='ленинградская')].population.sum()+d.official_minus_old_delta.sum()),'projected_remaining_region_deficit':1835,'raw_workbook_rows_verified':len(witness),'source_census_date':'2010-10-14','publication_date':'2012-04-23','source_date_evidence':'PDF physical page2 expressly says official statistical data obtained during 14 October2010 census; >100 values are concrete resident counts. PDF page1 title: Итоги Всероссийской переписи населения2010 года;2012 is publication year.','protected_raw_counts_separate':True,'null_source_presence_rows':2241,'unallocated_source_population':54199,'wrapped_name_repairs_outside_reviewed_delta':repairs,'inputs':{str(S):sha(S),str(P):sha(P),**{str(p):sha(p) for p in books}},'outputs':{}}
assert len(d)==512 and receipt['delta']==10478 and receipt['projected_new_region_selected_sum']==1715033
for name in ['reviewed_primary_override_delta_512.csv.gz','old_raw_workbook_cells_and_official_readback_512.csv.gz','source_census_year_and_publisher_context.txt','wrapped_source_names_corrections.json']:
 p=O/name;receipt['outputs'][name]={'bytes':p.stat().st_size,'sha256':sha(p)}
(O/'review_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['outputs','wrapped_name_repairs_outside_reviewed_delta','inputs']},ensure_ascii=False,indent=2))

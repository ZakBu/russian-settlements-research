import json,gzip,re,hashlib
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
O=Path(__file__).parent;p=O/'own_population_template_expansion.json.gz';t=json.load(gzip.open(p,'rt'))['expandtemplates']['wikitext'];rows=[]
for title,html in re.findall(r'== (.*?) ==\n(.*?)(?=\n== |\Z)',t,re.S):
 soup=BeautifulSoup(html,'html.parser');cells=[]
 for tr in soup.find_all('tr'):
  th=tr.find_all('th');td=tr.find_all('td')
  if th:heads=th
  elif td:
   for h,d in zip(heads,td):
    year=re.match(r'\d{4}',h.get_text());pop=re.sub(r'[^0-9]','',d.get_text())
    if year and pop:cells.append({'year':int(year[0]),'population':int(pop),'header':str(h)})
 census=[v for v in cells if v['year']==2002 and 'перепись населения 2002' in v['header']]
 status='no_literal_2002_own_census_cell_with_reference'
 if census:status='own_secondary_2002_census_observed_but_ordinary_native02_upgrade_available_no_duplicate_qualified_credit'
 rows.append({'own_title':title,'source_archive':str(p),'source_archive_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'own_table_caption':soup.caption.get_text() if soup.caption else '', 'own_population_cells_json':json.dumps(cells,ensure_ascii=False),'qualified_2002_cells_json':json.dumps(census,ensure_ascii=False),'qualified_admission_status':status,'native2002_credit':0,'qualified_credit_new_source_IDs':0,'population_primary_reference_verified':False,'publisher_reference_is_secondary_citation_not_verified_primary':True})
pd.DataFrame(rows).to_csv(O/'qualified_sidecar_source_review.csv.gz',index=False,compression='gzip')
pd.DataFrame(columns=['trajectory_id','year','population_source_value','native_source_record_id','population_quality','source_locator']).to_csv(O/'accepted_qualified_physical_observations.csv',index=False)
pd.DataFrame(columns=['source_record_id','year','population_source_value','population_quality','native_current_source_record_id','trajectory_id']).to_csv(O/'accepted_qualified_native_source_ID_credit_union.csv',index=False)
(O/'qualified_sidecar_receipt.json').write_text(json.dumps({'status':'qualified_secondary_own_table_review_complete_separate_from_native_application','own_population_tables_reviewed':len(rows),'new_qualified_paths':0,'new_native2002_qualified_credit':0,'reason':'Only Хатуей carries an explicit2002 census-referenced own table; native Старый Урух source row provides ordinary upgrade. Other3 have no2002 observation. No missing years synthesized.','source_review_sha256':hashlib.sha256((O/'qualified_sidecar_source_review.csv.gz').read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
print([(r['own_title'],r['qualified_admission_status']) for r in rows])

from pathlib import Path
from docx import Document
import pandas as pd,json,re
from link_primary2010 import context
ROOT=Path(__file__).resolve().parent;O=ROOT/'tver';f=pd.read_parquet(O/'primary_source_NP_inventory.parquet');doc=Document('/workspace/scratch/sgrt_demography2010/tver_extracted/pub08-02.docx')
counts={};zeros={}
for table_no,col,store in [(3,4,counts),(7,1,zeros)]:
 for row in doc.tables[table_no]._tbl.tr_lst:
  cc=[' '.join(c.xpath('.//w:t/text()')).strip()for c in row.tc_lst]
  if len(cc)>col and re.search(r'[А-Яа-яЁё]',cc[0]) and cc[col].isdigit():store[context(cc[0])]=int(cc[col])
rural=~f.settlement_type.isin(['город','пгт']);checks=[]
for county,g in f[rural].groupby('official_county'):
 key=context(county);nnull=int(g.primary_population.isna().sum());checks.append(dict(county=county,parsed_NP=len(g),source_NP=counts.get(key),parsed_dash_NULL=nnull,source_zero= zeros.get(key),count_matches=len(g)==counts.get(key),zero_count_matches=nnull==zeros.get(key)))
c=pd.DataFrame(checks);assert len(c)==36 and c.count_matches.all() and c.zero_count_matches.all();assert len(f)==9583 and f.primary_population.sum()==1353392 and f.primary_population.dropna().ge(0).all()
f['derived_zero_from_exhaustive_same_scope_controls']=f.primary_population.isna() & f.raw_population.eq('-');f['population_2010_with_control_derived_zero']=f.primary_population.mask(f.derived_zero_from_exhaustive_same_scope_controls,0);f['derived_zero_requires_root_review']=f.derived_zero_from_exhaustive_same_scope_controls
f.to_parquet(O/'primary_source_NP_inventory.parquet',index=False);f.to_csv(O/'primary_source_NP_inventory.csv.gz',index=False);c.to_parquet(O/'source_district_count_zero_controls.parquet',index=False)
r={'source_total_population':1353392,'numeric_settlement_population_sum':int(f.primary_population.sum()),'same_census_slice':'2010-10-14','same_grain':'physical urban and rural settlements','count_source_table_1based':4,'zero_count_source_table_1based':8,'parsed_all_settlements':9583,'source_all_settlements':9583,'district_controls':36,'all_district_NP_counts_match':True,'all_district_zero_counts_match':True,'derived_zero_rows':int(f.derived_zero_from_exhaustive_same_scope_controls.sum()),'derivation':'Exhaustive disjoint physical NP set, exact integer population sum equals same-scope regional total, missing values nonnegative => each missing value is zero; independently every district missing count equals explicit without-population control.','raw_primary_population_preserved_NULL':True,'model_override_requires_root_review':True};(O/'derived_zero_proof_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r)

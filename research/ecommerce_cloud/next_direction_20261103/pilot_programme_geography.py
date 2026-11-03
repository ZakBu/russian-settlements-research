#!/usr/bin/env python3
"""Audit named programme territories. No identities, treatment or openings inferred."""
import hashlib,json,re,unicodedata
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
WORK=ROOT/'work/ecommerce_next_20261103/identification'
AXIS=ROOT/'work/sources/research/ecommerce_settlement_20261024/national/national_target_source2021.parquet'
REGIONS={'Тверская область':'тверская','Краснодарский край':'краснодарский','Нижегородская область':'нижегородская','Республика Саха (Якутия)':'саха якутия'}
def norm(s):
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 source=WORK/'eligibility_20221022_rows.csv';a=pd.read_parquet(AXIS);a['name_key']=a.name_2021.map(norm)
 s=pd.read_csv(source);s['name_key']=s.name_source.map(norm);assert len(s)==2502
 assert a.source_record_id_2021.is_unique
 repeated=s.groupby(['region_source','name_key']).size()
 rows=[];candidates=[];summaries=[]
 for source_reg,base_reg in REGIONS.items():
  g=a[a.region_2021.eq(base_reg)];p=s[s.region_source.eq(source_reg)]
  for r in p.itertuples():
   matches=g[g.name_key.eq(r.name_key)];n=len(matches);reps=int(repeated.loc[(source_reg,r.name_key)])
   status='repeated_source_name' if reps>1 else 'no_exact_name' if n==0 else 'multiple_exact_names' if n>1 else 'single_exact_name_candidate_only'
   row={'row_n':r.row_n,'pdf_page':r.pdf_page,'region_source':source_reg,'name_source':r.name_source,'source_pair_rows_n':reps,'exact_base_candidates_n':n,'status':status,'confirmed_identity':False}
   if n==1:
    q=matches.iloc[0];row.update(candidate_id=q.source_record_id_2021,candidate_type=q.type_2021,candidate_district=q.district_2021,candidate_population2021=q.population_2021,candidate_population2010=q.population_2010,candidate_population2002=q.population_2002)
   rows.append(row)
   for q in matches.itertuples():
    candidates.append({'row_n':r.row_n,'region_source':source_reg,'name_source':r.name_source,'candidate_id':q.source_record_id_2021,'name_2021':q.name_2021,'type_2021':q.type_2021,'district_2021':q.district_2021,'population_2021':q.population_2021,'population_2010':q.population_2010,'population_2002':q.population_2002,'candidate_rule':'exact_full_name'})
  rr=[r for r in rows if r['region_source']==source_reg];u=[r for r in rr if r['status']=='single_exact_name_candidate_only']
  summaries.append({'region_source':source_reg,'base_settlements_n':len(g),'source_rows_n':len(p),'source_distinct_names_n':p.name_key.nunique(),'single_exact_name_candidate_only_rows_n':len(u),'multiple_exact_names_rows_n':sum(r['status']=='multiple_exact_names' for r in rr),'repeated_source_name_rows_n':sum(r['status']=='repeated_source_name' for r in rr),'no_exact_name_rows_n':sum(r['status']=='no_exact_name' for r in rr),'single_candidates_population2021_below1000_n':sum(r['candidate_population2021']<1000 for r in u),'single_candidates_population2021_1000_to3500_n':sum(1000<=r['candidate_population2021']<=3500 for r in u),'single_candidates_population2021_above3500_n':sum(r['candidate_population2021']>3500 for r in u),'confirmed_identities_n':0})
 # Explicit stress tests: alternative wording is displayed, never substituted.
 alternatives={('Нижегородская область','Тарасиха'):['Тарасиха','станции Тарасиха'],('Тверская область','Чуприяновка'):['"Чуприяновка"'],('Нижегородская область','Селекционной Станции сельский'):['Селекционной станции'],('Краснодарский край','Центральной Усадьбы свх Восток'):['Центральной Усадьбы совхоза Восток']}
 diagnostic=[]
 for (reg,name),names in alternatives.items():
  for q in a[a.region_2021.eq(REGIONS[reg])&a.name_2021.isin(names)].itertuples():
   diagnostic.append({'region_source':reg,'name_source':name,'candidate_id':q.source_record_id_2021,'name_2021':q.name_2021,'type_2021':q.type_2021,'district_2021':q.district_2021,'population_2021':q.population_2021,'population_2010':q.population_2010,'population_2002':q.population_2002,'identity_accepted':False})
 assert len(rows)==258 and len(candidates)==580
 assert sum(r['status']=='single_exact_name_candidate_only' for r in rows)==173
 assert sum(r['status']=='multiple_exact_names' for r in rows)==63
 assert sum(r['status']=='repeated_source_name' for r in rows)==17
 assert sum(r['status']=='no_exact_name' for r in rows)==5
 assert len(diagnostic)==5 and not any(r['identity_accepted'] for r in diagnostic)
 pd.DataFrame(rows).to_csv(OUT/'programme_pilot_row_disposition.csv',index=False)
 pd.DataFrame(candidates).to_csv(OUT/'programme_pilot_exact_candidates.csv',index=False)
 pd.DataFrame(summaries).to_csv(OUT/'programme_pilot_summary.csv',index=False)
 pd.DataFrame(diagnostic).to_csv(OUT/'programme_pilot_wording_stress_tests.csv',index=False)
 pd.DataFrame(rows).query("status == 'single_exact_name_candidate_only'").query('candidate_population2021 < 1000 or candidate_population2021 > 3500').to_csv(OUT/'programme_pilot_population_flags.csv',index=False)
 pins={'inputs':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in [source,AXIS,WORK/'tariff_20221022001416.pdf']], 'normalization':'Unicode NFKC; casefold; ё→е; collapse whitespace. No punctuation/type removal; no fuzzy/nearest/geocoding.','source_snapshot':'2022-10-22T00:14:16Z','population_year':2021,'confirmed_identities':0,'regions':REGIONS,'diagnostic_population_interval':[1000,3500],'interval_is_not_verified_assignment_variable':True}
 (OUT/'programme_pilot_inputs.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n')
 print(pd.DataFrame(summaries).to_string(index=False)); print('Exact candidate rows:',len(candidates))
if __name__=='__main__':main()

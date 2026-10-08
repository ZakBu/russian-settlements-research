from pathlib import Path
import pandas as pd,json,xlrd,hashlib
O=Path(__file__).parent;D=pd.read_csv(O/'candidate_constituent_credit_union.csv',keep_default_na=False);books={};proof=[]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for r in D[D.census_year.isin([2002,2010])].itertuples():
 if not r.source_file.endswith('.xls'):continue
 if r.source_file not in books:books[r.source_file]=xlrd.open_workbook(r.source_file)
 sn,n=r.source_row_locator.split('!row_1based=');b=books[r.source_file];s=b.sheet_by_index(0) if sn=='0' else b.sheet_by_name(sn);rr=s.row_values(int(float(n))-1)
 if r.census_year==2010:
  if sn=='Урал':ix=4;value=int(rr[7])
  elif 'Belg_Bryan_Vlad' in r.source_file:ix=3;value=int(rr[4])
  else:ix=4;value=int(rr[5])
 else:
  ix=next(i for i,z in enumerate(rr) if isinstance(z,str) and r.settlement_name.lower().replace('ё','е') in z.lower().replace('ё','е'));value=int(float(rr[ix+1]))
 assert value==r.population,(r.source_record_id,value,r.population)
 assert sha(r.source_file)==r.source_file_sha256
 proof.append({'group':r.group,'source_record_id':r.source_record_id,'year':r.census_year,'raw_original_file':r.source_file,'raw_original_sha256':r.source_file_sha256,'raw_locator':r.source_row_locator,'raw_atomic_label':str(rr[ix]),'raw_value':value,'selected_value':r.population,'source_quality':r.source_population_quality,'raw_original_row_first_columns_json':json.dumps(rr[:11],ensure_ascii=False),'selected_values_unmodified':True})
pd.DataFrame(proof).to_csv(O/'original_atomic_raw_row_bindings.csv',index=False)
g=pd.read_csv(O/'candidate_group_observations.csv');edges=[]
for group,x in g.groupby('group'):
 for a,b in [(2002,2010),(2010,2021)]:edges.append({'group':group,'from_observation_id':x[x.census_year.eq(a)].iloc[0].observation_id,'to_observation_id':x[x.census_year.eq(b)].iloc[0].observation_id,'relation':'complete_published_city_territorial_hierarchy_trace','ordinary_same_place':False,'boundary_comparability':'UNKNOWN','candidate_only':True,'exact_annexation_roster_claimed':False,'event_relations_effective_date':'UNKNOWN'})
pd.DataFrame(edges).to_csv(O/'candidate_scope_edges.csv',index=False);p=O/'candidate_receipt.json';r=json.loads(p.read_text());r['all_original_xls_atomic_rows_reopened']=len(proof);r['2010_closure_evidence']='Complete original regional published raw ruralNP block until nextcity, with selected primary owncity (and published urban subordinates). Original census2002 subordinate hierarchy and census2021allNP parent controls retained. Secondary confidentiality-protected values unchanged; source control disagreements retained without allocation.';r['outputs']={p.name:sha(p) for p in O.glob('*.csv')};p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('verified',len(proof),'bytes',sum(p.stat().st_size for p in O.iterdir() if p.is_file()))

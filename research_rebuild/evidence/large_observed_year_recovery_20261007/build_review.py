import sys,json,gzip,re,hashlib
from pathlib import Path
import pandas as pd
sys.path.insert(0,'/workspace/russian-settlements-research/research_rebuild/mass_linkage')
from working_state_20261007 import load,E
from current_chain_state_20261007 import sha,normalize,distance_km
O=E/'large_observed_year_recovery_20261007';s=load(15)
x=pd.read_csv(O/'current_residual2021.csv');x=x[~x.region_norm.isin(['крым','санкт петербург','севастополь','москва']) & ~x.already_aux].head(30)
related=s.obs[s.obs.region_norm.isin(x.region_norm) & s.obs.name_norm.isin(x.name_norm)].copy()
related['years']=related.root.map(lambda r:json.dumps(sorted(s.years[r])));related.to_csv(O/'selected_own_name_rows.csv',index=False)
rec=[]
for r in x.to_dict('records'):
 sid=r['source_record_id'];p=s.point_rows.get(sid,{})
 rec.append({'focus_id':sid,'name':r['settlement_name'],'region':r['region_norm'],'county':r['district_raw'],'years':r['years'],'component_ids':json.dumps(s.obs.loc[s.obs.root.eq(s.uf.find(sid)),'source_record_id'].tolist()),'point_json':json.dumps(p,ensure_ascii=False)})
pd.DataFrame(rec).to_csv(O/'current_components_points.csv',index=False)
(O/'baseline_receipt.json').write_text(json.dumps({'stage':15,'metrics':s.metrics(),'input_hashes':{str(p):sha(p) for p in s.inputs}},ensure_ascii=False,indent=2))
pops=[29533,20355,18536,13892,5192,8282,10189,95,3087,7628,8079,222,8835,8034,7115,6945,11306,12046,9145,4897]; y=s.obs[(s.obs.census_year<2021)&s.obs.population.isin(pops)].copy();y['years']=y.root.map(lambda r:json.dumps(sorted(s.years[r])));y.to_csv(O/'selected_population_signature_checks.csv',index=False);print(y[['source_record_id','census_year','settlement_name','region_norm','district_raw','population','years']].to_string(index=False))

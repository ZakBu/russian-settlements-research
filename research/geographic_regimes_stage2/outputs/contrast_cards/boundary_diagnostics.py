"""Diagnostic exclusions of selected urban rows; NOT repaired constant boundaries."""
from pathlib import Path
import pandas as pd,math,json,hashlib
B=Path(__file__).parent
rows=[]
for stem,name in [('contrast_concentration_a','Норильск'),('contrast_concentration_b','Самара'),('contrast_neighborhood_a','Волгоград'),('contrast_neighborhood_b','Саратов')]:
 d=pd.read_csv(B/(stem+'_roster.csv')).sort_values(['population_2002','entity_uid'],ascending=[False,True]);top=d.head(math.ceil(len(d)*.1))
 keep=d.settlement_name_2002!=name;q=d[keep];t=top[top.settlement_name_2002!=name]
 rows.append({'roster':stem,'removed_name':name,'n_removed':int((~keep).sum()),'retained_fixed_top_count':len(t),'diagnostic_top_delta_pp':100*(t.population_2021.sum()/q.population_2021.sum()-t.population_2002.sum()/q.population_2002.sum()),'diagnostic_population_change_pct':100*(q.population_2021.sum()/q.population_2002.sum()-1),'interpretation':'Selected-row omission only; no reconstruction of missing predecessor mass or constant boundaries; not primary estimand'})
pd.DataFrame(rows).to_csv(B/'boundary_omission_diagnostics.csv',index=False)
inputpath=Path('/workspace/scratch/c21afd18c709/repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz')
cols=['entity_uid','settlement_name_2002','effective_region_norm_2002','population_2002','population_2010','population_2021','population_value_quality_2021']
d=pd.read_csv(inputpath,usecols=cols,low_memory=False);checks=[]
for name,region in [('Талнах','красноярский'),('Кайеркан','красноярский'),('Норильск','красноярский'),('Гумрак','волгоградская'),('Водстрой','волгоградская'),('Горьковский','волгоградская'),('Волгоград','волгоградская'),('Саратов','саратовская')]:
 q=d[(d.settlement_name_2002.fillna('').str.casefold()==name.casefold())&(d.effective_region_norm_2002==region)]
 checks.append({'name2002_exact':name,'region2002':region,'n_matched':len(q),'records':q.to_dict('records')})
(B/'boundary_name_checks.json').write_text(json.dumps({'input_sha256':hashlib.sha256(inputpath.read_bytes()).hexdigest(),'checks':checks,'caveat':'Exact-name lookup; absent exact names are not proof of complete entity absence under aliases. No population corrected.'},ensure_ascii=False,indent=2))

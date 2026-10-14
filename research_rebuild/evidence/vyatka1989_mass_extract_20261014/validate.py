import json,hashlib
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
R=Path('/workspace/shared/vyatka1989_mass_extract')
D=pd.read_parquet(R/'facts.parquet')
b=Path('/workspace/shared/vyatka1989_acquisition/index.html').read_bytes();s=BeautifulSoup(b,'html.parser');expected=[]
for tr in s.select('table > tbody > tr'):
 td=tr.find_all('td',recursive=False)
 if len(td)==16 and td[0].get_text(strip=True).isdigit():
  v=[t.get_text(' ',strip=True) for t in td];expected.append(dict(district_id=v[0],district=v[1],expected_localities=v[6],expected_present=v[9],expected_permanent=v[12],object_level='district_aggregate' if v[0]!='45' else 'region_aggregate',raw_cells_json=json.dumps(v,ensure_ascii=False),table_url='https://rodnaya-vyatka.ru/vpn1989-kirov',table_sha256=hashlib.sha256(b).hexdigest()))
E=pd.DataFrame(expected);E.to_parquet(R/'index_aggregates.parquet',index=False)
checks=[]
for _,r in E[E.district_id!='45'].iterrows():
 d=D[D.district_id==r.district_id];checks.append(dict(district_id=r.district_id,rows=len(d),expected_rows=int(r.expected_localities),present=int(d.present_both.sum()),expected_present=int(r.expected_present),permanent=int(d.permanent_both.sum()),expected_permanent=int(r.expected_permanent)))
C=pd.DataFrame(checks);C.to_csv(R/'district_reconciliation.csv',index=False)
checks_summary={'row_count_match':int((C.rows==C.expected_rows).sum()),'present_sum_match':int((C.present==C.expected_present).sum()),'permanent_sum_match':int((C.permanent==C.expected_permanent).sum()),'districts':len(C),'present_sex_sum_failures':int((D.present_male+D.present_female!=D.present_both).sum()),'permanent_sex_sum_failures':int((D.permanent_male+D.permanent_female!=D.permanent_both).sum())}
(R/'validation.json').write_text(json.dumps(checks_summary,indent=2));print(checks_summary);print(C[(C.rows!=C.expected_rows)|(C.present!=C.expected_present)|(C.permanent!=C.expected_permanent)].to_string(index=False))

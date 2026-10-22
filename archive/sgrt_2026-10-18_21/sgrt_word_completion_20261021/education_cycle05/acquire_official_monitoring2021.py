#!/usr/bin/env python3
"""Acquire whole public federal-district education monitoring tables,2022report/data2021."""
from pathlib import Path
import requests,concurrent.futures,json,hashlib,time,datetime,bs4
HERE=Path(__file__).resolve().parent;OUT=HERE/'sources/official_monitoring2021';OUT.mkdir(exist_ok=True)
BASE='https://monitoring.miccedu.ru/iam/2022/'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fetch(it):
 sector,fd=it;u=f'{BASE}_{sector}/material.php?type=1&id={fd}';p=OUT/f'{sector}_federal_district_{fd}.html'
 if not p.exists() or p.stat().st_size<10000:
  for attempt in range(2):
   try:
    r=requests.get(u,timeout=50);r.raise_for_status();assert b'inst.php' in r.content;p.write_bytes(r.content);break
   except Exception as e:
    if attempt==1:return {'sector':sector,'fd':fd,'url':u,'status':'FAILED','error':str(e)}
    time.sleep(1)
 s=bs4.BeautifulSoup(p.read_bytes(),'html.parser');ids=[x.get('id')for x in s.select('td.inst[id]')]
 return{'sector':sector,'fd':fd,'url':u,'file':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'institution_rows':len(ids),'unique_institution_ids':len(set(ids)),'status':'ACQUIRED'}
if __name__=='__main__':
 before=datetime.datetime.now(datetime.timezone.utc).isoformat();out=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(fetch,[(sector,int(a['href'].split('id=')[-1]))for sector in ['vpo','spo']for a in bs4.BeautifulSoup((HERE/'sources'/f'monitoring2022_{sector}.html').read_bytes(),'html.parser').select('a[href]')if 'material.php?type=1&id=' in a['href']]));receipt={'created_utc':before,'download_completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'OfficialMICCEDU/Ministriespublicmonitoring2022archive, explicitlydata2021','expected_national_vpo_reporting_organizations_and_branches':1208,'expected_national_spo_reporting_organizations_and_branches':4572,'not_a_complete_census_of_all_operating_institutions':True,'scope_exclusions':'Military/security/lawenforcementandnonreportingorganizations excludedby officialsource footnote','files':out};(HERE/'official_monitoring2021_acquisition.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))

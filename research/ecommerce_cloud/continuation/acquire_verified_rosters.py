"""Verified Rosstat roster retry with the official 2024 intermediate chain."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from html import unescape
import concurrent.futures
import hashlib
import json
import re
import ssl
import subprocess
import urllib.request
from urllib.parse import urljoin, urlparse
from register_temporal_audit import russian_root_context, probe

out=Path('work/ecommerce_rosters_verified');out.mkdir(parents=True,exist_ok=True)
context,ca=russian_root_context(out)
report={'checked_utc':datetime.now(timezone.utc).isoformat(),'tls_verification':True,
        'old_official_chain':ca,'data_absence_established':False,
        'territorial_boundaries_verified':False,'causal_effect_estimated':False}
try:
    if context is None:
        raise RuntimeError('Official root could not be loaded and verified')
    url='https://gu-st.ru/content/lending/russian_trusted_sub_ca_2024_pem.crt'
    with urllib.request.urlopen(url,context=ssl.create_default_context(),timeout=35) as r:
        if not r.url.startswith('https://gu-st.ru/'):
            raise ValueError('Unexpected official intermediate redirect')
        pem=r.read(100001)
    if len(pem)>100000 or pem.count(b'-----BEGIN CERTIFICATE-----')!=1:
        raise ValueError('Expected one bounded PEM intermediate')
    path=out/'russian_trusted_sub_ca_2024_pem.crt';path.write_bytes(pem)
    root=out/'russian_trusted_root_ca_pem.crt'
    check=subprocess.run(['openssl','verify','-CAfile',str(root),str(path)],
                         check=True,capture_output=True,text=True)
    info=subprocess.run(['openssl','x509','-in',str(path),'-noout','-subject','-issuer',
                         '-dates','-sha256','-fingerprint'],
                        check=True,capture_output=True,text=True)
    context.load_verify_locations(cafile=str(path))
    report['additional_intermediate']={'url':url,'sha256':hashlib.sha256(pem).hexdigest(),
                                       'verified_to_pinned_root':True,
                                       'chain_check':check.stdout,'certificate_info':info.stdout}
    pageurl='https://rosstat.gov.ru/opendata/7708234640-oktmo'
    with urllib.request.urlopen(pageurl,context=context,timeout=45) as r:
        page=r.read(3000001)
        if len(page)>3000000:
            raise ValueError('Official catalogue page exceeded bounded size')
        report['catalogue_http_status']=r.status
    text=page.decode('utf-8',errors='replace')
    (out/'catalogue.html').write_bytes(page)
    report['catalogue_sha256']=hashlib.sha256(page).hexdigest()
    links=sorted(set(urljoin(pageurl,unescape(x)) for x in re.findall(
        r"""href=["']([^"']+\.csv[^"']*)["']""",text,re.I)))
    report['catalogue_csv_links']=links
    jobs=[('2023-01-01','data-20221228T1112-structure-20260210T1102.csv'),
          ('2024-01-01','data-20231219T1512-structure-20260210T1102.csv'),
          ('2025-01-01','data-20241227T1412-structure-20260210T1102.csv')]
    for year,stem in list(jobs):
        prefix=stem.split('-structure')[0]
        for link in links:
            if prefix in link and urlparse(link).hostname=='rosstat.gov.ru':
                name=link.rsplit('/',1)[-1]
                if (year,name) not in jobs:
                    jobs.append((year,name))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        report['roster_probes']=list(pool.map(lambda item:probe(item,out,context),jobs))
except Exception as error:
    report.update(error_type=type(error).__name__,error=str(error))
(out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('VERIFIED_ROSTERS_RESULT_BEGIN')
print(json.dumps(report,ensure_ascii=False,indent=2))
print('VERIFIED_ROSTERS_RESULT_END')

"""Inspect a failing public TLS chain without accepting source data."""
from pathlib import Path
import json
import re
import subprocess
from register_temporal_audit import russian_root_context

out=Path('work/ecommerce_tls_chain'); out.mkdir(parents=True,exist_ok=True)
context,provenance=russian_root_context(out)
report={'ca_provenance':provenance,'source_data_accepted':False,
        'diagnostic_certificate_is_not_trust_evidence':True}
paths=[out/'russian_trusted_root_ca_pem.crt',out/'russian_trusted_sub_ca_pem.crt']
if all(p.exists() for p in paths):
    bundle=out/'scoped_official_chain.pem'
    bundle.write_bytes(b''.join(p.read_bytes() for p in paths))
    command=['openssl','s_client','-connect','rosstat.gov.ru:443',
             '-servername','rosstat.gov.ru','-showcerts','-verify_return_error',
             '-verify_hostname','rosstat.gov.ru','-CAfile',str(bundle)]
    try:
        p=subprocess.run(command,input='',capture_output=True,text=True,timeout=30)
        report.update(handshake_returncode=p.returncode,
                      verification_stderr=p.stderr[:5000])
        certs=re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
                         p.stdout,re.S)
        report['presented_certificates_n']=len(certs)
        infos=[]
        for pem in certs[:8]:
            q=subprocess.run(['openssl','x509','-noout','-subject','-issuer',
                              '-dates','-sha256','-fingerprint'],input=pem,
                             capture_output=True,text=True,check=True)
            infos.append(q.stdout)
        report['presented_certificate_info_untrusted']=infos
    except Exception as error:
        report.update(error_type=type(error).__name__,error=str(error))
(out/'diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('TLS_CHAIN_DIAGNOSTIC_BEGIN')
print(json.dumps(report,ensure_ascii=False,indent=2))
print('TLS_CHAIN_DIAGNOSTIC_END')

"""Read-only audit of source-date semantics and three official roster candidates.

No census or previously restored file is edited. Codes, composition and
boundaries remain different concepts. Network failures are not absence.
"""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import re
import ssl
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
FIELDS = ['TER','KOD1','KOD2','KOD3','KC','RAZDEL','NAME1','Centrum',
          'NomDescr','NomAkt','Status','DateUtv','DateVved']
BASE = ROOT / 'work/sources/research/ecommerce_settlement_20261024'
REGISTER = BASE / 'history_stage_20261024/centres/raw'
CANDIDATES = BASE / 'settlement_role_stage_20261024/bdmo/singleton/internal_singleton_centre_district_candidates.csv'
OLD_AUDIT = BASE / 'settlement_role_stage_20261024/bdmo/singleton/audit.json'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def parse(data):
    try:
        text = data.decode('utf-8-sig')
        encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        text = data.decode('cp1251')
        encoding = 'cp1251'
    records = []
    for number, row in enumerate(csv.reader(io.StringIO(text), delimiter=';'), 1):
        if len(row) == 13 and all(row[j].isdigit() for j in range(4)):
            r = dict(zip(FIELDS, row))
            r['source_row'] = number
            records.append(r)
    return records, encoding

def effective_date(value):
    if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', value):
        return datetime.strptime(value, '%d.%m.%Y').date()
    return None

def source_audit():
    manifest = json.loads((ROOT/'research/ecommerce_cloud/data_manifest.json').read_text())
    pinned = {r['path']: r for r in manifest['files']}
    expected = {r['vintage']: r['future_rows_excluded']
                for r in json.loads(OLD_AUDIT.read_text())['register_audit']}
    with CANDIDATES.open(encoding='utf-8-sig', newline='') as stream:
        candidates = list(csv.DictReader(stream))
    assert len(candidates) == 338
    previous = {}
    summaries, futures = [], []
    for path in sorted(REGISTER.glob('data-*.csv')):
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        assert relative in pinned, relative
        assert sha(data) == pinned[relative]['sha256'], relative
        vintage = re.search(r'data-(\d{8})T',path.name).group(1)
        snapshot = datetime.strptime(vintage,'%Y%m%d').date()
        rows, encoding = parse(data)
        excluded = [r for r in rows if effective_date(r['DateVved']) is not None
                    and effective_date(r['DateVved']) > snapshot]
        assert len(excluded) == expected[vintage], (vintage,len(excluded),expected[vintage])
        status_counts = dict(Counter(r['Status'] for r in rows))
        for r in excluded:
            code11 = r['TER']+r['KOD1']+r['KOD2']+r['KOD3']
            code8 = code11[:8]
            direct, same_upper = [], []
            for c in candidates:
                key = c['source_record_id_2021']
                if code8 in [c['oktmo'],c['parent_oktmo']]:
                    direct.append(key)
                if code8[:5] == c['parent_oktmo'][:5]:
                    same_upper.append(key)
            record = dict(r, register_vintage=vintage,code11=code11,
                          previous_vintages_same_code=list(previous.get((r['RAZDEL'],code11),[])),
                          direct_candidate_ids=sorted(set(direct)),
                          same_upper_prefix_candidate_ids=sorted(set(same_upper)),
                          overlap_is_diagnostic_not_proven_effect=True)
            futures.append(record)
        summaries.append(dict(vintage=vintage,sha256=sha(data),encoding=encoding,
                              parsed_rows=len(rows),raw_status_counts=status_counts,
                              future_rows=len(excluded),
                              future_status_counts=dict(Counter(r['Status'] for r in excluded))))
        for r in rows:
            if effective_date(r['DateVved']) is None or effective_date(r['DateVved']) <= snapshot:
                code = r['TER']+r['KOD1']+r['KOD2']+r['KOD3']
                previous.setdefault((r['RAZDEL'],code),[]).append(
                    dict(vintage=vintage,name=r['NAME1'],Status=r['Status'],DateVved=r['DateVved']))
    return summaries,futures

def russian_root_context(output):
    # Extra trust is scoped to Rosstat probes, never the host CA store.
    url = 'https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt'
    provenance = dict(url=url, download_tls_verified=True,
                      trust_scope='Rosstat roster probes only')
    try:
        with urllib.request.urlopen(url, timeout=40, context=ssl.create_default_context()) as response:
            if not response.url.startswith('https://gu-st.ru/'):
                raise ValueError('Unexpected certificate download redirect')
            pem = response.read(100_001)
        if len(pem)>100_000 or pem.count(b'-----BEGIN CERTIFICATE-----')!=1:
            raise ValueError('Expected one bounded PEM certificate')
        path=output/'russian_trusted_root_ca_pem.crt'
        if sha(pem) != '936a43fea6e8e525bcc0f81acd9c3d21b4fc4b9b68acea7906d698005afc6504':
            raise ValueError('Official root PEM changed since independently logged first fetch')
        path.write_bytes(pem)
        info=subprocess.run(['openssl','x509','-in',str(path),'-noout',
                             '-subject','-issuer','-dates','-sha256','-fingerprint'],
                            check=True,capture_output=True,text=True).stdout
        if 'Russian Trusted Root CA' not in info:
            raise ValueError('Unexpected CA subject')
        verify=subprocess.run(['openssl','verify','-CAfile',str(path),str(path)],
                              check=True,capture_output=True,text=True).stdout
        context=ssl.create_default_context()
        context.load_verify_locations(cafile=str(path))
        suburl='https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt'
        with urllib.request.urlopen(suburl,timeout=40,context=ssl.create_default_context()) as response:
            if not response.url.startswith('https://gu-st.ru/'):
                raise ValueError('Unexpected intermediate redirect')
            sub=response.read(100_001)
        if len(sub)>100_000 or sub.count(b'-----BEGIN CERTIFICATE-----')!=1:
            raise ValueError('Expected bounded intermediate PEM')
        subpath=output/'russian_trusted_sub_ca_pem.crt'
        subpath.write_bytes(sub)
        subverify=subprocess.run(['openssl','verify','-CAfile',str(path),str(subpath)],
                                 check=True,capture_output=True,text=True).stdout
        context.load_verify_locations(cafile=str(subpath))
        provenance.update(intermediate_url=suburl,intermediate_sha256=sha(sub),
                          intermediate_chain_check=subverify,
                          intermediate_requires_verified_root=True)
        provenance.update(pem_sha256=sha(pem),certificate_info=info,
                          self_chain_check=verify)
        return context,provenance
    except Exception as error:
        provenance.update(error_type=type(error).__name__,error=str(error))
        return None,provenance

def probe(item, output, context=None):
    target, stem = item
    url = 'https://rosstat.gov.ru/opendata/7708234640-oktmo/'+stem
    record = dict(target_candidate_date=target,url=url,tls_verification=True,
                  requested_utc=datetime.now(timezone.utc).isoformat(),
                  date_in_filename_is_not_verified_effective_date=True)
    try:
        request = urllib.request.Request(url,headers={'User-Agent':'settlement-research-source-audit/1.0'})
        with urllib.request.urlopen(request,timeout=60,context=context or ssl.create_default_context()) as response:
            body = response.read(30_000_001)
            record.update(http_status=response.status,resolved_url=response.url,
                          bytes=len(body),content_type=response.headers.get('Content-Type'),
                          sha256=sha(body))
        if len(body) > 30_000_000:
            record['rejected'] = 'response exceeds size limit, incomplete body'
        else:
            rows,encoding = parse(body)
            record.update(parsed_records=len(rows),encoding=encoding)
            if len(rows)>100000 and any(r['RAZDEL']=='2' for r in rows):
                path=output/stem
                path.write_bytes(body)
                record.update(full_roster_candidate_saved=path.name,
                              source_schema_candidate_only=True,
                              boundaries_or_complete_history_verified=False)
            else:
                record['rejected']='not an accepted full-roster CSV candidate'
    except urllib.error.HTTPError as error:
        record.update(http_status=error.code,error=str(error),data_absence_established=False)
    except Exception as error:
        record.update(error_type=type(error).__name__,error=str(error),data_absence_established=False)
    return record

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='work/ecommerce_temporal_audit')
    args=parser.parse_args()
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    summaries,futures=source_audit()
    jobs=[('2023-01-01','data-20221228T1112-structure-20260210T1102.csv'),
          ('2024-01-01','data-20231219T1512-structure-20260210T1102.csv'),
          ('2025-01-01','data-20241227T1412-structure-20260210T1102.csv')]
    context,ca_provenance=russian_root_context(output)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        probes=list(pool.map(lambda job:probe(job,output,context),jobs))
    report=dict(checked_utc=datetime.now(timezone.utc).isoformat(),
                source_snapshots=summaries, future_rows=futures,
                candidates_n=338, primary_roster_probes=probes,
                additional_ca_provenance=ca_provenance,
                raw_status_semantics_primary_schema_confirmed=False,
                causal_effect_estimated=False,
                limitations=['Future-date code overlap is diagnostic, not proof of erroneous panel membership.',
                             'Roster identity does not prove territorial boundary invariance.',
                             'Singleton municipality does not locate every shop inside the settlement.',
                             'No numerical national effect is estimated.'])
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('TEMPORAL_REGISTER_AUDIT_JSON_BEGIN',flush=True)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    print('TEMPORAL_REGISTER_AUDIT_JSON_END',flush=True)

if __name__=='__main__':
    main()

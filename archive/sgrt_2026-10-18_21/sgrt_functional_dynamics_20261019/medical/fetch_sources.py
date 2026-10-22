"""Download public sources declared in captures/metadata.json, without authentication.

Use --out to avoid replacing accepted frozen captures. Failures are kept as failures.
The national eligibility list must not be mistaken for all physical medical sites.
"""
import argparse, json, urllib.request, hashlib, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);a=ap.parse_args()
    root=Path(__file__).resolve().parent;dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    rows=json.loads((root/'captures/metadata.json').read_text())
    rows+= [{'source_id':'rz_schema','url':'https://www.roszdravnadzor.gov.ru/opendata/7710537160-organizations/structure-20191004.csv'}, {'source_id':'rz_eligibility_list','url':'https://www.roszdravnadzor.gov.ru/opendata/7710537160-organizations/data-20261018-structure-20191004.csv'}]
    def fetch(row):
        out=dict(source_id=row['source_id'],url=row['url'],retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            r=urllib.request.urlopen(row['url'],timeout=40);b=r.read();ext='.pdf' if b.startswith(b'%PDF') else '.csv' if row['url'].endswith('.csv') else '.html';p=dest/(row['source_id']+ext);p.write_bytes(b)
            out.update(status=r.status,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),path=p.name)
        except Exception as e:out['error']=repr(e)
        return out
    results=list(ThreadPoolExecutor(4).map(fetch,rows))
    (dest/'DOWNLOAD_LOG.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(attempts=len(results),success=sum('sha256' in x for x in results)),ensure_ascii=False))

if __name__=='__main__':main()

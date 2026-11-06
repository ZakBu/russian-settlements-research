"""Restore public statistical mirrors without contacting blocked source hosts.

No new search, retry or TLS override. Content is pinned to a public Git commit.
"""
from pathlib import Path
import hashlib,json
from urllib.request import urlopen,Request
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_national_20261106/sber'
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cards=json.loads((HERE/'sber_consumption/sourcecards.json').read_text())
    for r in cards['pins']:
        if not r.get('url'):continue
        path=OUT/r['name']
        if path.exists():body=path.read_bytes()
        else:
            with urlopen(Request(r['url'],headers={'User-Agent':'settlements-research-public-source/1.0'}),timeout=45)as f:
                body=f.read()
        assert len(body)==r['bytes']and hashlib.sha256(body).hexdigest()==r['sha256'],r['name']
        path.write_bytes(body)
        print(r['name'],len(body),'pinned mirror matches')
    salary=ROOT/'work/ecommerce_national_20261106/employment_panel/raw/sber_bdmo_salary.parquet'
    salary.parent.mkdir(parents=True,exist_ok=True)
    if salary.exists():body=salary.read_bytes()
    else:
        url='https://raw.githubusercontent.com/TrueSpearmint/sberindex_hackathon/2688b801792b7d43e4f460d7004bccac374960d2/data_in/sberindex/4_bdmo_salary.parquet'
        with urlopen(url,timeout=45)as f:body=f.read()
    assert hashlib.sha256(body).hexdigest()=='f9a8956ad68c7ec81fac7b2e61ac2494b02b489887ce06204621b5dff29e62f2'
    salary.write_bytes(body)
    print('salary',len(body),'pinned mirror matches')
if __name__=='__main__':main()

"""Restore only the six accepted historical ATP bodies, with byte pins."""
from pathlib import Path
import argparse
import json
from acquire_atp_historical import Fetcher, RemoteZip, summarize, sha
import zipfile

ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',default='research/ecommerce_cloud/continuation/atp_pinned_manifest.json')
    p.add_argument('--output',default='work/ecommerce_atp_history')
    p.add_argument('--axis-csv')
    a=p.parse_args()
    out=ROOT/a.output;out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/a.manifest).read_text())
    fetch=Fetcher(out,600)
    summaries=[]
    for row in manifest['records']:
        rid=row['run_id']
        bodypath=out/(rid+'_wildberries.geojson')
        if bodypath.exists():
            body=bodypath.read_bytes()
        elif row['archive_member']:
            remote=RemoteZip(fetch,row['raw_url'])
            with zipfile.ZipFile(remote) as z:
                info=z.getinfo(row['archive_member'])
                if info.file_size>100*1024*1024:
                    raise ValueError('Expanded historical body too large')
                body=z.read(info)
        else:
            body,_=fetch.get(row['raw_url'],100*1024*1024)
        assert sha(body)==row['raw_sha256'], 'Historical raw byte pin mismatch: '+rid
        bodypath.write_bytes(body)
        stats,event=fetch.get(row['stats_url'],12*1024*1024)
        assert sha(stats)==row['stats_sha256'], 'Historical stats byte pin mismatch: '+rid
        (out/(rid+'_pinned_runwide_stats.json')).write_bytes(stats)
        summary,_=summarize(body,rid,out,None)
        assert summary['features_all_countries']==row['features_all_countries']
        summaries.append(summary)
    report={'scope':'six_fixed_byte_verified_historical_ATP_WB_outputs',
            'records':summaries,'http_events':fetch.events,
            'full_archive_sha256_verified':False,
            'opening_dates_established':False,'causal_effect_estimated':False}
    (out/'pinned_restoration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('ATP_PINNED_RESTORATION_BEGIN')
    print(json.dumps({k:v for k,v in report.items() if k!='http_events'},ensure_ascii=False))
    print('ATP_PINNED_RESTORATION_END')
if __name__=='__main__':
    main()

"""Read-only acquisition and schema audit. No inferred data or source edits."""
from pathlib import Path
import requests, json, hashlib, zipfile, re, os, pandas as pd
import pyarrow.parquet as pq
ROOT=Path('sgrt_inputs'); ROOT.mkdir(exist_ok=True)
S=requests.Session(); manifest=[]
def fetch(url,name):
    p=ROOT/name; p.parent.mkdir(parents=True,exist_ok=True)
    r=S.get(url,stream=True,timeout=(30,300)); r.raise_for_status()
    h=hashlib.sha256(); n=0
    with p.open('wb') as f:
        for b in r.iter_content(4*1024*1024):
            f.write(b);h.update(b);n+=len(b)
    manifest.append(dict(url=url,path=name,bytes=n,sha256=h.hexdigest()))
    print('DOWNLOADED',name,n,h.hexdigest(),flush=True)
    (ROOT/'download_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return p

def describe(df,name):
    x={'shape':list(df.shape),'columns':list(df.columns),'head':json.loads(df.head(3).to_json(orient='records',force_ascii=False)),'missing':df.isna().sum().to_dict()}
    (ROOT/(name+'.schema.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str))
    print('SCHEMA',name,json.dumps(x,ensure_ascii=False,default=str)[:26000],flush=True)

repo='https://raw.githubusercontent.com/ZakBu/russian-settlements-research/main/'
base='https://github.com/ZakBu/russian-settlements-research/releases/download/working-settlements-stage71-2026-10-09/'
for name in ['README.md','accepted_common_federal_territory_axis.csv','applied_state_observations.parquet','applied_point_snapshot.parquet']:
    try:
        p=fetch(base+name,name)
        if p.suffix=='.parquet':
            d=pd.read_parquet(p);describe(d,name)
            # CSV portable to environments lacking pyarrow; full state tables remain in source.
            d.to_csv(ROOT/(name+'.csv.gz'),index=False);p.unlink()
        elif p.suffix=='.csv': describe(pd.read_csv(p),name)
    except Exception as e: print('SOURCE_ERROR',name,str(e),flush=True)
for path in ['research_rebuild/evidence/historical_censuses_integration_20261014/population_1979_1989_long.parquet','research_rebuild/evidence/tochno_np_attach_20261013/bridges/native_np_municipality_bridge.csv.gz','research_rebuild/evidence/tochno_catalog_20261013/README.md','research_rebuild/evidence/tochno_catalog_20261013/population_downloads.csv']:
    try:
        name=path.split('/')[-1]; p=fetch(repo+path,name)
        if p.suffix=='.parquet':
            d=pd.read_parquet(p);describe(d,name);d.to_csv(ROOT/(name+'.csv.gz'),index=False);p.unlink()
        elif '.csv' in name:describe(pd.read_csv(p,low_memory=False),name)
    except Exception as e: print('SOURCE_ERROR',path,str(e),flush=True)
# Snapshot URL is explicit rather than an assumed latest version. Retain all classifications.
url='https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20250918/by_section/data_section7_112_v20250918_section_file.zip'
try:
    p=fetch(url,'agriculture_source.zip')
    with zipfile.ZipFile(p) as z:
        print('AGRI_MEMBERS',z.namelist(),flush=True)
        for member in z.namelist():
            if member.endswith('.parquet'):
                with z.open(member) as f:d=pd.read_parquet(f)
                describe(d,'agriculture'); d.to_csv(ROOT/'agriculture.csv.gz',index=False)
            elif member.endswith('.csv'):
                with z.open(member) as f:d=pd.read_csv(f,sep=';',low_memory=False)
                describe(d,'agriculture'); d.to_csv(ROOT/'agriculture.csv.gz',index=False)
            elif member.lower().endswith(('.txt','.md')): (ROOT/Path(member).name).write_bytes(z.read(member))
    p.unlink()
except Exception as e: print('AGRICULTURE_ERROR',str(e),flush=True)
# Fixed latest revision resolved once, then use same immutable HF commit for both years.
try:
    meta=S.get('https://huggingface.co/api/datasets/irlspbru/RFSD',timeout=60);meta.raise_for_status();sha=meta.json()['sha']
    (ROOT/'rfsd_revision.json').write_text(json.dumps({'revision':sha,'source':'irlspbru/RFSD'},indent=2))
    for year in [2011,2021]:
        p=fetch(f'https://huggingface.co/datasets/irlspbru/RFSD/resolve/{sha}/RFSD/year={year}/part-0.parquet',f'rfsd_{year}.parquet')
        pf=pq.ParquetFile(p); names=pf.schema_arrow.names
        selected=[n for n in names if re.search(r'(^inn$|^year$|okved|okato|oktmo|lon|lat|geoc|outlier|filing|imput|address|munic|region|line_2110$|line_2120$|line_1600$|line_1150$|line_2400$|line_4122$)',n,re.I)]
        print('RFSD_COLUMNS',year,names,'SELECTED',selected,flush=True)
        # Streaming export does not allocate all financial variables in memory.
        first=True; outfile=ROOT/f'rfsd_{year}_selected.csv.gz'
        import gzip
        with gzip.open(outfile,'wt',encoding='utf-8') as out:
            for batch in pf.iter_batches(batch_size=100000,columns=selected):
                d=batch.to_pandas()
                if first:describe(d,f'rfsd_{year}_sample');first=False
                d.to_csv(out,index=False,header=(out.tell()==0))
        p.unlink()
except Exception as e: print('RFSD_ERROR',str(e),flush=True)
# Public-domain cartographic background. It is not an administrative harmonization layer.
try:
    p=fetch('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson','world_50m.geojson')
except Exception as e: print('MAP_ERROR',str(e),flush=True)
(ROOT/'COMPLETE.txt').write_text('Acquisition finished; individual SOURCE_ERROR lines and manifests govern availability. No analysis completion is asserted.\n')

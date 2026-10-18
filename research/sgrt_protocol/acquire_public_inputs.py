"""Read-only public-source acquisition for the SGRT research protocol.
No credentials, source modifications or private data are used.
"""
from pathlib import Path
import requests, json, hashlib, re, traceback
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import pyarrow.parquet as pq
import pandas as pd
from bs4 import BeautifulSoup
OUT=Path('sgrt_enrichment'); OUT.mkdir(exist_ok=True)
manifest=[]
def download(url, name, maxbytes=800_000_000):
    p=OUT/name; p.parent.mkdir(parents=True,exist_ok=True)
    with requests.get(url,stream=True,timeout=(30,240)) as r:
        r.raise_for_status(); n=0; h=hashlib.sha256()
        with p.open('wb') as f:
            for chunk in r.iter_content(2**20):
                n+=len(chunk)
                if n>maxbytes: raise ValueError('Source exceeds acquisition size bound')
                f.write(chunk);h.update(chunk)
    manifest.append({'url':url,'file':str(p.relative_to(OUT)),'bytes':n,'sha256':h.hexdigest()})
    return p
BASE='https://raw.githubusercontent.com/ZakBu/russian-settlements-research/main/'
RELEASE='https://github.com/ZakBu/russian-settlements-research/releases/download/working-settlements-stage71-2026-10-09/'
resources={
 'population_1989.parquet':BASE+'research_rebuild/evidence/historical_sources_integration_20261014/population_1989_selected_long.parquet',
 'municipality_bridge.csv.gz':BASE+'research_rebuild/evidence/tochno_np_attach_20261013/bridges/native_np_municipality_bridge.csv.gz',
 'federal_axis.csv':RELEASE+'accepted_common_federal_territory_axis.csv',
 'point_snapshot.parquet':RELEASE+'applied_point_snapshot.parquet',
 'rfsd_names.csv':'https://raw.githubusercontent.com/irlcode/RFSD/main/aux_data/descriptive_names_dict.csv',
 'world.geojson':'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson',
}
errors=[]
def small(item):
    name,url=item
    try:
        p=download(url,name)
        if name.endswith('.parquet'):
            pf=pq.ParquetFile(p); info={'rows':pf.metadata.num_rows,'schema':str(pf.schema_arrow),'head':pf.read_row_group(0).slice(0,3).to_pandas().to_json(orient='records',force_ascii=False)}
            (OUT/(name+'.schema.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2));print(name,info['rows'],flush=True)
    except Exception as e: errors.append({'source':url,'error':str(e)});print(name,str(e),flush=True)
with ThreadPoolExecutor(max_workers=4) as ex: list(ex.map(small,resources.items()))
for year in [2016,2021]:
    url=f'https://huggingface.co/datasets/irlspbru/RFSD/resolve/main/RFSD/year={year}/part-0.parquet?download=true'
    try:
        p=download(url,f'cache/rfsd_{year}.parquet')
        pf=pq.ParquetFile(p); names=pf.schema_arrow.names
        selected=[n for n in names if n in ['inn','year','line_2110','line_1150','line_1600','line_2400'] or re.search(r'lat|lon|lng|okved|oktmo|okato|outlier|imput|filing|filed|articul|rank|precision|geocod|eligible',n,re.I)]
        info={'rows':pf.metadata.num_rows,'schema':str(pf.schema_arrow),'selected_columns':selected}
        table=pf.read(columns=selected)
        pq.write_table(table,OUT/f'rfsd_{year}_selected.parquet',compression='zstd')
        info['head']=table.slice(0,3).to_pandas().to_json(orient='records',force_ascii=False)
        (OUT/f'rfsd_{year}_schema.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
        print('RFSD',year,info,flush=True); del table; p.unlink()
    except Exception as e: errors.append({'source':url,'error':str(e)});print('RFSD',year,str(e),flush=True)
# Discover official municipal agriculture files; preserve exact titles and URLs.
pages=['https://54.rosstat.gov.ru/folder/36883','https://22.rosstat.gov.ru/national_census_2016','https://10.rosstat.gov.ru/folder/60012','https://40.rosstat.gov.ru/folder/40888','https://55.rosstat.gov.ru/vshp-2016']
links=[]
def agriculture(url):
    try:
        r=requests.get(url,timeout=60);r.raise_for_status();s=BeautifulSoup(r.content,'html.parser')
        for a in s.select('a[href]'):
            title=' '.join(a.get_text(' ',strip=True).split()); href=urljoin(url,a['href'])
            if re.search(r'xls|xlsx|zip|rar|pdf',href,re.I) and (re.search(r'муницип|книга\s*2|земель|посевн|том\s*1',title,re.I)):
                links.append({'page':url,'title':title,'url':href})
        (OUT/('agri_page_'+url.split('//')[1].split('.')[0]+'.html')).write_text(r.text)
    except Exception as e: errors.append({'source':url,'error':str(e)})
with ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(agriculture,pages))
for i,x in enumerate(links):
    if re.search(r'\.(xlsx?|zip|rar)(?:\?|$)',x['url'],re.I):
        try:download(x['url'],'agriculture/'+str(i)+'_'+x['url'].split('/')[-1].split('?')[0],maxbytes=30_000_000)
        except Exception as e:errors.append({'source':x['url'],'error':str(e)})
(OUT/'agriculture_links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2))
(OUT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(OUT/'acquisition_errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2))
print('AGRICULTURE_LINKS',json.dumps(links,ensure_ascii=False),flush=True)
print('ERRORS',json.dumps(errors,ensure_ascii=False),flush=True)

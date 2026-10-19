"""Range-read Overture Places, inspect metadata before spatial/column selection."""
from pathlib import Path
import urllib.request,xml.etree.ElementTree as ET,json,struct,hashlib,tempfile
from concurrent.futures import ThreadPoolExecutor,as_completed
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'metadata';RAW.mkdir(exist_ok=True,parents=True)
BASE='https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'

def request(url,start=None,end=None):
    errors=[]
    for trial in range(6):
        u=url if trial<3 else url.replace(BASE,'https://overturemapswestus2.blob.core.windows.net/')
        try:return request_once(u,start,end)
        except Exception as e:
            entry={'url':u,'start':start,'end':end,'attempt':trial+1,'error':type(e).__name__,'message':str(e)}
            with (RAW/'failed_operations.jsonl').open('a') as f:f.write(json.dumps(entry)+'\n')
            errors.append(entry)
    raise RuntimeError(errors)

def request_once(url,start=None,end=None):
    headers={'User-Agent':'Settlement-function-research/1.0'}
    if start is not None:headers['Range']=f'bytes={start}-{end}'
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=60) as r:
        data=r.read() if start is None else r.read(end-start+2)
        meta={'url':url,'status':r.status,'bytes':len(data),'ETag':r.headers.get('ETag'),'Content-Range':r.headers.get('Content-Range'),'sha256':hashlib.sha256(data).hexdigest()}
        if start is not None:
            assert r.status==206 and len(data)==end-start+1 and meta['Content-Range'].startswith(f'bytes {start}-{end}/'),meta
    return data,meta

def discover(selected_release=None):
    data,meta=request('https://stac.overturemaps.org/catalog.json')
    (RAW/'stac_catalog.json').write_bytes(data);(RAW/'stac_access.json').write_text(json.dumps(meta,indent=2))
    release=selected_release or json.loads(data)['latest'];prefix=f'release/{release}/theme=places/type=place/'
    previous=RAW/'source_manifest.json'
    if previous.exists() and json.loads(previous.read_text())['release']!=release:
        raise ValueError('Existing extraction is pinned to another release; use a separate namespace for a new release')
    from urllib.parse import urlencode
    objects=[];token=None;pages=[]
    while True:
        args={'list-type':'2','prefix':prefix,'max-keys':1000}
        if token:args['continuation-token']=token
        b,m=request(BASE+'?'+urlencode(args));pages.append(m)
        t=ET.fromstring(b);ns={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}
        for x in t.findall('s:Contents',ns):
            k=x.findtext('s:Key',namespaces=ns)
            if k.endswith('.parquet'):objects.append({'key':k,'size':int(x.findtext('s:Size',namespaces=ns)),'etag':x.findtext('s:ETag',namespaces=ns),'url':BASE+k})
        token=t.findtext('s:NextContinuationToken',namespaces=ns)
        if not token:break
    manifest={'release':release,'files':objects,'discovery_access':pages,'global_bytes_not_downloaded':sum(o['size'] for o in objects)}
    (RAW/'source_manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def footer(obj):
    name=Path(obj['key']).name
    cache=RAW/(name+'.footer')
    if cache.exists():b=cache.read_bytes();records=[]
    else:
        tail,m=request(obj['url'],obj['size']-8,obj['size']-1);assert tail[4:]==b'PAR1'
        n=struct.unpack('<I',tail[:4])[0]
        b,m2=request(obj['url'],obj['size']-n-8,obj['size']-1)
        cache.write_bytes(b);records=[m,m2]
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'source.parquet'
        with p.open('wb') as f:f.truncate(obj['size']);f.write(b'PAR1');f.seek(obj['size']-len(b));f.write(b)
        pf=pq.ParquetFile(p)
        cols=[pf.metadata.row_group(0).column(i).path_in_schema for i in range(pf.metadata.num_columns)]
        rg=[]
        for i in range(pf.metadata.num_row_groups):
            x=pf.metadata.row_group(i);bb={}
            for ci,c in enumerate(cols):
                if c.startswith('bbox.'):
                    s=x.column(ci).statistics
                    bb[c]=None if s is None else {'min':s.min,'max':s.max}
            rg.append({'row_group':i,'rows':x.num_rows,'bbox':bb})
        info={'file':name,'rows':pf.metadata.num_rows,'row_groups':pf.metadata.num_row_groups,'columns':cols,'schema':str(pf.schema_arrow),'row_group_bounds':rg,'access':records,'footer_sha256':hashlib.sha256(b).hexdigest(),'schema_inspected_before_data':True}
    (RAW/(name+'.metadata.json')).write_text(json.dumps(info,indent=2))
    print(name,info['rows'],info['row_groups'],flush=True)
    return info

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--release',default='2026-09-23.1');args=parser.parse_args()
    manifest=discover(args.release);print('release',manifest['release'],'files',len(manifest['files']),'globalbytes',manifest['global_bytes_not_downloaded'],flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results=list(ex.map(footer,manifest['files']))
    (RAW/'ALL_FOOTERS.json').write_text(json.dumps({'files':len(results),'rows':sum(x['rows'] for x in results),'all_schemas_inspected':True},indent=2))

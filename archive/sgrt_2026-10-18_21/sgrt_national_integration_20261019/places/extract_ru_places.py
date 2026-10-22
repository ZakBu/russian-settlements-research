"""Two-phase row-group/column pruning; no complete worldwide parquet download."""
from pathlib import Path
import json,hashlib,tempfile,asyncio,os
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from matplotlib.path import Path as GeoPath
from acquire_overture import ROOT,RAW,BASE,request
from concurrent.futures import ThreadPoolExecutor,as_completed

OUT=ROOT/'selected';OUT.mkdir(exist_ok=True)
WORLD=ROOT.parents[1]/'restored/extracted/inputs/recovery_inputs/enrichment/world.geojson'
world=json.loads(WORLD.read_text())
polygons=[]
for f in world['features']:
    if f['properties'].get('ADM0_A3')=='RUS':
        g=f['geometry'];polygons.extend([g['coordinates']] if g['type']=='Polygon' else g['coordinates'])

def country_mask(x,y):
    pts=np.column_stack([x,y]);inside=np.zeros(len(x),dtype=bool)
    for poly in polygons:
        ext=GeoPath(np.asarray(poly[0])).contains_points(pts)
        for hole in poly[1:]:ext &= ~GeoPath(np.asarray(hole)).contains_points(pts)
        inside |= ext
    return inside

def eligible_rg(info):
    out=[]
    for rg in info['row_group_bounds']:
        b=rg['bbox'];x=b.get('bbox.xmin');y=b.get('bbox.ymin')
        if not x or not y:out.append(rg['row_group']);continue
        if (x['max']>=19 and y['max']>=41 and y['min']<=83) or (x['min']<=-168 and y['max']>=60):out.append(rg['row_group'])
    return out

async def ranges_download(url,ranges,sparse,phase):
    merged=[]
    for start,end in sorted(set(ranges)):
        if merged and start<=merged[-1][1]+2048:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    audit=[]
    def get(ab):
        a,b=ab;data,meta=request(url,a,b)
        return a,b,data,{'phase':phase,'start':a,'end':b,'bytes':len(data),'status':meta['status'],'content_range_verified':True,'sha256':meta['sha256'],'endpoint':'S3' if meta['url']==url else 'Azure'}
    with ThreadPoolExecutor(max_workers=8) as ex, sparse.open('r+b') as f:
        for future in as_completed([ex.submit(get,x) for x in merged]):
            a,b,data,rec=future.result();f.seek(a);f.write(data);audit.append(rec)
    return audit

def column_ranges(pf,rgs,predicate):
    ranges=[]
    for rg in rgs:
        for i in range(pf.metadata.num_columns):
            cc=pf.metadata.row_group(rg).column(i)
            if not predicate(cc.path_in_schema):continue
            off=min(x for x in [cc.dictionary_page_offset,cc.data_page_offset] if x is not None and x>=4)
            ranges.append((off,off+cc.total_compressed_size-1))
    return ranges

def filter_table(tab):
    bb=tab['bbox'].combine_chunks();x=np.asarray(bb.field('xmin'));y=np.asarray(bb.field('ymin'))
    addresses=tab['addresses'].to_pylist()
    ru=np.asarray([any(a.get('country')=='RU' for a in (v or [])) for v in addresses])
    mask=country_mask(x,y)
    broad=((x>=19)&(y>=41)&(y<=83))|((x<=-168)&(y>=60))
    keep=broad&(ru|mask)
    return keep,ru,mask

def run(obj):
    name=Path(obj['key']).name;stem=name.split('-')[1];dest=OUT/f'overture_ru_selected_{stem}.parquet';auditfile=OUT/f'{stem}_acquisition.json'
    if dest.exists() and auditfile.exists():
        old=json.loads(auditfile.read_text())
        if old.get('source_url')!=obj['url'] or old.get('release')!=obj['key'].split('/')[1]:raise ValueError('A different release/source already occupies this output; do not overwrite immutable inputs')
        if hashlib.sha256(dest.read_bytes()).hexdigest()==old['selected_sha256']:print(stem,'existing verified',flush=True);return old
    info=json.loads((RAW/(name+'.metadata.json')).read_text());rgs=eligible_rg(info)
    if not rgs:
        return {'file':name,'candidate_row_groups':0,'selected_rows':0,'downloaded_data_bytes':0,'status':'spatially_pruned_by_footer'}
    footer=(RAW/(name+'.footer')).read_bytes()
    with tempfile.TemporaryDirectory(prefix='overture_partial_') as tmp:
        sparse=Path(tmp)/'sparse.parquet'
        with sparse.open('wb') as f:f.truncate(obj['size']);f.write(b'PAR1');f.seek(obj['size']-len(footer));f.write(footer)
        pf=pq.ParquetFile(sparse)
        pred=lambda c:c.startswith('bbox.') or c=='addresses.list.element.country'
        r1=column_ranges(pf,rgs,pred)
        print(stem,'phase1',len(rgs),'groups',sum(b-a+1 for a,b in r1),'bytes',flush=True)
        aud=asyncio.run(ranges_download(obj['url'],r1,sparse,'country_bbox'))
        relevant=[];masks={};phase1_rows=0
        for rg in rgs:
            tab=pf.read_row_group(rg,columns=['bbox','addresses.list.element.country'])
            keep,ru,inside=filter_table(tab);phase1_rows+=len(tab)
            if keep.any():relevant.append(rg);masks[rg]=keep
        tops={'id','geometry','confidence','addresses','names','sources','operating_status','basic_category','taxonomy','version','bbox'}
        r2=column_ranges(pf,relevant,lambda c:c.split('.')[0] in tops and not pred(c))
        print(stem,'phase2',len(relevant),'groups',sum(b-a+1 for a,b in r2),'bytes',flush=True)
        aud+=asyncio.run(ranges_download(obj['url'],r2,sparse,'attributes_selected'))
        tables=[]
        for rg in relevant:
            tab=pf.read_row_group(rg,columns=sorted(tops)).filter(pa.array(masks[rg]));tables.append(tab)
        table=pa.concat_tables(tables) if tables else pa.Table.from_batches([],schema=pa.schema([pf.schema_arrow.field(c) for c in sorted(tops)]))
        pending=dest.with_suffix('.parquet.partial')
        pq.write_table(table,pending,compression='zstd')
        with pending.open('rb') as durable:os.fsync(durable.fileno())
        assert pq.read_table(pending).equals(table)
        pending.replace(dest)
    summary={'source_file':name,'source_url':obj['url'],'release':obj['key'].split('/')[1],'candidate_row_groups':len(rgs),'attribute_row_groups':len(relevant),'candidate_rows_screened':phase1_rows,'selected_rows':len(table),'selected_columns':sorted(tops),'selection':'initial Russia-enclosing bbox; address_countryRU OR NaturalEarthRUSpolygon; flags retained downstream; not legal boundary assertion','world_polygon_sha256':hashlib.sha256(WORLD.read_bytes()).hexdigest(),'footer_sha256':info['footer_sha256'],'schema_inspected_before_data':True,'downloaded_data_bytes':sum(x['bytes'] for x in aud),'range_records':aud,'selected_file':dest.name,'selected_bytes':dest.stat().st_size,'selected_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'whole_upstream_downloaded_or_SHA_verified':False,'status':'selected_verified'}
    auditfile.write_text(json.dumps(summary,indent=2));print(stem,'selected',len(table),'downloadbytes',summary['downloaded_data_bytes'],flush=True);return summary

if __name__=='__main__':
    manifest=json.loads((RAW/'source_manifest.json').read_text());results=[]
    for obj in manifest['files']:results.append(run(obj))
    summary={'release':manifest['release'],'source_global_bytes':manifest['global_bytes_not_downloaded'],'selected_rows':sum(x['selected_rows'] for x in results),'downloaded_data_bytes':sum(x['downloaded_data_bytes'] for x in results),'source_files':results,'all_files_scoped':len(results)==len(manifest['files'])}
    (ROOT/'ACQUISITION.json').write_text(json.dumps(summary,indent=2));print('ALL',summary['selected_rows'],summary['downloaded_data_bytes'],flush=True)

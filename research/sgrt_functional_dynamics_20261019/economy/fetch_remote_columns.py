#!/usr/bin/env python3
"""Inspect remote Parquet footer, then fetch only requested column chunks.

Sparse temporary files preserve column offsets. Complete upstream bytes are NOT
downloaded or claimed SHA-verified; upstream LFS hash is metadata only.
"""
import argparse,asyncio,concurrent.futures,hashlib,json,os,struct,tempfile,time,urllib.request
from pathlib import Path
import pyarrow.parquet as pq
import aiohttp

WANTED=['inn','oktmo','okved','okved_section','filed']
REVISION='bde9b8b129a8be582b66de4e30ed79c9187a8515'
OUTPUT_STEM='identity_function_selected'
FOOTER_CACHE_DIR=None
def get(url,start,end,retries=3):
 last=None
 for trial in range(retries):
  try:
   # Standard direct-download endpoint; never trust a cached range response
   # without checking Content-Range and exact byte length below.
   u=url+'?download=true'
   req=urllib.request.Request(u,headers={'Range':f'bytes={start}-{end}','User-Agent':'SGRT-research/1.0'})
   with urllib.request.urlopen(req,timeout=45) as r:
    data=r.read(end-start+2)
    if r.status!=206 or len(data)!=end-start+1 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
     raise ValueError(f'Unexpected range response {r.status}, bytes={len(data)}, header={r.headers.get("Content-Range")}')
    return data
  except Exception as e:last=e
 raise last
def run(year,tree,out):
 obj=next(x for x in tree if x.get('path')==f'RFSD/year={year}/part-0.parquet');size=obj['size']
 url=f'https://huggingface.co/datasets/irlspbru/RFSD/resolve/{REVISION}/{obj["path"]}'
 acquisition=out/f'{year}_acquisition.json'
 if acquisition.exists():
  old=json.loads(acquisition.read_text());dest=out/old.get('selected_file','not_exists')
  if old.get('pinned_dataset_commit')==REVISION and old.get('available_requested_columns')==WANTED and old.get('verified_column_chunks') and dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest()==old.get('selected_file_sha256'):
   print(f'Year {year}: existing pinned column selection hash verified',flush=True);return {'year':year,'status':'verified_existing'}
 t=time.time();cache=(FOOTER_CACHE_DIR if FOOTER_CACHE_DIR is not None else out)/f'{year}_metadata.footer'
 if cache.exists():footer=cache.read_bytes();assert footer[-4:]==b'PAR1'
 else:
  tail=get(url,size-8,size-1);footer_size=struct.unpack('<I',tail[:4])[0];assert tail[4:]==b'PAR1'
  footer=get(url,size-footer_size-8,size-1);cache.write_bytes(footer)
 with tempfile.TemporaryDirectory(prefix=f'rfsd_{year}_') as tmp:
  sparse=Path(tmp)/'source_sparse.parquet'
  with open(sparse,'wb') as f:f.truncate(size);f.seek(0);f.write(b'PAR1');f.seek(size-len(footer));f.write(footer)
  pf=pq.ParquetFile(sparse)
  schema={'year':year,'rows':pf.metadata.num_rows,'num_columns':len(pf.schema.names),'num_row_groups':pf.metadata.num_row_groups,'schema':str(pf.schema_arrow),'available_requested_columns':[c for c in WANTED if c in pf.schema.names],'upstream_url':url,'pinned_dataset_commit':REVISION,'upstream_bytes':size,'upstream_LFS_sha256_metadata_not_download_verified':obj.get('lfs',{}).get('oid'),'footer_bytes':len(footer),'footer_sha256':hashlib.sha256(footer).hexdigest(),'schema_inspected_before_column_download':True}
  (out/f'{year}_schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2))
  assert set(WANTED).issubset(pf.schema.names)
  ranges=[]
  for rg in range(pf.metadata.num_row_groups):
   for ci,c in enumerate(pf.schema.names):
    if c not in WANTED:continue
    cc=pf.metadata.row_group(rg).column(ci)
    off=min(v for v in [cc.dictionary_page_offset,cc.data_page_offset] if v is not None and v>=4)
    ranges.append((off,off+cc.total_compressed_size-1))
  # Coalesce adjacent chunks without downloading whole unrelated columns.
  merged=[]
  for start,end in sorted(ranges):
   if merged and start<=merged[-1][1]+4096:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
   else:merged.append((start,end))
  print(f'Year {year}: metadata inspected; {len(merged)} column ranges, {sum(e-s+1 for s,e in merged)} bytes',flush=True)
  async def download():
   # Reuse verified object URL and pooled connections. The signed URL is ephemeral
   # and stays in memory only; never include it in logs or provenance.
   connector=aiohttp.TCPConnector(limit=24)
   timeout=aiohttp.ClientTimeout(total=45)
   async with aiohttp.ClientSession(trust_env=True,connector=connector,timeout=timeout) as session:
    async with session.get(url+'?download=true',headers={'Range':'bytes=0-3'}) as response:
     head=await response.read();assert response.status==206 and head==b'PAR1';object_url=str(response.url)
     object_headers={k:response.headers.get(k) for k in ['ETag','Last-Modified','Content-Range']}
    semaphore=asyncio.Semaphore(24)
    async def fetch(r):
     start,end=r
     async with semaphore:
      error=None
      for trial in range(3):
       try:
        async with session.get(object_url,headers={'Range':f'bytes={start}-{end}'}) as response:
         data=await response.read()
         if response.status!=206 or len(data)!=end-start+1 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
          raise ValueError(f'Invalid range status={response.status}; length={len(data)}; expected={end-start+1}')
         return r,data
       except Exception as e:error=e
      raise RuntimeError(f'Failed byte range {start}-{end}: {type(error).__name__}')
    chunk_audit=[]
    with open(sparse,'r+b') as f:
     for i,future in enumerate(asyncio.as_completed([fetch(r) for r in merged]),1):
      (start,end),data=await future;f.seek(start);f.write(data)
      chunk_audit.append({'start':start,'end':end,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'http_status':206,'content_range_verified':True})
      if i%500==0:print(f'Year {year}: {i}/{len(merged)} column ranges',flush=True)
    return object_headers,sorted(chunk_audit,key=lambda x:x['start'])
  object_headers,chunk_audit=asyncio.run(download())
  table=pq.read_table(sparse,columns=WANTED)
  dest=out/f'rfsd_{year}_{OUTPUT_STEM}.parquet';pq.write_table(table,dest,compression='zstd')
  read=pq.read_table(dest);assert table.equals(read)
  summary={**schema,'downloaded_range_count':len(merged)+3,'downloaded_bytes_including_metadata':len(footer)+12+sum(e-s+1 for s,e in merged),'column_ranges':merged,'verified_column_chunks':chunk_audit,'object_response_headers':object_headers,'selected_file':dest.name,'selected_file_bytes':dest.stat().st_size,'selected_file_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'elapsed_seconds':time.time()-t,'whole_selected_table_readback':True,'whole_upstream_SHA_verified':False}
  (out/f'{year}_acquisition.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
  print(json.dumps({'year':year,'rows':len(table),'selected_bytes':dest.stat().st_size,'downloaded_bytes':summary['downloaded_bytes_including_metadata'],'seconds':time.time()-t}),flush=True)
  return {'year':year,'status':'downloaded_verified'}
def main():
 global WANTED,OUTPUT_STEM,FOOTER_CACHE_DIR
 ap=argparse.ArgumentParser();ap.add_argument('--tree',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--years',nargs='+',type=int,required=True);ap.add_argument('--parallel-years',type=int,default=1);ap.add_argument('--columns',nargs='+');ap.add_argument('--output-stem',default=OUTPUT_STEM);ap.add_argument('--footer-cache-dir',type=Path);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);tree=json.loads(a.tree.read_text());WANTED=a.columns or WANTED;OUTPUT_STEM=a.output_stem;FOOTER_CACHE_DIR=a.footer_cache_dir
 def safe_run(year):
  try:return run(year,tree,a.out)
  except Exception as e:
   error={'year':year,'status':'failed','error_type':type(e).__name__,'error_classification':'verified_operation_failure_not_global_source_unavailability','pinned_dataset_commit':REVISION}
   (a.out/f'{year}_failed_attempt.json').write_text(json.dumps(error,indent=2));print(json.dumps(error),flush=True);return error
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.parallel_years) as ex:results=list(ex.map(safe_run,a.years))
 (a.out/'CALENDAR_ACQUISITION.json').write_text(json.dumps({'pinned_dataset_commit':REVISION,'years':results,'all_requested_years_verified':all(r['status']!='failed' for r in results)},indent=2))
 if any(r['status']=='failed' for r in results):raise SystemExit(1)
if __name__=='__main__':main()

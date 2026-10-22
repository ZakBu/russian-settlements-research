"""Publish byte-exact structured research data as deduplicated ZIP release assets."""
import os,json,pathlib,subprocess,hashlib,zipfile,sys,time,argparse,shutil
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workdir',type=pathlib.Path,required=True)
parser.add_argument('--catalog',type=pathlib.Path,default=pathlib.Path('data/catalog.json'))
args=parser.parse_args()
ROOT=args.workdir;ROOT.mkdir(parents=True,exist_ok=True)
REPO='ZakBu/russian-settlements-research';TAG='sgrt-research-data-20261022-v1';CAT=ROOT/'catalog.json';GD=ROOT/'source.git'
if not CAT.exists():shutil.copyfile(args.catalog,CAT)
sys.path.insert(0,str(ROOT/'pythondeps'));import pyarrow.parquet as pq
E={**os.environ,'GIT_DIR':str(GD),'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
def run(a,data=None,env=None):
 r=subprocess.run(a,input=data,capture_output=True,env=env)
 if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-3000:])
 return r.stdout
if not GD.exists():
 run(['git','clone','--bare','--filter=blob:none','--single-branch','--branch','research/sgrt-final-protocol-20261018','https://github.com/'+REPO+'.git',str(GD)])
baseline_pack_files={p.name for p in (GD/'objects/pack').iterdir()}
remote_probe=subprocess.run(['gh','api','repos/'+REPO+'/releases/tags/'+TAG],capture_output=True,text=True)
if remote_probe.returncode==0 and any(a['name']=='catalog.json' for a in json.loads(remote_probe.stdout)['assets']):
 run(['gh','release','download',TAG,'--repo',REPO,'--pattern','catalog.json','--dir',str(ROOT),'--clobber'])
cat=json.loads(CAT.read_text());cat.setdefault('schemas',{})
notes=ROOT/'release_notes.md';notes.write_text('Данные исследования СГРТ: исходные опубликованные структурированные файлы в Parquet и других форматах, без изменения значений. ZIP хранит каждый уникальный объект один раз; catalog.json восстанавливает исходные пути и содержит контрольные суммы.\n\nНаличие данных прежнего расчёта не подтверждает фактические связи СГРТ. Новая функциональная модель пока не рассчитана.\n')
if subprocess.run(['gh','release','view',TAG,'--repo',REPO],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
 run(['gh','release','create',TAG,'--repo',REPO,'--target','f06bf2578878c5c6d34d25b6541988cde30bed42','--title','СГРТ: переносимые исследовательские данные, 22.10.2026','--notes-file',str(notes),'--draft'])
def checkpoint():
 CAT.write_text(json.dumps(cat,ensure_ascii=False,indent=2)+'\n')
 run(['gh','release','upload',TAG,str(CAT),'--repo',REPO,'--clobber'])
checkpoint()
for n,asset in enumerate(cat['assets']):
 if asset['status']=='verified':continue
 print(json.dumps({'phase':'fetch','asset':asset['asset'],'index':n+1,'of':len(cat['assets']),'raw_bytes':asset['uncompressed_bytes']}),flush=True)
 run(['git','-c','gc.auto=0','-c','fetch.negotiationAlgorithm=noop','fetch','--no-tags','--no-write-fetch-head','--filter=blob:none','origin','--stdin'],('\n'.join(asset['objects'])+'\n').encode(),E)
 archive=ROOT/asset['asset'];members=[]
 with zipfile.ZipFile(archive,'w',allowZip64=True) as z:
  for sha in asset['objects']:
   obj=cat['objects'][sha];rawpath=ROOT/'current_object';h=hashlib.sha256();g=hashlib.sha1(b'blob '+str(obj['bytes']).encode()+b'\0');count=0
   proc=subprocess.Popen(['git','cat-file','blob',sha],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=E)
   with open(rawpath,'wb') as out:
    while b:=proc.stdout.read(4*1024*1024):out.write(b);h.update(b);g.update(b);count+=len(b)
   err=proc.stderr.read();assert proc.wait()==0,err.decode();assert count==obj['bytes'];assert g.hexdigest()==sha
   actual=h.hexdigest()
   if obj.get('sha256'):assert obj['sha256']==actual
   obj['sha256']=actual
   if obj['source_path'].endswith('.parquet'):
    p=pq.ParquetFile(rawpath);fields=[{'name':f.name,'type':str(f.type),'nullable':f.nullable} for f in p.schema_arrow]
    sid=hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest();cat['schemas'][sid]={'fields':fields};obj['schema_id']=sid;obj['rows']=p.metadata.num_rows
   compression=zipfile.ZIP_DEFLATED if obj['source_path'].endswith(('.csv','.geojson')) else zipfile.ZIP_STORED
   z.write(rawpath,'objects/'+sha,compress_type=compression,compresslevel=6 if compression else None);rawpath.unlink()
   members.append({'blob':sha,'bytes':count,'sha256':actual})
  z.writestr('objects_manifest.json',json.dumps({'source_commit':cat['source_commit'],'objects':members},ensure_ascii=False,indent=2))
 h=hashlib.sha256()
 with open(archive,'rb') as f:
  while b:=f.read(4*1024*1024):h.update(b)
 digest=h.hexdigest();print(json.dumps({'phase':'upload','asset':asset['asset'],'zip_bytes':archive.stat().st_size}),flush=True)
 run(['gh','release','upload',TAG,str(archive),'--repo',REPO,'--clobber'])
 remote=json.loads(run(['gh','api','repos/'+REPO+'/releases/tags/'+TAG]));a=next(a for a in remote['assets'] if a['name']==asset['asset'])
 assert a['size']==archive.stat().st_size;assert a['digest']=='sha256:'+digest
 asset.update(status='verified',bytes=a['size'],sha256=digest,url=a['browser_download_url'],asset_id=a['id']);checkpoint();archive.unlink()
 # Only auxiliary cache packs created by this shard are removed; metadata cloned at startup is retained.
 for cached in (GD/'objects/pack').iterdir():
  if cached.name not in baseline_pack_files:cached.unlink()
 print(json.dumps({'phase':'verified','asset':asset['asset'],'completed':n+1,'of':len(cat['assets']),'digest':digest}),flush=True)
cat['status']='verified_complete';cat['counts']['zip_bytes']=sum(a['bytes'] for a in cat['assets']);cat['counts']['unique_parquet_schemas']=len(cat['schemas']);checkpoint()
run(['gh','release','edit',TAG,'--repo',REPO,'--draft=false','--latest=false'])
print(json.dumps({'status':'complete','counts':cat['counts'],'tag':TAG}),flush=True)

import io,urllib.request,struct,zipfile,pathlib,csv,json,zlib,hashlib,concurrent.futures
base=pathlib.Path('/workspace/shared/tochno-20261013');out=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/tochno_catalog_20261013')
rows=list(csv.reader(open(out/'population_indicators.csv')))[1:];rows=[r for r in rows if int(float(r[2])) in [8112014,8112015,8112016,8112021,8112022,8112023]]
def extract(r):
 u=r[8];head=urllib.request.urlopen(urllib.request.Request(u,method='HEAD'),timeout=60);size=int(head.headers['Content-Length']);requests=[]
 def rng(a,b):
  resp=urllib.request.urlopen(urllib.request.Request(u,headers={'Range':f'bytes={a}-{b}'}),timeout=180)
  assert resp.status==206,(u,resp.status)
  assert resp.headers['Content-Range']==f'bytes {a}-{b}/{size}',resp.headers
  data=resp.read();assert len(data)==b-a+1
  requests.append({'start':a,'end':b,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});return data
 tail=rng(max(0,size-65557),size-1);offset=tail.rfind(b'PK\x05\x06');assert offset>=0
 e=struct.unpack('<4s4H2LH',tail[offset:offset+22]);cdsize,cdstart=e[5:7];assert cdstart+cdsize<size
 cd=rng(cdstart,cdstart+cdsize-1)
 # zipfile reads a synthetic directory-only archive; correct offsets separately through ZipInfo.
 fake=io.BytesIO(cd+struct.pack('<4s4H2LH',b'PK\x05\x06',0,0,e[3],e[4],cdsize,0,0));z=zipfile.ZipFile(fake)
 candidates=[x for x in z.infolist() if x.filename.endswith('.parquet') and '/' not in x.filename and '__MACOSX' not in x.filename]
 if not candidates:
  import re
  years={}
  for item in z.infolist():
   match=re.search(r'_year(\d{4})_',item.filename)
   if match and item.filename.endswith(('.parquet','.xlsx','.csv')):
    year=match.group(1);rank={'.parquet':0,'.xlsx':1,'.csv':2}[pathlib.Path(item.filename).suffix]
    if year not in years or rank<years[year][0]:years[year]=(rank,item)
  candidates=[years[y][1] for y in sorted(years)]
 assert candidates
 result=[]
 for x in candidates:
  a=x.header_offset
  hdr=rng(a,a+29);fields=struct.unpack('<4s5H3L2H',hdr);assert fields[0]==b'PK\x03\x04';start=a+30+fields[-2]+fields[-1]
  comp=rng(start,start+x.compress_size-1)
  data=zlib.decompress(comp,-15) if x.compress_type==8 else comp
  assert len(data)==x.file_size;assert zlib.crc32(data)&0xffffffff==x.CRC
  if x.filename.endswith('.parquet'):assert data[:4]==data[-4:]==b'PAR1'
  path=base/pathlib.Path(x.filename).name;path.write_bytes(data)
  rec={'indicator':int(float(r[2])),'source_url':u,'version':'20260928','zip_bytes':size,'zip_etag':head.headers.get('ETag'),'zip_sha256':None,'member':x.filename,'member_compressed_bytes':x.compress_size,'member_bytes':len(data),'member_crc32':f'{x.CRC:08x}','member_sha256':hashlib.sha256(data).hexdigest(),'local_path':str(path),'requests':requests.copy()}
  result.append(rec)
 (out/('range_'+str(int(float(r[2])))+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
 return result
records=[x for group in concurrent.futures.ThreadPoolExecutor(3).map(extract,rows) for x in group];(out/'range_receipts.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print([(x['indicator'],x['member_bytes'],x['local_path']) for x in records])

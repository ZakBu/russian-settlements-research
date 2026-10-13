import urllib.request,urllib.parse,pathlib,re,hashlib,json,concurrent.futures,time,html
RAW=pathlib.Path('/workspace/shared/rsfsr1989_rural_volga');E=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_volga_20261013')
rows=[json.loads(x) for x in (E/'tatarica_download_manifest.jsonl').read_text().splitlines()]
sample=pathlib.Path(rows[0]['path']).read_text()
ids=re.findall(r'<li[^>]*data-CID=\"(\d+)\"[^>]*>\s*([^<]*?район)\s*</li>',sample,re.S)
categories=[{'url':'https://tatarica.org/chapter/'+cid,'cid':cid,'district_name':re.sub(r'\s+',' ',name).strip()} for cid,name in ids]
print('categories',len(categories),flush=True)
def go(r):
 s='CCM_CID = '+r['cid'];m=re.search(r'CCM_CID\s*=\s*(\d+)',s)
 if not m:return {'category':r['url'],'error':'No CCM_CID'}
 data={'limit':'300','offset':'0','cID':m.group(1)};u='https://tatarica.org/chapter/get_more_articles'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,data=urllib.parse.urlencode(data).encode()),timeout=30).read();p=RAW/('tatarica_category_'+m.group(1)+'.html');p.write_bytes(b);s=b.decode();links=list(set(urllib.parse.urljoin(u,html.unescape(x)) for x in re.findall(r'href=[\"\']([^\"\']+)',s)))
  return {'category':r['url'],'district_name':r.get('district_name'),'url':u,'post_form':data,'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'links':links,'http_status':200}
 except Exception as e:return {'category':r['url'],'district_name':r.get('district_name'),'url':u,'post_form':data,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:out=list(ex.map(go,categories))
(E/'tatarica_category_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));urls=set(json.loads((RAW/'tatarica_urls.json').read_text()));urls.update(y for x in out for y in x.get('links',[]) if '/ru/razdely/municipalnye-obrazovaniya/municipalnye-rajony/' in y);(RAW/'tatarica_urls.json').write_text(json.dumps(sorted(urls),ensure_ascii=False,indent=2));print('urls',len(urls),'errors',[x for x in out if 'error' in x],flush=True)

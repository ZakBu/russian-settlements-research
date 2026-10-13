import urllib.request,urllib.parse,json,gzip,hashlib,datetime
from pathlib import Path
OUT=Path(__file__).resolve().parent
def fetch(base,params,filename):
 u=base+'?'+urllib.parse.urlencode(params);b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=45).read()
 with gzip.open(OUT/filename,'wb') as f:f.write(b)
 return json.loads(b),{'url':u,'response_sha256':hashlib.sha256(b).hexdigest(),'compressed_sha256':hashlib.sha256((OUT/filename).read_bytes()).hexdigest(),'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'file':filename}
pages=json.load(gzip.open(OUT/'wikipedia_live_revision_response.json.gz','rt'))['query']['pages']
d,m=fetch('https://ru.wikipedia.org/w/api.php',{'action':'query','format':'json','formatversion':'2','prop':'revisions|pageprops|coordinates','rvprop':'ids|timestamp|content','rvslots':'main','titles':'Пашковский (посёлок)|Московский (город)','redirects':'1','colimit':'max'},'corrected_titles_revision_response.json.gz');pages+=d['query']['pages'];qids=[r.get('pageprops',{}).get('wikibase_item') for r in pages if r.get('pageprops',{}).get('wikibase_item') and not r.get('pageprops',{}).get('disambiguation')=='']
d,wm=fetch('https://www.wikidata.org/w/api.php',{'action':'wbgetentities','format':'json','ids':'|'.join(qids),'props':'claims|labels|descriptions|sitelinks','languages':'ru'},'live_wikidata_entities.json.gz')
(OUT/'secondary_entities_fetch_manifest.json').write_text(json.dumps([m,wm],ensure_ascii=False,indent=2))
for q,e in d.get('entities',{}).items():
 print('\nENTITY',q,e.get('labels',{}).get('ru',{}).get('value'))
 for c in e.get('claims',{}).get('P1082',[]):
  qual=c.get('qualifiers',{});date=[v.get('datavalue',{}).get('value',{}).get('time') for v in qual.get('P585',[])];print(c.get('mainsnak',{}).get('datavalue',{}).get('value'),date,c.get('rank'))

import json,csv,urllib.request,urllib.parse,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent
rows=[x for x in csv.DictReader(open(E.parent/'rsfsr1989_primary_binding_20261013/primary_bindings.csv'))if not x['binding_status'].startswith('bound') and x['qualified_historical_region']=='Санкт-Петербург']
renames={'Петродворец':'Петергоф'}
def search(x):
 name=renames.get(x['source_name_parsed_for_binding'],x['source_name_parsed_for_binding']);u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbsearchentities',search=name,language='ru',format='json',limit=10));fn='search_'+hashlib.sha256(name.encode()).hexdigest()[:12]+'.json';b=(E/fn).read_bytes()if(E/fn).exists()else b'';d=json.loads(b)if b else {}; (E/fn).write_bytes(b)if b else None;return dict(source_record_id=x['source_record_id'],name=name,search_url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),results=d.get('search',[]))
a=[]
for x in concurrent.futures.ThreadPoolExecutor(5).map(search,rows):a.append(x)
(E/'search_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2))
qids=sorted({y['id']for x in a for y in x['results'][:3]});u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbgetentities',ids='|'.join(qids),props='labels|aliases|descriptions|claims',languages='ru',format='json'));b=urllib.request.urlopen(u,timeout=30).read();(E/'entities.json').write_bytes(b);print(len(rows),len(qids));d=json.loads(b)
admins=sorted({z['mainsnak'].get('datavalue',{}).get('value',{}).get('id')for x in d['entities'].values()for z in x.get('claims',{}).get('P131',[])if z['mainsnak'].get('datavalue',{}).get('value',{}).get('id')});u2='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbgetentities',ids='|'.join(admins),props='labels|claims',languages='ru',format='json'));b2=urllib.request.urlopen(u2,timeout=30).read();(E/'admins.json').write_bytes(b2);print('admins',admins)
(E/'entity_receipts.json').write_text(json.dumps([dict(url=u,path='entities.json',sha256=hashlib.sha256(b).hexdigest()),dict(url=u2,path='admins.json',sha256=hashlib.sha256(b2).hexdigest())],indent=2))

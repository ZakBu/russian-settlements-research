import csv,json,re,urllib.request,urllib.parse,hashlib,time
from pathlib import Path
E=Path(__file__).resolve().parent;P=E.parent
old={x['source_record_id']for x in csv.DictReader(open(P/'rsfsr1989_external_points_20261013/external_point_delta.csv'))};r=[x for x in csv.DictReader(open(P/'rsfsr1989_primary_binding_20261013/primary_bindings.csv'))if not x['binding_status'].startswith('bound')and x['source_record_id']not in old];r.sort(key=lambda x:-int(x['population_total']));target=r[:35];names={x['source_name_parsed_for_binding']for x in target};aliases={'Шпаковское':'Михайловск','Каспийский':'Лагань','Лянторский':'Лянтор','Кодинский':'Кодинск','Петрокрепость':'Шлиссельбург','Теучежск':'Адыгейск'};data=[]
for x in target:
 n=x['source_name_parsed_for_binding'];q=aliases.get(n,n);u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbsearchentities',search=q,language='ru',uselang='ru',format='json',limit=5));fn='search_'+hashlib.sha256(q.encode()).hexdigest()[:12]+'.json'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();(E/fn).write_bytes(b);z=json.loads(b);entry=dict(source_record_id=x['source_record_id'],name=n,query=q,region=x['qualified_historical_region'],url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),results=z.get('search',[]));print(n,x['population_total'],[(a['id'],a.get('label'),a.get('description'))for a in entry['results'][:3]],flush=True)
 except Exception as e:entry=dict(source_record_id=x['source_record_id'],name=n,query=q,url=u,error=str(e));print(n,str(e),flush=True)
 data.append(entry);(E/'search_receipts.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));time.sleep(.2)
(E/'target_rows.json').write_text(json.dumps(target,ensure_ascii=False,indent=2))

import csv,json,urllib.request,urllib.parse,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent;P=E.parent
alias={'Сырский':'Сырский Рудник','Холмский':'Холмская','Кодинский':'Кодинск','Кинель-Черкасы':'Кинель-Черкассы','Багаевский':'Багаевская','Алтайский':'Алтайское','Михайловский':'Михайловское','Правдинск':'Правдинск (Балахна)','Кочетовка':'Кочетовка (Мичуринск)','Моховая':'Моховая (Кунгур)','Красный Октябрь':'Красный Октябрь (Владимирская область)'}
old={x['source_record_id']for fn in ['rsfsr1989_external_points_20261013/external_point_delta.csv','rsfsr1989_external_points_delta2_20261013/external_point_delta2.csv']for x in csv.DictReader(open(P/fn))};rows=[x for x in csv.DictReader(open(P/'rsfsr1989_primary_binding_20261013/primary_bindings.csv'))if not x['binding_status'].startswith('bound')and x['source_record_id']not in old];rows.sort(key=lambda x:-int(x['population_total']));(E/'target_rows.json').write_text(json.dumps(rows[:40],ensure_ascii=False,indent=2));(E/'authorized_variants.json').write_text(json.dumps(alias,ensure_ascii=False,indent=2))
# Cached QIDs/public entity search only for explicit named variants.
def get(n):
 query=alias[n];u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbsearchentities',search=query,language='ru',uselang='ru',format='json',limit=5));fn='search_'+hashlib.sha256(query.encode()).hexdigest()[:12]+'.json'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();(E/fn).write_bytes(b);return dict(name=n,query=query,url=u,path=fn,sha256=hashlib.sha256(b).hexdigest(),results=json.loads(b).get('search',[]))
 except Exception as e:return dict(name=n,query=query,url=u,error=str(e))
a=[]
for n in alias:
 z=get(n);a.append(z);(E/'search_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print(n,[(x['id'],x.get('label'),x.get('description'))for x in z.get('results',[])[:3]],z.get('error'),flush=True)
 if '429'in z.get('error',''):break

import json,urllib.request,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent
selected={'Кочетовка':'Q28667386','Моховая':'Q60850477','Красный Октябрь':'Q4239557','Тацинский':'Q3980033','Тюльган':'Q4467426','Шипуново':'Q2236290','Покровка':'Q2100935','Крыловская':'Q3277082','Починки':'Q2106536','Толбазы':'Q4459655','Выльгорт':'Q2284109','Месягутово':'Q1924337','Бессоновка':'Q4085856','Бакалы':'Q4075849','Мамонтово':'Q4280028'}
def get(q):
 u='https://www.wikidata.org/wiki/Special:EntityData/'+q+'.json';fp=E/('entity_'+q+'.json')
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();fp.write_bytes(b);d=json.loads(b)['entities'][q];r=dict(qid=q,url=u,path=fp.name,sha256=hashlib.sha256(b).hexdigest());s=d.get('sitelinks',{}).get('ruwiki')
  if s:
   b2=urllib.request.urlopen(urllib.request.Request(s['url'],headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();fn='article_'+q+'.html';(E/fn).write_bytes(b2);r['article']=dict(title=s['title'],url=s['url'],path=fn,sha256=hashlib.sha256(b2).hexdigest())
  return r
 except Exception as e:return dict(qid=q,url=u,error=str(e))
a=list(concurrent.futures.ThreadPoolExecutor(3).map(get,selected.values()));(E/'entity_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));(E/'selected_candidates.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2));print('received',sum('path'in x for x in a),'articles',sum('article'in x for x in a))

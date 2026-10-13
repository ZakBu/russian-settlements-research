import json,urllib.request,concurrent.futures,hashlib
from pathlib import Path
E=Path(__file__).resolve().parent
selected={'Шпаковское':['Q159112'],'Нововятск':['Q136545928','Q4323399'],'Лянторский':['Q157850'],'Красноармейская':['Q1021749'],'Отрадная':['Q1010105'],'Вербовский':['Q4107522'],'Новая Усмань':['Q2003465'],'Каспийский':['Q156614'],'Чегем Первый':['Q197890'],'Петрокрепость':['Q15339'],'Теучежск':['Q102521'],'Куеда':['Q6449106']}
for x in json.load(open(E/'cached_candidates.json')):
 if len(x['candidate_qids'])==1 and x['population_total']>=3000:selected.setdefault(x['historical_name'],[x['candidate_qids'][0]['qid']])
for x in json.load(open(E/'article_receipts.json')):
 if x.get('qid_matches'):selected[x['title'].split(' (')[0]]=list(set(x['qid_matches']))
def get(q):
 u='https://www.wikidata.org/wiki/Special:EntityData/'+q+'.json';p=E/('entity_'+q+'.json')
 try:
  b=p.read_bytes()if p.exists()else urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();p.write_bytes(b);return dict(qid=q,url=u,path=p.name,sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:return dict(qid=q,url=u,error=str(e))
qs=sorted({q for a in selected.values()for q in a});r=list(concurrent.futures.ThreadPoolExecutor(3).map(get,qs));(E/'entity_receipts.json').write_text(json.dumps(r,indent=2));(E/'selected_candidates.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2));print('selected',len(selected),'qids',len(qs),'received',sum('path'in x for x in r))

import json,urllib.request,hashlib,concurrent.futures
from pathlib import Path
E=Path(__file__).resolve().parent
selected={'Зеленогорск':'Q46850','Колпино':'Q154738','Кронштадт':'Q155863','Ломоносов':'Q157688','Павловск':'Q177888','Петергоф':'Q178310','Пушкин':'Q7947','Сестрорецк':'Q194084','Александровская':'Q1964326','Белоостров':'Q1267638','Комарово':'Q260832','Левашово':'Q2993085','Лисий Нос':'Q1266569','Металлострой':'Q1267630','Парголово':'Q905431','Песочный':'Q3376279','Понтонный':'Q3397766'}
def get(q):
 u='https://www.wikidata.org/wiki/Special:EntityData/'+q+'.json';p=E/('entity_'+q+'.json')
 try:
  b=p.read_bytes()if p.exists()else urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=20).read();p.write_bytes(b);return dict(qid=q,url=u,path=p.name,sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:return dict(qid=q,url=u,error=str(e))
r=list(concurrent.futures.ThreadPoolExecutor(3).map(get,selected.values()));(E/'physical_entity_receipts.json').write_text(json.dumps(r,indent=2));(E/'selected_search_candidates.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2));print(r)

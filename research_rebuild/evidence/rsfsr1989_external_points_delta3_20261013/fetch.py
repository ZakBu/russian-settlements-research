import json,urllib.request,concurrent.futures,hashlib,shutil
from pathlib import Path
E=Path(__file__).resolve().parent;P=E.parent
selected={'Сырский':'Q4448121','Холмский':'Q1968861','Кодинский':'Q154648','Кинель-Черкасы':'Q1004270','Багаевский':'Q19426941','Алтайский':'Q434087','Михайловский':'Q258845','Правдинск':'Q4375848','Понтонный':'Q3397766','Отрадная':'Q1010105'}
for q,sub in [('Q3397766','rsfsr1989_external_points_20261013'),('Q1010105','rsfsr1989_external_points_delta2_20261013')]:shutil.copyfile(P/sub/('entity_'+q+'.json'),E/('entity_'+q+'.json'))
def get(q):
 u='https://www.wikidata.org/wiki/Special:EntityData/'+q+'.json';fp=E/('entity_'+q+'.json')
 try:
  b=fp.read_bytes()if fp.exists()else urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();fp.write_bytes(b);d=json.loads(b)['entities'][q];r=dict(qid=q,url=u,path=fp.name,sha256=hashlib.sha256(b).hexdigest());s=d.get('sitelinks',{}).get('ruwiki')
  if s:
   art='article_'+q+'.html';a=urllib.request.urlopen(urllib.request.Request(s['url'],headers={'User-Agent':'settlements-research/1.0'}),timeout=15).read();(E/art).write_bytes(a);r['article']=dict(title=s['title'],url=s['url'],path=art,sha256=hashlib.sha256(a).hexdigest())
  return r
 except Exception as e:return dict(qid=q,url=u,error=str(e))
a=list(concurrent.futures.ThreadPoolExecutor(3).map(get,selected.values()));(E/'entity_receipts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));(E/'selected_candidates.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2));print('received',sum('path'in x for x in a),'articles',sum('article'in x for x in a))

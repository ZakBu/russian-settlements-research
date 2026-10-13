from pathlib import Path
import urllib.request,urllib.parse,json,gzip
O=Path(__file__).parent
names=['Воскресенское (посёлок, Москва)','Ватутинки (посёлок)','Московский (город)','Института полиомиелита','Газопровод (посёлок)','Коммунарка (посёлок, Москва)','Мосрентген (посёлок)','Марьино (посёлок, Москва)','Филимонки','Совхоза имени 1 Мая','Марушкино','Совхоза «Крёкшино»','Яковлевское (деревня, Москва)','Первомайское (посёлок, Москва)','Птичное (посёлок)','Ремзавод (посёлок)','Дома отдыха «Вороново»','ЛМС','Клёново (Москва)','Красная Пахра (село)','Шишкин Лес (посёлок)','Рогово (посёлок, Москва)','Фабрики имени 1 Мая (посёлок)','Остафьево (посёлок)','Знамя Октября','Ерино (посёлок)','Щапово (посёлок, Москва)','Новогорск','Купавна (микрорайон)','Болшево','Первомайский (Королёв)','Текстильщик (Королёв)','Никольско-Архангельский','Салтыковка','Сходня','Новоподрезково','Фирсановка','Яковлево (Москва)']
params={'action':'query','format':'json','formatversion':2,'titles':'|'.join(names),'redirects':1,'prop':'coordinates|revisions','colimit':'max','rvprop':'ids|timestamp|content','rvslots':'main'}
req=urllib.request.Request('https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params),headers={'User-Agent':'SettlementSourceResearch/1.0'})
with urllib.request.urlopen(req,timeout=70) as r:
 raw=r.read();status=r.status;headers=r.headers
(O/'moscow_exact_ownwiki_http_receipt.json').write_text(json.dumps({'status':status,'retry_after':headers.get('Retry-After'),'title_count':len(names)},indent=2))
d=json.loads(raw)
with gzip.open(O/'moscow_exact_ownwiki_batch.json.gz','wt',encoding='utf8') as f:json.dump(d,f,ensure_ascii=False)
print('OK',len(raw),len(d.get('query',{}).get('pages',[])))

from pathlib import Path
import gzip,json,urllib.request,urllib.parse,datetime,hashlib
O=Path(__file__).parent
names=['Лёдово','Ледово','Ледово (посёлок, городской округ Кашира)','Ледово (посёлок, Каширский район)','Лёдово (посёлок, Каширский район)','Пешково (село)','Пешково (сельское поселение Стремиловское)','Пешково (сельское поселение Баранцевское)','Алёшино (слободка, Московская область)','Алещино','Щурово (Коломенский район)','Захарово (сельское поселение Новохаритоновское)','Захарово (сельское поселение Рыболовское)','Юдино (посёлок, Московская область)','Луч (посёлок, Щёлковский район)','Тимоховский','Посёлок участка № 2','Холмогорка','Санатория Звенигород','Абрамцево (Балашихинский район)']
for i in range(0,len(names),40):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(names[i:i+40]),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40)as r:b=r.read(12000000);status=r.status
  f=O/f'own_wikipedia_batch{i//40+4}.json.gz';f.write_bytes(gzip.compress(b));j=json.loads(b); rows=[dict(title=p['title'],missing='missing'in p,pageid=p.get('pageid'),revid=p.get('revisions',[{}])[0].get('revid'),point=p.get('coordinates'))for p in j.get('query',{}).get('pages',{}).values()];(O/f'fetch_batch{i//40+4}_receipt.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),request_url=u,normal_TLS=True,status=status,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),pages=rows),ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False))
 except Exception as e:print(type(e).__name__,str(e))

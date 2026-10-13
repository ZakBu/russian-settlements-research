from pathlib import Path
import gzip,json,urllib.request,urllib.parse,hashlib
O=Path(__file__).parent;titles=['Гришенки','Поповка (городское поселение Кратово)','Поповка (сельское поселение Сафоновское)','Масловский (посёлок)','Молодёжный (городской округ Подольск)','Петровское (Ленинский городской округ)','Успенский (Московская область)','Луговая (Лобня)','Шеметово (Сергиево-Посадский городской округ)','Кудиново (Богородский городской округ)'];qids=[]
for f in O.glob('own_wikipedia_batch*.json.gz'):
 for p in json.load(gzip.open(f,'rt'))['query']['pages'].values():
  if p['title']in titles and p.get('pageprops',{}).get('wikibase_item'):qids.append(p['pageprops']['wikibase_item'])
u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(dict(action='wbgetentities',ids='|'.join(sorted(set(qids))),props='labels|claims|descriptions',languages='ru',format='json'))
with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=40)as r:b=r.read(8000000)
f=O/'own_wikidata_entity_claims.json.gz';f.write_bytes(gzip.compress(b));(O/'own_entities_fetch_receipt.json').write_text(json.dumps(dict(url=u,normal_TLS=True,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),own_qids=sorted(set(qids))),ensure_ascii=False,indent=2));j=json.loads(b)
for q,e in j['entities'].items():
 pops=[]
 for claim in e.get('claims',{}).get('P1082',[]):
  v=claim.get('mainsnak',{}).get('datavalue',{}).get('value',{});dates=[z.get('datavalue',{}).get('value',{}).get('time')for z in claim.get('qualifiers',{}).get('P585',[])];pops.append((v.get('amount'),dates))
 print(q,e.get('labels',{}).get('ru',{}).get('value'),pops,'owncodes',{pr:[z.get('mainsnak',{}).get('datavalue',{}).get('value')for z in e.get('claims',{}).get(pr,[])]for pr in ['P721','P764']})

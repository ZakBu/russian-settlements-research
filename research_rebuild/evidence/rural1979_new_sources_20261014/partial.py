from pathlib import Path
from bs4 import BeautifulSoup
import re,json,hashlib,collections
root=Path('/workspace/shared/rural1979_new_sources');maps={r['provider_district_prefix']:r for r in json.loads((root/'adminmap.json').read_text())};rows=[]
regs={'33':'Кировская область','88':'Марийская АССР','92':'Татарская АССР','94':'Удмуртская АССР'}
for p in root.glob('perepis1979_pages_*.html'):
 if 'source' in p.name:continue
 b=p.read_bytes();s=BeautifulSoup(b,'lxml')
 for tr in s.select('table.sticky-enabled > tbody > tr'):
  td=tr.find_all('td',recursive=False);v=[c.get_text(' ',strip=True) for c in td]
  if len(v)==16 and re.fullmatch(r'\d+',v[0]):
   rows.append(dict(year=1979,region=regs.get(v[0][:2]),district_name=maps.get(v[0][:4],{}).get('district_name'),provider_id=v[0],provider_district_prefix=v[0][:4],provider_selsovet_prefix=v[0][:7],settlement_type=v[2],name=v[3],present_total=v[9],permanent_total=v[12],population_category=v[13],archive_locator=v[14],source_url='https://rodnaya-vyatka.ru/perepis1979/pages/'+p.stem.split('_')[-1],source_sha256=hashlib.sha256(b).hexdigest(),retrieved_date='2026-10-14',linked_place_url=next(('https://rodnaya-vyatka.ru'+a['href'] for a in td[1].find_all('a',href=True) if '/places/' in a['href']),None),raw_cells=v))
p=root/'partial_rows.jsonl';p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows));print(len(rows),dict(collections.Counter(r['region'] for r in rows)),flush=True)

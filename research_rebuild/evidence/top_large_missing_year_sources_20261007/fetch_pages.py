from pathlib import Path
import urllib.request,urllib.parse,json,gzip,hashlib,datetime
OUT=Path(__file__).resolve().parent
TITLES=['Железнодорожный (Балашиха)','Климовск','Пашковский','Калинино (Краснодар)','Юбилейный (Королёв)','Власиха (Московская область)','Сходня','Никольско-Архангельский','Придонской','Кедровка (Кемерово)','Косая Гора','Московский (Москва)','Северо-Задонск','Востряково (Домодедово)','Новосиликатный']
query={'action':'query','format':'json','formatversion':'2','prop':'revisions|pageprops|coordinates','rvprop':'ids|timestamp|content','rvslots':'main','titles':'|'.join(TITLES),'redirects':'1','colimit':'max'}
url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(query)
r=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=45);body=r.read();d=json.loads(body)
with gzip.open(OUT/'wikipedia_live_revision_response.json.gz','wb') as f:f.write(body)
(OUT/'fetch_manifest.json').write_text(json.dumps({'requested_titles':TITLES,'url':url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'response_sha256':hashlib.sha256(body).hexdigest(),'saved_file_sha256':hashlib.sha256((OUT/'wikipedia_live_revision_response.json.gz').read_bytes()).hexdigest(),'bytes_uncompressed':len(body)},ensure_ascii=False,indent=2))
for page in d.get('query',{}).get('pages',[]):
 text=page.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','')
 print('\nPAGE',page['title'],page.get('pageprops',{}).get('wikibase_item'),len(text))
 for line in text.splitlines():
  if ('2021' in line or '2010' in line or 'Численность населения' in line or 'Население' in line or 'Год переписи' in line or 'Год census' in line):print(line[:700])

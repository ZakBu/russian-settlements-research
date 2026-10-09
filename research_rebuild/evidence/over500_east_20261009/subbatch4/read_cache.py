from pathlib import Path
import gzip,json,re,hashlib
O=Path(__file__).parent
T=['Озёрное (Башкортостан)','Ишемгул','Арсёново (Башкортостан)','Крымский (Башкортостан)','Первомайская (Башкортостан)','Родниковка (Башкортостан)','Улуелга (Белорецкий район)','Дюмеево','Нижнеяркеево','Алагузово','Турналы','Комсомольского Отделения','Лоза (Удмуртия)','Кушья','Пижил','Люкшудья']
terms=['совхоза «Иняк»','совхоза «Янгильский»','Озёрного отделения','Озерного отделения','Раевского совхоза','Арслановского совхоза','Миякинский РТС','конезавода № 119','конезавода 119','Берёзовского спиртзавода','Сосновского отделения']
out=[]
for f in sorted(Path('/workspace/settlements-raw/data/raw/wikipedia_articles').glob('batch_*.json.gz')):
 try:j=json.load(gzip.open(f));pages=j.get('payload',j).get('query',{}).get('pages',[]);pages=pages.values()if isinstance(pages,dict)else pages
 except Exception:continue
 for p in pages:
  txt=p.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','')
  if p.get('title')in T or any(t.lower()in txt.lower()for t in terms):out.append(dict(source_path=str(f),source_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),page=p))
with gzip.open(O/'cached_own_pages.json.gz','wt')as f:json.dump(out,f,ensure_ascii=False)
print([x['page']['title']for x in out])

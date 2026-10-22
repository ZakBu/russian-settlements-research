"""Record verified data publication; never asserts new scientific results."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
catalog=json.loads(Path('data/catalog.json').read_text())
assert catalog['status']=='verified_complete'
assert all(a['status']=='verified' for a in catalog['assets'])
now=datetime.now(ZoneInfo('Europe/Moscow')).isoformat()
p=Path('research_context/current_state.json');state=json.loads(p.read_text());state['updated_moscow']=now;state['data_transfer']={'status':'verified_complete','catalog':'data/catalog.json','release_tag':catalog['release_tag'],'counts':catalog['counts'],'verification':'Every extracted source blob matched Git SHA-1 and SHA-256; each uploaded ZIP matched GitHub server SHA-256 digest. Parquet schemas recorded.'};p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
with open('research_context/diary/2026-10-22.md','a') as f:
 f.write('\n## '+now+' — завершение переноса данных\n\n')
 f.write('Автоматическая упаковка завершена. Каталог: data/catalog.json. Релиз: '+catalog['release_tag']+'.\n\n')
 f.write('Проверенные итоги: '+json.dumps(catalog['counts'],ensure_ascii=False)+'.\n\n')
 f.write('Каждый объект побайтно сопоставлен с исходным Git-хешем и SHA-256; ZIP проверены по серверным SHA-256 GitHub. Схемы Parquet сохранены в каталоге. Это проверка переноса, а не новая проверка научной модели. Новая функциональная модель не рассчитана.\n')

"""Index reviewed studies without upgrading their recorded reading depth."""
import csv,json,re
from pathlib import Path
P=Path(__file__).resolve().parent
rows=[]
for block in ['china','usa','russia','methods']:
 f=P/block/('studies_'+block+'.json')
 d=json.loads(f.read_text())
 for x in d['studies']:
  citation=x.get('citation')
  if not citation:
   citation='{} ({}). {}. {}'.format(x.get('authors',''),x.get('year',''),
    x.get('title',''),x.get('journal',x.get('venue','')))
  read=x.get('reading',x.get('reading_status',x.get('read_scope','')))
  if isinstance(read,dict):read=json.dumps(read,ensure_ascii=False)
  doi=x.get('doi') or ''
  doi=re.sub(r'^https?://(dx\.)?doi\.org/','',doi).lower().strip()
  rows.append({'block':block,'id':x.get('id',''),'citation':citation,'doi':doi,
   'primary_url':x.get('url',x.get('primary_url','')),
   'geography':x.get('country',x.get('geography','methodological')),
   'reading_scope':read,'record_file':str(f.relative_to(P))})
assert len(rows)==33,len(rows)
assert len([r for r in rows if r['block']=='china'])==10
assert len([r for r in rows if r['block']=='usa'])==8
assert len([r for r in rows if r['block']=='russia'])==8
assert len([r for r in rows if r['block']=='methods'])==7
keys=[r['doi'] or r['primary_url'] or r['citation'] for r in rows]
assert len(set(keys))==len(keys),'Duplicate bibliography record'
with (P/'evidence_index.csv').open('w',newline='',encoding='utf-8-sig') as h:
 w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lines=['Библиография и фактическая глубина чтения','24 октября 2026 года',
 'Целевой обзор: 26 предметных исследований и 7 общих методических опор.',
 'Американский блок включает один австралийский сравнительный случай.',
 'Скачивание оригинала не означает чтение всех его страниц.','']
for block,label in [('china','Китай'),('usa','США и сравнительная субурбия'),
                    ('russia','Россия'),('methods','Общие методы')]:
 lines.append(label)
 for r in rows:
  if r['block']!=block:continue
  lines.extend([r['citation'],'DOI: '+r['doi'] if r['doi'] else 'DOI не указан.',
    r['primary_url'],'Прочитано: '+str(r['reading_scope']),''])
(P/'BIBLIOGRAPHY.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
plan=P/'RESEARCH_PLAN.txt';s=plan.read_text()
s=re.sub(r'(?<=\d)(?=[А-Яа-яЁё])|(?<=[А-Яа-яЁё])(?=\d)', ' ', s)
s=s.replace('сПВЗ','с ПВЗ').replace('типНП','тип НП')
plan.write_text(s,encoding='utf-8')
print({'indexed_records':len(rows),'unique_doi_or_url_keys':len(set(keys)),
 'plan_words':len(s.split()),'plan_chars':len(s)})

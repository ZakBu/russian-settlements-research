#!/usr/bin/env python3
"""Curated named findings from a dated empirical paper; no automatic causal flag."""
from pathlib import Path
from lxml import html
import hashlib,json
import pandas as pd
H=Path(__file__).resolve().parent
p=H/'sources/transsib_industrial_functions2017.html';tree=html.fromstring(p.read_bytes());text=' '.join(' '.join(tree.itertext()).split())
assert tree.xpath('//meta[@name="citation_doi"]/@content')==['10.22363/2313-2329-2017-25-4-553-565']
assert 'В Анжеро-Судженске' in text and 'В Ачинске' in text and 'Так, в Петровск-Забайкальском' in text
axis=pd.read_parquet(H.parent/'axis/full_settlement_axis.parquet')
claims={'Петровск-Забайкальский':'Металлургический завод прекратил деятельность; исследование относит город к максимуму сокращения людности среди городов Транссиба1990–2015.','Анжеро-Судженск':'Ликвидированы нерентабельные шахты угледобывающей промышленности, которые были градообразующими.','Ачинск':'Прекратили работу предприятия нескольких отраслей; исследование констатирует сужение и изменение градообразующих промышленных функций, сохранились глиноземный комбинат и НПЗ.'}
rows=[]
for town,claim in claims.items():
 c=axis[axis.name.eq(town)&axis.type.eq('город')];assert len(c)==1
 rows.append({'id':c.iloc[0].id,'name':town,'published_industrial_function_contraction_history':True,'claim':claim,'research_period':'1990–2015','publication_year':2017,'source_class':'peer-reviewed empirical geographic research; primary analysis with partly secondary plant references','source_doi':'10.22363/2313-2329-2017-25-4-553-565','source_url':'https://journals.rudn.ru/economics/article/view/18230/en_US','authors':'Миронова М.Н.; Кузнецова Н.Г.; Шолудько А.Н.','article_title':'Типы городов Транссибирской железной дороги: динамика численности населения и промышленных функций','source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'entire_industrial_base_lost_proven':None,'absence_of_replacement_by_2021_proven':None,'2010_2021_specific_industrial_decline_measured':None,'national_industrial_decline_flag_mutated':False})
pd.DataFrame(rows).to_parquet(H/'industrial_function_contraction_research2017.parquet',index=False)
receipt={'rows':3,'period':'1990–2015','scope':'Independent published contraction history, not merely monoindustrial designation; does not prove complete2010–2021 industrial collapse or absence of replacement','nationalfeatures_changed':False,'extraction':'Curated three literal named findings; unique city name matches; not NLP-inferred population causes'}
(H/'industrial_function_contraction_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(receipt)

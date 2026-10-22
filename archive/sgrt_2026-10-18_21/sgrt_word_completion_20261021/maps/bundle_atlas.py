#!/usr/bin/env python3
"""Assemble fourteen source-backed PDF plates; per-level type supplements remain separate."""
from pathlib import Path
import argparse,hashlib,json
from pypdf import PdfWriter,PdfReader
H=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,required=True);m=p.parse_args().model_dir.resolve()
names=['01_axis_road_coverage','02_functional_evidence',f'03_road_hierarchy_{m.name}',f'04_nine_word_types_{m.name}','05_settlement_demographic_dynamics','06_ethnic_composition_context','07_agro_climate_soil','08_municipal_sown_share_2008','09_current_monotowns_2026',f'10_center_rural_dynamics_{m.name}',f'11_regional_sgrt_{m.name}','12_experimental_bonitet_intervals',f'13_demographic_source_recovery_{m.name}','14_municipal2008_vs_regional2021_land']
titles={'01':'Поселенческая ось и дорожный охват','02':'Независимые функциональные свидетельства','03':'Дорожная иерархия СГРТ','04':'Девять Word-типов: правила и гипотезы','05':'Исходная демографическая ось','06':'Этнические ответы переписи2021','07':'Агроклимат и почвенная оценка FAO','08':'Муниципальная посевная доля2008','09':'Юридические категории моногородов2026','10':'Динамика центра и сельского окружения','11':'Три фиксированных региональных окна','12':'Экспериментальные интервалы бонитета','13':'Влияние первичной поправки2010','14':'Разные пространственные уровни земельных источников'}
manifest={r['figure']:r for r in json.loads((H/'map_manifest.json').read_text())};writer=PdfWriter();inputs={}
for name in names:
 r=manifest[name]
 for relative,expected in r['inputs'].items():assert hashlib.sha256((H.parent/relative).read_bytes()).hexdigest()==expected,f'Changed figure source: {relative}'
 pdf=H/f'{name}.pdf';record=next(x for x in r['outputs'] if x['path']==pdf.name);actual=hashlib.sha256(pdf.read_bytes()).hexdigest();assert actual==record['sha256'];inputs[pdf.name]=actual;writer.append(pdf,outline_item=name[:2]+'. '+titles[name[:2]])
writer.add_metadata({'/Title':'СГРТ России: карты измеренных данных и расчетных гипотез','/Subject':m.name+'; preliminary research; full Word rules and operational hypotheses separate','/Author':'russian-settlements-research'})
out=H/f'atlas_{m.name}.pdf';tmp=out.with_suffix('.tmp.pdf')
with tmp.open('wb') as f:writer.write(f)
tmp.replace(out);pages=len(PdfReader(out).pages);assert pages==14
receipt={'configuration':m.name,'pages':pages,'output':out.name,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'input_pdf_sha256':inputs,'full_scientific_acceptance_implied':False,'scope':'Fourteen actual plates; source quality and nonproven causal mechanisms retained; per-level type posters separate'}
(H/f'atlas_{m.name}_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))

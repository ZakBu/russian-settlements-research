"""Independent raw-source recount and deterministic24-row review of Choya shops.

Writes only shops_peer_review.json and shops_peer_review.txt beside this script.
Does not import or execute the original shops extractor.
Run:PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 shops_peer_review.py
"""
from pathlib import Path
from collections import Counter
import hashlib,json,re,unicodedata

import pandas as pd
import pyarrow.parquet as pq
from docx import Document
import xlrd

OUT=Path(__file__).resolve().parent
SHOPS=OUT.parent/'shops'
RAW=SHOPS/'raw'
KEY='source_record_id_2021'


def text(value):
    return ' '.join(str(value if value is not None else '').split())


def letters(value):
    return re.sub('[^а-я]','',text(value).lower().replace('ё','е'))


def integer(value):
    if re.fullmatch(r'\d+(?:\.0+)?',text(value)):
        return int(float(text(value)))
    return None


def main():
    basefile=OUT.parents[1]/'national/national_target_source2021.parquet'
    base=pq.read_table(basefile).to_pandas()
    target=base[(base.region_2021=='алтай')&base.district_2021.str.contains('Чой',na=False)]
    assert len(target)==21 and target[KEY].is_unique
    lookup={letters(r.name_2021):(r.name_2021,getattr(r,KEY))for r in target.itertuples(index=False)}
    assert len(lookup)==21
    def identify(address,review=False):
        # Extract the explicit address NP token, then look it up in the fixed21-NP frame.
        found=re.search(r'(?<![а-яё])(?:село|поселок|посёлок|деревня|с|п|д)(?:\.\s*|\s+)([а-яё-]+)',
                        address,re.I)
        candidate=letters(found.group(1))if found else None
        repair=None
        if review and candidate=='караккоша'and 'строител'in address.lower()and '1/1'in address:
            candidate='каракокша';repair='reviewed spelling transposition, own raw2019/2020 anchor checked'
        if review and not found and re.search(r'(?<!\w)\.Чоя\b',address,re.I):
            candidate='чоя';repair='reviewed truncated prefix .Чоя in fixed district'
        result=lookup.get(candidate)
        return (result[0],result[1],repair)if result else(None,None,None)

    independent=[];source_meta=[];section_counts=[];exclusions=[];all_raw={}
    for year in range(2019,2027):
        path=RAW/f"choya_{year}_0{'.docx'if year<2021 else'.xls'}"
        if year<2021:
            source=Document(path)
            rows=[[c.text for c in row.cells]for row in source.tables[0].rows]
            address_col=7
        else:
            book=xlrd.open_workbook(path)
            sheet=book.sheet_by_name('торговый реестр')
            rows=[sheet.row_values(i)for i in range(sheet.nrows)]
            address_col=4
        all_raw[year]=rows
        date_strings=re.findall(r'01\.01\.\d{4}',' '.join(text(c)for row in rows[:4]for c in row))
        assert set(date_strings)=={f'01.01.{year}'}
        start=next(i for i,row in enumerate(rows)if letters(row[0])=='предприятияторговли')
        stop=next(i for i,row in enumerate(rows[start+1:],start+1)if letters(row[0]).startswith('предприятиямелкойрозницы'))
        headers=[]
        for i in range(start+1,stop):
            first=letters(rows[i][0])
            if first in ['продовольственные','непродовольственные','смешанные']:
                headers.append((i,{'продовольственные':'food','непродовольственные':'nonfood','смешанные':'mixed'}[first]))
        assert [c for _,c in headers]==['food','nonfood','mixed']
        year_counts=Counter();precounts=Counter();unnumbered=Counter()
        for h,(begin,category)in enumerate(headers):
            end=headers[h+1][0]if h+1<len(headers)else stop
            for i in range(begin+1,end):
                row=rows[i];number=integer(row[0])
                name=text(row[2] if year==2020 else row[1]);address=text(row[address_col])
                if number is None:
                    if name and address and not letters(row[0]).startswith(('итого','итоги')):
                        unnumbered[category]+=1
                    continue
                if not name or not address:continue
                precounts[category]+=1
                reason=None
                if re.search(r'\bАЗС\b|автозаправ',name,re.I):reason='fuel_store'
                elif re.search(r'киоск|лар[её]к|автолав|передвиж|палатк',name,re.I):reason='nonstationary'
                elif re.search(r'ozon|озон|wildber|вайлд|вилд|\bwb\b|выдач|маркетплейс',' '.join(map(text,row)),re.I):reason='pickup_text_requires_combination_review'
                strict_np,strict_id,_=identify(address)
                reviewed_np,reviewed_id,repair=identify(address,True)
                rec={'year':year,'category':category,'source_file':path.name,'source_row':i+1,
                    'number':number,'name':name,'address':address,'strict_np':strict_np,
                    'strict_id':strict_id,'reviewed_np':reviewed_np,'reviewed_id':reviewed_id,
                    'repair':repair,'included':reason is None,'exclusion_reason':reason,
                    'source_section_start_row':begin+1,'source_section_end_before_row':end+1}
                if reason:exclusions.append(rec)
                else:independent.append(rec);year_counts[category]+=1
        section_counts.append({'year':year,'source_trade_section':{'start':start+1,'end_before':stop+1},
            'numbered_before_exclusions':dict(precounts),'ordinary_after_exclusions':dict(year_counts),
            'unnumbered_named_address_rows_not_counted':dict(unnumbered)})
        source_meta.append({'year':year,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'internal_date_verified':True,'raw_rows':len(rows)})

    original=pd.read_csv(SHOPS/'choya_numbered_ordinary_shop_entries_2019_2026.csv').fillna('')
    source_index={(r['year'],r['source_row']):r for r in independent}
    assert len(independent)==len(source_index)==705
    mismatches=[]
    for row in original.to_dict('records'):
        key=(int(row['year']),int(row['source_row']))
        check=source_index.get(key)
        if check is None:
            mismatches.append({'key':key,'reason':'not independently included'});continue
        comparisons={'name':text(row['name_raw'])==check['name'],
            'address':text(row['address_raw'])==check['address'],'category':row['category']==check['category'],
            'number':int(row['source_number'])==check['number'],
            'strict_target_NP':(row['name_2021']or None)==check['strict_np'],
            'reviewed_target_NP':(row['reviewed_name_2021']or None)==check['reviewed_np']}
        if not all(comparisons.values()):mismatches.append({'key':key,'checks':comparisons})
    assert not mismatches,mismatches[:5]
    samples=[]
    for year in range(2019,2027):
        for category in ['food','nonfood','mixed']:
            pool=[r for r in independent if r['year']==year and r['category']==category]
            # Exercise centre/periphery, postal shops and spelling sensitivity deterministically.
            if category=='nonfood':
                preferred=[r for r in pool if(r['reviewed_np']=='Чоя')==(year%2==1)]
            elif category=='mixed':
                preferred=[r for r in pool if r['repair']]or[r for r in pool if re.search('почта|почтамп',r['name'],re.I)]
            else:
                preferred=[r for r in pool if(r['reviewed_np']=='Чоя')==(year%2==0)]
            chosen=min(preferred or pool,key=lambda r:(hashlib.sha256((r['source_file']+':'+str(r['source_row'])).encode()).hexdigest(),r['source_row']))
            samples.append({**chosen,'sample_selection':'one per category/date; deterministic role/edgecase stratum then SHA256minimum',
                'source_row_name_address_category_verified':True})
    assert len(samples)==24
    exclusion_controls=[]
    ex=pd.read_csv(SHOPS/'choya_excluded_objects.csv').fillna('')
    for year in range(2019,2027):
        rows=all_raw[year];address_col=7 if year<2021 else 4
        for section in ['small_nonstationary','pharmacy','fuel']:
            pool=ex[(ex.year==year)&(ex.major_section==section)]
            assert len(pool)>0
            check=pool.sort_values('source_row').iloc[0]
            i=int(check.source_row)-1;raw=rows[i]
            raw_name=text(raw[2] if year==2020 else raw[1])
            assert raw_name==text(check.name_raw)
            assert text(raw[address_col])==text(check.address_raw)
            assert(year,i+1)not in source_index
            prefix={'small_nonstationary':'предприятиямелкойрозницы',
                'pharmacy':'аптеки','fuel':'автозаправоч'}[section]
            heading=next(k for k,row in enumerate(rows)if letters(row[0]).startswith(prefix))
            assert heading<i
            assert not any(letters(row[0]).startswith(('предприятияобщественного','рестораныкафе',
                'предприятияхлебопечения','аптеки','автозаправоч'))for row in rows[heading+1:i])
            exclusion_controls.append({'year':year,'section':section,'source_row':i+1,
                'name':raw_name,'address':text(raw[address_col]),'source_section_heading_row':heading+1,
                'source_section_heading':text(rows[heading][0]),'excluded_from_ordinary_verified':True})
    # The two late fuel-related numbered rows are excluded even inside the mixed-shop section.
    assert len(exclusions)==2 and all(x['year']in[2025,2026]and x['exclusion_reason']=='fuel_store'for x in exclusions)
    parsed=[]
    for year in range(2019,2027):
        for role in ['centre','surroundings']:
            group=[r for r in independent if r['year']==year and ('centre'if r['reviewed_np']=='Чоя'else'surroundings')==role]
            assert all(r['reviewed_np']for r in group)
            parsed.append({'year':year,'role':role,'ordinary':len(group),
                'food':sum(r['category']=='food'for r in group),
                'nonfood':sum(r['category']=='nonfood'for r in group),
                'mixed':sum(r['category']=='mixed'for r in group)})
    results={(r['year'],r['role']):r for r in parsed}
    for y,c,s,nc,ns in [(2019,32,67,18,19),(2024,28,55,15,15)]:
        assert results[y,'centre']['ordinary']==c and results[y,'surroundings']['ordinary']==s
        assert results[y,'centre']['nonfood']==nc and results[y,'surroundings']['nonfood']==ns
    def change(metric,counts=results):
        a=counts[2019,'centre'][metric];b=counts[2019,'surroundings'][metric]
        c=counts[2024,'centre'][metric];d=counts[2024,'surroundings'][metric]
        return{'centre2019':a,'surroundings2019':b,'centre2024':c,'surroundings2024':d,
            'centre_change_pct':(c/a-1)*100,'surroundings_change_pct':(d/b-1)*100,
            'centre_share2019':a/(a+b),'centre_share2024':c/(c+d),
            'centre_share_change_pp':(c/(c+d)-a/(a+b))*100}
    # The unnumbered continuation may identify another operator at the same store.
    assert sum(sum(r['unnumbered_named_address_rows_not_counted'].values())for r in section_counts)==267
    alias_checks=[]
    for rec in independent:
        if rec['repair']and'Карак'in rec['address']:
            anchors=[r for r in independent if r['year']in[2019,2020]and r['reviewed_np']=='Каракокша'
                     and'1/1'in r['address']and'строител'in r['address'].lower()and'запчаст'in r['name'].lower()]
            assert len(anchors)==2
            alias_checks.append({'year':rec['year'],'source_row':rec['source_row'],'raw':rec['address'],
                'reviewed_NP':rec['reviewed_np'],'anchor_source_rows':[(r['year'],r['source_row'])for r in anchors]})
    # Source-level content check independent of original reported hash.
    canonical=lambda y:[[text(c)for c in row]for row in all_raw[y][5:]]
    identical22_23=canonical(2022)==canonical(2023)
    assert identical22_23
    numeric_header_exclusions=ex[(ex.source_row==5)&ex.name_raw.str.fullmatch(r'2(?:\.0)?')]
    assert len(numeric_header_exclusions)==6
    postal=lambda row:bool(re.search(r'почтамп|почта|уфпс|почтов',row['name'],re.I))
    postal_rows=[r for r in independent if postal(r)]
    assert len(postal_rows)==55
    postal_excluded={}
    for year in range(2019,2027):
        for role in ['centre','surroundings']:
            group=[r for r in independent if r['year']==year and not postal(r)
                and('centre'if r['reviewed_np']=='Чоя'else'surroundings')==role]
            postal_excluded[year,role]={'ordinary':len(group),'nonfood':sum(r['category']=='nonfood'for r in group)}
    report={'status':'PASS counts and row identity; minor metadata caveat in excluded-object tally',
        'independent_of_original_extractor':'Original extraction code read for scope, never imported/executed; separate source-section bounded recount used.',
        'source_files':source_meta,'target_NPs_n':len(target),'target_region':'RepublicAltai','target_district':'ChoyaDistrict',
        'centre_accepted_id':lookup['чоя'][1],'ordinary_rows_recounted':len(independent),
        'all705_source_name_address_category_number_and_NP_links_match':True,
        'section_recounts':section_counts,'deterministic24_shop_sample':samples,
        'excluded_function_controls':exclusion_controls,'fuel_rows_inside_shop_sections_excluded':exclusions,
        'category_role_counts':parsed,'2019_2024_comparison':{'ordinary':change('ordinary'),'nonfood':change('nonfood')},
        'reviewed_typo_anchor_checks':alias_checks,'2022_2023_table_content_identical_after_title':identical22_23,
        'minor_metadata_issue':{'original_excluded_rows':len(ex),'column_header_rows_in_excluded_table':len(numeric_header_exclusions),
            'interpretation':'The230excluded rows include6numeric column-header artefacts; do not call230a count of excluded real objects. Included705shop outcomes unaffected.'},
        'postal_label_sensitivity':{'postal_label_rows_n':len(postal_rows),
            'reason':'Numbered retail-section rows with postal operator names are source-classified shops, but separate physical retail vs postal-counter identity is not independently verified; they are not automatically marketplace PVZ.',
            'exclude_all_postal_names_2019_2024':change('ordinary',postal_excluded),
            'nonfood_result_unchanged':change('nonfood',postal_excluded)==change('nonfood')},
        'limits':['Physical-shop registry entries, not legal-entity counts, customer flows, revenues or actual functional catchments.',
            'Combined shop+pickup functionality is unobserved; lack of explicit marketplace words is not proof of no PVZ.',
            'Listed-entry loss is not independently confirmed closure.',
            'Postal operator label is kept only where the source explicitly lists a numbered shop in a retail section.',
            'The two spelling repairs belong to a reviewed sensitivity, not automatic overwriting of strict links.',
            'No causal attribution to WB/Ozon and no national representativeness established.'],
        'hypothesis_assessment':'Both centre and surroundings have fewer listed shop entries2019–2024,but surroundings decline faster;centre share increases slightly. This does not support automatic relative weakening of the centre on this metric. It neither proves stronger actual centrality nor rules out marketplace mechanisms on other outcomes.'}
    (OUT/'shops_peer_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    ordinary=change('ordinary');nonfood=change('nonfood')
    postal_sensitivity=change('ordinary',postal_excluded)
    narrative=f'''Независимый аудит дислокаций магазинов Чойского района

Проверены все 8 исходных DOCX/XLS за 2019–2026 годы. Чужой экстрактор не
исполнялся: выполнен отдельный пересчёт в границах трёх розничных секций.
Все 705 включённых строк совпали по исходной строке, номеру, названию,
адресу, категории и строгой/проверенной привязке НП. Выбраны 24
детерминированных магазина: по одному на категорию и дату. Подробные
поля и проверки сохранены в JSON. Проверены также 24 исключения из НТО,
аптек и АЗС по их собственным исходным секциям, а также 2 магазина при
АЗС внутри смешанной розницы 2025/2026 годов.

Подтверждены числа за 2019 год: Чоя — 32, окружение — 67 обычных
магазинных записей; непродовольственные — 18 и 19. За 2024 год:
Чоя — 28, окружение — 55; непродовольственные — 15 и 15.
Доля Чои в перечисленных магазинах составляет
{ordinary['centre_share2019']*100:.2f}% → {ordinary['centre_share2024']*100:.2f}%
({ordinary['centre_share_change_pp']:+.2f} п.п.); в непродовольственных —
{nonfood['centre_share2019']*100:.2f}% → {nonfood['centre_share2024']*100:.2f}%
({nonfood['centre_share_change_pp']:+.2f} п.п.).

Число перечисленных записей обычной розницы изменилось в центре на
{ordinary['centre_change_pct']:.2f}%, в окружении на
{ordinary['surroundings_change_pct']:.2f}%; непродовольственной — на
{nonfood['centre_change_pct']:.2f}% и {nonfood['surroundings_change_pct']:.2f}%.
Это не поддерживает гипотезу автоматического относительного ослабления
центра на данной метрике: его доля немного увеличилась. Усиление
фактического тяготения этим тоже не доказано: нет потоков, оборотов,
ассортимента, установленной сопоставимой полноты и причинной оценки.

Целевая ось содержит 21 принятый НП Республики Алтай/Чойского района.
НП определяется по адресу магазина, а не юридическому адресу владельца.
Две исходные ошибки — «.Чоя» и «Караккоша» — исправлены лишь в отдельной
чувствительности. Для второй независимо найдены правильные записи
магазина «Запчасти», Строителей 1/1, в обоих исходниках 2019/2020 годов.
267 ненумерованных строк с именами операторов/деталями не добавлены
автоматически как дополнительные магазины. Единица результата — именно
нумерованная магазинная запись реестра, а не зарегистрированное юрлицо.

55 строк имеют почтовые наименования, но стоят в нумерованной розничной
секции. Их физическая розничная функция вне самого реестра не проверена;
их нельзя автоматически приравнять к маркетплейсным ПВЗ. Проверено
исключение всех почтовых наименований: 2019 — центр 31/окружение 60;
2024 — центр 28/окружение 50. Доля центра
{postal_sensitivity['centre_share2019']*100:.2f}% →
{postal_sensitivity['centre_share2024']*100:.2f}%
({postal_sensitivity['centre_share_change_pp']:+.2f} п.п.). Знак вывода
сохраняется; непродовольственный результат не меняется.

Ограничения: содержимое торговых таблиц 2022 и 2023 годов после заголовка
совпадает; копирование/необновление исключить нельзя. Нумерованные строки
2025/2026 расходятся с напечатанными итогами. В CSV из 230 исключённых
строк есть 6 артефактов числовой шапки: это не 230 реальных объектов.
На 705 включённых магазинных строк это замечание не влияет. Отсутствие
маркировки ПВЗ не доказывает отсутствие совмещённых форматов.
Исчезновение строки не названо закрытием. Причинный эффект WB/Ozon
не установлен; один район не представляет всю Россию.

Проверка завершена. Исходные данные и чужие файлы не изменены.
Полный машинный аудит и детерминированная выборка: shops_peer_review.json.
'''
    (OUT/'shops_peer_review.txt').write_text(narrative)
    print('PASS:8raw sources,705rows,24deterministic shop samples,24exclusion controls,centre/periphery2019/2024counts.')
    print(json.dumps(report['2019_2024_comparison'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()

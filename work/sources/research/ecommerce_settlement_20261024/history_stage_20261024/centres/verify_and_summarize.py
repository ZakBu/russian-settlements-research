"""Verify exported administrative context and produce inspectable findings."""
from pathlib import Path
from collections import Counter
import csv
import json
import pyarrow.parquet as pq

OUT=Path(__file__).resolve().parent
BASE=OUT.parent.parent
manifest=json.loads((OUT/'audit_manifest.json').read_text())
rows=pq.read_table(OUT/'settlement_admin_context_main2021.parquet').to_pylist()
assert len(rows)==144151
assert len(set(r['source_record_id_2021'] for r in rows))==144151
ids={r['source_record_id_2021'] for r in rows}
checks=[]
pilot=[]
for summary in manifest['summaries']:
    vintage=summary['vintage']
    centres=list(csv.DictReader((OUT/f'centres_{vintage}.csv').open(encoding='utf-8-sig')))
    positive={r['source_record_id_2021'] for r in centres if r['centre_in_main_target']=='True'}
    assert len(positive)==summary['distinct_main_target_centres']
    actual={r['source_record_id_2021'] for r in rows if r['admin_centre_positive_'+vintage]}
    assert actual==positive
    for r in rows:
        centre_id=r['administrative_centre_source_record_id_2021_'+vintage]
        if r['context_status_'+vintage]=='accepted_administrative_parent_and_centre':
            assert centre_id and r['municipality_oktmo8_'+vintage]
            assert r['administrative_centre_name_2021_'+vintage]
    checks.append({'vintage':vintage,'unique_main_axis':True,'centre_flags_match_source_links':True,
                   'linked_context_centre_names_complete':True,
                   'distinct_main_target_centres':len(actual),
                   'main_target_accepted_context_n':sum(r['context_status_'+vintage]==
                       'accepted_administrative_parent_and_centre' for r in rows),
                   'external_centre_links_accepted':sum(r['official_centres_can_be_external']=='True'
                       and bool(r['source_record_id_2021']) for r in centres),
                   'shared_centre_ids_n':sum(n>1 for n in Counter(r['source_record_id_2021'] for r in centres
                       if r['source_record_id_2021']).values())})
    for r in centres:
        if r['municipality_oktmo8'].startswith('22') and r['administrative_centre_raw'] in [
            'рп Воскресенское','рп Шаранга','рп Тонкино','рп Тоншаево','г Ветлуга','г Урень']:
            pilot.append({k:r[k] for k in ['register_vintage','municipality_oktmo8','municipality_name',
                'administrative_centre_raw','source_record_id_2021','link_status','source_row','source_url']})
with (OUT/'pilot_six_centres_verification.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(pilot[0]));w.writeheader();w.writerows(pilot)
verification={'status':'PASS','checks':checks,'stable_code_centre2020_2021_candidate_n':
              sum(r['admin_code_and_centre_stable_2020_2021_candidate'] for r in rows),
              'boundary_stability_is_verified':False}
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
text = [
    'Независимые административные центры России: национальный первичный источник',
    '24 октября 2026 года',
    '',
    'Получены полные официальные CSV ОКТМО Росстата: 28.01.2015, 10.01.2020, 03.11.2021, 27.09.2022 и 01.10.2026. Исходные файлы, метаданные, структура, страницы и введение сохранены в raw/. Точные URL и SHA256 находятся в source_manifest.json и audit_manifest.json.',
    'https://rosstat.gov.ru/opendata/7708234640-oktmo',
    'https://rosstat.gov.ru/classification',
    '',
    'Семантика. Во введении к ОКТМО блок дополнительных данных определён как административные центры муниципальных образований. В CSV это поле Centrum. Использован верхний муниципальный уровень. Группирующие служебные строки с пустым Centrum не объявляются дополнительными муниципалитетами.',
    'Административный центр не равняется центру покупательского тяготения. Источник даёт независимую от ПВЗ административную иерархию и контекст; торговли, посещений и реального обслуживаемого ареала в нём нет.',
    '',
    'Связка. Официальные имя и тип центра сопоставляются с единственным НП раздела 2 своего МО. Иначе допускается единственный одноимённый НП того же типа в регионе классификатора. Затем требуется точное совпадение 11-значного ОКТМО, имени и типа с единственной физической строкой переписи 2021 года. Ведущие нули восстановлены. Ближайший или крупнейший НП не подставляется.',
    'Центр может находиться в другом МО и быть центром нескольких МО. Флаг центра рассчитан по уникальному ID поселения; число связанных МО сохранено отдельно. При суммировании населения и ПВЗ центр нельзя повторно учитывать для каждого такого МО.',
    '',
    'Главный слой: settlement_admin_context_main2021.parquet, 144151 уникальная строка принятой национальной оси. Каждый выпуск имеет отдельные положительный флаг центра, число связанных МО, родительский ОКТМО8, имя МО, ID и имя центра, административную роль и статус стыковки. False у флага означает отсутствие положительной принятой связи, а не доказанное отсутствие любой центральной функции.',
]
for check in checks:
    text.append(json.dumps(check, ensure_ascii=False))
text.extend([
    '',
    'Основной ранний контекст — выпуск 2020 года. Выпуск 2021 года служит отдельной проверкой. Разница между 1953 привязанными центрами в 2020 году и 2056 в 2021 году не означает рост числа центров: меняются коды, состав реестра и сопоставимость с осью 2021 года.',
    'У 127188 НП совпадают родительский код и ID центра в 2020 и 2021 годах. Это кандидат административной устойчивости; неизменность границ независимо НЕ подтверждена.',
    'Тоншаево и Урень найдены в официальном реестре 2020 года, но их старые коды не совпадают с осью 2021 года после реорганизации районов в округа. Строгая связь оставлена неизвестной. В 2021 году связаны все шесть пилотных центров. Пилот проверяет процедуру и не заменяет национальную выборку.',
    'НП с несопоставленным кодом, именем или типом не считаются периферией без центра. В принятом слое сохранены все 144151 НП, включая неизвестный контекст. Административное подчинение не доказывает фактического торгового тяготения; исторические границы автоматически не совмещаются.',
    'Исключены строки с датой вступления в силу после даты выпуска: одна в 2015 году, пять в 2022 году, ни одной в выпусках 2020, 2021 и 2026 годов. Дата записи классификатора не является датой появления функции.',
    '',
    'Проверки. build_centres.py успешно пересобрал связи. verify_and_summarize.py проверил уникальность оси, соответствие флагов первичным кодированным связям и наличие имён принятых центров. Результат PASS.',
    'Независимое ревью новых network и retail: review_stage_peers.py, stage_peer_review.json. Подтверждены хеши, число российских объектов и уникальность ID семи снимков WB. Все 4200 годовых и 18176 квартальных торговых значений совпадают с исходными Excel-ячейками.',
    'Это новые данные после первого аудита: история WB теперь получена, но изменившиеся флаги типов требуют согласования. Торговые ряды региональные, не поселенческие. Даты снимков не превращаются в открытия, региональные магазины не распределяются по деревням.',
])
(OUT/'findings.txt').write_text('\n'.join(text)+'\n')
print(json.dumps(verification, ensure_ascii=False, indent=2))

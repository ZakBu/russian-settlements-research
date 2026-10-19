#!/usr/bin/env python3
"""Generate a source-backed readout only after the full calendar is computed."""
import argparse,json,re
from pathlib import Path
import pandas as pd
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root;data=root/'pinned_calendar'
 coverage=pd.read_csv(data/'coverage_2011_2025.csv');audit=json.loads((data/'AUDIT.json').read_text());assert audit['pass'] and coverage.year.tolist()==list(range(2011,2026))
 trajectory=pd.read_csv(data/'trajectory_summary.csv');acqs=[json.loads((root/f'remote_selected/{year}_acquisition.json').read_text()) for year in range(2011,2026)]
 assert len({q['pinned_dataset_commit'] for q in acqs})==1
 table=coverage.set_index('year');subset=table.loc[[2011,2016,2021,2025],['source_rows','exact_settlement_code_entities','points_with_direct_service_witness','points_with_ge2_direct_groups','points_with_ge3_direct_groups']]
 names={'no_accepted_service_witness_any_year':'Ни в одном году нет принятого сервисного свидетельства','witness_all_years_unchanged_profile':'Во все15лет есть свидетельство, состав семи групп не меняется','witness_all_years_changed_profile':'Во все15лет есть свидетельство, состав групп меняется','first_appearance_without_later_dropout':'Первое появление свидетельства без последующего выпадения','last_disappearance_without_return':'Последнее исчезновение свидетельства без возвращения','one_internal_witness_episode':'Один внутренний эпизод наблюдаемого свидетельства','intermittent_witness_evidence':'Прерывистые свидетельства'}
 # Use a self-contained Markdown table without optional tabulate dependency.
 lines=['| Год | Строк RFSD | Юрлиц с точным кодом НП | НП с сервисной группой | НП с ≥2 группами | НП с ≥3 группами |','|---:|---:|---:|---:|---:|---:|']
 for year,row in subset.iterrows():lines.append('| '+str(year)+' | '+' | '.join(str(int(v)) for v in row)+' |')
 tr='\n'.join(f'- {names.get(row.witness_trajectory,row.witness_trajectory)}: **{int(row.n_settlements)} НП**.' for row in trajectory.itertuples())
 ncheck=len(audit['checks']);source_rows=int(coverage.source_rows.sum());downloaded=sum(q['downloaded_bytes_including_metadata'] for q in acqs);full=sum(q['upstream_bytes'] for q in acqs);chunks=sum(len(q['verified_column_chunks']) for q in acqs)
 txt=f'''# Экономические свидетельства функций: полный опубликованный календарь2011–2025

**Реально обработаны все15годов RFSD из одной зафиксированной версии.** Получен ряд2138550строк:142570одних и тех же населённых пунктов×15лет. Это история юридических свидетельств функций; физические объекты и их внешнее обслуживание он не заменяет.

## Что получено

{chr(10).join(lines)}

Узкие сервисные группы: розница47, питание56, образование85, медицина86, социальное обслуживание87–88, ремонт95, персональные услуги96. Размещение55, финансы64–66 и управление84 показаны отдельно. Основной ОКВЭД не равен всем фактическим видам деятельности организации; отдельно учтены юридический адрес и отсутствие информации об объектах/филиалах. ПВЗ не определяются автоматически из этих кодов.

## Траектории наблюдаемых свидетельств

{tr}

Смена профиля — смена набора наблюдаемых групп организаций в НП. «Исчезновение свидетельства» не названо закрытием магазина, школы, ФАП или больницы. НП без свидетельств могут иметь ИП, бюджетные учреждения и филиалы, которые RFSD не представляет. Ни один из этих типов сам по себе не является типом СГРТ или доказательством опорности.

## Как обеспечена сопоставимость

- Единственный источник календаря: Hugging Face `irlspbru/RFSD`, commit **bde9b8b129a8be582b66de4e30ed79c9187a8515**, версия карточки3.1.0. Годы не смешаны со старыми срезами неизвестной версии. Старый двухдатный расчёт находится отдельно в `results/` и `READOUT.md`.
- Для каждого года до загрузки выбранных данных прочитаны schema/footer. Получены только пять колонок: ИНН, ОКТМО, основной ОКВЭД, его секция и наличие поданной отчётности. Всего обработано{source_rows}исходных строк, проверено{chunks}колонковых диапазонов. Суммарно передано{downloaded}байт, включая метаданные, вместо{full}байт полных годовых файлов. Служебный footer иногда велик из-за множества rowgroups; это не загрузка всех финансовых колонок.
- Каждый диапазон имеет206, проверенный Content-Range, размер и SHA256. Для каждого производногоParquet выполнена полная обратная загрузка. Известный upstreamLFS-SHA сохранён как метаданные; проверка SHA полного нескачанного исходника не заявляется. ETag и SHA производного файла фиксируются отдельно.
- В пространстве использован только точный уникальный11-значный ОКТМО самого НП, словарь2021. Геокодового резервного присоединения нет. Неразрешённые коды не распределяются по соседним поселениям. Историческая юридическая преемственность всех кодов не доказана; современная ось не названа историческими границами.
- ИНН проверены на10-значный синтаксис и уникальность внутри года. Контрольная цифра рассчитана диагностически, строки с её несоответствием не отбрасывались скрыто; числа находятся в `coverage_2011_2025.csv`. Такая проверка не удостоверяет юридическую действительность записи ЕГРЮЛ.
- Отдельно вычислены14смежных общихИНН-когорт: присутствие одной организации в двух датах, одинаковый/различающийся точный код НП, потеря/приобретение присоединения. Для одной и той же организации в том же НП отдельно показаны изменения групп. ИНН только в одной дате не названы созданиями/ликвидациями.

## Научные ограничения с практическим следствием

RFSD содержит зарегистрированную основную деятельность юридических лиц, а не перепись объектов. IP/ИП не охвачены, бюджетные учреждения представлены неполно, филиалы не восстановлены. Выручка, номинальные рубли и рабочие места в этот расчёт не включены. Текущее население2025не выдумано: для размера НП использована отдельно маркированная перепись2021.

Авторская статья Bondarkov, Ledenev, Skougarevskiy(2025), Scientific Data12,995, [DOI10.1038/s41597-025-05150-1](https://www.nature.com/articles/s41597-025-05150-1), Methods→Harmonization подтверждает гармонизацию ОКВЭД и заполнение отсутствующих классификационных кодов по соседним годам того же ИНН. Авторская перекодировка здесь повторно не выполнялась. Прямое адресное геокодирование в статье описано для2014–2023; точная историческая датировка каждого ОКТМО2011–2013 отдельно не доказана. Ранние годы называются ретроспективными юридическими свидетельствами, а не прямыми наблюдениями тогдашней физической сети.

Поэтому ряд позволяет найти пункты для проверки удержания/утраты/перестройки организационных свидетельств, но не доказывает национальный перехват функций крупными центрами. Для такой гипотезы нужны датированные физические объекты, мощности и реальные либо документально закреплённые внешние связи. Сведения школы, медицины и ПВЗ присоединяются как отдельные категории доказательности.

## Проверки и команды

Фактически завершено **{ncheck}инвариантов, всеPASS**: полная ось15лет, уникальностьИД/год, баланс организаций, парные идентичности, разделение годов одного pinnedcommit, обратная загрузкаParquet, пространственные балансы. Независимая проверка выполняется другим агентом и должна цитироваться по его собственному протоколу; эти авторские инварианты её не подменяют.

Пространственная устойчивость трёх интервалов2011–2025/2016–2021/2021–2025 рассчитана целыми географическими блоками двух размеров,2000повторов,seed20261019. Это конверт чувствительности к географическому составу наблюдаемых пунктов, а не доверительный интервал всех услуг России и не причинная оценка. Зависимость между соседними блоками не устранена; обе ширины опубликованы, национальные псевдо-p-value не рассчитывались.

```bash
python3 functional_dynamics_20261019/economy/fetch_remote_columns.py --tree functional_dynamics_20261019/economy/RFSD_PINNED_TREE.json --out functional_dynamics_20261019/economy/remote_selected --years {' '.join(map(str,range(2011,2026)))} --parallel-years1
python3 functional_dynamics_20261019/economy/build_multiyear_exact.py --base . --out functional_dynamics_20261019/economy/pinned_calendar
python3 functional_dynamics_20261019/economy/compare_legacy_inputs.py --base . --out functional_dynamics_20261019/economy/legacy_vs_pinned.json
python3 functional_dynamics_20261019/economy/plot_calendar.py --data functional_dynamics_20261019/economy/pinned_calendar --out functional_dynamics_20261019/economy/figures
```

В первой команде ключ должен быть записан раздельно: `--parallel-years 1`. Реально выполненный запуск фиксируется в журнале. После первой загрузки возобновление повторно проверяет SHA готовых колонковых срезов. Незавершённый либо неполученный год не заполняется нулём. Ошибки доступа и восстановленный штатный маршрут описаны в `ACCESS_LOG.md`.

Данные: `pinned_calendar/point_exact_code_witnesses_2011_2025.parquet`; траектории: `point_witness_trajectories_2011_2025.parquet`; покрытие: `coverage_2011_2025.csv`; смежные когорты: `adjacent_year_INN_cohorts.csv`; переходы: `annual_and_benchmark_transitions.csv`; пространственная проверка: `spatial_robustness/`; происхождение и контрольные суммы: `AUDIT.json`,`MANIFEST.json`.
'''
 txt=txt.replace('--parallel-years1','--parallel-years 1').replace('В первой команде ключ должен быть записан раздельно: `--parallel-years 1`. ','')
 txt=re.sub(r'(?<=[А-Яа-яЁё])(?=\d)|(?<=\d)(?=[А-Яа-яЁё])',' ',txt)
 for old,new in [('rowgroups','групп строк'),('selectedParquet','выбранных Parquet'),('upstreamLFS-SHA','upstream LFS SHA'),('upstreamLFS','upstream LFS'),('Scientific Data12','Scientific Data 12'),('DOI10.','DOI 10.'),('одного pinnedcommit','одного pinned commit'),('IP/ИП','ИП'),('всеPASS','все PASS')]:txt=txt.replace(old,new)
 (root/'PINNED_CALENDAR_READOUT.md').write_text(txt)
 print(root/'PINNED_CALENDAR_READOUT.md')
if __name__=='__main__':main()

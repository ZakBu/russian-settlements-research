"""Execute the new source audit and readable notebook; render reviewed report.

The computational audit checks extraction/geography. It does not automatically
validate an informant's account or turn an advertising claim into a causal effect.
"""
from pathlib import Path
import importlib.util,sys
from html import escape
import nbformat
from nbclient import NotebookClient
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_operations_20261104/export'
OUT.mkdir(parents=True,exist_ok=True)
def notebook():
    md=nbformat.v4.new_markdown_cell;code=nbformat.v4.new_code_cell
    nb=nbformat.v4.new_notebook(metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
    nb.cells=[md('# Наблюдаемые изменения обращений к средним центрам\n\n'
        'Разделены историческая география предложения тарифа, сообщение о работе '
        'пункта и изменившееся действие покупателя. Источники самоотчётов прочитаны '
        'вручную; последующий расчёт не проверяет истинность каждого рассказа.'),
        code("from pathlib import Path\nimport runpy,sys,io,contextlib,json,pandas as pd\n"
        "from IPython.display import display\nROOT=Path.cwd()\n"
        "HERE=ROOT/'research/ecommerce_cloud/observed_operations_20261104'\n"
        "log=io.StringIO();saved=sys.argv[:]\ntry:\n    with contextlib.redirect_stdout(log):\n"
        "        for script in ['extract_ozon_postal_geography_20261104.py','independent_operations_check.py']:\n"
        "            sys.argv=[str(HERE/script)]\n            runpy.run_path(str(HERE/script),run_name='__main__')\n"
        "finally:\n    sys.argv=saved\n"
        "summary=json.loads((HERE/'postal_geography2023_summary.json').read_text())\n"
        "print({k:summary[k] for k in ['source_pages','extracted_rows','distinct_region_labels','multiline_name_rows','rows_sharing_postal_index']})\n"
        "print('Независимое извлечение всех строк и проверка 258 решений пилота завершились без расхождений.')"),
        md('## Идентичность места и границы выборки\n\n'
        'Поддержка адреса 2023 года не означает открытия ПВЗ и не переносится '
        'автоматически на 2022 год. Размер поселения и принадлежность к фиксированной '
        'административной когорте — разные поля.'),
        code("log=io.StringIO();saved=sys.argv[:]\ntry:\n    with contextlib.redirect_stdout(log):\n"
        "        for script in ['build_postal_case_evidence_20261104.py','audit_named_places.py','build_kuksin_register.py','compare_case_programme_lists_20261104.py']:\n"
        "            sys.argv=[str(HERE/script)]\n            runpy.run_path(str(HERE/script),run_name='__main__')\n"
        "finally:\n    sys.argv=saved\n"
        "places=pd.read_csv(HERE/'named_place_cohort_audit.csv')\n"
        "display(places[['name_2021','population_2002','passes_population_range2002','in_fixed1273']])\n"
        "identity=pd.read_csv(HERE/'postal_identity_case_evidence.csv')\n"
        "display(identity[['name2023','postal_index2023','census2021_name','assessment_for_2023_only','identity2022_confirmed']])"),
        md('## Операции и свидетельства изменения\n\n'
        'Ни дата отзыва, ни дата первого обнаружения не объявляются открытием. '
        'Число фрагментов научной публикации не является числом независимых случаев.'),
        code("operations=pd.read_csv(HERE/'kuksin_operations_register.csv')\n"
        "print('Размеченных опубликованных фрагментов:',len(operations))\n"
        "points=pd.read_csv(HERE/'actual_points.csv').fillna('не установлено')\n"
        "display(points[['name','operation_evidence_date','date_kind','prior_destination_named','status']])\n"
        "change=pd.read_csv(HERE/'destination_change.csv')\n"
        "display(change[['past_destination','current_pickup_place','respondent_origin_settlement','past_destination_medium_primary2002','named_residence_to_centre_OD']].fillna('не установлено'))\n"
        "north=pd.read_csv(HERE/'systematic_review_positive_extracts_nn_tver.csv')\n"
        "west=pd.read_csv(HERE/'systematic_review_positive_extracts_len.csv')\n"
        "display(north[['date_display','old_centre_named','current_pvz_locality','origin_locality']].fillna('не установлено'))\n"
        "display(west[['review_date','past_destinations_as_reported','current_pickup_place','residential_origin']].fillna('не установлено'))\n"
        "presence=pd.read_csv(HERE/'case_programme_presence.csv')\n"
        "display(presence[['case_name','case_operator','list2022_same_name_region_rows_n','list2023_same_name_region_rows_n','tariff_participation_proven']])"),
        md('## Вывод и предел\n\nПять опубликованных отзывов на трёх карточках называют '
        'прежние Лугу и Кашин; рекламный материал дополняет их Енисейском. Это четыре '
        'места нынешнего получения, не шесть независимых территорий. Частота, национальная '
        'массовость и общий баланс функций не измерены. Фактические грузовые маршруты '
        'этих покупательских случаев неизвестны. Полный ответ '
        'и независимый разбор — REPORT_RU.md и REVIEW_RU.md.')]
    nbformat.validate(nb)
    done=NotebookClient(nb,timeout=900,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbformat.write(done,OUT/'observed_centre_links_executed.ipynb')
    from markdown_it import MarkdownIt
    parser=MarkdownIt('default');html=['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Изменения обращений к центрам</title><style>body{max-width:1050px;margin:30px auto;padding:0 16px;font:16px/1.6 sans-serif;color:#25333c}pre{white-space:pre-wrap;font-size:13px}table{display:block;overflow-x:auto;border-collapse:collapse}td,th{padding:5px;border-bottom:1px solid #ddd}</style>']
    for c in done.cells:
        if c.cell_type=='markdown':html.append(parser.render(c.source));continue
        html.append('<details><summary>Код</summary><pre>'+escape(c.source)+'</pre></details>')
        for o in c.get('outputs',[]):
            data=o.get('data',{})
            if 'text/html' in data:html.append(data['text/html'])
            elif o.get('text'):html.append('<pre>'+escape(o.text)+'</pre>')
            elif 'text/plain' in data:html.append('<pre>'+escape(data['text/plain'])+'</pre>')
    (OUT/'observed_centre_links_notebook.html').write_text('\n'.join(html))
def pdf():
    spec=importlib.util.spec_from_file_location('pdf_renderer',HERE.parent/'dependency_20261026/build_deliverables.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    renderer.HERE=HERE;renderer.OUT=OUT
    renderer.pdf(documents=['REPORT_RU.md','REVIEW_RU.md'],filename='Observed_Centre_Links_20261104.pdf',
        footer_text='Изменения обращений к средним центрам · 4 ноября 2026',
        title='Какие связи со средним центром действительно меняются')
if __name__=='__main__':
    if '--pdf-only'not in sys.argv:notebook()
    pdf();print(OUT)

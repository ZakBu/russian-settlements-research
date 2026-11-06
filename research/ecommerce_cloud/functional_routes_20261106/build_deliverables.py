"""Execute source-register audit and render the scientific synthesis."""
from pathlib import Path
from html import escape
import importlib.util,sys
import nbformat
from nbclient import NotebookClient
from markdown_it import MarkdownIt
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_functional_20261106/export'

def notebook():
    md=nbformat.v4.new_markdown_cell;code=nbformat.v4.new_code_cell
    nb=nbformat.v4.new_notebook(metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
    nb.cells=[md('# Зависимость окружения от центра: разные операции\n\n'
        'Извлечения прочитаны вручную и сохранены без профилей пользователей. '
        'Код повторяет присоединение к неизменной базе населения и проверяет '
        'знаменатели реестров. Он не проверяет истинность рассказов и не оценивает причинный эффект.'),
        code("from pathlib import Path\nimport runpy,contextlib,io,pandas as pd\n"
             "from IPython.display import display\n"
             "HERE=Path.cwd()/'research/ecommerce_cloud/functional_routes_20261106'\n"
             "with contextlib.redirect_stdout(io.StringIO()):\n"
             "    runpy.run_path(str(HERE/'build_synthesis.py'),run_name='__main__')\n"
             "runpy.run_path(str(HERE/'check_evidence.py'),run_name='__main__')\n"
             "cases=pd.read_csv(HERE/'functional_evidence.csv').fillna('не установлено')\n"
             "display(cases[['current_receipt_place','prior_centre','residential_origin','source_kind','evidence_status','first_added_in_this_pass']])"),
        md('## Сохраняемые обращения, труд и разные масштабы\n\n'
           'Две трудовые связи относятся к уже известному Котовску и периоду до '
           'июльских событий 2026 года. Знаменка сама средний центр. Неназванный '
           'входящий узел местного довоза не восстанавливается по административному району. '
           'Региональные темпы Ozon не являются матрицей между поселениями.'),
        code("west=pd.read_csv(HERE/'observed_west/primary_extracts.csv').fillna('не установлено')\n"
             "display(west[['evidence_kind','named_centre','excerpt']])\n"
             "workers=pd.read_csv(HERE/'producer_functions/edges.csv')\n"
             "display(workers[['origin','destination','operation_period','status']])\n"
             "goods=pd.read_csv(HERE/'goods_routes/goods_edges.csv')\n"
             "display(goods)\n"
             "flows=pd.read_csv(HERE/'identification/regional_operator_flows.csv')\n"
             "display(flows[['origin','destination','reported_growth_factor_comparator','reported_growth_factor','reported_measure']])"),
        md('## Научный вывод\n\n'
           'Местное получение может заменять отдельное обращение к среднему центру. '
           'Другие покупатели продолжают приезжать в городской ПВЗ; склад может привлекать '
           'труд извне, а городской бизнес — переходить от розницы к опту и выдаче. '
           'Общий баланс и национальная частота по целевому поиску не вычисляются. '
           'Ответ с источниками и критическими границами — REPORT_RU.md и review/REVIEW_RU.md.')]
    nbformat.validate(nb)
    done=NotebookClient(nb,timeout=600,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbformat.write(done,OUT/'functional_routes_executed.ipynb')
    parser=MarkdownIt('default')
    html=['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
          '<title>Зависимость окружения от центра</title><style>body{max-width:1100px;margin:30px auto;padding:0 16px;font:16px/1.6 sans-serif;color:#25333c}table{display:block;overflow:auto;border-collapse:collapse}td,th{padding:6px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style>']
    for c in done.cells:
        if c.cell_type=='markdown':html.append(parser.render(c.source));continue
        html.append('<details><summary>Код</summary><pre>'+escape(c.source)+'</pre></details>')
        for o in c.get('outputs',[]):
            d=o.get('data',{})
            if 'text/html'in d:html.append(d['text/html'])
            elif o.get('text'):html.append('<pre>'+escape(o.text)+'</pre>')
            elif 'text/plain'in d:html.append('<pre>'+escape(d['text/plain'])+'</pre>')
    (OUT/'functional_routes_notebook.html').write_text('\n'.join(html))

def pdf():
    spec=importlib.util.spec_from_file_location('renderer',HERE.parent/'dependency_20261026/build_deliverables.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    renderer.HERE=HERE;renderer.OUT=OUT
    renderer.pdf(documents=['REPORT_RU.md','review/REVIEW_RU.md'],
        filename='Centre_Dependency_Functions_20261106.pdf',
        footer_text='Зависимость окружения от центра · 6 ноября 2026',
        title='Как маркетплейсы меняют зависимость поселений от среднего центра',
        link_base_url='https://github.com/ZakBu/russian-settlements-research/blob/codex/ecommerce-settlement-cloud-20261025/research/ecommerce_cloud/functional_routes_20261106/')

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    if '--pdf-only'not in sys.argv:notebook()
    pdf();print(OUT)

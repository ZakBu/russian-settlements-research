"""Scientific figures, executable audit and report.

Public mode does not contact the rate-limited archive. It explicitly audits ICT
aggregates; KOUZh and municipal spending are recomputed from restored raw files.
Default local mode also recomputes the already acquired primary ICT SAV.
"""
from pathlib import Path
from html import escape
import argparse,base64,importlib.util
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nbformat
from nbclient import NotebookClient
from markdown_it import MarkdownIt
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_national_test_20261106/export'

def figures():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False})
    series=pd.read_csv(HERE/'operator_evidence/ict_published_series.csv')
    s=series.loc[series.source_id.eq('hse_digital_indicators_2026')&series.age.eq('15+')&series.residence.eq('Село')].sort_values('year')
    ict=pd.read_csv(HERE/'ict_survey/ict_estimates.csv')
    t=ict.loc[ict.age_universe.eq('15+')&ict.geography.eq('rural')].set_index('metric')
    metrics=['online_any_goods_or_services_last12m','physical8_any_last12m','physical8_and_pickup_same_person']
    fig,ax=plt.subplots(1,2,figsize=(10.2,4.9),gridspec_kw={'width_ratios':[1,1.5]})
    ax[0].plot(s.year,s.value_pct,marker='o',lw=2.5,color='#235f81')
    for r in s.itertuples():ax[0].annotate(f'{r.value_pct:.1f}%',(r.year,r.value_pct),xytext=(0,9),textcoords='offset points',ha='center')
    ax[0].set(xticks=s.year,ylim=(0,72),ylabel='Доля сельских жителей 15+, %',title='Любые товары и услуги:\nопубликованный ряд')
    vals=[t.at[m,'pct']for m in metrics]
    ax[1].barh(range(3),vals,color=['#235f81','#39847e','#a0b8b6'])
    ax[1].set(yticks=range(3),yticklabels=['Любые заказы','8 вещевых групп','Вещи и самовывоз\nу одного человека'],xlim=(0,75),xlabel='Доля сельских жителей 15+, %',title='Микроданные 2024:\nза 12 месяцев')
    ax[1].invert_yaxis()
    for i,v in enumerate(vals):ax[1].text(v+1,i,f'{v:.1f}%',va='center')
    fig.text(.02,.025,'Источники: ВШЭ 2026, с.254; Росстат ИКТ-2024, взвешенный пересчёт.\nКалибровка волн может различаться; местность получения и связь самовывоза с тем же заказом неизвестны.',fontsize=10.5)
    fig.tight_layout(rect=(0,.12,1,1));fig.savefig(OUT/'rural_orders.png',dpi=180);plt.close(fig)
    d=pd.read_csv(HERE/'sber_consumption/balanced_municipal_annual.csv')
    x=d.marketplace_ratio_change_pp
    fig,ax=plt.subplots(figsize=(10.2,5.0))
    ax.hist(x,bins=35,color='#39847e',edgecolor='white')
    ax.axvline(x.median(),color='#9e572e',lw=2,label=f'Медиана изменений внутри МО: {x.median():.2f} п.п.')
    ax.set(xlabel='Изменение отношения «маркетплейсы / вся корзина», 2024 к 2023, п.п.',ylabel='Муниципалитетов',title='Рост отношения «маркетплейсы / вся корзина»\n2 016 МО с полными рядами, 2023–2024')
    ax.legend(frameon=False)
    fig.text(.02,.02,'Источник: модельные безналичные расходы жителей, СберИндекс. 73 региона, одинаковый вес каждого МО.\nЭто не взвешенная доля России, не оборот местных магазинов и не оценка вытеснения.',fontsize=10.5)
    fig.tight_layout(rect=(0,.13,1,1));fig.savefig(OUT/'municipal_marketplace_change.png',dpi=180);plt.close(fig)

def notebook(public):
    md=nbformat.v4.new_markdown_cell;code=nbformat.v4.new_code_cell
    nb=nbformat.v4.new_notebook(metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
    nb.cells=[md('# Интернет-заказы, расходы жителей и функции центров\n\n'
        'Здесь различены исходные самоотчёты Росстата, модельные средние СберИндекса '
        'и вручную извлечённые официальные таблицы. Ни один расчёт не превращён '
        'в причинный коэффициент влияния WB/Ozon на средние центры.\n\n'
        +('**Режим публикации:** полный SAV ИКТ в этой среде не восстанавливается. '
           'Для ИКТ проверяется арифметика опубликованных агрегатов и внешние контрольные значения. '
           'Полный файл был пересчитан двумя кодами в рабочей среде. '
           'КОУЖ и СберИндекс ниже пересчитываются из закреплённых исходных файлов.' if public else
           '**Полный локальный режим:** КОУЖ, СберИндекс и ранее полученный первичный SAV ИКТ читаются заново.')),
        code("from pathlib import Path\nimport runpy,sys,io,contextlib,pandas as pd\n"
             "from IPython.display import display,Image\nROOT=Path.cwd()\nHERE=ROOT/'research/ecommerce_cloud/national_test_20261106'\n"
             "def execute(path,args=()):\n    saved=sys.argv[:]\n    try:\n        sys.argv=[str(path),*args]\n        with contextlib.redirect_stdout(io.StringIO()):\n            runpy.run_path(str(path),run_name='__main__')\n    finally:\n        sys.argv=saved\n"
             "execute(HERE/'purchase_microdata/analyze_purchase_channels.py')\n"
             "execute(HERE/'sber_consumption/analyse_consumption.py')\n"
             "execute(HERE/'employment_panel/extract_sector_wages.py')\n"
             +( "print('ИКТ: первичный SAV здесь не прочитан; используются закреплённые агрегаты.')\n" if public else
                "execute(HERE/'ict_survey/analyze_ict_survey.py',['--years','2024'])\nprint('ИКТ: первичный SAV пересчитан.')\n")+
             "check_args="+repr(['--skip-ict-raw']if public else [])+"\n"
             "saved=sys.argv[:]\ntry:\n    sys.argv=[str(HERE/'review/independent_national_check.py'),*check_args]\n    runpy.run_path(str(HERE/'review/independent_national_check.py'),run_name='__main__')\nfinally:\n    sys.argv=saved"),
        md('## Заказы и способ получения\n\nОсновной возраст — 15+; стандартный 15–74 хранится отдельно. '
           'Вещевые группы и самовывоз пересекаются на уровне человека, не заказа. '
           'Адрес выдачи и прежний центр отсутствуют.'),
        code("ict=pd.read_csv(HERE/'ict_survey/ict_estimates.csv')\n"
             "display(ict.loc[ict.geography.eq('rural')&ict.metric.isin(['online_any_goods_or_services_last12m','physical8_any_last12m','physical8_and_pickup_same_person']),['age_universe','metric','unweighted_denominator_n','weighted_denominator_persons','pct']])\n"
             "display(Image(filename=str(ROOT/'work/ecommerce_national_test_20261106/export/rural_orders.png')))"),
        md('## Муниципальные модельные расходы\n\nМедианы рассчитаны с одинаковым весом МО. '
           'Остаток включает интернет-магазины других типов и услуги, поэтому не называется офлайном. '
           'Набор с полными рядами не является случайной выборкой.'),
        code("dist=pd.read_csv(HERE/'sber_consumption/municipality_distribution_summary.csv')\n"
             "display(dist.loc[dist.group.eq('all_balanced'),['n_municipalities','share_2023_pct_q50','share_2024_pct_q50','share_change_pp_q50','share_increased_n','nonmarketplace_nominal_increased_n']])\n"
             "display(Image(filename=str(ROOT/'work/ecommerce_national_test_20261106/export/municipal_marketplace_change.png')))"),
        md('## Разные функции и предел причинного вывода\n\nКОУЖ описывает основную географию приобретения '
           'всех покупок товарной группы. Это не маршрут человека или конкретного интернет-заказа. '
           'Трудовые показатели территории и её жителей также различены. Полный ответ — REPORT_RU.md.'),
        code("geo=pd.read_csv(HERE/'purchase_microdata/same_wave_standardised.csv')\n"
             "display(geo.loc[geo.year.eq(2024)&geo.group_definition.eq('same_goods_frequency')])\n"
             "display(pd.read_csv(HERE/'employment_panel/changes.csv'))\n"
             "display(pd.read_csv(HERE/'causal_sources/extracted_effects.csv'))")]
    nbformat.validate(nb)
    done=NotebookClient(nb,timeout=900,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbformat.write(done,OUT/'national_evidence_executed.ipynb')
    parser=MarkdownIt('default')
    html=['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
          '<title>Заказы и муниципальные расходы</title><style>body{max-width:1150px;margin:30px auto;padding:0 16px;font:16px/1.6 sans-serif;color:#25333c}img{max-width:100%}table{display:block;overflow:auto;border-collapse:collapse}td,th{padding:6px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style>']
    for c in done.cells:
        if c.cell_type=='markdown':html.append(parser.render(c.source));continue
        html.append('<details><summary>Код</summary><pre>'+escape(c.source)+'</pre></details>')
        for o in c.get('outputs',[]):
            d=o.get('data',{})
            if 'image/png'in d:html.append('<img src="data:image/png;base64,'+d['image/png']+'">')
            elif 'text/html'in d:html.append(d['text/html'])
            elif o.get('text'):html.append('<pre>'+escape(o.text)+'</pre>')
            elif 'text/plain'in d:html.append('<pre>'+escape(d['text/plain'])+'</pre>')
    (OUT/'national_evidence_notebook.html').write_text('\n'.join(html))

def pdf():
    spec=importlib.util.spec_from_file_location('renderer',HERE.parent/'dependency_20261026/build_deliverables.py')
    r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);r.HERE=HERE;r.OUT=OUT
    r.pdf(documents=['REPORT_RU.md','review/REVIEW_RU.md'],filename='National_Orders_and_Centre_Functions_20261106.pdf',
        footer_text='Интернет-заказы и функции средних центров · 6 ноября 2026',
        title='Насколько массово меняется снабжение и что происходит со средними центрами',
        link_base_url='https://github.com/ZakBu/russian-settlements-research/blob/codex/ecommerce-settlement-cloud-20261025/research/ecommerce_cloud/national_test_20261106/')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--public-ict-aggregates',action='store_true');p.add_argument('--pdf-only',action='store_true');a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);figures()
    if not a.pdf_only:notebook(a.public_ict_aggregates)
    pdf();print(OUT)

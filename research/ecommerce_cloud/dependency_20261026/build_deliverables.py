"""Execute the new notebook and render its two scientific figures and manuscript.

Run at repository root with .venv-ecommerce/bin/python. The source PDFs of other
authors are never added to the exported bundle. Figures use reviewed small CSVs.
"""
from pathlib import Path
from html import escape
import json
import sys
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'work/ecommerce_dependency_20261026/export'
OUT.mkdir(parents=True, exist_ok=True)

CHART_CODE = r'''
import matplotlib
matplotlib.use('module://matplotlib_inline.backend_inline')
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11,
    'axes.spines.top':False, 'axes.spines.right':False,
    'axes.labelcolor':'#25333c', 'text.color':'#25333c',
    'axes.edgecolor':'#87939a', 'figure.facecolor':'white'})

fig, ax = plt.subplots(figsize=(10,5.8))
for geo, label, color, marker in [('rural','Село','#245c82','o'),
                                 ('urban','Город','#9a722e','s')]:
    g=behaviour.loc[behaviour.geography.eq(geo)].sort_values('year')
    exact=g.loc[g.year.lt(2025)]
    ax.plot(exact.year,exact.percent,color=color,marker=marker,lw=2,label=label)
    tail=g.loc[g.year.ge(2024)]
    ax.plot(tail.year,tail.percent,color=color,marker=marker,lw=2,ls='--')
    for row in g.itertuples():
        ax.annotate(f'{row.percent:g}%',(row.year,row.percent),
                    xytext=(0,9),textcoords='offset points',ha='center',fontsize=10)
ax.set(xlim=(2019.7,2025.3),ylim=(0,85),xticks=list(range(2020,2026)),
       ylabel='Доля жителей 15 лет и старше, %',
       title='Онлайн-заказы товаров или услуг за последний год')
ax.grid(axis='y',color='#e1e6e9',lw=.7);ax.set_axisbelow(True)
ax.legend(loc='upper left',frameon=False,ncol=2)
fig.text(.09,.045,'Источник: Росстат, ИСИЭЗ НИУ ВШЭ. 2025: опубликованные округлённые доли.\n'
         'Все интернет-каналы; место получения и замещённые поездки не измерены.',fontsize=10)
fig.subplots_adjust(left=.09,right=.97,bottom=.21,top=.87)
fig.savefig(OUT/'online_ordering_2020_2025.png',dpi=170)
display(fig);plt.close(fig)

fig, ax = plt.subplots(figsize=(10,5.5))
regs=regions.loc[regions.vintage.eq(20200110)&regions.ozon_identity_radius_km.eq(5)
    &regions.wb_rule.eq('baseline')].set_index('region')
spec=[('краснодарский','Краснодарский край'),('тверская','Тверская область'),
      ('саха якутия','Якутия')]
values=[float(regs.loc[k,'either_population2021_share_pct']) for k,_ in spec]
ax.barh(range(3),values,color='#245c82',height=.52)
ax.set_yticks(range(3),[label for _,label in spec]);ax.invert_yaxis()
ax.set(xlim=(0,100),xlabel='Доля населения окружений по переписи 2021 года, %',
       title='Положительная запись WB/Ozon в собственном НП окружения')
for i,(value,(key,_)) in enumerate(zip(values,spec)):
    r=regs.loc[key]
    ax.text(value+1.1,i,f'{value:.1f}%',va='center',fontsize=12)
ax.grid(axis='x',color='#e1e6e9',lw=.7);ax.set_axisbelow(True)
fig.text(.06,.045,'Разные региональные подсовокупности окружений средних центров; сетка 2020.\n'
         'WB: 21.10.2026; Ozon: сторонний каталог 06.08.2026, допуск идентичности 5 км.\n'
         'Это расположение записей, не пользователи, доступность или доля отменённых поездок.',fontsize=9.5)
fig.subplots_adjust(left=.25,right=.95,bottom=.26,top=.86)
fig.savefig(OUT/'periphery_selected_regions.png',dpi=170)
display(fig);plt.close(fig)
'''


def notebook():
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = {'display_name':'Python 3', 'language':'python','name':'python3'}
    nb.cells = [
        nbformat.v4.new_markdown_cell('# Получение товаров вне среднего центра\n\n'
            'В 9 614 из 71 211 жилых НП окружений есть положительные записи WB/Ozon; '
            'в них жили 12 472 999 из 19 411 640 жителей переписи 2021 года (64,26%). '
            'Это география записей, не доля отказавшихся от поездки. '
            'Сельские онлайн-заказы выросли с 24% в 2020 до около 64% в 2025; '
            'место получения в этом обследовании неизвестно.'),
        nbformat.v4.new_markdown_cell('## Источники и метод\n\n'
            'Фиксированная когорта 1 273 центра: 5–50 тыс. жителей в 2002 и принятый '
            'мост административного центра 2020. НП окружений не перекрываются внутри '
            'одной сетки; разные сетки не складываются. Каталоги WB и Ozon разновременны. '
            'Входы восстанавливаются fetch_bundle.py и проверяются SHA256; их точные '
            'пути/хеши сохраняет national_options_inputs.json. Ряд поведения переписан '
            'из указанных страниц ИСИЭЗ, источник и точность есть в каждой строке CSV.'),
        nbformat.v4.new_code_cell("from pathlib import Path\nimport runpy, pandas as pd\nimport io, contextlib, json\n"
            "from IPython.display import display\nROOT=Path.cwd()\n"
            "HERE=ROOT/'research/ecommerce_cloud/dependency_20261026'\n"
            "OUT=ROOT/'work/ecommerce_dependency_20261026/export'\nOUT.mkdir(parents=True,exist_ok=True)\n"
            "log=io.StringIO()\nwith contextlib.redirect_stdout(log):\n"
            "    runpy.run_path(str(HERE/'analyze_national_options.py'),run_name='__main__')\n"
            "    runpy.run_path(str(HERE/'independent_options_check.py'),run_name='__main__')\n"
            "print('Выполнены расчёт и отдельная проверка из источников.')\n"
            "check=json.loads(log.getvalue().strip().splitlines()[-1])\n"
            "print(f\"Независимый пересчёт: {check['source_configs']} конфигураций, \""
            "f\"{check['all_config_checks']} проверок; расхождений: {check['max_discrepancy']}.\")"),
        nbformat.v4.new_markdown_cell('## Национальные результаты\n\n'
            'Показываем основной вариант и чувствительность географии/идентичности. '
            'Неизвестное присутствие не становится отсутствием услуги.'),
        nbformat.v4.new_code_cell("options=pd.read_csv(HERE/'national_options_summary.csv')\n"
            "regions=pd.read_csv(HERE/'national_options_regions.csv')\n"
            "behaviour=pd.read_csv(HERE/'behaviour_series.csv')\n"
            "view=options.loc[options.wb_rule.eq('baseline'),['vintage','ozon_identity_radius_km',"
            "'periphery_inhabited_np_n','periphery_population2021','either_positive_np_n',"
            "'either_population2021_share_pct']].copy()\n"
            "view['vintage']=view.vintage.map({20200110:'2020',20211103:'2021'})\n"
            "view=view.rename(columns={'vintage':'Сетка','ozon_identity_radius_km':'Допуск, км',"
            "'periphery_inhabited_np_n':'Жилых НП','periphery_population2021':'Жителей 2021',"
            "'either_positive_np_n':'НП с записью','either_population2021_share_pct':'Доля жителей, %'})\n"
            "display(view.round(2).reset_index(drop=True))\n"
            "display(behaviour.pivot(index='year',columns='geography',values='percent')"
            ".rename(columns={'all':'Все','rural':'Село','urban':'Город'})"
            ".rename_axis(index='Год',columns='Онлайн-заказы 15+, %'))"),
        nbformat.v4.new_markdown_cell('## Две разные шкалы\n\n'
            'Первый рисунок — личный онлайн-заказ товаров/услуг, второй — размещение '
            'положительных записей в НП окружения. Их доли имеют разные знаменатели '
            'и не перемножаются в число местных покупателей.'),
        nbformat.v4.new_code_cell(CHART_CODE),
        nbformat.v4.new_markdown_cell('## Граница вывода\n\n'
            'Обе шкалы показывают масштаб распространения канала. Направление '
            'прошлой/новой поездки, продавец и физический маршрут товара здесь '
            'не наблюдаются. Качественные случаи и документы логистики разобраны '
            'в DEPENDENCY_REPORT_RU.md; причинная величина для России не установлена.'),
    ]
    nbformat.validate(nb)
    nb = NotebookClient(nb, timeout=600, kernel_name='python3',
        resources={'metadata':{'path':str(ROOT)}},
        kernel_manager_class='jupyter_client.manager.KernelManager').execute()
    nbformat.write(nb, OUT/'dependency_executed.ipynb')
    # A static preview retains actual saved outputs, with no external scripts.
    import base64
    html = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Расчёт зависимости</title>',
            '<style>body{max-width:1050px;margin:32px auto;padding:0 16px;font:16px/1.6 sans-serif;'
            'color:#25333c}img{width:100%}pre{white-space:pre-wrap;font-size:13px}'
            'table{border-collapse:collapse;display:block;overflow-x:auto}td,th{padding:5px 10px;border-bottom:1px solid #ddd}</style>']
    from markdown_it import MarkdownIt
    md = MarkdownIt('default')
    for cell in nb.cells:
        if cell.cell_type == 'markdown':
            html.append(md.render(cell.source))
        else:
            html.append('<details><summary>Код</summary><pre>'+escape(cell.source)+'</pre></details>')
            for o in cell.get('outputs',[]):
                if 'image/png' in o.get('data',{}):
                    html.append('<img src="data:image/png;base64,'+o.data['image/png']+'">')
                elif 'text/html' in o.get('data',{}): html.append(o.data['text/html'])
                elif o.get('text'): html.append('<pre>'+escape(o.text)+'</pre>')
                elif 'text/plain' in o.get('data',{}):html.append('<pre>'+escape(o.data['text/plain'])+'</pre>')
    (OUT/'dependency_notebook.html').write_text('\n'.join(html))
    return nb


def pdf():
    from markdown_it import MarkdownIt
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from matplotlib.font_manager import FontProperties, findfont
    for name, weight in [('Body','normal'),('BodyBold','bold')]:
        pdfmetrics.registerFont(TTFont(name,findfont(FontProperties(family='DejaVu Sans',weight=weight))))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
    styles = {k:ParagraphStyle(k,fontName='BodyBold' if k in ('h1','h2','h3','th') else 'Body',
        fontSize=size,leading=size*1.4,spaceAfter=7,
        keepWithNext=k in ('h1','h2','h3'),textColor=colors.HexColor('#204d69') if k.startswith('h') else colors.HexColor('#25333c'))
        for k,size in [('body',9.2),('h1',18),('h2',13),('h3',10.5),('td',7.4),('th',7.4)]}

    def inline(children):
        chunks=[]
        for t in children or []:
            if t.type in ('text','code_inline'):chunks.append(escape(t.content))
            elif t.type=='strong_open':chunks.append('<b>')
            elif t.type=='strong_close':chunks.append('</b>')
            elif t.type in ('softbreak','hardbreak'):chunks.append(' ')
            elif t.type=='link_open':
                url=t.attrGet('href')
                if not url.startswith(('http://','https://')):
                    url='https://github.com/ZakBu/russian-settlements-research/blob/codex/ecommerce-settlement-cloud-20261025/research/ecommerce_cloud/dependency_20261026/'+url
                chunks.append('<a href="'+escape(url,quote=True)+'" color="#245c82">')
            elif t.type=='link_close':chunks.append('</a>')
        return ''.join(chunks)

    story=[]
    md=MarkdownIt('default')
    for file in ['DEPENDENCY_REPORT_RU.md','REVIEW_RU.md']:
        if not (HERE/file).exists():continue
        tokens=md.parse((HERE/file).read_text());i=0
        while i<len(tokens):
            t=tokens[i]
            if t.type=='heading_open':
                story.append(Paragraph(inline(tokens[i+1].children),styles[t.tag]));i+=3;continue
            if t.type=='paragraph_open':
                inner=tokens[i+1]
                im=next((x for x in inner.children or [] if x.type=='image'),None)
                if im:
                    from PIL import Image as PILImage
                    p=OUT/Path(im.attrGet('src')).name
                    with PILImage.open(p) as img:w,h=img.size
                    story.append(Image(str(p),width=17*cm,height=17*cm*h/w))
                else:story.append(Paragraph(inline(inner.children),styles['body']))
                i+=3;continue
            if t.type=='table_open':
                rows=[];row=[];i+=1
                while tokens[i].type!='table_close':
                    x=tokens[i]
                    if x.type=='tr_open':row=[]
                    elif x.type=='inline':row.append(inline(x.children))
                    elif x.type=='tr_close':rows.append(row)
                    i+=1
                n=len(rows[0]);fracs=([.24,.76] if n==2 else [.24]+[.76/(n-1)]*(n-1))
                tab=Table([[Paragraph(x,styles['th' if j==0 else 'td']) for x in row]
                    for j,row in enumerate(rows)],colWidths=[17*cm*f for f in fracs],repeatRows=1)
                tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4eef4')),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f7f9fa'),colors.white]),
                    ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                story.extend([tab,Spacer(1,8)])
            i+=1

    def footer(canvas,doc):
        canvas.setFont('Body',7.5);canvas.setFillColor(colors.HexColor('#5a6a75'))
        canvas.drawString(2*cm,1.2*cm,'Посредничество центра и маркетплейсы · 26 октября 2026')
        canvas.drawRightString(19*cm,1.2*cm,str(doc.page))
    doc=SimpleDocTemplate(str(OUT/'Dependency_and_Russian_Centres_20261026.pdf'),
        pagesize=(21*cm,29.7*cm),leftMargin=2*cm,rightMargin=2*cm,
        topMargin=1.8*cm,bottomMargin=2*cm,title='Посредническая роль средних центров и маркетплейсы')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)


if __name__=='__main__':
    if '--pdf-only' not in sys.argv:notebook()
    pdf()
    print(OUT)

"""Execute the joint-dependency notebook and export scientific PDF/figures."""
from pathlib import Path
import importlib.util
from html import escape
import sys
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_joint_20261103/export'
OUT.mkdir(parents=True,exist_ok=True)

CHARTS=r'''
import matplotlib
matplotlib.use('module://matplotlib_inline.backend_inline')
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,
    'axes.spines.right':False,'figure.facecolor':'white'})
categories=[('LLL_pct','Три местные','#246486'),('mixed_pct','Смешанный профиль','#a4bcc5'),
    ('EEE_pct','Три внешние','#b07d45'),('unknown_pct','Неизвестно','#dddddd')]
def chart(data,labels,title,filename,note):
    fig,ax=plt.subplots(figsize=(10,5.5));left=np.zeros(len(data));y=np.arange(len(data))
    for field,label,color in categories:
        values=data[field].to_numpy();ax.barh(y,values,left=left,color=color,label=label,height=.55)
        for i,v in enumerate(values):
            if v>=7:ax.text(left[i]+v/2,i,f'{v:.1f}%',ha='center',va='center',fontsize=10,
                color='white' if field in ['LLL_pct','EEE_pct'] else '#21343d')
        left+=values
    ax.set(yticks=y,yticklabels=labels,xlim=(0,100),xlabel='Доля сельских лиц 15+ с информацией, %',title=title)
    ax.invert_yaxis();ax.legend(loc='upper center',bbox_to_anchor=(.5,-.2),ncol=2,frameon=False)
    fig.text(.04,.035,note,fontsize=9)
    fig.subplots_adjust(left=.19,right=.98,top=.84,bottom=.36)
    fig.savefig(OUT/filename,dpi=170);display(fig);plt.close(fig)
std=pd.read_csv(HERE/'joint_purchase_standardised.csv').sort_values('year')
chart(std,std.year.astype(str),'Основные места приобретения трёх товарных групп',
    'joint_profiles_standardised.png',
    'Источник: КОУЖ. Состав сельского населения 2022 года: размер НП × возраст × пол.\n'
    '«Внешние» не означают один центр. Повторные срезы; не эффект платформ и не индивидуальные переходы.')
sizes=pd.read_csv(HERE/'joint_purchase_profiles.csv').query("year==2024 and scope=='rural_size'")
sizes=sizes.assign(size_code=pd.to_numeric(sizes['group'])).sort_values('size_code')
chart(sizes,['До 200','201–1 000','1 001–5 000','Более 5 000'],
    'География приобретения и размер сельского поселения, 2024',
    'joint_profiles_size2024.png','Источник: КОУЖ. Размер поселения — число жителей.\n'
    'Три группы: продукты/гигиена; одежда/обувь; техника/связь. Не измеряет место получения онлайн-заказа.')
'''


def notebook():
    md=nbformat.v4.new_markdown_cell;code=nbformat.v4.new_code_cell
    nb=nbformat.v4.new_notebook(metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
    nb.cells=[md('# Совместная география покупок и школьные связи\n\n'
        'КОУЖ: сельские лица15+ с информацией; household-сопоставление только2024. '
        'Это приобретение по основному месту, не поездки и не получение интернет-заказов. '
        'Три местные группы не означают все покупки исключительно в своём НП.'),
        code("from pathlib import Path\nimport runpy,sys,io,contextlib,pandas as pd\n"
        "from IPython.display import display\nROOT=Path.cwd()\n"
        "HERE=ROOT/'research/ecommerce_cloud/next_direction_20261103'\n"
        "OUT=ROOT/'work/ecommerce_joint_20261103/export'\nOUT.mkdir(parents=True,exist_ok=True)\n"
        "saved=sys.argv[:]\ntry:\n    for script in ['analyze_joint_dependencies.py','independent_joint_check.py']:\n"
        "        sys.argv=[str(HERE/script)]\n        runpy.run_path(str(HERE/script),run_name='__main__')\n"
        "finally:\n    sys.argv=saved"),
        md('## Совместные ответы\n\nL — свой НП, E — внешнее место. Порядок: продукты/гигиена, одежда, техника. '
        'Код внешнего места не устанавливает именованного центра. Неизвестный ответ по одной группе '
        'делает неизвестным весь профиль. Стандартизация описательная, не причинная.'),
        code("profiles=pd.read_csv(HERE/'joint_purchase_profiles.csv')\n"
        "display(profiles.query(\"scope=='rural_all'\")[[ 'year','n','LLL_pct','LEE_pct','EEE_pct','mixed_pct','unknown_pct']].round(2))\n"
        "households=pd.read_csv(HERE/'joint_household_school2024.csv')\n"
        "display(households.query(\"scope=='school_households' or scope=='remote_group'\")[[ 'scope','group','n_households','school_external_pct','internet_and_external_school_pct']].round(2))"),
        md('## Совместные профили и неоднородность\n\nДизайновые ошибки не оценены. '
        'Разные годы — разные выборки. Сезон и переписная основа менялись. '
        'Размер села не определяет его обслуживающий центр.'),code(CHARTS),
        md('## Предел вывода\n\nКОУЖ не выделяет окружение именно1273центров, WB/Ozon или географию '
        'получения онлайн-заказа. Same-household сочетание не доказывает совместную поездку или причинность. '
        'Источники и независимый разбор — в REPORT_RU.md и REVIEW_RU.md.')]
    nbformat.validate(nb)
    executed=NotebookClient(nb,timeout=900,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbformat.write(executed,OUT/'joint_dependencies_executed.ipynb')
    from markdown_it import MarkdownIt
    parser=MarkdownIt('default');html=['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Совместная география приобретения</title><style>body{max-width:1050px;margin:30px auto;padding:0 16px;font:16px/1.6 sans-serif;color:#25333c}img{width:100%}pre{white-space:pre-wrap;font-size:13px}table{display:block;overflow-x:auto;border-collapse:collapse}td,th{padding:5px;border-bottom:1px solid #ddd}</style>']
    for c in executed.cells:
        if c.cell_type=='markdown':html.append(parser.render(c.source));continue
        html.append('<details><summary>Код</summary><pre>'+escape(c.source)+'</pre></details>')
        for o in c.get('outputs',[]):
            data=o.get('data',{})
            if 'image/png' in data:html.append('<img src="data:image/png;base64,'+data['image/png']+'">')
            elif 'text/html' in data:html.append(data['text/html'])
            elif o.get('text'):html.append('<pre>'+escape(o.text)+'</pre>')
            elif 'text/plain' in data:html.append('<pre>'+escape(data['text/plain'])+'</pre>')
    (OUT/'joint_dependencies_notebook.html').write_text('\n'.join(html))


def pdf():
    spec=importlib.util.spec_from_file_location('pdf_renderer',HERE.parent/'dependency_20261026/build_deliverables.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    renderer.HERE=HERE;renderer.OUT=OUT
    renderer.pdf(documents=['REPORT_RU.md','REVIEW_RU.md'],filename='Joint_Dependencies_20261103.pdf',
        footer_text='Товарные профили и функции центров · 3 ноября 2026',
        title='Совместная география приобретения и функции средних центров')


if __name__=='__main__':
    if '--pdf-only' not in sys.argv:notebook()
    pdf();print(OUT)

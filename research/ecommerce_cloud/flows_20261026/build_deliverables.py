"""Execute the new survey notebook and export its figures and manuscript."""
from pathlib import Path
from html import escape
import importlib.util
import sys
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/ecommerce_flows_20261026/export'
OUT.mkdir(parents=True,exist_ok=True)

CHARTS=r'''
import matplotlib
matplotlib.use('module://matplotlib_inline.backend_inline')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,
    'axes.spines.top':False,'axes.spines.right':False,'text.color':'#25333c',
    'axes.edgecolor':'#87939a','figure.facecolor':'white'})
names={'food_and_personal_hygiene':'Продукты и личная гигиена',
    'clothing_and_footwear':'Одежда и обувь',
    'appliances_electronics_communications':'Техника, электроника, связь'}
own='own_locality_or_urban_district_pct'
fig,axs=plt.subplots(1,3,figsize=(13,5.4),sharey=True)
for ax,(goods,label),color in zip(axs,names.items(),['#536a77','#245c82','#9a722e']):
    g=rural.loc[rural.goods.eq(goods)].sort_values('year')
    value=float(standard.loc[standard.year.eq(2024)&standard.goods.eq(goods),own].iloc[0])
    ax.plot(g.year,g[own],marker='o',color=color,lw=2,label='Исходная доля')
    ax.scatter([2024],[value],marker='D',s=55,facecolors='white',edgecolors=color,zorder=5,
               label='2024 при составе 2022')
    for r in g.itertuples():
        ax.annotate(f'{getattr(r,own):.1f}%',(r.year,getattr(r,own)),
                    xytext=(0,10),textcoords='offset points',ha='center',fontsize=10)
    ax.annotate(f'{value:.1f}%',(2024,value),xytext=(0,-18),
                textcoords='offset points',ha='center',fontsize=10)
    ax.set(title=label,xticks=[2018,2022,2024],xlim=(2017.4,2024.8),ylim=(0,100))
    ax.grid(axis='y',color='#e1e6e9',lw=.7);ax.set_axisbelow(True)
axs[0].set_ylabel('Основное приобретение в своём НП, %')
axs[1].legend(loc='lower center',frameon=False,fontsize=9)
fig.suptitle('Заявленная география приобретения: сельские лица 15+ с информацией',fontsize=14)
fig.text(.06,.055,'Источник: пересчёт КОУЖ Росстата. Вес KVZV; ответы за другого члена семьи допускаются.\n'
         'Ромб: общая структура 2022 по размеру НП, возрасту и полу; это не причинная оценка.\n'
         'Основное место приобретения не разделяет продавца, заказ и получение и не измеряет число поездок.',fontsize=10)
fig.subplots_adjust(left=.07,right=.97,top=.80,bottom=.26,wspace=.17)
fig.savefig(OUT/'purchase_own_locality.png',dpi=160);display(fig);plt.close(fig)

fig,ax=plt.subplots(figsize=(10.5,5.5))
for group,label,color,marker in [('rural_all','Сельские школьники','#245c82','o'),
    ('urban_all','Городские школьники','#9a722e','s')]:
    g=school.loc[school.group.eq(group)].sort_values('year')
    ax.plot(g.year,g.pct_other_all_eligible,color=color,marker=marker,lw=2,label=label)
    for r in g.itertuples():
        ax.annotate(f'{r.pct_other_all_eligible:.2f}%',(r.year,r.pct_other_all_eligible),
                    xytext=(0,10),textcoords='offset points',ha='center')
ax.set(title='Посещаемая школа находится в другом населённом пункте',
    ylabel='Доля посещающих школу детей 7–14 лет, %',xticks=[2018,2022,2024],
    xlim=(2017.6,2024.5),ylim=(0,20))
ax.grid(axis='y',color='#e1e6e9',lw=.7);ax.set_axisbelow(True)
ax.legend(loc='upper left',frameon=False)
fig.text(.09,.055,'Источник: КОУЖ, детский блок. Вес KVZV; пропуски места школы сохранены в знаменателе.\n'
         'Это сведения о посещаемой школе; принимающий НП не назван, влияние WB/Ozon не оценено.\n'
         'Возрастная когорта и знаменатель отличаются от таблиц покупок.',fontsize=10)
fig.subplots_adjust(left=.09,right=.97,top=.86,bottom=.25)
fig.savefig(OUT/'school_other_locality.png',dpi=160);display(fig);plt.close(fig)

fig,ax=plt.subplots(figsize=(10.5,5.5))
for offset,group,label,color,marker in [(-.10,'remote_any','Использовали интернет','#245c82','o'),
    (.10,'no_remote','Не использовали интернет','#9a722e','s')]:
    for i,goods in enumerate(names):
        r=cross.loc[cross.goods.eq(goods)&cross.remote_group.eq(group)].iloc[0]
        ax.scatter(r.standardised_own_pct,i+offset,color=color,marker=marker,s=65,
                   label=label if i==0 else None)
        ax.text(r.standardised_own_pct+1.3,i+offset,f'{r.standardised_own_pct:.1f}%',va='center')
ax.set_yticks(range(3),list(names.values()));ax.invert_yaxis()
ax.set(xlim=(0,100),xlabel='Основное приобретение в своём НП, %')
fig.suptitle('Использование интернета и основная география приобретения, 2024',fontsize=13,y=.96)
ax.grid(axis='x',color='#e1e6e9',lw=.7);ax.set_axisbelow(True)
ax.legend(loc='upper center',bbox_to_anchor=(.5,1.20),frameon=False,fontsize=10)
fig.text(.05,.055,'Сельские лица 15+ с информацией; общая структура 2024 по возрасту, полу и размеру НП.\n'
    'Речь об основной географии всех приобретений людей, использовавших канал в этом году,\n'
    'а не о месте получения их интернет-заказов. Группы самоотбираются; причинный эффект не оценён.',fontsize=10)
fig.subplots_adjust(left=.31,right=.96,top=.74,bottom=.26)
fig.savefig(OUT/'purchase_remote_groups2024.png',dpi=160);display(fig);plt.close(fig)
'''


def notebook():
    nb=nbformat.v4.new_notebook()
    nb.metadata.kernelspec={'display_name':'Python 3','language':'python','name':'python3'}
    md=nbformat.v4.new_markdown_cell;code=nbformat.v4.new_code_cell
    nb.cells=[md('# География приобретения товаров и школьные связи\n\n'
        'В сельской части КОУЖ доля лиц 15+ с информацией, указывающих основное '
        'приобретение одежды в своём НП, изменилась с 27,35% в 2022 до 35,41% в 2024. '
        'При одинаковой структуре возраста, пола и размера НП доля 2024 — 32,15%. '
        'Для техники значения — 20,10%, 26,08% и 23,15%. '
        'Внешние приобретения остаются распространёнными. Среди сельских школьников '
        '7–14 лет школа в другом НП у 14,24% в 2024. Эти совокупности разные; '
        'именованные направления к средним центрам и причинный эффект WB/Ozon не измерены.'),
        md('## Источники и метод\n\nПубличные микроданные КОУЖ 2018/2022/2024. '
        'Восстановите 12 закреплённых файлов скриптом fetch_kouzh_inputs.py. '
        'Торговля: возраст 15+, информация получена (включая ответы другого лица), '
        'вес KVZV; затруднившиеся — отдельная категория. Школа: посещающие '
        'общеобразовательную организацию дети 7–14. Дизайновые ошибки не оценены. '
        '2018 — осенний опрос, 2022/2024 — май–июнь; вопрос о канале меняется '
        'с почты/интернета на интернет; переписная основа тоже изменилась. '
        'Это повторные срезы, не индивидуальная панель.'),
        code("from pathlib import Path\nimport runpy,io,contextlib,json,sys,pandas as pd\n"
        "from IPython.display import display\nROOT=Path.cwd()\n"
        "HERE=ROOT/'research/ecommerce_cloud/flows_20261026'\n"
        "OUT=ROOT/'work/ecommerce_flows_20261026/export'\nOUT.mkdir(parents=True,exist_ok=True)\n"
        "log=io.StringIO()\nprevious_argv=sys.argv[:]\ntry:\n"
        "    with contextlib.redirect_stdout(log):\n"
        "        for name in ['audit_schema_and_weights.py','analyze_purchase_geography.py',"
        "'analyze_school_links.py','independent_flows_check.py']:\n"
        "            sys.argv=[str(HERE/name)]\n"
        "            runpy.run_path(str(HERE/name),run_name='__main__')\n"
        "finally:\n    sys.argv=previous_argv\n"
        "print('Пересчитаны первичные агрегаты, опубликованная контрольная таблица и независимые сопоставления.')\n"
        "summaries=[]\nfor line in log.getvalue().splitlines():\n"
        "    try:\n        item=json.loads(line)\n"
        "    except (ValueError,TypeError):\n        continue\n"
        "    if isinstance(item,dict):\n        summaries.append(item)\n"
        "checks=sum(item.get('checks',0)+item.get('primary_shopping_checks',0)+"
        "item.get('primary_crossgroup_standardised_checks',0) for item in summaries)\n"
        "print(f'Независимые проверки: {checks}; все сопоставления завершились без расхождений.')"),
        md('## Основное место приобретения\n\nЗнаменатель — сельские лица 15+, по которым '
        'получены сведения. Доля относится к людям, не к заказам и не к расходам.'),
        code("purchases=pd.read_csv(HERE/'purchase_geography.csv')\n"
        "rural=purchases.loc[purchases.scope.eq('locality')&purchases.group.eq('rural')].copy()\n"
        "standard=pd.read_csv(HERE/'purchase_rural_standardised.csv')\n"
        "cross=pd.read_csv(HERE/'purchase_groups_standardised2024.csv')\n"
        "school=pd.read_csv(HERE/'school_locations.csv')\n"
        "labels={'food_and_personal_hygiene':'Продукты и гигиена','clothing_and_footwear':"
        "'Одежда, обувь','appliances_electronics_communications':'Техника, связь'}\n"
        "table=rural[['year','goods','sample_n','own_locality_or_urban_district_pct',"
        "'nearby_localities_or_districts_pct']].sort_values(['goods','year'])\n"
        "table['goods']=table.goods.map(labels)\n"
        "display(table.rename(columns={'year':'Год','goods':'Товары','sample_n':'Записей',"
        "'own_locality_or_urban_district_pct':'Свой НП, %',"
        "'nearby_localities_or_districts_pct':'Близлежащие, %'}).round(2).reset_index(drop=True))"),
        md('## Три разных наблюдения\n\nПервый рисунок — география основного приобретения; '
        'второй — место посещаемой школы; третий — сравнение разных групп людей, '
        'а не мест получения их онлайн-заказов. Ни один не является оценкой воздействия.'),
        code(CHARTS),
        md('## Граница ответа\n\nНовые данные измеряют национальную заявленную географию '
        'приобретения и внешнее обучение. Они не выделяют окружение именно наших '
        '1 273 центров, WB/Ozon, долю отменённых поездок или торговый доход. '
        'Расчёты с фиксированным составом — описательная чувствительность, не '
        'контрфактуал. Полный ответ и критический разбор находятся в REPORT_RU.md '
        'и REVIEW_FLOWS_RU.md.')]
    nbformat.validate(nb)
    executed=NotebookClient(nb,timeout=600,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbformat.write(executed,OUT/'purchase_geography_executed.ipynb')
    from markdown_it import MarkdownIt
    md=MarkdownIt('default')
    html=['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Покупки и школьные связи</title><style>body{max-width:1050px;margin:32px auto;padding:0 16px;'
        'font:16px/1.6 sans-serif;color:#25333c}img{width:100%}pre{white-space:pre-wrap;font-size:13px}'
        'table{border-collapse:collapse;display:block;overflow-x:auto}td,th{padding:5px 9px;border-bottom:1px solid #ddd}</style>']
    for c in executed.cells:
        if c.cell_type=='markdown':html.append(md.render(c.source));continue
        html.append('<details><summary>Код</summary><pre>'+escape(c.source)+'</pre></details>')
        for o in c.get('outputs',[]):
            data=o.get('data',{})
            if 'image/png' in data:html.append('<img src="data:image/png;base64,'+data['image/png']+'">')
            elif 'text/html' in data:html.append(data['text/html'])
            elif o.get('text'):html.append('<pre>'+escape(o.text)+'</pre>')
            elif 'text/plain' in data:html.append('<pre>'+escape(data['text/plain'])+'</pre>')
    (OUT/'purchase_geography_notebook.html').write_text('\n'.join(html))


def pdf():
    spec=importlib.util.spec_from_file_location('research_pdf_renderer',HERE.parent/'dependency_20261026/build_deliverables.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    renderer.HERE=HERE;renderer.OUT=OUT
    renderer.pdf(documents=['REPORT_RU.md','REVIEW_FLOWS_RU.md'],
        filename='Purchase_Geography_and_Centre_Functions_20261026.pdf',
        footer_text='География приобретения и функции центра · 26 октября 2026',
        title='Покупки, обучение и зависимость от внешнего центра')


if __name__=='__main__':
    if '--pdf-only' not in sys.argv:notebook()
    pdf()
    print(OUT)

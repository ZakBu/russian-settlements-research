from pathlib import Path
import nbformat as nbf
import re

OUT=Path(__file__).resolve().parent
n=nbf.v4.new_notebook()
n.metadata.kernelspec={'display_name':'Python3','language':'python','name':'python3'}
n.cells=[
nbf.v4.new_markdown_cell('''# Роль средних центров: население, обычные магазины и получение товаров

## Исследовательский приоритет
Главный исход — изменение относительного места центра в его окружении.
Измеряем отдельно долю населения и концентрацию обычной физической торговли.
Распространение ПВЗ — возможный механизм; количество ПВЗ не заменяет эти исходы.
Сокращение обычных магазинов проверяется, а не задаётся как обязательный результат.

В этом этапе получены частичная история Ozon, адресные магазинные реестры
сельского района2019–2026 и большой муниципальный слой физических объектов.
Есть фактические изменения, но причинное влияние маркетплейсов ещё не установлено.'''),
nbf.v4.new_markdown_cell('''## Методы и единицы
Средний центр в основной спецификации: административный центр ОКТМО2020,
имевший5000–49999жителей2002. Это явная аналитическая конвенция, не измеренный
торговый ранг. Чувствительность к размерным порогам и покрытию сохранена.

Демографическая доля рассчитана на одном фиксированном административном
контексте2020 и общей межпереписной оси НП с прямыми значениями2002/2021.
Она характеризует длительный фон, не постэффект ПВЗ. Административное
окружение не является измеренным покупательским ареалом.

Торговая доля C/S — число обычных магазинов нижнего муниципалитета центра
делённое на число магазинов всего района, синхронные IVкварталы2022–2024.
Во всех четырёх доступных выпусках2020/2021/2022/2026 нижний МО содержит
единственный тот же НП. Но составы2023/2024 и неизменность границ не проверены,
поэтому строгая единица результата — муниципальная территория центра;
привязка каждого магазина к НП остаётся условной. Адресный слой Чои даёт
другой, непосредственно поселенческий пример. Ничего не распределяется
между деревнями пропорционально населению.'''),
nbf.v4.new_code_cell('''from pathlib import Path
import contextlib,io,json,runpy
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display
ROOT=Path.cwd()
assert (ROOT/'system/centre_system_demography.csv').exists()
for file in ['analyze_functional_role.py','relate_receipt_and_trade.py']:
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(ROOT/file),run_name='__main__')
    print('Выполнен:',file)
plt.rcParams.update({'font.size':11,'axes.spines.top':False,
                     'axes.spines.right':False,'axes.axisbelow':True})
'''),
nbf.v4.new_markdown_cell('''## Демографический вес: исторический фон2002–2021
Падение собственной численности и потеря доли — разные события.
В основной пригодной подвыборке1195центров медиана собственной динамики−11,50%,
но медиана изменения доли+4,06п.п. Эти интервалы не привязаны к локальным
открытиям маркетплейсов. Изменение роли после2021 пока не следует из этого фона.'''),
nbf.v4.new_code_cell('''dem=pd.read_csv(ROOT/'system/centre_system_demography.csv')
g=dem[dem.medium_primary2002 & dem.demographic_comparison_supported].copy()
assert len(g)==1195
share=g.centre_population_share_change_pp
decline=g.centre_change2002_2021_pct.lt(0)
rows=[]
for label,mask in [('Доля выросла ≥1п.п.',share.ge(1)),
                   ('Модуль изменения доли <1п.п.',share.abs().lt(1)),
                   ('Доля снизилась ≥1п.п.',share.le(-1))]:
    rows.append({'Категория':label,'Население сократилось':int((mask&decline).sum()),
                 'Население выросло/не изменилось':int((mask&~decline).sum())})
dt=pd.DataFrame(rows)
assert dt.iloc[:,1:].to_numpy().sum()==len(g)
display(dt)
fig,ax=plt.subplots(figsize=(11,5.5))
ax.barh(dt['Категория'],dt['Население сократилось'],color='#426b97',label='Население сократилось')
ax.barh(dt['Категория'],dt['Население выросло/не изменилось'],
        left=dt['Население сократилось'],color='#d79533',label='Выросло/не изменилось')
ax.set_xlabel('Число центров, шт.')
ax.set_title('Убыль населения центра не равна потере его относительного веса')
ax.grid(axis='x',alpha=.2)
ax.invert_yaxis()
ax.legend()
fig.tight_layout()
fig.subplots_adjust(bottom=.21)
fig.text(.02,.02,'2002–2021; 1195 центров с 5–50 тыс. жителей в 2002 в фиксированном контексте 2020.\\n'
         'Это длительный фон, не чистый доплатформенный период; влияние ПВЗ и неизменность границ не установлены.',fontsize=9.5)
fig.savefig(ROOT/'population_weight.png',dpi=150)
plt.show()
'''),
nbf.v4.new_markdown_cell('''## Физическая торговля в центре и районе: основной функциональный исход
Источник — показатель количества физических объектов БДПМО в обработке
«Если быть точным», версия28.09.2026. Он не является числом зарегистрированных
юрлиц. Обычные магазины отделены от общепита, рынков, аптек и АЗС.
Все магазинные подкатегории не суммируются между собой.

Основная панель C/S включает174средних центра для «Магазинов»,161для
специализированных непродовольственных. Это выбранные пригодные случаи,
не репрезентативная оценка по всем центрам России. Годовые строки, IVкварталы,
«На1января» и новая номенклатура2025 не объединяются в один ряд.'''),
nbf.v4.new_code_cell('''trade=pd.read_csv(ROOT/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv')
trade=trade[trade.medium_primary2002].copy()
tab=[]
for category,h in trade.groupby('category'):
    x=h.centre_stock_change2022_2024
    tab.append({'Категория':category,'Центров':len(h),
                'Запас сократился':int(x.lt(0).sum()),'Запас вырос':int(x.gt(0).sum()),
                'Не изменился':int(x.eq(0).sum()),
                'Доля снизилась':int(h.centre_share_change2022_2024_pp.lt(-1e-9).sum()),
                'Медиана Δдоли, п.п.':h.centre_share_change2022_2024_pp.median()})
display(pd.DataFrame(tab).round(2))
t=pd.read_csv(ROOT/'trade_share_threshold_sensitivity.csv')
display(t)
plot=t[t.share_threshold_pp.eq(1)]
fig,ax=plt.subplots(figsize=(11,5.7))
left=np.zeros(len(plot))
for field,label,color in [
    ('share_loss_n','Доля снизилась ≥1п.п.','#426b97'),
    ('share_between_thresholds_n','Изменение по модулю <1п.п.','#b8bec5'),
    ('share_gain_n','Доля выросла ≥1п.п.','#d79533')]:
    pct=100*plot[field]/plot.centres_n
    ax.barh(range(len(plot)),pct,left=left,label=label,color=color)
    left=left+pct.to_numpy()
ax.set_yticks(range(len(plot)),['Обычные магазины, n=174','Спец. непродовольственные, n=161'])
ax.set_xlim(0,100)
ax.set_xlabel('Доля центров соответствующей панели, %')
ax.set_title('Изменение концентрации физической торговли в территории центра')
ax.grid(axis='x',alpha=.2)
ax.invert_yaxis()
ax.legend(loc='upper center',bbox_to_anchor=(.5,-.15),ncol=1)
fig.tight_layout()
fig.subplots_adjust(bottom=.42)
fig.text(.02,.02,'C/S: нижний муниципалитет центра / весь район, IV кварталы 2022–2024.\\n'
         'Поселенческая идентичность условна: полный состав 2023/2024 не проверен. Эффект ПВЗ не оценён.',fontsize=9.5)
fig.savefig(ROOT/'trade_weight.png',dpi=150)
plt.show()
'''),
nbf.v4.new_markdown_cell('''## Непосредственно поселенческие адреса: Чойский район
Получены8официальных реестров2019–2026;705пронумерованных магазин–дата после
исключения других секций. Отсутствующие НП оставлены неизвестными.
Адресная чувствительность отдельно исправляет11подтверждённых написаний.

Источник2022/2023 после заголовка одинаков. В2025/2026 итоги не сходятся
со строками; эти точки показаны как требующие подтверждения. Число записей
не равно проверенному числу открытий или закрытий. Почтовые наименования
имеют отдельную чувствительность; явных маркеров ПВЗ в исходниках нет,
что не доказывает отсутствия совмещённых функций. Один район — проверка
измеримости исхода, не национальная экстраполяция.'''),
nbf.v4.new_code_cell('''choya=pd.read_csv(ROOT/'choya_functional_concentration.csv')
display(choya[choya.category.isin(['all_observed','nonfood'])].round(2))
z=choya[choya.category.eq('nonfood')].sort_values('year')
solid=z[z.year.le(2024)]
late=z[z.year.ge(2024)]
fig,axes=plt.subplots(1,2,figsize=(12,5.8))
for field,label,color in [('centre_listed_entries','Село Чоя','#426b97'),
                         ('surrounding_listed_entries','Окружение','#d79533')]:
    axes[0].plot(solid.year,solid[field],marker='o',label=label,color=color)
    axes[0].plot(late.year,late[field],ls='--',color=color)
    uncertain=late[late.year.gt(2024)]
    axes[0].scatter(uncertain.year,uncertain[field],facecolors='white',edgecolors=color,zorder=3)
axes[0].set_ylabel('Перечисленные магазинные записи, шт.')
axes[0].set_title('Непродовольственные магазины')
axes[0].legend()
axes[1].plot(solid.year,solid.centre_share_pct,marker='o',color='#426b97')
axes[1].plot(late.year,late.centre_share_pct,ls='--',color='#426b97')
axes[1].scatter(uncertain.year,uncertain.centre_share_pct,facecolors='white',edgecolors='#426b97',zorder=3)
axes[1].set_ylabel('Доля перечисленных записей, %')
axes[1].set_title('Доля центра в районе')
axes[1].set_ylim(0,60)
for ax in axes:
    ax.set_xticks([2019,2021,2024,2026])
    ax.set_xlabel('Дата реестра: 1 января указанного года')
    ax.grid(alpha=.2)
fig.tight_layout()
fig.subplots_adjust(bottom=.25)
fig.text(.02,.02,'Адресные реестры администрации Чойского района, 2019–2026.\\n'
         'Пустые маркеры/пунктир 2025–2026: расхождения строк с итогами. В 2022/2023 содержимое одинаково.\\n'
         'Динамика записей не доказывает реальные закрытия и причинное влияние маркетплейсов.',fontsize=9.5)
fig.savefig(ROOT/'choya_trade_role.png',dpi=150)
plt.show()
'''),
nbf.v4.new_markdown_cell('''## Сопоставление с рассредоточением получения товаров
Таблица связывает центр с положительной записью WB на обеих датах и чистое
изменение числа других НП с записями. Каталожный интервал29.09.2022–11.03.2024
и торговый интервалIV2022–IV2024 различаются. Профили источников не полностью
гармонизированы. Это совместное описание, не «обработанная» и «контрольная» группы.
Сравнения учитывают радиусы и два профиля; они не оценивают причинность.'''),
nbf.v4.new_code_cell('''co=pd.read_csv(ROOT/'receipt_trade_descriptive_summary.csv')
display(co[(co.radius_km==5)&co.catalogue_profile.eq('allcatalog_objects')][
    ['category','receipt_category','centres_n','stock_decline_n',
     'share_loss_atleast1pp_n','share_gain_atleast1pp_n','median_trade_share_change_pp']].round(2))
'''),
nbf.v4.new_markdown_cell('''## Полученная история Ozon
Два реальных официальных APIответа:19.03.2023 —3444ID,09.06.2024 —1885ID.
Первый покрывает Москву/Подмосковье, второй — более узкую часть Москвы.
Неизвестны исходные POSTviewport. Разность3444→1885 не является сокращением сети.
Дополнительно получены32положительных геосвидетельства2021–2025; это архивная
выборка, а не равномерная история России. Отдельный XLSX36958адресов не имеет
подтверждённой даты наблюдения и не объявляется срезом2025 по свойствам файла.
Даты архивирования не названы открытиями, отсутствие в архиве не значит отсутствия услуги.'''),
nbf.v4.new_code_cell('''oz=[]
for name in ['ozon_opp_api_positive_points_20230319.parquet',
             'ozon_opp_api_positive_points_20240609.parquet']:
    p=ROOT/'ozon'/name
    df=pd.read_parquet(p)
    oz.append({'Файл':name,'Записей':len(df)})
display(pd.DataFrame(oz))
'''),
nbf.v4.new_markdown_cell('''## Что теперь можно и чего нельзя заключить
Получены независимые исходы относительного веса центра. Сокращение запаса
магазинов и потеря доли в окружении не обязаны совпадать; то же верно для населения.
Распространение получения заказов вне центра может сосуществовать с его
демографической концентрацией и неодинаковой динамикой непродовольственных функций.

Фактический рост магазинов не доказывает отсутствия вытеснения: без маркетплейсов
рост мог быть выше. Падение также не доказывает причинности: есть иные процессы.
Нужны согласованные временные определения воздействия, подходящие сравнения,
проверка территориальных изменений и независимое подтверждение истории объектов.
Сейчас оценка «насколько ПВЗ вызвал изменение роли центра» ещё не идентифицирована.

Подробные результаты и оговорки: ROLE_RESULTS.txt. Расчёты и источник каждой
таблицы доступны в system/, bdmo/singleton/, shops/, ozon/ и корневых скриптах.
Покупательский опрос и невидимые потоки в обязательный дизайн не возвращались.''')
]
for cell in n.cells:
    if cell.cell_type=='markdown':
        cell.source=re.sub(r'([А-Яа-яЁё])(?=\d)',r'\1 ',cell.source)
        cell.source=re.sub(r'(\d)(?=[А-Яа-яЁё])',r'\1 ',cell.source)
nbf.validate(n)
nbf.write(n,OUT/'settlement_roles.ipynb')
print(OUT/'settlement_roles.ipynb')

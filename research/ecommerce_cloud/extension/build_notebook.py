"""Build and execute the new reproducible analytical notebook; preserve old notebooks."""
from pathlib import Path
import nbformat as nbf
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output
import os

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
nb=nbf.v4.new_notebook()
nb.metadata.kernelspec={'display_name':'Ecommerce research portable Python','language':'python','name':'ecommerce-cloud-20261025'}
md=nbf.v4.new_markdown_cell;code=nbf.v4.new_code_cell
nb.cells=[
md('# Средние центры и окружение: национальное продолжение\n\nИсполненное продолжение 25 октября 2026. Независимые исходы: население, торговые запасы и площадь; история WB/Ozon анализируется отдельно. Ни одна таблица ниже не является причинным эффектом платформ. Полный русский научный текст — `research/ecommerce_cloud/REPORT_RU.md`.'),
code("from pathlib import Path\nimport json, subprocess, sys\nimport pandas as pd\nfrom IPython.display import display\nROOT=Path.cwd()\nHERE=ROOT/'research/ecommerce_cloud/extension'\nassert (ROOT/'AGENTS.md').exists()\nresult=subprocess.run([sys.executable,str(HERE/'run_extension.py')],cwd=ROOT,capture_output=True,text=True)\nprint(result.stdout[-2500:])\nif result.returncode: print(result.stderr[-5000:])\nassert result.returncode==0\nprint('Python:',sys.version.split()[0])"),
md('## Исходы после переписи\n170 средних центров, 34 региона; 1 января 2023–2025. Окружение — остаток муниципального района. Полный состав 2023/2024 не подтверждён. Совпадение с городской таблицей проверяет две публикации одного процесса Росстата, а не независимые измерения.'),
code("p=json.loads((HERE/'outcomes/recent_population_summary.json').read_text())\ndisplay(pd.DataFrame(p['results']))\ndisplay(pd.DataFrame([json.loads((HERE/'outcomes/urban_remainders_summary.json').read_text())]))"),
md('## Количество, площадь, центр и окружение\n174 торговых центра — 13,67% из 1273, 35 из 81 региона. Площадь не приравнивается к обороту или мощности. Десятикратные разрывы не исправлены догадкой; исключения показаны как чувствительность.'),
code("display(pd.read_csv(HERE/'outcomes/centre_periphery_stock_types.csv'))\ndisplay(pd.read_csv(HERE/'outcomes/area_sensitivity.csv'))\ndisplay(pd.read_csv(HERE/'outcomes/selection_characteristics.csv'))"),
md('## География и масштаб\nФиксированные круги перекрываются и не являются наблюдёнными ареалами. Порог в процентных пунктах зависит от размера доли, поэтому отдельно показаны знак и логарифмический относительный темп.'),
code("display(pd.read_csv(HERE/'demographic_size.csv'))\ndisplay(pd.read_csv(HERE/'spatial_sensitivity.csv'))"),
md('## Исторические свидетельства\nНовое Ozon API расширяет историю назад до 2021 года и добавляет Ростов, но остаётся оконной выборкой. Постоянный кодовый профиль WB не равен постоянной полноте и открытиям.'),
code("display(pd.read_csv(HERE/'history/ozon_cms_summary.csv'))\ndisplay(pd.read_csv(HERE/'history/wb_historical_profile_summary.csv')) if (HERE/'history/wb_historical_profile_summary.csv').exists() else display(pd.read_csv(HERE/'history/wb_historical_profile.csv'))\ndisplay(pd.read_csv(HERE/'history/wb_historical_pairs.csv').head())"),
md('## Независимая проверка\nПересчёт первичных значений, вычитания окружения и прямых расстояний проверяет арифметику. Границы, полнота архивов и контрфактуал этими проверками не доказываются.'),
code("for name in ['independent_csv_results.json','independent_new_outcomes_results.json','independent_spatial_results.json']:\n p=HERE/'review'/name\n if p.exists():\n  x=json.loads(p.read_text()); x.pop('checks',None);print(name);display(x)\nprint('Причинный эффект: не идентифицирован.')"),
]
out=HERE/'national_extension.ipynb'
nbf.write(nb,out)
# This workspace disallows binding both TCP and IPC ZMQ sockets. Execute the
# actual cells in an IPython process instead of manufacturing cached outputs.
# The saved notebook remains a standard notebook usable with a normal kernel.
nb.metadata['execution_engine']='IPython in-process; TCP/IPC kernel sockets unavailable in this workspace'
shell=InteractiveShell.instance()
os.chdir(ROOT)
count=0
for cell in nb.cells:
    if cell.cell_type!='code':continue
    count+=1
    with capture_output(stdout=True,stderr=True,display=True) as captured:
        result=shell.run_cell(cell.source,store_history=True)
    cell.execution_count=count
    cell.outputs=[]
    if captured.stdout:cell.outputs.append(nbf.v4.new_output('stream',name='stdout',text=captured.stdout))
    if captured.stderr:cell.outputs.append(nbf.v4.new_output('stream',name='stderr',text=captured.stderr))
    for output in captured.outputs:
        cell.outputs.append(nbf.v4.new_output('display_data',data=output.data,metadata=output.metadata))
    if result.error_before_exec or result.error_in_exec:
        nbf.write(nb,out)
        raise RuntimeError(f'Cell {count} failed: {result.error_before_exec or result.error_in_exec}')
nbf.write(nb,out)
print(out)

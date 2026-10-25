"""Build and execute the real nonshop population figure notebook with nbclient."""
from pathlib import Path
import hashlib
import json
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "research/ecommerce_cloud/continuation/render_nonshop.py"
OUTPUT = ROOT / "work/ecommerce_continuation"
OUTPUT.mkdir(parents=True, exist_ok=True)
source = SOURCE.read_text(encoding="utf8")
source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
embedded = source.replace("ROOT = Path(__file__).resolve().parents[3]", "ROOT = Path.cwd()")
embedded = embedded.replace('if __name__ == "__main__":\n    render()\n',
                            'figure_summary = render(ROOT)\n')
assert embedded != source and "figure_summary = render(ROOT)" in embedded
intro = """# Демографическая концентрация средних центров, 2023–2025

Воспроизводимое продолжение исследования по России. Расчёт не отбирает центры
по наличию магазинов. Исходная совокупность — 1 273 средних центра; сопоставленная
условная панель — 425 центров в 55 регионах. Это доступная панель, не
вероятностная выборка России.

**Что измеряется.** Собственное население центра и его доля в административном
контексте. Связь центра и муниципалитетов датирована 10 января 2020 года.
Три официальные публикации составов проверены отдельно; действовавшие на1января состояния и постоянство координатных границ целиком не подтверждены. Поездки не наблюдались.
Результат нельзя интерпретировать как причинный эффект WB или Ozon.

Рисунки ниже создаются из panels.csv, фиксированной национальной оси 2021 года
и centre_system_demography.csv. Источник расчётной панели — скрипт
extension/outcomes/nonshop_population_contexts.py; первичные численности —
Росстат, БДПМО Y48112027 и принятый бюллетень городского населения.
"""
panel_summary=json.loads((ROOT/'work/ecommerce_extension_outcomes/nonshop_population_contexts/summary.json').read_text())
intro=intro.replace('425 центров в 55 регионах',str(panel_summary['overlap_old170']['new_medium_positive_remainder_n'])+' центров в '+str(panel_summary['representativeness']['new_regions_n'])+' регионах')
notebook = nbformat.v4.new_notebook()
notebook.metadata.update({
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
    "renderer_source_sha256": source_sha,
    "scientific_status": "descriptive_conditional_territories_causality_not_identified",
})
notebook.cells = [
    nbformat.v4.new_markdown_cell(intro),
    nbformat.v4.new_markdown_cell(
        "## Выполнение расчёта и проверок\n\nНиже встроен фактический код построения; "
        "табличные значения и рисунки вычисляются ядром Python при исполнении. "
        "SHA256 исходного renderer: " + source_sha + "."),
    nbformat.v4.new_code_cell(
        "from pathlib import Path\n"
        "import subprocess, sys\n"
        "ROOT=Path.cwd()\n"
        "for script, args in [\n"
        " ('research/ecommerce_cloud/extension/outcomes/nonshop_population_contexts.py', []),\n"
        " ('research/ecommerce_cloud/continuation/check_nonshop_population.py', ['work/ecommerce_extension_outcomes/nonshop_population_contexts']),\n"
        " ('research/ecommerce_cloud/continuation/restore_rosters_pinned.py', []),\n"
        " ('research/ecommerce_cloud/extension/outcomes/full_roster_analysis.py', []),\n"
        " ('research/ecommerce_cloud/extension/outcomes/trade_roster_sensitivity.py', [])\n"
        "]:\n"
        " result=subprocess.run([sys.executable, str(ROOT/script), *args], cwd=ROOT, capture_output=True, text=True, check=True)\n"
        " print(script, 'completed successfully; complete outputs preserved under work/')\n"
    ),
    nbformat.v4.new_code_cell(embedded),
    nbformat.v4.new_code_cell(
        "from IPython.display import display, Image\n"
        "display(pd.DataFrame([{\n"
        "    'Средних центров в основе': figure_summary['target_n'],\n"
        "    'Центров в условной панели': figure_summary['selected_n'],\n"
        "    'Регионов панели': figure_summary['selected_regions'],\n"
        "    'Доля выросла': figure_summary['target_counts'].get('gain', 0),\n"
        "    'Доля снизилась': figure_summary['target_counts'].get('loss', 0),\n"
        "    'Сам центр сократился': figure_summary['selected_own_population_decline_n'],\n"
        "    'Остальная часть сократилась': figure_summary['selected_remainder_population_decline_n']\n"
        "}]))\n"
        "display(pd.DataFrame(figure_summary['inputs']))"),
    nbformat.v4.new_markdown_cell(
        "## Проверка составов\n\nСравниваются коды и названия НП в полных официальных публикациях. "
        "Совпадение перечня не доказывает постоянство геометрических границ."),
    nbformat.v4.new_code_cell(
        "import json\n"
        "receipt=json.loads((ROOT/'work/ecommerce_extension_outcomes/nonshop_population_contexts/roster_analysis/summary.json').read_text())\n"
        "table=pd.DataFrame(receipt['nonshop_demography_sensitivity'])\n"
        "display(table[(table['view']=='publication') & (table['restriction'].isin(['baseline_conditional','same_code_name_sets_vs2020_2021']))])\n"
    ),
    nbformat.v4.new_markdown_cell(
        "## География наблюдений\n\nТочки показывают местоположение центров. Серый цвет "
        "обозначает отсутствие сопоставленного исхода; считать его нулевым изменением нельзя. "
        "Полигонов административных территорий или ареалов поездок на карте нет."),
    nbformat.v4.new_code_cell(
        "display(Image(filename=str(ROOT / "
        "'work/ecommerce_continuation/figures/nonshop_population_map.png')))"),
    nbformat.v4.new_markdown_cell(
        "## Центр и административный остаток\n\nНа диаграмме показаны все наблюдения. "
        "Выше диагонали центр меняется лучше остальной части контекста. "
        "Рост доли может происходить при сокращении самого центра."),
    nbformat.v4.new_code_cell(
        "display(Image(filename=str(ROOT / "
        "'work/ecommerce_continuation/figures/nonshop_population_scatter.png')))"),
    nbformat.v4.new_markdown_cell(
        "## Граница вывода\n\nПолучена описательная картина условной демографической "
        "концентрации. Она сама по себе не устанавливает изменение функций обслуживания, "
        "фактических поездок, причинное влияние платформ или репрезентативный результат "
        "для всех средних центров. Неустановленное постоянство границ и селекция доступных исходов остаются "
        "ограничениями. На карте и диаграмме сохранены эти оговорки."),
]
destination = OUTPUT / "nonshop_population_executed.ipynb"
nbformat.write(notebook, destination)
client = NotebookClient(notebook, timeout=1200, kernel_name="python3",
                        resources={"metadata": {"path": str(ROOT)}},
                        allow_errors=False)
client.execute()
nbformat.validate(notebook)
assert all(c.execution_count is not None for c in notebook.cells if c.cell_type == "code")
assert not any(o.output_type == "error" for c in notebook.cells if c.cell_type == "code" for o in c.outputs)
nbformat.write(notebook, destination)
summary = {
    "path": str(destination.relative_to(ROOT)),
    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    "renderer_source_sha256": source_sha,
    "code_cells": sum(c.cell_type == "code" for c in notebook.cells),
    "all_code_cells_executed": True, "errors": 0,
    "execution_method": "nbclient NotebookClient.execute with fresh python3 kernel",
}
(OUTPUT / "notebook_execution.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
print("NONSHOP_NOTEBOOK_EXECUTION_BEGIN")
print(json.dumps(summary, ensure_ascii=False))
print("NONSHOP_NOTEBOOK_EXECUTION_END")

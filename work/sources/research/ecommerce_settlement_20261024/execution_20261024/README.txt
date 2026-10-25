Национальный эмпирический этап WB/Ozon — 24.10.2026

ПРОДОЛЖЕНИЕ: ../history_stage_20261024/HISTORY_RESULTS.txt.
Во втором этапе получены7реальных архивовWB2022–2024, официальные ОКТМО
и региональные физические магазины. Прежние выводы о неполученной истории
ниже относятся к состоянию данных на момент первого этапа.

Начните с RESEARCH_RESULTS.txt. Расчётный носитель — national_research.ipynb;
national_research.html — локальный просмотр сохранённых исполненных ячеек.
Три специализированных агента: geography/, demography/, audit/.
Координатор: accessibility/, сводный ноутбук, результаты и проверка входов.

Ноутбук выполняет все пять скриптов; audit/peer_review.py отдельно пересчитывает
350 численных соотношений. Каждая папка содержит собственные результаты.

Повторный запуск из этой папки в текущей среде:
PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 geography/analyze_geography.py
PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 demography/analyze_demography.py
PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 accessibility/analyze_accessibility.py
PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 audit/audit.py
PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 audit/peer_review.py

Для ноутбука: build_notebook.py создаёт исходный notebook без исполненных ячеек;
после его запуска выполнить notebook сверху вниз в Jupyter/nbclient и сохранить.
Сданный national_research.ipynb уже исполнен; заново создавать его ради просмотра
не нужно. nbconvert в текущей среде отсутствует, HTML получен прямым экспортом
сохранённых выводов. Графики просмотрены отдельно, верх HTML проверен в браузере.

Исходные национальные parquet находятся в соседней national/, полный перечень
фактически прочитанных входов со схемами и SHA256 — audit/audit.json.
Они не дублируются в этой папке и не добавляются в Git автоматически.
environment.json документирует текущий Python; переносимая среда требует pandas,
numpy, pyarrow, matplotlib, nbformat, nbclient и ipykernel. Временный PYTHONPATH
относится только к текущей машине.

Главная граница: выполнено исследование конфигурации и селективности размещения;
причинное влияние и изменения системы во времени не идентифицированы.
Полная сопоставимая история сети и физических магазинов пока не получена.

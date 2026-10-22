set -euo pipefail
echo "docs: record history cleanup, fix pinned commit links" > "$RUNNER_TEMP/commit_message"
touch "$RUNNER_TEMP/no_log"
python - <<'PY'
import json
from pathlib import Path

OLD = "85aebaff43d1b8ecf7314a697add2b2370f93d73"
NEW = "c2a1e28c024edbf6db6751f96877e6e6b6b977dc"
OLD_PATH = "sgrt/literature/delimitation/karachurina_mkrtchyan/METHOD_READOUT.md"
ORIG_PATH = "research/sgrt_word_completion_20261021/literature/cycle07_delimitation/karachurina_mkrtchyan/METHOD_READOUT.md"


def replace(path, old, new, count):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert text.count(old) == count, (path, old[:40], text.count(old))
    p.write_text(text.replace(old, new), encoding="utf-8")


replace("references/sources.json", f"{OLD}/{OLD_PATH}", f"{NEW}/{ORIG_PATH}", 3)
replace("references/sources.json", OLD, NEW, 10)
json.loads(Path("references/sources.json").read_text(encoding="utf-8"))

replace(
    "archive/side_studies/geographic_regimes_stage2_2026-10-18/protocols/user_design.md",
    "https://github.com/ZakBu/russian-settlements-research/blob/6170041d3294db2f040f3d73f0138c86caca7aaa/research/settlement_context_20261018/docs/FINAL_REPORT.md",
    "[FINAL_REPORT.md](../../settlement_context_2026-10-18/docs/FINAL_REPORT.md) (в архиве)",
    1,
)

replace(
    "AI_START_HERE.md",
    "Клонируй без старой истории — так быстрее:",
    "Полный клон весит около 400 МБ; для работы достаточно последней версии:",
    1,
)

replace(
    "archive/README.md",
    "Ничего не потеряно. Вернуть удалённое можно двумя способами:",
    "Ничего не потеряно. Вернуть удалённое можно так:",
    1,
)
replace(
    "archive/README.md",
    "2. Взять файл из Git по метке, поставленной на последнее состояние до разбора:",
    "2. Взять файл из Git по метке, поставленной на последнее состояние до разбора. Так можно вернуть только файлы до 1 МБ: крупные файлы данных убраны из истории Git (см. ниже), их берите из ZIP или из полной копии истории.",
    1,
)
Path("archive/README.md").open("a", encoding="utf-8").write(
    "\n## История Git\n\n"
    "22 октября 2026 года история Git очищена от файлов больше 1 МБ, которых нет в текущем дереве: старых версий таблиц, архивов и карт. "
    "Объём истории уменьшился с 9,9 ГБ до 0,4 ГБ. Все коммиты, их сообщения, код и тексты сохранились, но хеши коммитов изменились. "
    "Соответствие старых и новых хешей — в файле `commit-map.txt` релиза "
    "[git-history-backup-20261022](https://github.com/ZakBu/russian-settlements-research/releases/tag/git-history-backup-20261022). "
    "Например, срез базы населения от 13 октября, который указан в каталогах данных как `source_commit` 85aebaff, теперь — коммит c2a1e28c.\n\n"
    "Полная копия прежней истории со всеми ветками и данными лежит в том же релизе: шесть частей общим объёмом около 10 ГБ, инструкция по сборке — в описании релиза.\n\n"
    "Рабочая ветка связывания переписей (`research/mass-linkage-2026-10-02`, 145 коммитов за 2–13 октября) сохранена меткой `census-linkage-work-2026-10-13`. "
    "Остальные ветки удалены. Их содержимое либо вошло в `main`, либо перенесено в этот архив, либо было промежуточной попыткой переупаковать репозиторий; все они есть в полной копии истории.\n"
)

p = Path("research_context/current_state.json")
state = json.loads(p.read_text(encoding="utf-8"))
state["updated_moscow"] = "2026-10-22T19:40:00+03:00"
state["known_limits"].append(
    "Хеши коммитов до 22.10.2026 изменились при очистке истории Git; старые хеши (например, source_commit в каталогах данных) переводятся по commit-map.txt релиза git-history-backup-20261022."
)
state["entrypoints"]["history_backup"] = "https://github.com/ZakBu/russian-settlements-research/releases/tag/git-history-backup-20261022"
p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
cat >> research_context/diary/2026-10-22.md <<'EOF'

## 2026-10-22, 19:10–19:40 (Москва) — очистка истории Git

**Итог.** История репозитория уменьшилась с 9,9 ГБ до 0,4 ГБ: полный клон теперь скачивается за секунды, а не за десятки минут. Текущие файлы не изменились: дерево `main` до и после очистки совпадает побайтно.

**Что сделали.** Сначала сохранили полную копию прежней истории (10 веток и 13 меток, около 10 ГБ) в релиз [git-history-backup-20261022](https://github.com/ZakBu/russian-settlements-research/releases/tag/git-history-backup-20261022) и сверили контрольные суммы на сервере. Затем убрали из всех коммитов 1 734 файла больше 1 МБ, которых нет в текущем дереве: это старые версии таблиц, архивов и карт. Коммиты, их сообщения, код и тексты сохранены, в `main` — 250 коммитов. Рабочую ветку связывания переписей сохранили меткой `census-linkage-work-2026-10-13`, остальные ветки удалили. Ссылки на конкретные коммиты в `references/sources.json` переведены на новые хеши.

**Ограничения.** Хеши коммитов изменились; соответствие старых и новых — в `commit-map.txt` того же релиза. GitHub ещё какое-то время может показывать прежний размер репозитория: старые объекты держатся ссылками закрытых PR, пока GitHub их не удалит.

**Дальше.** Репозиторий готов к работе над районами тяготения: [sgrt/README.md](../../sgrt/README.md), раздел «Следующие шаги».
EOF
git diff --stat

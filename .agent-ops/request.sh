set -euo pipefail
echo "refactor: split current materials from archive, drop agent process artifacts" > "$RUNNER_TEMP/commit_message"
SOURCE=ffd44464abd4a0f277e100487294fd6902b4e0d5
echo "source commit (pre-cleanup main): $SOURCE"
TAG=repository-archive-20261022
WORK=$RUNNER_TEMP/archive
mkdir -p "$WORK"
sudo apt-get install -y -qq zip >/dev/null

python .agent-ops/reorganize.py --out "$WORK/plan"
(git ls-files -z | tr '\0' '\n' | grep -Fxf "$WORK/plan/removed.txt" > "$WORK/removed_present.txt") || true
wc -l "$WORK/plan/removed.txt" "$WORK/removed_present.txt"
zip -q -X -y "$WORK/removed-from-main-20261022.zip" -@ < "$WORK/removed_present.txt"

declare -A SIDE=(
  [research/settlement-context-2026-10-18]="research/settlement_context_20261018 settlement_context_2026-10-18"
  [research/geographic-regimes-stage2-2026-10-18]="research/geographic_regimes_stage2 geographic_regimes_stage2_2026-10-18"
  [codex/settlement-progress-report-20261021]="reports/settlement_progress_20261021 settlement_progress_report_2026-10-21"
)
mkdir -p "$WORK/side"
for branch in "${!SIDE[@]}"; do
  read -r dir name <<< "${SIDE[$branch]}"
  git fetch -q --depth 1 origin "$branch"
  rm -rf "$WORK/side/$name" && mkdir -p "$WORK/side/$name"
  git archive FETCH_HEAD "$dir" | tar -x -C "$WORK/side/$name" --strip-components=$(echo "$dir" | tr -cd '/' | wc -c | awk '{print $1+1}')
  echo "$branch -> $name: $(find "$WORK/side/$name" -type f | wc -l) files"
done
(cd "$WORK/side" && zip -q -r -X -y "$WORK/side-studies-20261022.zip" .)
find "$WORK/side/settlement_progress_report_2026-10-21" -name '*.pdf' -exec cp {} "$WORK/settlement-progress-report-20261021.pdf" \;
find "$WORK/side/settlement_progress_report_2026-10-21" -name '*.docx' -exec cp {} "$WORK/settlement-progress-report-20261021.docx" \;
find "$WORK/side/geographic_regimes_stage2_2026-10-18" -name '*.pdf' -exec cp {} "$WORK/geographic-regimes-stage2-20261018.pdf" \;
ls -la "$WORK"

python .agent-ops/reorganize.py --apply --out "$WORK/plan"

for name in $(ls "$WORK/side"); do
  (cd "$WORK/side/$name" && find . -type f \( -name '*.md' -o -name '*.py' -o -name '*.yaml' -o -name '*.yml' -o -name '*.txt' -o -name '*.bib' -o -name '*.sql' -o -name '*.ipynb' \) -size -1M) | while read -r f; do
    mkdir -p "archive/side_studies/$name/$(dirname "$f")"
    cp "$WORK/side/$name/$f" "archive/side_studies/$name/$f"
  done
done
cp "$WORK/plan/removed.txt" archive/removed_files.txt
git add -A -f archive/side_studies archive/removed_files.txt
git add -A

cat > "$WORK/notes.md" <<'EOF'
Архив материалов, убранных из рабочего дерева при разборе репозитория 22 октября 2026 года. Метка указывает на последнее состояние main до разбора.

- `removed-from-main-20261022.zip` — все удалённые из main файлы с исходными путями (машинные выгрузки JSON/CSV и служебные файлы агентов). Список — `archive/removed_files.txt`.
- `side-studies-20261022.zip` — полные папки трёх побочных исследований из закрытых черновых PR #2, #3 и #5, включая PDF, DOCX, рисунки и таблицы.
- `settlement-progress-report-20261021.pdf` / `.docx` — иллюстрированный отчёт «Трансформация территориальной структуры расселения России в 2002–2021 гг.» (бывший PR #5).
- `geographic-regimes-stage2-20261018.pdf` — записка об атласе изменений расселения (бывший PR #3).

Путеводитель — archive/README.md.
EOF
if ! gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$REPO" --target "$SOURCE" --title "Архив разбора репозитория, 22.10.2026" --notes-file "$WORK/notes.md" --latest=false
fi
for f in removed-from-main-20261022.zip side-studies-20261022.zip settlement-progress-report-20261021.pdf settlement-progress-report-20261021.docx geographic-regimes-stage2-20261018.pdf; do
  if [ -f "$WORK/$f" ]; then gh release upload "$TAG" "$WORK/$f" --repo "$REPO" --clobber; fi
done
gh release view "$TAG" --repo "$REPO" --json assets --jq '.assets[] | "\(.name) \(.size) \(.digest)"'
git status --short | awk '{print $1}' | sort | uniq -c

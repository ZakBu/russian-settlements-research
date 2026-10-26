"""Author contract checks with isolated content; no live publication or Git operations."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import site_content as site


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "web/content"
        (self.base / "materials").mkdir(parents=True)
        (self.base / "visuals").mkdir()
        self.write("research.json", [{"id": "population", "title": "Население", "description": "Переписи", "status": "ready", "summary": "База", "nextStep": "Сравнение", "order": 1}])
        self.write("datasets.json", [{"id": "census", "title": "Переписи", "release": "census-v1", "sourceCommit": "a" * 40, "url": "https://example.org/releases/census-v1/data.csv", "period": "2002–2021", "scope": "Россия", "limitations": ["Покрытие не равно точности"]}])
        self.visual = {"id": "population-trend", "template": "census-trend", "title": "Численность", "caption": "Наблюдения переписей", "datasetId": "census", "palette": "blue", "unit": "человек", "categories": ["2002", "2010", "2021"], "series": [{"name": "Население", "values": [10, None, 0]}]}
        self.write("visuals/population-trend.json", self.visual)
        self.material = {"id": "population-note", "researchId": "population", "title": "Изменение населения", "summary": "Пропуск сохранён", "kind": "finding", "topic": "Демография", "territory": "Пример", "period": "2002–2021", "publishedAt": "2026-10-25", "updatedAt": "2026-10-25", "visibility": "published", "evidence": "calculation", "currency": "current", "sourceCommit": "a" * 40, "sources": [{"title": "Переписи", "url": "https://example.org/census"}], "datasetIds": ["census"], "visualIds": ["population-trend"], "body": "Численность известна за два года.\n\nЗа 2010 год сведений нет."}
        self.write("materials/population-note.json", self.material)

    def write(self, name, value):
        (self.base / name).write_text(json.dumps(value, ensure_ascii=False))

    def test_real_contract_retains_null_and_zero(self):
        self.assertEqual(site.validate(self.root), [])
        self.assertEqual(site.load(self.base / "visuals/population-trend.json")["series"][0]["values"], [10, None, 0])

    def test_wiki_references_require_real_visible_documents_and_registered_visuals(self):
        self.material["body"] = "[[missing|Источник]]\n\n:::visual not-registered\n:::"
        self.write("materials/population-note.json", self.material)
        errors = site.validate(self.root)
        self.assertTrue(any("Unknown wiki document" in e["message"] for e in errors))
        self.assertTrue(any("Register inline visual" in e["message"] for e in errors))
        draft = dict(self.material, id="draft-note", visibility="draft", body="Черновик")
        self.write("materials/draft-note.json", draft)
        self.material["body"] = "[[draft-note|Метод]]"
        self.write("materials/population-note.json", self.material)
        self.assertTrue(any("cannot point to a draft" in e["message"] for e in site.validate(self.root)))

    def test_wiki_examples_in_code_are_literal_and_inline_visuals_are_unique(self):
        self.material["body"] = "```md\n[[missing]]\n:::visual unknown\n:::\n```\n\n`[[also-missing]]`\n\n:::visual population-trend\n:::"
        self.write("materials/population-note.json", self.material)
        self.assertEqual(site.validate(self.root), [])
        self.material["body"] += "\n\n:::visual population-trend\n:::"
        self.write("materials/population-note.json", self.material)
        self.assertTrue(any("only once" in e["message"] for e in site.validate(self.root)))

    def test_missing_unit_has_field_specific_error(self):
        self.visual["unit"] = ""
        self.write("visuals/population-trend.json", self.visual)
        self.assertTrue(any(e["field"] == "unit" for e in site.validate(self.root)))

    def test_missing_source_reference_blocks_publication(self):
        self.material["datasetIds"] = ["missing"]
        self.material["sources"] = []
        self.write("materials/population-note.json", self.material)
        fields = {e["field"] for e in site.validate(self.root)}
        self.assertIn("datasetIds", fields)
        self.assertIn("sources", fields)

    def test_unknown_palette_and_raw_options_rejected(self):
        self.visual.update(palette="#ff0000", option={"series": []})
        self.write("visuals/population-trend.json", self.visual)
        fields = {e["field"] for e in site.validate(self.root)}
        self.assertTrue({"palette", "option"}.issubset(fields))

    def test_mismatched_categories_and_nonfinite_values_rejected(self):
        self.visual["series"][0]["values"] = [float("nan")]
        self.write("visuals/population-trend.json", self.visual)
        self.assertGreaterEqual(len(site.validate(self.root)), 2)

    def test_script_and_executable_markdown_rejected(self):
        for text in ('<script>alert(1)</script>', '[link](javascript:alert(1))', 'import Chart from "x"', '<Chart />'):
            with self.subTest(text=text):
                self.material["body"] = text
                self.write("materials/population-note.json", self.material)
                self.assertTrue(any(e["field"] == "body" for e in site.validate(self.root)))

    def test_draft_creation_is_idempotent_and_does_not_publish(self):
        command = ["--root", str(self.root), "new", "--id", "new-note", "--research", "population", "--title", "Новый вывод"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(site.main(command), 0)
            original = (self.base / "materials/new-note.json").read_bytes()
            self.assertEqual(site.main(command), 0)
        self.assertEqual((self.base / "materials/new-note.json").read_bytes(), original)
        self.assertEqual(site.load(self.base / "materials/new-note.json")["visibility"], "draft")
        self.assertEqual(site.validate(self.root), [])

    def test_existing_different_material_is_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, "Already exists"):
            site.save_new(self.base / "materials/population-note.json", {"id": "population-note"})

    def test_json_errors_are_machine_readable(self):
        self.visual["unit"] = ""
        self.write("visuals/population-trend.json", self.visual)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = site.main(["--root", str(self.root), "validate", "--json"])
        self.assertEqual(code, 1)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["valid"])
        self.assertIn("message", result["errors"][0])

    def test_latest_dataset_is_rejected(self):
        rows = site.load(self.base / "datasets.json")
        rows[0]["url"] = "https://example.org/releases/latest/data.csv"
        self.write("datasets.json", rows)
        self.assertTrue(any(e["field"] == "census.release" for e in site.validate(self.root)))

    def test_state_ingestion_is_content_sensitive_idempotent_and_preserves_articles(self):
        state_dir = self.root / "research_context"
        state_dir.mkdir()
        state_path = state_dir / "current_state.json"
        state = {"updated_moscow": "2026-10-25T23:36:03+03:00", "parts": {"population_base": {"status": "ready", "summary": "Связаны наблюдения переписей.", "doc": "POPULATION_BASE.md"}}, "known_limits": ["Покрытие не равно точности."]}
        state_path.write_text(json.dumps(state))
        original = (self.base / "materials/population-note.json").read_bytes()
        first = site.sync_state(self.root, "a" * 40)
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(first["updatedResearch"], ["population"])
        self.assertEqual(site.sync_state(self.root, "a" * 40)["created"], [])
        self.assertEqual((self.base / "materials/population-note.json").read_bytes(), original)
        state["parts"]["population_base"]["summary"] = "Уточнена сопоставимость переписей."
        state_path.write_text(json.dumps(state))
        self.assertEqual(len(site.sync_state(self.root, "b" * 40)["created"]), 1)
        self.assertEqual(len(list((self.base / "materials").glob("state-*.json"))), 2)
        self.assertEqual(site.validate(self.root), [])

    def test_build_time_change_alone_creates_no_state_note(self):
        state_dir = self.root / "research_context"
        state_dir.mkdir()
        path = state_dir / "current_state.json"
        state = {"updated_moscow": "2026-10-25T23:36:03+03:00", "parts": {"population_base": {"status": "ready", "summary": "Готовая база"}}, "known_limits": []}
        path.write_text(json.dumps(state))
        site.sync_state(self.root, "a" * 40)
        state["updated_moscow"] = "2026-10-26T06:00:00+03:00"
        path.write_text(json.dumps(state))
        result = site.sync_state(self.root, "b" * 40)
        self.assertEqual(result["created"], [])
        self.assertEqual(result["updatedResearch"], [])

    def test_source_document_change_is_detected_without_summary_change(self):
        state_dir = self.root / "research_context"
        state_dir.mkdir()
        source = self.root / "POPULATION_BASE.md"
        source.write_text("Первое описание данных.")
        state = {"updated_moscow": "2026-10-25T23:36:03+03:00", "parts": {"population_base": {"status": "ready", "summary": "Готовая база", "doc": "POPULATION_BASE.md"}}, "known_limits": []}
        (state_dir / "current_state.json").write_text(json.dumps(state))
        first = site.sync_state(self.root, "a" * 40)
        self.assertEqual(len(first["created"]), 1)
        source.write_text("Уточнение ограничений данных без изменения короткого итога.")
        second = site.sync_state(self.root, "b" * 40)
        self.assertEqual(len(second["created"]), 1)
        self.assertNotEqual(first["created"], second["created"])
        self.assertEqual(site.sync_state(self.root, "b" * 40)["created"], [])
        self.assertEqual(site.validate(self.root), [])

    def test_new_state_archives_previous_snapshot_preserving_curated_material(self):
        state_dir = self.root / "research_context"
        state_dir.mkdir()
        path = state_dir / "current_state.json"
        state = {"updated_moscow": "2026-10-25T23:36:03+03:00", "parts": {"population_base": {"status": "ready", "summary": "Первый итог"}}, "known_limits": []}
        path.write_text(json.dumps(state))
        first = site.sync_state(self.root, "a" * 40)
        old_path = self.base / "materials" / (first["created"][0] + ".json")
        original_old = site.load(old_path)
        curated = (self.base / "materials/population-note.json").read_bytes()
        state["parts"]["population_base"]["summary"] = "Уточнённый итог"
        state["updated_moscow"] = "2026-10-26T06:00:00+03:00"
        path.write_text(json.dumps(state))
        second = site.sync_state(self.root, "b" * 40)
        self.assertEqual(second["archived"], first["created"])
        old = site.load(old_path)
        self.assertEqual(old["visibility"], "archived")
        self.assertEqual(old["currency"], "superseded")
        for field in ("body", "sources", "sourceCommit", "publishedAt", "updatedAt"):
            self.assertEqual(old[field], original_old[field])
        current_path = self.base / "materials" / (second["created"][0] + ".json")
        current = site.load(current_path)
        self.assertEqual(current["supersedes"], first["created"][0])
        self.assertEqual(current["visibility"], "published")
        self.assertEqual(current["currency"], "current")
        self.assertEqual((self.base / "materials/population-note.json").read_bytes(), curated)
        before = {p.name: p.read_bytes() for p in (self.base / "materials").glob("*.json")}
        repeat = site.sync_state(self.root, "b" * 40)
        self.assertEqual(repeat["created"], [])
        self.assertEqual(repeat["archived"], [])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.base / "materials").glob("*.json")})
        self.assertEqual(site.validate(self.root), [])

    def test_existing_duplicate_state_notes_reconciled_once(self):
        state_dir = self.root / "research_context"
        state_dir.mkdir()
        state = {"updated_moscow": "2026-10-25T23:36:03+03:00", "parts": {"population_base": {"status": "ready", "summary": "Текущий итог"}}, "known_limits": []}
        (state_dir / "current_state.json").write_text(json.dumps(state))
        initial = site.sync_state(self.root, "a" * 40)
        old = site.load(self.base / "materials" / (initial["created"][0] + ".json"))
        old["id"] = "state-population-oldfingerprint"
        old["updatedAt"] = "2026-10-24"
        self.write("materials/" + old["id"] + ".json", old)
        result = site.sync_state(self.root, "a" * 40)
        self.assertEqual(result["created"], [])
        self.assertEqual(result["archived"], [old["id"]])
        again = site.sync_state(self.root, "a" * 40)
        self.assertEqual(again["archived"], [])

    def test_newer_document_commit_pins_source_and_publication_date(self):
        state_dir = self.root / "research_context"
        state_dir.mkdir()
        (self.root / "POPULATION_BASE.md").write_text("Уточнение источников.")
        state = {"updated_moscow": "2026-10-25T23:36:03+03:00", "parts": {"population_base": {"status": "ready", "summary": "Готовая база", "doc": "POPULATION_BASE.md"}}, "known_limits": []}
        (state_dir / "current_state.json").write_text(json.dumps(state))
        with patch.object(site.subprocess, "check_output", side_effect=["a" * 40 + "\n", "b" * 40 + "\n2026-10-26T05:00:00+03:00\n"]) as command:
            result = site.sync_state(self.root)
        record = site.load(self.base / "materials" / (result["created"][0] + ".json"))
        self.assertEqual(record["sourceCommit"], "b" * 40)
        self.assertEqual(record["publishedAt"], "2026-10-26T05:00:00+03:00")
        self.assertIn("POPULATION_BASE.md", command.call_args.args[0])
        self.assertIn("b" * 40, record["sources"][1]["url"])

    def layer_fixture(self):
        datasets = site.load(self.base / "datasets.json")
        datasets[0]["url"] = "https://raw.githubusercontent.com/example/research/" + "a" * 40 + "/centres.csv"
        datasets[0]["sha256"] = "b" * 64
        self.write("datasets.json", datasets)
        return {"id": "centre-members", "researchId": "population", "title": "Размер окружения центра", "description": "Модельный состав", "datasetId": "census", "adapter": "csv-settlement", "geometry": "point", "fields": {"id": "star_id", "name": "centre_name", "value": "strict_external_member_count", "settlementKey": "centre_settlement_id"}, "palette": "blue", "unit": "НП", "period": "2026", "evidence": "model", "visibility": "published"}

    def test_layer_cli_is_published_only_explicitly_and_idempotent(self):
        self.layer_fixture()
        fields = self.root / "fields.json"
        fields.write_text(json.dumps({"id": "star_id", "name": "centre_name", "value": "strict_external_member_count", "settlementKey": "centre_settlement_id"}))
        command = ["--root", str(self.root), "layer", "--id", "new-layer", "--research", "population", "--dataset-ref", "census", "--adapter", "csv-settlement", "--geometry", "point", "--title", "Окружение", "--unit", "НП", "--period", "2026", "--evidence", "model", "--fields-file", str(fields)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(site.main(command), 0)
            original = (self.base / "layers/new-layer.json").read_bytes()
            self.assertEqual(site.main(command), 0)
            self.assertEqual((self.base / "layers/new-layer.json").read_bytes(), original)
            self.assertEqual(site.main(command[:-1] + [str(fields), "--publish", "--id", "published-layer"]), 0)
        self.assertEqual(site.load(self.base / "layers/new-layer.json")["visibility"], "draft")
        self.assertEqual(site.load(self.base / "layers/published-layer.json")["visibility"], "published")
        self.assertEqual(site.validate(self.root), [])

    def test_layer_rejects_unknown_geometry_and_csv_polygon(self):
        row = self.layer_fixture()
        datasets = {r["id"]: r for r in site.load(self.base / "datasets.json")}
        for geometry in ("triangle", "polygon"):
            row["geometry"] = geometry
            self.assertTrue(any(field == "geometry" for field, _ in site.layer_errors(row, datasets, {"population": {}})))

    def test_layer_requires_pinned_hashed_source_and_field_contract(self):
        row = self.layer_fixture()
        datasets = {r["id"]: r for r in site.load(self.base / "datasets.json")}
        datasets["census"]["sha256"] = "bad"
        datasets["census"]["url"] = "https://raw.githubusercontent.com/example/research/main/centres.csv"
        del row["fields"]["settlementKey"]
        problems = site.layer_errors(row, datasets, {"population": {}})
        self.assertTrue(any("SHA-256" in message for _, message in problems))
        self.assertTrue(any("immutable" in message for _, message in problems))
        self.assertTrue(any(field == "fields.settlementKey" for field, _ in problems))

    def test_visual_links_only_registered_published_layers(self):
        row = self.layer_fixture()
        (self.base / "layers").mkdir()
        self.write("layers/centre-members.json", row)
        self.visual["mapState"] = {"layers": ["population", "centre-members"]}
        self.write("visuals/population-trend.json", self.visual)
        self.assertEqual(site.validate(self.root), [])
        self.visual["mapState"]["layers"] = ["misspelled-layer"]
        self.write("visuals/population-trend.json", self.visual)
        self.assertTrue(any(e["field"] == "mapState.layers" for e in site.validate(self.root)))
        self.visual["mapState"]["layers"] = ["centre-members"]
        row["visibility"] = "draft"
        self.write("layers/centre-members.json", row)
        self.write("visuals/population-trend.json", self.visual)
        self.assertTrue(any("published layer" in e["message"] for e in site.validate(self.root)))


if __name__ == "__main__":
    unittest.main()

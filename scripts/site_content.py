#!/usr/bin/env python3
"""Author and validate declarative atlas content; no JavaScript is accepted in articles."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KINDS = {"finding", "method", "note", "correction"}
EVIDENCE = {"observation", "calculation", "model", "hypothesis", "method"}
TEMPLATES = {"census-trend", "bars", "comparison", "scatter", "table", "settlement-map", "service-links"}
PALETTES = {"population-change", "categorical", "service-type", "blue"}
MATERIAL_FIELDS = {"id", "researchId", "title", "summary", "kind", "topic", "territory", "period", "publishedAt", "updatedAt", "visibility", "evidence", "currency", "sourceCommit", "sources", "datasetIds", "visualIds", "body", "supersedes", "featured", "tags"}
VISUAL_FIELDS = {"id", "template", "title", "caption", "datasetId", "palette", "unit", "series", "categories", "data", "mapState", "limitations"}
LAYER_FIELDS = {"id", "researchId", "title", "description", "datasetId", "adapter", "geometry", "fields", "palette", "unit", "period", "evidence", "visibility"}
BUILTIN_LAYERS = {"population", "schools", "medical", "services", "links", "centres", "districts", "regions"}


def layer_errors(row, datasets, research):
    """Local contract validation; exporter separately verifies source bytes and geometries."""
    errors = []
    def error(field, message):
        errors.append((field, message))
    if not isinstance(row, dict):
        return [("$", "Expected a layer object")]
    for field in LAYER_FIELDS - {"fields"}:
        if not isinstance(row.get(field), str) or (field != "description" and not row[field].strip()):
            error(field, "Required nonempty string")
    for field in row.keys() - LAYER_FIELDS:
        error(field, "Unknown layer field; arbitrary code and rendering options are forbidden")
    if not ID.fullmatch(str(row.get("id", ""))):
        error("id", "Use lowercase kebab words")
    if str(row.get("id")) in BUILTIN_LAYERS:
        error("id", "This ID is reserved for a built-in layer")
    for field, allowed in (("adapter", {"geojson", "csv-points", "csv-settlement"}), ("geometry", {"point", "line", "polygon"}), ("palette", PALETTES), ("evidence", EVIDENCE), ("visibility", {"draft", "published", "archived"})):
        if not isinstance(row.get(field), str) or row[field] not in allowed:
            error(field, "Expected one of: " + ", ".join(sorted(allowed)))
    if row.get("adapter") in ("csv-points", "csv-settlement") and row.get("geometry") != "point":
        error("geometry", "CSV adapters support points only; line/polygon need GeoJSON")
    if not isinstance(row.get("researchId"), str) or row["researchId"] not in research:
        error("researchId", "Unknown research ID")
    dataset = datasets.get(row.get("datasetId")) if isinstance(row.get("datasetId"), str) else None
    if dataset is None:
        error("datasetId", "Register an existing pinned dataset")
    else:
        url = dataset.get("url", "")
        if not isinstance(url, str) or not url.startswith("https://") or not valid_url(url):
            error("datasetId", "Layer source must be a pinned HTTPS CSV/GeoJSON URL")
        elif re.search(r"/(?:main|master|HEAD|latest)(?:/|$)", url, re.I) or "/blob/" in url:
            error("datasetId", "Use an immutable raw source, not main/latest or a GitHub HTML blob page")
        if not re.fullmatch(r"[a-f0-9]{64}", str(dataset.get("sha256", ""))):
            error("datasetId", "Layer dataset requires an exact 64-character SHA-256")
    fields = row.get("fields")
    for field in ("title", "description", "unit", "period"):
        if not safe_markdown(str(row.get(field, ""))):
            error(field, "Plain text only; executable content is forbidden")
    if not isinstance(fields, dict):
        error("fields", "Expected a field mapping object")
    else:
        for field in set(fields) - {"id", "name", "value", "longitude", "latitude", "settlementKey"}:
            error("fields." + field, "Unknown mapping; use source field names only")
        required = {"id", "name"}
        if row.get("adapter") == "csv-points":
            required.update({"longitude", "latitude"})
        if row.get("adapter") == "csv-settlement":
            required.add("settlementKey")
        for field in required:
            if not isinstance(fields.get(field), str) or not fields[field].strip():
                error("fields." + field, "Required source column name")
        for field, value in fields.items():
            if not isinstance(value, str) or not value.strip() or not safe_markdown(value):
                error("fields." + field, "Expected a nonempty source field name, never code")
    return errors


def content(root):
    return Path(root) / "web/content"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_new(path, value):
    """Identical retries are harmless; an existing different record is never replaced."""
    if path.exists():
        if load(path) == value:
            return False
        raise ValueError(f"Already exists: {path}. Edit the existing record explicitly or choose a new ID.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def safe_id(value):
    if not ID.fullmatch(value):
        raise ValueError("ID must use lowercase ASCII words separated by hyphens, e.g. census-comparison")
    return value


def safe_markdown(text):
    # Plain Markdown only. HTML tags, MDX expressions/imports and executable links are disallowed.
    if re.search(r"<\s*/?\s*[A-Za-z!]|^\s*(?:import|export)\s|\{[^\n]*(?:=>|require\(|import\(|<\w)", text, re.M):
        return False
    link_text = re.sub(r"\[@data:[a-z0-9]+(?:-[a-z0-9]+)*(?:,[^\]\n]+)?\]", "", text)
    if re.search(r"(?:javascript|vbscript|data)\s*:", link_text, re.I):
        return False
    return True


def document_prose(text):
    """Ignore literal code examples while validating declarative references."""
    lines, fence = [], ""
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            mark = marker.group(1)
            if not fence:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = ""
            continue
        if not fence:
            lines.append(line)
    return re.sub(r"(`+)[^\n]*?\1", "", "\n".join(lines))


def document_references(text):
    prose = document_prose(text)
    links = re.findall(r"\[\[([a-z0-9]+(?:-[a-z0-9]+)*)(?:#[^\]|\n]+)?(?:\|[^\]\n]+)?\]\]", prose)
    visuals = re.findall(r"^:::visual[ \t]+([a-z0-9]+(?:-[a-z0-9]+)*)[ \t]*$", prose, re.M)
    return links, visuals


def valid_url(value):
    return isinstance(value, str) and urlparse(value).scheme in {"https", "http"} and bool(urlparse(value).netloc)


def validate(root=ROOT, material_id=None):
    errors = []
    base = content(root)

    def err(file, field, message):
        errors.append({"file": str(file.relative_to(root)), "field": field, "message": message})

    def read(path, fallback):
        try:
            return load(path)
        except (OSError, ValueError) as exc:
            err(path, "$", str(exc))
            return fallback

    def records(path):
        rows = read(path, [])
        if not isinstance(rows, list):
            err(path, "$", "Expected an array of objects")
            return {}
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not ID.fullmatch(row["id"]):
                err(path, "id", "Expected an object with a lowercase kebab ID")
                continue
            if row["id"] in result:
                err(path, "id", f"Duplicate ID: {row['id']}")
            result[row["id"]] = row
        return result

    research = records(base / "research.json")
    datasets = records(base / "datasets.json")
    tags_path = base / "tags.json"
    tags = records(tags_path) if tags_path.exists() else {}
    for key, tag in tags.items():
        for field in tag.keys() - {"id", "label", "aliases"}:
            err(tags_path, f"{key}.{field}", "Unknown tag field")
        if not isinstance(tag.get("label"), str) or not tag["label"].strip() or not safe_markdown(tag["label"]):
            err(tags_path, f"{key}.label", "Expected a nonempty plain-text tag label")
        aliases = tag.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias.strip() or not safe_markdown(alias) for alias in aliases):
            err(tags_path, f"{key}.aliases", "Expected an array of plain-text search synonyms")
    literature_path = root / "references/sources.json"
    literature = {r["id"]: r for r in load(literature_path).get("records", [])} if literature_path.exists() else {}

    def bibliography_fields(row, path, prefix=""):
        for field in ("publisher", "place", "journal", "pages", "doi", "referenceId"):
            if field in row and (not isinstance(row[field], str) or not row[field].strip()):
                err(path, prefix + field, "Expected factual nonempty bibliographic text")
        if "authors" in row and not (isinstance(row["authors"], str) and row["authors"].strip() or isinstance(row["authors"], list) and row["authors"] and all(isinstance(a, str) and a.strip() for a in row["authors"])):
            err(path, prefix + "authors", "Expected author text or an array of author names")
        if "year" in row and not re.fullmatch(r"\d{4}", str(row["year"])):
            err(path, prefix + "year", "Use the known publication year, not an inferred date")
        if "accessed" in row:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row["accessed"])):
                    raise ValueError()
                datetime.strptime(row["accessed"], "%Y-%m-%d")
            except (ValueError, TypeError):
                err(path, prefix + "accessed", "Expected the actual access date YYYY-MM-DD")
        if row.get("referenceId") and row["referenceId"] not in literature:
            err(path, prefix + "referenceId", "Unknown literature registry record")
    for key, row in research.items():
        for field in ("title", "description", "status", "summary", "nextStep", "order"):
            if field not in row:
                err(base / "research.json", f"{key}.{field}", "Required field")
    for key, row in datasets.items():
        bibliography_fields(row, base / "datasets.json", key + ".")
        for field in ("title", "release", "sourceCommit", "url", "period", "scope", "limitations"):
            if field not in row:
                err(base / "datasets.json", f"{key}.{field}", "Required field")
        if not re.fullmatch(r"[a-f0-9]{40}", str(row.get("sourceCommit", ""))):
            err(base / "datasets.json", f"{key}.sourceCommit", "Pin the full 40-character source commit")
        if not valid_url(row.get("url")):
            err(base / "datasets.json", f"{key}.url", "Use a pinned HTTP(S) source URL")
        if "/latest" in str(row.get("url", "")) or str(row.get("release", "")).lower() == "latest":
            err(base / "datasets.json", f"{key}.release", "Pin an immutable release, not GitHub Latest")
        if "sha256" in row and not re.fullmatch(r"[a-f0-9]{64}", str(row["sha256"])):
            err(base / "datasets.json", f"{key}.sha256", "Expected 64 lowercase hexadecimal characters")
        if not isinstance(row.get("limitations"), list):
            err(base / "datasets.json", f"{key}.limitations", "Expected an array; describe actual scientific limitations")

    layers = {}
    for path in sorted((base / "layers").glob("*.json")):
        row = read(path, {})
        for field, message in layer_errors(row, datasets, research):
            err(path, field, message)
        if isinstance(row, dict):
            if row.get("id") != path.stem:
                err(path, "id", "Layer ID must match its filename")
            layers[path.stem] = row

    visuals = {}
    for path in sorted((base / "visuals").glob("*.json")):
        row = read(path, {})
        if not isinstance(row, dict):
            err(path, "$", "Expected a visual object")
            continue
        key = row.get("id")
        if key != path.stem or not ID.fullmatch(str(key)):
            err(path, "id", "ID must match the filename and use lowercase kebab words")
        visuals[path.stem] = row
        for field in ("id", "template", "title", "caption", "datasetId", "palette", "unit"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                err(path, field, "Required nonempty string; unit examples: человек, %, км, ед.")
        for field in row.keys() - VISUAL_FIELDS:
            err(path, field, "Unknown field; use the declared template, not custom code or ECharts options")
        if not isinstance(row.get("template"), str) or row["template"] not in TEMPLATES:
            err(path, "template", "Choose a registered template: " + ", ".join(sorted(TEMPLATES)))
        if not isinstance(row.get("palette"), str) or row["palette"] not in PALETTES:
            err(path, "palette", "Choose a semantic palette: " + ", ".join(sorted(PALETTES)))
        if not isinstance(row.get("datasetId"), str) or row["datasetId"] not in datasets:
            err(path, "datasetId", "Unknown dataset; register its pinned source in datasets.json")
        if row.get("template") in ("census-trend", "bars", "comparison"):
            if not isinstance(row.get("categories"), list) or not row["categories"] or not isinstance(row.get("series"), list) or not row["series"]:
                err(path, "series", "This chart needs nonempty categories and series from actual data")
        if row.get("template") in ("scatter", "table") and (not isinstance(row.get("data"), list) or not row["data"]):
            err(path, "data", "This template needs a nonempty array of actual observations")
        if "categories" in row and (not isinstance(row["categories"], list) or any(not isinstance(c, str) for c in row["categories"])):
            err(path, "categories", "Expected an array of strings")
        if "series" in row:
            if not isinstance(row["series"], list):
                err(path, "series", "Expected an array")
            else:
                for index, series in enumerate(row["series"]):
                    if not isinstance(series, dict) or not isinstance(series.get("name"), str) or not isinstance(series.get("values"), list):
                        err(path, f"series.{index}", "Expected {name, values:[number|null]}")
                        continue
                    if isinstance(row.get("categories"), list) and len(series["values"]) != len(row["categories"]):
                        err(path, f"series.{index}.values", "Length must match categories; retain missing observations as null")
                    if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in series["values"]):
                        err(path, f"series.{index}.values", "Only finite numbers or null; unknown is not zero")
        for field in ("title", "caption"):
            if not safe_markdown(str(row.get(field, ""))):
                err(path, field, "Plain text/Markdown only; executable content is not accepted")
        if "mapState" in row:
            map_state = row["mapState"]
            if not isinstance(map_state, dict):
                err(path, "mapState", "Expected an object")
            else:
                active = map_state.get("layers", [])
                if not isinstance(active, list) or any(not isinstance(value, str) for value in active):
                    err(path, "mapState.layers", "Expected an array of registered layer IDs")
                else:
                    for value in active:
                        if value not in BUILTIN_LAYERS and value not in layers:
                            err(path, "mapState.layers", f"Unknown layer: {value}")
                        elif value in layers and layers[value].get("visibility") != "published":
                            err(path, "mapState.layers", f"Map links require a published layer: {value}")

    materials = {}
    for path in sorted((base / "materials").glob("*.json")):
        row = read(path, {})
        if not isinstance(row, dict):
            err(path, "$", "Expected a material object")
            continue
        key = row.get("id")
        materials[path.stem] = row
        if key != path.stem or not ID.fullmatch(str(key)):
            err(path, "id", "ID must match the filename and use lowercase kebab words")
        for field in MATERIAL_FIELDS - {"supersedes", "featured", "tags"}:
            if field not in row:
                err(path, field, "Required field")
        for field in row.keys() - MATERIAL_FIELDS:
            err(path, field, "Unknown material field")
        for field, allowed in (("kind", KINDS), ("evidence", EVIDENCE), ("visibility", {"draft", "published", "archived"}), ("currency", {"current", "known-issues", "superseded"})):
            if not isinstance(row.get(field), str) or row[field] not in allowed:
                err(path, field, "Expected one of: " + ", ".join(sorted(allowed)))
        if not isinstance(row.get("researchId"), str) or row["researchId"] not in research:
            err(path, "researchId", "Unknown research; register it in research.json")
        if "tags" in row:
            selected_tags = row["tags"]
            if not isinstance(selected_tags, list):
                err(path, "tags", "Expected an array of tag registry IDs")
            else:
                seen_tags = set()
                for ref in selected_tags:
                    if not isinstance(ref, str) or ref not in tags:
                        err(path, "tags", f"Unknown tag: {ref}")
                    elif ref in seen_tags:
                        err(path, "tags", f"Duplicate tag: {ref}")
                    else:
                        seen_tags.add(ref)
        for field, known in (("datasetIds", datasets), ("visualIds", visuals)):
            if not isinstance(row.get(field), list):
                err(path, field, "Expected an array of IDs")
            else:
                for ref in row[field]:
                    if not isinstance(ref, str) or ref not in known:
                        err(path, field, f"Unknown reference: {ref}")
        for ref in row.get("visualIds", []) if isinstance(row.get("visualIds"), list) else []:
            if isinstance(ref, str) and ref in visuals and visuals[ref].get("datasetId") not in (row.get("datasetIds") if isinstance(row.get("datasetIds"), list) else []):
                err(path, "datasetIds", f"Include dataset used by visual {ref}")
        if not isinstance(row.get("sources"), list):
            err(path, "sources", "Expected [{title,url}]")
        else:
            for index, source in enumerate(row["sources"]):
                if not isinstance(source, dict) or not source.get("title") or not valid_url(source.get("url")):
                    err(path, f"sources.{index}", "Expected a title and HTTP(S) source URL")
                else:
                    bibliography_fields(source, path, f"sources.{index}.")
        if row.get("visibility") == "published":
            for field in ("title", "summary", "topic", "territory", "period", "sourceCommit", "body"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    err(path, field, "Complete this scientific context before publication")
            if not row.get("sources"):
                err(path, "sources", "Published findings require evidence/source links")
            if not re.fullmatch(r"[a-f0-9]{40}", str(row.get("sourceCommit", ""))):
                err(path, "sourceCommit", "Pin the full 40-character source commit")
            for field in ("publishedAt", "updatedAt"):
                try:
                    datetime.fromisoformat(row.get(field, "").replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    err(path, field, "Expected an ISO date or timestamp")
        if not isinstance(row.get("body"), str) or not safe_markdown(row.get("body", "")):
            err(path, "body", "Use plain Markdown. HTML/JS/MDX, imports and executable links are forbidden")
    for key, row in materials.items():
        path = base / "materials" / f"{key}.json"
        prose = document_prose(str(row.get("body", "")))
        for ref in re.findall(r"\[@([^\],\s]+)(?:,[^\]\n]+)?\]", prose):
            if ref.startswith("source:"):
                number = ref[7:]
                if not number.isdigit() or not 1 <= int(number) <= len(row.get("sources") if isinstance(row.get("sources"), list) else []):
                    err(path, "body", f"Unknown source citation: {ref}")
            elif ref.startswith("data:"):
                if ref[5:] not in (row.get("datasetIds") if isinstance(row.get("datasetIds"), list) else []):
                    err(path, "body", f"Register the cited dataset in datasetIds: {ref[5:]}")
            elif ref.startswith("fig:"):
                figure = ref[4:]
                if figure.startswith("image-"):
                    count = len(re.findall(r"!\[[^\]]*\]\(", prose))
                    if not figure[6:].isdigit() or not 1 <= int(figure[6:]) <= count:
                        err(path, "body", f"Unknown image cross-reference: {figure}")
                elif figure not in (row.get("visualIds") if isinstance(row.get("visualIds"), list) else []) or visuals.get(figure, {}).get("template") == "service-links":
                    err(path, "body", f"Unknown numbered figure/table: {figure}")
            elif ref not in literature or not valid_url(literature[ref].get("url") or literature[ref].get("reading_url")):
                err(path, "body", f"Unknown or unavailable literature citation: {ref}")
        wiki_links, inline_visuals = document_references(str(row.get("body", "")))
        for ref in wiki_links:
            if ref not in materials:
                err(path, "body", f"Unknown wiki document: {ref}")
            elif row.get("visibility") != "draft" and materials[ref].get("visibility") == "draft":
                err(path, "body", f"Published wiki links cannot point to a draft: {ref}")
        for ref in inline_visuals:
            if ref not in (row.get("visualIds") if isinstance(row.get("visualIds"), list) else []):
                err(path, "body", f"Register inline visual in visualIds: {ref}")
        if len(inline_visuals) != len(set(inline_visuals)):
            err(path, "body", "Embed each visual only once; link to it for repeated mentions")
        if row.get("supersedes") and (not isinstance(row["supersedes"], str) or row["supersedes"] not in materials or row["supersedes"] == key):
            err(base / "materials" / f"{key}.json", "supersedes", "Reference an existing different material")
    if material_id is not None and material_id not in materials:
        err(base / "materials" / f"{material_id}.json", "id", "Material not found")
    return errors


def base_path():
    value = os.environ.get("PUBLIC_BASE_PATH", "/").strip("/")
    return "/" + value + "/" if value else "/"


def route(material=None, visual=None):
    return base_path() + (f"visuals/{safe_id(visual)}/" if visual else f"materials/{safe_id(material)}/" if material else "")


def sync_state(root=ROOT, source_commit=None):
    """Compile explicit research state into portal content, without interpreting scientific tables."""
    root = Path(root)
    state_path = root / "research_context/current_state.json"
    if not state_path.is_file():
        raise ValueError("Research state not found: research_context/current_state.json")
    state = load(state_path)
    research_path = content(root) / "research.json"
    studies = load(research_path)
    explicit_commit = source_commit
    source_commit = source_commit or subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "research_context/current_state.json"], cwd=root, text=True).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", source_commit):
        raise ValueError("State ingestion requires an existing full source commit; pass --source-commit for isolated tests")
    date = state.get("updated_moscow")
    try:
        datetime.fromisoformat(str(date).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("State updated_moscow must be an ISO timestamp") from exc
    limits = state.get("known_limits", [])
    if not isinstance(limits, list) or any(not isinstance(limit, str) for limit in limits):
        raise ValueError("State known_limits must be an array of source-written explanations")
    created = []
    updated = []
    archived = []
    refs = {"population": "population_base", "sgrt": "sgrt"}
    for study in studies:
        part = state.get("parts", {}).get(refs.get(study["id"], ""))
        if not isinstance(part, dict) or not part.get("summary"):
            continue
        next_step = part.get("nextStep") or part.get("next_step") or part.get("main_blocker")
        if not next_step:
            next_step = study.get("nextStep", "")
        raw_status = str(part.get("status", ""))
        status = ("Готовая база" if study["id"] == "population" else "Готовый результат") if raw_status == "ready" else "Проверка и исправления" if "audit" in raw_status else "Исследовательский результат"
        meaningful = {"summary": part["summary"], "nextStep": next_step, "sourceStatus": raw_status, "limitations": limits}
        documents = []
        for field in ("results", "doc"):
            path = part.get(field)
            if path is None:
                continue
            if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
                raise ValueError(f"Unsafe state document for {study['id']}")
            file = root / path
            if not file.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"State document escapes repository: {path}")
            if file.is_file() and file.resolve() != state_path.resolve() and path not in [item["path"] for item in documents]:
                documents.append({"path": path, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
        # Document content can change while the short state.summary remains unchanged.
        # Do not hash current_state.json itself: its update timestamp is not scientific news.
        if documents:
            meaningful["documentSha256"] = hashlib.sha256(json.dumps(documents, sort_keys=True).encode()).hexdigest()
        identity = hashlib.sha256(json.dumps(meaningful, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        key = f"state-{study['id']}-{identity}"
        part_commit = source_commit
        part_date = date
        if not explicit_commit and documents:
            # Git history chooses the newest relevant change, not the latest site rebuild.
            log = subprocess.check_output(["git", "log", "-1", "--format=%H%n%cI", "--", "research_context/current_state.json", *[item["path"] for item in documents]], cwd=root, text=True).strip().splitlines()
            if len(log) == 2:
                part_commit, commit_date = log
                if datetime.fromisoformat(commit_date) > datetime.fromisoformat(str(date).replace("Z", "+00:00")):
                    part_date = commit_date
        source_base = f"https://github.com/ZakBu/russian-settlements-research/blob/{part_commit}/"
        sources = [{"title": "Закреплённое состояние исследования", "url": source_base + "research_context/current_state.json"}]
        sources.extend({"title": "Описание результата и ограничений", "url": source_base + item["path"]} for item in documents)
        body = part["summary"] + "\n\n## Следующий шаг\n\n" + str(next_step)
        if limits:
            body += "\n\n## Ограничения из состояния исследования\n\n" + "\n".join("- " + value for value in limits)
        body += "\n\nАвтоматическая публикация передаёт явно записанное состояние исследования и фиксирует изменения его описания. Обновление описания может уточнять данные или ограничения и само по себе не означает нового открытия. Это не новый расчёт или дополнительная научная проверка."
        record = {"id": key, "researchId": study["id"], "title": "Состояние и описание исследования: " + study["title"], "summary": part["summary"], "kind": "note", "topic": "Ход исследования", "territory": "Область исследования по указанным источникам", "period": "Состояние на " + str(part_date)[:10], "publishedAt": part_date, "updatedAt": part_date, "visibility": "published", "evidence": "calculation" if study["id"] == "population" else "model", "currency": "current", "sourceCommit": part_commit, "sources": sources, "datasetIds": [], "visualIds": [], "body": body}
        target = content(root) / "materials" / f"{key}.json"
        prior = []
        for path in sorted((content(root) / "materials").glob(f"state-{study['id']}-*.json")):
            old = load(path)
            if path != target and old.get("id") == path.stem and old.get("researchId") == study["id"] and old.get("kind") == "note" and old.get("topic") == "Ход исследования":
                prior.append((path, old))
        if not target.exists():
            if prior:
                def previous_order(item):
                    value = datetime.fromisoformat(item[1].get("updatedAt", item[1]["publishedAt"]).replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                    return value.timestamp(), item[1]["id"]
                previous = max(prior, key=previous_order)[1]
                record["supersedes"] = previous["id"]
            save_new(target, record)
            created.append(key)
        # One current generated snapshot per research. Older scientific articles and
        # original snapshot dates/sources/body remain intact and addressable directly.
        for path, old in prior:
            if old.get("visibility") != "archived" or old.get("currency") != "superseded":
                old.update(visibility="archived", currency="superseded")
                path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                archived.append(old["id"])
        current = load(target)
        if current.get("visibility") != "published" or current.get("currency") != "current":
            current.update(visibility="published", currency="current")
            target.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Curated scientific articles are untouched; only their hub summary follows explicit state.
        changes = {"summary": part["summary"], "nextStep": str(next_step), "status": status}
        if any(study.get(field) != value for field, value in changes.items()):
            study.update(changes)
            updated.append(study["id"])
    if updated:
        research_path.write_text(json.dumps(studies, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"created": created, "archived": archived, "updatedResearch": updated, "sourceCommit": source_commit}


def browser_export(args):
    try:
        from playwright.sync_api import Error as BrowserError, sync_playwright
    except ImportError as exc:
        raise ValueError("Install export support: python -m pip install playwright && python -m playwright install chromium") from exc
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    server = None
    origin = args.url.rstrip("/") if args.url else f"http://127.0.0.1:{args.port}"
    if not args.url:
        server = subprocess.Popen(["npm", "exec", "--", "astro", "dev", "--host", "127.0.0.1", "--port", str(args.port)], cwd=Path(args.root) / "web", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    url = origin + route(args.material, args.visual)
    try:
        for _ in range(120):
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                if server and server.poll() is not None:
                    raise ValueError("Preview server stopped. Run npm --prefix web install and inspect npm --prefix web run dev")
                time.sleep(.5)
        else:
            raise ValueError(f"Preview URL unavailable: {url}")
        with sync_playwright() as pw:
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            if not executable and not Path(pw.chromium.executable_path).exists():
                executable = shutil.which("chromium") or shutil.which("google-chrome")
            try:
                browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
            except BrowserError as exc:
                raise ValueError("Cannot launch Chromium. Run python -m playwright install chromium, or set PLAYWRIGHT_CHROMIUM_EXECUTABLE to an installed browser. " + str(exc).splitlines()[0]) from exc
            page = browser.new_page(viewport={"width": 1440, "height": 1024}, device_scale_factor=2)
            page.goto(url, wait_until="networkidle")
            page.evaluate("document.documentElement.dataset.theme = '" + args.theme + "'")
            page.evaluate("window.dispatchEvent(new Event('atlas-theme'))")
            page.evaluate("document.fonts.ready")
            if args.visual:
                page.locator(f'[data-visual-id="{args.visual}"]').wait_for()
                spec = load(content(args.root) / "visuals" / f"{args.visual}.json")
                if spec["template"] not in {"table", "settlement-map", "service-links"}:
                    page.locator(f'[data-visual-id="{args.visual}"] .chart svg').wait_for()
            page.wait_for_timeout(500)
            if args.format == "pdf":
                page.emulate_media(media="screen")
                page.pdf(path=str(output), print_background=True, width="1440px", height="1024px")
            else:
                if args.visual:
                    page.locator(f'[data-visual-id="{args.visual}"]').screenshot(path=str(output), animations="disabled")
                else:
                    page.add_style_tag(content="astro-dev-toolbar { display: none !important; }")
                    page.screenshot(path=str(output), full_page=True, animations="disabled")
            browser.close()
    finally:
        if server:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
    print(str(output))


def submit(args):
    root = Path(args.root)
    def git(*parts):
        return subprocess.check_output(["git", *parts], cwd=root, text=True).strip()
    if git("diff", "--cached", "--name-only"):
        raise ValueError("Unstage existing changes first; submit only commits selected content")
    branch = git("branch", "--show-current")
    if branch in {"main", "master", ""}:
        if not args.branch:
            raise ValueError("Use a topic branch or pass --branch content/research-result; never submit directly from main")
        git("switch", "-c", args.branch)
    elif args.branch and branch != args.branch:
        raise ValueError("Already on another topic branch; switch explicitly before submitting")
    changed = git("diff", "--name-only", "--", "web/content").splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard", "--", "web/content").splitlines()
    paths = sorted(set(changed + untracked))
    branch = git("branch", "--show-current")
    if not paths:
        # A previous attempt may have committed and pushed successfully before
        # PR creation failed. Resume it without another commit or duplicate PR.
        pending = git("diff", "--name-only", "origin/main...HEAD", "--", "web/content")
        if not pending:
            raise ValueError("No content changes to submit")
    else:
        git("add", "--", *paths)
        git("commit", "-m", args.title)
    git("push", "-u", "origin", "HEAD")
    existing = subprocess.check_output(["gh", "pr", "list", "--head", branch, "--base", "main", "--state", "open", "--json", "url", "--jq", ".[0].url"], cwd=root, text=True).strip()
    if existing:
        print(existing)
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8") as body:
        body.write(args.body or "Добавлены материалы исследования и декларативные визуализации. Контент проверен site_content.py validate.")
        body.flush()
        subprocess.run(["gh", "pr", "create", "--title", args.title, "--body-file", body.name, "--base", "main", "--head", branch], cwd=root, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root (also useful for isolated authoring tests)")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Create an idempotent draft; complete scientific context before publication")
    new.add_argument("--id", required=True)
    new.add_argument("--research", required=True)
    new.add_argument("--kind", choices=sorted(KINDS), default="finding")
    new.add_argument("--title", required=True)
    for name in ("summary", "topic", "territory", "period", "source-commit", "source-url"):
        new.add_argument("--" + name, default="")
    new.add_argument("--evidence", choices=sorted(EVIDENCE), default="calculation")
    new.add_argument("--dataset", action="append", default=[])
    new.add_argument("--visual", action="append", default=[])
    visual = commands.add_parser("visual", help="Register a visual from actual values, preserving null observations")
    for name in ("id", "template", "dataset-ref", "title", "unit", "caption"):
        visual.add_argument("--" + name, required=True, choices=sorted(TEMPLATES) if name == "template" else None)
    visual.add_argument("--palette", choices=sorted(PALETTES), default="blue")
    visual.add_argument("--values-file", type=Path, help="JSON object containing categories/series, data or mapState")
    layer = commands.add_parser("layer", help="Add a data-driven map layer without modifying UI code")
    for name in ("id", "research", "dataset-ref", "title", "unit", "period"):
        layer.add_argument("--" + name, required=True)
    layer.add_argument("--adapter", choices=["geojson", "csv-points", "csv-settlement"], required=True)
    layer.add_argument("--geometry", choices=["point", "line", "polygon"], required=True)
    layer.add_argument("--evidence", choices=sorted(EVIDENCE), required=True)
    layer.add_argument("--fields-file", type=Path, required=True)
    layer.add_argument("--description", default="")
    layer.add_argument("--palette", choices=sorted(PALETTES), default="blue")
    layer.add_argument("--publish", action="store_true", help="Explicitly publish after the scientific inputs are complete; default is draft")
    check = commands.add_parser("validate", help="Validate all registries, evidence refs and declarative visual specs")
    check.add_argument("--material")
    check.add_argument("--json", action="store_true")
    sync = commands.add_parser("sync-state", help="Deterministically ingest current_state into hubs and source-pinned progress notes")
    sync.add_argument("--json", action="store_true")
    sync.add_argument("--source-commit", help="Full state source commit; normally discovered from Git history")
    preview = commands.add_parser("preview", help="Serve the real Astro preview, including unpublished drafts locally")
    preview.add_argument("--material")
    preview.add_argument("--port", type=int, default=4321)
    preview.add_argument("--url-only", action="store_true")
    export = commands.add_parser("export", help="Render the actual site visual/material with Chromium to PNG, PDF or DOCX")
    group = export.add_mutually_exclusive_group(required=True)
    group.add_argument("--material")
    group.add_argument("--visual")
    group.add_argument("--materials", help="Comma-separated ordered materials for one Word volume")
    group.add_argument("--research", help="Export the published materials of one research to Word")
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=["png", "pdf", "docx"], default="png")
    export.add_argument("--reference-doc", help="Optional university DOCX style template")
    export.add_argument("--theme", choices=["light", "dark"], default="light")
    export.add_argument("--url", help="Existing preview origin; default starts the local preview automatically")
    export.add_argument("--port", type=int, default=4321)
    publish = commands.add_parser("submit", help="Validate, commit content only on a topic branch, push and open a PR")
    publish.add_argument("--branch")
    publish.add_argument("--title", required=True)
    publish.add_argument("--body")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "new":
            key = safe_id(args.id)
            day = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
            value = {"id": key, "researchId": safe_id(args.research), "title": args.title, "summary": args.summary, "kind": args.kind, "topic": args.topic, "territory": args.territory, "period": args.period, "publishedAt": day, "updatedAt": day, "visibility": "draft", "evidence": args.evidence, "currency": "current", "sourceCommit": args.source_commit, "sources": [{"title": "Источник результата", "url": args.source_url}] if args.source_url else [], "datasetIds": args.dataset, "visualIds": args.visual, "body": ""}
            path = content(root) / "materials" / f"{key}.json"
            if path.exists():
                existing = load(path)
                # Preserve the first creation date on otherwise identical retries.
                value["publishedAt"] = existing.get("publishedAt", day)
                value["updatedAt"] = existing.get("updatedAt", day)
            changed = save_new(path, value)
            print(json.dumps({"path": str(path), "created": changed, "visibility": "draft", "next": "Add evidence, period, territory, body and visual IDs; validate before setting published."}, ensure_ascii=False))
        elif args.command == "visual":
            value = {"id": safe_id(args.id), "template": args.template, "title": args.title, "caption": args.caption, "datasetId": safe_id(args.dataset_ref), "palette": args.palette, "unit": args.unit}
            if args.values_file:
                payload = load(args.values_file)
                if not isinstance(payload, dict) or set(payload) - {"categories", "series", "data", "mapState", "limitations"}:
                    raise ValueError("Values file accepts categories, series, data, mapState, limitations only")
                value.update(payload)
            elif args.template not in {"settlement-map", "service-links"}:
                raise ValueError("Supply actual data with --values-file; synthetic placeholders are not generated")
            path = content(root) / "visuals" / f"{value['id']}.json"
            changed = save_new(path, value)
            print(json.dumps({"path": str(path), "created": changed}))
        elif args.command == "layer":
            value = {"id": safe_id(args.id), "researchId": safe_id(args.research), "title": args.title, "description": args.description, "datasetId": safe_id(args.dataset_ref), "adapter": args.adapter, "geometry": args.geometry, "fields": load(args.fields_file), "palette": args.palette, "unit": args.unit, "period": args.period, "evidence": args.evidence, "visibility": "published" if args.publish else "draft"}
            datasets = {row["id"]: row for row in load(content(root) / "datasets.json")}
            research = {row["id"]: row for row in load(content(root) / "research.json")}
            problems = layer_errors(value, datasets, research)
            if problems:
                raise ValueError("\n".join(field + ": " + message for field, message in problems))
            path = content(root) / "layers" / f"{value['id']}.json"
            changed = save_new(path, value)
            print(json.dumps({"path": str(path), "created": changed, "visibility": value["visibility"]}, ensure_ascii=False))
        elif args.command == "validate":
            errors = validate(root, args.material)
            if args.json:
                print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
            else:
                print("Content valid" if not errors else "\n".join(f"{e['file']}:{e['field']}: {e['message']}" for e in errors))
            return int(bool(errors))
        elif args.command == "sync-state":
            result = sync_state(root, args.source_commit)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Created {len(result['created'])} state notes; updated {len(result['updatedResearch'])} research hubs")
        elif args.command == "preview":
            url = f"http://127.0.0.1:{args.port}" + route(args.material)
            print(url, flush=True)
            if not args.url_only:
                return subprocess.call(["npm", "exec", "--", "astro", "dev", "--host", "127.0.0.1", "--port", str(args.port)], cwd=root / "web")
        elif args.command == "export":
            if args.format == "docx":
                if args.visual:
                    raise ValueError("For Word, select --material, --materials or --research")
                if args.research:
                    if args.research not in {r["id"] for r in load(content(root) / "research.json")}:
                        raise ValueError("Unknown research")
                else:
                    for key in (args.materials.split(",") if args.materials else [args.material]):
                        if not (content(root) / "materials" / f"{safe_id(key)}.json").is_file():
                            raise ValueError(f"Material not found: {key}")
                errors = validate(root)
                if errors:
                    raise ValueError("Content validation failed; run validate --json before export")
                command = ["node", str(root / "web/scripts/build-word-exports.mjs"), "--output", args.output]
                for key in ("material", "materials", "research", "reference_doc"):
                    if getattr(args, key, None):
                        command += ["--" + key.replace("_", "-"), getattr(args, key)]
                subprocess.run(command, cwd=root, check=True)
            else:
                if args.materials or args.research:
                    raise ValueError("Collections use --format docx")
                target = content(root) / ("visuals" if args.visual else "materials") / f"{safe_id(args.visual or args.material)}.json"
                if not target.is_file():
                    raise ValueError(f"Record not found: {target}")
                browser_export(args)
        elif args.command == "submit":
            errors = validate(root)
            if errors:
                raise ValueError("Content validation failed; run validate --json before submit")
            submit(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

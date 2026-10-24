#!/usr/bin/env python3
"""Download the Rosstat 2025 settlement workbook archive and write per-region CSV tables.

Files over 1 MB are not produced: each region is its own CSV. Workbooks that the
archive tool cannot extract are listed in russia/extract_failures.csv.
"""
from __future__ import annotations

import csv
import re
import subprocess
import urllib.request
from collections import defaultdict
from pathlib import Path

import openpyxl

RAR_URL = "https://rosstat.gov.ru/storage/mediabank/stat.info_NP_2025.rar"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sgrt" / "sources" / "russia"
WORK = Path("/tmp/rosstat_np_2025")


def safe(name: str) -> str:
    name = name.replace("/", "-").replace("\\", "-").strip()
    return re.sub(r"\s+", " ", name)


def download() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    dest = WORK / "stat.info_NP_2025.rar"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    request = urllib.request.Request(RAR_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=180) as response, dest.open("wb") as handle:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
    print("downloaded", dest.stat().st_size, flush=True)
    return dest


def members(rar: Path) -> list[str]:
    listing = subprocess.check_output(["7z", "l", "-ba", str(rar)], text=True, errors="replace")
    paths = []
    for line in listing.splitlines():
        marker = "stat.info_NP_2025/"
        if marker not in line:
            continue
        paths.append(line[line.find(marker):].strip())
    return paths


def wanted(paths: list[str]) -> list[tuple[str, str]]:
    selected = []
    for path in paths:
        name = path.split("/")[-1]
        if "2-10_Труд" in path and re.match(r"п\.?\s*9_", name) and name.endswith("_НП.xlsx"):
            selected.append(("headcount", path))
        elif "Образован" in path and name in ("п. 39_Число мест_НП.xlsx", "п. 44_Число ставок_НП.xlsx"):
            selected.append(("preschool", path))
        elif "Образован" in path and name.endswith("_НП.xlsx") and name.startswith("п. 40_") and "восп" in name.lower():
            selected.append(("preschool_children", path))
    return selected


def extract(rar: Path, path: str, dest_root: Path) -> Path | None:
    dest = dest_root / path
    if dest.exists() and dest.stat().st_size > 500:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["unar", "-q", "-o", str(dest_root), "-f", str(rar), path], capture_output=True)
    if dest.exists() and dest.stat().st_size > 500:
        return dest
    return None


def rows_of(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = list(wb.active.iter_rows(values_only=True))
    wb.close()
    parsed = []
    for row in sheet:
        if not row or row[0] in (None, ""):
            continue
        settlement = str(row[0]).strip()
        if settlement in {"Наименование", "А", "Б"} or settlement.startswith(("(", "Средн", "Числ", "Число", "Данные")):
            continue
        cells = [cell for cell in row[1:] if cell not in (None, "")]
        if not cells:
            continue
        oktmo = str(cells[0]).strip() if len(cells) >= 2 else ""
        value = cells[-1]
        if value in {"...", "…"} or (isinstance(value, str) and set(value.strip()) <= {".", "…"}):
            parsed.append({"settlement": settlement, "oktmo": oktmo, "value": "", "value_status": "suppressed"})
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            text = str(int(value)) if float(value).is_integer() else str(value)
            parsed.append({"settlement": settlement, "oktmo": oktmo, "value": text, "value_status": "observed"})
    return parsed


def write_region(folder: Path, region: str, rows: list[dict], extra_fields: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe(region)}.csv"
    fields = ["region", "settlement", "oktmo", "value", "value_status", *extra_fields]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row["region"] = region
            writer.writerow(row)
    if path.stat().st_size > 1_048_576:
        raise SystemExit(f"{path} exceeds 1 MB")


def main() -> None:
    rar = download()
    paths = members(rar)
    failures = []
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for kind, path in wanted(paths):
        extracted = extract(rar, path, WORK)
        region = path.split("/")[2] if path.count("/") >= 2 else ""
        if extracted is None:
            failures.append({"kind": kind, "region": region, "path": path})
            continue
        try:
            parsed = rows_of(extracted)
        except Exception as exc:
            failures.append({"kind": kind, "region": region, "path": path, "error": str(exc)})
            continue
        indicator = ""
        if kind == "preschool":
            indicator = "preschool_places" if "39_" in extracted.name else "preschool_posts"
            for row in parsed:
                row["indicator"] = indicator
        grouped[kind][region].extend(parsed)

    for kind, regions in grouped.items():
        extra = ["indicator"] if kind == "preschool" else []
        for region, rows in regions.items():
            write_region(OUT / kind, region, rows, extra)

    fail_path = OUT / "extract_failures.csv"
    fail_path.parent.mkdir(parents=True, exist_ok=True)
    with fail_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kind", "region", "path", "error"])
        writer.writeheader()
        for row in failures:
            row.setdefault("error", "archive member could not be extracted")
            writer.writerow(row)
    print(f"regions written, failures {len(failures)}")


if __name__ == "__main__":
    main()

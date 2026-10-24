#!/usr/bin/env python3
"""Скачать файлы реестров медорганизаций по описи и положить текст таблиц в репозиторий.

В git попадают только текстовые таблицы. xlsx, xls, zip, rar и pdf остаются во временной
папке раннера. Строка описи без адреса файла не скачивается: отсутствие файла не заменяется
чужим регионом.
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import ssl
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("sgrt/sources/medicine")
INVENTORY = ROOT / "registry_inventory.csv"
OUT = ROOT / "tables"
LOG = ROOT / "download_log.csv"
PART_LIMIT = 900_000
FILE_LIMIT = 1_048_576
TMP = Path("/tmp/medicine_fetch")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    curl = subprocess.run(
        [
            "curl", "-fL", "--retry", "3", "--retry-delay", "2",
            "--max-time", "180", "-A", "sgrt-source-fetch",
            "-o", str(dest), url,
        ],
        capture_output=True,
    )
    if curl.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
        return
    request = Request(url, headers={"User-Agent": "sgrt-source-fetch"})
    context = ssl._create_unverified_context()
    with urlopen(request, context=context, timeout=180) as response:
        dest.write_bytes(response.read())
    if dest.stat().st_size == 0:
        raise RuntimeError("пустой ответ")


def looks_like_html(path: Path) -> bool:
    head = path.read_bytes()[:500].lstrip().lower()
    return head.startswith(b"<html") or head.startswith(b"<!doctype") or head.startswith(b"<head")


def cell(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return text.strip()


def xlsx_lines(path: Path):
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in book.worksheets:
            for row in sheet.iter_rows(values_only=True):
                values = [cell(item) for item in row]
                if any(values):
                    yield sheet.title + "\t" + "\t".join(values)
    finally:
        book.close()


def xls_lines(path: Path):
    import xlrd

    book = xlrd.open_workbook(str(path))
    for sheet in book.sheets():
        for index in range(sheet.nrows):
            values = [cell(item.value) for item in sheet.row(index)]
            if any(values):
                yield sheet.name + "\t" + "\t".join(values)


def pdf_lines(path: Path):
    text_path = path.with_suffix(".txt")
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), str(text_path)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[:500])
    for line in text_path.read_text(encoding="utf-8", errors="replace").splitlines():
        cleaned = line.replace("\t", " ").rstrip()
        if cleaned:
            yield cleaned


def file_kind(path: Path) -> str:
    head = path.read_bytes()[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if head.startswith(b"Rar!"):
        return "rar"
    if head.startswith(b"PK") and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        if any(name.startswith("xl/") for name in names):
            return "xlsx"
        return "zip"
    return "unknown"


def extract_archives(path: Path, folder: Path) -> list[Path]:
    kind = file_kind(path)
    if kind in {"xlsx", "xls", "pdf"}:
        renamed = path.with_suffix("." + kind)
        if renamed != path:
            path.rename(renamed)
        return [renamed]
    folder.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(path) as archive:
            archive.extractall(folder)
    elif kind == "rar":
        result = subprocess.run(
            ["unar", "-quiet", "-output-directory", str(folder), str(path)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace")[:500])
    else:
        raise RuntimeError(f"это не таблица и не архив ({kind})")
    found = [
        item for item in folder.rglob("*")
        if item.is_file() and file_kind(item) in {"xlsx", "xls", "pdf"}
    ]
    return found


def write_parts(stem: str, lines: list[str]) -> list[str]:
    names: list[str] = []
    buf: list[str] = []
    size = 0
    part = 1

    def flush() -> None:
        nonlocal buf, size, part
        if not buf:
            return
        text = "\n".join(buf) + "\n"
        encoded = text.encode("utf-8")
        if len(encoded) > FILE_LIMIT:
            raise RuntimeError(f"{stem} часть {part} больше 1 МБ")
        destination = OUT / f"{stem}_part{part:02d}.tsv"
        destination.write_bytes(encoded)
        names.append(destination.name)
        part += 1
        buf = []
        size = 0

    for line in lines:
        encoded = (line + "\n").encode("utf-8")
        if len(encoded) > PART_LIMIT:
            raise RuntimeError(f"строка в {stem} длиннее допустимой части")
        if buf and size + len(encoded) > PART_LIMIT:
            flush()
        buf.append(line)
        size += len(encoded)
    flush()
    return names


def safe_stem(filename: str, region: str, index: int) -> str:
    base = Path(filename.replace("\\", "/")).name
    base = base.rsplit(".", 1)[0]
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in base)
    cleaned = cleaned.strip("._") or f"row_{index:03d}"
    return cleaned[:80]


def convertible(path: Path):
    kind = file_kind(path)
    if kind == "xlsx":
        return xlsx_lines(path)
    if kind == "xls":
        return xls_lines(path)
    if kind == "pdf":
        return pdf_lines(path)
    raise RuntimeError(f"нет разбора для {kind}")


def main() -> int:
    if not INVENTORY.exists():
        print("нет описи", INVENTORY, file=sys.stderr)
        return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    TMP.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(INVENTORY.open(encoding="utf-8")))
    log_rows = []
    for index, row in enumerate(rows, start=1):
        region = row.get("region", "")
        url = (row.get("url") or "").strip()
        filename = (row.get("filename") or "").strip()
        status = (row.get("http_status") or "").strip()
        entry = {
            "region": region,
            "url": url,
            "http_status_in_inventory": status,
            "result": "",
            "bytes": "",
            "sha256": "",
            "data_rows": "",
            "files": "",
            "note": "",
        }
        if not url or not filename or status != "200":
            entry["result"] = "skipped"
            entry["note"] = "в описи нет готового файла по прямому адресу"
            log_rows.append(entry)
            continue
        stem = safe_stem(filename, region, index)
        target = TMP / f"{index:03d}_{Path(filename.replace('\\', '/')).name}"
        try:
            download(url, target)
            entry["bytes"] = str(target.stat().st_size)
            entry["sha256"] = sha256(target)
            if looks_like_html(target):
                entry["result"] = "html"
                entry["note"] = "адрес открыл страницу, а не файл реестра"
                log_rows.append(entry)
                continue
            extracted = extract_archives(target, TMP / f"{index:03d}_unpack")
            if not extracted:
                entry["result"] = "no_table"
                entry["note"] = "в архиве нет xlsx, xls или pdf"
                log_rows.append(entry)
                continue
            lines: list[str] = []
            for item in extracted:
                lines.extend(convertible(item))
            written = write_parts(stem, lines)
            entry["result"] = "saved"
            entry["data_rows"] = str(len(lines))
            entry["files"] = " ".join(written)
        except Exception as error:  # noqa: BLE001 — журнал должен сохранить сбой одной строки
            entry["result"] = "error"
            entry["note"] = str(error).replace("\n", " ")[:500]
        log_rows.append(entry)
        print(entry["result"], region, entry["files"] or entry["note"], flush=True)
    with LOG.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(log_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(log_rows)
    saved = sum(1 for item in log_rows if item["result"] == "saved")
    print(f"saved {saved} of {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

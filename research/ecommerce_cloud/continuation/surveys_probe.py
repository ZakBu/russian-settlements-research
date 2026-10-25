#!/usr/bin/env python3
"""Bounded remote-ZIP survey discovery; never output or persist microdata rows.

Reads central directories, selected documentation and the first CSV header only.
A form's geographic field is NOT evidence it survives in the public release.
Only stdlib is required; PDF text extraction is optional via installed pdftotext.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import ssl
import subprocess
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import zipfile
from datetime import datetime, timezone

BASE = "https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_surveys_135_v20260903/"
ARCHIVES = {"kouzh": "КОУЖ.zip", "kdu": "КДУ.zip", "timeuse": "ВНИСФВ.zip"}
DOC = re.compile(r"кодбук|кодировка|описан|переменн|справоч|вопросник|анкет|question|codebook|dict|readme", re.I)
GEO = re.compile(r"(?:[hiнi]00_0[2-8])|geo|region|settle|окато|октмо|террит|населен|тип.?нп", re.I)
TOPIC = re.compile(r"магазин|покуп|достав|выдач|интернет|поезд|доступност|транспорт|маршрут|населен|ОКАТО|ОКТМО|H00_0[234]|I00_0[234]", re.I)
LIMIT = 300 * 1024 * 1024

def digest(body):
    return hashlib.sha256(body).hexdigest()

def decode(body):
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        return body.decode("utf-16", errors="replace")
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("cp1251", errors="replace")

class RangeZIP(io.RawIOBase):
    def __init__(self, url, budget=LIMIT):
        self.url, self.pos, self.budget, self.used = url, 0, budget, 0
        self.context = ssl.create_default_context()
        self.requests = []
        self.head = {}
        try:
            with urlopen(Request(url, method="HEAD"), timeout=30, context=self.context) as r:
                self.head = {"status": r.status, "url": r.url,
                             "content_length": r.headers.get("Content-Length"),
                             "accept_ranges": r.headers.get("Accept-Ranges")}
        except Exception as e:
            self.head = {"error_type": type(e).__name__}
        _, total = self._get(0, 0)
        self.size = total

    def _get(self, start, end):
        if self.used + end - start + 1 > self.budget:
            raise ValueError("300MB archive transfer cap reached")
        request = Request(self.url, headers={"Range": "bytes=%d-%d" % (start, end),
                          "User-Agent": "settlement-research-surveys-probe/1.0"})
        with urlopen(request, timeout=35, context=self.context) as r:
            cr = r.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", cr)
            if r.status != 206 or not match:
                raise ValueError("Server did not honor explicit Range; full download not attempted")
            a, b, total = map(int, match.groups())
            if a != start or b > end:
                raise ValueError("Unexpected Content-Range")
            body = r.read(b - a + 2)
            if len(body) != b - a + 1:
                raise ValueError("Incomplete range")
            self.used += len(body)
            self.requests.append({"start": a, "end": b, "total": total,
                                  "bytes": len(body), "sha256": digest(body),
                                  "http_status": r.status, "resolved_url": r.url})
            return body, total

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (offset if whence == 0 else self.pos + offset if whence == 1
                    else self.size + offset)
        if self.pos < 0:
            raise ValueError("Negative seek")
        return self.pos

    def read(self, size=-1):
        size = self.size - self.pos if size is None or size < 0 else size
        size = min(size, self.size - self.pos)
        if size <= 0:
            return b""
        if size > 32 * 1024 * 1024:
            raise ValueError("Single ZIP read exceeds32MB")
        body, total = self._get(self.pos, self.pos + size - 1)
        if total != self.size:
            raise ValueError("Remote archive size changed")
        self.pos += len(body)
        return body

def member_year(name):
    years = re.findall(r"(?:^|[/_ -])(20[0-9]{2})(?=[/_ .-]|$)", name)
    return max(map(int, years)) if years else 0

def xlsx_rows(raw):
    """Read static codebook rows, resolving shared strings and inline cells."""
    rows = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            if z.getinfo("xl/sharedStrings.xml").file_size > 16 * 1024 * 1024:
                raise ValueError("Codebook shared strings exceed16MB")
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.findall(".//x:t", ns))
                      for si in root.findall("x:si", ns)]
        names = sorted(n for n in z.namelist()
                       if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        for name in names[:12]:
            if z.getinfo(name).file_size > 16 * 1024 * 1024:
                continue
            root = ET.fromstring(z.read(name))
            for row in root.findall(".//x:sheetData/x:row", ns):
                cells = []
                for cell in row.findall("x:c", ns):
                    value = cell.findtext("x:v", default="", namespaces=ns)
                    kind = cell.get("t")
                    if kind == "s":
                        try:
                            value = shared[int(value)]
                        except (IndexError, ValueError):
                            value = ""
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall(".//x:t", ns))
                    cells.append({"column": cell.get("r", ""), "text": str(value)})
                rows.append({"sheet": name, "row": row.get("r"), "cells": cells})
                if len(rows) >= 20000:
                    return rows
    return rows

def codebook_evidence(raw):
    pattern = re.compile(r"^(?:[HIН][0-9]{2}_[A-Za-z0-9_]+|REGION|REG|ID|ID_H|ID_I|PSU|STRATA|SETTLEMENT|OKATO|OKTMO)$", re.I)
    evidence = []
    previous = None
    for row in xlsx_rows(raw):
        values = [re.sub(r"\s+", " ", c["text"]).strip() for c in row["cells"]]
        variables = [v for v in values if pattern.fullmatch(v)]
        if variables:
            previous = variables[0]
        text = " | ".join(v for v in values if v)
        geo = any(GEO.search(v) for v in values) or bool(previous and GEO.search(previous))
        if geo or TOPIC.search(text):
            evidence.append({"sheet": row["sheet"], "row": row["row"],
                             "variable_on_row": variables[:3],
                             "previous_variable_context": previous,
                             "cells": [{"column": c["column"], "text": c["text"][:350]}
                                       for c in row["cells"][:8]],
                             "geography_match": bool(geo)})
    evidence.sort(key=lambda r: (not r["geography_match"], int(r["row"] or 0)))
    return evidence[:65]

def documentation_text(name, raw):
    suffix = Path(name).suffix.lower()
    if suffix in (".txt", ".csv", ".json", ".md", ".html", ".htm", ".xml"):
        return decode(raw), "decoded_static_documentation"
    if suffix == ".xlsx":
        rows = xlsx_rows(raw)
        return "\n".join(" | ".join(c["text"] for c in row["cells"]) for row in rows), "static_codebook_xlsx_rows"
    if suffix == ".docx":
        strings = []
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            candidates = (["word/document.xml"] if suffix == ".docx" else
                          [n for n in z.namelist() if n == "xl/sharedStrings.xml" or n.startswith("xl/worksheets/")])
            for n in candidates[:12]:
                info = z.getinfo(n)
                if info.file_size > 16 * 1024 * 1024:
                    continue
                root = ET.fromstring(z.read(n))
                strings.extend(t.text or "" for t in root.iter()
                               if t.tag.rsplit("}", 1)[-1] == "t")
        return "\n".join(strings), "static_office_xml"
    if suffix == ".pdf" and shutil.which("pdftotext"):
        p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=raw,
                           capture_output=True, timeout=25, check=True)
        return decode(p.stdout), "optional_pdftotext"
    return "", "text_extraction_unavailable"

def selected_lines(text):
    # Called ONLY on explicitly named documentation, never on a microdata body.
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if TOPIC.search(line) and 3 < len(line) < 1400:
            if line not in lines:
                lines.append(line[:220])
        if len(lines) >= 12:
            break
    return lines

def inspect(label, url, output, max_docs=10):
    result = {"archive": label, "url": url, "started_utc": datetime.now(timezone.utc).isoformat(),
              "tls_verified": True, "microdata_rows_output": False,
              "archive_sha256": None, "archive_fully_downloaded": False,
              "geokey_identity_validated": False,
              "settlement_representativeness_established": False}
    remote = None
    try:
        remote = RangeZIP(url)
        result["archive_bytes"] = remote.size
        result["head"] = remote.head
        with zipfile.ZipFile(remote) as z:
            members = z.infolist()
            inventory = [{"name": i.filename, "uncompressed_bytes": i.file_size,
                          "compressed_bytes": i.compress_size,
                          "declared_crc32": "%08x" % i.CRC} for i in members]
            member_json = json.dumps(inventory, ensure_ascii=False, sort_keys=True).encode()
            (output / (label + "_members.json")).write_bytes(member_json)
            result.update(members_n=len(members), member_inventory_sha256=digest(member_json),
                          declared_member_crc_is_not_full_payload_verification=True)
            headers, documents = [], []
            for info in sorted(members, key=lambda i: (-member_year(i.filename), i.filename)):
                name = info.filename
                if info.is_dir():
                    continue
                doc = bool(DOC.search(Path(name).name))
                if name.lower().endswith(".csv") and member_year(name) in (2023, 2024, 2025) and not doc:
                    # Read no more than a bounded prefix; retain and output HEADER ONLY.
                    with z.open(info) as f:
                        prefix = f.read(65536)
                    first_line = decode(prefix).split("\n", 1)[0].rstrip("\r")
                    if "\n" not in decode(prefix):
                        headers.append({"member": name, "status": "no_complete_header_in64KB"})
                        continue
                    delimiter = max([";", ",", "\t"], key=first_line.count)
                    fields = next(csv.reader([first_line], delimiter=delimiter))
                    header_like = (len(fields) >= 3 and
                                   sum(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", f))
                                       for f in fields) / len(fields) >= 0.8)
                    # On an unfamiliar schema report only hash/count, never potential data values.
                    header = {"member": name, "header_sha256": digest(first_line.encode()),
                              "recognized_variable_header": header_like,
                              "fields_n": len(fields), "year": member_year(name),
                              "first20_field_names": fields[:20] if header_like else [],
                              "H00_03_present": ("H00_03" in fields) if header_like else None,
                              "I00_03_present": ("I00_03" in fields) if header_like else None,
                              "other_identifier_field_names": [
                                  f for f in fields if header_like and
                                  re.search(r"^(?:ID|PSU|STRAT|SETT|DIST|REG|GEO|OKATO|OKTMO)|_ID$", f, re.I)][:40],
                              "geographic_field_names": [
                                  f[:120] for f in fields if header_like and GEO.search(f)][:50],
                              "field_presence_does_not_validate_public_geokey": True}
                    headers.append(header)
                    if len(headers) >= 30:
                        break
            docs = [i for i in members if not i.is_dir()
                    and DOC.search(Path(i.filename).name)
                    and member_year(i.filename) in (2023, 2024, 2025)
                    and i.file_size <= 8 * 1024 * 1024
                    and Path(i.filename).suffix.lower() in {
                        ".txt", ".csv", ".json", ".md", ".html", ".htm", ".xml", ".docx", ".xlsx", ".pdf"}]
            def doc_priority(i):
                name = Path(i.filename).name.lower()
                codebook = bool(re.search(r"кодбук|codebook|dict|переменн|кодиров", name))
                child = bool(re.search(r"дет|child", name))
                return (-member_year(i.filename), not codebook, child, i.filename)
            docs.sort(key=doc_priority)
            # Reserve two slots per available target year; never spend cap on2011.
            chosen = []
            for year in (2025, 2024, 2023):
                chosen.extend([i for i in docs if member_year(i.filename) == year][:2])
            chosen.extend(i for i in docs if i not in chosen)
            for info in chosen[:max_docs]:
                raw = z.read(info)
                text, method = documentation_text(info.filename, raw)
                entry = {"member": info.filename, "year": member_year(info.filename),
                         "bytes": len(raw), "sha256": digest(raw), "method": method,
                         "topic_or_geography_lines": selected_lines(text),
                         "static_documentation_not_microdata": True}
                if Path(info.filename).suffix.lower() == ".xlsx":
                    entry["codebook_variable_label_rows"] = codebook_evidence(raw)
                documents.append(entry)
            result["csv_header_probes"] = headers
            result["available_csv_years_2023_2025"] = sorted(set(
                member_year(i.filename) for i in members if i.filename.lower().endswith(".csv")
                and member_year(i.filename) in (2023, 2024, 2025)))
            result["csv2024_header_probes"] = [h for h in headers if h.get("year") == 2024]
            result["documentation_probes"] = documents
            result["status"] = "bounded_discovery_complete_not_substantive_analysis"
    except Exception as e:
        result.update(status="blocked", error_type=type(e).__name__, error=str(e)[:400])
    finally:
        if remote is not None:
            result["transferred_bytes"] = remote.used
            (output / (label + "_ranges.json")).write_text(
                json.dumps(remote.requests, ensure_ascii=False, indent=2) + "\n")
    (output / (label + "_probe.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="work/ecommerce_surveys_probe")
    parser.add_argument("--archives", nargs="+", choices=list(ARCHIVES), default=list(ARCHIVES))
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    results = [inspect(k, BASE + quote(ARCHIVES[k]), out) for k in args.archives]
    report = {"checked_utc": datetime.now(timezone.utc).isoformat(), "source_page": "https://tochno.st/datasets/surveys",
              "probes": results, "causal_effect_estimated": False,
              "limitations": ["Blank-form fields do not prove their retention or identity in public microdata.",
                             "Header presence cannot distinguish an OKATO code from an anonymized ID.",
                             "Absence of H00_03/I00_03 in inspected releases does not exclude other keys, other versions, or restricted-use data.",
                             "No microdata rows are saved, printed, or inspected for geographic identity.",
                             "Repeated cross-sections are not household panels or observed OD flows.",
                             "No population or settlement representativeness inferred by this probe."]}
    (out / "surveys_probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("SURVEYS_PROBE_JSON_BEGIN")
    # Keep rich codebook evidence in artifacts; only a bounded receipt in the log.
    console = json.loads(json.dumps(report))
    for probe in console["probes"]:
        for doc in probe.get("documentation_probes", []):
            doc["codebook_variable_label_rows"] = doc.get("codebook_variable_label_rows", [])[:12]
    print(json.dumps(console, ensure_ascii=False, separators=(",", ":")))
    print("SURVEYS_PROBE_JSON_END")

if __name__ == "__main__":
    main()

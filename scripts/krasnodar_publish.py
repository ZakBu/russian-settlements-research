#!/usr/bin/env python3
"""Acquire exact study polygons and package an immutable Krasnodar release.

Publication itself uses gh in Actions; no scientific asset is uploaded here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TAG = "krasnodar-access-maps-20261031-v1"
RELATIONS = {"Яблоновское": 5442463, "Старобжегокайское": 5442459,
             "Тахтамукайское": 5442460, "Афипсипское": 5442457, "Адыгейск": 1850083}
USER_AGENT = ("russian-settlements-research/1.0 "
              "(https://github.com/ZakBu/russian-settlements-research; academic boundary comparison)")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def nominatim(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    url = "https://nominatim.openstreetmap.org/lookup?" + urlencode({
        "osm_ids": ",".join("R" + str(v) for v in RELATIONS.values()),
        "format": "jsonv2", "polygon_geojson": 1, "accept-language": "ru"})
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=120) as response:
        raw = response.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Nominatim response exceeds 10 MiB")
    values = json.loads(raw)
    if not isinstance(values, list) or len(values) != len(RELATIONS):
        raise ValueError("Nominatim lookup did not return the five requested relations")
    (output / "nominatim-lookup.json").write_bytes(raw)
    for name, relation in RELATIONS.items():
        matches = [r for r in values if r.get("osm_type") == "relation" and r.get("osm_id") == relation]
        if len(matches) != 1:
            raise ValueError(f"Nominatim relation missing or duplicated: {relation}")
        value = matches[0]
        if (value.get("type") != "administrative" or "Адыгея" not in value.get("display_name", "")
                or value.get("geojson", {}).get("type") not in {"Polygon", "MultiPolygon"}):
            raise ValueError(f"Nominatim returned an unexpected entity for relation {relation}")
        dump(output / f"nominatim-{name}.json", matches)
    dump(output / "nominatim_metadata.json", {"url": url, "userAgent": USER_AGENT,
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "relations": RELATIONS, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        "source": "OpenStreetMap / Nominatim", "license": "ODbL-1.0",
        "geometryMeaning": "Current reference geometry, not reconstructed historical study boundary"})
    print(json.dumps({"nominatimRelations": len(values), "bytes": len(raw)}, ensure_ascii=False))


def archive(directory: Path, target: Path, predicate=None) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and (predicate is None or predicate(path)):
                member = path.relative_to(directory).as_posix()
                info = zipfile.ZipInfo(member, date_time=(2026, 10, 31, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                bundle.writestr(info, path.read_bytes())


def package(args) -> None:
    from krasnodar_site_data import MAX_BYTES, verify_payload
    verify_payload(args.app, args.source_commit)
    if sum(p.stat().st_size for p in args.app.iterdir() if p.is_file()) > MAX_BYTES:
        raise ValueError("Application payload exceeds the website loader's 25 MiB limit")
    args.output.mkdir(parents=True, exist_ok=True)
    # Fail on reused output names rather than silently publishing stale data.
    for name in ("app.zip", "results.zip", "inputs.zip", "release_catalog.json", "SHA256SUMS"):
        if (args.output / name).exists():
            raise FileExistsError(f"Publication output already exists: {name}")
    archive(args.app, args.output / "app.zip")
    archive(args.results, args.output / "results.zip")
    inputs = args.output / "input-staging"
    inputs.mkdir()
    for path in args.raw.glob("nominatim*.json"):
        shutil.copyfile(path, inputs / path.name)
    for name in ("core-shard97.json", "krasnodar-core.geojson"):
        shutil.copyfile(args.input / name, inputs / name)
    provenance = args.results / "input_provenance.json"
    if not provenance.is_file():
        raise FileNotFoundError("The reproduced calculation lacks input_provenance.json")
    shutil.copyfile(provenance, inputs / "input_provenance.json")
    pbf = args.input / "south-fed-district-261029.osm.pbf"
    input_provenance = json.loads(provenance.read_text())
    if sha(pbf) != input_provenance["road_sha256"]:
        raise ValueError("Preserved PBF differs from the reproduced calculation's provenance")
    metadata = {"sourceCommit": args.source_commit, "release": TAG,
        "roadArchiveName": pbf.name, "roadSha256": sha(pbf), "roadBytes": pbf.stat().st_size,
        "files": {p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
                  for p in sorted(inputs.iterdir()) if p.is_file()},
        "populationRelease": "sgrt-census-population-20261022-v1",
        "populationCatalog": "data/catalog.json",
        "referenceBoundaries": {"url": "https://github.com/ZakBu/russian-settlements-research/releases/download/atlas-boundaries-20261026-v1/RUS-adm2.geojson",
            "sha256": "3c8dd7b7d6977c506c0cfb2c1b3a328df6abd585a709a468648a5e3566ff1bad"}}
    dump(inputs / "input_metadata.json", metadata)
    archive(inputs, args.output / "inputs.zip")
    shutil.rmtree(inputs)
    shutil.copyfile(pbf, args.output / pbf.name)
    base = f"https://github.com/{args.repository}/releases/download/{TAG}/"
    files = {}
    for key, name in (("app", "app.zip"), ("results", "results.zip"), ("inputs", "inputs.zip"), ("road", pbf.name)):
        path = args.output / name
        files[key] = {"url": base + name, "sha256": sha(path), "bytes": path.stat().st_size}
    for key, name in (("accessMap", "access-destinations.png"), ("candidateMap", "candidate-sensitivity.png")):
        source = args.app / name
        if not source.is_file():
            raise FileNotFoundError(f"Required article map not built: {name}")
        target = args.output / name
        shutil.copyfile(source, target)
        files[key] = {"url": base + name, "sha256": sha(target), "bytes": target.stat().st_size}
    dump(args.output / "release_catalog.json", {"release": TAG, "sourceCommit": args.source_commit, "files": files})
    # Include the catalog itself in the independent checksum list.
    (args.output / "SHA256SUMS").write_text("".join(
        f"{sha(p)}  {p.name}\n" for p in sorted(args.output.iterdir()) if p.is_file()))
    (args.output / "release_notes.md").write_text(
        "Краснодар: воспроизводимый сценарий автомобильной доступности и сравнение опубликованных составов.\n\n"
        "Это модель дорожной доступности, не наблюдаемые трудовые поездки и не рассчитанный критерий 15%. "
        "Население — перепись 2021 года; дороги — снимок 29 октября 2026 года.\n\n"
        "app.zip — проверяемый пакет атласа; results.zip — расчётные таблицы и геометрии; inputs.zip — "
        "исходные ответы Nominatim, принятый контур и происхождение входов. Дорожный PBF опубликован "
        "отдельно для сохранения недолговечного дневного снимка Geofabrik. SHA256SUMS и release_catalog.json "
        "закрепляют версии и контрольные суммы. © OpenStreetMap contributors / Geofabrik, ODbL 1.0.\n\n"
        f"Исходный код: {args.source_commit}.\n")
    print(json.dumps({"release": TAG, "files": files}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    lookup = sub.add_parser("nominatim")
    lookup.add_argument("--output", type=Path, required=True)
    packing = sub.add_parser("package")
    for name in ("app", "results", "input", "raw", "output"):
        packing.add_argument("--" + name, type=Path, required=True)
    packing.add_argument("--source-commit", required=True)
    packing.add_argument("--repository", default="ZakBu/russian-settlements-research")
    args = parser.parse_args()
    nominatim(args.output) if args.command == "nominatim" else package(args)

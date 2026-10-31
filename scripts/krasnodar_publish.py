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

TAG = "krasnodar-access-maps-20261031-v2"
SOURCE_V1 = {
    "app.zip": "d086ff40a54f5eb3acfb27637b861be97e8c35257f8b3e0475948170ef15499a",
    "results.zip": "949fd368f868368d98c2198e02687824023169ea9aa754be619557cce78b798a",
    "inputs.zip": "ceac76a624b7080b093cb1b47acbe4c36307251ea4daec6f56537fdd124c32f2",
    "south-fed-district-261029.osm.pbf": "d8a4c4dd696428f2aca8dacf85801e4b790cc80419528a06979e177600c26052",
}
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


def prepare_v2(args) -> None:
    """Reuse immutable v1 scientific results; do not request or route fresh roads."""
    from krasnodar_site_data import extract_verified
    source = args.work / "source-v1"
    source.mkdir(parents=True, exist_ok=True)
    base = "https://github.com/ZakBu/russian-settlements-research/releases/download/krasnodar-access-maps-20261031-v1/"
    for name, expected in SOURCE_V1.items():
        path = source / name
        if not path.is_file():
            with urlopen(Request(base + name, headers={"User-Agent": USER_AGENT}), timeout=180) as response, path.open("wb") as target:
                shutil.copyfileobj(response, target)
        if sha(path) != expected:
            raise ValueError(f"Immutable v1 source checksum differs: {name}")
    for name, destination in (("results.zip", args.work / "results-v1"), ("inputs.zip", args.work / "input")):
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source / name) as bundle:
            if sum(m.file_size for m in bundle.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Unexpected v1 scientific archive size")
            for member in bundle.infolist():
                if Path(member.filename).name != member.filename or member.is_dir() or "\\" in member.filename:
                    raise ValueError("Non-flat scientific source archive")
            bundle.extractall(destination)
    app = args.work / "app-v1"
    app.mkdir(parents=True, exist_ok=True)
    extract_verified(source / "app.zip", app, "0cb25a1cd5f891fca4f4da806964ce9282253a6c")
    manifest = json.loads((app / "manifest.json").read_text())
    args.studies.mkdir(parents=True, exist_ok=True)
    dump(args.studies / "studies.json", manifest["studies"])
    for study in manifest["studies"]:
        shutil.copyfile(app / study["geometryUrl"], args.studies / study["geometryUrl"])
    args.raw.mkdir(parents=True, exist_ok=True)
    inputs = args.work / "input"
    for path in inputs.glob("nominatim*.json"):
        shutil.copyfile(path, args.raw / path.name)
    shutil.copyfile(source / "south-fed-district-261029.osm.pbf", inputs / "south-fed-district-261029.osm.pbf")
    shutil.copyfile(inputs / "input_metadata.json", inputs / "source_v1_input_metadata.json")
    config = json.loads((Path(__file__).resolve().parents[1] / "data/site_assets.json").read_text())
    mask_source = next(a for a in config["boundaries"] if a["id"] == "regions")
    mask = inputs / "RUS-adm1.geojson"
    with urlopen(Request(mask_source["url"], headers={"User-Agent": USER_AGENT}), timeout=180) as response, mask.open("wb") as target:
        shutil.copyfileobj(response, target)
    if sha(mask) != mask_source["sha256"]:
        raise ValueError("Clipping mask differs from pinned RUS ADM1")
    dump(inputs / "v2_source_metadata.json", {"sourceRelease": "krasnodar-access-maps-20261031-v1",
        "sourceFiles": SOURCE_V1, "mask": mask_source, "rerouting": False,
        "operation": "Clip generalized polygons to pinned RUS mask; keep road times and membership"})
    print(json.dumps({"source": "immutable-v1", "maskSha256": sha(mask), "rerouting": False}))


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
    for name in ("RUS-adm1.geojson", "source_v1_input_metadata.json", "v2_source_metadata.json"):
        if (args.input / name).is_file():
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
    if (args.input / "v2_source_metadata.json").is_file():
        metadata["postprocessing"] = json.loads((args.input / "v2_source_metadata.json").read_text())
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
        "Версия 2 обрезает обобщённые научные полигоны по закреплённому контуру России. "
        "Времена и членство НП взяты из неизменного выпуска v1 без повторного поиска путей; "
        "маска и происхождение сохранены в inputs.zip.\n\n"
        f"Исходный код: {args.source_commit}.\n")
    print(json.dumps({"release": TAG, "files": files}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    lookup = sub.add_parser("nominatim")
    lookup.add_argument("--output", type=Path, required=True)
    reuse = sub.add_parser("prepare-v2")
    for name in ("work", "raw", "studies"):
        reuse.add_argument("--" + name, type=Path, required=True)
    packing = sub.add_parser("package")
    for name in ("app", "results", "input", "raw", "output"):
        packing.add_argument("--" + name, type=Path, required=True)
    packing.add_argument("--source-commit", required=True)
    packing.add_argument("--repository", default="ZakBu/russian-settlements-research")
    args = parser.parse_args()
    if args.command == "nominatim":
        nominatim(args.output)
    elif args.command == "prepare-v2":
        prepare_v2(args)
    else:
        package(args)

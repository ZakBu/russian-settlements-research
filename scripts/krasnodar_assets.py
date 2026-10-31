"""Assemble the source-backed Krasnodar map/deck payload, without rerouting.

python scripts/krasnodar_assets.py --access /tmp/krasnodar-access/final --studies /tmp/krasnodar-studies --output /tmp/krasnodar-app
The output is generated scientific data: publish in Releases, never commit it.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def build(access, studies_dir, output, source_commit):
    output.mkdir(parents=True, exist_ok=True)
    studies = json.loads((studies_dir / "studies.json").read_text())
    access_manifest = json.loads((access / "manifest.json").read_text())
    stats = json.loads((access / "statistics.json").read_text())
    summary = json.loads((access / "summary.json").read_text())
    inventory = ["isochrone_bands.geojson", "isochrones_base.geojson", "isochrones_slow.geojson",
                 "core_isochrones_base.geojson", "core_isochrones_slow.geojson", "core.geojson",
                 "candidate_60.geojson", "candidate_60_slow.geojson", "places.geojson", "context.geojson",
                 "statistics.json", "summary.json", "settlement_access.csv", "candidate_roster.csv"]
    for name in inventory:
        shutil.copyfile(access / name, output / name)
    for name in ["input_provenance.json", "sample_routes.json", "sample_routes.geojson"]:
        if (access / name).is_file():
            shutil.copyfile(access / name, output / name)
    for study in studies:
        filename = study["geometryUrl"]
        if Path(filename).name != filename or not filename.endswith(".geojson"):
            raise ValueError("Study geometry must be a plain GeoJSON filename")
        shutil.copyfile(studies_dir / filename, output / filename)
    dump(output / "calculation_manifest.json", access_manifest)
    base = next(r for r in stats["counts"] if r["destination"] == "core_contour" and r["minutes"] == 60)
    interval = stats["core60Range"]
    assert base["settlementRecords"] == interval["maxSettlements"]
    assert base["population2021"] == interval["maxPopulation2021"]
    fmt = lambda n: f"{n:,}".replace(",", " ")
    report = "https://zakbu.github.io/russian-settlements-research/materials/krasnodar-first-calculation/"
    candidate = {
        "id": "our-core60", "title": "Наш расчёт: 60 минут до контура Краснодара", "year": 2026,
        "authors": "Авторский транспортный сценарий", "sourceUrl": report,
        "sourceDate": "2026-10-31", "geometryDate": "2026-10-29", "geometryKind": "polygon",
        "geometryUrl": "candidate_60.geojson", "robustGeometryUrl": "candidate_60_slow.geojson",
        "sourceVersion": "krasnodar-access-maps-20261031-v1", "evidence": "model",
        "summary": f"60 минут до принятого контура города: {fmt(base['settlementRecords'])} переписные записи НП, {fmt(base['population2021'])} жителей по переписи 2021 года. При времени +30% остаются {fmt(interval['minSettlements'])} записей и {fmt(interval['minPopulation2021'])} жителей.",
        "whatBoundaryMeans": "Предварительная автомобильная доступность для проверки транспортной задачи, не установленная граница функциональной агломерации.",
        "limitations": ["Трудовой критерий 15% пока не рассчитан: направления поездок неизвестны.",
                         "Население 2021 года включает Краснодар. Контур обобщён; времена отдельных НП смотрите в точках."],
        "metrics": [
            {"label": "60 минут · базовый сценарий", "value": fmt(base["settlementRecords"]), "unit": "записи НП",
             "note": f"{fmt(base['population2021'])} человек · перепись 2021, включая Краснодар"},
            {"label": "60 минут · время +30%", "value": fmt(interval["minSettlements"]), "unit": "записи НП",
             "note": f"{fmt(interval['minPopulation2021'])} человек · перепись 2021, включая Краснодар"},
        ],
    }
    iso_note = "Автомобильный сценарий без измеренных пробок. Полигон обобщён; точные модельные минуты для НП показаны в точках."
    manifest = {
        "version": "krasnodar-access-maps-20261031-v1", "sourceCommit": source_commit,
        "title": "Краснодар: границы, доступность и предварительный транспортный сценарий",
        "studies": studies, "candidate": candidate,
        "isochrones": {"url": "isochrone_bands.geojson", "thresholds": [30, 60, 90], "sourceUrl": report,
            "summary": "Расчётный въезд к центральной точке Краснодара по дорожной сети на 29 октября 2026 года.",
            "limitations": [iso_note], "geometryMode": "disjoint_bands",
            "variants": [
                {"id": "point-base", "title": "До центра · базовое время", "url": "isochrone_bands.geojson", "destination": "central_point", "speedTimeFactor": 1, "geometryMode": "disjoint_bands", "summary": "Въезд к принятой центральной точке Краснодара; базовые модельные скорости."},
                {"id": "point-slow", "title": "До центра · время +30%", "url": "isochrones_slow.geojson", "destination": "central_point", "speedTimeFactor": 1.3, "geometryMode": "cumulative", "summary": "Въезд к той же центральной точке; все расчётные времена увеличены на 30%. Это сценарий, а не наблюдённая пробка."},
                {"id": "core-base", "title": "До контура города · базовое время", "url": "core_isochrones_base.geojson", "destination": "core_contour", "speedTimeFactor": 1, "geometryMode": "cumulative", "summary": "Время до ближайшего доступного дорожного узла внутри принятого картографического контура НП Краснодар."},
                {"id": "core-slow", "title": "До контура города · время +30%", "url": "core_isochrones_slow.geojson", "destination": "core_contour", "speedTimeFactor": 1.3, "geometryMode": "cumulative", "summary": "Тот же контур НП; расчётное время увеличено на 30%. Этот сценарий даёт более узкую зону кандидатов."},
            ]},
        "context": {"url": "context.geojson", "sourceDate": "2026-10-29", "source": "OpenStreetMap / Geofabrik"},
        "places": {"url": "places.geojson", "populationYear": 2021, "unit": "переписная запись населённого пункта"},
        "core": access_manifest["core"], "table": access_manifest["table"],
        "candidateTable": {"url": "candidate_roster.csv", "unit": "переписная запись НП"},
        "provenance": {"url": "summary.json", "inputUrl": "input_provenance.json", "statisticsUrl": "statistics.json"},
        "statistics": {"items": [
            {"label": "Обследования Краснодара", "value": "3 000", "unit": "анкеты", "note": "2022 год · исходные анкеты ещё не получены"},
            {"label": "Существующая модель", "value": "419", "unit": "транспортных районов", "note": "2022 год · открытой матрицы направлений нет"},
            {"label": "Открытая перепись", "value": "6", "unit": "проверенных таблиц", "note": "Наблюдение 2021 года · не раскрывают поток НП → Краснодар"},
        ], "computed": stats, "populationYear": 2021},
        "calculation": {"direction": "inbound", "roadSnapshot": "2026-10-29", "populationYear": 2021,
            "functionalCriterionComputed": False, "fieldObservations": False, "centralPoint": summary["centre"],
            "bboxNotTruncated90": summary["bbox_not_truncated_90"], "modelLimitations": summary["limits"]},
        "attribution": "© OpenStreetMap contributors / Geofabrik, Terrae; принятая база переписей; источники исследований указаны отдельно.",
    }
    if not (access / "input_provenance.json").is_file():
        manifest["provenance"].pop("inputUrl", None)
    from krasnodar_figures import build_figures
    figures = build_figures(access, output)
    manifest["figures"] = [{"url": name, "evidence": "road_network_model", "populationYear": 2021, "roadSnapshot": "2026-10-29"} for name in figures]
    dump(output / "manifest.json", manifest)
    files = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
             for p in sorted(output.iterdir()) if p.is_file() and p.name != "asset_manifest.json"}
    dump(output / "asset_manifest.json", {"sourceCommit": source_commit, "files": files})
    print(json.dumps({"studies": len(studies), "candidate_records": base["settlementRecords"],
        "robust_records": interval["minSettlements"], "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access", type=Path, required=True)
    parser.add_argument("--studies", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", default=None)
    args = parser.parse_args()
    commit = args.source_commit or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    build(args.access, args.studies, args.output, commit)

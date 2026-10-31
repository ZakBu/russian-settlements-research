"""Compare published municipality lists; never infer a commuting boundary.

python scripts/krasnodar_boundary_comparison.py --boundaries /tmp/krasnodar-reference-adm2.geojson --output /tmp/krasnodar-comparison
The reference file is the pinned atlas-boundaries-20261026-v1/RUS-adm2.geojson.
Historical membership is shown on reference polygons dated 2026-09-28.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

SOURCE_SHA = "3c8dd7b7d6977c506c0cfb2c1b3a328df6abd585a709a468648a5e3566ff1bad"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.boundaries.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError("Reference geography differs from the pinned source")
    root = Path(__file__).resolve().parents[1]
    membership = root / "research_context/krasnodar_agglomeration/comparison/municipality_membership.csv"
    rows = list(csv.DictReader(membership.open()))
    assert len(rows) == len({r["reference_id"] for r in rows}) == 9
    assert sum(int(r["ieg_2023"]) for r in rows) == 7
    assert sum(int(r["ieg_2018"]) for r in rows) == 9
    reference = {f["properties"]["adm2_id"]: f for f in json.loads(raw)["features"]}
    features = []
    for row in rows:
        f = reference[row["reference_id"]]
        # IDs are explicit reviewed matches, never nearest-point or fuzzy-name joins.
        if f["properties"]["unit_key"] != "RUS":
            raise ValueError("Non-Russian reference polygon")
        features.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "id": row["reference_id"], "name": row["name"], "region": row["region"],
            "value": 1 if row["ieg_2023"] == "1" else 2,
            "ieg_2018": int(row["ieg_2018"]), "ieg_2023": int(row["ieg_2023"]),
            "geography_date": "2026-09-28", "source_reference": "IUE_AGGLOMERATION_TRENDS2023",
            "interpretation": "Published municipality membership on current reference geometry; not historic geometry or observed commuting",
        }})
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "krasnodar-municipality-comparison.geojson"
    target.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")))
    (args.output / membership.name).write_bytes(membership.read_bytes())
    draw(features, args.output / "krasnodar-municipality-comparison.png")
    print(json.dumps({"municipalities_2018": 9, "municipalities_2023": 7,
        "removed": [r["name"] for r in rows if r["ieg_2023"] == "0"],
        "geometry_date": "2026-09-28", "reference_sha256": SOURCE_SHA,
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(args.output.iterdir()) if p.is_file()}}, ensure_ascii=False, indent=2))


def draw(features, output):
    import math
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Patch
    from shapely.geometry import shape

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, ax = plt.subplots(figsize=(11, 8), dpi=160)
    fig.set_facecolor("#f5f7ff")
    ax.set_facecolor("#f5f7ff")
    labels = {
        "r269701": ("Краснодар", (0, 0)),
        "r364116": ("Динской\nрайон", (10, 5)),
        "r364150": ("Северский\nрайон", (0, 0)),
        "r365144": ("Горячий Ключ", (0, -10)),
        "r1850083": ("Адыгейск", (-35, -28)),
        "r365285": ("Тахтамукайский\nрайон", (-48, -16)),
        "r953560": ("Теучежский\nрайон", (10, -10)),
        "r919011": ("Усть-Лабинский\nрайон", (0, 0)),
        "r953559": ("Красногвардейский\nрайон", (48, 5)),
    }
    for feature in features:
        geom = shape(feature["geometry"])
        for part in getattr(geom, "geoms", [geom]):
            ax.add_patch(Polygon(list(part.exterior.coords), facecolor="#a9baff" if feature["properties"]["value"] == 1 else "#f2c28b",
                edgecolor="#26385d", linewidth=0.7, hatch=None if feature["properties"]["value"] == 1 else "///", zorder=2))
            for ring in part.interiors:
                ax.add_patch(Polygon(list(ring.coords), facecolor="#f5f7ff", edgecolor="#26385d", linewidth=0.4, zorder=3))
        center = geom.representative_point()
        label, offset = labels[feature["properties"]["id"]]
        ax.annotate(label, (center.x, center.y), xytext=offset, textcoords="offset points", ha="center", va="center",
            fontsize=10, color="#15234a", bbox={"facecolor": "white", "edgecolor": "none", "alpha": .88, "pad": 2},
            arrowprops={"arrowstyle": "-", "color": "#26385d", "lw": .7} if offset != (0, 0) else None, zorder=5)
    bounds = [shape(f["geometry"]).bounds for f in features]
    ax.set_xlim(min(b[0] for b in bounds)-.16, max(b[2] for b in bounds)+.23)
    ax.set_ylim(min(b[1] for b in bounds)-.12, max(b[3] for b in bounds)+.12)
    ax.set_aspect(1 / math.cos(math.radians(45)))
    ax.set_axis_off()
    fig.suptitle("Какие территории различают варианты из 9 и 7 муниципалитетов", fontsize=16, x=.06, ha="left", y=.97)
    ax.legend(handles=[Patch(facecolor="#a9baff", edgecolor="#26385d", label="7 общих территорий: состав ИЭГ 2023 года"),
        Patch(facecolor="#f2c28b", edgecolor="#26385d", hatch="///", label="2 дополнительных района: только состав исследования 2018 года")],
        loc="lower left", bbox_to_anchor=(0, -.07), frameon=False, fontsize=10)
    fig.text(.06, .035, "Перечни: Институт экономики города, 2023, с. 60–61. Контуры: Terrae / © OpenStreetMap contributors, 28.09.2026.", fontsize=8.5)
    fig.text(.06, .013, "Сравнение состава на справочных контурах 2026 года. Исторические границы не восстановлены; поездки здесь не измеряются.", fontsize=8.5)
    fig.subplots_adjust(top=.9, bottom=.14, left=.04, right=.97)
    fig.savefig(output, facecolor=fig.get_facecolor(), metadata={"Software": "scripts/krasnodar_boundary_comparison.py"})
    plt.close(fig)


if __name__ == "__main__":
    main()

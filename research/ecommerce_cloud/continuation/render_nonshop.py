"""Draw the executed nonshop-selected conditional population panel.

Only factual input tables are used. Map points locate centres, not administrative
boundaries or travel areas; neither figure estimates a marketplace effect.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
BASE = Path("work/sources/research/ecommerce_settlement_20261024")
KEY = "source_record_id_2021"
COLORS = {"unselected": "#c3c7cd", "gain": "#2166a7",
          "loss": "#b96332", "unchanged": "#747b84"}


def true(v):
    return str(v).strip().casefold() in {"true", "1"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(latitude, longitude):
    # Same Lambert azimuthal equal-area projection as extension/render_figures.py.
    la = np.radians(np.asarray(latitude, dtype=float))
    lo = np.radians(np.asarray(longitude, dtype=float))
    la0, lo0 = np.radians(62), np.radians(100)
    k = np.sqrt(2 / (1 + np.sin(la0) * np.sin(la)
                    + np.cos(la0) * np.cos(la) * np.cos(lo - lo0)))
    return (6371.0088 * k * np.cos(la) * np.sin(lo - lo0),
            6371.0088 * k * (np.cos(la0) * np.sin(la)
                            - np.sin(la0) * np.cos(la) * np.cos(lo - lo0)))


def save(fig, output, name):
    paths = []
    for ext in ("png", "svg", "pdf"):
        path = output / (name + "." + ext)
        fig.savefig(path, dpi=190, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def render(root=ROOT):
    root = Path(root).resolve()
    panel_path = root / "work/ecommerce_extension_outcomes/nonshop_population_contexts/panels.csv"
    system_path = root / BASE / "settlement_role_stage_20261024/system/centre_system_demography.csv"
    # The fixed axis's manifest path is national_target_source2021.parquet.
    axis_path = root / BASE / "national/national_target_source2021.parquet"
    output = root / "work/ecommerce_continuation/figures"
    output.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(panel_path)
    system = pd.read_csv(system_path)
    axis = pd.read_parquet(axis_path)
    for label, frame in (("panel", panel), ("system", system), ("axis", axis)):
        assert frame[KEY].is_unique, label + " key is not unique"
    target = system.loc[system.medium_primary2002.map(true)].copy()
    assert len(target) == 1273
    selected = panel.loc[
        panel.medium_primary2002.map(true)
        & panel.positive_other_population_all_years.map(true)
    ].copy()
    assert len(selected) == 425
    assert selected.region_2021.nunique() == 55
    assert set(selected[KEY]) <= set(target[KEY])
    assert np.isfinite(selected[[
        "own_change2023_2025_pct", "other_change2023_2025_pct",
        "centre_share_change2023_2025_pp"
    ]].to_numpy()).all()
    selected["group"] = np.where(
        selected.centre_share_change2023_2025_pp.gt(0), "gain",
        np.where(selected.centre_share_change2023_2025_pp.lt(0), "loss", "unchanged"))
    assert selected.group.eq("gain").sum() == 340
    assert selected.group.eq("loss").sum() == 85
    target = target.merge(
        selected[[KEY, "group", "centre_share_change2023_2025_pp"]],
        on=KEY, how="left", validate="one_to_one")
    target["group"] = target.group.fillna("unselected")
    coords = ["accepted_latitude_2021", "accepted_longitude_2021"]
    target = target.merge(axis[[KEY] + coords], on=KEY, how="left", validate="one_to_one")
    valid = (np.isfinite(target[coords].to_numpy()).all(axis=1)
             & target[coords[0]].between(-90, 90)
             & target[coords[1]].between(-180, 180))
    plotted = target.loc[valid].copy()
    target.to_csv(output / "nonshop_population_map_data.csv", index=False)
    selected.to_csv(output / "nonshop_population_scatter_data.csv", index=False)
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.axisbelow": True, "savefig.facecolor": "white",
        "svg.fonttype": "none", "pdf.fonttype": 42})
    labels = {
        "unselected": "Нет сопоставленного условного исхода",
        "gain": "Доля населения центра выросла",
        "loss": "Доля населения центра снизилась",
        "unchanged": "Доля не изменилась"}
    total_counts = target.group.value_counts().to_dict()
    plotted_counts = plotted.group.value_counts().to_dict()
    missing_n = int((~valid).sum())
    figs = []
    fig, ax = plt.subplots(figsize=(13, 7.2))
    for group in ("unselected", "loss", "gain", "unchanged"):
        data = plotted.loc[plotted.group.eq(group)]
        if data.empty:
            continue
        ax.scatter(*project(data[coords[0]], data[coords[1]]),
                   s=12 if group == "unselected" else 22,
                   color=COLORS[group], alpha=.65 if group == "unselected" else .85,
                   edgecolors="white", linewidths=.25,
                   label=f"{labels[group]}: {len(data)}")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Демографическая доля средних центров: рост преобладает в наблюдаемой панели",
                 loc="left", fontsize=13, pad=18)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -.015),
              frameon=False, ncol=2, fontsize=9, markerscale=1.4)
    fig.subplots_adjust(bottom=.26, top=.90)
    fig.text(.06, .025,
             "1 273 средних центра принятой основы; условная панель — 425 центров, 55 регионов.\n"
             "Изменение доли на 1 января 2023–2025 гг.; центр и административное окружение заданы связью 2020 г.\n"
             f"Точки с доступными координатами: {len(plotted)}; без координат: {missing_n}. "
             "Серый цвет означает пропуск исхода, а не стабильность.\n"
             "Состав территорий 2023–2025 гг. не подтверждён; границы и поездки не показаны. "
             "Причинный эффект маркетплейсов не оценён.", fontsize=8.6)
    figs += save(fig, output, "nonshop_population_map")
    fig, ax = plt.subplots(figsize=(8.7, 8.3))
    xcol, ycol = "other_change2023_2025_pct", "own_change2023_2025_pct"
    values = selected[[xcol, ycol]].to_numpy()
    low, high = float(values.min()), float(values.max())
    pad = max(1, .06 * (high - low))
    limits = (low - pad, high + pad)
    ax.plot(limits, limits, color="#636b74", linewidth=1.1, linestyle="--",
            label="Одинаковое изменение центра и окружения")
    for group in ("gain", "loss", "unchanged"):
        data = selected.loc[selected.group.eq(group)]
        if len(data):
            ax.scatter(data[xcol], data[ycol], color=COLORS[group], s=27, alpha=.7,
                       edgecolors="white", linewidths=.35,
                       label=f"{labels[group]}: {len(data)}", zorder=3)
    ax.axhline(0, color="#bdc2c8", linewidth=.8)
    ax.axvline(0, color="#bdc2c8", linewidth=.8)
    ax.set_xlim(*limits)
    ax.set_ylim(*limits)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=.15)
    ax.set_xlabel("Изменение населения остальной части контекста, %")
    ax.set_ylabel("Изменение собственного населения центра, %")
    ax.set_title("Рост доли часто сопровождается сокращением самого центра",
                 loc="left", fontsize=12, pad=16)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.subplots_adjust(left=.13, right=.96, bottom=.24, top=.88)
    fig.text(.06, .025,
             "425 средних центров; все наблюдения показаны, выбросы не скрыты. "
             "На 1 января 2023–2025 гг.\n"
             "Выше диагонали население центра меняется лучше, чем население остальной части контекста.\n"
             "Окружение — условный административный остаток, не наблюдённый ареал поездок.\n"
             "Состав территорий не подтверждён. Это описательная динамика, не влияние маркетплейсов.",
             fontsize=8.5)
    figs += save(fig, output, "nonshop_population_scatter")
    summary = {
        "scope": "executed_population_panel_figures_not_causal_effect",
        "target_n": len(target), "selected_n": len(selected),
        "selected_regions": int(selected.region_2021.nunique()),
        "target_counts": total_counts, "plotted_counts": plotted_counts,
        "target_missing_coordinates": missing_n,
        "selected_own_population_decline_n": int(selected[ycol].lt(0).sum()),
        "selected_remainder_population_decline_n": int(selected[xcol].lt(0).sum()),
        "median_own_change_pct": float(selected[ycol].median()),
        "median_remainder_change_pct": float(selected[xcol].median()),
        "scatter_limits": list(limits), "all_selected_observations_displayed": True,
        "projection": "Lambert azimuthal equal-area; latitude0=62 longitude0=100 R=6371.0088km",
        "boundaries_displayed": False, "travel_catchment_observed": False,
        "territorial_comparability_verified": False, "causal_effect_identified": False,
        "inputs": [{"path": str(p.relative_to(root)), "sha256": sha(p)}
                   for p in (panel_path, system_path, axis_path)],
        "figures": [{"path": str(p.relative_to(root)), "sha256": sha(p)}
                    for p in figs]}
    (output / "nonshop_figures_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
    print("NONSHOP_FIGURES_SUMMARY_BEGIN")
    print(json.dumps(summary, ensure_ascii=False))
    print("NONSHOP_FIGURES_SUMMARY_END")
    return summary


if __name__ == "__main__":
    render()

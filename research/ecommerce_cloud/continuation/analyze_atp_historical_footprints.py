"""Historical ATP WB footprints with the previously reviewed symmetric matcher.

Only observed positive records are counted. No opening/closure dates, nearest-
settlement membership, 2026 survivors, true catchments, or causal effects.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import itertools
import json
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "work/sources/research/ecommerce_settlement_20261024"
KEY = "source_record_id_2021"
PINS = json.loads('''[{"run_id":"2023-10-28-13-32-45","sha256":"0838baa3e8ee3b6caa161c9034f08c1dab9943eeb2664d126384fcda200dbbe0","features":29250,"ru":26281,"start":"2023-10-28T13:32:45Z","end":"2023-10-29T23:59:20Z"},{"run_id":"2023-12-30-13-32-01","sha256":"16e903e7d3f52ae2fb764737d129a244429bc09561bd61719c6ded694b472b45","features":34069,"ru":30425,"start":"2023-12-30T13:32:01Z","end":"2023-12-31T22:13:11Z"},{"run_id":"2024-03-30-13-32-35","sha256":"7563859c886ca878225524f1f4642248ed1390f26fc0dc9ce4540c3294388a8b","features":38455,"ru":34192,"start":"2024-03-30T13:32:35Z","end":"2024-03-31T23:10:37Z"},{"run_id":"2024-06-29-13-32-11","sha256":"8d5e5ba3ea6c0c6666d02611e20e8611905d1a2997dd69c854b34df6c75a86f2","features":42805,"ru":37867,"start":"2024-06-29T13:32:11Z","end":"2024-07-01T01:16:09Z"},{"run_id":"2024-09-07-13-32-11","sha256":"b0bd9fdf68da6995d3947f8d0540bf43bd5e22be3fa52e806e4eeabbac485729","features":47472,"ru":42104,"start":"2024-09-07T13:32:11Z","end":"2024-09-09T05:18:02Z"},{"run_id":"2024-12-28-13-31-57","sha256":"106c7739077c78c50dbd5e6bf0413b8f27a71d7f6f054da7b50c09f314b1a25e","features":61595,"ru":55726,"start":"2024-12-28T13:31:57Z","end":"2024-12-30T09:00:31Z"}]''')
FIRST = "2023-10-28-13-32-45"
LAST_SAME_API = "2024-09-07-13-32-11"
DEC_BREAK = "2024-12-28-13-31-57"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def true(value):
    return str(value).strip().casefold() in {"true", "1"}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf8")


def main(args):
    output = ROOT / args.output
    rawdir = ROOT / args.raw_dir
    output.mkdir(parents=True, exist_ok=True)
    matcher_path = BASE / "history_stage_20261024/link_history_symmetrically.py"
    spec = importlib.util.spec_from_file_location("reviewed_symmetric_wb", matcher_path)
    matcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matcher)
    axis_path = BASE / "national/national_target_source2021.parquet"
    context_path = BASE / "history_stage_20261024/centres/settlement_admin_context_main2021.parquet"
    system_path = BASE / "settlement_role_stage_20261024/system/centre_system_demography.csv"
    axis, context = pd.read_parquet(axis_path), pd.read_parquet(context_path)
    system = pd.read_csv(system_path)
    assert axis[KEY].is_unique and context[KEY].is_unique and system[KEY].is_unique
    assert len(axis) == len(context) == 144151
    fields = [KEY] + [
        f"{field}_{vintage}" for vintage in ("20200110", "20211103")
        for field in ("admin_centre_positive", "context_status",
                      "administrative_centre_source_record_id_2021")]
    nodes = axis.merge(context[fields], on=KEY, validate="one_to_one")
    medium = system.loc[system.medium_primary2002.map(true)].copy()
    assert len(medium) == 1273
    medium_ids = set(medium[KEY])
    assert medium_ids <= set(axis[KEY])
    points = axis.loc[axis.accepted_point_present_2021].copy().reset_index(drop=True)
    assert len(points) == 144149
    xyz = matcher.unit_vectors(points.accepted_latitude_2021.to_numpy(),
                               points.accepted_longitude_2021.to_numpy())
    tree = cKDTree(xyz)
    names = [matcher.norm(v) for v in points.name_2021]
    ids = points[KEY].tolist()
    source_evidence, all_links, ru_objects = [], [], {}
    for pin in PINS:
        rid = pin["run_id"]
        body_path = rawdir / (rid + "_wildberries.geojson")
        csv_path = rawdir / (rid + "_points.csv")
        assert sha(body_path) == pin["sha256"], "Historical raw body pin failed: " + rid
        fs = json.loads(body_path.read_bytes())["features"]
        assert len(fs) == pin["features"]
        data = pd.read_csv(csv_path, dtype={"source_ref": str, "country_reported": str},
                           keep_default_na=False)
        assert len(data) == len(fs)
        # The CSV is an execution convenience, not a substitute for pinned raw.
        expected = []
        for feature in fs:
            p, geometry = feature["properties"], feature["geometry"]
            expected.append({
                "source_ref": str(p.get("ref") or ""),
                "country_reported": str(p.get("addr:country") or p.get("country") or "").upper(),
                "longitude": float(geometry["coordinates"][0]),
                "latitude": float(geometry["coordinates"][1]),
                "address_full": str(p.get("addr:full") or p.get("addr_full") or p.get("address") or ""),
            })
        expected = pd.DataFrame(expected)
        for col in ("source_ref", "country_reported", "address_full"):
            assert data[col].astype(str).tolist() == expected[col].astype(str).tolist(), (rid, col)
        assert np.allclose(data[["longitude", "latitude"]], expected[["longitude", "latitude"]],
                           rtol=0, atol=1e-10)
        assert set(data.run_id) == {rid}
        ru = data.loc[data.country_reported.eq("RU")].copy().reset_index(drop=True)
        assert len(ru) == pin["ru"] and ru.source_ref.is_unique
        ru_objects[rid] = ru.set_index("source_ref")
        obj_xyz = matcher.unit_vectors(data.latitude.to_numpy(), data.longitude.to_numpy())
        candidates = tree.query_ball_point(obj_xyz, 2 * np.sin(10 / (2 * matcher.EARTH)))
        links = []
        for row, location, nearby in zip(data.itertuples(index=False), obj_xyz, candidates):
            textual = matcher.address_names(row.address_full)
            matches = []
            for idx in nearby:
                if names[idx] in textual:
                    chord = np.linalg.norm(location - xyz[idx])
                    km = 2 * matcher.EARTH * np.arcsin(min(1, chord / 2))
                    matches.append((ids[idx], float(km)))
            record = {"run_id": rid, "source_ref": row.source_ref, "country_reported": row.country_reported,
                      "latitude": row.latitude, "longitude": row.longitude, "address": row.address_full}
            for radius in (1, 5, 10):
                accepted = [(i, km) for i, km in matches if km <= radius]
                record[f"link_status_{radius}km"] = (
                    "accepted_unique_exact_address_component_and_coordinate" if len(accepted) == 1 else
                    "ambiguous_multiple_named_candidates" if len(accepted) > 1 else "unresolved_no_named_candidate")
                record[f"{KEY}_{radius}km"] = accepted[0][0] if len(accepted) == 1 else None
                record[f"distance_km_{radius}km"] = accepted[0][1] if len(accepted) == 1 else None
            links.append(record)
        full = pd.DataFrame(links)
        full["country_scope"] = "all_countries"
        only_ru = full.loc[full.country_reported.eq("RU")].copy()
        only_ru["country_scope"] = "RU_only"
        all_links.extend([full, only_ru])
        source_evidence.append({
            **pin, "raw_path": str(body_path.relative_to(ROOT)),
            "points_csv_path": str(csv_path.relative_to(ROOT)),
            "points_csv_sha256": sha(csv_path),
            "ru_rows_verified_against_raw": len(ru),
            "source_uri_counts": pd.Series([
                str(f["properties"].get("@source_uri") or "") for f in fs
            ]).value_counts().to_dict(),
            "nonempty_country_counts": expected.country_reported.value_counts().to_dict(),
        })
    linked = pd.concat(all_links, ignore_index=True)
    assert not linked.duplicated(["run_id", "country_scope", "country_reported", "source_ref"]).any()
    linked.to_parquet(output / "atp_wb_symmetric_links.parquet", index=False)
    inventory, footprints, centre_rows, positive_sets = [], [], [], {}
    for (rid, country_scope), group in linked.groupby(["run_id", "country_scope"]):
        api_group = "new_api_break_dec2024" if rid == DEC_BREAK else "same_pickups_api_oct2023_sep2024"
        for radius in (1, 5, 10):
            col = f"{KEY}_{radius}km"
            accepted = group.loc[group[col].notna()]
            counts = accepted.groupby(col).size()
            positive = set(counts.index)
            positive_sets[(rid, country_scope, radius)] = positive
            inventory.append({
                "run_id": rid, "country_scope": country_scope, "api_group": api_group, "radius_km": radius,
                "objects_in_country_scope": len(group), "linked_objects": len(accepted),
                "positive_nodes": len(positive),
                "status_counts": json.dumps(group[f"link_status_{radius}km"].value_counts().to_dict()),
            })
            for vintage in ("20200110", "20211103"):
                centre_flag = f"admin_centre_positive_{vintage}"
                known_flag = f"context_status_{vintage}"
                group_col = f"administrative_centre_source_record_id_2021_{vintage}"
                known = nodes[known_flag].eq("accepted_administrative_parent_and_centre")
                observed = nodes.loc[nodes[KEY].isin(positive)]
                footprints.append({
                    "run_id": rid, "country_scope": country_scope, "api_group": api_group, "radius_km": radius,
                    "context_vintage": vintage, "positive_nodes": len(observed),
                    "positive_centre_nodes": int(observed[centre_flag].map(true).sum()),
                    "positive_other_known_nodes": int((
                        observed[known_flag].eq("accepted_administrative_parent_and_centre")
                        & ~observed[centre_flag].map(true)).sum()),
                    "positive_unknown_context_nodes": int((
                        ~observed[known_flag].eq("accepted_administrative_parent_and_centre")
                        & ~observed[centre_flag].map(true)).sum()),
                })
                groups = dict(tuple(nodes.loc[known].groupby(group_col)))
                for row in medium.itertuples(index=False):
                    cid = getattr(row, KEY)
                    members = groups.get(cid)
                    if members is None:
                        others = nodes.iloc[:0]
                    else:
                        others = members.loc[members[KEY].ne(cid)]
                    inhabited = others.loc[others.population_2021.gt(0)]
                    other_positive = inhabited.loc[inhabited[KEY].isin(positive)]
                    own_positive = cid in positive
                    if members is None or len(inhabited) == 0:
                        category = "no_accepted_inhabited_periphery_observed"
                    elif own_positive and len(other_positive):
                        category = "positive_centre_and_positive_periphery"
                    elif own_positive:
                        category = "positive_centre_no_positive_periphery_record"
                    elif len(other_positive):
                        category = "positive_periphery_no_positive_centre_record"
                    else:
                        category = "no_positive_records_not_proven_absence"
                    centre_rows.append({
                        "run_id": rid, "country_scope": country_scope, "api_group": api_group, "radius_km": radius,
                        "context_vintage": vintage, KEY: cid,
                        "name_2021": row.name_2021, "region_2021": row.region_2021,
                        "centre_positive_record": own_positive,
                        "centre_observed_objects": int(counts.get(cid, 0)),
                        "context_has_accepted_members": members is not None,
                        "other_accepted_members": len(others),
                        "other_inhabited_members2021": len(inhabited),
                        "positive_other_inhabited_members": len(other_positive),
                        "positive_other_objects": int(sum(counts.get(i, 0) for i in other_positive[KEY])),
                        "category": category,
                    })
    inv, footprint, centres = map(pd.DataFrame, (inventory, footprints, centre_rows))
    assert centres.groupby(["run_id", "country_scope", "radius_km", "context_vintage"]).size().eq(1273).all()
    assert centres.positive_other_inhabited_members.le(centres.other_inhabited_members2021).all()
    inv.to_csv(output / "atp_wb_linkage_inventory.csv", index=False)
    footprint.to_csv(output / "atp_wb_footprints.csv", index=False)
    centres.to_csv(output / "atp_wb_1273_contexts.csv", index=False)
    aggregates = []
    for keys, g in centres.groupby(["run_id", "country_scope", "api_group", "radius_km", "context_vintage"]):
        aggregates.append({
            **dict(zip(["run_id", "country_scope", "api_group", "radius_km", "context_vintage"], keys)),
            "target_medium_centres": len(g),
            "centre_positive_record_n": int(g.centre_positive_record.sum()),
            "contexts_positive_periphery_n": int(g.positive_other_inhabited_members.gt(0).sum()),
            "positive_other_inhabited_members_sum": int(g.positive_other_inhabited_members.sum()),
            "median_positive_other_inhabited_members": float(g.positive_other_inhabited_members.median()),
            "category_counts": json.dumps(g.category.value_counts().to_dict()),
        })
    agg = pd.DataFrame(aggregates)
    agg.to_csv(output / "atp_wb_1273_summary.csv", index=False)
    transitions = []
    for country_scope, radius in itertools.product(("all_countries", "RU_only"), (1, 5, 10)):
        for end in (LAST_SAME_API, DEC_BREAK):
            a, b = positive_sets[(FIRST, country_scope, radius)], positive_sets[(end, country_scope, radius)]
            transitions.append({
                "first_run": FIRST, "last_run": end, "country_scope": country_scope, "radius_km": radius,
                "api_comparability": "same_spider_source_and_filters" if end == LAST_SAME_API else "source_api_break_do_not_read_as_growth",
                "first_positive_nodes": len(a), "last_positive_nodes": len(b),
                "positive_both_nodes": len(a & b), "first_only_record_nodes": len(a - b),
                "last_only_record_nodes": len(b - a),
                "warning": "Record differences are not opening/closure dates or true network changes.",
            })
    pd.DataFrame(transitions).to_csv(output / "atp_wb_observed_set_differences.csv", index=False)

    paired_rows, paired_summary = [], []
    for country_scope, radius in itertools.product(("all_countries", "RU_only"), (1, 5, 10)):
        for vintage in ("20200110", "20211103"):
            a = centres.loc[
                centres.run_id.eq(FIRST) & centres.country_scope.eq(country_scope) & centres.radius_km.eq(radius)
                & centres.context_vintage.eq(vintage)
            ].set_index(KEY)
            for end in (LAST_SAME_API, DEC_BREAK):
                b = centres.loc[
                    centres.run_id.eq(end) & centres.country_scope.eq(country_scope) & centres.radius_km.eq(radius)
                    & centres.context_vintage.eq(vintage)
                ].set_index(KEY).reindex(a.index)
                assert len(a) == len(b) == 1273
                assert a.other_inhabited_members2021.equals(b.other_inhabited_members2021)
                change = (b.positive_other_inhabited_members - a.positive_other_inhabited_members)
                both = a.centre_positive_record & b.centre_positive_record
                supported = a.other_inhabited_members2021.gt(0)
                group = {
                    "first_run": FIRST, "last_run": end, "country_scope": country_scope, "radius_km": radius,
                    "context_vintage": vintage, "api_break": end == DEC_BREAK}
                paired_summary.append({
                    **group, "all_medium_centres_n": 1273,
                    "accepted_inhabited_periphery_contexts_n": int(supported.sum()),
                    "centres_positive_in_both_n": int(both.sum()),
                    "periphery_positive_count_increased_all_n": int((supported & change.gt(0)).sum()),
                    "periphery_positive_count_decreased_all_n": int((supported & change.lt(0)).sum()),
                    "positive_both_centres_with_periphery_increase_n": int((both & supported & change.gt(0)).sum()),
                    "positive_both_centres_with_periphery_decrease_n": int((both & supported & change.lt(0)).sum()),
                    "warning": "Historical positive-both cohort is descriptive selection, not a causal estimand; no2026 conditioning.",
                })
                for cid in a.index:
                    paired_rows.append({
                        **group, KEY: cid,
                        "centre_positive_first": bool(a.at[cid, "centre_positive_record"]),
                        "centre_positive_last": bool(b.at[cid, "centre_positive_record"]),
                        "other_inhabited_members2021": int(a.at[cid, "other_inhabited_members2021"]),
                        "positive_periphery_first": int(a.at[cid, "positive_other_inhabited_members"]),
                        "positive_periphery_last": int(b.at[cid, "positive_other_inhabited_members"]),
                        "observed_positive_periphery_difference": int(change.at[cid]),
                    })
    pd.DataFrame(paired_rows).to_csv(output / "atp_wb_1273_paired_contexts.csv", index=False)
    pd.DataFrame(paired_summary).to_csv(output / "atp_wb_1273_paired_summary.csv", index=False)

    identity = []
    for end in (LAST_SAME_API, DEC_BREAK):
        a, b = ru_objects[FIRST], ru_objects[end]
        common = a.index.intersection(b.index)
        u = matcher.unit_vectors(a.loc[common].latitude.to_numpy(), a.loc[common].longitude.to_numpy())
        v = matcher.unit_vectors(b.loc[common].latitude.to_numpy(), b.loc[common].longitude.to_numpy())
        km = 2 * matcher.EARTH * np.arcsin(np.minimum(1, np.linalg.norm(u - v, axis=1) / 2))
        identity.append({
            "first_run": FIRST, "last_run": end, "common_ru_reported_refs": len(common),
            "common_refs_coordinates_within100m": int((km <= .1).sum()),
            "common_refs_coordinates_over1km": int((km > 1).sum()),
            "api_break": end == DEC_BREAK,
            "warning": "Stable coordinates support identity continuity; do not establish equal object taxonomy or completeness.",
        })

    coexistence = {"status": "not_computed_demographic_panel_not_present"}
    demo_path = ROOT / args.demographic_panel
    if demo_path.exists():
        demo = pd.read_csv(demo_path)
        demo = demo.loc[demo.medium_primary2002.map(true)
                        & demo.positive_other_population_all_years.map(true)].copy()
        assert demo[KEY].is_unique and 0 < len(demo) <= len(medium)
        pair = pd.DataFrame(paired_rows)
        pair = pair.loc[
            pair.last_run.eq(LAST_SAME_API) & pair.radius_km.eq(5)
            & pair.context_vintage.eq("20200110") & pair.country_scope.eq("all_countries")
        ].copy()
        joined = demo.merge(pair, on=KEY, how="left", validate="one_to_one", indicator=True)
        assert len(joined) == len(demo) and joined._merge.eq("both").all()
        joined["observed_periphery_positive_count_increased"] = joined.observed_positive_periphery_difference.gt(0)
        joined.to_csv(output / "atp_wb_demography_descriptive_join.csv", index=False)
        coexistence_rows = []
        for increased, g in joined.groupby("observed_periphery_positive_count_increased"):
            coexistence_rows.append({
                "observed_periphery_positive_count_increased": bool(increased), "centres_n": len(g),
                "demographic_share_increased_n": int(g.centre_share_change2023_2025_pp.gt(0).sum()),
                "own_population_declined_n": int(g.own_change2023_2025_pct.lt(0).sum()),
                "median_demographic_share_change_pp": float(g.centre_share_change2023_2025_pp.median()),
                "median_own_population_change_pct": float(g.own_change2023_2025_pct.median()),
                "median_other_population_change_pct": float(g.other_change2023_2025_pct.median()),
            })
        coexistence = {
            "status": "descriptive_coexistence_joined",
            "source_path": str(demo_path.relative_to(ROOT)), "source_sha256": sha(demo_path),
            "n": len(joined), "groups": coexistence_rows,
            "warning": "Different observation windows, selected demographic panel and unverified territories; association/coexistence is not a platform effect.",
        }

    summary = {
        "scope": "historical_observed_ATP_WB_named_address_footprints",
        "demographic_coexistence": coexistence,
        "status": "computed_from_six_pinned_actual_raw_bodies",
        "linker": {"path": str(matcher_path.relative_to(ROOT)), "sha256": sha(matcher_path),
                   "rule": "Unmodified prior norm/address_names/unit_vectors; unique exact name in first four comma-separated address components, type prefix and parentheses removed, coordinate radius1/5/10km.",
                   "independent_region_validator": False, "settlement_boundaries_verified": False},
        "inputs": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)}
                   for p in (axis_path, context_path, system_path)],
        "sources": source_evidence,
        "same_api_spider_pin": "45d26f4042ee0128facc8d4cf1636eec007bd7b7",
        "december_api_change_pin": "e84f9cccfa02e73afbbbc2d5695211e55b693bcb",
        "main_2020_context_5km": agg.loc[
            agg.radius_km.eq(5) & agg.context_vintage.eq("20200110") & agg.country_scope.eq("all_countries")
        ].to_dict("records"),
        "national_5km": footprint.loc[
            footprint.radius_km.eq(5) & footprint.context_vintage.eq("20200110") & footprint.country_scope.eq("all_countries")
        ].to_dict("records"),
        "set_differences": transitions, "identity_continuity": identity,
        "paired_main_2020_5km": [r for r in paired_summary if r["radius_km"] == 5 and r["context_vintage"] == "20200110" and r["country_scope"] == "all_countries"],
        "limits": [
            "ATP addr:country may be reverse-geocoded, not provider-reported country.",
            "Main geography uses all-country records on the fixed accepted national axis; RU-only is a separate sensitivity.",
            "The producer excludes external postamats and dtype6; raw operator/type/fitting fields are absent from ATP output.",
            "Same spider code and source API do not prove an unchanged backend catalogue universe or reverse-geocoder.",
            "Run metadata windows cover all spiders; individual Wildberries collection timestamps are not established.",
            "September observation is the successful September7 run, not September28 or quarter end.",
            "December2024 uses a different source API; analyse separately.",
            "Name-coordinate matching is not proof of settlement boundary membership or actual trips.",
            "Fixed2021 names/coordinates and administrative2020/2021 contexts may miss historical or changed links.",
            "Counts measure observed pickup infrastructure, not the functions or weakening of centres.",
            "No openings, closures, true absence, population effects or causal platform effects are inferred.",
            "No 2026 observations enter the selection, identity comparison or denominator.",
        ],
    }
    write_json(output / "atp_wb_analysis_summary.json", summary)
    print("ATP_WB_ANALYSIS_BEGIN")
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    print("ATP_WB_ANALYSIS_END")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default="work/ecommerce_atp_history")
    parser.add_argument("--output", default="work/ecommerce_atp_analysis")
    parser.add_argument("--demographic-panel", default="work/ecommerce_extension_outcomes/nonshop_population_contexts/panels.csv")
    main(parser.parse_args())

"""Audit actual ATP historical run inventories for a Russian Ozon spider.

Non-discovery is about this data source, never physical absence of Ozon points.
The similarly named Ozone.bg spider is a different Bulgarian retailer, added2026.
"""
from pathlib import Path
import argparse
import json
import hashlib
from acquire_atp_historical import Fetcher, parse_json
ROOT = Path(__file__).resolve().parents[3]
TREE_AUDIT = json.loads('''[{"year":"2021-12-31","sha":"2ba3afabf795ff828dde31669dce47fbdb4890a4","date":"2021-12-29T04:09:56Z","tree":"6abe229aa477b777b948d5024b7b6457c0d70b3a","truncated":false,"tree_count":868,"spider_count":813,"ozon_matches":[{"path":"locations/spiders/autozone.py","sha":"eda2cd2e64a6a26420e06cccde63dc36476c1cb1"}]},{"year":"2022-12-31","sha":"011ace8b6780ac7a0bc3ac68a1584990d58e1c90","date":"2022-12-31T21:08:11Z","tree":"070768bbf775c622cd700969bf105f2fd356e916","truncated":false,"tree_count":1261,"spider_count":1133,"ozon_matches":[{"path":"locations/spiders/autozone.py","sha":"5eea138e7a9134192313e5b2c318587fae59926a"}]},{"year":"2023-12-31","sha":"81a2b7b58f02078899d505a022d6e57b210a1576","date":"2023-12-31T15:11:16Z","tree":"478f4b696c3131dadb03e1fd3294843bd34f7326","truncated":false,"tree_count":2164,"spider_count":1959,"ozon_matches":[]},{"year":"2024-12-31","sha":"5b1029cd4478c1769b011a6adf162e5a74f70bc9","date":"2024-12-30T16:04:00Z","tree":"31aa2a5d40bfbdb9fce6a3e21bf5e66484120861","truncated":false,"tree_count":5430,"spider_count":3485,"ozon_matches":[{"path":"locations/spiders/autozone_us.py","sha":"06e41c892d4d8313622baa985798f561fa493799"}]}]''')
HISTORY_URLS = ["https://data.alltheplaces.xyz/runs/history.json",
                "https://alltheplaces-data.openaddresses.io/runs/history.json"]
RUSSIAN_CANDIDATES = {"ozon", "ozon_ru", "ozon_russia", "ozonru", "ozon_pickup"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entries(obj):
    """Extract explicit spider records, retaining feature-count provenance."""
    if isinstance(obj, list):
        return [row for row in obj if isinstance(row, dict)
                and isinstance(row.get("spider"), str)]
    if isinstance(obj, dict):
        if isinstance(obj.get("spider"), str):
            return [obj]
        for key in ("results", "spiders"):
            if key in obj:
                value = obj[key]
                if isinstance(value, dict):
                    return [{"spider": k, **v} for k, v in value.items()
                            if isinstance(v, dict)]
                found = entries(value)
                if found:
                    return found
    return []


def profile(body, metadata, source):
    obj = parse_json(body)
    rows = entries(obj)
    names = sorted(set(row["spider"] for row in rows))
    matches = [row for row in rows if "ozon" in row["spider"].casefold()]
    russian = [row for row in rows if row["spider"].casefold() in RUSSIAN_CANDIDATES]
    expected = metadata.get("spiders")
    return {
        "source": source, "run_metadata": metadata, "body_sha256": sha(body),
        "body_bytes": len(body), "parsed_spider_names_n": len(names),
        "expected_spiders_from_metadata": expected,
        "inventory_count_matches_metadata": len(names) == expected if isinstance(expected, int) else None,
        "schema_recognized": bool(rows),
        "ozon_substring_matches_including_unrelated_autozone": matches,
        "explicit_russian_ozon_candidate_entries": russian,
        "spider_names_sha256": sha("\n".join(names).encode()),
        "meaning": "Source inventory non-discovery only; no claim about platform network absence.",
    }, names


def main(args):
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    fetch = Fetcher(output, 180)
    results, failures = [], []
    manifest_path = ROOT / "research/ecommerce_cloud/continuation/atp_pinned_manifest.json"
    pinned = json.loads(manifest_path.read_text())["records"]
    # Read all six actual byte-pinned 2023/2024 inventories already restored in CI.
    for row in pinned:
        rid = row["run_id"]
        path = ROOT / args.pinned_dir / (rid + "_pinned_runwide_stats.json")
        try:
            body = path.read_bytes()
            assert sha(body) == row["stats_sha256"]
            meta = row.get("run_metadata", {"run_id": rid})
            info, names = profile(body, meta, str(path.relative_to(ROOT)))
            (output / (rid + "_spider_names.txt")).write_text("\n".join(names), encoding="utf8")
            results.append(info)
        except Exception as exc:
            failures.append({"run_id": rid, "phase": "pinned_inventory", "error": str(exc)})
    history = None
    for url in HISTORY_URLS:
        try:
            body, event = fetch.get(url, 12 * 1024 * 1024)
            obj = parse_json(body)
            if not isinstance(obj, list):
                raise ValueError("Expected documented history list")
            history = obj
            (output / "history.json").write_bytes(body)
            history_evidence = {"url": url, "sha256": sha(body), "bytes": len(body)}
            break
        except Exception as exc:
            failures.append({"url": url, "phase": "metadata", "error": str(exc)})
    if history is not None:
        for year in (2021, 2022, 2023, 2024):
            candidates = [r for r in history if isinstance(r, dict)
                          and str(r.get("run_id", "")).startswith(str(year) + "-")]
            candidates.sort(key=lambda r: r["run_id"], reverse=True)
            for row in candidates[:3]:
                rid, url = row["run_id"], row.get("stats_url", "")
                try:
                    if rid not in url:
                        raise ValueError("Metadata stats URL lacks its actual run ID")
                    body, event = fetch.get(url, 12 * 1024 * 1024)
                    info, names = profile(body, row, url)
                    (output / (rid + "_runwide_stats.json")).write_bytes(body)
                    (output / (rid + "_spider_names.txt")).write_text("\n".join(names), encoding="utf8")
                    results.append(info)
                    if info["schema_recognized"]:
                        break
                except Exception as exc:
                    failures.append({"run_id": rid, "url": url, "phase": "annual_inventory", "error": str(exc)})
    report = {
        "scope": "ATP historical Russian Ozon source audit, not platform absence",
        "source_tree_audits": TREE_AUDIT,
        "history": history_evidence if history is not None else None,
        "actual_run_inventory_profiles": results, "failures": failures,
        "http_evidence": fetch.events,
        "current_ozone_bg": {
            "spider_path": "locations/spiders/ozone_bg.py",
            "blob_sha": "68df07f3ed06df44cd467a06259361441af09a59",
            "added_commit": "d9aebbaf2be56b9793b0fd8e477384bbcbf2e896",
            "added_at": "2026-08-24T01:06:49Z",
            "brand": "Ozone.bg", "start_url": "https://www.ozone.bg/our-shops/",
            "russian_ozon": False,
        },
        "limits": [
            "Year-end trees do not exhaust every transient filename or unnamed multibrand source.",
            "No matching spider in an inventory does not prove no pickup objects existed.",
            "A zero feature count or failed spider would describe acquisition, not physical absence.",
            "An unrelated AutoZone/Ozone.bg match is not a Russian Ozon observation.",
        ],
    }
    (output / "ozon_source_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print("ATP_OZON_SOURCE_AUDIT_BEGIN")
    print(json.dumps(report, ensure_ascii=False))
    print("ATP_OZON_SOURCE_AUDIT_END")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="work/ecommerce_atp_ozon_audit")
    p.add_argument("--pinned-dir", default="work/ecommerce_atp_history")
    main(p.parse_args())

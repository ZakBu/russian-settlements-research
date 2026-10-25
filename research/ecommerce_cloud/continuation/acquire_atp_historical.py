#!/usr/bin/env python3
"""Bounded, stdlib-only acquisition of *historical* ATP Wildberries output.

No latest endpoints, opening-date inference, absence-as-closure inference, or
survivor conditioning. Network/TLS verification is always enabled. Run metadata,
HTTP evidence, bytes and SHA256 are preserved; output is usable independently of
the optional geometric proximity audit. CC0 source: alltheplaces/alltheplaces.
"""
import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import pathlib
import re
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

VERSION = "atp-wb-historical-v1"
FIRST = "2023-10-27"
LAST = "2024-12-31"
TARGETS = ["2023-10-31", "2023-12-31", "2024-03-31", "2024-06-30",
           "2024-09-30", "2024-12-31"]
HOSTS = ["https://data.alltheplaces.xyz",
         "https://alltheplaces-data.openaddresses.io",
         "https://alltheplaces.openaddresses.io"]
CODE_CHANGES = [
    {"sha": "45d26f4042ee0128facc8d4cf1636eec007bd7b7",
     "date": "2023-10-27", "endpoint": "www.wildberries.ru/webapi/spa/modules/pickups",
     "filter": "exclude isExternalPostamat and dtype=6"},
    {"sha": "e84f9cccfa02e73afbbbc2d5695211e55b693bcb",
     "date": "2024-12-04", "endpoint": "static-basket-01.wbbasket.ru/vol0/data/all-poo-fr-v9.json",
     "filter": "loop countries; exclude isExternalPostamat and dtype=6"},
]
LIMIT = 100 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm(value):
    return re.sub(r"[^0-9a-zа-я]+", " ", str(value).casefold().replace("ё", "е")).strip()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Fetcher:
    def __init__(self, output, deadline, ca_file=None):
        self.output = output
        self.deadline = time.monotonic() + deadline
        self.context = ssl.create_default_context()
        if ca_file:
            self.context.load_verify_locations(cafile=ca_file)
        self.events = []
        self.counter = 0

    def get(self, url, limit, headers=None, method="GET"):
        if time.monotonic() > self.deadline:
            raise RuntimeError("global network deadline exceeded")
        if not url.startswith("https://") or "/latest" in url:
            raise ValueError("only verified HTTPS historical URLs permitted")
        self.counter += 1
        event = {"request_id": self.counter, "url": url, "method": method,
                 "at": stamp(), "request_headers": headers or {}}
        self.events.append(event)
        req = urllib.request.Request(
            url, headers={"User-Agent": "settlement-history-research/1.0",
                          "Accept-Encoding": "identity", **(headers or {})},
            method=method)
        try:
            with urllib.request.urlopen(req, timeout=20, context=self.context) as response:
                event.update(status=response.status, final_url=response.url,
                             headers=dict(response.headers))
                if "/latest" in response.url:
                    raise ValueError("redirect to latest rejected")
                if method == "HEAD":
                    data = b""
                else:
                    chunks = []
                    size = 0
                    while True:
                        if time.monotonic() > self.deadline:
                            raise RuntimeError("global network deadline exceeded")
                        chunk = response.read(min(1024 * 1024, limit + 1 - size))
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > limit:
                            raise ValueError("response exceeds bounded byte limit")
                        chunks.append(chunk)
                    data = b"".join(chunks)
                event.update(bytes=len(data), sha256=sha(data), complete=True)
                return data, event
        except urllib.error.HTTPError as exc:
            body = exc.read(16384)
            event.update(status=exc.code, error=str(exc), error_body_sha256=sha(body),
                         error_body_excerpt=body[:400].decode("utf8", "replace"))
            raise
        except Exception as exc:
            event.update(error=type(exc).__name__ + ": " + str(exc), complete=False)
            raise


class RemoteZip(io.RawIOBase):
    """Read only a ZIP directory and selected member using verified HTTP ranges."""
    def __init__(self, fetcher, url):
        self.fetcher, self.url, self.pos = fetcher, url, 0
        self.calls, self.transferred = 0, 0
        data, event = fetcher.get(url, 1, {"Range": "bytes=0-0"})
        cr = event.get("headers", {}).get("Content-Range", "")
        if not cr:
            cr = next((v for k, v in event.get("headers", {}).items()
                       if k.lower() == "content-range"), "")
        match = re.fullmatch(r"bytes 0-0/(\d+)", cr)
        if event.get("status") != 206 or not match:
            raise ValueError("server does not support verifiable byte ranges")
        self.size = int(match.group(1))
        self.transferred = len(data)

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (
            self.pos + offset if whence == 1 else self.size + offset)
        if self.pos < 0:
            raise ValueError("negative ZIP seek")
        return self.pos

    def read(self, size=-1):
        size = self.size - self.pos if size < 0 else min(size, self.size - self.pos)
        if size <= 0:
            return b""
        if size > 32 * 1024 * 1024 or self.calls >= 32 or self.transferred + size > LIMIT:
            raise ValueError("bounded ZIP range budget exceeded")
        end = self.pos + size - 1
        data, event = self.fetcher.get(self.url, size,
                                      {"Range": "bytes=%d-%d" % (self.pos, end)})
        headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
        expected = "bytes %d-%d/%d" % (self.pos, end, self.size)
        if event.get("status") != 206 or headers.get("content-range") != expected or len(data) != size:
            raise ValueError("invalid/ignored ZIP range response")
        self.calls += 1
        self.transferred += len(data)
        self.pos += len(data)
        return data


def parse_json(raw):
    if raw[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
            raw = zipped.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("expanded gzip exceeds byte limit")
    return json.loads(raw)


def features(raw):
    obj = parse_json(raw)
    if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
        return obj["features"]
    if isinstance(obj, list):
        return obj
    raise ValueError("expected complete GeoJSON FeatureCollection or feature list")


def historical_runs(obj):
    if isinstance(obj, dict):
        for key in ("runs", "history", "results"):
            if isinstance(obj.get(key), list):
                obj = obj[key]
                break
        else:
            obj = [{"run_id": k, **v} for k, v in obj.items() if isinstance(v, dict)]
    if not isinstance(obj, list):
        raise ValueError("unknown history schema")
    rows = []
    for row in obj:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("run_id", ""))
        if re.fullmatch(r"\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d", rid):
            if FIRST <= rid[:10] <= LAST:
                rows.append(row)
    return sorted(rows, key=lambda x: x["run_id"], reverse=True)


def load_axis(path):
    if not path:
        return None
    cells = collections.defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                lat = float(row["accepted_latitude_2021"])
                lon = float(row["accepted_longitude_2021"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
            except (ValueError, TypeError, KeyError):
                continue
            row["_lat"], row["_lon"] = lat, lon
            row["_name"] = norm(row.get("name_2021", ""))
            cells[(math.floor(lat * 5), math.floor(lon * 5))].append(row)
    return cells


def distance(lat, lon, lat2, lon2):
    a, b, c = math.radians(lat), math.radians(lat2), math.radians(lon2 - lon)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(c / 2) ** 2
    return 12742 * math.asin(min(1, math.sqrt(h)))


def proximity(axis, lat, lon, address):
    """Positive geometric proximity ONLY, not administrative/travel membership."""
    if axis is None:
        return None, None, False
    # Search rectangle covers 10km up to 85N; data beyond85N has no proximity result.
    if abs(lat) > 85:
        return None, None, False
    dlon = 10 / (111 * max(0.08, math.cos(math.radians(lat)))) + 0.01
    candidates = []
    for y in range(math.floor((lat - .1) * 5), math.floor((lat + .1) * 5) + 1):
        for x in range(math.floor((lon - dlon) * 5), math.floor((lon + dlon) * 5) + 1):
            for row in axis.get((y, x), []):
                km = distance(lat, lon, row["_lat"], row["_lon"])
                if km <= 10:
                    candidates.append((km, row))
    if not candidates:
        return None, None, False
    candidates.sort(key=lambda x: x[0])
    km, row = candidates[0]
    text = " " + norm(address) + " "
    named = bool(row["_name"]) and (" " + row["_name"] + " ") in text
    return row, km, named


def summarize(raw, run_id, output, axis):
    fs = features(raw)
    country = collections.Counter()
    fields = collections.Counter()
    rows = []
    ids = collections.Counter()
    points_by_id = {}
    proxy = {r: set() for r in (1, 5, 10)}
    named = set()
    regions = collections.Counter()
    missing_ref = invalid_coord = ru = 0
    for feature in fs:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        for k, value in props.items():
            if value not in (None, "", [], {}):
                fields[k] += 1
        cc = str(props.get("addr:country") or props.get("country") or "").upper()
        country[cc or "UNKNOWN"] += 1
        ref = str(props.get("ref") or "")
        if not ref:
            missing_ref += 1
        coords = geometry.get("coordinates")
        try:
            lon, lat = float(coords[0]), float(coords[1])
            if geometry.get("type") != "Point" or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("coordinate")
        except (TypeError, ValueError, IndexError):
            invalid_coord += 1
            continue
        address = str(props.get("addr:full") or props.get("addr_full") or props.get("address") or "")
        city = str(props.get("addr:city") or props.get("city") or "")
        nearest, km, name_match = (None, None, False)
        if cc in ("RU", "RUS", "RUSSIA", "РОССИЯ"):
            ru += 1
            nearest, km, name_match = proximity(axis, lat, lon, address + " " + city)
            if nearest:
                sid = nearest.get("source_record_id_2021", "")
                for radius in proxy:
                    if km <= radius:
                        proxy[radius].add(sid)
                if name_match:
                    named.add(sid)
                regions[nearest.get("region_2021", "")] += 1
        identity = cc + ":" + ref if ref else ""
        if identity:
            ids[identity] += 1
            points_by_id[identity] = (lat, lon)
        rows.append({"run_id": run_id, "source_ref": ref, "country_reported": cc,
                     "longitude": lon, "latitude": lat, "address_full": address,
                     "city_reported": city, "name": str(props.get("name") or ""),
                     "nearest_axis_id_within10km": nearest.get("source_record_id_2021", "") if nearest else "",
                     "nearest_distance_km": round(km, 5) if km is not None else "",
                     "nearest_name_in_address": int(name_match)})
    if rows:
        with (output / (run_id + "_points.csv")).open("w", encoding="utf8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        "run_id": run_id, "features_all_countries": len(fs),
        "country_counts_reported_by_ATP": dict(country),
        "ru_reported_valid_coordinates": ru, "invalid_or_nonpoint_coordinates": invalid_coord,
        "missing_source_ref": missing_ref, "duplicate_country_ref_keys": sum(v > 1 for v in ids.values()),
        "nonempty_property_counts": dict(fields),
        "axis_status": "geometric_proximity_only" if axis is not None else "blocked_no_axis_csv",
        "positive_nearest_axis_within_km": {str(r): len(v) for r, v in proxy.items()} if axis is not None else None,
        "nearest_axis_name_present_in_address_within10km": len(named) if axis is not None else None,
        "nearest_axis_region_point_counts_within10km": dict(regions) if axis is not None else None,
        "raw_sha256": sha(raw),
        "warning": "Country may be ATP reverse-geocoded. Proximity is not settlement membership, opening, closure, service function or travel catchment."
    }
    # Duplicated IDs are excluded from longitudinal identity comparisons.
    stable = {k: v for k, v in points_by_id.items() if ids[k] == 1}
    return summary, stable



def extract_spider_stats(obj):
    """Locate only an explicitly named Wildberries entry, without guessing counts."""
    if isinstance(obj, dict):
        if "wildberries" in obj and isinstance(obj["wildberries"], dict):
            return obj["wildberries"]
        if str(obj.get("spider", obj.get("name", ""))).casefold() == "wildberries":
            return obj
        for key in ("results", "spiders", "stats", "data"):
            if key in obj:
                found = extract_spider_stats(obj[key])
                if found is not None:
                    return found
    elif isinstance(obj, list):
        for item in obj:
            found = extract_spider_stats(item)
            if found is not None:
                return found
    return None


def run(args):
    output = pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    fetch = Fetcher(output, args.network_seconds, args.ca_file)
    report = {"version": VERSION, "retrieved_at": stamp(), "status": "blocked",
              "history_attempts": [], "attempts": [], "selected": [],
              "source_code_changes_not_exact_run_pins": CODE_CHANGES,
              "scope": "historical ATP Wildberries observed records; not opening dates or complete platform networks"}
    history = None
    for host in HOSTS:
        url = host + "/runs/history.json"
        try:
            raw, ev = fetch.get(url, 12 * 1024 * 1024)
            parsed = historical_runs(parse_json(raw))
            if not parsed:
                raise ValueError("no historical run IDs in requested interval")
            (output / "history.json").write_bytes(raw)
            report["history"] = {"url": url, "sha256": sha(raw), "bytes": len(raw),
                                 "historical_run_count": len(parsed), "schema": "run metadata"}
            history = parsed
            break
        except Exception as exc:
            report["history_attempts"].append({"url": url, "error": str(exc)})
    stable_outputs = []
    seen = set()
    axis = load_axis(args.axis_csv)
    try:
        if history:
            for target in args.targets.split(","):
                candidates = [r for r in history if r["run_id"][:10] <= target]
                selected = False
                for meta in candidates[:args.candidates_per_target]:
                    rid = meta["run_id"]
                    if rid in seen:
                        report["attempts"].append({"target": target, "run_id": rid, "status": "already_selected"})
                        selected = True
                        break
                    attempt = {"target": target, "run_id": rid, "run_metadata": meta, "stats": [], "raw": []}
                    report["attempts"].append(attempt)
                    stats = None
                    stats_source = None
                    # Follow the publisher's actual run-wide URL before fallback paths.
                    stats_urls = []
                    if meta.get("stats_url"):
                        stats_urls.append((meta["stats_url"], "runwide_metadata_url"))
                    stats_urls += [(h + "/runs/" + rid + "/stats/wildberries.json",
                                    "per_spider_fallback") for h in HOSTS[:2]]
                    for url, kind in stats_urls:
                        try:
                            data, ev = fetch.get(url, 12 * 1024 * 1024)
                            obj = parse_json(data)
                            (output / (rid + "_" + kind + "_stats.json")).write_bytes(data)
                            event = {"url": url, "sha256": sha(data), "status": "parsed", "kind": kind}
                            attempt["stats"].append(event)
                            if kind == "per_spider_fallback":
                                candidate = obj if isinstance(obj, dict) else None
                            else:
                                candidate = extract_spider_stats(obj)
                            event["wildberries_entry"] = candidate
                            if candidate is not None:
                                stats, stats_source = candidate, kind
                                # An empty/missing log is not a verified zero and does not block raw.
                                if any(k in stats for k in ("item_scraped_count", "features", "items")):
                                    break
                        except Exception as exc:
                            attempt["stats"].append({"url": url, "error": str(exc), "kind": kind})
                    count = stats.get("item_scraped_count", stats.get("features", stats.get("items"))) if stats else None
                    attempt["item_scraped_count"] = count
                    # Missing/zero stats cannot block acquisition of independent raw evidence.
                    raw = None
                    for host in HOSTS[:2]:
                        url = host + "/runs/" + rid + "/output/wildberries.geojson"
                        try:
                            data, ev = fetch.get(url, LIMIT)
                            features(data)  # Reject HTML, broken/truncated JSON and unknown formats.
                            raw = data
                            attempt["raw"].append({"url": url, "sha256": sha(data), "status": "parsed"})
                            break
                        except Exception as exc:
                            attempt["raw"].append({"url": url, "error": str(exc)})
                    if raw is None:
                        zipurl = meta.get("output_url", "")
                        if urllib.parse.urlsplit(zipurl).path.endswith(".zip") and rid in urllib.parse.unquote(zipurl):
                            try:
                                remote = RemoteZip(fetch, zipurl)
                                with zipfile.ZipFile(remote) as archive:
                                    matches = [i for i in archive.infolist()
                                               if i.filename.endswith("/wildberries.geojson")
                                               or i.filename == "wildberries.geojson"]
                                    if len(matches) != 1:
                                        raise ValueError("not exactly one WB GeoJSON member")
                                    member = matches[0]
                                    if member.file_size > LIMIT:
                                        raise ValueError("ZIP member exceeds expanded limit")
                                    raw = archive.read(member)
                                    features(raw)
                                    attempt["raw"].append({"url": zipurl, "status": "range_zip_member_parsed",
                                                           "member": member.filename,
                                                           "member_crc32": member.CRC, "sha256_extracted_member": sha(raw),
                                                           "archive_sha256": None, "range_bytes": remote.transferred})
                            except Exception as exc:
                                raw = None
                                attempt["raw"].append({"url": zipurl, "error": str(exc)})
                    if raw is None:
                        attempt["status"] = "no_valid_downloaded_raw"
                        continue
                    rawpath = output / (rid + "_wildberries.geojson")
                    rawpath.write_bytes(raw)
                    summary, stable = summarize(raw, rid, output, axis)
                    stats = stats or {}
                    if summary["features_all_countries"] == 0:
                        attempt["status"] = "downloaded_zero_features_not_physical_absence"
                        continue
                    summary.update({"target": target, "run_metadata": meta,
                                    "stats_item_scraped_count_or_runwide_reported_features": count,
                                    "stats_source_kind": stats_source,
                                    "stats_coverage_caution": "Run-wide aggregate features may replace missing scrape count with zero in publisher code.",
                                    "stats_start_time": stats.get("start_time"),
                                    "stats_finish_time": stats.get("finish_time"),
                                    "stats_finish_reason": stats.get("finish_reason"),
                                    "stats_raw_count_equal": summary["features_all_countries"] == count})
                    report["selected"].append(summary)
                    stable_outputs.append((rid, stable))
                    attempt["status"] = "downloaded_and_profiled"
                    seen.add(rid)
                    selected = True
                    break
                if not selected:
                    report["attempts"].append({"target": target, "status": "no_downloaded_positive_run_within_bounded_candidates"})
        report["identity_comparisons"] = []
        stable_outputs.sort()
        for (left, a), (right, b) in zip(stable_outputs, stable_outputs[1:]):
            common = set(a).intersection(b)
            moved = sum(distance(*a[k], *b[k]) > 1 for k in common)
            report["identity_comparisons"].append({
                "left": left, "right": right, "common_unique_country_ref": len(common),
                "common_coordinates_changed_over1km": moved,
                "left_observed_not_right": len(set(a) - set(b)),
                "right_observed_not_left": len(set(b) - set(a)),
                "warning": "Observed set differences are NOT openings/closures. ID semantic continuity is unproven across API/schema changes."
            })
        if report["selected"]:
            report["status"] = "historical_raw_obtained"
    except Exception as exc:
        report["fatal_partial_error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        report["http_events"] = fetch.events
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        compact = {k: v for k, v in report.items() if k != "http_events"}
        print("ATP_HISTORY_RESULT_BEGIN")
        print(json.dumps(compact, ensure_ascii=False))
        print("ATP_HISTORY_RESULT_END")
        print("ATP_HTTP_EVIDENCE_BEGIN")
        print(json.dumps(fetch.events, ensure_ascii=False))
        print("ATP_HTTP_EVIDENCE_END")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="work/ecommerce_atp_history")
    parser.add_argument("--axis-csv", help="CSV with source_record_id_2021,name_2021,region_2021,accepted_latitude_2021,accepted_longitude_2021")
    parser.add_argument("--targets", default=",".join(TARGETS))
    parser.add_argument("--candidates-per-target", type=int, default=6)
    parser.add_argument("--network-seconds", type=int, default=600)
    parser.add_argument("--ca-file", help="Additional explicitly supplied PEM CA; system roots and TLS verification remain enabled")
    raise SystemExit(run(parser.parse_args()))

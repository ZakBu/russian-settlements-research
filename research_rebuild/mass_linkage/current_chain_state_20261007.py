"""Load the published working graph plus accepted deltas without changing inputs."""
from __future__ import annotations

import hashlib
import math
import unicodedata

import duckdb
import pandas as pd

from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind
from measure_event_aware_path_union_20261005 import EDGES, POINTS, SELECTED, EDGE_DELTAS, POINT_DELTAS


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalize(value):
    if value is None or pd.isna(value):
        return ""
    return " ".join(unicodedata.normalize("NFKC", str(value)).lower().replace("ё", "е").split())


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


class State:
    def __init__(self):
        c = duckdb.connect(config={"threads": 1, "memory_limit": "1GB"})
        columns = "source_record_id,census_year,settlement_name,settlement_type,name_norm,type_norm,region_norm,district_raw,population,population_scope,is_additive_settlement_record,population_value_quality,latitude,longitude,oktmo,okato,source_file,source_path,source_sha256,source_locator"
        self.obs = c.execute("SELECT " + columns + " FROM read_parquet(?)", [str(SELECTED)]).fetchdf()
        if self.obs.source_record_id.isna().any() or self.obs.source_record_id.duplicated().any():
            raise ValueError("Selected source IDs must be nonnull and unique")
        self.by_id = self.obs.set_index("source_record_id", drop=False)
        self.uf = UnionFind(self.obs.source_record_id)
        self.years = {sid: {int(y)} for sid, y in self.obs[["source_record_id", "census_year"]].itertuples(index=False, name=None)}
        edges = c.execute("SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) WHERE relation='same_place' AND decision_status IN (SELECT UNNEST(?))", [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)]).fetchall()
        for a, b in edges:
            self.union(a, b)
        for path, ac, bc in EDGE_DELTAS:
            for a, b in pd.read_csv(path, dtype=str)[[ac, bc]].itertuples(index=False, name=None):
                self.union(a, b)
        self.point_rows = {}
        self.point_alternatives = []
        self.conflicting_point_targets = set()
        point_columns = ["target_source_record_id", "latitude", "longitude", "carrier_latitude", "carrier_longitude", "coordinate_admission_status", "coordinate_source_record_id", "source_sha256", "source_locator", "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind"]
        available = {r[0] for r in c.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(POINTS)]).fetchall()}
        core = c.execute("SELECT " + ",".join(k for k in point_columns if k in available) + " FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))", [str(POINTS), sorted(ACCEPTED_COORDINATE_STATUSES)]).fetchdf()
        for path in [POINTS] + POINT_DELTAS:
            frame = core if path == POINTS else pd.read_csv(path, dtype=str, keep_default_na=False, usecols=lambda k: k in point_columns)
            for row in frame.to_dict("records"):
                if "latitude" not in row:
                    row["latitude"], row["longitude"] = row["carrier_latitude"], row["carrier_longitude"]
                sid = str(row["target_source_record_id"])
                if sid not in self.by_id.index:
                    raise ValueError("Point target is not selected: " + sid)
                row["latitude"], row["longitude"] = float(row["latitude"]), float(row["longitude"])
                if not (-90 <= row["latitude"] <= 90 and -180 <= row["longitude"] <= 180):
                    raise ValueError("Impossible accepted point")
                if sid in self.point_rows:
                    old = self.point_rows[sid]
                    if (old["latitude"], old["longitude"]) != (row["latitude"], row["longitude"]):
                        distance = distance_km((old["latitude"], old["longitude"]), (row["latitude"], row["longitude"]))
                        self.point_alternatives.append({"target_source_record_id": sid, "distance_km": distance, "earlier_ledger": old["point_ledger_path"], "later_ledger": str(path)})
                        if distance > 5:
                            self.conflicting_point_targets.add(sid)
                row["point_ledger_path"] = str(path)
                self.point_rows[sid] = row
        self.obs["root"] = self.obs.source_record_id.map(self.uf.find)
        self.inputs = [SELECTED, EDGES, POINTS] + [p for p, _, _ in EDGE_DELTAS] + POINT_DELTAS
        c.close()

    def union(self, a, b):
        if a not in self.uf.parent or b not in self.uf.parent:
            raise ValueError("Unknown graph vertex")
        a, b = self.uf.find(a), self.uf.find(b)
        if a == b:
            return False
        if self.years[a] & self.years[b]:
            raise ValueError("Repeated census year in same_place component")
        years = self.years[a] | self.years[b]
        self.uf.union(a, b)
        root = self.uf.find(a)
        self.years[root] = years
        self.years.pop(b if root == a else a)
        return True

    def add_deltas(self, edge_paths=(), point_paths=()):
        for path in edge_paths:
            frame = pd.read_csv(path, keep_default_na=False)
            for row in frame.to_dict("records"):
                if row.get("relation", "same_place") != "same_place" or row.get("decision_status") not in ACCEPTED_EDGE_STATUSES:
                    raise ValueError("Extra edge is not accepted same_place")
                self.union(str(row["from_source_record_id"]), str(row["to_source_record_id"]))
            self.inputs.append(path)
        for path in point_paths:
            for row in pd.read_csv(path, keep_default_na=False).to_dict("records"):
                sid = str(row["target_source_record_id"])
                if row.get("coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES or sid not in self.by_id.index:
                    raise ValueError("Extra point lacks selected target or accepted status")
                lat, lon = float(row["latitude"]), float(row["longitude"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("Extra point out of range")
                if sid in self.point_rows and distance_km((lat, lon), (self.point_rows[sid]["latitude"], self.point_rows[sid]["longitude"])) > 5:
                    raise ValueError("Extra point contradicts accepted target")
                row.update(latitude=lat, longitude=lon, point_ledger_path=str(path))
                self.point_rows[sid] = row
            self.inputs.append(path)
        self.obs["root"] = self.obs.source_record_id.map(self.uf.find)

    def reject_point_uses(self, path):
        """Supersede explicit reviewed claims without editing the frozen ledger."""
        for row in pd.read_csv(path, keep_default_na=False).to_dict("records"):
            sid = row["target_source_record_id"]
            if row["rejection_status"] != "reviewed_rejected_coordinate_claim_only":
                raise ValueError("Unsupported point rejection status")
            old = self.point_rows[sid]
            if (old["latitude"], old["longitude"]) != (float(row["old_latitude"]), float(row["old_longitude"])):
                raise ValueError("Rejected claim does not match the active point")
            ledger = row["origin_ledger"]
            if old["point_ledger_path"] != ledger:
                raise ValueError("Rejected claim ledger is not active")
            from pathlib import Path
            if sha(Path(ledger)) != row["origin_ledger_sha256"]:
                raise ValueError("Rejected claim input hash differs")
            self.point_rows.pop(sid)
            self.conflicting_point_targets.discard(sid)
        self.inputs.append(path)

    def metrics(self, extra_point_ids=(), extra_covered_ids=()):
        point_ids = set(self.point_rows) | set(extra_point_ids)
        scoped_ids = set(extra_covered_ids)
        rows = self.obs[self.obs.is_additive_settlement_record.fillna(False) & ~self.obs.region_norm.isin(["москва", "санкт петербург", "севастополь"])].copy()
        rows = rows[~((rows.census_year == 2021) & rows.region_norm.eq("крым"))]
        rows["covered"] = rows.source_record_id.map(lambda sid: (sid in point_ids and self.years[self.uf.find(sid)] == {2002, 2010, 2021}) or sid in scoped_ids)
        result = {}
        for y, d in rows.groupby("census_year"):
            denominator = int(d.population.sum())
            covered = int(d.loc[d.covered, "population"].sum())
            result[str(int(y))] = {"denominator_selected_ordinary_population": denominator, "covered_population": covered, "coverage_percent": 100*covered/denominator, "covered_rows": int(d.covered.sum()), "residual_rows": int((~d.covered).sum()), "gap_to_99_percent": max(0, math.ceil(.99*denominator)-covered)}
        return result

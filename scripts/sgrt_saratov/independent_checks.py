"""Independent directed-road and polygon checks for the Saratov pilot.

Small exact examples use Bellman--Ford relaxation rather than the production
shortest-path call. Polygon checks compare only the same centre: overlap between
different centres is expected and is not a failure.
"""
from __future__ import annotations

import argparse
import heapq
import hashlib
import io
import json
import math
from pathlib import Path


def heap_shortest_path(graph, origin, destination):
    """Independent original-direction heap implementation on the saved CSR."""
    n = graph.shape[0]
    if not 0 <= origin < n or not 0 <= destination < n:
        raise ValueError("Road vertex outside graph")
    known = {int(origin): 0.0}
    heap = [(0.0, int(origin))]
    visited = 0
    while heap:
        distance, node = heapq.heappop(heap)
        if distance != known[node]:
            continue
        visited += 1
        if node == destination:
            return distance, visited
        start, end = int(graph.indptr[node]), int(graph.indptr[node + 1])
        for position in range(start, end):
            next_node, weight = int(graph.indices[position]), float(graph.data[position])
            if weight < 0 or not math.isfinite(weight):
                raise ValueError("Invalid road weight")
            candidate = distance + weight
            if candidate < known.get(next_node, math.inf):
                known[next_node] = candidate
                heapq.heappush(heap, (candidate, next_node))
    return math.inf, visited


def inbound_oracle(n, edges, target, destination_connector=0.0):
    """Minimum cost from each vertex to target, including the destination access."""
    if not 0 <= target < n or not math.isfinite(destination_connector) or destination_connector < 0:
        raise ValueError("Invalid target or destination connector")
    edges = [(int(u), int(v), float(w)) for u, v, w in edges]
    if any(not 0 <= u < n or not 0 <= v < n or not math.isfinite(w) or w < 0 for u, v, w in edges):
        raise ValueError("Edges require valid vertices and finite nonnegative costs")
    distance = [math.inf] * n
    distance[target] = float(destination_connector)
    for _ in range(n - 1):
        changed = False
        for u, v, w in edges:
            candidate = w + distance[v]
            if candidate < distance[u]:
                distance[u] = candidate
                changed = True
        if not changed:
            break
    return distance


def inbound_edge_fraction(head_cost, edge_cost, budget):
    """Reachable fraction from head v back towards tail u on directed u->v.

    None means that the cost of the head is unknown. Infinite means a confirmed
    unreachable head in this graph model, not a missing observation.
    """
    if not math.isfinite(edge_cost) or edge_cost < 0 or not math.isfinite(budget) or budget < 0:
        raise ValueError("Nonnegative finite cost and budget required")
    if head_cost is None or math.isnan(head_cost):
        return None
    if head_cost < 0:
        raise ValueError("Negative arrival cost")
    if math.isinf(head_cost) or head_cost > budget:
        return 0.0
    if edge_cost == 0:
        return 1.0
    return min(1.0, (budget - head_cost) / edge_cost)


def reachable_segment(tail, head, fraction):
    if fraction is None:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError("Fraction outside [0,1]")
    start = tuple(float(head[i] + fraction * (tail[i] - head[i])) for i in range(2))
    return start, tuple(head)


def inbound_polyline_piece(coordinates, fraction):
    """Independent length traversal along an original u->v polyline.

    The fraction is valid for a constant-speed original arc. It is not a license
    to distribute a mixed-speed compressed edge's total time by geometric length.
    """
    if fraction is None:
        return None
    if not 0 <= fraction <= 1 or len(coordinates) < 2:
        raise ValueError("Polyline and a fraction in [0,1] required")
    points = [tuple(map(float, point)) for point in coordinates]
    if any(len(point) != 2 or not all(map(math.isfinite, point)) for point in points):
        raise ValueError("Finite planar coordinates required")
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points[:-1], points[1:])]
    remaining = sum(lengths) * fraction
    reverse_piece = [points[-1]]
    for position in range(len(points) - 2, -1, -1):
        if remaining <= 0:
            break
        a, b, length = points[position], points[position + 1], lengths[position]
        if length <= 0:
            continue
        if remaining >= length:
            reverse_piece.append(a)
            remaining -= length
        else:
            ratio = remaining / length
            reverse_piece.append((b[0] + ratio * (a[0] - b[0]), b[1] + ratio * (a[1] - b[1])))
            break
    return tuple(reversed(reverse_piece))


def polygon_checks(cumulative, bands, *, centre_field="centre_id", minutes_field="minutes", area_tolerance=1.0, measure_area=None):
    """Compare geometries in their delivered coordinates; measure areas separately.

    Geometry objects are supplied by the caller so this function is also useful
    for small exact tests without any national or geographic input.
    """
    from shapely.ops import unary_union
    measure_area = measure_area or (lambda geometry: geometry.area)

    def collect(features):
        result = {}
        for properties, geometry in features:
            key = (str(properties[centre_field]), float(properties[minutes_field]))
            if key in result:
                raise ValueError("Duplicate centre/time polygon")
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError("Nonempty valid polygon required")
            result[key] = geometry
        return result

    cumulative, bands = collect(cumulative), collect(bands)
    if set(cumulative) != set(bands):
        raise ValueError("Cumulative and band centre/time keys differ")
    diagnostics = []
    for centre in sorted({key[0] for key in cumulative}):
        previous = None
        previous_bands = []
        for key in sorted([key for key in cumulative if key[0] == centre], key=lambda key: key[1]):
            geometry, band = cumulative[key], bands[key]
            nonnested = measure_area(previous.difference(geometry)) if previous is not None else 0.0
            expected_band = geometry.difference(previous) if previous is not None else geometry
            band_difference = measure_area(band.symmetric_difference(expected_band))
            overlap = measure_area(band.intersection(unary_union(previous_bands))) if previous_bands else 0.0
            diagnostics.append({"centre_id": centre, "minutes": key[1],
                                "cumulative_area_m2": measure_area(geometry), "band_area_m2": measure_area(band),
                                "nonnested_area_m2": nonnested, "band_difference_area_m2": band_difference,
                                "overlap_previous_bands_m2": overlap,
                                "violation": max(nonnested, band_difference, overlap) > area_tolerance})
            previous, previous_bands = geometry, [*previous_bands, band]
    return diagnostics


def counterexamples():
    from shapely.geometry import LineString, MultiPoint, Point
    from shapely.ops import unary_union

    edges = [(0, 1, 10), (1, 2, 10), (2, 1, 30), (1, 0, 40)]
    costs = inbound_oracle(3, edges, 2, 3)
    fraction = inbound_edge_fraction(costs[1], 10, 18)
    # A right-angle reachable road reaches the opposite bank at its bridge.
    # A hull fills the river between those roads, despite no road there.
    road = unary_union([LineString([(0, 0), (0, 10)]), LineString([(0, 10), (10, 10)])])
    hull = MultiPoint([(0, 0), (0, 10), (10, 10)]).convex_hull
    witness = Point(5, 8)
    return {"schema": "sgrt.saratov.independent_counterexamples.v1",
            "inbound_costs_with_destination_connector": costs,
            "target": 2, "connector_minutes": 3,
            "budget_minutes": 18, "partial_u0_v1_fraction": fraction,
            "partial_u0_v1_segment": reachable_segment((0, 0), (10, 0), fraction),
            "unknown_head_fraction": inbound_edge_fraction(None, 10, 18),
            "hull_river_witness_inside_hull": hull.covers(witness),
            "hull_river_witness_inside_road_corridor": road.buffer(0.1).covers(witness),
            "scope": "Synthetic coordinates, not a measured river or real Russian travel."}


def audit_geojson(cumulative_path, bands_path, *, centre_field, minutes_field, area_tolerance=1.0, precision_grid=1e-7):
    import shapely
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    projection = Transformer.from_crs(4326, 32638, always_xy=True)
    def read(path):
        payload = json.loads(Path(path).read_text())
        if payload.get("type") != "FeatureCollection":
            raise ValueError("FeatureCollection required")
        return [(f["properties"], shape(f["geometry"])) for f in payload["features"]]
    cumulative, bands = read(cumulative_path), read(bands_path)
    measure = lambda geometry: transform(projection.transform, geometry).area
    raw = polygon_checks(cumulative, bands, centre_field=centre_field,
                         minutes_field=minutes_field, area_tolerance=area_tolerance, measure_area=measure)
    if not math.isfinite(precision_grid) or precision_grid < 0:
        raise ValueError("Declared nonnegative coordinate precision required; zero means full floating overlay")
    normalized_cumulative = [(properties, shapely.set_precision(geometry, precision_grid)) for properties, geometry in cumulative] if precision_grid else cumulative
    normalized_bands = [(properties, shapely.set_precision(geometry, precision_grid)) for properties, geometry in bands] if precision_grid else bands
    rows = polygon_checks(normalized_cumulative, normalized_bands, centre_field=centre_field,
                          minutes_field=minutes_field, area_tolerance=area_tolerance, measure_area=measure)
    return {"schema": "sgrt.saratov.geometry_numeric_checks.v1", "area_projection": "EPSG:32638",
            "overlay_coordinates": "delivered EPSG:4326; differences projected only for area",
            "declared_precision_grid_degrees": precision_grid,
            "fixed_precision_restoration_applied": precision_grid > 0,
            "precision_semantics": "Restore the producer's declared fixed precision after GeoJSON loses GEOS precision metadata. Raw floating overlay diagnostics remain below; area tolerance is not enlarged.",
            "raw_float_overlay_rows": raw,
            "raw_float_overlay_violations_at_same_area_tolerance": sum(row["violation"] for row in raw),
            "area_tolerance_m2": area_tolerance, "rows": rows,
            "violations": sum(row["violation"] for row in rows),
            "scope": "Valid polygon arithmetic does not validate off-road access or real journeys."}


def audit_route_pairs(centres_path, graph_directory, times_path=None):
    """Independent original-direction paths between four named real centres."""
    import pandas as pd
    from scipy.sparse import load_npz

    centres = pd.read_csv(centres_path)
    if centres.name.duplicated().any() or centres.source_record_id.duplicated().any():
        raise ValueError("Centre names and identities must be unique for this explicit pair sample")
    parts = [Path(graph_directory)/"graph_npz_parts"/f"part_{i:03d}.bin" for i in range(3)]
    buffer = io.BytesIO()
    digest = hashlib.sha256()
    for part in parts:
        with part.open("rb") as f:
            for chunk in iter(lambda: f.read(4 << 20), b""):
                digest.update(chunk)
                buffer.write(chunk)
    graph_sha = digest.hexdigest()
    if graph_sha != "a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366":
        raise ValueError("Different public graph bytes")
    buffer.seek(0)
    graph = load_npz(buffer)
    del buffer
    index = centres.set_index("name")
    pairs = [("Саратов", "Энгельс"), ("Энгельс", "Саратов"),
             ("Питерка", "Новоузенск"), ("Новоузенск", "Питерка")]
    pairs += [(name, name) for name in centres.name]
    output = []
    times = pd.read_parquet(times_path) if times_path else None
    if times is not None and times.duplicated(["origin_id", "centre_id"]).any():
        raise ValueError("Duplicated production origin/centre pairs")
    for origin_name, destination_name in pairs:
        origin, destination = index.loc[origin_name], index.loc[destination_name]
        if not bool(origin.road_endpoint_accepted) or not bool(destination.road_endpoint_accepted):
            raise ValueError("Selected independent pair has no accepted current road endpoint")
        network, visited = heap_shortest_path(graph, int(origin.road_node_index), int(destination.road_node_index))
        origin_connector, destination_connector = float(origin.snap_km) * 4, float(destination.snap_km) * 4
        total = 0.0 if origin.source_record_id == destination.source_record_id else network + origin_connector + destination_connector
        item = {"origin_name": origin_name, "centre_name": destination_name,
                "origin_id": origin.source_record_id, "centre_id": destination.source_record_id,
                "independent_network_minutes": network if math.isfinite(network) else None,
                "origin_connector_minutes": origin_connector, "destination_connector_minutes": destination_connector,
                "independent_total_minutes": total if math.isfinite(total) else None, "visited_vertices": visited}
        if times is not None:
            actual = times.loc[times.origin_id.eq(origin.source_record_id) & times.centre_id.eq(destination.source_record_id)]
            if len(actual) != 1:
                raise ValueError("Exactly one production pair required")
            cost = actual.iloc[0].time_minutes_total
            if math.isfinite(total) and pd.notna(cost):
                item["total_absolute_difference_minutes"] = abs(float(cost) - total)
            else:
                item["missingness_agrees"] = not math.isfinite(total) and pd.isna(cost)
        output.append(item)
    differences = [item.get("total_absolute_difference_minutes", 0) for item in output]
    return {"schema": "sgrt.saratov.original_direction_heap_checks.v1", "graph_sha256": graph_sha,
            "method": "Python heap relaxation on original CSR; no production loader, reverse search, or production shortest-path function",
            "rows": output, "maximum_total_absolute_difference_minutes": max(differences, default=0),
            "violations": sum(item.get("total_absolute_difference_minutes", 0) > 1e-8 or item.get("missingness_agrees") is False for item in output),
            "scope": "Independent algorithm, same published graph; not independent observation of real travel times."}


def audit_np_coverage(settlements_path, centres_path, times_path, cumulative_path):
    """Describe road-corridor coverage independently of exact NP time classes."""
    import numpy as np
    import pandas as pd
    import shapely
    from pyproj import Transformer
    from shapely.geometry import shape, Point
    from shapely.ops import transform

    settlements, centres, times = pd.read_parquet(settlements_path), pd.read_csv(centres_path), pd.read_parquet(times_path)
    if settlements.source_record_id.isna().any() or settlements.source_record_id.duplicated().any():
        raise ValueError("Settlement identities must be non-null and unique")
    if centres.source_record_id.isna().any() or centres.source_record_id.duplicated().any():
        raise ValueError("Centre identities must be non-null and unique")
    if times.duplicated(["origin_id", "centre_id"]).any():
        raise ValueError("Duplicate model origin/centre pair")
    expected = {(str(o), str(c)) for o in settlements.source_record_id for c in centres.source_record_id}
    actual = set(zip(times.origin_id.astype(str), times.centre_id.astype(str)))
    errors = []
    if expected - actual:
        errors.append(f"Missing settlement/centre pairs: {len(expected - actual)}")
    if actual - expected:
        errors.append(f"Unexpected settlement/centre pairs: {len(actual - expected)}")
    expected_total = times.network_minutes + times.origin_connector_minutes + times.destination_connector_minutes
    self_points = times.origin_id.eq(times.centre_id)
    expected_total = expected_total.where(~self_points, 0.0)
    actual_total = pd.to_numeric(times.time_minutes_total, errors="raise")
    finite_expected = np.isfinite(expected_total)
    finite_actual = np.isfinite(actual_total)
    component_missingness_mismatches = int((finite_expected != finite_actual).sum())
    difference = (expected_total[finite_expected & finite_actual] - actual_total[finite_expected & finite_actual]).abs()
    maximum_component_difference = float(difference.max()) if len(difference) else 0.0
    if component_missingness_mismatches:
        errors.append(f"Component-sum finite/missing mismatches: {component_missingness_mismatches}")
    if maximum_component_difference > 1e-8:
        errors.append(f"Component-sum maximum difference minutes: {maximum_component_difference}")
    classification_mismatches = {}
    for budget in (10, 20, 30, 60):
        column = f"within_{budget}min_exact_cost"
        if column not in times:
            errors.append("Missing exact-cost classification: " + column)
            continue
        expected_flag = actual_total.le(budget).where(finite_actual).astype("boolean")
        actual_flag = times[column].astype("boolean")
        mismatch = (expected_flag.isna() != actual_flag.isna()) | (expected_flag.fillna(False) != actual_flag.fillna(False))
        classification_mismatches[column] = int(mismatch.sum())
        if mismatch.any():
            errors.append(f"Exact-cost flag mismatches {column}: {int(mismatch.sum())}")
    data = json.loads(Path(cumulative_path).read_text())
    projection = Transformer.from_crs(4326, 32638, always_xy=True)
    finite_coordinates = np.isfinite(settlements.lon) & np.isfinite(settlements.lat)
    points = np.empty(len(settlements), dtype=object)
    points[:] = Point()
    positions_with_point = np.flatnonzero(finite_coordinates)
    points[positions_with_point] = shapely.points(settlements.lon.iloc[positions_with_point], settlements.lat.iloc[positions_with_point])
    rows = []
    for feature in data["features"]:
        centre, minutes = str(feature["properties"]["centre_id"]), float(feature["properties"]["minutes"])
        part = times.loc[times.centre_id.astype(str).eq(centre)].set_index("origin_id")
        costs = pd.to_numeric(settlements.source_record_id.map(part.time_minutes_total), errors="raise").to_numpy(dtype=float)
        finite = np.isfinite(costs)
        reachable = finite & (costs <= minutes + 1e-9)
        geometry = shape(feature["geometry"])
        inside = np.asarray(shapely.covers(geometry, points)) & finite_coordinates.to_numpy()
        display_only = inside & finite & ~reachable
        routed_not_drawn = reachable & ~inside
        unknown_inside = inside & ~finite
        witness_rows = []
        for position in np.flatnonzero(display_only)[:5]:
            witness = settlements.iloc[int(position)]
            witness_rows.append({"source_record_id": str(witness.source_record_id), "name": str(witness["name"]),
                                 "exact_minutes": float(costs[position]), "excess_minutes": float(costs[position] - minutes)})
        missing_distances = []
        projected_geometry = transform(projection.transform, geometry)
        for position in np.flatnonzero(routed_not_drawn):
            if finite_coordinates.iloc[int(position)]:
                projected_point = transform(projection.transform, points[position])
                missing_distances.append(float(projected_geometry.distance(projected_point)))
        rows.append({"centre_id": centre, "minutes": minutes, "settlement_records": len(settlements),
                     "records_without_finite_coordinates": int((~finite_coordinates).sum()),
                     "finite_time_records": int(finite.sum()), "unknown_or_infinite_time_records": int((~finite).sum()),
                     "unknown_time_status_counts": part.loc[part.index.isin(settlements.source_record_id[~finite]), "status"].value_counts().to_dict() if "status" in part else {},
                     "exact_time_reachable_records": int(reachable.sum()), "inside_display_polygon_records": int(inside.sum()),
                     "finite_time_inside_but_above_budget": int(display_only.sum()),
                     "exact_time_reachable_outside_display": int(routed_not_drawn.sum()),
                     "unknown_time_inside_display": int(unknown_inside.sum()),
                     "maximum_known_excess_inside_display_minutes": float((costs[display_only] - minutes).max()) if display_only.any() else 0.0,
                     "maximum_distance_of_reachable_point_outside_display_m": max(missing_distances, default=0.0),
                     "inside_but_above_budget_examples": witness_rows})
    return {"schema": "sgrt.saratov.np_display_comparison.v1", "rows": rows,
            "expected_np_time_rows": len(expected), "actual_np_time_rows": len(times),
            "component_missingness_mismatches": component_missingness_mismatches,
            "maximum_component_sum_difference_minutes": maximum_component_difference,
            "exact_cost_classification_mismatches": classification_mismatches,
            "errors": errors, "violations": len(errors),
            "scope": "Descriptive comparison: a cartographic road buffer is not a literal complete isochrone surface. Display/time mismatches are retained, not corrected by changing travel times."}


def audit_native_polylines(edges_path, ways_path, nodes_path):
    """Check every delivered road shape against ordered original OSM vertices.

    This does not call the production compression or length helper. A chord
    joining the correct endpoints fails whenever original bends were omitted.
    """
    import pandas as pd
    import shapely

    edges = pd.read_parquet(edges_path)
    ways = pd.read_parquet(ways_path)
    nodes = pd.read_parquet(nodes_path)
    if ways.way_id.duplicated().any() or nodes.osm_id.duplicated().any():
        raise ValueError("Unique original way/node identities required")
    way_index = {int(row.way_id): row for row in ways.itertuples(index=False)}
    positions = {int(row.osm_id): (float(row.lon), float(row.lat)) for row in nodes.itertuples(index=False)}
    errors = []
    maximum_length_error = maximum_cost_error = 0.0
    checked_vertices = curved_segments = 0
    for row in edges.itertuples(index=False):
        source = way_index.get(int(row.way_id))
        geometry = shapely.from_wkb(row.native_geometry_wkb)
        coords = tuple(geometry.coords) if geometry.geom_type == "LineString" else ()
        if source is None or row.geometry_crs != "EPSG:4326" or len(coords) < 2:
            errors.append({"way_id": int(row.way_id), "problem": "Missing source or non-line WGS84 geometry"})
            continue
        refs = list(map(int, source.refs))
        candidates = [refs[i:i + len(coords)] for i, ref in enumerate(refs)
                      if ref == int(row.u_osm) and i + len(coords) <= len(refs)
                      and refs[i + len(coords) - 1] == int(row.v_osm)]
        matched = any(tuple(positions[ref] for ref in candidate) == coords for candidate in candidates)
        if not matched or int(row.source_polyline_vertices) != len(coords):
            errors.append({"way_id": int(row.way_id), "problem": "Geometry is not the complete ordered source slice"})
            continue
        checked_vertices += len(coords)
        curved_segments += int(len(coords) > 2)
        length = 0.0
        for (lon_a, lat_a), (lon_b, lat_b) in zip(coords[:-1], coords[1:]):
            a, b = math.radians(lat_a), math.radians(lat_b)
            half = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon_b - lon_a) / 2) ** 2
            length += 2 * 6371.0088 * math.asin(math.sqrt(max(0.0, min(1.0, half))))
        cost = length / float(source.speed_kmh) * 60
        length_error = abs(length - float(row.native_length_km))
        cost_error = abs(cost - float(row.edge_minutes))
        maximum_length_error = max(maximum_length_error, length_error)
        maximum_cost_error = max(maximum_cost_error, cost_error)
        if length_error > 1e-7 or cost_error > 1e-7 or int(row.oneway) != int(source.oneway) or float(row.speed_kmh) != float(source.speed_kmh):
            errors.append({"way_id": int(row.way_id), "problem": "Original curve length, direction or speed differs"})
    return {"schema": "sgrt.saratov.native_source_shape_checks.v1", "segments_checked": len(edges),
            "source_vertices_checked_with_multiplicity": checked_vertices, "segments_with_intermediate_vertices": curved_segments,
            "maximum_length_difference_km": maximum_length_error, "maximum_cost_difference_minutes": maximum_cost_error,
            "tolerance_km_and_minutes": 1e-7, "violations": len(errors), "examples": errors[:10],
            "scope": "Every native segment is compared with the original ordered source vertices; lengths use an independent scalar spherical calculation, not the production compression or length code."}


def audit_model(model, inputs, graph_directory):
    summary = json.loads((model/"summary.json").read_text())
    if "topology_precision_grid_degrees" not in summary:
        raise ValueError("Model must explicitly declare topology_precision_grid_degrees (zero for full floating overlay)")
    grid = float(summary["topology_precision_grid_degrees"])
    geometry = audit_geojson(model/"isochrones_cumulative.geojson", model/"isochrones_bands.geojson",
                            centre_field="centre_id", minutes_field="minutes", precision_grid=grid)
    routes = audit_route_pairs(inputs/"centres.csv", graph_directory, model/"settlement_travel_times.parquet")
    coverage = audit_np_coverage(inputs/"all_current_settlements.parquet", inputs/"centres.csv",
                                model/"settlement_travel_times.parquet", model/"isochrones_cumulative.geojson")
    native = audit_native_polylines(model/"native_edges.parquet", model.parent/"geometry_recovery/ways.parquet",
                                   model.parent/"geometry_recovery/nodes.parquet")
    errors = []
    if geometry["violations"]:
        errors.append(f"Polygon arithmetic violations: {geometry['violations']}")
    if routes["violations"]:
        errors.append(f"Independent route mismatches: {routes['violations']}")
    errors += coverage["errors"]
    if native["violations"]:
        errors.append(f"Original source shape mismatches: {native['violations']}")
    return {"schema": "sgrt.saratov.independent_numeric.v1", "geometry": geometry,
            "original_direction_routes": routes, "np_polygon_comparison": coverage, "native_source_shapes": native,
            "errors": errors, "violations": len(errors),
            "scope": "Independent arithmetic and displayed geometry checks, not observed trips or completed settlement systems."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cumulative", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--bands", type=Path)
    parser.add_argument("--centre-field", default="centre_id")
    parser.add_argument("--minutes-field", default="minutes")
    parser.add_argument("--area-tolerance", type=float, default=1.0)
    parser.add_argument("--centres", type=Path)
    parser.add_argument("--graph-dir", type=Path)
    parser.add_argument("--np-times", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.cumulative) != bool(args.bands):
        parser.error("Both cumulative and band files are required")
    if args.model:
        if not args.inputs or not args.graph_dir:
            parser.error("--inputs and --graph-dir required with --model")
        result = audit_model(args.model, args.inputs, args.graph_dir)
    elif args.centres:
        if not args.graph_dir:
            parser.error("--graph-dir required with --centres")
        result = audit_route_pairs(args.centres, args.graph_dir, args.np_times)
    else:
        result = audit_geojson(args.cumulative, args.bands, centre_field=args.centre_field,
                              minutes_field=args.minutes_field, area_tolerance=args.area_tolerance) if args.cumulative else counterexamples()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("errors", [] if not result.get("violations", 0) else ["Numeric or geometric discrepancies"])
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "violations": result.get("violations", 0)}))
    if result.get("violations", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

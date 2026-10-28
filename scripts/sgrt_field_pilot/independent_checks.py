"""Small, scalar reference calculations for the settlement-field experiment.

This module deliberately does not import the production field implementation.
Travel times are directed: row i describes access from location i to source j.
None means unmeasured time; positive infinity is allowed ONLY when the caller
has established disconnection in the complete routing graph. Search censoring
must be passed as None instead. No available route is evidence of no service.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence


def kernel_scalar(cost: float, scale: float, family: str) -> float:
    """K_h(t), with h a scale in the same units as t, not a fitted radius."""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be finite and positive")
    if math.isnan(cost) or cost < 0:
        raise ValueError("cost must be nonnegative, not NaN")
    if family == "exponential":
        return math.exp(-cost / scale)
    if family == "gaussian":
        return math.exp(-0.5 * (cost / scale) ** 2)
    raise ValueError("unknown kernel family")


def scalar_potential_bounds(
    times: Sequence[Sequence[float | None]],
    masses: Sequence[float | None],
    scale: float,
    family: str = "exponential",
    include_self: bool = True,
) -> list[dict]:
    """Exact observed sum and conservative bounds for unknown contributions.

    Missing nonnegative mass has no finite upper bound. Missing time with known
    mass has a contribution in [0, mass], as K lies in [0, 1]. Bounds concern
    ONLY the supplied source set, never all settlements outside a pilot window.
    """
    n = len(masses)
    if len(times) != n or any(len(row) != n for row in times):
        raise ValueError("expected a square matrix matching source masses")
    kernel_scalar(0.0, scale, family)
    for mass in masses:
        if mass is not None and (not math.isfinite(mass) or mass < 0):
            raise ValueError("known mass must be finite and nonnegative")
    result = []
    for i, row in enumerate(times):
        observed = []
        upper_extra = []
        unknown_time = 0
        unknown_mass = 0
        disconnected = 0
        for j, (time, mass) in enumerate(zip(row, masses)):
            if i == j and not include_self:
                continue
            if time is not None:
                if math.isnan(time) or time < 0:
                    raise ValueError("unknown time must be None, not NaN/negative")
                if math.isinf(time):
                    disconnected += 1
                    continue
            if mass is None:
                unknown_mass += 1
                upper_extra.append(math.inf)
                continue
            if mass == 0:
                observed.append(0.0)
                continue
            if time is None:
                unknown_time += 1
                upper_extra.append(mass)
            else:
                observed.append(mass * kernel_scalar(time, scale, family))
        lower = math.fsum(observed)
        upper = lower + math.fsum(upper_extra)
        result.append({
            "lower": lower,
            "upper": upper,
            "point_value_known": not unknown_time and not unknown_mass,
            "unknown_time_contributions": unknown_time,
            "unknown_mass_contributions": unknown_mass,
            "confirmed_disconnected_contributions": disconnected,
        })
    return result


def strict_local_peaks(values: Sequence[float], neighbours: Sequence[Sequence[int]]) -> list[int]:
    """Strict singleton peaks; ties are intentionally NOT broken by row order.

    Plateau components must be examined separately; this function cannot assert
    absence of a maximum merely because its strict singleton result is empty.
    The supplied neighbourhood is fixed, and need not equal a kernel bandwidth.
    """
    if len(values) != len(neighbours):
        raise ValueError("neighbourhood length must match values")
    if any(not math.isfinite(x) for x in values):
        raise ValueError("cannot classify peaks of unknown/non-finite potential")
    return [i for i, nb in enumerate(neighbours)
            if nb and all(values[i] > values[j] for j in nb)]


def plateau_maxima(values: Sequence[float], neighbours: Sequence[Sequence[int]]) -> list[list[int]]:
    """Maximal connected EXACT-equality plateaus with no higher boundary node.

    This scalar reference uses exact equality to make the mathematical contract
    transparent. Production floating-point tie tolerances require their own
    documented rule; approximate equality is not a transitive relation.
    Isolated samples are returned as one-node plateaus, not evidence of a centre.
    """
    if len(values) != len(neighbours):
        raise ValueError("neighbourhood length must match values")
    if any(not math.isfinite(x) for x in values):
        raise ValueError("cannot classify peaks of unknown/non-finite potential")
    n = len(values)
    for i, nb in enumerate(neighbours):
        for j in nb:
            if not 0 <= j < n or j == i or i not in neighbours[j]:
                raise ValueError("plateau adjacency must be symmetric and omit self")
    remaining = set(range(n))
    maxima = []
    while remaining:
        seed = min(remaining)
        stack = [seed]
        component = {seed}
        remaining.remove(seed)
        while stack:
            i = stack.pop()
            for j in neighbours[i]:
                if j in remaining and values[j] == values[seed]:
                    remaining.remove(j)
                    component.add(j)
                    stack.append(j)
        boundary = {j for i in component for j in neighbours[i]} - component
        if all(values[seed] > values[j] for j in boundary):
            maxima.append(sorted(component))
    return maxima


def shortest_paths_fixture(n: int, edges: Sequence[Sequence[float]]) -> tuple[list[list[float]], list[list[int]]]:
    """Tiny undirected Floyd–Warshall fixture; not the production routing code."""
    matrix = [[0.0 if i == j else math.inf for j in range(n)] for i in range(n)]
    neighbours = [[] for _ in range(n)]
    for a, b, cost in edges:
        a, b = int(a), int(b)
        matrix[a][b] = matrix[b][a] = float(cost)
        neighbours[a].append(b)
        neighbours[b].append(a)
    for k in range(n):
        for i in range(n):
            for j in range(n):
                matrix[i][j] = min(matrix[i][j], matrix[i][k] + matrix[k][j])
    return matrix, neighbours


def counterexamples() -> dict:
    edges = [[1, 0, 6], [2, 0, 7], [3, 2, 8], [4, 0, 5], [5, 4, 1]]
    masses = [52, 36, 58, 75, 34, 17]
    times, neighbours = shortest_paths_fixture(6, edges)
    scales = []
    for h in (2, 4, 8):
        values = [x["lower"] for x in scalar_potential_bounds(times, masses, h)]
        scales.append({"scale": h, "potential": values,
                       "strict_peak_indices": strict_local_peaks(values, neighbours)})
    plateau = plateau_maxima([3.0, 3.0, 1.0], [[1], [0, 2], [1]])
    unknown = scalar_potential_bounds([[0.0, None], [None, 0.0]], [10, 20], 5)
    # Locations x=(0,1,-1) on a line: omitting the third, external settlement
    # reverses the ordering of the first two locations without moving anyone.
    clipped_values = [x["lower"] for x in scalar_potential_bounds([[0, 1], [1, 0]], [10, 20], 1)]
    expanded_values = [x["lower"] for x in scalar_potential_bounds(
        [[0, 1, 1], [1, 0, 2], [1, 2, 0]], [10, 20, 100], 1)]
    # Same TWO sources, but the evaluation set can include a location with no
    # settlement. Population is not duplicated by adding an evaluation point.
    at_settlements = 1 + math.exp(-0.5 * (2 / 2) ** 2)
    at_midpoint = 2 * math.exp(-0.5 * (1 / 2) ** 2)
    incoming_values = [r["lower"] for r in scalar_potential_bounds(
        [[0, 1, 3], [1, 0, 2], [3, 2, 0]], [1, 2, 4], 1)]
    return {
        "schema": "sgrt.field.scalar.counterexamples.v1",
        "status": "synthetic_method_examples_not_geographic_observations",
        "peak_birth_on_symmetric_tree": {
            "edges": edges, "masses": masses, "kernel": "exp(-t/h)",
            "include_self": True, "neighbourhood": "fixed tree edges",
            "shortest_times": times, "scales": scales,
            "conclusion": "More smoothing does not guarantee fewer sampled local maxima.",
        },
        "equal_plateau": {"values": [3, 3, 1], "maximum_components": plateau},
        "uncomputed_routes": {"masses": [10, 20], "bounds": unknown},
        "external_source_changes_inner_ordering": {
            "locations": [0, 1, -1], "masses": [10, 20, 100], "scale": 1,
            "kernel": "exp(-t/h)", "clipped_source_indices": [0, 1],
            "inner_potential_clipped_sources": clipped_values,
            "inner_potential_all_three_sources": expanded_values[:2],
            "conclusion": "An edge effect can reverse the apparent inner centre.",
        },
        "settlement_sampling_misses_nonsettlement_peak": {
            "source_locations": [-1, 1], "masses": [1, 1], "scale": 2,
            "kernel": "exp(-0.5*(t/h)^2)",
            "at_either_settlement": at_settlements, "at_unpopulated_midpoint": at_midpoint,
            "conclusion": "Values sampled only at settlements do not locate every surface maximum.",
        },
        "outgoing_coverage_does_not_cover_incoming_union_edges": {
            "locations": [0, 1, 3], "masses": [1, 2, 4], "scale": 1,
            "kernel": "exp(-t/h)", "sampled_evaluation_indices": [0, 1], "k": 1,
            "global_outgoing_nearest_neighbors": [[1], [0], [1]],
            "sampled_union_edges": [[0, 1]], "global_union_edges": [[0, 1], [1, 2]],
            "potential_from_all_three_sources": incoming_values,
            "sampled_peak_indices": strict_local_peaks(incoming_values[:2], [[1], [0]]),
            "global_union_peak_indices": strict_local_peaks(incoming_values, [[1], [0, 2], [1]]),
            "conclusion": "All outgoing neighbors of sampled points can lie inside the window while an untested incoming union edge removes a sampled maximum.",
        },
    }


def audit_pilot_output(directory: Path, inputs: Path | None = None) -> dict:
    """Recompute every supplied field value and sampled peak from saved routes.

    Pandas is used only for I/O/grouping. Contributions use math.fsum and scalar
    math.exp, rather than the author's vectorized kernel/dot/peak code. This
    verifies arithmetic and comparison logic, not the truth of the road model.
    """
    import pandas as pd

    directory = Path(directory)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    routes = pd.read_parquet(directory / "routed_contributions.parquet")
    fields = pd.read_parquet(directory / "fields.parquet")
    peaks = pd.read_parquet(directory / "peaks.parquet")
    edges = pd.read_parquet(directory / "comparison_edges.parquet")
    sources = pd.read_parquet(directory / "national_mass_sources.parquet")
    costs = pd.read_parquet(directory / "evaluation_costs.parquet")
    field_key = ["source_record_id", "pilot_id", "kernel", "half_time_minutes", "include_self"]
    peak_key = field_key + ["neighbor_count"]
    errors = []
    if routes.duplicated(["origin_id", "source_id"]).any():
        errors.append("Repeated origin/source contributions")
    if fields.duplicated(field_key).any():
        errors.append("Repeated field rows")
    if peaks.duplicated(peak_key).any():
        errors.append("Repeated peak classifications")
    mass_column = "source_mass_2021"
    stock = dict(zip(sources.source_record_id, sources[mass_column]))
    if len(stock) != len(sources):
        errors.append("Duplicate national mass source identities")
    total = math.fsum(float(x) for x in stock.values())
    cutoff = summary["search_cutoff_minutes"]
    unmapped = summary["known_positive_mass_without_accepted_endpoint"]
    max_population_difference = 0.0
    max_connector_difference = 0.0
    has_connector_columns = {"network_minutes", "connector_minutes"}.issubset(routes.columns)
    for r in routes.itertuples(index=False):
        if r.source_id not in stock:
            errors.append("Route source absent from national inventory")
            continue
        max_population_difference = max(max_population_difference, abs(float(stock[r.source_id]) - r.source_population_2021))
        if has_connector_columns:
            max_connector_difference = max(max_connector_difference, abs(r.network_minutes + r.connector_minutes - r.cost_minutes))
        if not (0 <= r.cost_minutes <= cutoff) or not math.isfinite(r.cost_minutes):
            errors.append("Invalid saved finite route cost")
    if max_population_difference != 0:
        errors.append("Contribution population differs from source ledger")
    if max_connector_difference > 1e-6:
        errors.append("Network plus connector minutes differ from saved total")
    grouped = {k: list(v.itertuples(index=False)) for k, v in routes.groupby("origin_id", sort=False)}
    omitted_groups = None
    omitted_ledger = None
    if (directory / "omitted_published_sources.parquet").exists():
        omitted = pd.read_parquet(directory / "omitted_published_sources.parquet")
        omitted_routes = pd.read_parquet(directory / "omitted_routed_contributions.parquet")
        omitted_stock = dict(zip(omitted.source_record_id, omitted.published_raw_population_2021))
        if len(omitted_stock) != len(omitted) or set(omitted_stock) & set(stock):
            errors.append("Omitted published sensitivity sources duplicate accepted weights or identities")
        if omitted_routes.duplicated(["origin_id", "source_id"]).any():
            errors.append("Repeated origin/source omitted sensitivity contributions")
        for r in omitted_routes.itertuples(index=False):
            if r.source_id not in omitted_stock or r.published_raw_population_2021 != omitted_stock[r.source_id]:
                errors.append("Omitted sensitivity route weight differs from its raw ledger")
            if not (0 <= r.cost_minutes <= cutoff) or not math.isfinite(r.cost_minutes):
                errors.append("Invalid omitted sensitivity finite route cost")
            if r.source_id == r.origin_id and r.cost_minutes != 0:
                errors.append("Omitted source has nonzero own cost")
        omitted_routable = omitted.loc[omitted.accepted_source_endpoint.eq(True), "published_raw_population_2021"]
        omitted_unmapped = math.fsum(omitted.loc[~omitted.accepted_source_endpoint.eq(True), "published_raw_population_2021"])
        omitted_total_routable = math.fsum(omitted_routable)
        omitted_total = math.fsum(omitted_stock.values())
        omitted_groups = {k: list(v.itertuples(index=False)) for k, v in omitted_routes.groupby("origin_id", sort=False)}
        if inputs is not None:
            input_summary = json.loads((Path(inputs) / "input_summary.json").read_text())
            envelope = input_summary["population_accounting"]["conservative_excluded_published_raw_sum_upper_bound_may_double_count"]
            if omitted_total != envelope:
                errors.append("Omitted source raw sum differs from independent input accounting")
        omitted_ledger = {"positive_raw_source_rows": len(omitted), "routed_contribution_rows": len(omitted_routes),
                          "raw_population_sum_not_added_to_base": omitted_total,
                          "raw_population_with_accepted_endpoints": omitted_total_routable,
                          "raw_population_without_accepted_endpoints": omitted_unmapped,
                          "scope": "Published-reference upper sensitivity with possible double count, not an additive population total."}
    scalar_values = {}
    scalar_uppers = {}
    scalar_published_uppers = {}
    max_value_difference = 0.0
    max_tail_difference = 0.0
    max_known_upper_difference = 0.0
    max_published_reference_upper_difference = 0.0
    for row in fields.itertuples(index=False):
        contributions = grouped.get(row.source_record_id, [])
        # Convert the producer's half-value scale to the independent kernel's h.
        half = float(row.half_time_minutes)
        scale = half / (math.log(2) if row.kernel == "exponential" else math.sqrt(2 * math.log(2)))
        terms = []
        for r in contributions:
            if row.include_self or r.source_id != row.source_record_id:
                terms.append(float(r.source_population_2021) * kernel_scalar(float(r.cost_minutes), scale, row.kernel))
            if r.source_id == row.source_record_id and r.cost_minutes != 0:
                errors.append("Own source cost is not zero")
        value = math.fsum(terms)
        known_mass = math.fsum(float(r.source_population_2021) for r in contributions)
        tail = (total - known_mass) * kernel_scalar(cutoff, scale, row.kernel)
        upper = value + tail + unmapped
        delta = abs(value - row.known_routed_potential)
        max_value_difference = max(max_value_difference, delta)
        max_tail_difference = max(max_tail_difference, abs(tail - row.censored_routed_mass_potential_upper))
        max_known_upper_difference = max(max_known_upper_difference, abs(upper - row.known_mass_potential_upper))
        if not math.isclose(value, row.known_routed_potential, abs_tol=1e-7, rel_tol=1e-12):
            errors.append("Scalar field differs from saved potential")
        if not math.isclose(tail, row.censored_routed_mass_potential_upper, abs_tol=1e-7, rel_tol=1e-12):
            errors.append("Independent cutoff tail differs")
        if not math.isclose(upper, row.known_mass_potential_upper, abs_tol=1e-7, rel_tol=1e-12):
            errors.append("Independent known-mass upper bound differs")
        if omitted_groups is not None:
            aux = omitted_groups.get(row.source_record_id, [])
            aux_value = math.fsum(float(r.published_raw_population_2021) * kernel_scalar(float(r.cost_minutes), scale, row.kernel)
                                  for r in aux if row.include_self or r.source_id != row.source_record_id)
            aux_reached_mass = math.fsum(float(r.published_raw_population_2021) for r in aux)
            aux_tail = (omitted_total_routable - aux_reached_mass) * kernel_scalar(cutoff, scale, row.kernel)
            for expected, observed in [(aux_value, row.omitted_published_routed_potential_upper),
                                       (aux_tail, row.omitted_published_censored_potential_upper),
                                       (omitted_unmapped, row.omitted_published_unmapped_potential_upper)]:
                if not math.isclose(expected, observed, abs_tol=1e-7, rel_tol=1e-12):
                    errors.append("Independent omitted-published sensitivity contribution differs")
            published_upper = upper + aux_value + aux_tail + omitted_unmapped
            max_published_reference_upper_difference = max(max_published_reference_upper_difference,
                                                          abs(published_upper - row.published_reference_potential_upper))
            if not math.isclose(published_upper, row.published_reference_potential_upper, abs_tol=1e-7, rel_tol=1e-12):
                errors.append("Independent published-reference upper sensitivity differs")
        key = (row.source_record_id, row.pilot_id, row.kernel, row.half_time_minutes, row.include_self)
        scalar_values[key] = value
        scalar_uppers[key] = upper
        if omitted_groups is not None:
            scalar_published_uppers[key] = published_upper
    if fields.complete_population_field_upper.notna().any():
        errors.append("Complete national field was incorrectly assigned a finite upper bound")
    if peaks.is_certified_complete_field_peak.any():
        errors.append("Complete population-field peak was certified despite excluded source records")
    peak_disagreements = 0
    compared_peak_rows = 0
    approximate_equal_edges = 0
    peak_counts = []
    known_mass_robustness_disagreements = 0
    published_envelope_robustness_disagreements = 0
    for keys, g in peaks.groupby(["pilot_id", "kernel", "half_time_minutes", "include_self", "neighbor_count"], sort=False):
        ids = sorted(g.source_record_id)
        position = {s: i for i, s in enumerate(ids)}
        values = [scalar_values[(s, keys[0], keys[1], keys[2], keys[3])] for s in ids]
        adjacent = [set() for _ in ids]
        e = edges.loc[edges.pilot_id.eq(keys[0]) & edges.neighbor_count.eq(keys[4])]
        for r in e.itertuples(index=False):
            a, b = position[r.source_id_a], position[r.source_id_b]
            adjacent[a].add(b)
            adjacent[b].add(a)
            if values[a] != values[b] and math.isclose(values[a], values[b], abs_tol=1e-9, rel_tol=1e-12):
                approximate_equal_edges += 1
        components = plateau_maxima(values, adjacent)
        maxima = {ids[i] for component in components for i in component if adjacent[i]}
        reported = set(g.loc[g.is_sampled_local_maximum, "source_record_id"])
        peak_disagreements += len(maxima ^ reported)
        compared_peak_rows += len(g)
        peak_counts.append({"pilot_id": keys[0], "kernel": keys[1], "half_time_minutes": float(keys[2]),
                            "include_self": bool(keys[3]), "neighbor_count": int(keys[4]),
                            "scalar_peak_points": len(maxima), "reported_peak_points": len(reported)})
        for r in g.itertuples(index=False):
            i = position[r.source_record_id]
            expected_known = (r.source_record_id in maxima and all(values[i] > scalar_uppers[(ids[j], *keys[:4])] + 1e-9
                                                                    for j in adjacent[i]))
            if hasattr(r, "peak_robust_to_known_mass_tail_and_unmapped"):
                known_mass_robustness_disagreements += int(bool(r.peak_robust_to_known_mass_tail_and_unmapped) != expected_known)
            if omitted_groups is not None and hasattr(r, "peak_robust_to_published_reference_envelope"):
                expected_published = (r.source_record_id in maxima and all(values[i] > scalar_published_uppers[(ids[j], *keys[:4])] + 1e-9
                                                                            for j in adjacent[i]))
                published_envelope_robustness_disagreements += int(bool(r.peak_robust_to_published_reference_envelope) != expected_published)
    if peak_disagreements and approximate_equal_edges == 0:
        errors.append("Scalar exact peak classifications differ without tolerance ties")
    if known_mass_robustness_disagreements:
        errors.append("Independent known-mass robustness classification differs")
    if published_envelope_robustness_disagreements:
        errors.append("Independent published-reference robustness classification differs")
    directed_pairs = costs.pivot(index="origin_id", columns="destination_id", values="cost_minutes")
    both = directed_pairs.notna() & directed_pairs.T.notna()
    asymmetric = both & (directed_pairs - directed_pairs.T).abs().gt(1e-6)
    boundary = []
    input_ledger = None
    if inputs is not None:
        evaluation = pd.read_csv(Path(inputs) / "evaluation.csv")
        inventory = pd.read_parquet(Path(inputs) / "sourceweights.parquet")
        eligible = (inventory.credit_2021.eq(True) & inventory.budget_population_credit.eq(True)
                    & inventory.ordinary_spatial_2021.eq(True) & inventory.population_2021.gt(0)
                    & inventory.routable.eq(True))
        expected = inventory.loc[eligible].set_index("source_record_id").population_2021.to_dict()
        missing_expected = set(expected) - set(stock)
        unexpected = set(stock) - set(expected)
        changed_mass = [s for s in set(expected) & set(stock) if expected[s] != stock[s]]
        if missing_expected or unexpected or changed_mass:
            errors.append("Model source weights differ from independently prepared credited endpoint inventory")
        input_ledger = {"expected_routed_positive_source_records": len(expected),
                        "missing_expected_source_records": len(missing_expected),
                        "unexpected_model_source_records": len(unexpected),
                        "changed_source_population_records": len(changed_mass),
                        "expected_routed_positive_population": math.fsum(expected.values()),
                        "evaluated_published_zero_population_records": int(evaluation.population_2021.eq(0).sum()),
                        "evaluated_credited_zero_population_records": int((evaluation.population_2021.eq(0)
                            & evaluation.credit_2021.eq(True) & evaluation.budget_population_credit.eq(True)).sum())}
        pilot_col = "pilot_id" if "pilot_id" in evaluation else "pilot"
        comparison_by_origin = {origin: list(zip(g.destination_id, g.cost_minutes))
                                for origin, g in costs.groupby("origin_id", sort=False)}
        for pilot, g in evaluation.groupby(pilot_col, sort=True):
            local = set(g.source_record_id)
            core = dict(zip(g.source_record_id, g.evaluation_core))
            for k in sorted(peaks.neighbor_count.unique()):
                row_counts = {"core": {"evaluations": 0, "known_closer_outside_positive_sources": 0,
                                      "fewer_than_k_local_routes": 0},
                              "outer": {"evaluations": 0, "known_closer_outside_positive_sources": 0,
                                       "fewer_than_k_local_routes": 0}}
                for origin in sorted(local):
                    category = "core" if core[origin] else "outer"
                    target = row_counts[category]
                    target["evaluations"] += 1
                    comp = sorted(cost for destination, cost in comparison_by_origin.get(origin, [])
                                  if destination in local and destination != origin and math.isfinite(cost))
                    if len(comp) < k:
                        target["fewer_than_k_local_routes"] += 1
                    if not len(comp):
                        continue
                    threshold = comp[min(int(k), len(comp)) - 1]
                    missing = [r for r in grouped.get(origin, [])
                               if r.source_id not in local and r.cost_minutes <= threshold + 1e-10]
                    if missing:
                        target["known_closer_outside_positive_sources"] += 1
                boundary.append({"pilot_id": pilot, "neighbor_count": int(k), **row_counts,
                                 "scope": "Known credited positive sources only; zero/uncredited outside records are not certified absent."})
    return {
        "schema": "sgrt.field.scalar.audit.v1",
        "method": "independent scalar exp/fsum and connected exact-equality plateau comparison; no production imports",
        "routed_contribution_rows": len(routes), "field_rows_recomputed": len(fields),
        "peak_rows_compared": compared_peak_rows, "peak_classification_disagreements": peak_disagreements,
        "approximate_equal_comparison_edges": approximate_equal_edges,
        "known_mass_robustness_disagreements": known_mass_robustness_disagreements,
        "published_reference_robustness_disagreements": published_envelope_robustness_disagreements,
        "maximum_field_absolute_difference": max_value_difference,
        "maximum_tail_absolute_difference": max_tail_difference,
        "maximum_known_mass_upper_absolute_difference": max_known_upper_difference,
        "maximum_published_reference_upper_absolute_difference": max_published_reference_upper_difference if omitted_groups is not None else None,
        "maximum_population_difference": max_population_difference,
        "connector_columns_available": has_connector_columns,
        "maximum_connector_arithmetic_difference_minutes": max_connector_difference if has_connector_columns else None,
        "finite_directional_pairs_with_different_reverse_cost": int(asymmetric.to_numpy().sum()),
        "full_population_peak_certification_count": int(peaks.is_certified_complete_field_peak.sum()),
        "independent_peak_counts": peak_counts,
        "input_source_ledger_comparison": input_ledger,
        "omitted_published_sensitivity_ledger": omitted_ledger,
        "evaluation_neighborhood_boundary_checks": boundary,
        "errors": sorted(set(errors)),
        "scope": "Arithmetic from saved routes, not independent validation of travel times, journeys, or service boundaries.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", "--pilot-directory", dest="pilot_directory", type=Path)
    parser.add_argument("--inputs", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = audit_pilot_output(args.pilot_directory, args.inputs) if args.pilot_directory else counterexamples()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "synthetic": args.pilot_directory is None,
                      "errors": result.get("errors", [])}))
    if result.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

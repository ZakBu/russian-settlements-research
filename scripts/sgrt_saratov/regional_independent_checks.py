"""Independent numerical checks for Saratov's regional functional-field study.

The scalar oracles below deliberately do not import the production regional
field or functional algorithms.  They test arithmetic and graph conventions;
they do not turn a modelled route or an institution record into observed trips.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import heapq
import io
import json
import math
from pathlib import Path

GRAPH_SHA256 = "a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366"

# Explicit service definitions are checked against the frozen input records;
# no production normalizer, prepared provider list or source cache identity is
# used to derive the expected inventory.
SERVICE_FAMILIES = {
    "school_general": "school", "preschool": "preschool",
    "vocational_education": "vocational_education", "higher_education": "higher_education",
    "medical_basic_primary": "medical_basic", "medical_physician_primary": "medical_physician",
    "medical_inpatient": "medical_hospital", "medical_specialized": "medical_specialized",
    "medical_hightech_licensed": "medical_hightech", "daily_grocery": "grocery",
    "daily_grocery_current_retail_host": "grocery", "daily_food_specialist": "food_specialist",
    "comparison_retail": "comparison_retail", "shopping_centre": "shopping_centre",
    "parcel_pickup": "parcel_pickup", "marketplace_unspecified_assortment": "marketplace_unspecified_assortment",
    "postal_service": "postal_service",
}


def all_pairs_relaxation(node_count, edges):
    """Small-fixture shortest paths by relaxation, independently of SciPy."""
    distances = [[math.inf] * node_count for _ in range(node_count)]
    for i in range(node_count):
        distances[i][i] = 0.0
    for u, v, cost in edges:
        if not (0 <= u < node_count and 0 <= v < node_count):
            raise ValueError("Invalid directed vertex")
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("Nonnegative finite road costs required")
        distances[u][v] = min(distances[u][v], float(cost))
    for k in range(node_count):
        for i in range(node_count):
            for j in range(node_count):
                distances[i][j] = min(distances[i][j], distances[i][k] + distances[k][j])
    return distances


def forward_union_fixture(node_count, edges, origins, horizon):
    """Check that a forward union retains every original path within horizon."""
    if not origins or not math.isfinite(horizon) or horizon < 0:
        raise ValueError("Origins and finite nonnegative horizon required")
    original = all_pairs_relaxation(node_count, edges)
    keep = [v for v in range(node_count) if min(original[o][v] for o in origins) <= horizon]
    remap = {v: i for i, v in enumerate(keep)}
    retained = [(remap[u], remap[v], w) for u, v, w in edges if u in remap and v in remap]
    restricted = all_pairs_relaxation(len(keep), retained)
    comparisons = []
    for origin in origins:
        for target in range(node_count):
            before = original[origin][target]
            after = restricted[remap[origin]][remap[target]] if target in remap else math.inf
            if before <= horizon:
                comparisons.append((origin, target, before, after))
                if before != after:
                    raise ValueError("The bounded forward union lost a valid path")
    return {"retained_nodes": keep, "pairs_within_horizon_compared": comparisons}


def connected_cost(network_cost, origin_connector, destination_connector, *, same_record=False):
    if same_record:
        return 0.0
    if network_cost is None or math.isnan(network_cost):
        return None
    if any(not math.isfinite(x) or x < 0 for x in (origin_connector, destination_connector)):
        raise ValueError("Finite nonnegative connectors required")
    return network_cost + origin_connector + destination_connector


def sparse_known_cost(indices, values, destination):
    """Missing sparse entry is unknown/censored, never an implicit zero cost."""
    known = {int(index): float(value) for index, value in zip(indices, values)}
    return known.get(int(destination))


def kernel_scalar(cost, half_time, family):
    if not math.isfinite(half_time) or half_time <= 0:
        raise ValueError("Positive finite half-time required")
    if cost is None or math.isnan(cost):
        return None
    if cost < 0:
        raise ValueError("Negative transport cost")
    if family in {"exp", "exponential"}:
        exponent = -cost / half_time
    elif family in {"gauss", "gaussian"}:
        exponent = -(cost / half_time) ** 2
    else:
        raise ValueError("Unknown kernel family")
    return 2.0 ** exponent


def scalar_fields(known_costs, masses, half_time, family, *, self_index=None,
                  horizon=480.0, travel_lower_bounds=None):
    """Independent fsum over stored costs and monotone conservative tails.

    masses must contain ONLY the independently accepted original masses.  A
    missing numeric mass is not converted to an observed zero: its uncertainty
    must be reported separately by the caller, outside these known-mass bounds.
    """
    if horizon < 0 or not math.isfinite(horizon):
        raise ValueError("Finite nonnegative computation horizon required")
    contributions = []
    omitted_bounds = []
    own = 0.0
    for j, population in enumerate(masses):
        if population is None or not math.isfinite(population) or population < 0:
            raise ValueError("Supply accepted finite nonnegative original masses")
        cost = known_costs.get(j)
        if cost is not None:
            if not math.isfinite(cost) or cost < 0 or cost > horizon + 1e-7:
                raise ValueError("Stored finite routes must be within computation horizon")
            part = population * kernel_scalar(cost, half_time, family)
            contributions.append(part)
            if j == self_index:
                own = part
        else:
            lower_bound = horizon
            if travel_lower_bounds is not None:
                lower_bound = max(lower_bound, travel_lower_bounds[j])
            omitted_bounds.append(population * kernel_scalar(lower_bound, half_time, family))
    lower = math.fsum(contributions)
    return {"with_self": lower, "without_self": lower - own,
            "self_contribution": own, "routable_tail_upper": math.fsum(omitted_bounds)}


def nearest_compatible(known_costs, compatible, *, own_site=None, tie_tolerance=1e-8):
    """A basic-service oracle: multiplicity/population cannot win over proximity."""
    candidates = [(float(cost), identity) for identity, cost in known_costs.items()
                  if identity in compatible and cost is not None and math.isfinite(cost) and cost >= 0]
    if own_site is not None and own_site in compatible:
        candidates.append((0.0, own_site))
    if not candidates:
        return {"primary": None, "tied": [], "status": "no_compatible_known_route"}
    minimum = min(cost for cost, _ in candidates)
    tied = sorted({identity for cost, identity in candidates if abs(cost - minimum) <= tie_tolerance})
    return {"primary": tied[0], "tied": tied, "cost": minimum,
            "status": "modelled_nearest_known_provider"}


def direct_members(costs_to_centre, maximum_cost):
    """A connected chain cannot substitute for each member's direct eligibility."""
    return [i for i, cost in enumerate(costs_to_centre)
            if cost is not None and math.isfinite(cost) and cost <= maximum_cost]


def heap_shortest(graph, origin, destination, maximum=math.inf):
    """Original directed CSR with a heap; no production shortest-path helper."""
    best = {int(origin): 0.0}
    queue = [(0.0, int(origin))]
    popped = 0
    while queue:
        cost, vertex = heapq.heappop(queue)
        if cost != best[vertex]:
            continue
        if cost > maximum:
            break
        popped += 1
        if vertex == destination:
            return cost, popped
        for at in range(int(graph.indptr[vertex]), int(graph.indptr[vertex + 1])):
            target, weight = int(graph.indices[at]), float(graph.data[at])
            if not math.isfinite(weight) or weight < 0:
                raise ValueError("Invalid original graph cost")
            proposal = cost + weight
            if proposal < best.get(target, math.inf) and proposal <= maximum:
                best[target] = proposal
                heapq.heappush(queue, (proposal, target))
    return math.inf, popped


def original_graph(graph_dir):
    """Read the exact original national CSR without the regional loader."""
    from scipy.sparse import load_npz
    stream = io.BytesIO()
    digest = hashlib.sha256()
    parts = sorted((Path(graph_dir) / "graph_npz_parts").glob("part_*.bin"))
    if not parts:
        raise ValueError("Original graph parts are missing")
    for path in parts:
        with path.open("rb") as handle:
            while block := handle.read(4 << 20):
                digest.update(block)
                stream.write(block)
    if digest.hexdigest() != GRAPH_SHA256:
        raise ValueError("Original national graph differs from the pinned source")
    stream.seek(0)
    graph = load_npz(stream)
    return graph


def route_oracles(regional_roster, graph_dir, previous_isochrones=None):
    """Compute a fixed set of substantive original-graph route controls."""
    import pandas as pd
    roster = pd.read_parquet(regional_roster)
    by_suffix = {str(r.source_record_id).rsplit(":", 1)[-1]: r
                 for r in roster.itertuples(index=False)}
    # Adjacent cities, ordinary rural destinations and a longer rural-city pair.
    pairs = [("118372", "118308"), ("118308", "118372"),
             ("117733", "117688"), ("117688", "117733"),
             ("117733", "117415"), ("117415", "117733")]
    if previous_isochrones:
        old = pd.read_parquet(previous_isochrones)
        for centre in ("Балаково", "Балашов"):
            candidates = old.loc[old.centre_name.eq(centre) & ~old.self_point_zero
                                 & old.population_2021.gt(0) & old.time_minutes_total.gt(0)
                                 & old.time_minutes_total.le(15)].sort_values(
                                     ["time_minutes_total", "origin_id"])
            if not candidates.empty:
                row = candidates.iloc[0]
                a, b = str(row.origin_id).rsplit(":", 1)[-1], str(row.centre_id).rsplit(":", 1)[-1]
                pairs.extend([(a, b), (b, a)])
    graph = original_graph(graph_dir)
    records = []
    for a, b in pairs:
        origin, destination = by_suffix[a], by_suffix[b]
        network, popped = heap_shortest(graph, int(origin.road_node_index), int(destination.road_node_index))
        total = network + 4.0 * (float(origin.snap_km) + float(destination.snap_km))
        if not math.isfinite(total):
            raise ValueError("A selected connected route-control pair is unreachable")
        records.append({"origin_id": origin.source_record_id,
                        "destination_id": destination.source_record_id,
                        "origin_name": origin.name, "destination_name": destination.name,
                        "network_minutes": network, "total_minutes": total,
                        "origin_connector_minutes": 4.0 * float(origin.snap_km),
                        "destination_connector_minutes": 4.0 * float(destination.snap_km),
                        "original_graph_heap_vertices_popped": popped})
    return {"schema": "sgrt.saratov.original_graph_heap_controls.v1",
            "graph_sha256": GRAPH_SHA256,
            "method": "Independent heap on original full directed national CSR; no regional or SciPy shortest-path helper",
            "routes": records, "controls": len(records),
            "scope": "Arithmetic/direction controls, not measured real travel times"}


def catalog_checks(functions_root, source_root, catalog_path):
    """Reconcile every provider/presence identity against pinned raw sources."""
    import pandas as pd
    import pyarrow.parquet as pq
    functions_root, source_root = Path(functions_root), Path(source_root)
    catalogue = json.loads(Path(catalog_path).read_text())
    specifications = {r["path"]: r for r in catalogue["files"]}
    providers = pd.read_parquet(functions_root / "provider_catalog.parquet")
    presence = pd.read_parquet(functions_root / "np_function_presence.parquet")
    errors, source_facts = [], []
    if providers.catalog_id.duplicated().any():
        errors.append("Duplicate prepared catalog_id")
    if presence.duplicated(["family", "source_record_id"]).any():
        errors.append("Duplicate NP/function presence")
    if providers.capacity_used_as_attraction_weight.eq(True).any():
        errors.append("Facility counts/capacity used as attraction without a capacity model")
    expected_providers, expected_presence = [], set()

    def flag(frame, column, default=False):
        if column not in frame:
            return pd.Series(default, index=frame.index, dtype=bool)
        return frame[column].map(lambda v: False if pd.isna(v) else v in (True, 1, "true", "True"))

    for group, filename, kinds in [("education", "physical_sites.parquet", ["sites", "np"]),
                                   ("health", "physical_sites.parquet", ["sites", "np"]),
                                   ("commerce", "sites.parquet", ["sites"]),
                                   ("food_host", "sites.parquet", ["sites"])]:
        for kind in kinds:
            name = "np_supply.parquet" if kind == "np" else filename
            path = source_root / "sources" / group / name
            relative = f"sgrt/identity20261026/routes/sources/{group}/{name}"
            spec = specifications[relative]
            with path.open("rb") as handle:
                fingerprint = hashlib.file_digest(handle, "sha256").hexdigest()
            if path.stat().st_size != spec["bytes"] or fingerprint != spec["blob"]:
                raise ValueError("A pinned raw source differs: " + relative)
            names = set(pq.read_schema(path).names)
            wanted = [c for c in ["provider_id", "source_record_id", "service_code", "supply_status",
                "eligible", "eligible_site_supply", "route_eligible", "local_supply_eligible",
                "default_external_seed_eligible", "named_child_only_contingent",
                "actual_operational_status_verified", "actual_operational_status_checked", "current_operation_verified"] if c in names]
            raw = pd.read_parquet(path, columns=wanted)
            family = raw.service_code.map(SERVICE_FAMILIES)
            admitted = raw.supply_status.isin(["observed", "proxy"]) & family.notna()
            for c in ["eligible", "eligible_site_supply", "route_eligible", "local_supply_eligible"]:
                if c in raw:
                    admitted &= flag(raw, c)
            # Education has child-age demand by definition. Child-only medical
            # supply must not be generalised to a whole-population adult need.
            child_medical = family.fillna("").str.startswith("medical_") & flag(raw, "named_child_only_contingent")
            admitted &= ~child_medical
            external = admitted & flag(raw, "default_external_seed_eligible", default=kind == "sites")
            for sid, family_name in zip(raw.loc[admitted, "source_record_id"], family.loc[admitted]):
                if pd.notna(sid):
                    expected_presence.add((str(family_name), str(sid)))
            use = raw.loc[external].copy()
            use["family"] = family.loc[external]
            use["catalog_id"] = group + ":" + kind + ":" + use.provider_id.astype(str)
            use["operation_verified_expected"] = flag(use, "actual_operational_status_verified") | flag(use, "current_operation_verified")
            expected_providers.append(use[["catalog_id", "source_record_id", "family", "operation_verified_expected"]])
            source_facts.append({"source": relative, "raw_records": len(raw), "known_general_offers": int(admitted.sum()),
                                 "external_provider_records": int(external.sum()), "sha256": fingerprint,
                                 "checked_but_not_explicitly_verified": int((flag(raw, "actual_operational_status_checked")
                                    & ~(flag(raw, "actual_operational_status_verified") | flag(raw, "current_operation_verified"))).sum())})
    expected = pd.concat(expected_providers, ignore_index=True).set_index("catalog_id")
    actual = providers.set_index("catalog_id")
    missing = sorted(set(expected.index) - set(actual.index))
    extra = sorted(set(actual.index) - set(expected.index))
    if missing or extra:
        errors.append({"provider_set_difference": {"missing": len(missing), "extra": len(extra),
                                                  "missing_examples": missing[:10], "extra_examples": extra[:10]}})
    common = expected.index.intersection(actual.index)
    left = expected.loc[common, "source_record_id"].astype("string").fillna("__UNKNOWN__")
    right = actual.loc[common, "correctsource_record_id"].astype("string").fillna("__UNKNOWN__")
    wrong_identity = left.ne(right)
    wrong_family = expected.loc[common, "family"].ne(actual.loc[common, "family"])
    wrong_operation = expected.loc[common, "operation_verified_expected"].ne(actual.loc[common, "operation_verified"])
    if wrong_identity.any(): errors.append({"source_identity_mismatches": int(wrong_identity.sum())})
    if wrong_family.any(): errors.append({"family_mismatches": int(wrong_family.sum())})
    if wrong_operation.any(): errors.append({"operation_flag_mismatches": int(wrong_operation.sum())})
    actual_presence = set(zip(presence.family.astype(str), presence.source_record_id.astype(str)))
    if actual_presence != expected_presence:
        errors.append({"presence_set_difference": {"missing": len(expected_presence - actual_presence),
                                                   "extra": len(actual_presence - expected_presence)}})
    unresolved = actual.correctsource_record_id.isna()
    if not actual.loc[unresolved, "provider_destination_key"].str.startswith("site:").all():
        errors.append("A physical provider with unresolved NP identity was assigned an NP destination")
    return {"schema": "sgrt.saratov.provider_reconciliation.v1", "source_files": source_facts,
            "prepared_provider_records_compared": len(providers), "distinct_known_np_function_pairs": len(presence),
            "unresolved_np_identity_physical_providers": int(unresolved.sum()),
            "provider_counts_by_family": providers.groupby("family").size().to_dict(),
            "errors": errors, "violations": len(errors),
            "scope": "All-row reconciliation of admission, identities and provenance against published raw sources; actual service operation/trips are not independently established"}


def counterexamples():
    edges = [(0, 1, 3.0), (1, 2, 3.0), (0, 2, 100.0), (2, 3, 3.0)]
    forward = forward_union_fixture(4, edges, [0], 6.0)
    reversed_costs = all_pairs_relaxation(4, [(v, u, cost) for u, v, cost in edges])
    return {
        "scope": "Synthetic mathematical counterexamples, not geographic observations",
        "forward_union_keeps_external_intermediate_vertex": forward,
        "reverse_union_would_retain_only": [v for v in range(4) if reversed_costs[0][v] <= 6],
        "regional_only_induced_cost": 100.0,
        "original_route_through_external_vertex_cost": 6.0,
        "sparse_absent_cost": sparse_known_cost([0], [0.0], 1),
        "sparse_explicit_self_cost": sparse_known_cost([0], [0.0], 0),
        "nearest_basic_site_despite_many_distant_sites": nearest_compatible(
            {"local": 4.0, "large_city": 50.0}, {"local", "large_city"}),
        "chain_direct_members_within_five": direct_members([0, 3, 6, 9], 5),
        "separate_functions": {"school": "A", "primary_medicine": "B",
                               "single_common_centre_supported": False},
        "own_mass_not_attached_population": scalar_fields(
            {0: 0., 1: 10.}, [10., 20.], 10., "exponential", self_index=0),
    }


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")



def ellipsoid_area_upper(geometry):
    """Rigorous WGS84 area upper bound for linear lon/lat polygon rings.

    The geographic Jacobian is a²(1-e²)cos(phi)/(1-e²sin²(phi))².
    Bounding the denominator by (1-e²)² and cos by its maximum on
    the geometry's latitude interval gives an upper bound, without treating
    reprojected near-collinear ring vertices as a new straight polygon.
    """
    if geometry.is_empty or geometry.area == 0:
        return 0.0
    _,south,_,north=geometry.bounds
    if south < -90 or north > 90: raise ValueError('Latitude outside WGS84')
    near_zero=0. if south<=0<=north else min(abs(south),abs(north))
    a=6378137.;flattening=1/298.257223563;e2=flattening*(2-flattening)
    jacobian=a*a/(1-e2)*math.cos(math.radians(near_zero))*(math.pi/180)**2
    return float(geometry.area)*jacobian


def actual_cartographic_checks(folder):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    folder=Path(folder)
    cumulative=json.loads((folder/'isochrones_generalized_cumulative.geojson').read_text())
    bands=json.loads((folder/'isochrones_generalized_bands.geojson').read_text())
    key=lambda f:(f['properties']['centre_id'],float(f['properties']['minutes']))
    cs={key(f):shape(f['geometry']) for f in cumulative['features']}
    bs={key(f):shape(f['geometry']) for f in bands['features']}
    errors=[];rows=[]
    if len(cs)!=len(cumulative['features']) or len(bs)!=len(bands['features']):errors.append('Duplicate centre/time geometry')
    if set(cs)!=set(bs):errors.append('Band/cumulative identities differ')
    for centre in sorted({c for c,_ in cs}):
        earlier=[];previous=None
        for time in sorted(t for c,t in cs if c==centre):
            g,b=cs[centre,time],bs[centre,time]
            if not g.is_valid or not b.is_valid:errors.append('Invalid geometry: '+str((centre,time)))
            nonnested=g.intersection(previous).symmetric_difference(previous) if previous is not None else g.difference(g)
            overlap=b.intersection(unary_union(earlier)) if earlier else b.difference(b)
            earlier.append(b)
            partition=g.symmetric_difference(unary_union(earlier))
            metrics={'centre_id':centre,'minutes':time,'non_nested_area_upper_m2':ellipsoid_area_upper(nonnested),
                'band_overlap_area_upper_m2':ellipsoid_area_upper(overlap),'partition_difference_area_upper_m2':ellipsoid_area_upper(partition)}
            if any(metrics[k]>1. for k in ['non_nested_area_upper_m2','band_overlap_area_upper_m2','partition_difference_area_upper_m2']):errors.append('Delivered time-band topology exceeds 1m²: '+str((centre,time)))
            rows.append(metrics);previous=g
    return {'schema':'sgrt.saratov.cartographic_independent.v1','features_compared':len(cs),
        'rows':rows,'errors':errors,'violations':len(errors),
        'area_measurement':'Rigorous WGS84 geographic-Jacobian upper bound applied to polygon overlays in the delivered linear lon/lat ring plane',
        'scope':'Display-zone geometry only; does not validate modelled travel costs or observed service use'}


def close_numeric(actual, expected, *, absolute=1e-7, relative=1e-11):
    """Numerical arithmetic tolerance, never a geographic acceptance radius."""
    return math.isfinite(actual) and math.isfinite(expected) and abs(actual-expected) <= absolute+relative*max(abs(actual),abs(expected))


def actual_field_checks(fields_root, route_controls=None, organisation_root=None, sample_origins=20):
    """Audit completed output using raw CSR rows and scalar fsum kernels.

    All origin rows, self costs, missing-origin contracts, scenario axes and
    neighbour rankings are checked. Scalar arithmetic is checked for a fixed
    evenly spaced origin sample plus every original-graph route control.
    """
    import numpy as np
    import pandas as pd
    from scipy.sparse import load_npz
    root=Path(fields_root)
    roster=pd.read_parquet(root/'regional_roster.parquet').sort_values('row_index')
    dest=pd.read_parquet(root/'destinations.parquet').sort_values('destination_index')
    fields=pd.read_parquet(root/'fields.parquet')
    costs=load_npz(root/'destination_costs.npz')
    regional=np.load(root/'regional_costs.npy',mmap_mode='r')
    neighbours=pd.read_parquet(root/'national_neighbors.parquet')
    errors=[]; facts={}; max_delta=0.; numeric_checks=0
    def problem(condition,message):
        if condition: errors.append(message)
    problem(list(roster.row_index)!=list(range(len(roster))),'Regional row axis is not consecutive')
    problem(list(dest.destination_index)!=list(range(len(dest))),'Destination axis is not consecutive')
    problem(not roster.source_record_id.is_unique or not dest.source_record_id.is_unique,'Repeated source identity')
    problem(costs.shape!=(len(roster),len(dest)),'Sparse cost shape does not match axes')
    problem(not costs.has_canonical_format,'Noncanonical sparse coordinates')
    problem(bool((~np.isfinite(costs.data)|(costs.data<0)|(costs.data>480.+1e-8)).any()),'Invalid or beyond-horizon stored cost')
    problem(regional.shape!=(len(roster),len(roster)),'Regional matrix shape differs')
    problem(fields.duplicated(['source_record_id','kernel','half_time','include_self']).any(),'Duplicate scenario identities')
    problem(set(fields.source_record_id)!=set(roster.source_record_id),'Field origin inventory differs')
    problem(fields.groupby('source_record_id').size().nunique()!=1,'Origin scenario completeness differs')
    finite_fields=fields[fields.value.notna()]
    if len(finite_fields):
        problem(bool((~np.isfinite(finite_fields.value)|finite_fields.value.lt(-1e-7)).any()),'Invalid finite field lower value')
        if 'own_credited_mass' in finite_fields:
            paired=finite_fields.pivot(index=['source_record_id','kernel','half_time'],columns='include_self',values='value')
            own_mass=finite_fields.groupby(['source_record_id','kernel','half_time']).own_credited_mass.first()
            problem(not np.allclose(paired[True]-paired[False],own_mass,atol=1e-7,rtol=1e-11),'All-origin own mass subtraction differs')
        for col in ['tail_upper','unmapped_mass_upper','unmapped_mass_upper_without_distance_assumption']:
            problem(bool((~np.isfinite(finite_fields[col])|finite_fields[col].lt(0)).any()),'Invalid field uncertainty column: '+col)
        problem(not np.allclose(finite_fields.accepted_mass_field_upper,finite_fields.value+finite_fields.tail_upper+finite_fields.unmapped_mass_upper,atol=1e-7,rtol=1e-11),'All-origin known mass bound arithmetic differs')
    index=dict(zip(dest.source_record_id.astype(str),dest.destination_index.astype(int)))
    field_index=fields.set_index(['source_record_id','kernel','half_time','include_self'])
    origin_index=dict(zip(roster.source_record_id.astype(str),roster.row_index.astype(int)))
    ordinary=dest.ordinary_spatial_2021.eq(True).to_numpy()
    dest_ids=dest.source_record_id.astype(str).to_numpy()
    mass=np.where(dest.positive_source_mass.to_numpy(bool),dest.source_mass_2021.to_numpy(float),0.)
    by_origin={sid:g for sid,g in neighbours.groupby('origin_id',sort=False)}
    checked_knn=checked_region_pairs=unknown=0
    for r in roster.itertuples(index=False):
        sid=str(r.source_record_id);i=int(r.row_index)
        a,b=costs.indptr[i:i+2];cols=costs.indices[a:b];minutes=costs.data[a:b]
        row_fields=fields[fields.source_record_id.eq(sid)]
        if not bool(r.accepted_source_endpoint):
            unknown+=1
            problem(len(cols)!=0 or np.isfinite(regional[i]).any(),f'Unknown origin has numeric routes: {sid}')
            problem(row_fields.value.notna().any() or not row_fields.status.eq('origin_endpoint_unavailable').all(),f'Unknown field appears numeric: {sid}')
            continue
        at=np.flatnonzero(cols==index[sid])
        problem(len(at)!=1 or (len(at)==1 and abs(float(minutes[at[0]]))>1e-9),f'Missing explicit self-zero: {sid}')
        desired=np.full(len(roster),np.nan)
        col_position={int(j):float(t) for j,t in zip(cols,minutes)}
        for other,j in origin_index.items():
            if other in index and index[other] in col_position: desired[j]=col_position[index[other]]
        problem(not np.allclose(regional[i],desired,rtol=0,atol=1e-9,equal_nan=True),f'Regional matrix is not a CSR subset: {sid}')
        checked_region_pairs+=len(roster)
        eligible=ordinary[cols] & (dest_ids[cols]!=sid)
        c=cols[eligible];t=minutes[eligible]
        actual=by_origin.get(sid,neighbours.iloc[:0])
        expected=set();ordered_times=sorted(map(float,t))
        if len(c):
            limit=ordered_times[min(6,len(t))-1]
            expected={str(dest_ids[j]) for j,time in zip(c,t) if time<=limit+1e-10}
        problem(set(actual.destination_id.astype(str))!=expected,f'Outgoing national kNN candidate set differs: {sid}')
        for n in actual.itertuples(index=False):
            cost=col_position[index[str(n.destination_id)]]
            rank=1+bisect_left(ordered_times,cost-1e-10)
            problem(not close_numeric(float(n.minutes),cost,absolute=1e-9,relative=0) or int(n.rank)!=rank or bool(n.in_k3)!=(rank<=3) or bool(n.in_k6)!=(rank<=6),f'Outgoing kNN rank/cost differs: {sid}')
            checked_knn+=1
    valid=roster[roster.accepted_source_endpoint].row_index.to_numpy(int)
    samples=set(map(int,valid[np.linspace(0,len(valid)-1,min(sample_origins,len(valid)),dtype=int)]))
    route_count=0
    if route_controls:
        controls=json.loads(Path(route_controls).read_text())
        for control in controls['routes']:
            i=origin_index[control['origin_id']];j=index[control['destination_id']]
            a,b=costs.indptr[i:i+2]
            actual=sparse_known_cost(costs.indices[a:b],costs.data[a:b],j)
            problem(actual is None or not close_numeric(float(actual),float(control['total_minutes']),absolute=1e-7,relative=1e-11),'Original full graph heap route mismatch: '+control['origin_name']+' -> '+control['destination_name'])
            samples.add(i);route_count+=1
    for i in sorted(samples):
        r=roster.iloc[i];sid=str(r.source_record_id)
        a,b=costs.indptr[i:i+2];cols=costs.indices[a:b];minutes=costs.data[a:b]
        selected=mass[cols]>0
        p=mass[cols[selected]];t=minutes[selected]
        own=float(r.source_mass_2021) if bool(r.positive_source_mass) else 0.
        for row in fields[fields.source_record_id.eq(sid)].itertuples(index=False):
            expected=math.fsum(float(m)*kernel_scalar(float(cost),float(row.half_time),row.kernel) for m,cost in zip(p,t))-(0. if row.include_self else own)
            max_delta=max(max_delta,abs(float(row.value)-expected));numeric_checks+=1
            problem(not close_numeric(float(row.value),expected),f'Scalar field fsum differs: {sid}/{row.kernel}/{row.half_time}/{row.include_self}')
            problem(not close_numeric(float(row.accepted_mass_field_upper),float(row.value)+float(row.tail_upper)+float(row.unmapped_mass_upper)),f'Known-source bound arithmetic differs: {sid}')
            problem(float(row.tail_upper)<0 or float(row.unmapped_mass_upper)<0 or float(row.unmapped_mass_upper)>float(row.unmapped_mass_upper_without_distance_assumption)+1e-7,f'Invalid uncertainty bounds: {sid}')
    facts.update(regional_origins=len(roster),published_positive_population_records=int(roster.population_2021.gt(0).sum()) if 'population_2021' in roster else None,published_zero_population_records=int(roster.population_2021.eq(0).sum()) if 'population_2021' in roster else None,published_unknown_population_records=int(roster.population_2021.isna().sum()) if 'population_2021' in roster else None,missing_endpoint_origins=unknown,stored_directed_costs=int(costs.nnz),regional_matrix_entries_compared=checked_region_pairs,
                 national_neighbour_records_compared=checked_knn,independent_original_graph_route_controls=route_count,
                 scalar_fsum_origins=len(samples),scalar_fsum_scenario_checks=numeric_checks,maximum_scalar_absolute_difference=max_delta)
    if organisation_root:
        peaks=pd.read_parquet(Path(organisation_root)/'point_maxima.parquet')
        halo=pd.read_parquet(root/'halo_fields.parquet')
        all_values=pd.concat([fields,halo],ignore_index=True).set_index(['source_record_id','kernel','half_time','include_self'])
        scalar_value_lookup=all_values.value.to_dict()
        grouped={(sid,k):g.destination_id.astype(str).tolist() for k in (3,6) for sid,g in neighbours[neighbours[f'in_k{k}'].eq(True)].groupby('origin_id')}
        peak_errors=0
        for row in peaks.itertuples(index=False):
            ids=grouped.get((str(row.source_record_id),int(row.neighbour_count)),[])
            key=(row.kernel,row.half_time,row.include_self)
            own=scalar_value_lookup[(str(row.source_record_id),*key)]
            xs=[scalar_value_lookup.get((sid,*key),np.nan) for sid in ids]
            testable=np.isfinite(own) and len(ids)>=row.neighbour_count and all(np.isfinite(x) for x in xs)
            maximum=testable and all(float(x)<=float(own)+1e-9+1e-12*max(abs(float(own)),abs(float(x))) for x in xs)
            if bool(row.point_comparison_testable)!=bool(testable) or bool(row.sampled_point_maximum)!=bool(maximum): peak_errors+=1
            if bool(row.proves_functional_centre) or bool(row.proves_complete_surface_maximum): peak_errors+=1
        problem(peak_errors>0,{'independently_recomputed_peak_flag_mismatches':peak_errors})
        facts['multiscale_peak_rows_compared']=len(peaks)
        growing_path=Path(organisation_root)/'scale_neighbourhood_maxima.parquet'
        if growing_path.exists():
            growing=pd.read_parquet(growing_path)
            region_names=set(roster.region.dropna().astype(str))
            external=~dest.region.astype(str).isin(region_names).to_numpy()
            outside=[]
            for i in range(len(roster)):
                a,b=costs.indptr[i:i+2]
                candidate=[float(t) for j,t in zip(costs.indices[a:b],costs.data[a:b]) if external[j]]
                outside.append(min(candidate) if candidate else math.inf)
            field_vectors={key:g.set_index('source_record_id').value.reindex(roster.source_record_id).to_numpy(float)
                           for key,g in fields.groupby(['kernel','half_time','include_self'])}
            mismatch=0
            for row in growing.itertuples(index=False):
                i=origin_index[str(row.source_record_id)];key=(row.kernel,row.half_time,row.include_self)
                values=field_vectors[key];radius=float(row.comparison_minutes)
                mask=np.isfinite(regional[i])&(regional[i]<=radius);mask[i]=False
                other=values[mask];own=values[i]
                testable=np.isfinite(own) and len(other)>0 and np.isfinite(other).all()
                maximum=testable and all(float(x)<=float(own)+1e-9+1e-12*max(abs(float(own)),abs(float(x))) for x in other)
                border=np.isfinite(regional[i,i]) and outside[i]>radius
                if (int(row.regional_comparators)!=int(mask.sum()) or bool(row.regional_comparison_testable)!=bool(testable)
                    or bool(row.regional_scale_maximum)!=bool(maximum) or bool(row.external_comparison_complete)!=bool(border)
                    or bool(row.complete_routable_point_scale_maximum)!=bool(maximum and border)
                    or bool(row.proves_functional_level) or bool(row.common_population_surface)!=bool(row.include_self)):
                    mismatch+=1
            problem(mismatch>0,{'growing_neighbourhood_or_border_flag_mismatches':mismatch})
            facts['growing_neighbourhood_rows_compared']=len(growing)
    return {'schema':'sgrt.saratov.actual_output_independent.v1','facts':facts,'errors':errors,'violations':len(errors),
            'arithmetic_tolerance':{'absolute':1e-7,'relative':1e-11},'scope':'Arithmetic, identities, direction, missingness and peak diagnostics; not observed trip or complete service-inventory validation'}



def actual_function_checks(fields_root, functions_root, sample_origins=20, baseline_provider_root=None):
    """Independent completed nearest-known-provider and field arithmetic audit."""
    import numpy as np
    import pandas as pd
    from scipy.sparse import load_npz
    fr,fu=Path(fields_root),Path(functions_root)
    roster=pd.read_parquet(fr/'regional_roster.parquet').sort_values('row_index')
    dest=pd.read_parquet(fr/'destinations.parquet').sort_values('destination_index')
    costs=load_npz(fr/'destination_costs.npz')
    regional=np.load(fr/'regional_costs.npy',mmap_mode='r')
    provider_root=Path(baseline_provider_root) if baseline_provider_root is not None else fu
    baseline=pd.read_parquet(provider_root/'np_function_presence.parquet')
    physical=pd.read_parquet(fr/'physical_provider_candidates.parquet')
    additional_path=fu/'additional_physical_candidates.parquet'
    additional=pd.read_parquet(additional_path) if additional_path.exists() else pd.DataFrame()
    errors=[];facts=[]
    proxies=pd.read_parquet(fu/'documented_np_campus_proxies.parquet') if (fu/'documented_np_campus_proxies.parquet').exists() else pd.DataFrame()
    origin_axis=dict(zip(roster.source_record_id.astype(str),roster.row_index.astype(int)))
    dest_axis=dict(zip(dest.source_record_id.astype(str),dest.destination_index.astype(int)))
    valid=roster[roster.accepted_source_endpoint].row_index.to_numpy(int)
    samples=valid[np.linspace(0,len(valid)-1,min(sample_origins,len(valid)),dtype=int)]
    variants=[('baseline_',baseline)] if (fu/'baseline_functional_links.parquet').exists() else []
    enriched_path=fu/'np_function_presence_enriched.parquet'
    variants.append(('',pd.read_parquet(enriched_path) if enriched_path.exists() else baseline))
    for prefix,presence in variants:
        links=pd.read_parquet(fu/(prefix+'functional_links.parquet'))
        members=pd.read_parquet(fu/(prefix+'functional_system_members.parquet'))
        units=pd.read_parquet(fu/(prefix+'functional_systems.parquet'))
        potentials=pd.read_parquet(fu/(prefix+'functional_potentials.parquet'))
        candidates=physical[['origin_id','family','destination_group_key','cost_minutes']].copy()
        if len(additional):candidates=pd.concat([candidates,additional[['origin_id','family','destination_group_key','cost_minutes']]],ignore_index=True)
        if not prefix and len(proxies):
            extra=[]
            for proxy in proxies.itertuples(index=False):
                sid=str(proxy.correctsource_record_id)
                for origin,i in origin_axis.items():
                    value=regional[i,origin_axis[sid]]
                    if np.isfinite(value):extra.append({'origin_id':origin,'family':proxy.family,
                        'destination_group_key':'np:'+sid,'cost_minutes':float(value)})
            candidates=pd.concat([candidates,pd.DataFrame(extra)],ignore_index=True)
        candidate_groups={k:g for k,g in candidates.groupby(['origin_id','family'],sort=False)}
        current_path=fr/'physical_provider_candidates_current.parquet'
        current_groups={}
        if current_path.exists():
            current=pd.read_parquet(current_path)[['origin_id','family','destination_group_key','cost_minutes']]
            if len(additional):current=pd.concat([current,additional[['origin_id','family','destination_group_key','cost_minutes']]],ignore_index=True)
            if not prefix and len(proxies):
                current_proxy_meta=proxies.loc[~proxies.historical_only]
                current_proxy_keys=set(zip(current_proxy_meta.family,current_proxy_meta.provider_destination_key))
                current_extra=[r for r in extra if (r['family'],r['destination_group_key']) in current_proxy_keys]
                current=pd.concat([current,pd.DataFrame(current_extra)],ignore_index=True)
            current_groups={k:g for k,g in current.groupby(['origin_id','family'],sort=False)}
        accepted=dict(zip(roster.source_record_id.astype(str),roster.accepted_source_endpoint.astype(bool)))
        count_flags=0;numeric=0;max_delta=0.;membership_expected=set()
        for scenario,group in links.groupby('evidence_scenario'):
            families=set(group.family);expected_origins=set(roster.source_record_id)
            if group.duplicated(['origin_id','family']).any() or set(group.origin_id)!=expected_origins or len(group)!=len(roster)*len(families):
                errors.append(prefix+'Incomplete or repeated origin/function outcome axis')
            active=presence if scenario=='all_dated_known' else presence[~presence.historical_only]
            local=set(zip(active.source_record_id.astype(str),active.family.astype(str)))
            for row in group.itertuples(index=False):
                origin=str(row.origin_id);key=(origin,row.family)
                choices=(candidate_groups if scenario=='all_dated_known' else current_groups).get(key,candidates.iloc[:0])
                if scenario!='all_dated_known' and not current_path.exists():
                    raise ValueError('Current-only scenario lacks separately routed current-provider candidate axis')
                observed=json.loads(row.coequal_primary_keys_json)
                if key in local:
                    expected=['np:'+origin];expected_cost=0.
                elif len(choices):
                    expected_cost=float(choices.cost_minutes.min())
                    expected=sorted(set(choices.loc[(choices.cost_minutes-expected_cost).abs()<=1e-10,'destination_group_key'].astype(str)))
                else:expected=[];expected_cost=float('nan')
                if observed!=expected or bool(row.known_local_supply)!=(key in local):count_flags+=1
                if expected and not close_numeric(float(row.cost_minutes),expected_cost,absolute=1e-9,relative=0):count_flags+=1
                if not expected and pd.notna(row.cost_minutes):count_flags+=1
                if not accepted[origin] and not bool(row.known_local_supply) and expected:count_flags+=1
                if bool(row.observed_flow) or bool(row.provider_inventory_complete):count_flags+=1
                for target in expected:membership_expected.add((origin,row.family,scenario,target))
        membership_actual=set(zip(members.origin_id.astype(str),members.family,members.evidence_scenario,members.destination_group_key.astype(str)))
        if membership_actual!=membership_expected:errors.append({'variant':prefix,'membership_difference':len(membership_actual^membership_expected)})
        if count_flags:errors.append({'variant':prefix,'link_flag_or_direct_cost_mismatches':count_flags})
        for (scenario,system),g in members.groupby(['evidence_scenario','system_id']):
            u=units[units.system_id.eq(system)&units.evidence_scenario.eq(scenario)]
            if len(u)!=1 or len(g)!=int(u.iloc[0].member_records):errors.append(prefix+'Unit member total mismatch '+str(system));continue
            centre=u.iloc[0].centre_id
            positive_external=(g.population_2021.gt(0)&g.origin_id.ne(centre)).sum()
            if int(positive_external)!=int(u.iloc[0].external_positive_population_member_records):errors.append(prefix+'Unit external positive total mismatch '+str(system))
            if not close_numeric(float(g.cost_minutes.max()),float(u.iloc[0].maximum_selected_minutes),absolute=1e-9,relative=0):errors.append(prefix+'Unit is not direct member costs '+str(system))
        for scenario,pf in potentials.groupby('evidence_scenario'):
            active=presence if scenario=='all_dated_known' else presence[~presence.historical_only]
            offer_sets={family:{dest_axis[sid] for sid in g.source_record_id.astype(str) if sid in dest_axis}
                        for family,g in active.groupby('family')}
            selected=pf[pf.origin_id.isin(roster.iloc[samples].source_record_id)]
            rows_by_origin={sid:g for sid,g in selected.groupby('origin_id')}
            for sid,g in rows_by_origin.items():
                i=origin_axis[str(sid)];a,b=costs.indptr[i:i+2]
                by_family={family:[float(t) for j,t in zip(costs.indices[a:b],costs.data[a:b]) if int(j) in ids]
                           for family,ids in offer_sets.items()}
                for row in g.itertuples(index=False):
                    expected=math.fsum(kernel_scalar(t,float(row.half_time_minutes),row.kernel) for t in by_family.get(row.family,[]))
                    max_delta=max(max_delta,abs(expected-float(row.known_np_offer_potential)));numeric+=1
                    if not close_numeric(float(row.known_np_offer_potential),expected):errors.append(prefix+'Scalar NP-function potential differs '+str((sid,row.family)))
                    if bool(row.observed_flow) or bool(row.source_inventory_complete):errors.append(prefix+'Potential mislabelled as observed or complete')
        facts.append({'variant_prefix':prefix,'outcomes':len(links),'direct_memberships':len(members),
            'functional_systems':len(units),'scalar_np_offer_field_checks':numeric,'maximum_scalar_absolute_difference':max_delta})
    return {'schema':'sgrt.saratov.functional_independent.v1','variants':facts,'errors':errors,'violations':len(errors),
        'scope':'All origin/function axes, nearest retained physical/proxy alternatives, direct memberships and sampled scalar functional fields. Original raw inventories checked separately; no observed-flow or profile-compatibility assertion.'}



def actual_worker_checks(fields_root, context_root, samples=20):
    """Check the partial-worker field independently of its producer module."""
    import numpy as np
    import pandas as pd
    from scipy.sparse import load_npz
    fr,cr=Path(fields_root),Path(context_root)
    roster=pd.read_parquet(fr/'regional_roster.parquet').sort_values('row_index')
    dest=pd.read_parquet(fr/'destinations.parquet').sort_values('destination_index')
    source=pd.read_parquet(cr/'worker_source_np_axis.parquet').sort_values('destination_index')
    missing=pd.read_parquet(cr/'known_worker_sources_without_route_axis.parquet')
    fields=pd.read_parquet(cr/'known_partial_worker_fields.parquet')
    costs=load_npz(fr/'destination_costs.npz');errors=[];checked=0;maximum=0.
    if list(source.source_record_id)!=list(dest.source_record_id):errors.append('Worker source destination axis differs')
    if fields.duplicated(['source_record_id','kernel','half_time_minutes']).any() or len(fields)!=len(roster)*8:errors.append('Worker field scenario axis differs')
    if fields.all_workplaces_or_all_workers_potential_upper.notna().any() or fields.complete_workplace_capacity_known.any():errors.append('Incomplete worker subset presented as total jobs')
    if fields.kernel_is_empirically_calibrated_to_work_trips.any():errors.append('Uncalibrated scenario presented as observed work trips')
    numeric=source.worker_observation_known.to_numpy(bool)
    values=source.partial_organisation_workforce_2025.to_numpy(float)
    ordinary=source.ordinary_spatial_2021.eq(True).to_numpy(bool)
    if np.any(numeric & (~np.isfinite(values)|(values<0)|~ordinary)):errors.append('Invalid known partial worker source')
    total=math.fsum(float(v) for v in values[numeric])
    unlocated=math.fsum(float(v) for v in missing.partial_organisation_workforce_2025)
    own=dict(zip(source.source_record_id,source.partial_organisation_workforce_2025))
    valid=roster[roster.accepted_source_endpoint].row_index.to_numpy(int)
    sample=set(map(int,valid[np.linspace(0,len(valid)-1,min(samples,len(valid)),dtype=int)]))
    absent=set(roster.loc[~roster.accepted_source_endpoint,'source_record_id'])
    unknown=fields[fields.source_record_id.isin(absent)]
    if unknown.known_partial_worker_potential_with_self.notna().any() or not unknown.field_status.eq('unknown_origin_endpoint').all():errors.append('Unknown endpoint worker fields were filled')
    for i in sorted(sample):
        sid=roster.iloc[i].source_record_id;a,b=costs.indptr[i:i+2]
        pairs=[(float(t),float(values[j])) for j,t in zip(costs.indices[a:b],costs.data[a:b]) if numeric[j]]
        own_value=own.get(sid,np.nan);own_value=float(own_value) if pd.notna(own_value) else 0.
        routed_sum=math.fsum(v for _,v in pairs)
        for row in fields[fields.row_index.eq(i)].itertuples(index=False):
            expected=math.fsum(v*kernel_scalar(t,float(row.half_time_minutes),row.kernel) for t,v in pairs)
            tail=(total-routed_sum)*kernel_scalar(480.,float(row.half_time_minutes),row.kernel)+unlocated
            for actual,wanted in [(row.known_partial_worker_potential_with_self,expected),
                (row.known_partial_worker_potential_external,expected-own_value),
                (row.known_worker_subset_route_tail_upper,tail)]:
                maximum=max(maximum,abs(float(actual)-wanted))
                if not close_numeric(float(actual),wanted):errors.append('Worker scalar fsum or subset bound mismatch: '+str(sid))
            checked+=1
    return {'schema':'sgrt.saratov.worker_independent.v1','scenario_rows':len(fields),'sampled_origins':len(sample),
        'scalar_scenarios_compared':checked,'unknown_endpoint_scenarios':len(unknown),'maximum_absolute_difference':maximum,
        'known_source_np_without_route_endpoint':len(missing),'known_partial_workers_without_route_endpoint':unlocated,
        'errors':errors,'violations':len(errors),'scope':'Known partial Rosstat organisation-worker subset only; not total jobs or observed commuting'}



def actual_unit_context_checks(fields_root,functions_root,context_root,primary2010_evidence=None):
    """Every functional unit's fixed-membership population sums, independently."""
    import numpy as np
    import pandas as pd
    fr,fu,cr=Path(fields_root),Path(functions_root),Path(context_root)
    raw=pd.read_parquet(fr/'national_reference_with_endpoints.parquet')
    raw=raw[raw.source_record_id.notna()].set_index('source_record_id')
    if primary2010_evidence is not None:
        evidence=pd.read_parquet(primary2010_evidence).set_index('source_record_id_2010')
        if not evidence.index.is_unique:raise ValueError('Primary2010evidence identities are repeated')
        for sid,row in raw.iterrows():
            key=row.source_record_id_2010
            if key in evidence.index and bool(evidence.loc[key,'primary_value_admissible_in_separate_derived_variant']):
                raw.loc[sid,'population_2010']=float(evidence.loc[key,'primary_population_2010'])
                raw.loc[sid,'population_value_quality_2010']='regional_primary_2010_reported_value_frozen_reader_unique_original_identity'
    errors=[];facts=[]
    allowed={'direct_published_census_value','direct_official_city_value',
             'reviewed_primary_source_value_or_null','reviewed_primary_reported_value','fresh_primary_r5_source',
             'regional_primary_2010_reported_value_frozen_reader_unique_original_identity'}
    rural={'село','посёлок','деревня','хутор','станция','железнодорожный объект','железнодорожный разъезд','железнодорожная станция'}
    urban={'город','пгт','посёлок городского типа','рабочий посёлок'}
    folders=[('',cr)]
    if primary2010_evidence is None and (fu/'baseline_functional_system_members.parquet').exists() and cr.with_name('context_baseline').exists():folders.append(('baseline_',cr.with_name('context_baseline')))
    variants=[]
    for prefix,folder in folders:
        np_context=pd.read_parquet(folder/'np_context.parquet').set_index('source_record_id')
        if set(np_context.index)!=set(pd.read_parquet(fr/'regional_roster.parquet').source_record_id):errors.append(prefix+'NP context roster differs')
        expected=raw.loc[np_context.index]
        for col in ['population_2002','population_2010','population_2021']:
            if not np.allclose(np_context[col].to_numpy(float),expected[col].to_numpy(float),rtol=0,atol=0,equal_nan=True):errors.append(prefix+'NP demographic source differs '+col)
        for col in ['credit_2002','credit_2010','credit_2021','budget_population_credit','source_record_id_2010']:
            if not np_context[col].astype('string').fillna('__NA__').equals(expected[col].astype('string').fillna('__NA__')):errors.append(prefix+'NP foundation identity/credit changed '+col)
        variants.append((prefix,folder,'functional_system'))
        if (folder/'basic_centre_demographic_components.parquet').exists():variants.append((prefix,folder,'NP_basic_centre'))
    for prefix,folder,unit_kind in variants:
        if unit_kind=='functional_system':
            members=pd.read_parquet(fu/(prefix+'functional_system_members.parquet'))
            units=pd.read_parquet(fu/(prefix+'functional_systems.parquet'))
            types=pd.read_parquet(folder/'functional_system_dynamic_types.parquet')
            components=pd.read_parquet(folder/'functional_system_demographic_components.parquet')
        else:
            members=pd.read_parquet(fu/(prefix+'basic_centre_members.parquet'))
            units=pd.read_parquet(fu/(prefix+'basic_centre_profiles.parquet'))
            members['system_id']='basic-centre:'+members.centre_id.astype(str)
            units['system_id']='basic-centre:'+units.centre_id.astype(str)
            types=pd.read_parquet(folder/'basic_centre_dynamic_types.parquet')
            components=pd.read_parquet(folder/'basic_centre_demographic_components.parquet')
        if 'evidence_scenario' in members:members=members[members.evidence_scenario.eq('all_dated_known')]
        if 'evidence_scenario' in units:units=units[units.evidence_scenario.eq('all_dated_known')]
        if not types.system_id.is_unique or set(types.system_id)!=set(units.system_id):errors.append(prefix+'Unit context identity inventory differs')
        for col in ['descriptive_dynamic_type','functional_service_class','descriptive_territorial_role','dynamic_evidence_status']:
            if types[col].isna().any() or types[col].astype(str).str.strip().eq('').any():errors.append(prefix+'Empty classification column '+col)
        needed=set(members.origin_id)|set(types.centre_id.dropna());lookup=raw.loc[raw.index.intersection(list(needed))].to_dict('index')
        by_unit={sid:g for sid,g in members.groupby('system_id')}
        type_lookup=types.set_index('system_id').to_dict('index')
        identities={};checked=0
        for system,g in by_unit.items():
            target=type_lookup[system];centre=target['centre_id'];origins=sorted(set(g.origin_id))
            ext=[sid for sid in origins if sid!=centre]
            country=[sid for sid in ext if lookup[sid].get('settlement_type_2021') in rural]
            unknown_kind=any(lookup[sid].get('settlement_type_2021') not in rural|urban for sid in ext)
            identities[system]={'centre':[centre] if centre in lookup else [],'external':ext,'rural_external':country,'unknown_kind':unknown_kind}
            if int(target['regional_origins'])!=len(origins) or int(target['regional_external_origins'])!=len(ext) or int(target['regional_rural_external_origins'])!=len(country):errors.append(prefix+'Unit component membership counts differ '+system)
        for row in components.itertuples(index=False):
            ids=identities[row.system_id][row.component];paired=[]
            for sid in ids:
                data=lookup[sid];valid=True
                for year in (int(row.start_year),int(row.end_year)):
                    value=data.get(f'population_{year}')
                    valid=valid and pd.notna(value) and math.isfinite(float(value)) and float(value)>=0 and pd.notna(data.get(f'source_record_id_{year}')) and data.get(f'credit_{year}')==True and data.get('budget_population_credit')==True
                    if row.evidence_mode=='strict':valid=valid and data.get(f'population_value_quality_{year}') in allowed
                if valid:paired.append(sid)
            complete=bool(ids) and len(ids)==len(paired) and not(row.component=='rural_external' and identities[row.system_id]['unknown_kind'])
            a=math.fsum(float(lookup[sid][f'population_{int(row.start_year)}']) for sid in paired) if paired else np.nan
            b=math.fsum(float(lookup[sid][f'population_{int(row.end_year)}']) for sid in paired) if paired else np.nan
            direction=('growth' if b>a else 'decline' if b<a else 'unchanged') if complete else 'unknown'
            good=(int(row.records)==len(ids) and int(row.paired_eligible_records)==len(paired)
                  and bool(row.complete_component)==complete and row.direction==direction)
            for observed,wanted in [(row.paired_known_population_start,a),(row.paired_known_population_end,b)]:
                good=good and ((pd.isna(observed) and pd.isna(wanted)) or close_numeric(float(observed),float(wanted)))
            key=f'{row.component}_direction_{int(row.start_year)}_{int(row.end_year)}_{row.evidence_mode}'
            good=good and type_lookup[row.system_id][key]==direction
            if hasattr(row,'annualized_population_change_percent'):
                if complete and a>0 and b>0:
                    rate=100.*(math.pow(b/a,1./(int(row.end_year)-int(row.start_year)))-1.)
                    good=good and close_numeric(float(row.annualized_population_change_percent),rate,absolute=1e-9,relative=1e-10)
                else:good=good and pd.isna(row.annualized_population_change_percent)
            if not good:errors.append(prefix+'Demographic component arithmetic/eligibility differs '+str((row.system_id,row.component,row.start_year,row.end_year,row.evidence_mode)))
            checked+=1
        if len(components)!=18*len(types):errors.append(prefix+'Incomplete component/year/evidence axis')
        for identity,data in type_lookup.items():
            for mode in ['accepted','strict']:
                for scope in ['centre','external','rural_external']:
                    a=data[f'{scope}_direction_2002_2010_{mode}'];b=data[f'{scope}_direction_2010_2021_{mode}']
                    wanted=a+'__'+b if a!='unknown' and b!='unknown' else 'unknown'
                    if data[f'{scope}_trajectory_2002_2010_2021_{mode}']!=wanted:errors.append(prefix+'Three-point trajectory differs '+str(identity))
        detail={'variant_prefix':prefix,'unit_kind':unit_kind,'functional_units':len(types),'demographic_component_rows_compared':checked,'all_units_have_explicit_functional_role_and_evidence_classes':True}
        if unit_kind=='NP_basic_centre':
            regional=types.centre_in_regional_roster.eq(True)
            detail['regional_NP_basic_centres']=int(regional.sum())
            for mode in ['accepted','strict']:
                complete=types[f'centre_trajectory_2002_2010_2021_{mode}'].ne('unknown')&types[f'rural_external_trajectory_2002_2010_2021_{mode}'].ne('unknown')
                detail['regional_complete_three_point_centre_rural_'+mode]=int((regional&complete).sum())
        facts.append(detail)
    return {'schema':'sgrt.saratov.unit_context_independent.v1','variants':facts,'errors':errors,'violations':len(errors),
        'primary2010_separate_numeric_source_variant':primary2010_evidence is not None,
        'scope':'Every fixed current membership component re-summed from original NP census records with explicit credit and quality eligibility. No historical boundary reconstruction or causal typology asserted.'}



def actual_basic_centre_checks(fields_root,functions_root):
    """Deduplicate each external origin once per NP-centre across basic functions."""
    import pandas as pd
    fr,fu=Path(fields_root),Path(functions_root)
    roster=pd.read_parquet(fr/'regional_roster.parquet').set_index('source_record_id').to_dict('index')
    errors=[];facts=[]
    for prefix in ['baseline_','']:
        profile_path=fu/(prefix+'basic_centre_profiles.parquet')
        if not profile_path.exists():continue
        profiles=pd.read_parquet(profile_path);union=pd.read_parquet(fu/(prefix+'basic_centre_members.parquet'))
        members=pd.read_parquet(fu/(prefix+'functional_system_members.parquet'))
        basic=members[members.family.isin(['school','medical_basic','grocery']) & members.centre_id.notna()
                      & members.origin_id.ne(members.centre_id) & members.population_2021.gt(0)]
        expected=set(zip(basic.evidence_scenario,basic.centre_id,basic.origin_id))
        actual=set(zip(union.evidence_scenario,union.centre_id,union.origin_id))
        if expected!=actual or union.duplicated(['evidence_scenario','centre_id','origin_id']).any():errors.append(prefix+'Basic centre origin-union inventory differs')
        grouped={(s,c):g for (s,c),g in union.groupby(['evidence_scenario','centre_id'])}
        if set(zip(profiles.evidence_scenario,profiles.centre_id))!=set(grouped):errors.append(prefix+'Basic centre profile inventory differs')
        for row in profiles.itertuples(index=False):
            group=grouped[row.evidence_scenario,row.centre_id];ids=list(group.origin_id)
            credited=[sid for sid in ids if roster[sid]['credit_2021']==True and roster[sid]['budget_population_credit']==True]
            expected_population=math.fsum(float(roster[sid]['population_2021']) for sid in credited)
            if int(row.external_positive_origin_count)!=len(ids) or int(row.external_credited_positive_origin_count)!=len(credited) or not close_numeric(float(row.external_credited_population_2021),expected_population):errors.append(prefix+'Basic centre duplicates or miscredits external population '+str(row.centre_id))
            if bool(row.exclusive_regional_partition_established) or bool(row.observed_service_catchment_established) or bool(row.centre_order_assigned_from_population):errors.append(prefix+'Basic centre given unsupported partition/order/observed status')
            for family in ['school','medical_basic','grocery']:
                selected=basic[basic.evidence_scenario.eq(row.evidence_scenario)&basic.centre_id.eq(row.centre_id)&basic.family.eq(family)]
                if int(getattr(row,family+'_external_positive_origin_count'))!=selected.origin_id.nunique():errors.append(prefix+'Per-function external member count differs '+str(row.centre_id))
        for row in union.itertuples(index=False):
            source=roster[row.origin_id];valid=source['credit_2021']==True and source['budget_population_credit']==True
            if bool(row.population_credit_eligible)!=valid or (valid and not close_numeric(float(row.credited_population_2021),float(source['population_2021']))) or (not valid and pd.notna(row.credited_population_2021)):errors.append(prefix+'Origin credit/value differs '+str(row.origin_id))
        facts.append({'variant_prefix':prefix,'centre_scenario_rows':len(profiles),'deduplicated_external_origin_centre_rows':len(union),
            'all_known_centres':int(profiles.evidence_scenario.eq('all_dated_known').sum()),
            'nonhistorical_centres':int(profiles.evidence_scenario.eq('nonhistorical_evidence_only').sum())})
    return {'schema':'sgrt.saratov.basic_centre_independent.v1','variants':facts,'errors':errors,'violations':len(errors),
        'scope':'Every NP-centre union and credited external-origin sum; one origin is counted once per centre across basic functions, while overlaps between different centres remain explicit.'}



def heap_nearest_terminal(graph,origin,terminal_offsets):
    """Forward original-graph nearest source, including the destination connector."""
    if any(not math.isfinite(float(v)) or float(v)<0 for v in terminal_offsets.values()):raise ValueError('Invalid terminal connector')
    queue=[(0.,int(origin))];best={int(origin):0.};minimum=math.inf;winners=set();popped=0
    while queue:
        cost,u=heapq.heappop(queue)
        if cost!=best[u]:continue
        if cost>minimum+1e-8:break
        popped+=1
        if u in terminal_offsets:
            proposal=cost+float(terminal_offsets[u])
            if proposal<minimum-1e-8:minimum=proposal;winners={u}
            elif abs(proposal-minimum)<=1e-8:winners.add(u)
        for at in range(int(graph.indptr[u]),int(graph.indptr[u+1])):
            v,w=int(graph.indices[at]),float(graph.data[at]);proposal=cost+w
            if w<0 or not math.isfinite(w):raise ValueError('Invalid graph cost')
            if proposal<best.get(v,math.inf) and proposal<=minimum+1e-8:
                best[v]=proposal;heapq.heappush(queue,(proposal,v))
    return minimum,winners,popped


def actual_medical_competition_checks(folder,graph_dir,samples=12):
    """Original-graph forward heap controls for both medical need orders."""
    import numpy as np
    import pandas as pd
    folder=Path(folder);graph=original_graph(graph_dir);errors=[];rows=[]
    for family in ['medical_basic','medical_physician']:
        seeds=pd.read_parquet(folder/(family+'_seeds.parquet'))
        nodes=pd.read_parquet(folder/(family+'_road_nodes.parquet')).sort_values('node_index')
        terminal={int(node):float(offset) for node,offset in seeds.groupby('road_node_index').destination_connector_minutes.min().items()}
        chosen=nodes.iloc[np.linspace(0,len(nodes)-1,min(samples,len(nodes)),dtype=int)]
        for row in chosen.itertuples(index=False):
            expected,winners,popped=heap_nearest_terminal(graph,int(row.node_index),terminal)
            actual=float(row.minutes_to_nearest_known_provider)
            valid=(math.isinf(expected) and math.isinf(actual)) or close_numeric(actual,expected,absolute=1e-7,relative=1e-11)
            selected=int(row.seed_index)
            if math.isfinite(expected):
                valid=valid and 0<=selected<len(seeds)
                if valid:
                    seed=seeds.iloc[selected];source_node=int(seed.road_node_index)
                    valid=source_node in winners and abs(float(seed.destination_connector_minutes)-terminal[source_node])<=1e-8
            if not valid:errors.append('Original-graph nearest medical source differs '+str((family,int(row.node_index))))
            rows.append({'family':family,'road_node_index':int(row.node_index),'expected_minutes':expected if math.isfinite(expected) else None,
                'production_minutes':actual if math.isfinite(actual) else None,'original_graph_heap_nodes_popped':popped,
                'minimum_terminal_node_count':len(winners),'passed':bool(valid)})
    return {'schema':'sgrt.saratov.medical_competition_independent.v1','graph_sha256':GRAPH_SHA256,
        'original_forward_graph_controls':len(rows),'rows':rows,'errors':errors,'violations':len(errors),
        'scope':'Two distinct medical need families; scalar forward full-graph routing plus terminal connectors, not patient flows, referral rules or current-operation verification'}



def actual_magnit_source_checks(source_excerpt,curated_path,fields_root,provider_root=None,road_nodes=None,graph_dir=None):
    """Reconcile all locator records against frozen original used API fields."""
    import numpy as np
    import pandas as pd
    import re
    if Path(source_excerpt).suffix=='.gz':
        import gzip
        source_bytes=gzip.decompress(Path(source_excerpt).read_bytes());payload=json.loads(source_bytes)
        raw={'records':payload['data'],'totalCount':payload['totalCount'],'full_response_sha256':hashlib.sha256(source_bytes).hexdigest()}
    else:raw=json.loads(Path(source_excerpt).read_text())
    if raw['full_response_sha256']!='423b90cc8336e0e7723def683290e0cc2f358a326569503abaa24288fd5341cd':raise ValueError('Original locator response differs from the frozen source')
    curated=json.loads(Path(curated_path).read_text())
    source={str(r['externalId']['storeCode']):r for r in raw['records']}
    actual={str(r['provider_id']).split(':',1)[1]:r for r in curated}
    errors=[];identity_checks=0
    if len(source)!=len(raw['records']) or len(source)!=int(raw['totalCount']) or set(source)!=set(actual) or len(actual)!=len(curated):errors.append('Original locator inventory differs or duplicates IDs')
    reference=pd.read_parquet(Path(fields_root)/'national_reference_with_endpoints.parquet').set_index('source_record_id')
    def norm(value):return re.sub(r'\s+',' ',str(value).casefold().replace('ё','е').replace('ѐ','е').replace('–','-').replace('—','-')).strip()
    def region(value):return re.sub(r'\s+',' ',re.sub(r'(?<![а-я])(?:область|обл|республика|респ|край)(?![а-я])','',norm(value))).strip(' .')
    for code,record in source.items():
        target=actual[code];coords=record['coordinates']
        admitted=(record.get('storeTypeV2') in {'MM','MM_MINI','GM','ME','MC'} and record.get('isActive') is True and record.get('status')=='STATUS_ACTIVE' and 'DELIVERY_TYPE_OFFLINE' in record.get('deliveryTypeList',[]))
        valid=(bool(target['admitted_grocery_offer'])==admitted and target['activity_address']==record['address']
            and float(target['site_lat']).hex()==float(coords['latitude']).hex() and float(target['site_lon']).hex()==float(coords['longitude']).hex()
            and target['city_fias_id_publisher_literal']==record.get('cityFiasId')
            and target['store_format']==record['storeTypeV2'] and target['publisher_status']==record['status']
            and target['publisher_is_active']==record['isActive'] and not target['operation_verified']
            and not target['capacity_verified'] and not target['identity_is_nearest_only'])
        if not valid:errors.append('Original locator fields/admission differ '+code)
        sid=target.get('source_record_id')
        if sid is not None:
            if sid not in reference.index:errors.append('Assigned locator NP absent from source census '+code);continue
            row=reference.loc[sid];identity_checks+=1
            before=[]
            for component in record['address'].split(','):
                if re.search(r'(?<![а-я])(?:ул\.?|улица|проспект|пр-кт|переулок|пер\.?|шоссе|проезд|пр-д|площадь|пл\.?)(?![а-я])',norm(component)):break
                if not re.search(r'муниципальн|городск.{0,8}округ|р-н|район',norm(component)):before.append(component)
            text=norm(','.join(before));literal=norm(row['name'])
            if not re.search(r'(?<![а-яa-z])'+re.escape(literal)+r'(?![а-яa-z])',text):errors.append('Accepted NP has no literal pre-street locality witness '+code)
            if region(record['address'].split(',')[0])!=region(row['region']):errors.append('Accepted NP region differs from original physical address '+code)
            a,b,c,d=map(math.radians,[float(coords['latitude']),float(coords['longitude']),float(row.lat),float(row.lon)])
            hav=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
            km=6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,hav))))
            if km>5.+1e-8 or not close_numeric(float(target['literal_coordinate_difference_km']),km,absolute=1e-8,relative=1e-11) or int(target['literal_candidate_count'])!=1:errors.append('Accepted literal NP coordinate/uniqueness contract differs '+code)
    provider_records=0;snap_checks=0;max_snap_difference=0.;route_checks=[]
    if provider_root is not None:
        providers=pd.read_parquet(Path(provider_root)/'provider_catalog.parquet');provider_records=len(providers)
        expected={'magnit:'+code for code,r in actual.items() if r['admitted_grocery_offer']}
        if set(providers.provider_id)!=expected or providers.provider_id.duplicated().any():errors.append('Routed Magnit provider inventory differs from original admitted stores')
        for row in providers.itertuples(index=False):
            original=actual[str(row.provider_id).split(':',1)[1]]
            sid=None if pd.isna(row.correctsource_record_id) else str(row.correctsource_record_id)
            if sid!=original.get('source_record_id') or float(row.site_lat)!=float(original['site_lat']) or float(row.site_lon)!=float(original['site_lon']) or row.family!='grocery' or bool(row.operation_verified) or bool(row.capacity_used_as_attraction_weight):errors.append('Routed source coordinates/identity/scope changed '+str(row.provider_id))
        if road_nodes is not None:
            sample=providers.sort_values('provider_id').iloc[np.linspace(0,len(providers)-1,min(12,len(providers)),dtype=int)]
            samples=list(sample.itertuples(index=False));minimum=np.full(len(samples),np.inf);nearest=np.full(len(samples),-1,dtype='int64')
            for path in sorted(Path(road_nodes).glob('part_*.parquet')):
                roads=pd.read_parquet(path,columns=['node_index','lat','lon']);lat=np.radians(roads.lat.to_numpy(float));lon=np.radians(roads.lon.to_numpy(float));ids=roads.node_index.to_numpy('int64')
                for i,row in enumerate(samples):
                    a,b=math.radians(float(row.site_lat)),math.radians(float(row.site_lon))
                    hav=np.sin((lat-a)/2)**2+math.cos(a)*np.cos(lat)*np.sin((lon-b)/2)**2
                    distances=6371.0088*2*np.arcsin(np.sqrt(np.clip(hav,0.,1.)));at=int(np.argmin(distances));value=float(distances[at])
                    if value<minimum[i]:minimum[i]=value;nearest[i]=ids[at]
            for i,row in enumerate(samples):
                delta=abs(float(row.snap_km)-float(minimum[i]));max_snap_difference=max(max_snap_difference,delta);snap_checks+=1
                if delta>1e-8 or bool(row.accepted_snap)!=(minimum[i]<=2.):errors.append('Brute-force original road-vertex snap differs '+str(row.provider_id))
    if provider_root is not None and graph_dir is not None:
        routes=pd.read_parquet(Path(provider_root)/'physical_provider_candidates.parquet')
        terminals=providers.loc[providers.accepted_snap.eq(True)]
        offsets={int(node):float(offset) for node,offset in terminals.groupby('road_node_index').destination_connector_minutes.min().items()}
        origins=pd.read_parquet(Path(fields_root)/'regional_roster.parquet')
        origins=origins[origins.accepted_source_endpoint.eq(True)].sort_values('row_index')
        chosen=set(origins.iloc[np.linspace(0,len(origins)-1,min(12,len(origins)),dtype=int)].source_record_id)
        chosen.update(origins.loc[origins.source_record_id.str.endswith(':116922'),'source_record_id'])
        graph=original_graph(graph_dir)
        for row in origins[origins.source_record_id.isin(chosen)].itertuples(index=False):
            network,winners,popped=heap_nearest_terminal(graph,int(row.road_node_index),offsets)
            expected=network+4.*float(row.snap_km)
            subset=routes[routes.origin_id.eq(row.source_record_id)]
            route_actual=float(subset.cost_minutes.min()) if len(subset) else math.inf
            passed=(expected>480. and not len(subset)) or close_numeric(route_actual,expected,absolute=1e-7,relative=1e-11)
            if not passed:errors.append('Original forward nearest Magnit route differs '+str(row.source_record_id))
            route_checks.append({'origin_id':row.source_record_id,'name':row.name,'expected_minutes':expected if math.isfinite(expected) else None,
                'production_nearest_minutes':route_actual if math.isfinite(route_actual) else None,'original_graph_vertices_popped':popped,
                'route_within_computational_horizon':expected<=480.,'passed':bool(passed)})
    return {'schema':'sgrt.saratov.magnit_source_independent.v1','original_records':len(source),'original_totalCount':int(raw['totalCount']),
        'original_full_response_sha256':raw['full_response_sha256'],'curated_records_compared':len(actual),
        'accepted_literal_np_identities_checked':identity_checks,'routed_provider_records_compared':provider_records,
        'independent_full_road_vertex_snap_samples':snap_checks,'maximum_snap_distance_difference_km':max_snap_difference,
        'independent_original_forward_nearest_route_controls':len(route_checks),'nearest_route_controls':route_checks,
        'errors':errors,'violations':len(errors),'scope':'All original used API fields, active/offline grocery admission and assigned literal-address witnesses; optional brute-force snap sample. Not a proof of current door opening, all-retail completeness or observed customer trips.'}



def actual_medical_scope_checks(source_root,functions_root,fields_root):
    """Bounded name/operator audit; ordinary MSCh/FMBA names are not excluded."""
    import pandas as pd
    source=Path(source_root)/'sources/health/physical_sites.parquet'
    raw=pd.read_parquet(source,columns=['provider_id','provider_name','source_name','source_tags_json','tags_json','supply_status','service_code','explicit_restricted_access_signal','public_scope_exclusion_reason','context_region'])
    catalogue=pd.read_parquet(Path(functions_root)/'provider_catalog.parquet')
    links=pd.read_parquet(Path(functions_root)/'functional_links.parquet')
    patterns={'penitentiary_explicit':r'(?<![а-я])(?:У?ФСИН|СИЗО)(?![а-я])|исправительн|исполнения.*наказан|пенитенц|колони[яиюй]|следственн.*изолятор',
        'military_civilian_access_not_established':r'военн|Минобороны',
        'police_security_civilian_access_not_established':r'(?<![а-я])(?:ФСБ|ФСО|МВД|УВД|ГУВД|ГУМВД)(?![а-я])|росгвард|национальн.{0,25}гвард'}
    candidates={name:pd.read_parquet(Path(fields_root)/name) for name in ['physical_provider_candidates.parquet','physical_provider_candidates_current.parquet']}
    facts=[];errors=[]
    for category,pattern in patterns.items():
        mask=pd.Series(False,index=raw.index)
        for col in ['provider_name','source_name','source_tags_json','tags_json']:mask|=raw[col].fillna('').str.contains(pattern,case=False,regex=True)
        selected_raw=raw[mask];ids=set('health:sites:'+selected_raw.provider_id.astype(str))
        admitted=catalogue[catalogue.catalog_id.isin(ids)]
        admitted_ids=set(admitted.catalog_id);chosen=links[links.provider_site_id.isin(admitted_ids)]
        selections={name:int(frame.catalog_id.isin(admitted_ids).sum()) for name,frame in candidates.items()}
        record={'scope_category':category,'raw_service_offer_rows':len(selected_raw),
            'raw_distinct_physical_source_objects':selected_raw.provider_id.str.rsplit(':',n=1).str[0].nunique(),
            'baseline_admitted_offer_rows':len(admitted),'saratov_selected_outcome_rows':len(chosen),
            'saratov_selected_published_positive_origin_rows':int(chosen.population_2021.gt(0).sum()),
            'saratov_top3_candidate_rows':selections,
            'raw_supply_status_counts':selected_raw.supply_status.value_counts().to_dict(),
            'admitted_source_examples':admitted[['catalog_id','provider_name','family','correctsource_record_id']].where(pd.notna(admitted[['catalog_id','provider_name','family','correctsource_record_id']]),None).to_dict('records')}
        facts.append(record)
        if category=='penitentiary_explicit' and (len(admitted) or len(chosen) or any(selections.values())):errors.append('Explicit penitentiary offer admitted as a general civilian service')
    return {'schema':'sgrt.saratov.medical_source_scope_names.v1','categories':facts,'errors':errors,'violations':len(errors),
        'military_police_names_alone_prove_total_civilian_closure':False,
        'ordinary_MSCh_FMBA_railway_factory_facilities_blanket_excluded':False,
        'scope':'Names and operator tags in frozen physical-source records; source classifications and actual Saratov selected/TOP3 identities reconciled. Does not establish public access, current operation or every clinical profile for all facilities; global military/police civilian-access uncertainty remains explicit.'}



def actual_intercentre_checks(folder,functions_root):
    """All direct centre relations against original functional outcomes."""
    import numpy as np
    import pandas as pd
    folder,fu=Path(folder),Path(functions_root)
    profiles=pd.read_parquet(fu/'basic_centre_profiles.parquet');links=pd.read_parquet(fu/'functional_links.parquet')
    origins=set(zip(profiles.loc[profiles.centre_in_regional_roster.eq(True),'centre_id'],profiles.loc[profiles.centre_in_regional_roster.eq(True),'evidence_scenario']))
    expected=links[[((r.origin_id,r.evidence_scenario) in origins) for r in links.itertuples(index=False)]].copy()
    outcomes=pd.read_parquet(folder/'centre_function_outcomes.parquet');edges=pd.read_parquet(folder/'direct_centre_function_edges.parquet')
    summary=pd.read_parquet(folder/'functional_relation_summary.parquet');pairs=pd.read_parquet(folder/'cross_function_complementarity_pairs.parquet')
    keys=['origin_id','evidence_scenario','family'];errors=[]
    if expected.duplicated(keys).any() or outcomes.duplicated(keys).any() or set(map(tuple,expected[keys].to_numpy()))!=set(map(tuple,outcomes[keys].to_numpy())):errors.append('Direct-centre outcome identity set differs')
    a=expected.set_index(keys).sort_index();b=outcomes.set_index(keys).sort_index()
    for column in ['cost_minutes','provider_settlement_id','coequal_primary_keys_json','known_local_supply']:
        if column=='cost_minutes':same=np.allclose(a[column].to_numpy(float),b[column].to_numpy(float),rtol=0,atol=1e-9,equal_nan=True)
        else:same=a[column].astype('string').fillna('__NA__').equals(b[column].astype('string').fillna('__NA__'))
        if not same:errors.append('Direct-centre original outcome changed '+column)
    lookup={};families={};expected_edges=set()
    for row in expected.itertuples(index=False):
        options=json.loads(row.coequal_primary_keys_json) if np.isfinite(row.cost_minutes) else []
        for target in options:
            key=(row.origin_id,row.evidence_scenario,row.family,target);expected_edges.add(key)
            lookup[key]=(float(row.cost_minutes),len(options))
            target_np=target[3:] if target.startswith('np:') else None
            if target_np is not None and target_np!=row.origin_id:families.setdefault((row.evidence_scenario,row.origin_id,target_np),set()).add(row.family)
    actual_edges=set(zip(edges.origin_id,edges.evidence_scenario,edges.family,edges.destination_group_key))
    if actual_edges!=expected_edges or len(actual_edges)!=len(edges):errors.append('A centre edge was removed, duplicated or added transitively')
    for row in edges.itertuples(index=False):
        key=(row.origin_id,row.evidence_scenario,row.family,row.destination_group_key);value,count=lookup[key]
        target=row.destination_group_key[3:] if row.destination_group_key.startswith('np:') else None
        if not close_numeric(float(row.cost_minutes),value,absolute=1e-9,relative=0) or bool(row.is_local_self)!=(target==row.origin_id) or int(row.coequal_candidate_count)!=count or bool(row.model_choice_unique)!=(count==1) or bool(row.actual_intercentre_flow_observed) or bool(row.is_hierarchical_parent_assignment):errors.append('Direct-centre edge cost/meaning differs '+str(key))
    expected_pairs={(scenario,min(a,b),max(a,b)) for scenario,a,b in families if (scenario,b,a) in families}
    actual_pairs=set(zip(pairs.evidence_scenario,pairs.centre_a,pairs.centre_b))
    if actual_pairs!=expected_pairs or len(actual_pairs)!=len(pairs):errors.append('Direct cross-function reciprocal pair set differs')
    for row in pairs.itertuples(index=False):
        ab=families[row.evidence_scenario,row.centre_a,row.centre_b];ba=families[row.evidence_scenario,row.centre_b,row.centre_a]
        if set(json.loads(row.a_to_b_families_json))!=ab or set(json.loads(row.b_to_a_families_json))!=ba or bool(row.merge_into_one_system):errors.append('Reciprocal family composition changed or transitive merger asserted')
    for row in summary.itertuples(index=False):
        group=expected[expected.evidence_scenario.eq(row.evidence_scenario)&expected.family.eq(row.family)]
        known=group.cost_minutes.notna();local=known&group.known_local_supply.eq(True);outside=known&~local;np_known=group.provider_settlement_id.notna()
        counts=(len(group),int(local.sum()),int((outside&np_known).sum()),int((outside&~np_known).sum()),int((~known).sum()))
        actual=(int(row.regional_basic_centres),int(row.known_local_offer),int(row.known_external_np_choice),int(row.known_external_site_np_unresolved),int(row.accessibility_unknown))
        if counts!=actual or bool(row.actual_trip_flows_established):errors.append('Intercentre functional summary differs '+str((row.evidence_scenario,row.family)))
    return {'schema':'sgrt.saratov.intercentre_independent.v1','regional_centre_function_outcomes_compared':len(expected),
        'direct_edges_compared':len(edges),'reciprocal_pairs_compared':len(pairs),'functional_summaries_compared':len(summary),
        'errors':errors,'violations':len(errors),'scope':'Direct conditional known-offer relationships only; all coequal alternatives retained, no observed journey, rank, transitive merger or hierarchical parent inferred.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--precompute-routes", action="store_true")
    parser.add_argument("--regional-roster", type=Path)
    parser.add_argument("--graph-dir", type=Path)
    parser.add_argument("--previous-isochrones", type=Path)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--functions-root", type=Path)
    parser.add_argument("--provider-source-root", type=Path)
    parser.add_argument("--provider-catalog", type=Path)
    parser.add_argument("--intercentre-root", type=Path)
    parser.add_argument("--medical-scope-source-root", type=Path)
    parser.add_argument("--magnit-source-excerpt","--magnit-raw-source", dest="magnit_source_excerpt", type=Path)
    parser.add_argument("--magnit-curated", type=Path)
    parser.add_argument("--magnit-provider-root", type=Path)
    parser.add_argument("--road-nodes-dir", type=Path)
    parser.add_argument("--primary2010-evidence", type=Path)
    parser.add_argument("--baseline-provider-root", type=Path)
    parser.add_argument("--medical-competition-root", type=Path)
    parser.add_argument("--basic-centres-root", type=Path)
    parser.add_argument("--unit-context-root", type=Path)
    parser.add_argument("--context-root", type=Path)
    parser.add_argument("--functions-results-root", type=Path)
    parser.add_argument("--maps-root", type=Path)
    parser.add_argument("--actual-fields-root", type=Path)
    parser.add_argument("--route-controls", type=Path)
    parser.add_argument("--organisation-root", type=Path)
    args = parser.parse_args()
    if args.intercentre_root:
        if not args.functions_results_root: parser.error("Intercentre audit requires original functional results")
        report=actual_intercentre_checks(args.intercentre_root,args.functions_results_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Intercentre audit failed")
        return
    if args.medical_scope_source_root:
        if not args.functions_results_root or not args.actual_fields_root: parser.error("Medical scope audit requires functions and fields")
        report=actual_medical_scope_checks(args.medical_scope_source_root,args.functions_results_root,args.actual_fields_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Medical source-scope audit failed")
        return
    if args.magnit_source_excerpt:
        if not args.actual_fields_root or not args.magnit_curated: parser.error("Magnit source audit requires fields and curated locator data")
        report=actual_magnit_source_checks(args.magnit_source_excerpt,args.magnit_curated,args.actual_fields_root,args.magnit_provider_root,args.road_nodes_dir,args.graph_dir)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Magnit source audit failed")
        return
    if args.medical_competition_root:
        if not args.graph_dir: parser.error("Medical competition audit requires original graph")
        report=actual_medical_competition_checks(args.medical_competition_root,args.graph_dir)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Medical competition audit failed")
        return
    if args.basic_centres_root:
        if not args.actual_fields_root: parser.error("Basic-centre audit requires fields")
        report=actual_basic_centre_checks(args.actual_fields_root,args.basic_centres_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Basic-centre audit failed")
        return
    if args.unit_context_root:
        if not args.actual_fields_root or not args.functions_results_root: parser.error("Unit context audit requires fields and functions")
        report=actual_unit_context_checks(args.actual_fields_root,args.functions_results_root,args.unit_context_root,args.primary2010_evidence)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Unit demographic audit failed")
        return
    if args.context_root:
        if not args.actual_fields_root: parser.error("Worker audit requires --actual-fields-root")
        report=actual_worker_checks(args.actual_fields_root,args.context_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Worker audit failed")
        return
    if args.functions_results_root:
        if not args.actual_fields_root: parser.error("Functional audit requires --actual-fields-root")
        report=actual_function_checks(args.actual_fields_root,args.functions_results_root,baseline_provider_root=args.baseline_provider_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Functional audit failed")
        return
    if args.maps_root:
        report=actual_cartographic_checks(args.maps_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Cartographic audit failed")
        return
    if args.actual_fields_root:
        report=actual_field_checks(args.actual_fields_root,args.route_controls,args.organisation_root)
        write_json(args.output,report)
        if report["violations"]: raise SystemExit("Actual-output audit failed: "+str(report["violations"]))
        return
    if args.catalog_only:
        if not args.functions_root or not args.provider_source_root or not args.provider_catalog:
            parser.error("Provider reconciliation requires all three provider paths")
        write_json(args.output, catalog_checks(args.functions_root, args.provider_source_root, args.provider_catalog))
        return
    if args.precompute_routes:
        if not args.regional_roster or not args.graph_dir:
            parser.error("Route controls require --regional-roster and --graph-dir")
        write_json(args.output, route_oracles(args.regional_roster, args.graph_dir, args.previous_isochrones))
        return
    write_json(args.output, {"schema": "sgrt.saratov.regional_independent.v1",
                            "counterexamples": counterexamples(),
                            "scope": "Synthetic counterexamples only; no actual-output audit requested"})


if __name__ == "__main__":
    main()

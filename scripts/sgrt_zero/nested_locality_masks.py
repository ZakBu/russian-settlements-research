"""Resolve complete named finer-locality footprints without moving census points.

Input is the unmodified Geofabrik identity inventory AFTER physical-neighbour
guard calculation. Output is a separate derived inventory. Raw geometries and
raw point-guard evidence survive. Do not recompute raw point guards afterwards.
"""
from __future__ import annotations
import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import shapely

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.match import normalize_name
from scripts.sgrt_zero.cartographic_identity import (
    ACCEPTED, geometry_from_row, point_polygon_offset_km, file_sha,
)
from scripts.sgrt_zero.geofabrik_identity import COMPATIBLE_TYPES


def parsed_ids(value):
    values = json.loads(value or '[]')
    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
        raise ValueError('Raw neighbour IDs must be a list of exact census strings')
    return values


def cycle_nodes_and_dependents(graph):
    """Remove leaves; the remainder has a cycle or depends on one."""
    degree, reverse = {}, defaultdict(set)
    nodes = set(graph) | {child for children in graph.values() for child in children}
    for node in nodes:
        degree[node] = len(graph.get(node, set()))
        for child in graph.get(node, set()):
            reverse[child].add(node)
    queue = deque(node for node, count in degree.items() if not count)
    while queue:
        child = queue.popleft()
        for parent in reverse[child]:
            degree[parent] -= 1
            if degree[parent] == 0:
                queue.append(parent)
    return {node for node, count in degree.items() if count}


def build_nested_locality_masks(inventory, reference, *, coordinate_holds=None,
                                coordinate_hold_provenance_sha256=None,
                                max_nominal_offset_km=10.):
    """Return (derived inventory, per-parent diagnostics).

    coordinate_holds must be the set returned by validated load_coordinate_holds,
    never a set inferred from population accounting or a nearest-location guess.
    """
    if not np.isfinite(max_nominal_offset_km) or max_nominal_offset_km < 0:
        raise ValueError('Nominal coordinate sanity must be finite and nonnegative')
    if 'nested_mask_applied' in inventory and inventory.nested_mask_applied.fillna(False).any():
        raise ValueError('Nested masks require original, unmasked input inventory')
    ref = reference[reference.source_record_id.notna()].copy()
    if not ref.source_record_id.is_unique:
        raise ValueError('Reference census IDs must be unique')
    ref['_normalized_name'] = ref.name.map(normalize_name)
    by_name = ref.groupby('_normalized_name', sort=False).indices
    ref = ref.reset_index(drop=True)
    # Rebuild indices after resetting; all records, including unlocated rows,
    # participate in nominal name/type uniqueness.
    by_name = ref.groupby('_normalized_name', sort=False).indices
    ref_by_id = ref.set_index('source_record_id')
    holds = set(coordinate_holds or set())
    if not holds <= set(ref.source_record_id):
        raise ValueError('Validated coordinate hold contains an unknown census ID')
    out = inventory.copy().reset_index(drop=True)
    out['original_other_positive_census_places'] = inventory.other_positive_census_places.to_numpy()
    out['original_other_positive_census_place_ids_json'] = inventory.other_positive_census_place_ids_json.to_numpy()
    out['raw_geometry_sha256'] = inventory.geometry_sha256.to_numpy()
    out['raw_geometry_wkb'] = pd.Series([None] * len(out), dtype=object)
    out['geometry_identity_resolution'] = 'unchanged'
    out['nested_mask_applied'] = False
    out['nested_mask_status'] = 'not_needed'
    out['nested_mask_unresolved_other_count'] = inventory.other_positive_census_places.to_numpy()
    for column in ['nested_mask_census_ids_json', 'coordinate_hold_census_ids_json',
                   'nested_mask_source_feature_ids_json', 'nested_mask_child_geometry_sha256_json',
                   'nested_mask_reference_child_point_offsets_json']:
        out[column] = '[]' if column.endswith('ids_json') else '{}'
    out['nested_mask_method'] = None
    out['coordinate_hold_provenance_sha256'] = None
    out['nested_mask_parent_reference_point_in_residual'] = pd.Series([None] * len(out), dtype=object)
    named = defaultdict(list)
    owner_values = inventory.source_record_id.to_numpy()
    status_values = inventory.polygon_identity_status.to_numpy()
    for position, (owner, status) in enumerate(zip(owner_values, status_values)):
        if isinstance(owner, str) and status == ACCEPTED:
            named[owner].append(position)
    active = np.flatnonzero(inventory.other_positive_census_places.to_numpy() > 0)
    raw_ids, graph = {}, defaultdict(set)
    for position in active:
        ids = parsed_ids(inventory.iloc[position].other_positive_census_place_ids_json)
        if len(ids) != int(inventory.iloc[position].other_positive_census_places) or len(ids) != len(set(ids)):
            raise ValueError('Physical-neighbour count/list is inconsistent')
        raw_ids[position] = ids
        owner = owner_values[position]
        if isinstance(owner, str) and status_values[position] == ACCEPTED:
            graph[owner].update(set(ids) - holds)
    cyclic = cycle_nodes_and_dependents(graph)
    geometry_cache, child_cache = {}, {}

    def geometry_at(position):
        if position not in geometry_cache:
            geometry_cache[position] = geometry_from_row(inventory.iloc[position])
        return geometry_cache[position]

    def child_footprint(child):
        if child in child_cache:
            return child_cache[child]
        positions = named.get(child, [])
        reason, info = None, None
        if len(positions) != 1:
            reason = 'missing_or_ambiguous_named_child_footprint'
        elif child not in ref_by_id.index:
            reason = 'child_census_identity_unknown'
        else:
            position = positions[0]
            row = inventory.iloc[position]
            target = ref_by_id.loc[child]
            if row.get('source_dataset') != 'geofabrik_places_a':
                reason = 'child_not_primary_geofabrik_footprint'
            elif normalize_name(row.get('source_name')) != target['_normalized_name'] or normalize_name(row['name']) != target['_normalized_name']:
                reason = 'child_literal_name_conflict'
            elif row.get('source_fclass') not in COMPATIBLE_TYPES or target.settlement_type_2021 not in COMPATIBLE_TYPES[row.source_fclass]:
                reason = 'child_fclass_conflict'
            elif pd.isna(target.lat) or pd.isna(target.lon):
                reason = 'child_reference_point_unavailable'
            else:
                geometry = geometry_at(position)
                point = shapely.Point(float(target.lon), float(target.lat))
                offset = point_polygon_offset_km(point, geometry)
                basis = row.get('mapping_basis')
                if geometry.is_empty or not geometry.is_valid:
                    reason = 'child_source_geometry_invalid'
                elif offset > max_nominal_offset_km:
                    reason = 'child_reference_offset_exceeds_sanity'
                elif basis == 'literal_name_fclass_and_census_point_containment' and not geometry.covers(point):
                    reason = 'child_containment_claim_not_reproduced'
                elif basis == 'unique_literal_name_and_fclass_reference_point_outside':
                    candidates = ref.iloc[by_name.get(target['_normalized_name'], np.array([], dtype=int))]
                    candidates = candidates[candidates.settlement_type_2021.isin(COMPATIBLE_TYPES[row.source_fclass])]
                    if len(candidates) != 1 or candidates.iloc[0].source_record_id != child:
                        reason = 'child_nominal_uniqueness_not_reproduced'
                elif basis != 'literal_name_fclass_and_census_point_containment':
                    reason = 'child_identity_mapping_basis_unknown'
                if reason is None:
                    raw_wkb = bytes(row.geometry_wkb)
                    if hashlib.sha256(raw_wkb).hexdigest() != row.geometry_sha256:
                        reason = 'child_source_geometry_hash_conflict'
                    else:
                        info = {'position': position, 'source_feature_id': str(row.source_feature_id),
                                'geometry_sha256': row.geometry_sha256, 'reference_point_offset_km': offset}
        child_cache[child] = reason, info
        return reason, info

    diagnostics = []
    for position in active:
        row = inventory.iloc[position]
        owner, ids = row.source_record_id, raw_ids[position]
        exempt = sorted(set(ids) & holds)
        required = sorted(set(ids) - holds)
        out.at[position, 'raw_geometry_wkb'] = bytes(row.geometry_wkb)
        out.at[position, 'coordinate_hold_census_ids_json'] = json.dumps(exempt)
        if exempt:
            out.at[position, 'coordinate_hold_provenance_sha256'] = coordinate_hold_provenance_sha256
        status, child_info = None, {}
        if row.get('source_dataset') != 'geofabrik_places_a' or row.polygon_identity_status != ACCEPTED or not isinstance(owner, str):
            status = 'held_parent_identity_not_established'
        elif owner in holds:
            status = 'held_parent_coordinate_quality'
        elif owner in cyclic:
            status = 'held_cycle_or_dependency_on_cycle'
        elif owner not in ref_by_id.index:
            status = 'held_parent_reference_unknown'
        else:
            for child in required:
                reason, info = child_footprint(child)
                if reason:
                    status = 'held_' + reason
                    break
                child_info[child] = info
            if status is None:
                target = ref_by_id.loc[owner]
                if pd.isna(target.lat) or pd.isna(target.lon):
                    status = 'held_parent_reference_point_unavailable'
                else:
                    parent_point = shapely.Point(float(target.lon), float(target.lat))
                    children = [geometry_at(info['position']) for info in child_info.values()]
                    if any(g.covers(parent_point) for g in children):
                        status = 'held_parent_reference_point_in_child_mask'
                    else:
                        try:
                            original_geometry = geometry_at(position)
                            union = shapely.union_all(children) if children else shapely.GeometryCollection()
                            residual = original_geometry.difference(union)
                            if residual.is_empty or not residual.is_valid or residual.geom_type not in {'Polygon', 'MultiPolygon'}:
                                status = 'held_empty_or_invalid_city_residual'
                            else:
                                new_wkb = shapely.to_wkb(residual) if children else bytes(row.geometry_wkb)
                                out.at[position, 'geometry_wkb'] = new_wkb
                                out.at[position, 'geometry_sha256'] = hashlib.sha256(new_wkb).hexdigest()
                                out.at[position, 'other_positive_census_places'] = 0
                                out.at[position, 'other_positive_census_place_ids_json'] = '[]'
                                out.at[position, 'nested_mask_unresolved_other_count'] = 0
                                out.at[position, 'nested_mask_applied'] = True
                                out.at[position, 'nested_mask_census_ids_json'] = json.dumps(required)
                                out.at[position, 'nested_mask_source_feature_ids_json'] = json.dumps({k: v['source_feature_id'] for k, v in child_info.items()})
                                out.at[position, 'nested_mask_child_geometry_sha256_json'] = json.dumps({k: v['geometry_sha256'] for k, v in child_info.items()})
                                out.at[position, 'nested_mask_reference_child_point_offsets_json'] = json.dumps({k: v['reference_point_offset_km'] for k, v in child_info.items()})
                                out.at[position, 'nested_mask_parent_reference_point_in_residual'] = bool(residual.covers(parent_point))
                                resolution = 'both' if required and exempt else 'named_child_footprints_separated' if required else 'invalid_census_point_held'
                                out.at[position, 'geometry_identity_resolution'] = resolution
                                out.at[position, 'nested_mask_method'] = 'raw_parent_minus_all_named_child_footprints_with_validated_coordinate_holds'
                                status = 'applied'
                        except shapely.errors.GEOSException:
                            status = 'held_geometry_difference_error'
        out.at[position, 'nested_mask_status'] = status
        diagnostics.append({'source_record_id': owner, 'source_feature_id': row.get('source_feature_id'),
                            'name': row.get('name'), 'status': status, 'original_other_count': len(ids),
                            'named_child_footprints_checked': len(child_info), 'validated_coordinate_holds': len(exempt)})
    return out, pd.DataFrame(diagnostics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['inventory', 'reference', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--coordinate-holds', type=Path)
    parser.add_argument('--max-nominal-offset-km', type=float, default=10.)
    args = parser.parse_args()
    if args.output.resolve() == args.inventory.resolve().parent:
        raise ValueError('Write a new derived inventory; never overwrite original data')
    args.output.mkdir(parents=True, exist_ok=True)
    source_sha = file_sha(args.inventory)
    reference_sha = file_sha(args.reference)
    reference = pd.read_parquet(args.reference)
    holds = set()
    if args.coordinate_holds:
        from scripts.sgrt_zero.coordinate_quality import load_coordinate_holds
        holds = load_coordinate_holds(args.coordinate_holds, reference, repo_root=REPO)
    derived, diagnostics = build_nested_locality_masks(pd.read_parquet(args.inventory), reference,
        coordinate_holds=holds, coordinate_hold_provenance_sha256=file_sha(args.coordinate_holds) if args.coordinate_holds else None,
        max_nominal_offset_km=args.max_nominal_offset_km)
    derived.to_parquet(args.output / 'locality_polygons.parquet', index=False, compression='zstd')
    diagnostics.to_parquet(args.output / 'mask_diagnostics.parquet', index=False, compression='zstd')
    if file_sha(args.inventory) != source_sha or file_sha(args.reference) != reference_sha:
        raise ValueError('Original input changed during mask derivation')
    manifest = {'operation': 'named_finer_footprint_difference_and_validated_coordinate_holds',
                'source_inventory_sha256': source_sha, 'reference_sha256': reference_sha,
                'coordinate_hold_provenance_sha256': file_sha(args.coordinate_holds) if args.coordinate_holds else None,
                'coordinate_hold_ids': sorted(holds), 'raw_inputs_unchanged': True,
                'do_not_recompute_point_guards_after_this_stage': True,
                'rows': len(derived), 'applied_parent_records': int(derived.nested_mask_applied.sum()),
                'geometry_identity_resolution_counts': derived.geometry_identity_resolution.value_counts().to_dict(),
                'diagnostic_status_counts': diagnostics.status.value_counts().to_dict() if len(diagnostics) else {},
                'derived_inventory_sha256': file_sha(args.output / 'locality_polygons.parquet'),
                'module_sha256': file_sha(__file__), 'cartographic_not_legal_boundary': True}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

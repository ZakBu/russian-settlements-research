"""Exact bulk-column execution of cartographic_identity.assign_cartographic_identity.

The source routine remains the specification. This implementation changes only
Pandas scalar writes and repeated polygon-row/metadata construction; predicates,
query ordering, first-polygon handling and all ambiguity guards are unchanged.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import shapely
from scripts.sgrt_zero.cartographic_identity import (
    ACCEPTED, geometry_from_row, literal_localities, parse, present,
    normalize_name, normalize_region,
    CARTOGRAPHIC_RESOLUTION_METADATA,
)

OBJECT_FIELDS = [
    'cartographic_candidate_source_record_id', 'cartographic_accepted_source_record_id', 'verified_boundary_source_record_id',
    'cartographic_source_wof_id', 'cartographic_src_geom',
    'cartographic_source_repository_commit', 'cartographic_source_accessed_utc',
    'cartographic_source_archive_sha256', 'cartographic_geometry_sha256', 'cartographic_currency',
    'cartographic_mapping_basis', 'cartographic_reference_point_polygon_offset_km',
    'cartographic_source_dataset', 'cartographic_source_feature_id',
    'cartographic_source_snapshot', 'cartographic_source_url',
    'cartographic_source_component_sha256_json',
    *[target for target, _ in CARTOGRAPHIC_RESOLUTION_METADATA],
]
METADATA = [
    ('cartographic_source_wof_id', 'wof_id'), ('cartographic_src_geom', 'src_geom'),
    ('cartographic_source_repository_commit', 'source_repository_commit'),
    ('cartographic_source_accessed_utc', 'source_accessed_utc'),
    ('cartographic_source_archive_sha256', 'source_archive_sha256'),
    ('cartographic_geometry_sha256', 'geometry_sha256'), ('cartographic_currency', 'cartographic_currency'),
    ('cartographic_mapping_basis', 'mapping_basis'),
    ('cartographic_reference_point_polygon_offset_km', 'reference_point_polygon_offset_km'),
    ('cartographic_source_dataset', 'source_dataset'), ('cartographic_source_feature_id', 'source_feature_id'),
    ('cartographic_source_snapshot', 'source_snapshot'), ('cartographic_source_url', 'source_url'),
    ('cartographic_source_component_sha256_json', 'source_component_sha256_json'),
    *CARTOGRAPHIC_RESOLUTION_METADATA,
]


def assign_cartographic_identity(sites, polygons, *, lat_col='site_lat', lon_col='site_lon',
                                 owner_col='source_record_id'):
    out = sites.copy()
    if not out.index.is_unique:
        raise ValueError('Institution row index must be unique')
    n = len(out)
    values = {field: np.full(n, None, dtype=object) for field in OBJECT_FIELDS}
    values.update({
        'cartographic_identity_status': np.full(n, 'no_supported_locality_polygon', dtype=object),
        'cartographic_identity_accepted': np.zeros(n, dtype=bool),
        'cartographic_contains_other_census_places': np.zeros(n, dtype=bool),
        'cartographic_polygon_matches': np.zeros(n, dtype=np.int64),
        'cartographic_geometry_candidate_present': np.zeros(n, dtype=bool),
        'cartographic_not_legal_boundary': np.ones(n, dtype=bool),
        'cartographic_identity_is_observed_assignment': np.zeros(n, dtype=bool),
    })
    if len(polygons) and n:
        usable = polygons.reset_index(drop=True)
        # Arrays preserve pd.NA/NaN/None scalar distinctions of source columns.
        poly = {c: usable[c].to_numpy(dtype=object) for c in usable}
        geometry_columns = {c: poly[c] for c in ['geometry_wkb', 'geometry_json'] if c in poly}
        geometries = np.array([geometry_from_row({c: a[i] for c, a in geometry_columns.items()})
                               for i in range(len(usable))], dtype=object)
        tree = shapely.STRtree(geometries)
        lat = pd.to_numeric(out[lat_col], errors='coerce')
        lon = pd.to_numeric(out[lon_col], errors='coerce')
        valid = lat.between(-90, 90) & lon.between(-180, 180)
        values['cartographic_identity_status'][(~valid).to_numpy()] = 'invalid_source_coordinates'
        positions = np.flatnonzero(valid.to_numpy())
        points = shapely.points(lon.iloc[positions].to_numpy(), lat.iloc[positions].to_numpy())
        point_by_position = np.full(n, None, dtype=object)
        point_by_position[positions] = points
        pairs = tree.query(points, predicate='intersects')
        by_origin = {}
        for origin_position, polygon_position in zip(*pairs):
            by_origin.setdefault(int(positions[origin_position]), []).append(int(polygon_position))
        accepted = usable.polygon_identity_status.eq(ACCEPTED).fillna(True).to_numpy(dtype=bool)
        source = {c: out[c].to_numpy(dtype=object) for c in
                  ['tags_json', 'source_address_locality', 'source_address_state',
                   'activity_address', 'source_addr_full', 'source_address_full', owner_col] if c in out}
        details = {}
        for position, matched in by_origin.items():
            values['cartographic_polygon_matches'][position] = len(matched)
            values['cartographic_geometry_candidate_present'][position] = True
            if not accepted[matched].all():
                values['cartographic_identity_status'][position] = 'held_unresolved_primary_geometry'
                continue
            owners = {poly['source_record_id'][i] for i in matched if not pd.isna(poly['source_record_id'][i])}
            if len(owners) != 1:
                values['cartographic_identity_status'][position] = 'held_overlapping_different_census_localities'
                continue
            first = matched[0]
            if first not in details:
                owner = poly['source_record_id'][first]
                names = set(parse(poly['name_aliases_json'][first], [])) | {normalize_name(poly['name'][first])}
                region = normalize_region(poly['region'][first])
                other = int(poly['other_positive_census_places'][first]) > 0
                metadata = [(target, poly[field][first] if field in poly else None) for target, field in METADATA]
                details[first] = owner, names, region, other, metadata
            owner, names, region, other, metadata = details[first]
            values['cartographic_candidate_source_record_id'][position] = owner
            for target, value in metadata:
                values[target][position] = value
            row = {c: a[position] for c, a in source.items()}
            claims = literal_localities(row)
            tags = parse(row.get('tags_json'), {})
            region_values = [row.get('source_address_state'), tags.get('addr:state')]
            regions = {normalize_region(v) for v in region_values if present(v)}
            values['cartographic_contains_other_census_places'][position] = other
            existing = row.get(owner_col)
            if not geometries[first].contains(point_by_position[position]):
                status = 'held_point_on_cartographic_boundary'
            elif present(existing) and existing != owner:
                status = 'held_existing_source_owner_conflict'
            elif claims - names:
                status = 'held_literal_locality_conflict'
            elif regions and regions != {region}:
                status = 'held_literal_region_conflict'
            elif other:
                status = 'held_finer_census_places_inside_cartographic_polygon'
            else:
                status = 'cartographic_containment_with_literal_corroboration' if claims else 'cartographic_containment_no_literal_locality'
                values['verified_boundary_source_record_id'][position] = owner
                values['cartographic_accepted_source_record_id'][position] = owner
                values['cartographic_identity_accepted'][position] = True
            values['cartographic_identity_status'][position] = status
    for column, array in values.items():
        out[column] = array
    return out

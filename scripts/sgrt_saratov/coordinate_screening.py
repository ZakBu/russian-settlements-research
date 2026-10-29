"""Flag large conflicts with independently named OSM settlement polygons.

This is a screening query, not identity validation or an automatic coordinate
repair. OSM place class is deliberately not treated as a census settlement type.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import shape, Point
from shapely.ops import transform


def normalized(value):
    return re.sub(r'\s+', ' ', str(value).strip().lower().replace('ё', 'е'))


def screen(reference, places, boundary, threshold_km=5.):
    places = places.loc[places.fclass.isin(['city', 'town', 'village', 'hamlet'])].copy()
    places['geometry'] = shapely.from_wkb(places.geometry_wkb)
    places = places[[g is not None and not g.is_empty and boundary.covers(g.centroid)
                     for g in places.geometry]].copy()
    duplicate_extract_rows = int(places.duplicated(['osm_id', 'geometry_wkb', 'name', 'fclass']).sum())
    places = places.drop_duplicates(['osm_id', 'geometry_wkb', 'name', 'fclass']).copy()
    reference = reference.copy()
    reference['name_key'] = reference.name.map(normalized)
    places['name_key'] = places.name.map(normalized)
    refcounts, placecounts = reference.name_key.value_counts(), places.name_key.value_counts()
    project = Transformer.from_crs(4326, 32638, always_xy=True).transform
    rows = []
    for r in reference.itertuples(index=False):
        d = {'source_record_id': r.source_record_id, 'name': r.name,
             'district': r.district, 'settlement_type': r.settlement_type_2021,
             'reference_lat': r.lat, 'reference_lon': r.lon}
        candidates = places[places.name_key.eq(r.name_key)]
        if refcounts[r.name_key] != 1 or len(candidates) != 1:
            d['status'] = 'name_ambiguous_or_absent'
        elif not (np.isfinite(r.lat) and np.isfinite(r.lon)):
            d['status'] = 'reference_point_unknown'
        else:
            p = candidates.iloc[0]; point = Point(r.lon, r.lat)
            distance = transform(project, point).distance(transform(project, p.geometry)) / 1000
            d.update(status='large_conflict_over_5km' if distance > threshold_km else 'within_5km_of_named_polygon',
                     osm_id=p.osm_id, osm_fclass=p.fclass,
                     osm_centroid_lat=p.geometry.centroid.y, osm_centroid_lon=p.geometry.centroid.x,
                     distance_to_polygon_km=distance,
                     distance_to_centroid_km=transform(project, point).distance(transform(project, p.geometry.centroid)) / 1000)
        rows.append(d)
    result = pd.DataFrame(rows)
    summary = {'reference_records': len(reference), 'osm_named_polygons_in_region': len(places),
               'identical_cross_shard_extract_rows_deduplicated': duplicate_extract_rows,
               'statuses': result.status.value_counts().to_dict(),
               'threshold_km_outside_named_polygon': threshold_km,
               'normalised_name_must_be_unique_across_all_census_types': True,
               'near_polygon_is_identity_accuracy_validation': False,
               'automatic_coordinate_corrections': False}
    return result, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('reference', 'places', 'boundary', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args(); b = json.loads(a.boundary.read_text())
    boundary = shapely.union_all([shape(f['geometry']) for f in b['features']]) if b['type'] == 'FeatureCollection' else shape(b.get('geometry', b))
    table, summary = screen(pd.read_parquet(a.reference), pd.read_parquet(a.places), boundary)
    summary['input_sha256'] = {}
    for name in ('reference', 'places', 'boundary'):
        with getattr(a, name).open('rb') as f: summary['input_sha256'][name] = hashlib.file_digest(f, 'sha256').hexdigest()
    a.output.mkdir(parents=True, exist_ok=True)
    table.to_parquet(a.output / 'reference_place_audit.parquet', index=False, compression='zstd')
    table[table.status.eq('large_conflict_over_5km')].to_csv(a.output / 'large_coordinate_conflicts.csv', index=False)
    (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__': main()

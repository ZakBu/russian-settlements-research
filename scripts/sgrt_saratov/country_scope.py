"""Clip final drawings to the existing pinned Russian outline.

This deliberately makes no assertion about transit in pre-existing cost tables.
Run after buffers, simplification, water restoration and other map operations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shapely
from shapely.geometry import shape, mapping, box
from pyproj import Transformer
from shapely.ops import transform
from scripts.sgrt_saratov.source_inventory import BOUNDARY_SHA256, BOUNDARY_BYTES


def load_russia(path):
    raw = Path(path).read_bytes()
    if len(raw) != BOUNDARY_BYTES or hashlib.sha256(raw).hexdigest() != BOUNDARY_SHA256:
        raise ValueError('Country outline differs from the pinned atlas source')
    features = json.loads(raw)['features']
    if any(f['properties'].get('unit_key') != 'RUS' for f in features):
        raise ValueError('Foreign outline in Russian source')
    mask = shapely.union_all([shapely.make_valid(shape(f['geometry'])) for f in features])
    if mask.is_empty or not mask.is_valid:
        raise ValueError('Invalid national outline')
    return mask


def clip(document, mask):
    result = {k:v for k,v in document.items() if k != 'features'}
    output, diagnostics = [], []
    if document['features']:
        bounds = shapely.total_bounds([shape(f['geometry']) for f in document['features']])
        mask = shapely.intersection(mask,box(bounds[0]-1,bounds[1]-1,bounds[2]+1,bounds[3]+1))
    project = Transformer.from_crs(4326,32638,always_xy=True).transform
    for f in document['features']:
        original = shape(f['geometry'])
        cut = shapely.intersection(shapely.make_valid(original),mask)
        if original.geom_type in {'Polygon','MultiPolygon'}:
            parts = [g for g in shapely.get_parts(cut) if g.geom_type in {'Polygon','MultiPolygon'}]
            cut = shapely.union_all(parts)
        if not cut.is_empty:
            if not cut.is_valid or shapely.difference(cut, mask).area > 1e-14:
                raise ValueError('Final drawing leaves country mask')
            output.append({**f,'geometry':mapping(cut),'properties':{**f.get('properties',{}),
                'display_country_scope':'Russia_pinned_atlas_outline',
                'foreign_transit_in_original_costs_verified':False}})
        diagnostics.append({'id':f.get('properties',{}).get('id'),
            'removed_display_area_km2':float(transform(project,original.difference(mask)).area/1e6),
            'empty_after_clip':cut.is_empty})
    result['features'] = output
    return result, diagnostics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boundary',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result, diagnostics=clip(json.loads(args.source.read_text()),load_russia(args.boundary))
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(diagnostics,ensure_ascii=False,indent=2))

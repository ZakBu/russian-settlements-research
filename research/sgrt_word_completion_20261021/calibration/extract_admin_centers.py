#!/usr/bin/env python3
"""Extract explicit OSM administrative-center relations, independently of gravity zones.

OSM is an attributed mapping source, not proof of legal municipal boundaries.
Unresolved centers and code ambiguities remain in the output.
"""
from pathlib import Path
import hashlib
import json
import re
import time
import osmium
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/workspace/scratch/sgrt_transport/russia.osm.pbf')

def main():
    started = time.time()
    records = []
    for obj in osmium.FileProcessor(str(SOURCE), entities=osmium.osm.RELATION):
        tags = dict(obj.tags)
        if tags.get('boundary') != 'administrative':
            continue
        centers = [(m.type, m.ref, m.role) for m in obj.members
                   if m.role in ('admin_centre', 'admin_center')]
        if not centers:
            continue
        for kind, ref, role in centers:
            records.append({'relation_id': obj.id, 'relation_name': tags.get('name'),
                            'admin_level': tags.get('admin_level'),
                            'oktmo_literal': tags.get('ref:oktmo') or tags.get('oktmo:user'),
                            'okato_literal': tags.get('ref:okato'),
                            'center_osm_type': kind, 'center_osm_id': ref,
                            'member_role': role, 'relation_tags_json': json.dumps(tags, ensure_ascii=False)})
    out = pd.DataFrame(records)
    wanted = set(out.loc[out.center_osm_type.eq('n'), 'center_osm_id'])
    nodes = {}
    for obj in osmium.FileProcessor(str(SOURCE), entities=osmium.osm.NODE).with_filter(osmium.filter.IdFilter(wanted)):
        if obj.id in wanted:
            tags = dict(obj.tags)
            nodes[obj.id] = {'center_name': tags.get('name'), 'center_place': tags.get('place'),
                             'center_lat': obj.location.lat, 'center_lon': obj.location.lon,
                             'center_oktmo_literal': tags.get('ref:oktmo')}
    for key in ('center_name', 'center_place', 'center_lat', 'center_lon', 'center_oktmo_literal'):
        out[key] = [nodes.get(n, {}).get(key) if kind == 'n' else None
                    for kind, n in zip(out.center_osm_type, out.center_osm_id)]
    out['municipal_code8_literal'] = out.oktmo_literal.map(
        lambda x: x if isinstance(x, str) and re.fullmatch(r'\d{8}', x) else None)
    out['source_snapshot'] = '2026-10-19T20:21:11Z'
    out['independent_of_model_catchments'] = True
    out.to_parquet(ROOT/'calibration/osm_explicit_admin_centers.parquet', index=False)
    receipt = {'source_url': 'https://download.geofabrik.de/russia-261019.osm.pbf',
               'source_sha256': '164d82cef6e96f9d625e03b6759f4521b17013d4e8d5ad88aca059a9607fafbb',
               'source_bytes': SOURCE.stat().st_size, 'rows': len(out),
               'with_eight_digit_code': int(out.municipal_code8_literal.notna().sum()),
               'with_node_coordinates': int(out.center_lat.notna().sum()),
               'seconds': round(time.time()-started, 2),
               'legal_authority': False, 'used_for_training': False,
               'warning': 'Current OSM explicit center relation; codes and historical boundary alignment require verification.'}
    (ROOT/'calibration/osm_admin_centers_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False))

if __name__ == '__main__':
    main()

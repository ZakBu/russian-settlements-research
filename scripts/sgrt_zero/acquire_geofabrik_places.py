"""Restore frozen Geofabrik place polygons by pinned byte ranges, not live APIs.

The optional ZIP contains raw source members and pinned provenance. Parquet v2
is reproducible from that ZIP, preserving DBF code/population and all raw fields.
No whole-upstream-archive checksum or legal settlement boundary is claimed.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata
import json
from pathlib import Path
import struct
import urllib.request
import zipfile
import zlib


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_member(path, member):
    if path.stat().st_size != member['raw'] or sha(path) != member['sha256']:
        raise ValueError('Existing source differs: ' + str(path))
    checksum = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            checksum = zlib.crc32(block, checksum)
    if checksum != member['crc']:
        raise ValueError('CRC differs: ' + str(path))


def restore_shard(shard, output, *, offline=False):
    dest = output / shard['shard']
    dest.mkdir(parents=True, exist_ok=True)
    missing = []
    for member in shard['members']:
        if Path(member['name']).name != member['name']:
            raise ValueError('Unsafe member name')
        path = dest / member['name']
        if path.exists(): verify_member(path, member)
        else: missing.append(member)
    if not missing: return {'shard': shard['shard'], 'reused_members': len(shard['members'])}
    if offline:
        raise FileNotFoundError('Offline source members missing in ' + str(dest))
    start, end = shard['selected_range']
    request = urllib.request.Request(shard['url'], headers={
        'Range': f'bytes={start}-{end}', 'If-Match': shard['http_etag']})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 206: raise ValueError('Pinned source did not return HTTP206')
        if response.headers.get('ETag') != shard['http_etag']:
            raise ValueError('Upstream ETag changed; restore frozen source members instead')
        content_range = response.headers.get('Content-Range', '')
        if not content_range.startswith(f'bytes {start}-{end}/'):
            raise ValueError('Wrong upstream byte range')
        data = response.read(end-start+2)
    if len(data) != end-start+1: raise ValueError('Truncated/oversized range')
    for member in shard['members']:
        pos = member['offset'] - start
        h = struct.unpack('<4s5H3L2H', data[pos:pos+30])
        if h[0] != b'PK\x03\x04': raise ValueError('Not a ZIP local header')
        name_start = pos+30
        name = data[name_start:name_start+h[-2]].decode('utf-8')
        if name != member['name']: raise ValueError('Pinned ZIP name differs')
        payload_start = name_start+h[-2]+h[-1]
        payload = data[payload_start:payload_start+member['compressed']]
        if h[3] == 0: raw = payload
        elif h[3] == 8: raw = zlib.decompress(payload, -15)
        else: raise ValueError('Unsupported ZIP compression')
        if (len(raw) != member['raw'] or zlib.crc32(raw) != member['crc']
                or hashlib.sha256(raw).hexdigest() != member['sha256']):
            raise ValueError('Pinned member CRC/length/SHA differs: ' + name)
        path = dest / name
        if path.exists(): verify_member(path, member)
        else: path.write_bytes(raw)
    return {'shard': shard['shard'], 'downloaded_bytes': len(data),
            'verified_members': len(shard['members'])}


def convert(provenance, provenance_path, output):
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapefile
    from shapely.geometry import shape
    target = output / 'places_polygons_v2.parquet'
    manifest_path = output / 'places_polygons_v2_manifest.json'
    producer = sha(__file__)
    if target.exists():
        if not manifest_path.exists(): raise FileExistsError('Unmanifested output exists')
        old = json.loads(manifest_path.read_text())
        if (old['provenance_sha256'] != sha(provenance_path)
                or old['producer_sha256'] != producer
                or old['parquet']['sha256'] != sha(target)):
            raise ValueError('Existing Parquet differs from its frozen producer/provenance')
        return old
    counts = Counter(); invalid = 0; total = 0; writer = None
    partial = target.with_suffix('.parquet.partial')
    if partial.exists(): raise FileExistsError('Incomplete output exists: ' + str(partial))
    def write(rows):
        nonlocal writer
        table = pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False)
        if writer is None: writer = pq.ParquetWriter(partial, table.schema, compression='zstd')
        writer.write_table(table.cast(writer.schema))
    try:
        for shard in sorted(provenance['shards'], key=lambda x:x['shard']):
            reader = shapefile.Reader(str(output / shard['shard'] / 'gis_osm_places_a_free_1.shp'))
            hashes = json.dumps({m['name']:m['sha256'] for m in shard['members']}, sort_keys=True)
            rows = []; seen = 0
            for i, record in enumerate(reader.iterRecords()):
                feature_index = getattr(record, 'oid', i)
                raw = record.as_dict()
                try:
                    geom = shape(reader.shape(feature_index).__geo_interface__)
                    geometry = geom.wkb; valid = bool(geom.is_valid)
                    geom_type = geom.geom_type; error = ''
                except Exception as exc:
                    geometry = None; valid = False; geom_type = 'unparsed'
                    error = type(exc).__name__ + ': ' + str(exc)
                counts[raw['fclass']] += 1; invalid += not valid; total += 1; seen += 1
                rows.append({**raw, 'osm_id': str(raw['osm_id']), 'geometry_wkb':geometry,
                    'geometry_valid':valid, 'geometry_type':geom_type, 'geometry_parse_error':error,
                    'source_dbf_fields_json':json.dumps(raw, ensure_ascii=False, sort_keys=True),
                    'source_feature_index':feature_index, 'source_shard':shard['shard'],
                    'source_url':shard['url'], 'source_snapshot':shard['snapshot'],
                    'source_snapshot_basis':'archive_HTTP_Last_Modified_not_OSM_object_timestamp',
                    'source_http_etag':shard['http_etag'], 'source_component_sha256_json':hashes,
                    'source_archive_sha256':None})
                if len(rows) == 5000: write(rows); rows = []
            if rows: write(rows)
            if seen != reader.numRecords:
                raise ValueError('DBF deleted/missing records require explicit reconciliation')
            reader.close()
    finally:
        if writer is not None: writer.close()
    partial.rename(target)
    result = {'schema':'sgrt.geofabrik_places_table.v2', 'raw_features':total,
        'invalid_geometry_records_retained_with_flag':invalid, 'fclass_counts':dict(counts),
        'all_dbf_fields_preserved':True, 'raw_population_not_census_population':True,
        'producer_sha256':producer, 'provenance_sha256':sha(provenance_path),
        'versions':{n:importlib.metadata.version(n) for n in ['pyshp','pandas','pyarrow','shapely']},
        'parquet':{'path':target.name, 'bytes':target.stat().st_size, 'sha256':sha(target)}}
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def package_sources(provenance, provenance_path, output, archive):
    if archive.exists(): raise FileExistsError('Do not replace an existing source archive')
    archive.parent.mkdir(parents=True, exist_ok=True)
    entries = [(f"{s['shard']}/{m['name']}", output/s['shard']/m['name'])
               for s in provenance['shards'] for m in s['members']]
    entries.append(('provenance.json', provenance_path))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name,path in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes(), compresslevel=6)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('Source ZIP CRC failure')
    return {'path':archive.name, 'bytes':archive.stat().st_size, 'sha256':sha(archive),
            'raw_members':len(entries)-1, 'includes_parquet':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--offline', action='store_true', help='Use already restored raw members only')
    parser.add_argument('--skip-parquet', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    source = json.loads(args.provenance.read_text())
    if source.get('schema') != 'sgrt.geofabrik_places_source.v1': raise ValueError('Wrong provenance schema')
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        transfers = list(pool.map(lambda s:restore_shard(s, args.output, offline=args.offline), source['shards']))
    result = {'source_members_verified':sum(len(s['members']) for s in source['shards']), 'transfers':transfers}
    if not args.skip_parquet: result['table'] = convert(source, args.provenance, args.output)
    if args.archive: result['archive'] = package_sources(source, args.provenance, args.output, args.archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Stream a graph16 long-table successor with reviewed 2001/2014 event rows.

The original graph16 long base and event source remain immutable. Current source
entity IDs are refreshed by exact source-record ID; historical event rows remain
scoped and never become ordinary Russian-census identity/population claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path('/workspace/settlements-work/continuation_20261004/root/long_graph16_with_364032_secondary_display/settlements_long_with_secondary_history.parquet')
EVENTS = Path('/workspace/settlements-work/continuation_20261004/root/eleventh_full_long_rebuild/final/accepted_scoped_2014_1016_plus_ukraine_2001_27.parquet')
POINT_APPLICATION = Path('/workspace/settlements-work/continuation_20261004/accepted_graph16_biofabriki_point_20261005')
TARGET = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46737'
EVENT_SHA = 'a4ee46eb7b4fbd693abbea6dd76aeb5386e5ee5fee4bb95c33e946c626bb9763'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def conform(table: pa.Table, schema: pa.Schema) -> pa.Table:
    arrays = []
    for field in schema:
        if field.name not in table.column_names:
            arrays.append(pa.nulls(table.num_rows, type=field.type))
        else:
            col = table[field.name]
            arrays.append(col if col.type == field.type else col.cast(field.type, safe=False))
    return pa.Table.from_arrays(arrays, schema=schema)


def run(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    base = pq.ParquetFile(BASE)
    events_file = pq.ParquetFile(EVENTS)
    if sha(EVENTS) != EVENT_SHA or events_file.metadata.num_rows != 1043:
        raise ValueError('scoped event source hash/row-count mismatch')
    events = pq.read_table(EVENTS)
    app_dir = POINT_APPLICATION
    point_receipt = json.loads((app_dir / 'application_receipt.json').read_text())
    point_path = app_dir / 'accepted_point_uses.parquet'
    if sha(point_path) != point_receipt['output_point_uses_sha256']:
        raise ValueError('point ledger does not match its application receipt')
    point_rows = pq.read_table(point_path, columns=['target_source_record_id','target_year','latitude','longitude','coordinate_quality','coordinate_admission_status','coordinate_temporal_basis','coordinate_measurement_date_unknown','boundary_comparability_asserted','coordinate_source','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','admission_rule','coordinate_provenance','point_origin_file','point_origin_sha256','point_origin_locator'])
    matched = [r for r in point_rows.to_pylist() if r['target_source_record_id'] == TARGET and str(r['coordinate_admission_status']) == 'reviewed_case_accepted']
    if len(matched) != 1:
        raise ValueError('expected one accepted Biofabriki point use')
    point = matched[0]
    if (float(point['latitude']),float(point['longitude'])) != (45.0822595,39.1995747) or int(float(point['target_year'])) != 2021:
        raise ValueError('accepted Biofabriki point changed')

    # Build exact current-source to graph16 entity mapping from the base in a
    # narrow projection. No name, coordinate, or administrative matching here.
    current_entities = {}
    target_rows = 0
    census_rows = 0
    census_population = 0.0
    for batch in base.iter_batches(batch_size=8192, columns=['record_type','observation_year','source_record_id','entity_id','population_value']):
        d = batch.to_pydict()
        for typ, year, sid, entity, pop in zip(d['record_type'],d['observation_year'],d['source_record_id'],d['entity_id'],d['population_value']):
            if typ != 'census':
                continue
            census_rows += 1
            census_population += float(pop or 0)
            target_rows += sid == TARGET
            if int(year) == 2021:
                if sid in current_entities:
                    raise ValueError(f'duplicate graph16 current source record: {sid}')
                current_entities[sid] = entity
    if target_rows != 1 or census_rows != 465800 or round(census_population) != 434700152:
        raise ValueError(f'graph16 base census integrity mismatch: rows={census_rows}, sum={census_population}, target={target_rows}')
    event_dicts = events.to_pylist()
    for row in event_dicts:
        current_id = row.get('current_2021_source_record_id')
        if current_id not in current_entities:
            raise ValueError(f'event current source ID does not resolve: {current_id}')
        entity = current_entities[current_id]
        for field in ('entity_id','associated_census_entity_id','current_2021_entity_id','current_place_entity_id'):
            if field in row:
                row[field] = entity
    events = pa.Table.from_pylist(event_dicts, schema=events.schema)
    schema = pa.unify_schemas([base.schema_arrow,events.schema],promote_options='permissive')

    destination = output / 'settlements_long_graph16_complete_20261005.parquet'
    point_values = {
        'latitude': point['latitude'], 'longitude': point['longitude'],
        'coordinate_quality': point['coordinate_quality'],
        'coordinate_admission_status': point['coordinate_admission_status'],
        'coordinate_temporal_basis': 'target-year point; measurement date unknown',
        'coordinate_measurement_date_unknown': True,
        'boundary_comparability_asserted': False,
        'coordinate_source': point['coordinate_source'],
        'coordinate_source_record_id': point['coordinate_source_record_id'],
        'coordinate_provider': point['coordinate_provider'],
        'coordinate_provider_id': point['coordinate_provider_id'],
        'coordinate_admission_rule': point['admission_rule'],
        'coordinate_provenance': point['coordinate_provenance'],
        'point_source_file': point['point_origin_file'],
        'point_source_sha256': point['point_origin_sha256'],
        'point_source_locator': point['point_origin_locator'],
    }
    dest = pq.ParquetWriter(destination,schema,compression='zstd')
    try:
        for batch in base.iter_batches(batch_size=2048):
            table = pa.Table.from_batches([batch],schema=base.schema_arrow)
            data = table.to_pydict()
            for i,(typ,sid) in enumerate(zip(data['record_type'],data['source_record_id'])):
                if typ == 'census' and sid == TARGET:
                    for field,value in point_values.items():
                        if field in data:
                            data[field][i] = value
            dest.write_table(conform(pa.Table.from_pydict(data,schema=base.schema_arrow),schema),row_group_size=2048)
        dest.write_table(conform(events,schema),row_group_size=1024)
    finally:
        dest.close()

    final = pq.ParquetFile(destination)
    if final.metadata.num_rows != base.metadata.num_rows + events_file.metadata.num_rows or final.metadata.num_rows != 865395:
        raise ValueError(f'long table row count mismatch: {final.metadata.num_rows}')
    readback = pq.read_table(destination,columns=['record_type','source_record_id','population_value','latitude','longitude','coordinate_admission_status'])
    idx = [i for i,r in enumerate(readback['source_record_id'].to_pylist()) if r == TARGET and readback['record_type'][i].as_py() == 'census']
    if len(idx) != 1:
        raise ValueError(f'Biofabriki final row count is {len(idx)}')
    i = idx[0]
    if (readback['population_value'][i].as_py(),readback['latitude'][i].as_py(),readback['longitude'][i].as_py(),readback['coordinate_admission_status'][i].as_py()) != (3302.0,45.0822595,39.1995747,'reviewed_case_accepted'):
        raise ValueError('Biofabriki final coordinate/population readback mismatch')
    event_counts = {}
    for row in event_dicts:
        key=(row['record_type'],int(row['observation_year']))
        event_counts[key]=event_counts.get(key,0)+1
    result={
        'status':'graph16_full_long_refresh_complete_scoped_event_sidecar_integrated',
        'base_sha256':sha(BASE),'event_scope_sha256':sha(EVENTS),
        'point_application_receipt_sha256':sha(app_dir/'application_receipt.json'),
        'entity_id_remap':'exact current_2021_source_record_id -> graph16 2021 census entity_id',
        'event_entity_id_unresolved_rows':0,'event_row_counts':[{ 'record_type':k[0],'year':k[1],'rows':v} for k,v in sorted(event_counts.items())],
        'base_census_rows':census_rows,'base_census_population_sum':round(census_population),
        'total_long_rows':final.metadata.num_rows,'long_sha256':sha(destination),'long_bytes':destination.stat().st_size,
        'biofabriki_point_only':{'source_record_id':TARGET,'population':3302,'latitude':45.0822595,'longitude':39.1995747,'identity_edges_added':0,'population_changed':False,'provider_label_mismatch_retained':True},
        'event_layers_remain_scope_limited':True,'ordinary_identity_and_population_comparability_claims_added':False,
        'analysis_csv_regenerated':False,
    }
    (output/'refresh_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.output),ensure_ascii=False,indent=2))

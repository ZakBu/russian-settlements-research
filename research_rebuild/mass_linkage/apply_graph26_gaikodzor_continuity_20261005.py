#!/usr/bin/env python3
"""Apply two reviewed RCSI-point continuity uses for Гай-Кодзор.

The current 2021 locality point is already accepted from an exact RCSI row.
This adds the same representative point to selected 2002/2010 observations by
their already accepted same-place graph path. No historic coordinate or
population-boundary comparability is claimed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path('/workspace/settlements-work/continuation_20261004')
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
GRAPH = BASE / 'accepted_graph25_bounded_cases_20261005/accepted_identity_edges.parquet'
POINTS = BASE / 'accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet'
RESIDUAL = BASE / 'accepted_graph24_anapa_20261005/scoped_joint_residual.parquet'
REVIEW = Path('/workspace/settlements-work/continuation_20261004/regions/krasnodar_exact_triads_graph20_review_20261005/independent_source_followup_v1/review.json')
RCSI = Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv')
OUT = Path('/tmp/graph26_gaikodzor_continuity_20261005')
IDS = {
    2002: '2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:354',
    2010: '2010:005_888282bccc_13._20Краснодарский_край_2010.xls:КК:52',
    2021: '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46762',
}
PINS = {
    'selected': '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
    'graph': '1cc307f2855d15c7503dd226a278c49bdab72f178f5e2564c5e20fa4195a7d1a',
    'points': 'cc2a7cf67d7c25eec2de7f962c49478dd275646138f1303ae3410bf2a6922d23',
    'residual': '669d2755db4c13504024d8d80cd899013886587bd7dad10d5759954c5d59750f',
    'review': '7e46ef95802052f0444a09dd9fb9dfaa881bbb48bb97379bac48fa685c2d60bd',
    'rcsi': '50317de1174e35fca893f5c8d965d9c7f40d6a60a06149b96672bb1a134268d0',
}
ACTIVE = ['checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect',
          'accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted',
          'case_review_accepted','independent_case_review_accepted','accepted_case_specific']


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def main() -> None:
    if OUT.exists(): raise FileExistsError(OUT)
    paths={'selected':SELECTED,'graph':GRAPH,'points':POINTS,'residual':RESIDUAL,'review':REVIEW,'rcsi':RCSI}
    for k,p in paths.items(): assert sha(p)==PINS[k],(k,sha(p))
    con=duckdb.connect(config={'threads':'1','memory_limit':'2GB'})
    ids=list(IDS.values())
    selected=con.execute('SELECT * FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))',[str(SELECTED),ids]).fetchdf().set_index('source_record_id')
    assert set(selected.index.astype(str))==set(ids)
    expectations={2002:('село','краснодарский',2917),2010:('село','краснодарский',2971),2021:('село','краснодарский',3248)}
    for year,sid in IDS.items():
        r=selected.loc[sid]
        assert (int(r.census_year),str(r.settlement_name),str(r.settlement_type),str(r.region_norm),int(r.population))==(year,'Гай-Кодзор',*expectations[year])
        assert bool(r.is_additive_settlement_record)
    residual=con.execute('SELECT source_record_id FROM read_parquet(?)',[str(RESIDUAL)]).fetchdf().source_record_id.astype(str)
    assert set([IDS[2002],IDS[2010]]).issubset(set(residual))
    assert IDS[2021] not in set(residual)
    edges=con.execute('SELECT from_source_record_id,to_source_record_id,decision_status,relation,decision_id FROM read_parquet(?) WHERE relation=\'same_place\' AND decision_status IN (SELECT unnest(?))',[str(GRAPH),ACTIVE]).fetchdf()
    assert ((edges.from_source_record_id==IDS[2002]) & (edges.to_source_record_id==IDS[2010])).any()
    assert ((edges.from_source_record_id==IDS[2010]) & (edges.to_source_record_id==IDS[2021])).any()
    point_rows=con.execute('SELECT * FROM read_parquet(?) WHERE target_source_record_id IN (SELECT unnest(?))',[str(POINTS),ids]).fetchdf()
    assert len(point_rows)==1 and str(point_rows.iloc[0].target_source_record_id)==IDS[2021]
    carrier=point_rows.iloc[0].to_dict()
    lat,lon=float(carrier['latitude']),float(carrier['longitude'])
    assert abs(lat-44.8544444444444)<1e-8 and abs(lon-37.4377777777778)<1e-8
    assert str(carrier['coordinate_source'])=='RCSI named-locality point; exact row crosswalked by name/type and preserved OKTMO comparison'
    assert str(carrier['point_origin_sha256'])==PINS['rcsi']
    assert str(carrier['point_origin_locator'])=='line_1based=67247;RCSI_id=67245;OKTMO_literal=03703000176'

    schema=pq.read_schema(POINTS)
    additions=[]
    for year in (2002,2010):
        sid=IDS[year]; target=selected.loc[sid]
        row={name:(None if pd.isna(value) else value) for name,value in carrier.items() if name in schema.names}
        source_file=str(target.source_file); source_hash=str(target.source_sha256 or '')
        row.update({
            'target_source_record_id':sid,'target_year':year,
            'source_name':str(target.settlement_name),'source_type':str(target.settlement_type),'source_region':str(target.region_norm),
            'source_file':source_file,'source_sha256':source_hash,'source_row':target.source_row,
            'source_locator':str(target.source_locator or target.source_native_id),
            'source_okato_raw':str(target.okato or ''),'source_oktmo_raw':str(target.oktmo or ''),
            'coordinate_quality':'independently_reviewed_retrospective_named_place_continuity',
            'coordinate_provenance':'RCSI named locality representative point for the exact 2021 Гай-Кодзор row; assigned to this historical source row through the accepted same_place path. The 2002 GeoKLADR point is spatially dislocated and is not used. No census-date coordinate measurement, external-provider ID binding, or population-boundary comparability is asserted.',
            'admission_rule':'independent RCSI locality-code/name review plus accepted same_place continuity from current 2021 locality point',
            'coordinate_admission_status':'reviewed_case_accepted','coordinate_application_family':'graph26_gaikodzor_retrospective_point_continuity_20261005',
            'application_inference_kind':'modern_representative_point_retrospective_continuity_inference',
            'direct_historical_coordinate_measurement':False,'coordinate_measurement_date_unknown':True,
            'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,
            'coordinate_provider':'RCSI named-locality source','coordinate_source':'RCSI named-locality point carried from 2021 own-locality row',
            'provider_binding_status':'RCSI row crosswalk applied by exact locality name/type and preserved OKTMO comparison; no coordinate-provider identifier binding asserted',
            'coordinate_source_record_id':IDS[2021],'coordinate_source_file':str(RCSI),'coordinate_source_sha256':PINS['rcsi'],
            'coordinate_source_locator':'line_1based=67247;RCSI_id=67245;OKTMO_literal=03703000176',
            'coordinate_source_origin':'RCSI named locality representative point; undated',
            'point_origin_file':str(RCSI),'point_origin_sha256':PINS['rcsi'],
            'point_origin_locator':'line_1based=67247;RCSI_id=67245;OKTMO_literal=03703000176','point_origin_kind':'raw_named_typed_rcsi_locality_point',
            'coordinate_application_review_sha256':PINS['review'],'review_id':'independent_krasnodar_local_source_followup_20261005',
            'inference_modern_point_use_target_source_record_id':IDS[2021],
            'inference_identity_path_from_source_record_id':sid,'inference_identity_path_to_source_record_id':IDS[2021],
            'inference_identity_path_decision_ids_json':json.dumps(['krasnodar-2002-2010-3','graph24-anapa-q2389159'] if year==2002 else ['graph24-anapa-q2389159']),
            'inference_identity_path_edge_count':2 if year==2002 else 1,
            'admission_allowed':True,'coordinate_admitted':True,'point_admitted':True,'identity_edge_admitted':False,'historical_propagation_allowed':True,
            'coordinate_uncertainty_flags_json':json.dumps({'measurement_date_unknown':True,'historical_measurement_not_asserted':True,'native_identifier_binding_not_asserted':True,'population_boundary_comparability_not_asserted':True},sort_keys=True),
            'target_source_name_raw':str(target.source_name_raw or target.settlement_name),
            'target_source_evidence_json':json.dumps({'population':int(target.population),'source_locator':target.source_locator,'quality':target.population_value_quality},ensure_ascii=False,sort_keys=True),
            'point_use_id':f'graph26-gaikodzor-continuity:{sid}',
        })
        for f in schema:
            v=row.get(f.name)
            if v is None or pd.isna(v): row[f.name]=None
            elif pa.types.is_string(f.type) or pa.types.is_large_string(f.type): row[f.name]=str(v)
            elif pa.types.is_boolean(f.type): row[f.name]=bool(v)
            elif pa.types.is_integer(f.type): row[f.name]=int(v)
            elif pa.types.is_floating(f.type): row[f.name]=float(v)
        additions.append(row)
    OUT.mkdir(parents=True)
    target_path=OUT/'accepted_point_uses.parquet'
    writer=pq.ParquetWriter(target_path,schema,compression='zstd')
    base=pq.ParquetFile(POINTS)
    for batch in base.iter_batches(batch_size=25000): writer.write_batch(batch)
    writer.write_table(pa.Table.from_pylist(additions,schema=schema)); writer.close()
    assert pq.ParquetFile(target_path).metadata.num_rows==base.metadata.num_rows+2
    receipt={'status':'two_reviewed_historical_point_continuity_uses_applied','inputs':{k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()},
             'graph_sha256':sha(GRAPH),'point_ledger_before_sha256':sha(POINTS),'point_ledger_after_sha256':sha(target_path),
             'new_point_uses':[{'source_record_id':IDS[y],'year':y,'latitude':lat,'longitude':lon,'status':'reviewed_case_accepted','population':int(selected.loc[IDS[y]].population)} for y in (2002,2010)],
             'coordinates_are_direct_historical_measurements':False,'population_boundary_comparability_asserted':False,'population_values_modified':False,
             'limits':['RCSI coordinate date is unknown.','Selected 2010 population 2971 remains the protected value; auxiliary Wikidata 2968 is not substituted.','Historical 2002 GeoKLADR point is rejected for this place because it is about 280 km from the independently concordant RCSI/Wikidata current-locality cluster.']}
    (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__': main()

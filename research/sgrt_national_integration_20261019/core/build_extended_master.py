#!/usr/bin/env python3
"""Append two explicitly territorial federal-city rows without altering UID cohort.

The ordinary master remains142570 rows. Unknown native RFSD fields for federal
territories remain null; available legacy federal aggregates have own namespace.
"""
from pathlib import Path
import json,hashlib
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from build_feature_master import fsync_file,fsync_dir

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;WORK=ROOT.parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build():
    mainpath=HERE/'feature_master.parquet';before=sha(mainpath)
    main=pq.read_table(mainpath);assert len(main)==142570
    axpath=WORK/'anchor_research_20261019/data/external_federal_axis.csv'
    ax=pd.read_csv(axpath);assert len(ax)==6 and ax.territory_key.nunique()==2
    records={};inputs={str(mainpath.relative_to(WORK)):before,str(axpath.relative_to(WORK)):sha(axpath)}
    for uid,g in ax.groupby('territory_key'):
        first=g.iloc[0]
        r=dict(id=uid,name=first.territory_name,type='federal_city_territory_aggregate',region=first.region_norm,lat=first.latitude,lon=first.longitude,ordinary_same_place_identity=False,all_three_own_point_uses=False,coordinate_reference_year=2021,historical_coordinate_measurement_asserted=False,historical_boundary_comparability='not_established',axis_kind='federal_city_territory_aggregate',settlement_identity_asserted=False)
        for _,x in g.iterrows():
            y=int(x.census_year)
            r.update({f'population_{y}':x.territory_population,f'source_record_id_{y}':x.population_source_record_id,f'population_value_quality_{y}':x.population_value_quality,f'source_actual_sha256_{y}':x.population_source_sha256 if pd.notna(x.population_source_sha256) else None,f'population_{y}_observed':True,f'population_{y}_zero':x.territory_population==0,f'federal_population_scope_note_{y}':x.published_scope_note})
        records[uid]=r
    for year in [2016,2021]:
        f=WORK/f'anchor_research_20261019/economy/federal_results/{year}/federal_legal_territory_features.parquet'
        data=pd.read_parquet(f);inputs[str(f.relative_to(WORK))]=sha(f)
        assert not data.duplicated(['id','quality_mode']).any()
        for _,r in data.iterrows():
            for c in data:
                if c in ['id','year','quality_mode']:continue
                records[r.id][f'econ_legacy_federal_{year}_{r.quality_mode}_{c}']=r[c]
    wbpath=ROOT/'services/wb_federal_summary.csv'
    if wbpath.exists():
        w=pd.read_csv(wbpath);inputs[str(wbpath.relative_to(WORK))]=sha(wbpath)
        for uid,g in w.groupby('wb_federal_address_candidate'):
            assert uid in records
            r=records[uid]
            r['wb_federal_address_all_types_locations']=int(g.locations.sum())
            r['wb_federal_address_focus_type8_34_locations']=int(g[g.typePoint.isin([8,34])].locations.sum())
            r['wb_federal_address_expanded_types_locations']=int(g[g.typePoint.isin([8,34,28,53,54])].locations.sum())
            r['wb_federal_address_technical_types_locations']=int(g[g.typePoint.isin([2,85])].locations.sum())
            r['wb_snapshot_date']='2026-10-19'
            r['wb_observation_scope']='published_delivery_locations_explicit_federal_source_address'
            r['wb_external_catchments_measured']=False
            for _,z in g.iterrows():r[f'wb_federal_address_type_{int(z.typePoint)}_locations']=int(z.locations)
    placespath=ROOT/'places/places_objects_and_crosswalk.parquet'
    if placespath.exists():
        cols=['source_place_id','source_release','source_geography_scope','function_group','source_operating_status','name_signal_fap','name_signal_school','name_signal_market','name_signal_ozon','name_signal_wildberries']
        places=pd.read_parquet(placespath,columns=cols);inputs[str(placespath.relative_to(WORK))]=sha(placespath)
        family=['school','preschool','other_education','hospital','healthcare','veterinary','pharmacy','bank','atm','post_office','postal_collection_point','market','retail_store','food_service','unknown_999','outside_requested_functions']
        for uid,city in [('RU-FED-MOW','moscow'),('RU-FED-SPB','saint_petersburg')]:
            for mode,scope in [('explicit',f'external_{city}_explicit_source_address'),('coordinate_core',f'external_{city}_core_coordinate_candidate_not_legal_mask')]:
                q=places[places.source_geography_scope.eq(scope)];prefix=f'places_federal_{mode}_';row=records[uid]
                nc=q[~q.source_operating_status.eq('permanently_closed')]
                row[prefix+'all_categories_count']=len(q)
                row[prefix+'requested_function_count']=int((~nc.function_group.isin(['outside_requested_functions','unknown_999'])).sum())
                row[prefix+'requested_function_diversity']=nc.loc[~nc.function_group.isin(['outside_requested_functions','unknown_999']),'function_group'].nunique()
                for f in family:row[prefix+f+'_count']=int(nc.function_group.eq(f).sum())
                for st in ['open','permanently_closed','unknown']:row[prefix+'operating_'+st+'_count']=int(q.source_operating_status.fillna('unknown').eq(st).sum())
                for signal in ['fap','school','market','ozon','wildberries']:row[prefix+'name_signal_'+signal+'_count']=int(nc['name_signal_'+signal].sum())
                row[prefix+'scope']='publisher_explicit_city_address_not_verified_legal_polygon' if mode=='explicit' else 'coordinate_near_city_anchor_not_legal_territory_membership'
                row[prefix+'physical_operation_independently_verified']=False
                row[prefix+'source_release']='2026-09-23.1'
        assert records['RU-FED-MOW']['places_federal_explicit_all_categories_count']==124772
        assert records['RU-FED-SPB']['places_federal_explicit_all_categories_count']==60449
        pd.DataFrame(records.values()).filter(regex='^id$|^places_federal_').to_csv(HERE/'external_federal_places_features.csv',index=False)
    fed=pd.DataFrame(records.values()).sort_values('id').reset_index(drop=True)
    fed.to_csv(HERE/'external_federal_features.csv',index=False)
    # Build Arrow arrays against the ordinary schema: integer nulls stay integer
    # nulls, without float coercion or replacement by artificial zeros.
    fed_arrays=[]
    for field in main.schema:
        values=fed[field.name].where(fed[field.name].notna(),None).tolist() if field.name in fed else [None,None]
        fed_arrays.append(pa.array(values,type=field.type))
    fed_table=pa.Table.from_arrays(fed_arrays,names=main.column_names)
    for c in fed:
        if c in main.column_names:continue
        arr=pa.Array.from_pandas(fed[c]);main=main.append_column(c,pa.nulls(len(main),type=arr.type));fed_table=fed_table.append_column(c,arr)
    if 'axis_kind' not in main.column_names:
        main=main.append_column('axis_kind',pa.array(['ordinary_settlement']*len(main)));fed_table=fed_table.append_column('axis_kind',pa.array(['federal_city_territory_aggregate']*2))
    else:
        i=main.schema.get_field_index('axis_kind');main=main.set_column(i,'axis_kind',pa.array(['ordinary_settlement']*len(main)))
    if 'settlement_identity_asserted' in main.column_names:
        i=main.schema.get_field_index('settlement_identity_asserted');main=main.set_column(i,'settlement_identity_asserted',pa.array([True]*len(main)))
    # Metadata describes the heterogeneous support and does not claim a census
    # of every settlement, historical city boundary comparability or jobs.
    main=main.replace_schema_metadata(None);fed_table=fed_table.replace_schema_metadata(None)
    full=pa.concat_tables([main,fed_table])
    assert len(full)==142572 and len(set(full.column('id').to_pylist()))==142572
    assert full.slice(0,142570).equals(main)
    output=HERE/'feature_master_extended142572.parquet'
    pending=output.with_suffix('.parquet.partial')
    pq.write_table(full,pending,compression='zstd',row_group_size=50000)
    fsync_file(pending);fsync_dir(HERE)
    assert pq.read_table(pending).equals(full)
    pending.replace(output);fsync_dir(HERE)
    assert pq.read_table(output).equals(full)
    assert sha(mainpath)==before,'Ordinary master changed during extension; rerun after freeze'
    audit={'status':'PASS','ordinary_rows':142570,'external_federal_territory_rows':2,'extended_rows':142572,'columns':len(full.column_names),'ordinary_master_modified':False,'ordinary_values_exactly_preserved_in_extended':True,'federal_rows_are_individual_settlements':False,'native_federal_RFSD_unknown_values':'null_not_zero','legacy_federal_finance_unit':'nominal_thousand_rub','source_support':'federal_city_territorial_aggregate_not_common_point_support','all_arrow_cells_and_types_exact_readback':True,'inputs':inputs,'output_sha256':sha(output),'output_bytes':output.stat().st_size}
    (HERE/'EXTENDED_MASTER_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));fsync_file(HERE/'EXTENDED_MASTER_AUDIT.json');fsync_dir(HERE)
    assert pq.ParquetFile(output).metadata.num_rows==142572
    assert sha(output)==audit['output_sha256']
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':build()

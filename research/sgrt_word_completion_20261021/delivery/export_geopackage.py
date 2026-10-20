#!/usr/bin/env python3
"""Export actual modeled point memberships to a portable OGC GeoPackage.

No hulls, Voronoi boundaries, or other inferred territorial polygons are generated.
Unlocated source entities remain inspectable in a nonspatial table.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import sqlite3
import struct
import zipfile
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
WKT='GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'
def quote(x):return '"'+str(x).replace('"','""')+'"'
def value(x):
    if x is None or x is pd.NA:return None
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(bool,np.bool_)):return int(x)
    if isinstance(x,(np.floating,float)):return None if not np.isfinite(x) else float(x)
    if isinstance(x,(dict,list)):return json.dumps(x,ensure_ascii=False)
    try:
        if pd.isna(x):return None
    except (TypeError,ValueError):pass
    return str(x)
def write_layer(db,name,frame,spatial=True):
    frame=frame.reset_index(drop=True).copy()
    assert frame.columns.is_unique
    columns=list(frame.columns)
    kinds={c:'INTEGER' if pd.api.types.is_bool_dtype(frame[c].dtype) or pd.api.types.is_integer_dtype(frame[c].dtype) else 'REAL' if pd.api.types.is_numeric_dtype(frame[c].dtype) else 'TEXT' for c in columns}
    fields=['fid INTEGER PRIMARY KEY']+(['geom BLOB'] if spatial else [])+[f'{quote(c)} {kinds[c]}' for c in columns]
    db.execute(f'CREATE TABLE {quote(name)} ({",".join(fields)})')
    sql=f'INSERT INTO {quote(name)} VALUES ({",".join(["?"]*(len(columns)+1+int(spatial)))})'
    rows=[]
    for fid,row in enumerate(frame.itertuples(index=False,name=None),1):
        vals=[value(x) for x in row]
        if spatial:
            lon=float(row[columns.index('lon')]);lat=float(row[columns.index('lat')]);assert -180<=lon<=180 and -90<=lat<=90
            geometry=struct.pack('<2sBBi',b'GP',0,1,4326)+struct.pack('<BIdd',1,1,lon,lat)
            rows.append([fid,geometry]+vals)
        else:rows.append([fid]+vals)
        if len(rows)>=5000:db.executemany(sql,rows);rows=[]
    if rows:db.executemany(sql,rows)
    bounds=[float(frame.lon.min()),float(frame.lat.min()),float(frame.lon.max()),float(frame.lat.max())] if spatial and len(frame) else [None]*4
    now=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    db.execute('INSERT INTO gpkg_contents VALUES (?,?,?,?,?,?,?,?,?,?)',(name,'features' if spatial else 'attributes',name,'Model hypotheses; not observed trips or territorial polygons',now,*bounds,4326 if spatial else None))
    if spatial:db.execute('INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)',(name,'geom','POINT',4326,0,0))
    if 'id' in columns:db.execute(f'CREATE INDEX {quote(name+"_id_idx")} ON {quote(name)} (id)')
    return {'layer':name,'rows':len(frame),'geometry':'POINT EPSG:4326' if spatial else None}
def run(model):
    receipt=json.loads((model/'run_receipt.json').read_text())
    if not receipt['status'].startswith('COMPUTED'):raise ValueError('Routed model output required')
    tracked=[model/x for x in ['run_receipt.json','memberships.parquet','nodes.parquet','candidate_centers.parquet','systems.parquet','word_type_hypotheses.parquet','hierarchy.parquet','function_specific_memberships.parquet']]
    def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    frozen={str(p):digest(p) for p in tracked}
    manifest=json.loads((model/'output_manifest.json').read_text())
    assert manifest['run_receipt_sha256']==digest(model/'run_receipt.json'),'Committed model snapshot required'
    for p in tracked[1:]:assert manifest['files'][p.name]['sha256']==frozen[str(p)],'Model artifact differs from completed snapshot: '+p.name
    canonical_dir=ROOT/'typology/canonical'/model.name
    canonical_receipt=canonical_dir/'receipt.json';canonical_types=canonical_dir/'word_type_hypotheses.parquet'
    if not canonical_receipt.exists():raise ValueError('Independently reviewable canonical Word typology required before GIS export')
    cr=json.loads(canonical_receipt.read_text())
    if not str(cr.get('status','')).startswith('COMPUTED'):raise ValueError('Canonical typology not ready')
    cm_path=canonical_dir/'manifest.json';cm=json.loads(cm_path.read_text())
    assert cm['model_output_manifest_sha256']==digest(model/'output_manifest.json'),'Canonical types belong to another physics snapshot'
    assert cm['receipt_sha256']==digest(canonical_receipt) and cm['files']['word_type_hypotheses.parquet']['sha256']==digest(canonical_types),'Canonical typology checksum mismatch'
    frozen[str(cm_path)]=digest(cm_path)
    frozen[str(canonical_receipt)]=digest(canonical_receipt);frozen[str(canonical_types)]=digest(canonical_types)
    mem=pd.read_parquet(model/'memberships.parquet');axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet')
    keep=['id','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021']
    effective=pd.read_parquet(model/'nodes.parquet',columns=keep)
    mem=mem.merge(effective,on='id',how='left',validate='one_to_one')
    raw=axis[['id','population_2010','population_value_quality_2010']].rename(columns={'population_2010':'original_axis_population2010','population_value_quality_2010':'original_axis_population_quality2010'})
    mem=mem.merge(raw,on='id',how='left',validate='one_to_one')
    context_layers={
        'context/climate_settlement_features.parquet':['climate_gaez_sat_above10_cday_1981_2010','climate_gaez_summer_precipitation_over_pet_1981_2010'],
        'context/soil_settlement_features.parquet':['soil_gaez_low_input_most_limiting_rating_class','soil_gaez_low_input_most_limiting_rating_class_label'],
        'soil_bonitet_recovery/experimental_bonitet_settlement_intervals.parquet':['soil_bonitet_atlas_experimental_interval_lower','soil_bonitet_atlas_experimental_interval_upper','soil_bonitet_atlas_status','soil_bonitet_atlas_scientifically_adopted'],
        'land2021_recovery/settlement_regional_farmland2021_context.parquet':['region_farmland2021_sown_share','region_farmland2021_native_grain','region_farmland2021_pair_status','region_farmland2021_do_not_sum_over_settlements'],
    }
    for filename,cols in context_layers.items():
        p=ROOT/filename;frozen[str(p)]=digest(p)
        mem=mem.merge(pd.read_parquet(p,columns=['id']+cols),on='id',how='left',validate='one_to_one')
    function_path=model/'function_specific_memberships.parquet'
    if function_path.exists():
        f=pd.read_parquet(function_path,columns=['id','function_group','assigned_center_id','assigned_travel_minutes','assignment_status'])
        assert not f.duplicated(['id','function_group']).any()
        wide=f.pivot(index='id',columns='function_group',values=['assigned_center_id','assigned_travel_minutes','assignment_status'])
        wide.columns=[f'function_{group}_{field}' for field,group in wide.columns]
        mem=mem.merge(wide.reset_index(),on='id',how='left',validate='one_to_one')
        del f,wide
    centers=pd.read_parquet(model/'candidate_centers.parquet');systems=pd.read_parquet(model/'systems.parquet')
    path=ROOT/'delivery'/f'SGRT_{model.name}.gpkg';temporary=path.with_suffix('.gpkg.building')
    if temporary.exists():temporary.unlink()
    db=sqlite3.connect(temporary);db.execute('PRAGMA application_id=1196444487');db.execute('PRAGMA user_version=10300')
    db.executescript('CREATE TABLE gpkg_spatial_ref_sys(srs_name TEXT NOT NULL,srs_id INTEGER PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition TEXT NOT NULL,description TEXT); CREATE TABLE gpkg_contents(table_name TEXT PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT UNIQUE,description TEXT DEFAULT "",last_change DATETIME NOT NULL,min_x DOUBLE,min_y DOUBLE,max_x DOUBLE,max_y DOUBLE,srs_id INTEGER REFERENCES gpkg_spatial_ref_sys(srs_id)); CREATE TABLE gpkg_geometry_columns(table_name TEXT NOT NULL,column_name TEXT NOT NULL,geometry_type_name TEXT NOT NULL,srs_id INTEGER NOT NULL,z TINYINT NOT NULL,m TINYINT NOT NULL,PRIMARY KEY(table_name,column_name),FOREIGN KEY(table_name) REFERENCES gpkg_contents(table_name),FOREIGN KEY(srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));')
    db.executemany('INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)',[('Undefined Cartesian SRS',-1,'NONE',-1,'undefined',None),('Undefined geographic SRS',0,'NONE',0,'undefined',None),('WGS84',4326,'EPSG',4326,WKT,'longitude, latitude degrees')])
    geo=mem.lat.notna()&mem.lon.notna();layers=[write_layer(db,'settlements',mem[geo]),write_layer(db,'unlocated_source_entities',mem[~geo],False)]
    layers.append(write_layer(db,'candidate_centers',centers[centers.lat.notna()&centers.lon.notna()]))
    types=pd.read_parquet(canonical_types)
    for level,group in systems.groupby('level'):
        t=types[types.level.eq(level)].groupby('center_id').apply(lambda d:json.dumps({'operational_hypotheses':d.loc[d.operational_hypothesis,'word_type'].astype(int).tolist(),'fully_satisfied':d.loc[d.rule_status.eq('satisfied_observed_indicators'),'word_type'].astype(int).tolist()},ensure_ascii=False),include_groups=False)
        group=group.copy();group['word_type_status_json']=group.center_id.map(t)
        for typ in range(1,10):
            specific=types[types.level.eq(level)&types.word_type.eq(typ)].set_index('center_id')
            group[f'word_type{typ}_operational_hypothesis']=group.center_id.map(specific.operational_hypothesis)
            group[f'word_type{typ}_evidence_status']=group.center_id.map(specific.rule_status)
        layers.append(write_layer(db,f'systems_level{int(level)}',group[group.lat.notna()&group.lon.notna()]))
    layers.append(write_layer(db,'hierarchy_links',pd.read_parquet(model/'hierarchy.parquet'),False))
    broad_path=canonical_dir/'broad_prototypes.parquet'
    if broad_path.exists():
        assert cm['files'][broad_path.name]['sha256']==digest(broad_path)
        frozen[str(broad_path)]=digest(broad_path)
        broad=pd.read_parquet(broad_path)
        layers.append(write_layer(db,'broad_prototypes_not_literal_word_types',broad,False))
    layers.append(write_layer(db,'model_run_provenance',pd.DataFrame([{'model_directory':str(model),'receipt_json':json.dumps(receipt,ensure_ascii=False),'membership_sha256':hashlib.sha256((model/'memberships.parquet').read_bytes()).hexdigest()}]),False))
    db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert sum(x['rows'] for x in layers[:2])==len(mem)
    # Decode an independently sampled stored geometry, not just its source values.
    blob,lon,lat=db.execute('SELECT geom,lon,lat FROM settlements LIMIT 1').fetchone()
    assert blob[:2]==b'GP' and struct.unpack('<i',blob[4:8])[0]==4326
    endian,typ,x,y=struct.unpack('<BIdd',blob[8:]);assert endian==1 and typ==1 and x==lon and y==lat
    db.close()
    assert frozen=={p:digest(Path(p)) for p in frozen},'Inputs changed during GIS export'
    temporary.replace(path)
    try:
        import pyogrio
        for layer in layers:
            if layer['geometry']:
                info=pyogrio.read_info(path,layer=layer['layer'])
                assert info['features']==layer['rows'] and info['crs']=='EPSG:4326'
        independent_reader='GDAL via pyogrio; layer counts and EPSG:4326 verified'
    except ImportError:independent_reader='not installed; SQLite and geometry checks only'
    archive=path.with_suffix('.gpkg.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:z.write(path,path.name)
    result={'status':'EXPORTED_ACTUAL_MODEL_POINTS','path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'archive':archive.name,'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'independent_reader':independent_reader,'model_directory':str(model),'layers':layers,'input_sha256':frozen,'population_axis_and_external_anchors_separate_in_attributes':True,'inferred_territorial_polygons':False,'all_model_ids_accounted_for':True,'checks':['sqlite_integrity','foreign_keys','geometry_binary_decode','axis_conservation','input_hashes_before_after']}
    (path.with_suffix('.receipt.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);a=p.parse_args();run(a.model)

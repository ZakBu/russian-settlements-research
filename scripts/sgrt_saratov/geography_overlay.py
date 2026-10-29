"""Apply explicit, evidenced pilot-coordinate corrections to derived inputs only.

The published population foundation and its original endpoint file are never
modified. Matching coordinates and source hashes are required before a curated
correction can be admitted. The corrected point remains a representative point,
not an observed home, institution location, or journey.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_mass.site_geometry import snap_points,ROAD_PREFIX,N_VERTICES

REQUIRED={'source_record_id','expected_lat','expected_lon','corrected_lat','corrected_lon',
    'source_id','source_url','coordinate_kind','correction_basis','evidence_path','evidence_sha256'}
KINDS={'osm_place_node','official_published_point','published_settlement_polygon_representative_point'}
QUALITY_COLUMNS=['verified_component_id','verified_component_node_count','verified_road_out_degree',
                 'verified_road_in_degree','small_component_under_100_nodes']


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def validate_corrections(reference,endpoints,corrections,*,evidence_root=REPO):
    if not REQUIRED <= set(corrections):raise ValueError('Incomplete geography correction registry: '+str(REQUIRED-set(corrections)))
    if corrections.empty:raise ValueError('An explicit nonempty correction registry is required')
    if corrections.source_record_id.isna().any() or corrections.source_record_id.duplicated().any():
        raise ValueError('Correction identities must be non-null and unique')
    if reference.source_record_id.dropna().duplicated().any() or endpoints.source_record_id.duplicated().any():
        raise ValueError('Input current settlement identities are not unique')
    for column in REQUIRED-{'expected_lat','expected_lon','corrected_lat','corrected_lon'}:
        if corrections[column].isna().any() or corrections[column].astype(str).str.strip().eq('').any():
            raise ValueError('Missing correction evidence field: '+column)
    if not corrections.coordinate_kind.isin(KINDS).all():raise ValueError('Unrecognised correction coordinate kind')
    numeric=corrections[['expected_lat','expected_lon','corrected_lat','corrected_lon']].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():raise ValueError('Correction coordinates must be finite')
    if not corrections.corrected_lat.between(-90,90).all() or not corrections.corrected_lon.between(-180,180).all():
        raise ValueError('Corrected coordinate outside Earth')
    ref=reference.set_index('source_record_id');end=endpoints.set_index('source_record_id')
    provenance=[]
    for row in corrections.itertuples(index=False):
        sid=str(row.source_record_id)
        if sid not in ref.index or sid not in end.index:raise ValueError('Correction identity is absent from input reference/endpoints: '+sid)
        old=ref.loc[sid]
        if not np.allclose([old.lat,old.lon],[row.expected_lat,row.expected_lon],rtol=0,atol=1e-12):
            raise ValueError('Correction expected coordinates differ from the pinned input: '+sid)
        if np.allclose([old.lat,old.lon],[row.corrected_lat,row.corrected_lon],rtol=0,atol=1e-12):
            raise ValueError('Correction does not change the coordinate: '+sid)
        relative=Path(str(row.evidence_path))
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Evidence must be a safe repository-relative path')
        evidence=Path(evidence_root)/relative
        if not evidence.is_file() or sha(evidence)!=str(row.evidence_sha256):
            raise ValueError('Correction evidence SHA256 differs or source is missing: '+str(relative))
        if not str(row.source_url).startswith('https://'):raise ValueError('Correction source URL must be explicit HTTPS')
        if row.coordinate_kind=='published_settlement_polygon_representative_point':
            from shapely.geometry import shape,Point
            raw=json.loads(evidence.read_text())
            geometry=shape(raw['geometry'] if raw.get('type')=='Feature' else raw)
            if geometry.geom_type not in {'Polygon','MultiPolygon'} or not geometry.is_valid:
                raise ValueError('Coordinate evidence is not a valid settlement polygon')
            if not geometry.covers(Point(float(row.corrected_lon),float(row.corrected_lat))):
                raise ValueError('Corrected representative point lies outside its evidenced polygon')
            if geometry.covers(Point(float(row.expected_lon),float(row.expected_lat))):
                raise ValueError('Original point is already inside the polygon; claimed correction needs separate review')
        provenance.append({'source_record_id':sid,'evidence_path':relative.as_posix(),
                           'evidence_sha256':str(row.evidence_sha256),'source_id':str(row.source_id)})
    return provenance


def derive_inputs(reference,endpoints,corrections,roads,*,evidence_root=REPO,max_snap_km=10.):
    provenance=validate_corrections(reference,endpoints,corrections,evidence_root=evidence_root)
    point=corrections.copy().rename(columns={'corrected_lat':'site_lat','corrected_lon':'site_lon'})
    snapped=snap_points(point,roads,max_snap_km=max_snap_km)
    if not snapped.accepted_snap.all():raise ValueError('Corrected representative point exceeds explicit road snap screen')
    ref=reference.copy();end=endpoints.copy()
    for table in [ref,end]:table['pilot_geography_correction_applied']=False
    ref['pilot_original_lat']=ref.lat;ref['pilot_original_lon']=ref.lon
    changed=['road_node_index','snap_km','road_endpoint_accepted','weak_component',*QUALITY_COLUMNS]
    for column in changed:
        if column in end:end['pilot_original_'+column]=end[column]
    for row in snapped.itertuples(index=False):
        rm=ref.source_record_id.eq(row.source_record_id);em=end.source_record_id.eq(row.source_record_id)
        ref.loc[rm,['lat','lon']]=[row.site_lat,row.site_lon]
        ref.loc[rm,'pilot_geography_correction_applied']=True
        end.loc[em,'pilot_geography_correction_applied']=True
        for table,mask in [(ref,rm),(end,em)]:
            for source,target in [('source_id','pilot_coordinate_source_id'),('source_url','pilot_coordinate_source_url'),
                ('coordinate_kind','pilot_coordinate_kind'),('correction_basis','pilot_coordinate_correction_basis'),
                ('evidence_sha256','pilot_coordinate_evidence_sha256')]:
                if target not in table:table[target]=None
                table.loc[mask,target]=getattr(row,source)
        for target,source in [('road_node_index','road_node_index'),('snap_km','snap_km'),
                              ('road_endpoint_accepted','accepted_snap'),('weak_component','weak_component')]:
            if hasattr(row,source):end.loc[em,target]=getattr(row,source)
        # These checks described the OLD vertex. They cannot silently be reused
        # for a new vertex. The independently read weak-component ID is retained.
        for column in QUALITY_COLUMNS:
            if column in end:
                if column=='small_component_under_100_nodes':end[column]=end[column].astype('boolean')
                end.loc[em,column]=pd.NA
        end.loc[em,'small_component_is_quality_risk_not_proven_unreachable']=True
        end.loc[em,'pilot_endpoint_quality_reverification_required']=True
        end.loc[em,'pilot_road_osm_node']=row.road_osm_node
        end.loc[em,'pilot_road_snap_lat']=row.road_snap_lat
        end.loc[em,'pilot_road_snap_lon']=row.road_snap_lon
    return ref,end,snapped,{'schema':'sgrt.saratov.geography_overlay.v1',
        'corrected_settlement_records':len(corrections),'evidence':provenance,
        'original_reference_and_endpoint_sources_modified':False,
        'correction_changes_population_or_credit_flags':False,
        'old_endpoint_quality_reused_for_corrected_vertex':False,
        'road_snap_screen_km':float(max_snap_km),'connector_scenario_kmh':15.,
        'point_is_building_or_observed_trip_location':False}


def apply_provider_proxies(providers,reference,endpoints):
    """Move only declared NP-point proxies; physical institutions stay put."""
    if 'pilot_geography_correction_applied' not in reference:
        raise ValueError('Derived reference has no explicit geography overlay')
    corrected=reference[reference.pilot_geography_correction_applied.eq(True)]
    ep=endpoints.set_index('source_record_id')
    out=providers.copy();out['pilot_coordinate_overlay_applied']=False
    original_columns=['site_lat','site_lon','road_node_index','destination_connector_minutes',
                      'accepted_snap','routable_provider']
    for column in original_columns:out['pilot_original_'+column]=out[column]
    changes=[]
    for row in corrected.itertuples(index=False):
        mask=out.correctsource_record_id.eq(row.source_record_id)&out.input_kind.eq('np')
        if not mask.any():continue
        old=out.loc[mask]
        if not np.allclose(old.site_lat,row.pilot_original_lat,atol=1e-12,rtol=0) or not np.allclose(old.site_lon,row.pilot_original_lon,atol=1e-12,rtol=0):
            raise ValueError('NP proxy cached point differs from corrected source original: '+str(row.source_record_id))
        e=ep.loc[row.source_record_id]
        out.loc[mask,'site_lat']=row.lat;out.loc[mask,'site_lon']=row.lon
        out.loc[mask,'road_node_index']=e.road_node_index
        out.loc[mask,'destination_connector_minutes']=4.*float(e.snap_km)
        accepted=bool(e.road_endpoint_accepted) and np.isfinite(e.road_node_index) and 0<=e.road_node_index<N_VERTICES and float(e.road_node_index).is_integer() and np.isfinite(e.snap_km) and 0<=e.snap_km<=10
        out.loc[mask,'accepted_snap']=accepted;out.loc[mask,'routable_provider']=accepted
        out.loc[mask,'pilot_coordinate_overlay_applied']=True
        changes.extend(out.loc[mask,'catalog_id'].astype(str).tolist())
    return out,{'np_point_proxies_corrected':len(changes),'corrected_catalog_ids':sorted(changes),
                'physical_site_coordinates_modified':False,'np_function_presence_modified':False}


def run(reference,endpoints,corrections,road_nodes,road_catalog,output,*,evidence_root=REPO):
    reference,endpoints,corrections,road_nodes,output=map(Path,[reference,endpoints,corrections,road_nodes,output])
    if reference.resolve()==(output/'analysis_reference.parquet').resolve() or endpoints.resolve()==(output/'endpoint_network_quality.parquet').resolve():
        raise ValueError('Derived outputs must not overwrite either immutable input')
    cat=json.loads(Path(road_catalog).read_text());specs={s['path']:s for s in cat['files'] if s['path'].startswith(ROAD_PREFIX)}
    parts=sorted(road_nodes.glob('part_*.parquet'))
    if len(parts)!=24 or len(specs)!=24:raise ValueError('All 24 pinned road-node parts are required')
    hashes=[]
    for part in parts:
        spec=specs[ROAD_PREFIX+part.name];digest=sha(part)
        if part.stat().st_size!=spec['bytes'] or digest!=cat['objects'][spec['blob']]['sha256']:
            raise ValueError('Road-node source differs: '+part.name)
        hashes.append({'path':ROAD_PREFIX+part.name,'bytes':part.stat().st_size,'sha256':digest})
    roads=pd.read_parquet(road_nodes,columns=['node_index','osm_id','lat','lon','weak_component'])
    if len(roads)!=N_VERTICES or not np.array_equal(roads.node_index,np.arange(N_VERTICES)):
        raise ValueError('Road-node axis differs from pinned graph')
    a,b,snapped,summary=derive_inputs(pd.read_parquet(reference),pd.read_parquet(endpoints),
        pd.read_csv(corrections,dtype={'source_record_id':str}),roads,evidence_root=evidence_root)
    output.mkdir(parents=True,exist_ok=True)
    for name,table in [('analysis_reference',a),('endpoint_network_quality',b),('coordinate_corrections',snapped)]:
        table.to_parquet(output/(name+'.parquet'),index=False,compression='zstd')
    summary['inputs']=[{'role':role,'filename':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for role,p in [('reference',reference),('endpoints',endpoints),('curated_corrections',corrections)]]
    summary['road_coordinate_sources']=hashes
    (output/'geography_overlay_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ['reference','endpoints','corrections','road-nodes','road-catalog','output']:
        p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--evidence-root',type=Path,default=REPO)
    a=p.parse_args()
    print(json.dumps(run(a.reference,a.endpoints,a.corrections,a.road_nodes,a.road_catalog,a.output,
                        evidence_root=a.evidence_root),ensure_ascii=False,indent=2))

if __name__=='__main__':main()

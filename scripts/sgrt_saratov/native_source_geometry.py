"""Recover original 2021 OSM way geometry from an immutable complete source.

The source PBF is already published in six parts. Selection uses the exact V2
static-car profile and source ways touching at least one reached graph vertex.
Only two source passes are needed: way references, then the required node IDs.
There is no global location index and no substitution with current OSM.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import time
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_zero.cloud_common_systems import RemoteZip
from scripts.research_data import archive_member
from scripts.sgrt_field_pilot.input_inventory import catalog_source,digest

PBF_PREFIX='research/sgrt_word_completion_20261021/transport/cycle06_network2021/sources/'
PBF_NAME='roads2021_reference_complete.osm.pbf'
PBF_BYTES=491143669
PBF_SHA256='294807be65aa2bf8061bd8eeb91350160523b34a30322dfa196eb0ce5b8d5520'
PROFILE_PATH='archive/sgrt_2026-10-18_21/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/road_profile.py'
PROFILE_SHA256='54084592e074a831c07d492a6392153c7926b4ffef97b4176c82874c3dd90b95'
POLICY_SHA256='ba574904411bb07bb24a90a65619ea0e6786c96d5dcda120a561670229c8e897'
HISTORICAL_COMMIT='85aebaff43d1b8ecf7314a697add2b2370f93d73'
GRAPH_SHA256='a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366'


def source_specs():
    return [catalog_source(REPO/'data/catalog.json',PBF_PREFIX+PBF_NAME+f'.part{n:03d}') for n in range(6)]


def load_profile():
    path=REPO/PROFILE_PATH;policy=path.with_name('finite_access_policy_proposal.json')
    if digest(path)!=PROFILE_SHA256 or digest(policy)!=POLICY_SHA256:
        raise ValueError('Historical V2 profile/policy bytes differ from the graph source')
    spec=importlib.util.spec_from_file_location('sgrt_exact_2021_v2_profile',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def restore_pbf(path,source_parts=None):
    """Verify an existing complete PBF, or restore it without replacing files."""
    specs=source_specs();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.stat().st_size!=PBF_BYTES or digest(path)!=PBF_SHA256:
            raise ValueError('Existing PBF differs; it will not be replaced')
        return {'combined_bytes':PBF_BYTES,'combined_sha256':PBF_SHA256,'source_files':specs,
                'mode':'existing_complete_original_bytes_verified'}
    if path.resolve().is_relative_to(REPO) or shutil.disk_usage(path.parent).free<PBF_BYTES+500_000_000:
        raise ValueError('Use an external source directory with enough capacity')
    catalogue=json.loads((REPO/'data/catalog.json').read_text());temporary=path.with_suffix('.incoming')
    h=hashlib.sha256();total=0;facts=[]
    try:
        with temporary.open('xb') as out:
            for n,spec in enumerate(specs):
                if source_parts is not None:
                    part=Path(source_parts)/(PBF_NAME+f'.part{n:03d}');data=part.read_bytes()
                    mode='local_pinned_part'
                else:
                    row=next(x for x in catalogue['files'] if x['path']==spec['path'])
                    obj=catalogue['objects'][row['blob']]
                    asset=next(x for x in catalogue['assets'] if x['asset']==row['asset'])
                    remote=RemoteZip(asset['url'],asset['bytes'])
                    with zipfile.ZipFile(remote) as archive:data=archive.read(archive_member(obj,row['blob']))
                    mode='public_http_ranges_part_sha_verified'
                if len(data)!=spec['bytes'] or hashlib.sha256(data).hexdigest()!=spec['sha256']:
                    raise ValueError('Original PBF part differs: '+spec['path'])
                out.write(data);h.update(data);total+=len(data);facts.append({'path':spec['path'],'mode':mode})
                print(json.dumps({'restored_part':n,'combined_bytes':total}),flush=True)
        if total!=PBF_BYTES or h.hexdigest()!=PBF_SHA256:raise ValueError('Combined historical PBF differs')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return {'combined_bytes':total,'combined_sha256':h.hexdigest(),'source_files':specs,'part_retrieval':facts,
            'mode':'all_six_original_parts_and_combined_bytes_verified'}


def selected_way_row(way_id,refs,tags,version,timestamp,profile):
    """Apply precisely the source V2 non-geometric profile to a selected way."""
    if tags.get('highway') not in profile.SPEED:return None,'outside_historical_highway_profile'
    reasons=profile.exclusions(tags)
    if reasons:return None,';'.join(reasons)
    if len(refs)<2:return None,'fewer_than_two_source_vertices'
    raw=json.dumps(tags,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return {'way_id':int(way_id),'refs':list(map(int,refs)),'speed_kmh':float(profile.speed(tags)),
        'oneway':int(profile.oneway(tags)),'highway':tags['highway'],'osm_version':int(version),
        'source_timestamp':str(timestamp),'all_source_tags_sha256':hashlib.sha256(raw.encode()).hexdigest(),
        'source_tags_json':raw,'source_profile_sha256':PROFILE_SHA256,'geometry_crs':'EPSG:4326'},None


def extract(pbf,needed_vertices,output,source_parts=None):
    import osmium
    source=restore_pbf(pbf,source_parts);profile=load_profile();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    needed=pd.read_parquet(needed_vertices,columns=['osm_id'])
    if needed.osm_id.isna().any() or needed.osm_id.duplicated().any():
        raise ValueError('Needed graph OSM IDs must be known and unique')
    numeric=pd.to_numeric(needed.osm_id,errors='raise').to_numpy()
    if not np.isfinite(numeric).all() or (numeric!=np.floor(numeric)).any():raise ValueError('Noninteger graph OSM ID')
    wanted=set(map(int,numeric));rows=[];refs_needed=set();reasons=Counter();seen=0;touching=0
    start=time.monotonic()
    for way in osmium.FileProcessor(str(pbf),entities=osmium.osm.WAY):
        seen+=1
        refs=[n.ref for n in way.nodes]
        if wanted.isdisjoint(refs):continue
        touching+=1
        row,reason=selected_way_row(way.id,refs,dict(way.tags),way.version,way.timestamp,profile)
        if row is None:reasons[reason]+=1;continue
        rows.append(row);refs_needed.update(refs)
    print(json.dumps({'way_pass_source_objects':seen,'touching_ways':touching,'profile_allowed_selected_ways':len(rows),
        'required_original_nodes':len(refs_needed),'seconds':round(time.monotonic()-start,3)}),flush=True)
    found={}
    proc=osmium.FileProcessor(str(pbf),entities=osmium.osm.NODE).with_filter(osmium.filter.IdFilter(refs_needed))
    for node in proc:
        if not node.location.valid():continue
        lat,lon=float(node.lat),float(node.lon)
        if not np.isfinite([lat,lon]).all() or not (-90<=lat<=90 and -180<=lon<=180):continue
        if node.id in found:raise ValueError('Duplicate source OSM node identity')
        found[int(node.id)]=(lat,lon)
    missing=refs_needed-set(found);bad=[row for row in rows if not missing.isdisjoint(row['refs'])]
    for row in bad:reasons['missing_original_source_node_geometry']+=1
    rows=[row for row in rows if missing.isdisjoint(row['refs'])]
    if len({row['way_id'] for row in rows})!=len(rows):raise ValueError('Duplicate source way identity')
    retained_refs=set(ref for row in rows for ref in row['refs'])
    schema=pa.schema([('way_id',pa.int64()),('refs',pa.list_(pa.int64())),('speed_kmh',pa.float64()),
        ('oneway',pa.int8()),('highway',pa.string()),('osm_version',pa.int32()),('source_timestamp',pa.string()),
        ('all_source_tags_sha256',pa.string()),('source_tags_json',pa.string()),('source_profile_sha256',pa.string()),
        ('geometry_crs',pa.string())])
    rows.sort(key=lambda r:r['way_id'])
    pq.write_table(pa.Table.from_pylist(rows,schema=schema),output/'ways.parquet',compression='zstd')
    nodes=pd.DataFrame([(n,*found[n],'EPSG:4326') for n in sorted(retained_refs)],columns=['osm_id','lat','lon','geometry_crs'])
    nodes.to_parquet(output/'nodes.parquet',index=False,compression='zstd')
    summary={'schema':'sgrt.saratov_native_source_geometry.v1','source_pbf':source,'graph_sha256':GRAPH_SHA256,
        'historical_code_commit':HISTORICAL_COMMIT,'source_profile_path':PROFILE_PATH,
        'source_profile_sha256':PROFILE_SHA256,'source_policy_sha256':POLICY_SHA256,
        'osmium_version':importlib.metadata.version('osmium'),'geometry_crs':'EPSG:4326',
        'needed_graph_vertex_count':len(wanted),'source_way_objects_scanned':seen,'source_ways_touching_needed_vertex':touching,
        'selected_valid_profile_ways':len(rows),'selected_original_geometry_nodes':len(nodes),
        'relevant_profile_or_geometry_exclusions':dict(sorted(reasons.items())),
        'source_nodes_missing_after_reference_complete_pass':len(missing),'source_ways_with_missing_geometry':len(bad),
        'needed_vertices_sha256':digest(needed_vertices),
        'selection':'Source ways containing any reached graph OSM node, passing exactly the historical V2 static-car profile and complete original source geometry checks; all allowed parallel ways retained.',
        'compression':'Native cuts must use the complete graph OSM junction set, not only reached nodes. Reference order is preserved.',
        'no_current_osm_geometry':True,'no_global_node_location_index':True,'paths':{'pbf':str(pbf),'needed_vertices':str(needed_vertices)},
        'outputs':{n:{'bytes':(output/n).stat().st_size,'sha256':digest(output/n)} for n in ['ways.parquet','nodes.parquet']}}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['needed_graph_vertex_count','selected_valid_profile_ways','selected_original_geometry_nodes','source_ways_with_missing_geometry','no_current_osm_geometry']}),flush=True)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pbf',type=Path,required=True)
    p.add_argument('--needed-road-vertices',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-parts',type=Path,help='Optional directory with the six already downloaded pinned parts')
    a=p.parse_args();extract(a.pbf,a.needed_road_vertices,a.output,a.source_parts)

if __name__=='__main__':main()

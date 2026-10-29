"""Directed nearest-school competition on native roads in a stated display window.

National provider competition is solved before local drawing. The Piterka60
window is a map extent, not a school catchment limit. Official campus proxies
are settlement centroids, never invented school-building coordinates. Coarse
polygons can overlap; only road costs/assignments have a network interpretation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape, mapping, LineString
from shapely.ops import transform
from pyproj import Transformer

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_mass.routes import load_graph, weighted_multisource, GRAPH_SHA256
from scripts.sgrt_saratov.native_road_shapes import spherical_lengths
from scripts.sgrt_saratov.generalized_maps import generalize_corridor, protect_water, polygonal

THRESHOLDS=(10.,20.,30.,60.)
PITERKA='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:117733'
DISPLAY_CENTRE_CLASSES={'117733':0,'117699':1,'117685':2,'117707':3}
DISPLAY_CLASS_LABELS={'0':'Питерка','1':'Мироновка','2':'Агафоновка','3':'Новотулка','4':'Другие известные школьные площадки'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def edge_intervals(cost_u,cost_v,weight,oneway,thresholds=THRESHOLDS):
    """Intervals along u->v with exact lower envelope of permitted endpoint exits.

    Entries are (start_fraction,end_fraction,exit_endpoint,time_band,midpoint_cost).
    Cost varies linearly in original spherical path length, matching edge weight.
    """
    if weight<0 or not np.isfinite(weight) or oneway not in {-1,0,1}:raise ValueError('Invalid road')
    cuts={0.,1.}
    if oneway==0 and np.isfinite(cost_u) and np.isfinite(cost_v) and weight>0:
        cuts.add(float(np.clip((weight+cost_v-cost_u)/(2*weight),0,1)))
    for t in thresholds:
        if weight>0:
            if oneway<=0 and np.isfinite(cost_u):cuts.add(float(np.clip((t-cost_u)/weight,0,1)))
            if oneway>=0 and np.isfinite(cost_v):cuts.add(float(np.clip(1-(t-cost_v)/weight,0,1)))
    cuts=sorted(cuts);result=[]
    for a,b in zip(cuts[:-1],cuts[1:]):
        if b-a<=1e-12:continue
        x=(a+b)/2
        u=cost_u+x*weight if oneway<=0 else np.inf
        v=cost_v+(1-x)*weight if oneway>=0 else np.inf
        endpoint='u' if u<=v else 'v';cost=min(u,v)
        if np.isfinite(cost) and cost<=max(thresholds):
            band=int(np.searchsorted(thresholds,cost,side='left'))
            result.append((a,b,endpoint,band,float(cost)))
    return result


def fraction_geometry(xy,start,end):
    """Cut WGS84 polyline by original spherical-length fractions, preserving bends."""
    xy=np.asarray(xy,dtype=float)
    lengths=np.r_[0.,np.cumsum(spherical_lengths(xy[:,1],xy[:,0]))]
    total=lengths[-1]
    if total<=0 or end<=start:return None
    def at(f):
        target=f*total;i=min(max(int(np.searchsorted(lengths,target,side='right'))-1,0),len(xy)-2)
        d=lengths[i+1]-lengths[i]
        return xy[i] if d<=0 else xy[i]+(target-lengths[i])/d*(xy[i+1]-xy[i])
    middle=xy[(lengths>start*total)&(lengths<end*total)]
    out=np.vstack([at(start),middle,at(end)])
    return LineString(out) if len(np.unique(out,axis=0))>1 else None


def prepare_seeds(catalog,roster,presence,official):
    baseline=catalog[catalog.family.eq('school')&catalog.routable_provider.eq(True)].copy()
    baseline=baseline.sort_values('catalog_id').reset_index(drop=True)
    baseline['source_record_id']=baseline.correctsource_record_id
    baseline['anchor_precision']=baseline.location_precision
    known=set(presence.loc[presence.family.eq('school'),'source_record_id'].dropna().astype(str))
    axis=roster.set_index('source_record_id');extra=[]
    for r in official.itertuples(index=False):
        # Mixed official education registries also contain kindergartens.
        # A settlement-level preschool witness cannot seed a school field.
        if r.service_code!='school_general' or r.eligible_np_presence_proxy not in (True,1,'true','True'):continue
        sid=str(r.source_record_id)
        if sid in known or sid not in axis.index:continue
        known.add(sid);a=axis.loc[sid]
        if not bool(a.road_endpoint_accepted) or pd.isna(a.road_node_index) or not 0<=a.snap_km<=10:continue
        extra.append({'catalog_id':str(r.provider_id),'source_record_id':sid,
            'provider_destination_key':'np:'+sid,'provider_name':r.name,
            'road_node_index':int(a.road_node_index),'destination_connector_minutes':4*float(a.snap_km),
            'anchor_precision':'settlement_point_not_building','source_id':r.source_id})
    return baseline,pd.concat([baseline,pd.DataFrame(extra)],ignore_index=True),pd.DataFrame(extra)




def omit_empty_display_features(features):
    kept=[];omissions=[]
    for f in features:
        geometry=shape(f['geometry'])
        if geometry.is_empty:
            omissions.append({'id':f['properties'].get('id'),'name':f['properties'].get('name'),
                'reason':'clipped_outside_display_window_or_zero_area_after_cartographic_generalization',
                'road_assignments_retained':True})
        else:kept.append(f)
    return kept,omissions


def compare_scenarios(output):
    output=Path(output);parts=[]
    for scenario in ['baseline','documented_campus_enriched']:
        d=pd.read_parquet(output/(scenario+'_road_nodes.parquet'))
        seeds=pd.read_parquet(output/(scenario+'_school_seeds.parquet'))
        d['destination_key']=None;valid=d.seed_index.ge(0)
        d.loc[valid,'destination_key']=seeds.iloc[d.loc[valid,'seed_index'].astype(int)].provider_destination_key.to_numpy()
        parts.append(d[['node_index','minutes_to_nearest_school','destination_key']].rename(columns={
            'minutes_to_nearest_school':scenario+'_minutes','destination_key':scenario+'_destination_key'}))
    d=parts[0].merge(parts[1],on='node_index',validate='one_to_one')
    a=d.baseline_minutes.to_numpy();b=d.documented_campus_enriched_minutes.to_numpy()
    both=np.isfinite(a)&np.isfinite(b)
    if np.any(b[both]>a[both]+1e-8):raise ValueError('Added school supply increased nearest time')
    d['changed_destination']=d.baseline_destination_key.fillna('').ne(d.documented_campus_enriched_destination_key.fillna(''))
    d['reduction_minutes']=np.where(both,a-b,np.nan)
    d.to_parquet(output/'road_node_scenario_comparison.parquet',index=False)
    return {'sampled_native_road_nodes':len(d),'changed_destination_nodes':int(d.changed_destination.sum()),
        'finite_comparable_nodes':int(both.sum()),'nodes_with_lower_time':int((d.reduction_minutes>1e-8).sum()),
        'median_reduction_minutes_over_all_comparable_road_nodes':float(np.median(d.reduction_minutes[both])),
        'maximum_reduction_minutes':float(np.max(d.reduction_minutes[both])),
        'denominator':'native_road_nodes_in_display_window_not_settlements_or_people'}


def run(graph_dir,native_path,reachable_path,provider_path,roster_path,presence_path,official_paths,water_path,output,resume=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    roster=pd.read_parquet(roster_path);catalog=pd.read_parquet(provider_path);presence=pd.read_parquet(presence_path)
    official=pd.concat([pd.read_csv(p) for p in official_paths],ignore_index=True)
    baseline,enriched,extra=prepare_seeds(catalog,roster,presence,official)
    native=pd.read_parquet(native_path);roads=shapely.from_wkb(native.native_geometry_wkb.to_numpy())
    to_metric=Transformer.from_crs(4326,32638,always_xy=True);to_wgs=Transformer.from_crs(32638,4326,always_xy=True)
    reach=pd.read_parquet(reachable_path);row=reach[reach.centre_id.eq(PITERKA)&reach.minutes.eq(60.)].iloc[0]
    window_metric=shapely.from_wkb(row.reachable_road_geometry_wkb).buffer(250)
    window=transform(to_wgs.transform,window_metric)
    display_window=generalize_corridor(window_metric,expansion_m=1500.)
    keep=shapely.intersects(roads,window);native=native.loc[keep].reset_index(drop=True);roads=roads[keep]
    water=polygonal(shapely.union_all([shape(f['geometry']) for f in json.loads(Path(water_path).read_text())['features']]))
    water_metric=transform(to_metric.transform,water).intersection(window_metric.buffer(5000))
    water_metric=polygonal(shapely.union_all([g for g in shapely.get_parts(water_metric) if g.area>=5e6])).simplify(800,preserve_topology=True)
    graph=load_graph(graph_dir);reverse=graph.T.tocsr();del graph
    node_subset=np.unique(np.r_[native.u.to_numpy(),native.v.to_numpy()]).astype('int64')
    summary={'schema':'sgrt.saratov.school_competition.v1','graph_sha256':GRAPH_SHA256,
        'display_window':'native_segments_intersecting_prior_Piterka60_road_corridor_boundary_segments_retained_full_not_school_radius',
        'native_segments_in_window':len(native),'new_campus_proxies':len(extra),
        'thresholds_minutes':THRESHOLDS,'centre_display_class_labels':DISPLAY_CLASS_LABELS,'scenarios':[],
        'cartography':{'road_corridor_m':250,'buffer_quadrant_segments':2,'expansion_m':1250,'closing_m':2000,'simplification_m':600,
            'fill_holes_under_m2':25e6,'display_window_expansion_m':1500,'water_simplification_m':800,
            'minimum_water_component_m2':5e6,'coordinate_precision_degrees':1e-7},
        'limits':['School grade coverage/admission/currentoperation unknown unless separately evidenced.',
            'Min-only search stores one deterministic winner; all equal-cost alternatives not enumerated.',
            'Road costs include destination connector; no off-road household travel inferred.',
            'Generalized polygon overlap is cartographic, not a second observed school assignment.',
            'National transport graph2021, school inventorymainly2026, official assignments2025.']}
    extra.to_parquet(output/'new_campus_proxies.parquet',index=False)
    for scenario,seeds in [('baseline',baseline),('documented_campus_enriched',enriched)]:
        seeds=seeds.reset_index(drop=True)
        print(json.dumps({'event':'school_competition_search','scenario':scenario,'seeds':len(seeds)}),flush=True)
        if resume and (output/(scenario+'_road_nodes.parquet')).exists():
            old_seeds=pd.read_parquet(output/(scenario+'_school_seeds.parquet'))
            cols=['catalog_id','road_node_index','destination_connector_minutes']
            if not old_seeds[cols].equals(seeds[cols]):raise ValueError('Resume seeds differ')
            nodes=pd.read_parquet(output/(scenario+'_road_nodes.parquet'))
            if not np.array_equal(nodes.node_index.to_numpy(),node_subset):raise ValueError('Resume node axis differs')
            distance=np.full(reverse.shape[0],np.inf);selected=np.full(reverse.shape[0],-1,dtype='int64')
            distance[node_subset]=nodes.minutes_to_nearest_school;selected[node_subset]=nodes.seed_index
        else:
            distance,selected=weighted_multisource(reverse,seeds.road_node_index.to_numpy(dtype='int64'),
                seeds.destination_connector_minutes.to_numpy(dtype=float))
            nodes=pd.DataFrame({'node_index':node_subset,'minutes_to_nearest_school':distance[node_subset],
                'seed_index':selected[node_subset]})
        valid=nodes.seed_index.ge(0)
        nodes.loc[valid,'provider_id']=seeds.iloc[nodes.loc[valid,'seed_index'].astype(int)].catalog_id.to_numpy()
        nodes.to_parquet(output/(scenario+'_road_nodes.parquet'),index=False)
        pieces=[]
        for i,r in enumerate(native.itertuples(index=False)):
            for a,b,exit,band,midcost in edge_intervals(distance[r.u],distance[r.v],float(r.edge_minutes),int(r.oneway)):
                idx=int(selected[r.u if exit=='u' else r.v])
                if idx<0:continue
                geom=fraction_geometry(np.asarray(roads[i].coords),a,b)
                if geom is None:continue
                if geom.is_empty:continue
                s=seeds.iloc[idx]
                pieces.append({'u':int(r.u),'v':int(r.v),'way_id':int(r.way_id),'start_fraction':a,
                    'end_fraction':b,'exit_endpoint':exit,'class_index':band,
                    'minutes_band_upper':THRESHOLDS[band],'midpoint_minutes':midcost,
                    'provider_id':s.catalog_id,'destination_key':s.provider_destination_key,
                    'destination_np_id':s.source_record_id,'provider_name':s.provider_name,
                    'anchor_precision':s.anchor_precision,'geometry_crs':'EPSG:4326','geometry_wkb':shapely.to_wkb(geom)})
        table=pd.DataFrame(pieces);table.to_parquet(output/(scenario+'_road_competition.parquet'),index=False)
        seeds.to_parquet(output/(scenario+'_school_seeds.parquet'),index=False)
        features=[];cumulative_features=[]
        used=table[['provider_id','destination_key','destination_np_id','provider_name','anchor_precision']].drop_duplicates('provider_id')
        roadfeatures=[]
        for r in table.itertuples(index=False):
            roadfeatures.append({'type':'Feature','properties':{'provider_id':r.provider_id,'destination_key':r.destination_key,
                'class_index':int(r.class_index),'minutes_band_upper':r.minutes_band_upper,
                'anchor_precision':r.anchor_precision},'geometry':mapping(shapely.from_wkb(r.geometry_wkb))})
        write(output/(scenario+'_roads.geojson'),{'type':'FeatureCollection','features':roadfeatures})
        for j,(key,part) in enumerate(table.groupby('destination_key',sort=True)):
            geoms=shapely.from_wkb(part.geometry_wkb.to_numpy());line=shapely.union_all(geoms)
            metric=transform(to_metric.transform,line);corridor=shapely.union_all(shapely.buffer(shapely.get_parts(metric),250,quad_segs=2))
            coarse=generalize_corridor(corridor)
            coarse=protect_water(coarse,corridor,water_metric)
            # Drawing does not expand the chosen map extent indefinitely.
            coarse=coarse.intersection(display_window)
            p=part.iloc[0];npnames=roster.set_index('source_record_id')['name'].to_dict();display_name=npnames.get(p.destination_np_id,None);display_name=display_name if pd.notna(display_name) else (p.provider_name if pd.notna(p.provider_name) else 'Школьная площадка: населённый пункт не установлен');props={'id':key,'name':str(display_name),'destination_np_id':p.destination_np_id if pd.notna(p.destination_np_id) else None,
                'class_index':DISPLAY_CENTRE_CLASSES.get(str(p.destination_np_id).rsplit(':',1)[-1],4),'source_count':int(part.provider_id.nunique()),'road_pieces':len(part),
                'interpretation':'generalized_display_of_nearest_known_school_roads_not_exact_offroad_catchment',
                'scenario':scenario,'anchor_precisions':sorted(part.anchor_precision.dropna().unique().tolist())}
            features.append({'type':'Feature','properties':props,'geometry':mapping(polygonal(shapely.set_precision(polygonal(transform(to_wgs.transform,coarse)),1e-7)))})
        previous=shapely.Polygon()
        for band,t in enumerate(THRESHOLDS):
            part=table[table.minutes_band_upper.le(t)]
            if part.empty:continue
            line=shapely.union_all(shapely.from_wkb(part.geometry_wkb.to_numpy()))
            metric=transform(to_metric.transform,line);corridor=shapely.union_all(shapely.buffer(shapely.get_parts(metric),250,quad_segs=2))
            current_metric=protect_water(generalize_corridor(corridor),corridor,water_metric)
            current=shapely.set_precision(polygonal(shapely.set_precision(polygonal(transform(to_wgs.transform,current_metric)),1e-7)),0).union(previous)
            b=polygonal(current.difference(previous));previous=current
            cumulative_features.append({'type':'Feature','properties':{'class_index':band,'minutes':t,
                'name':str(t)+' мин до ближайшей известной школы','scenario':scenario,
                'interpretation':'coarse_display_timeband_not_precise_offroad_isochrone'},'geometry':mapping(b)})
        features,display_omissions=omit_empty_display_features(features)
        cumulative_features,timeband_omissions=omit_empty_display_features(cumulative_features)
        write(output/(scenario+'_zones.geojson'),{'type':'FeatureCollection','features':features})
        write(output/(scenario+'_nearest_timebands.geojson'),{'type':'FeatureCollection','features':cumulative_features})
        if any(shape(f['geometry']).is_empty or not shape(f['geometry']).is_valid for f in features+cumulative_features):raise ValueError('Invalid display geometry')
        summary['scenarios'].append({'scenario':scenario,'national_seeds':len(seeds),'displayed_destination_groups':len(features),'road_destination_groups':int(table.destination_key.nunique()),
            'empty_display_omissions':display_omissions,'empty_timeband_omissions':timeband_omissions,
            'road_pieces':len(table),'geometry_vertices':int(sum(shapely.get_num_coordinates(shape(f['geometry'])) for f in features)),
            'displayed_provider_ids':used.provider_id.tolist()})
        del distance,selected
    summary['road_node_comparison']=compare_scenarios(output)
    sources=[native_path,reachable_path,provider_path,roster_path,presence_path,water_path,*official_paths]
    summary['inputs']=[{'path':str(p),'sha256':sha(p),'bytes':Path(p).stat().st_size} for p in sources]
    write(output/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['graph-dir','native-path','reachable-path','provider-path','roster-path','presence-path','water-path','output']:
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--official-paths',nargs='+',type=Path,required=True)
    a=p.parse_args();run(**vars(a))
if __name__=='__main__':main()

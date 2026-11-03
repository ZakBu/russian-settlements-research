"""Inspect the magnitude of native-road departures from the pinned outline.

A domestic edge requires its complete original geometry to be covered.
Keeping both endpoints alone is insufficient for a bending road.
"""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box,Point,LineString
from shapely.ops import transform
from pyproj import Transformer
from scripts.sgrt_zero.cloud_common_systems import acquire
from scripts.sgrt_saratov.country_scope import load_russia
from scripts.sgrt_saratov.source_inventory import BOUNDARY_URL


def domestic_mask(geometries,mask):
    return shapely.covered_by(geometries,mask)



def inside_directed_arcs(native,mask):
    """Rebuild minimum costs from surviving native ways, preserving identities.

    This only builds arcs for the supplied source window. It must never be
    passed off as the full national graph. Parallel costs are minimized only
    AFTER the full-geometry filter, not inherited from the old compressed CSR.
    """
    if native.edge_minutes.isna().any() or not np.isfinite(native.edge_minutes).all() or native.edge_minutes.lt(0).any():
        raise ValueError('Invalid original edge time')
    if not native.oneway.isin([-1,0,1]).all():
        raise ValueError('Unknown one-way profile')
    geometries=shapely.from_wkb(native.native_geometry_wkb.to_numpy())
    kept=native.loc[domestic_mask(geometries,mask)]
    forward=kept[kept.oneway.ge(0)][['u','v','edge_minutes']]
    reverse=kept[kept.oneway.le(0)][['v','u','edge_minutes']].copy()
    reverse.columns=['u','v','edge_minutes']
    arcs=pd.concat([forward,reverse],ignore_index=True)
    if arcs.empty:return arcs
    return arcs.groupby(['u','v'],as_index=False,sort=True).edge_minutes.min()


def run(work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    name='sgrt/saratov-isochrones20261028/results/model/native_edges.parquet'
    proof=acquire(Path('data/saratov_isochrones_catalog_20261028.json').resolve(),lambda p:p==name,work/'input',work/'cache')
    boundary=work/'RUS-adm1.geojson'
    with urllib.request.urlopen(BOUNDARY_URL,timeout=60) as r:boundary.write_bytes(r.read())
    mask=load_russia(boundary)
    native=pd.read_parquet(work/'input'/name)
    geos=shapely.from_wkb(native.native_geometry_wkb.to_numpy())
    b=shapely.total_bounds(geos);mask=shapely.intersection(mask,box(b[0]-1,b[1]-1,b[2]+1,b[3]+1))
    inside=domestic_mask(geos,mask)
    project=Transformer.from_crs(4326,32638,always_xy=True).transform
    rows=[]
    for i in np.flatnonzero(~inside):
        r=native.iloc[int(i)];g=geos[int(i)];outside=g.difference(mask)
        rows.append({'u':int(r.u),'v':int(r.v),'way_id':int(r.way_id),'oneway':int(r.oneway),
            'outside_metres':float(transform(project,outside).length),
            'source_segment_length_metres':float(transform(project,g).length),
            'first_point_in_country':bool(mask.covers(Point(g.coords[0]))),
            'last_point_in_country':bool(mask.covers(Point(g.coords[-1]))),
            'wgs84_bounds':list(g.bounds)})
    lengths=[r['outside_metres'] for r in rows]
    result={'source_native_segments':len(native),'entirely_inside_count':int(inside.sum()),
        'not_entirely_inside_count':len(rows),'outside_length_metres':sum(lengths),
        'outside_length_max_metres':max(lengths,default=0.),
        'both_endpoints_inside_but_native_line_not_inside':sum(r['first_point_in_country'] and r['last_point_in_country'] for r in rows),
        'rows':rows,'country_source_sha256':hashlib.sha256(boundary.read_bytes()).hexdigest(),
        'scope':'Saved original road shapes in the six-centre 60-minute window only; not a national route audit.',
        'rule':'Full native line must be covered; endpoints alone do not admit a road. Keep direction and original cost for surviving edges.',
        'old_cost_matrix_recomputed':False,'actual_foreign_transit_proven':False,
        'source_outline_is_exact_legal_border':False,
        'limitations':['Outside the adopted outline is not necessarily outside the exact legal border; source generalisation and epochs differ.',
                       'This is an exclusion rule and a diagnostic list, not a claim that any published shortest path used these segments.'],
        'provenance':proof}
    path=Path('research_context/analysis_snapshots/saratov_native_country_details_20261103.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'rows','provenance'}},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--check-fixture',action='store_true');a=p.parse_args()
    if a.check_fixture:
        mask=box(0,0,1,1)
        lines=[LineString([(0.1,0.1),(0.9,0.9)]),LineString([(0.1,0.1),(1.5,0.5),(0.9,0.9)])]
        assert domestic_mask(lines,mask).tolist()==[True,False]
    run(a.work)

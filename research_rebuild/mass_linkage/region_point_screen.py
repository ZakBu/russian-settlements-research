"""Modern ADM1 polygon contradiction screen, separate from point admission.

GeoBoundaries 2017 ADM1 polygons are approximate context, not dated settlement
boundaries. Crimea/Sevastopol census-2021 geography is looked up explicitly in
UKR geometry; the source's sovereignty coding never becomes an identity veto.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from pyproj import Geod

REGION_ISO = dict(x.split(':') for x in '''адыгея:RU-AD алтай:RU-AL алтайский:RU-ALT амурская:RU-AMU архангельская:RU-ARK астраханская:RU-AST башкортостан:RU-BA белгородская:RU-BEL брянская:RU-BRY бурятия:RU-BU владимирская:RU-VLA волгоградская:RU-VGG вологодская:RU-VLG воронежская:RU-VOR дагестан:RU-DA еврейская:RU-YEV забайкальский:RU-ZAB ивановская:RU-IVA ингушетия:RU-IN иркутская:RU-IRK калининградская:RU-KGD калмыкия:RU-KL калужская:RU-KLU камчатский:RU-KAM карелия:RU-KR кемеровская:RU-KEM кировская:RU-KIR коми:RU-KO костромская:RU-KOS краснодарский:RU-KDA красноярский:RU-KYA крым:UA-43 курганская:RU-KGN курская:RU-KRS ленинградская:RU-LEN липецкая:RU-LIP магаданская:RU-MAG мордовия:RU-MO москва:RU-MOW московская:RU-MOS мурманская:RU-MUR ненецкий:RU-NEN нижегородская:RU-NIZ новгородская:RU-NGR новосибирская:RU-NVS омская:RU-OMS оренбургская:RU-ORE орловская:RU-ORL пензенская:RU-PNZ пермский:RU-PER приморский:RU-PRI псковская:RU-PSK ростовская:RU-ROS рязанская:RU-RYA самарская:RU-SAM саратовская:RU-SAR сахалинская:RU-SAK свердловская:RU-SVE севастополь:UA-40 смоленская:RU-SMO ставропольский:RU-STA тамбовская:RU-TAM татарстан:RU-TA тверская:RU-TVE томская:RU-TOM тульская:RU-TUL тыва:RU-TY тюменская:RU-TYU удмуртская:RU-UD ульяновская:RU-ULY хабаровский:RU-KHA хакасия:RU-KK челябинская:RU-CHE чеченская:RU-CE чувашская:RU-CU чукотский:RU-CHU ярославская:RU-YAR'''.split())
REGION_ISO.update({'кабардино балкарская':'RU-KB','карачаево черкесская':'RU-KC','марий эл':'RU-ME','санкт петербург':'RU-SPE','саха якутия':'RU-SA','северная осетия алания':'RU-SE','ханты мансийский югра':'RU-KHM','ямало ненецкий':'RU-YAN'})


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()


def screen(rows: pd.DataFrame, geometries: dict[str,object]) -> pd.DataFrame:
    result=rows[['source_record_id','region_norm','population','latitude','longitude']].copy()
    result['geometry_iso']=result.region_norm.map(REGION_ISO)
    result['point_valid_wgs84']=pd.to_numeric(result.latitude,errors='coerce').between(-90,90)&pd.to_numeric(result.longitude,errors='coerce').between(-180,180)
    result['region_screen_status']='point_missing_or_invalid'
    result['outside_distance_estimate_km']=np.nan
    geod=Geod(ellps='WGS84')
    for iso,index in result.loc[result.point_valid_wgs84].groupby('geometry_iso',dropna=False).groups.items():
        geom=geometries.get(iso)
        if geom is None:
            result.loc[index,'region_screen_status']='geometry_mapping_unavailable';continue
        if not shapely.is_valid(geom):raise ValueError(f'invalid source polygon: {iso}')
        points=shapely.points(result.loc[index,'longitude'].to_numpy(),result.loc[index,'latitude'].to_numpy())
        inside=shapely.covers(geom,points)
        result.loc[index,'region_screen_status']=np.where(inside,'inside_expected_modern_region','outside_expected_region_requires_review')
        outside_index=index[~inside]
        if len(outside_index):
            lines=shapely.shortest_line(points[~inside],geom)
            nearest=shapely.get_point(lines,-1)
            _,_,metres=geod.inv(result.loc[outside_index,'longitude'].to_numpy(),result.loc[outside_index,'latitude'].to_numpy(),shapely.get_x(nearest),shapely.get_y(nearest))
            result.loc[outside_index,'outside_distance_estimate_km']=np.abs(metres)/1000
            near=np.abs(metres)<=3000
            result.loc[outside_index[near],'region_screen_status']='border_near_or_simplification_uncertain'
    result['admission_status']='diagnostic_only_no_admission'
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--selected',type=Path,required=True);p.add_argument('--geometry-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args()
    if a.output_root.exists():raise FileExistsError('Use a new immutable output directory')
    paths=[a.geometry_root/'RUS_ADM1_simplified.geojson',a.geometry_root/'UKR_ADM1.geojson']
    g=pd.concat([gpd.read_file(p) for p in paths],ignore_index=True)
    if not all(shapely.is_valid(g.geometry.to_numpy())):raise ValueError('Invalid polygons; repair requires an explicit source-specific decision')
    if g.shapeISO.duplicated().any():raise ValueError('Ambiguous ISO geometry')
    geometries=dict(zip(g.shapeISO,g.geometry))
    d=pd.read_parquet(a.selected,columns=['source_record_id','census_year','population','latitude','longitude','region_norm']);d=d[d.census_year.eq(2021)]
    result=screen(d,geometries);a.output_root.mkdir(parents=True)
    out=a.output_root/'region_point_screen.parquet';result.to_parquet(out,index=False)
    receipt={'role':'diagnostic_only_no_admission','builder_sha256':sha(Path(__file__)),'geometry_source_year':2017,'inputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in paths+[a.selected]},'output':{'file':out.name,'sha256':sha(out),'rows':len(result)},'mapping':REGION_ISO,'statuses':[],'limitations':['2017 ADM1 context is not a census-date settlement polygon.','Simplified borders and source geometry may differ from legal boundaries.','Outside distance is an estimate to a longitude/latitude nearest boundary point; targeted review is required.','Crimea/Sevastopol source country labels are independent of explicit census-2021 coverage.']}
    for status,v in result.groupby('region_screen_status'):receipt['statuses'].append({'status':status,'rows':len(v),'known_population':int(v.population.sum())})
    (a.output_root/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt['statuses'],ensure_ascii=False))

if __name__=='__main__':main()

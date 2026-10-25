"""Symmetric named-address + coordinate linkage of WB catalogue vintages.

Links dated catalogue evidence, never opening dates or true service boundaries.
All types are retained because typePoint definitions changed across vintages.
"""
from pathlib import Path
from collections import defaultdict, Counter
import hashlib
import json
import re
import unicodedata
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
KEY = 'source_record_id_2021'
EARTH = 6371.0088


def norm(s):
    s = unicodedata.normalize('NFKC', str(s)).lower().replace('ё', 'е')
    s = re.sub(r'[^\w\s-]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


PREFIX = re.compile(
    r'^(?:город|г\.?|село|с\.?|деревня|д\.?|хутор|х\.?|станица|ст-ца|'
    r'поселок городского типа|рабочий поселок|пгт\.?|р\.?\s*п\.?|'
    r'поселок|пос\.?|п\.?|аул|слобода|сл\.?|станция|ст\.?)\s+', re.I)


def address_names(address):
    names = set()
    for part in str(address or '').lower().replace('ё', 'е').split(',')[:4]:
        part = re.sub(r'\([^)]*\)', ' ', part).strip()
        part = PREFIX.sub('', part).strip()
        value = norm(part)
        if value:
            names.add(value)
    return names


def unit_vectors(lat, lon):
    lat, lon = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])


def main():
    paths = [OUT/'network/wb_history_normalized.parquet',
             BASE.parent.parent/'wb20261021_objects.parquet',
             BASE/'national/national_target_source2021.parquet',
             OUT/'centres/settlement_admin_context_main2021.parquet']
    historical = pd.read_parquet(paths[0])
    current = pd.read_parquet(paths[1])
    current = current.rename(columns={'snapshot_date':'archive_date'})
    fields = ['archive_date','source_object_id','source_country','latitude','longitude','address',
              'typePoint','fitting_rooms']
    objects = pd.concat([historical[fields], current[fields]], ignore_index=True)
    objects = objects.loc[objects.source_country.eq('ru')].copy()
    objects.source_object_id = objects.source_object_id.astype(str)
    assert not objects.duplicated(['archive_date','source_object_id']).any()
    d = pd.read_parquet(paths[2])
    context = pd.read_parquet(paths[3])
    assert d[KEY].is_unique and context[KEY].is_unique
    d = d.merge(context[[KEY,'admin_centre_positive_20200110',
                         'context_status_20200110','admin_centre_positive_20211103',
                         'context_status_20211103']], on=KEY,validate='one_to_one')
    points = d.loc[d.accepted_point_present_2021].copy().reset_index(drop=True)
    assert len(points) == 144149
    xyz = unit_vectors(points.accepted_latitude_2021.to_numpy(),
                       points.accepted_longitude_2021.to_numpy())
    tree = cKDTree(xyz)
    names = [norm(v) for v in points.name_2021]
    ids = points[KEY].tolist()
    valid = objects.latitude.between(-90,90) & objects.longitude.between(-180,180)
    assert valid.all()
    obj_xyz = unit_vectors(objects.latitude.to_numpy(), objects.longitude.to_numpy())
    # One broad spatial query, then exact address-name matching and radius-specific uniqueness.
    candidates = tree.query_ball_point(obj_xyz, 2*np.sin(10/(2*EARTH)))
    links = []
    for row, location, nearby in zip(objects.itertuples(index=False), obj_xyz, candidates):
        textual = address_names(row.address)
        matches = []
        for idx in nearby:
            if names[idx] in textual:
                chord = np.linalg.norm(location-xyz[idx])
                km = 2*EARTH*np.arcsin(min(1,chord/2))
                matches.append((ids[idx],float(km)))
        record = dict(archive_date=row.archive_date, source_object_id=row.source_object_id,
                      typePoint=None if pd.isna(row.typePoint) else int(row.typePoint),
                      fitting_rooms=None if pd.isna(row.fitting_rooms) else float(row.fitting_rooms),
                      address=row.address, latitude=row.latitude, longitude=row.longitude)
        for radius in (1,5,10):
            selected = [(i,km) for i,km in matches if km<=radius]
            record[f'link_status_{radius}km'] = (
                'accepted_unique_exact_address_component_and_coordinate' if len(selected)==1 else
                'ambiguous_multiple_named_candidates' if len(selected)>1 else 'unresolved_no_named_candidate')
            record[f'{KEY}_{radius}km'] = selected[0][0] if len(selected)==1 else None
            record[f'distance_km_{radius}km'] = selected[0][1] if len(selected)==1 else None
        links.append(record)
    linked = pd.DataFrame(links)
    linked.to_parquet(OUT/'wb_history_symmetric_links.parquet',index=False)
    inventory, footprint = [], []
    count_tables = []
    for radius in (1,5,10):
        col = f'{KEY}_{radius}km'
        for date, g in linked.groupby('archive_date'):
            accepted = g.loc[g[col].notna()].copy()
            accepted['current_focus_object'] = (
                accepted.archive_date.eq('2026-10-21') & accepted.typePoint.isin([8,34]))
            inventory.append(dict(
                archive_date=date, radius_km=radius, ru_catalogue_objects=len(g),
                linked_objects=len(accepted), unresolved_or_ambiguous=len(g)-len(accepted),
                status_counts=json.dumps(g[f'link_status_{radius}km'].value_counts().to_dict()),
            ))
            aggreg = accepted.groupby(col).agg(
                allcatalog_objects=('source_object_id','size'),
                fitting_positive_objects=('fitting_rooms',lambda x:int(x.ge(1).sum())),
                fitting_unknown_objects=('fitting_rooms',lambda x:int(x.isna().sum())),
                current_focus_objects=('current_focus_object','sum'),
            ).reset_index().rename(columns={col:KEY})
            aggreg['archive_date']=date
            aggreg['radius_km']=radius
            count_tables.append(aggreg)
            for profile, flag in [
                ('all_catalogue',aggreg.allcatalog_objects.gt(0)),
                ('fitting_positive_observed',aggreg.fitting_positive_objects.gt(0)),
                ('fitting_positive_or_unknown',
                 (aggreg.fitting_positive_objects+aggreg.fitting_unknown_objects).gt(0)),
            ]:
                node_ids=set(aggreg.loc[flag,KEY])
                nodes=d.loc[d[KEY].isin(node_ids)]
                for vintage in ['20200110','20211103']:
                    centre=nodes[f'admin_centre_positive_{vintage}']
                    known=nodes[f'context_status_{vintage}'].eq('accepted_administrative_parent_and_centre')
                    footprint.append(dict(
                        archive_date=date,radius_km=radius,profile=profile,context_vintage=vintage,
                        positive_nodes=len(nodes),population2021=nodes.population_2021.sum(),
                        inhabited_positive_nodes=int(nodes.population_2021.gt(0).sum()),
                        centre_positive_nodes=int(centre.sum()),
                        other_known_positive_nodes=int((known & ~centre).sum()),
                        unknown_context_positive_nodes=int((~known & ~centre).sum()),
                    ))
    pd.DataFrame(inventory).to_csv(OUT/'wb_history_linkage_inventory.csv',index=False)
    f=pd.DataFrame(footprint)
    f.to_csv(OUT/'wb_history_admin_footprints.csv',index=False)
    counts=pd.concat(count_tables,ignore_index=True)
    counts.to_parquet(OUT/'wb_history_settlement_counts.parquet',index=False)
    changes=[]
    for radius in (1,5,10):
        x=counts.loc[counts.radius_km.eq(radius)]
        current=x.loc[x.archive_date.eq('2026-10-21')]
        current_all=set(current[KEY])
        current_fitted=set(current.loc[current.fitting_positive_objects.gt(0),KEY])
        current_focus=set(current.loc[current.current_focus_objects.gt(0),KEY])
        for date,g in x.loc[~x.archive_date.eq('2026-10-21')].groupby('archive_date'):
            old=set(g[KEY])
            added=current_all-old
            removed=old-current_all
            conservative=current_fitted-old
            c=d.loc[d[KEY].isin(conservative)]
            focus_added=current_focus-old
            ca=d.loc[d[KEY].isin(focus_added)]
            changes.append(dict(
                older_date=date,current_date='2026-10-21',radius_km=radius,
                older_catalogue_nodes=len(old),current_catalogue_nodes=len(current_all),
                retained_nodes=len(old & current_all),
                current_only_catalogue_nodes=len(added),older_only_catalogue_nodes=len(removed),
                current_fitting_positive_nodes_without_old_catalogue_record=len(conservative),
                latter_documented_centres2021=int(c.admin_centre_positive_20211103.sum()),
                latter_other_known_members2021=int((
                    c.context_status_20211103.eq('accepted_administrative_parent_and_centre') &
                    ~c.admin_centre_positive_20211103).sum()),
                current_focus_nodes=len(current_focus),
                current_focus_nodes_without_old_any_catalogue_record=len(focus_added),
                focus_latter_documented_centres2021=int(ca.admin_centre_positive_20211103.sum()),
                focus_latter_other_known_members2021=int((
                    ca.context_status_20211103.eq('accepted_administrative_parent_and_centre') &
                    ~ca.admin_centre_positive_20211103).sum()),
            ))
    pd.DataFrame(changes).to_csv(OUT/'wb_catalogue_footprint_changes.csv',index=False)
    summary={
        'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
        'objects_ru':len(linked),'snapshots':sorted(linked.archive_date.unique()),
        'link_rule':'Unique exact settlement-name match to one of first four comma-separated address components, recognized type prefix/parenthetical region removed, plus distance1/5/10km on fixed credited2021 coordinates.',
        'different_from_previous_WB_linkage':True,
        'main_5km_footprints':f.query("radius_km==5 and profile=='all_catalogue' and context_vintage=='20211103'").to_dict('records'),
        'limits':[
            'All catalogue types retained; typePoint changed meaning across dates.',
            'Observed catalogue footprint changes are not actual openings/closures or complete network growth.',
            'Fitting-room reporting improved; positive-or-unknown is a sensitivity profile, not confirmed customer points.',
            'One fixed census2021 point/name axis used; historical names and administrative changes may reduce matches.',
            'Address-coordinate match does not establish location inside settlement boundaries.',
            'Main linkage differs from the earlier current WB bridge, so previous7991 count is not the denominator here.',
        ],
    }
    (OUT/'wb_history_symmetric_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary['main_5km_footprints'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

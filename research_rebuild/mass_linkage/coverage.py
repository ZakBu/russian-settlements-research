"""Measure independent quality axes without promoting candidates or filling totals.

The legacy availability flag is an inventory of candidate point bindings, never
an admission. Identity edges and point uses must be independently admitted before
being supplied here. This calculator preserves official-control gaps and labels
unmeasured event/comparability coverage explicitly.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import pandas as pd


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)


def identity_sets(selected: pd.DataFrame, edges: pd.DataFrame):
    """Separate DFS verifier; a same-year component collision fails closed."""
    years = selected.set_index('source_record_id').census_year.to_dict()
    adjacency = defaultdict(set)
    for a,b in edges[['from_source_record_id','to_source_record_id']].itertuples(index=False, name=None):
        if a not in years or b not in years or a == b or years[a] == years[b]:
            raise ValueError('identity edge has absent, identical or same-year endpoints')
        adjacency[a].add(b); adjacency[b].add(a)
    seen, full, components = set(), set(), []
    for start in sorted(adjacency):
        if start in seen: continue
        stack, members = [start], set()
        while stack:
            node = stack.pop()
            if node in members: continue
            members.add(node); stack.extend(adjacency[node]-members)
        seen.update(members)
        component_years = [int(years[n]) for n in members]
        if len(component_years) != len(set(component_years)):
            raise ValueError('multiple source rows for one census year in component')
        if {2002,2010,2021}.issubset(component_years): full.update(members)
        components.append(members)
    return seen, full, components


def metric(group: pd.DataFrame, ids: set[str], control: int) -> dict:
    mask = group.source_record_id.isin(ids)
    population = int(group.loc[mask,'population'].sum())
    denominator = int(group.population.sum())
    return {'rows': int(mask.sum()), 'known_population': population,
            'row_fraction': float(mask.mean()),
            'selected_known_population_fraction': population/denominator if denominator else None,
            'official_control_population_fraction': population/control,
            'unknown_population_rows': int(group.loc[mask,'population'].isna().sum())}


def measure(selected: pd.DataFrame, legacy: pd.DataFrame, edges: pd.DataFrame,
            point_uses: pd.DataFrame, controls: dict[int,int]) -> dict:
    if selected.source_record_id.isna().any() or not selected.source_record_id.is_unique:
        raise ValueError('selected IDs must be unique and nonnull')
    if not legacy.source_record_id.is_unique: raise ValueError('legacy availability IDs not unique')
    if not set(selected.census_year).issubset({2002,2010,2021}):
        raise ValueError('census calculator does not assign national denominators to annual observations')
    ids = set(selected.source_record_id)
    if not set(point_uses.target_source_record_id).issubset(ids):
        raise ValueError('point-use endpoint absent from selected source layer')
    if point_uses.target_source_record_id.duplicated().any():
        raise ValueError('accepted point uses must be resolved to one point per source record')
    if not point_uses.empty:
        lat = pd.to_numeric(point_uses.latitude,errors='coerce')
        lon = pd.to_numeric(point_uses.longitude,errors='coerce')
        if not (lat.between(-90,90)&lon.between(-180,180)).all():
            raise ValueError('invalid accepted WGS84 point')
        aggregate_ids=set(selected.loc[selected.population_scope.eq('federal_city_region'),'source_record_id'])
        if set(point_uses.target_source_record_id)&aggregate_ids:
            raise ValueError('federal territorial aggregate cannot receive a settlement point use')
    linked, full, components=identity_sets(selected,edges)
    point_ids=set(point_uses.target_source_record_id)
    availability=selected.source_record_id.map(legacy.set_index('source_record_id').any_legacy_point_available).astype('boolean').fillna(False).astype(bool)
    available=set(selected.loc[availability | (selected.latitude.notna()&selected.longitude.notna()),'source_record_id']) | point_ids
    legacy_pointer_available = set()
    if 'settlement_id' in selected and 'settlement_id' in legacy:
        pointer_ids=set(legacy.loc[legacy.any_legacy_point_available.fillna(False).astype(bool),'settlement_id'].dropna())
        legacy_pointer_available=set(selected.loc[selected.settlement_id.isin(pointer_ids),'source_record_id'])
    broad_inventory = available | legacy_pointer_available
    rows=[]
    for year,g in selected.groupby('census_year',sort=True):
        year=int(year); control=controls[year]; known=int(g.population.sum())
        r={'year':year,'selected_rows':len(g),'selected_known_population':known,
           'unknown_population_rows':int(g.population.isna().sum()),'official_control':control,
           'selected_known_population_gap_to_control':control-known,
           'target_population':control*0.999,
           'axes':{'coordinate_availability_by_exact_source_route':metric(g,available,control),
                   'coordinate_inventory_including_unaccepted_legacy_place_pointers':metric(g,broad_inventory,control),
                   'coordinate_admitted':metric(g,point_ids,control),
                   'identity_link_to_other_census':metric(g,linked,control),
                   'full_census_chain':metric(g,full,control),
                   'joint_admitted_coordinate_and_other_census':metric(g,point_ids&linked,control),
                   'joint_admitted_coordinate_and_full_chain':metric(g,point_ids&full,control)},
           'population_quality_categories':[
               {'source_quality':str(k),'rows':len(v),'known_population':int(v.population.sum())}
               for k,v in g.groupby('population_value_quality',dropna=False)],
           'retained_federal_city_aggregate':{'rows':int(g.population_scope.eq('federal_city_region').sum()),
               'known_population':int(g.loc[g.population_scope.eq('federal_city_region'),'population'].sum())},
           'historical_event_coverage':{'status':'not_measured','reason':'an event ledger and a defined applicable denominator are required'},
           'population_boundary_comparability':{'status':'not_measured','reason':'same-place identity alone does not harmonize population boundaries'},
           'dated_oktmo_history':{'status':'not_measured','reason':'observed code snapshots are distinct from verified validity intervals'},
           'reliable_coordinate_population_remaining_to_target':max(0,control*0.999-int(g.loc[g.source_record_id.isin(point_ids),'population'].sum()))}
        rows.append(r)
    return {'scope':'current selected census records; no annual nationwide denominator inferred',
            'census_metrics':rows,'identity_graph':{'edges':len(edges),'linked_vertices':len(linked),
                'components':len(components),'full_census_components':len(full)//3},
            'limitations':['Exact-source availability and inventory via unaccepted legacy place pointers are separate; neither admits a point or verifies identity.',
                           'Source-tagged counts are preserved, including confidentiality-protected 2010 values.',
                           'Admission status is supplied by independent decision receipts, not inferred from point presence.',
                           'Population-weighted shares describe known recorded values, not calibrated probabilities of correctness.']}


def main():
    p=argparse.ArgumentParser()
    for key in ['selected','legacy-quality','edges','points','policy','output']:p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args(); paths={'selected':a.selected,'legacy_quality':a.legacy_quality,'edges':a.edges,'points':a.points,'policy':a.policy}
    selected=pd.read_parquet(a.selected,columns=['source_record_id','census_year','population','latitude','longitude','population_scope','population_value_quality','settlement_id'])
    legacy=pd.read_parquet(a.legacy_quality,columns=['source_record_id','any_legacy_point_available','settlement_id'])
    edges=read_table(a.edges); points=read_table(a.points)
    if 'selection_projection_status' in points:points=points[points.selection_projection_status.eq('active_endpoints_selected')]
    policy=json.loads(a.policy.read_text()); controls={int(k):int(v) for k,v in policy['population_controls_from_preserved_audit'].items()}
    result=measure(selected,legacy,edges,points,controls)
    result['inputs']={k:{'file':v.name,'sha256':sha(v),'bytes':v.stat().st_size} for k,v in paths.items()}
    result['builder_sha256']=sha(Path(__file__))
    if a.output.exists():raise FileExistsError('output receipt already exists; use a new immutable output path')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'receipt':str(a.output),'graph':result['identity_graph']},ensure_ascii=False))


if __name__=='__main__':main()

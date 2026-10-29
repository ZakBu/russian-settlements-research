"""Independent accepted-mass and uncensored directed-field QA.

No production population/functional field module is imported. The two federal
territories remain aggregate reference anchors, not ordinary settlements.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_saratov.regional_independent_checks import (
    independent_full_cost_rows, original_graph, heap_shortest, kernel_scalar, close_numeric,
)


def source_mass_oracle(reference,federal):
    """Reconstruct the accepted ledger directly from published source fields."""
    import numpy as np
    import pandas as pd
    if not reference.source_record_id.is_unique:raise ValueError('Repeated reference identity')
    pop=pd.to_numeric(reference.population_2021,errors='coerce')
    ordinary=reference.population_role.eq('ordinary_settlement_record')&reference.credit_2021.eq(True)&pop.ge(0)&np.isfinite(pop)
    f=federal[federal.census_year.eq(2021)]
    if len(f)!=2 or set(f.territory_key)!={'RU-FED-MOW','RU-FED-SPB'} or not f.population_source_record_id.is_unique:
        raise ValueError('Expected exactly the accepted Moscow and SPb territory totals')
    federalmask=reference.source_record_id.isin(f.population_source_record_id)
    if int(federalmask.sum())!=2 or (federalmask&ordinary).any():raise ValueError('Missing or double-credited federal population')
    for x in f.itertuples(index=False):
        r=reference[reference.source_record_id.eq(x.population_source_record_id)].iloc[0]
        if r.population_role!='external_context_nonadditive' or float(r.population_2021)!=float(x.territory_population):
            raise ValueError('Federal aggregate conflicts with its separate source territory')
    return ordinary.to_numpy(bool),federalmask.to_numpy(bool),pop.to_numpy(float)


def lower_time_minutes(a_lat,a_lon,b_lat,b_lon):
    """Great-circle distance / declared 130 km/h bound, unknown location -> 0."""
    if not all(math.isfinite(float(x)) for x in (a_lat,a_lon,b_lat,b_lon)):return 0.
    p1,p2=math.radians(float(a_lat)),math.radians(float(b_lat))
    dp,dl=p2-p1,math.radians(float(b_lon)-float(a_lon))
    q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,q))))/130.*60.


def audit(fields,federal_csv,catalog,scope_root,cache_root=None,graph_dir=None):
    import numpy as np
    import pandas as pd
    root=Path(fields);scope=Path(scope_root)
    reference=pd.read_parquet(root/'national_reference_with_endpoints.parquet')
    ledger=pd.read_parquet(root/'population_mass_sources.parquet')
    federal=pd.read_csv(federal_csv)
    catalogue=json.loads(Path(catalog).read_text())
    spec=next(x for x in catalogue['files'] if x['path']=='data/population/federal_territories.csv')
    expectedsha=catalogue['objects'][spec['blob']]['sha256']
    actualsha=hashlib.sha256(Path(federal_csv).read_bytes()).hexdigest()
    errors=[];facts={}
    def check(condition,message):
        if not condition:errors.append(message)
    check(actualsha==expectedsha and Path(federal_csv).stat().st_size==spec['bytes'],'Federal CSV source bytes differ from accepted catalogue')
    ordinary,fmask,pop=source_mass_oracle(reference,federal)
    check(list(reference.source_record_id)==list(ledger.source_record_id),'Mass ledger source axis changed')
    try:pd.testing.assert_frame_equal(reference,ledger[reference.columns],check_exact=True)
    except AssertionError:errors.append('An original national-reference value or credit flag changed')
    eligible=ordinary|fmask
    expected=np.where(eligible,pop,np.nan)
    check(np.allclose(ledger.field_mass_2021,expected,rtol=0,atol=0,equal_nan=True),'Ledger field mass does not match independent accepted source scope')
    for col,wanted in [('eligible_ordinary_field_mass',ordinary),('eligible_federal_territory_field_mass',fmask),('eligible_field_mass',eligible),('positive_field_mass',eligible&(pop>0))]:
        check(np.array_equal(ledger[col].to_numpy(bool),wanted),'Ledger admission flags differ: '+col)
    known=math.fsum(float(x) for x in pop[eligible]);ordinarysum=math.fsum(float(x) for x in pop[ordinary]);fsum=math.fsum(float(x) for x in pop[fmask])
    check(known==144329319. and ordinarysum==125717296. and fsum==18612023.,'Accepted canonical population budget differs')
    missing=eligible&(pop>0)&~reference.accepted_source_endpoint.eq(True).to_numpy(bool)
    missinggeo=missing&(~np.isfinite(reference.lat.to_numpy(float))|~np.isfinite(reference.lon.to_numpy(float)))
    missingmass=math.fsum(float(x) for x in pop[missing]);nogeo=math.fsum(float(x) for x in pop[missinggeo])
    check(missingmass==11263. and nogeo==39.,'Missing route/coordinate accepted-source budget differs')
    facts.update(accepted_population_mass=known,ordinary_population_mass=ordinarysum,federal_territory_population_mass=fsum,
        federal_territories_count=int(fmask.sum()),accepted_mass_without_endpoint=missingmass,accepted_mass_without_coordinates=nogeo,
        model_reference_columns_preserved_in_mass_ledger=len(reference.columns),federal_csv_sha256=actualsha)
    full=independent_full_cost_rows(root,cache_root,scope)
    dest=pd.read_parquet(root/'destinations.parquet').sort_values('destination_index')
    base=reference.set_index('source_record_id');d=base.loc[dest.source_record_id]
    ordinaryd=d.population_role.eq('ordinary_settlement_record')&d.credit_2021.eq(True)&d.population_2021.ge(0)&np.isfinite(d.population_2021)
    fd=d.index.isin(federal.loc[federal.census_year.eq(2021),'population_source_record_id'])
    massd=np.where(ordinaryd.to_numpy(bool)|fd,d.population_2021.to_numpy(float),0.)
    roster=pd.read_parquet(root/'regional_roster.parquet');halo=pd.read_parquet(root/'halo_roster.parquet')
    origins=pd.concat([roster,halo],ignore_index=True)
    table=pd.concat([pd.read_parquet(root/'fields.parquet'),pd.read_parquet(root/'halo_fields.parquet')],ignore_index=True)
    chosen=origins[origins.source_record_id.isin(full)&origins.accepted_source_endpoint.eq(True)]
    if cache_root is not None:
        wanted=pd.read_parquet(scope/'selected_unbounded_origin_axis.parquet').source_record_id
        chosen=chosen[chosen.source_record_id.isin(wanted)]
    check(len(chosen)>0,'No independent full-cost scalar origins checked')
    byid=origins.set_index('source_record_id');scenario_count=0;maximum=0.;routed_over480=0
    unmap=reference.loc[missing]
    for origin in chosen.itertuples(index=False):
        sid=str(origin.source_record_id);costs=full[sid]
        check(not np.isnan(costs).any() and not (costs<0).any(),'Known origin full costs include NaN/negative: '+sid)
        j=np.flatnonzero(dest.source_record_id.eq(sid).to_numpy())
        check(len(j)==1 and costs[int(j[0])]==0.,'Unbounded self zero differs: '+sid)
        routed_over480+=int((np.isfinite(costs)&(costs>480)&(massd>0)).sum())
        lower=[lower_time_minutes(origin.lat,origin.lon,x.lat,x.lon) for x in unmap.itertuples(index=False)]
        own=base.loc[sid];ownmass=float(own.population_2021) if ((own.population_role=='ordinary_settlement_record' and bool(own.credit_2021)) or sid in set(federal.loc[federal.census_year.eq(2021),'population_source_record_id'])) else 0.
        for row in table[table.source_record_id.eq(sid)].itertuples(index=False):
            vals=[float(m)*kernel_scalar(float(t),float(row.half_time),row.kernel) for m,t in zip(massd,costs)]
            total=math.fsum(vals)-(0. if row.include_self else ownmass)
            ordinary_value=math.fsum(v for v,flag in zip(vals,ordinaryd) if flag)-(ownmass if not row.include_self and own.population_role=='ordinary_settlement_record' else 0.)
            federal_value=math.fsum(v for v,flag in zip(vals,fd) if flag)-(ownmass if not row.include_self and sid in set(d.index[fd]) else 0.)
            bound=math.fsum(float(m)*kernel_scalar(t,float(row.half_time),row.kernel) for m,t in zip(pop[missing],lower))
            for actual,wanted,label in [(row.value,total,'total'),(row.ordinary_known_field,ordinary_value,'ordinary'),(row.federal_context_field,federal_value,'federal'),(row.unmapped_mass_upper,bound,'unmapped bound'),(row.accepted_mass_field_upper,total+bound,'accepted upper')]:
                maximum=max(maximum,abs(float(actual)-wanted))
                check(close_numeric(float(actual),wanted),'Scalar unbounded '+label+' differs: '+sid)
            check(float(row.tail_upper)==0. and bool(row.whole_field_is_unbounded),'Unbounded field retains computational tail/cutoff')
            check(float(row.unmapped_mass_upper_without_distance_assumption)==missingmass and float(row.credited_population_without_coordinates_upper)==nogeo,'Unknown source mass omitted from bound')
            scenario_count+=1
    absent=origins.loc[~origins.accepted_source_endpoint.eq(True),'source_record_id']
    unknown=table[table.source_record_id.isin(absent)]
    check(unknown.value.isna().all() and unknown.status.eq('origin_endpoint_unavailable').all(),'Unknown origin field converted to zero')
    facts.update(scalar_origins=len(chosen),scalar_scenarios=scenario_count,maximum_scalar_difference=maximum,
        positive_mass_destinations_beyond480_in_controls=routed_over480,unknown_origin_scenarios=len(unknown))
    if graph_dir:
        from scipy.sparse.csgraph import dijkstra
        graph=original_graph(graph_dir);reverse=graph.transpose().tocsr();controls=[];heaps=[]
        anchors=ledger[ledger.eligible_federal_territory_field_mass]
        citycosts=pd.read_parquet(root/'external_city_costs.parquet')
        for city in anchors.itertuples(index=False):
            dist=dijkstra(reverse,directed=True,indices=int(city.road_node_index))
            for origin in origins[origins.accepted_source_endpoint.eq(True)].itertuples(index=False):
                value=float(dist[int(origin.road_node_index)])+4.*float(origin.snap_km)+float(dest.loc[dest.source_record_id.eq(city.source_record_id),'destination_connector_minutes'].iloc[0])
                if origin.source_record_id==city.source_record_id:value=0.
                actual=citycosts[citycosts.origin_id.eq(origin.source_record_id)&citycosts.city_id.eq(city.source_record_id)]
                check(len(actual)==1,'Missing federal directed cost control')
                if len(actual):check((math.isinf(value) and math.isinf(float(actual.iloc[0].cost_minutes))) or close_numeric(float(actual.iloc[0].cost_minutes),value,absolute=1e-7,relative=1e-11),'Full reverse federal cost differs')
                controls.append({'origin_id':origin.source_record_id,'city_id':city.source_record_id,'independent_total_minutes':value})
            # Independent Python heap additionally guards the reverse-query orientation.
            origin=roster.loc[roster.name.eq('Саратов')].iloc[0]
            network,popped=heap_shortest(graph,int(origin.road_node_index),int(city.road_node_index))
            wanted=network+4.*float(origin.snap_km)+float(dest.loc[dest.source_record_id.eq(city.source_record_id),'destination_connector_minutes'].iloc[0])
            actual=next(x['independent_total_minutes'] for x in controls if x['origin_id']==origin.source_record_id and x['city_id']==city.source_record_id)
            check(close_numeric(actual,wanted,absolute=1e-7,relative=1e-11),'Forward independent heap vs reverse federal orientation differs')
            heaps.append({'origin_id':origin.source_record_id,'city_id':city.source_record_id,'total_minutes':wanted,'vertices_popped':popped})
        pd.DataFrame(controls).to_parquet(scope/'independent_federal_cost_controls.parquet',index=False)
        corrected_routes=[]
        corrected=reference.loc[reference.pilot_geography_correction_applied.eq(True)] if 'pilot_geography_correction_applied' in reference else reference.iloc[:0]
        saratov=roster.loc[roster.name.eq('Саратов')].iloc[0]
        destination_by_id=dest.set_index('source_record_id')
        origin_by_id=origins.set_index('source_record_id')
        for point in corrected.itertuples(index=False):
            sid=str(point.source_record_id)
            if sid not in origin_by_id.index:continue
            for a,b in [(str(saratov.source_record_id),sid),(sid,str(saratov.source_record_id))]:
                check(a in full,'Corrected point has no retained full-cost scalar vector: '+a)
                if a not in full:continue
                source=origin_by_id.loc[a];target=destination_by_id.loc[b]
                network,popped=heap_shortest(graph,int(source.road_node_index),int(target.road_node_index))
                wanted=network+4.*float(source.snap_km)+float(target.destination_connector_minutes)
                actual=float(full[a][int(target.destination_index)])
                passed=(math.isinf(wanted) and math.isinf(actual)) or close_numeric(actual,wanted,absolute=1e-7,relative=1e-11)
                check(passed,'Independent directed route to/from corrected point differs: '+a+' -> '+b)
                corrected_routes.append({'origin_id':a,'destination_id':b,'total_minutes':wanted if math.isfinite(wanted) else None,
                                         'vertices_popped':popped,'full_cost_vector_agrees':passed})
        facts.update(independent_reverse_original_graph_pairs=len(controls),independent_forward_heap_controls=heaps,
                     independent_corrected_point_directed_routes=corrected_routes)
    return {'schema':'sgrt.saratov.unbounded_mass_independent.v1','facts':facts,'errors':errors,'violations':len(errors),
        'scope':'Exact declared directed graph costs and accepted source population, not measured journeys; federal anchors remain coarse territory references; Inf means graph unreachable, NaN unknown endpoint'}


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('fields','federal-csv','catalog','scope-root','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cost-cache',type=Path);p.add_argument('--graph-dir',type=Path)
    a=p.parse_args();report=audit(a.fields,a.federal_csv,a.catalog,a.scope_root,a.cost_cache,a.graph_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    if report['violations']:raise SystemExit('Unbounded source/field QA failed')
if __name__=='__main__':main()

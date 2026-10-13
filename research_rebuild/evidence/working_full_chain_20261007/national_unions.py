"""National companion axes requiring admitted point uses on all three rows."""
import math

def build(ordinary,componentpoints,partition_ids,qualified_ids,federal_population,national,common):
    base=set(componentpoints)
    partition=base|set(partition_ids)
    qualified=partition|set(qualified_ids)
    out={}
    for year,rows in ordinary.groupby('census_year'):
        year=int(year);denom=int(rows.population.sum())
        def take(ids):
            frame=rows[rows.source_record_id.isin(ids)]
            return {'rows':len(frame),'population':int(frame.population.sum()),'unknown_population_rows':int(frame.population.isna().sum())}
        b,p,q=take(base),take(partition),take(qualified)
        fed=int(federal_population[year])
        pv=p['population']+fed;qv=q['population']+fed
        out[year]={
            'ordinary_all_three_component_point_uses':dict(b,population_percent_of_selected_ordinary=100*b['population']/denom,row_percent_of_selected_ordinary=100*b['rows']/len(rows)),
            'all_three_component_points_plus_whole_partitions_plus_federal':{
                'selected_source_id_union_rows':p['rows'],
                'selected_source_id_union_population':p['population'],
                'partition_net_population_added_by_source_id_union':p['population']-b['population'],
                'federal_territory_population':fed,
                'combined_population':pv,
                'official_national_control':national[year],
                'common_three_census_control':common[year],
                'percent_of_national_control':100*pv/national[year],
                'percent_of_common_control':100*pv/common[year],
                'gap_to_99_percent_common':max(0,math.ceil(.99*common[year])-pv)},
            'all_three_component_points_plus_partitions_plus_qualified_physical_scopes_plus_federal':{
                'selected_source_id_union_rows':q['rows'],
                'selected_source_id_union_population':q['population'],
                'qualified_selected_source_id_union_net_population_added':q['population']-p['population'],
                'federal_territory_population':fed,
                'combined_population':qv,
                'official_national_control':national[year],
                'common_three_census_control':common[year],
                'percent_of_national_control':100*qv/national[year],
                'percent_of_common_control':100*qv/common[year],
                'gap_to_99_percent_common':max(0,math.ceil(.99*common[year])-qv)}
        }
        assert q['population']>=p['population']>=b['population']
    return {'definition':'Ordinary identity components qualify only when all three census source rows have admitted point uses. Whole-partition representative points and federal-territory anchors retain their distinct grains. Qualified physical sidecars additionally credit their reviewed existing selected source IDs by exclusive union; secondary child and auxiliary amounts stay nonadditive.','coordinate_calibration_asserted':False,'point_use_per_census_row_is_historical_measurement_asserted':False,'by_year':out}

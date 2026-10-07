"""Refine all-own-point unions to three finite population observations."""
import copy,json,math
from pathlib import Path
import duckdb,pandas as pd

def build(report,out):
    export=report['ordinary_complete_number_export'];exclude=export['excluded_components']
    unknown=[r for r in exclude if r['reason']=='unknown_population']
    assert len(unknown)==1 and unknown[0]['unknown_years']==[2010]
    ids=unknown[0]['source_ids'];manifest=json.loads((out/'export_source_hash_manifest.json').read_text())
    selected=next(p for p in manifest if p.endswith('/selected_observations.parquet'))
    con=duckdb.connect(config={'threads':1,'memory_limit':'128MB'})
    removed=con.execute('SELECT source_record_id,census_year,population FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))',[selected,ids]).fetchdf();con.close()
    assert len(removed)==3 and set(removed.census_year)=={2002,2010,2021}
    partition=set(pd.read_csv(out/'complete_publisher_partition_members.csv').source_record_id)
    qualified=set(pd.read_csv(out/'qualified_scope_source_id_credit_union.csv').source_record_id)
    refined=copy.deepcopy(report['all_three_component_points_national_unions'])
    for y in (2002,2010,2021):
        key=str(y) if str(y) in refined['by_year'] else y
        group=refined['by_year'][key];old=removed[removed.census_year==y].iloc[0];sid=old.source_record_id
        value=0 if pd.isna(old.population) else int(old.population)
        b=group['ordinary_all_three_component_point_uses'];b['rows']-=1;b['population']-=value;b['unknown_population_rows']=0
        assert b['rows']==export['rows'] and b['population']==export['population_by_year'].get(str(y),export['population_by_year'].get(y))
        axis=report['ordinary_axes_by_year'][str(y)] if str(y) in report['ordinary_axes_by_year'] else report['ordinary_axes_by_year'][y]
        b['population_percent_of_selected_ordinary']=100*b['population']/axis['denominator_population']
        b['row_percent_of_selected_ordinary']=100*b['rows']/axis['denominator_rows']
        p=group['all_three_component_points_plus_whole_partitions_plus_federal'];q=group['all_three_component_points_plus_partitions_plus_qualified_physical_scopes_plus_federal']
        for entry,retain in [(p,partition),(q,partition|qualified)]:
            if sid not in retain:
                entry['selected_source_id_union_rows']-=1
                entry['selected_source_id_union_population']-=value
                entry['combined_population']-=value
            entry['percent_of_national_control']=100*entry['combined_population']/entry['official_national_control']
            entry['percent_of_common_control']=100*entry['combined_population']/entry['common_three_census_control']
            entry['gap_to_99_percent_common']=max(0,math.ceil(.99*entry['common_three_census_control'])-entry['combined_population'])
        p['partition_net_population_added_by_source_id_union']=p['selected_source_id_union_population']-b['population']
        q['qualified_selected_source_id_union_net_population_added']=q['selected_source_id_union_population']-p['selected_source_id_union_population']
    refined['definition']='Ordinary full3 identity components require all three admitted own point uses AND three finite source populations. One unknown-2010 component is excluded for every census year. Accepted whole partitions, qualified physical selected-source-ID references and federal territories retain separate grains and exclusive source-ID union.'
    refined['excluded_unknown_population_components']=unknown
    refined['complete_number_count']=3
    return refined

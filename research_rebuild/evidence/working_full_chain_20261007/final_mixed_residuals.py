"""Prioritize remaining native observations after the final exclusive source-ID union."""
import math
import pandas as pd

def build(state,ordinary,componentpoints,partition_ids,qualified_ids,named_ids,out):
    blocked={state.uf.find(sid) for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(pop) or not math.isfinite(float(pop))}
    finite={sid for sid in componentpoints if state.uf.find(sid) not in blocked}
    credited=finite|set(partition_ids)|set(qualified_ids)|set(named_ids)
    frame=ordinary.copy()
    frame['credited_by_final_mixed_native_source_ID_union']=frame.source_record_id.isin(credited)
    frame['remaining_known_population']=frame.population.where(~frame.credited_by_final_mixed_native_source_ID_union,0)
    frame['remaining_unknown_population']=frame.population.isna() & ~frame.credited_by_final_mixed_native_source_ID_union
    frame['credited_known_population']=frame.population.where(frame.credited_by_final_mixed_native_source_ID_union,0)
    frame['empty_imported_population_quality']=frame.population_value_quality.isna() | frame.population_value_quality.eq('')
    ranked=frame.groupby(['census_year','region_norm']).agg(selected_known_ordinary_population=('population','sum'),selected_ordinary_rows=('source_record_id','count'),final_mixed_credited_known_population=('credited_known_population','sum'),remaining_known_native_population=('remaining_known_population','sum'),remaining_unknown_native_population_rows=('remaining_unknown_population','sum'),empty_imported_population_quality_rows=('empty_imported_population_quality','sum')).reset_index()
    counts=frame.loc[~frame.credited_by_final_mixed_native_source_ID_union].groupby(['census_year','region_norm']).size()
    ranked['remaining_native_rows']=[int(counts.get((r.census_year,r.region_norm),0)) for r in ranked.itertuples()]
    ranked['final_mixed_percent_of_selected_known_regional_population']=100*ranked.final_mixed_credited_known_population/ranked.selected_known_ordinary_population
    ranked['remaining_population_rank_within_year']=ranked.groupby('census_year').remaining_known_native_population.rank(method='first',ascending=False).astype(int)
    ranked.sort_values(['census_year','remaining_population_rank_within_year']).to_csv(out/'regional_final_mixed_residual_rank.csv',index=False)
    columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm','district_raw','population','population_value_quality','source_file','source_path','source_sha256','source_locator','oktmo','okato','credited_by_final_mixed_native_source_ID_union']
    summaries={}
    for year,group in frame.groupby('census_year'):
        remaining=group.loc[~group.credited_by_final_mixed_native_source_ID_union]
        remaining.nlargest(100,'population')[columns].to_csv(out/f'top100_final_mixed_residual_{int(year)}.csv',index=False)
        top=ranked.loc[ranked.census_year.eq(year)].nlargest(3,'remaining_known_native_population')
        summaries[int(year)]={'remaining_native_rows':len(remaining),'remaining_known_native_population':int(remaining.population.sum()),'remaining_unknown_native_population_rows':int(remaining.population.isna().sum()),'top_regions_by_remaining_known_population':top[['region_norm','remaining_known_native_population','remaining_native_rows']].to_dict('records')}
    return {'axis':'Actual uncredited ordinary native source IDs after finite ordinary full3/all-three-own-point components plus complete partitions, qualified native references and named-merger constituent credits. Federal territories remain separate national aggregates; regional denominators contain selected known ordinary population only.','unknown_population_never_zero_or_imputed':True,'regional_national_control_shortfall_not_allocated_to_NPs':True,'by_year':summaries}

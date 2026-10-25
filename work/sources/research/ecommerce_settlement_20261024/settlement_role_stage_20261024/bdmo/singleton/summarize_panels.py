"""Common panels retain one category and period, identical complete municipal keys.
Multiple singleton units mapping to one NP are collapsed only if all years agree.
"""
from pathlib import Path
import json
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
KEY='source_record_id_2021'
systems=pd.read_csv(BASE/'settlement_role_stage_20261024/system/centre_system_demography.csv')
medium=set(systems.loc[systems.medium_primary2002,KEY])
metadata=pd.read_parquet(BASE/'national/national_target_source2021.parquet').set_index(KEY)
summaries=[];conflicts=[]
for period,filename,years in [
    ('annual2015_2021','annual2015_2021_singleton_candidate_observations.parquet',list(range(2015,2022))),
    ('quarterIV2022_2024','quarterIV2022_2024_singleton_candidate_observations.parquet',[2022,2023,2024])]:
    rows=pd.read_parquet(OUT/filename)
    assert rows.obroz.eq('Магазины').all()
    assert rows.indicator_period.nunique()==1
    completeness=rows.groupby(['oktmo','mun_level']).year.nunique()
    complete=completeness.loc[completeness.eq(len(years))].reset_index()[['oktmo','mun_level']]
    selected=rows.merge(complete,on=['oktmo','mun_level'],validate='many_to_one')
    assert not selected.duplicated(['oktmo','mun_level','year']).any()
    panel=[]
    for source_id,g in selected.groupby(KEY):
        if g.groupby('year').indicator_value.nunique().gt(1).any():
            conflicts.append({'period':period,KEY:source_id,'reason':'overlapping_singleton_units_disagree_on_stock',
                              'oktmo_codes':','.join(sorted(g.oktmo.unique()))})
            continue
        byyear=g.groupby('year').indicator_value.first()
        assert len(byyear)==len(years)
        row={KEY:source_id,'name_2021':metadata.loc[source_id,'name_2021'],
             'region_2021':metadata.loc[source_id,'region_2021'],
             'medium_centre2002':source_id in medium,
             'municipal_codes_complete_panel':','.join(sorted(g.oktmo.unique())),
             'municipal_levels':';'.join(sorted(g.mun_level.unique())),
             'candidate_unit_count':len(g[['oktmo','mun_level']].drop_duplicates()),
             'obroz':'Магазины','period':period,
             'year_specific_np_identity_verified':False,
             'physical_openings_or_closures_identified':False}
        for y in years:row['shops_'+str(y)]=byyear[y]
        difference=byyear[years[-1]]-byyear[years[0]]
        row['stock_change']=difference
        row['stock_change_pct']=100*difference/byyear[years[0]] if byyear[years[0]]>0 else None
        row['stock_direction']='decline' if difference<0 else 'growth' if difference>0 else 'stable'
        panel.append(row)
    table=pd.DataFrame(panel)
    table.to_csv(OUT/(period+'_common_np_candidate_panel.csv'),index=False)
    for scope in ['all_singleton_np_candidates','medium_centres2002']:
        x=table if scope=='all_singleton_np_candidates' else table.loc[table.medium_centre2002]
        summaries.append({'period':period,'scope':scope,'complete_municipal_keys':len(complete),
            'unique_np_candidates_common_panel':len(x),
            'decline_n':int(x.stock_direction.eq('decline').sum()),
            'growth_n':int(x.stock_direction.eq('growth').sum()),
            'stable_n':int(x.stock_direction.eq('stable').sum()),
            'median_stock_change':x.stock_change.median(),
            'median_pct_change_excluding_zero_baseline':x.stock_change_pct.median(),
            'time_periods_not_combined':True,'settlement_unit_is_conditional':True})
pd.DataFrame(conflicts).to_csv(OUT/'overlapping_singleton_units_stock_conflicts.csv',index=False)
report={'status':'PASS_with_temporal_identity_limit','summaries':summaries,
        'np_unit_conflicts_excluded_n':len(conflicts),
        'definition':'full-register singleton in every available required vintage; exact same code/name/type to main census2021; same municipal key has every year; no municipal allocation, overlapping territorial reports retained only when every year agrees',
        'limits':'No year-specific2023/2024 composition; annual2015–2021 and IVquarter2022–2024 remain separate; stock differences are net changes, not gross closures or platform effects.'}
(OUT/'panel_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))

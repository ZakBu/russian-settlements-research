"""Independent demographic arithmetic, threshold sensitivity and same-schema WB checks."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parent.parent
HIST=BASE/'history_stage_20261024'
KEY='source_record_id_2021'
s=pd.read_csv(OUT/'centre_system_demography.csv')
d=pd.read_parquet(BASE/'national/national_target_source2021.parquet').set_index(KEY)
a=pd.read_parquet(HIST/'centres/settlement_admin_context_main2021.parquet').set_index(KEY)
parent='administrative_centre_source_record_id_2021_20200110'
strict=(d.population_value_quality_2002=='direct_published_census_value') & \
       (d.population_value_quality_2021=='direct_published_census_value')
sample=s.loc[s.medium_primary2002&s.demographic_comparison_supported]
examples=pd.concat([sample.nsmallest(5,'centre_population_share_change_pp'),
                    sample.nlargest(5,'centre_population_share_change_pp')]).drop_duplicates(KEY)
checks=[]
for _,row in examples.iterrows():
    centre=row[KEY]
    ids=set(a.index[(a[parent]==centre) & a.context_status_20200110.eq('accepted_administrative_parent_and_centre')])
    ids.add(centre)
    roster=d.loc[sorted(ids)]
    common=roster.loc[strict.loc[roster.index]]
    start=100*d.loc[centre,'population_2002']/sum(common.population_2002)
    finish=100*d.loc[centre,'population_2021']/sum(common.population_2021)
    diff=finish-start
    error=abs(diff-row.centre_population_share_change_pp)
    assert error<1e-9
    checks.append({'id':centre,'name':row.name_2021,'independent_share_change_pp':diff,
                   'saved_share_change_pp':row.centre_population_share_change_pp,'absolute_difference':error})
examples.to_csv(OUT/'individual_demographic_examples_verified.csv',index=False)

sensitivity=[]
for baseyear in [2002,2021]:
    pop=s[f'population_{baseyear}']
    for lower,upper in [(3000,30000),(5000,50000),(5000,100000)]:
        for coverage in [.90,.95,1.0]:
            g=s.loc[s.demographic_comparison_supported & pop.ge(lower)&pop.lt(upper)&
                    s.common_roster_population2021_coverage.ge(coverage-1e-12)]
            for threshold in [.5,1,2]:
                concentration=g.centre_population_share_change_pp.ge(threshold)
                loss=g.centre_population_share_change_pp.le(-threshold)
                shrink=g.centre_change2002_2021_pct.lt(0)
                sensitivity.append({'size_baseyear':baseyear,'lower_inclusive':lower,'upper_exclusive':upper,
                    'population2021_roster_coverage_min':coverage,'share_shift_threshold_pp':threshold,
                    'centres_n':len(g),'population_share_increase_n':int(concentration.sum()),
                    'population_share_decrease_n':int(loss.sum()),
                    'shrinking_centre_share_increase_n':int((shrink&concentration).sum()),
                    'shrinking_centre_share_decrease_n':int((shrink&loss).sum()),
                    'median_share_change_pp':g.centre_population_share_change_pp.median(),
                    'median_own_population_change_pct':g.centre_change2002_2021_pct.median()})
pd.DataFrame(sensitivity).to_csv(OUT/'demographic_definition_sensitivity.csv',index=False)

# Same URL and same source-code profile, no typePoint8/34 backcasting.
links=pd.read_parquet(HIST/'wb_history_symmetric_links.parquet')
raw=pd.read_parquet(HIST/'network/wb_history_normalized.parquet')
dates=['2022-11-18','2023-01-01']
raw=raw.loc[raw.source_country.eq('ru')&raw.archive_date.isin(dates)]
raw=raw.loc[raw.dtype.eq(0)&raw.isWb.eq(True)&raw.pickupType.isin([3,4])]
joined=raw[['archive_date','source_object_id']].merge(links,on=['archive_date','source_object_id'],validate='one_to_one')
centres=s[KEY].tolist()
groups={c:set(g.index) for c,g in a.loc[a.context_status_20200110.eq('accepted_administrative_parent_and_centre')].groupby(parent)}
for c in centres: groups.setdefault(c,set()).add(c)
output=[]
for radius in [1,5,10]:
    key=KEY+f'_{radius}km'
    count={date:g[key].value_counts() for date,g in joined.loc[joined[key].notna()].groupby('archive_date')}
    for c in centres:
        other=sorted(groups[c]-{c})
        first=count[dates[0]];last=count[dates[1]]
        before=first.get(c,0);after=last.get(c,0)
        members_before=int(first.reindex(other,fill_value=0).gt(0).sum())
        members_after=int(last.reindex(other,fill_value=0).gt(0).sum())
        total_before=before+first.reindex(other,fill_value=0).sum()
        total_after=after+last.reindex(other,fill_value=0).sum()
        typ=('centre_retained_and_other_footprint_expands' if before>0 and after>0 and members_after>members_before else
             'centre_retained_without_other_footprint_expansion' if before>0 and after>0 else
             'earlier_centre_only_catalogue_record' if before>0 and after==0 else
             'later_centre_record_not_earlier' if before==0 and after>0 else 'no_centre_record_both_dates')
        output.append({KEY:c,'radius_km':radius,'source_profile':'dtype0_isWbTrue_pickupType3or4',
            'centre_before':int(before),'centre_after':int(after),
            'other_positive_members_before':members_before,'other_positive_members_after':members_after,
            'other_positive_members_change':members_after-members_before,
            'centre_object_share_before_pct':100*before/total_before if total_before>0 else np.nan,
            'centre_object_share_after_pct':100*after/total_after if total_after>0 else np.nan,
            'catalogue_type':typ,'date_before':dates[0],'date_after':dates[1]})
short=pd.DataFrame(output).merge(s[[KEY,'medium_primary2002','demographic_comparison_supported','demographic_type']],on=KEY,validate='many_to_one')
short.to_csv(OUT/'same_schema_short_interval_typology.csv',index=False)
cases=short.loc[short.radius_km.eq(5)&short.medium_primary2002&short.demographic_comparison_supported&
                short.catalogue_type.eq('centre_retained_and_other_footprint_expands')].merge(
    s[[KEY,'name_2021','region_2021','centre_population_share_change_pp','centre_change2002_2021_pct']],
    on=KEY,validate='one_to_one')
case_rows=[]
for _,case in cases.iterrows():
    c=case[KEY]
    after=joined.loc[joined.archive_date.eq(dates[1])&joined[KEY+'_5km'].isin(groups[c]-{c})]
    before_nodes=set(joined.loc[joined.archive_date.eq(dates[0]),KEY+'_5km'].dropna())
    new_nodes=set(after[KEY+'_5km'].dropna())-before_nodes
    previous_raw_ids=set(raw.loc[raw.archive_date.eq(dates[0]),'source_object_id'])
    after_new=after.loc[after[KEY+'_5km'].isin(new_nodes)]
    record=case.to_dict()
    record['new_other_catalogue_positive_member_ids']=json.dumps(sorted(new_nodes))
    record['new_other_catalogue_positive_member_names']=json.dumps([d.loc[i,'name_2021'] for i in sorted(new_nodes)],ensure_ascii=False)
    record['new_member_points_with_id_absent_previous_same_source_profile_n']=int((~after_new.source_object_id.isin(previous_raw_ids)).sum())
    record['physical_openings_established']=False
    case_rows.append(record)
pd.DataFrame(case_rows).to_csv(OUT/'same_schema_receipt_dispersion_individual_cases.csv',index=False)
summary=short.loc[short.medium_primary2002&short.demographic_comparison_supported]
summary.groupby(['radius_km','catalogue_type']).size().rename('centres_n').reset_index().to_csv(
    OUT/'same_schema_short_interval_summary.csv',index=False)
result={'status':'PASS','independent_demographic_example_checks':checks,
        'sensitivity_specs_n':len(sensitivity),
        'same_schema_raw_profile_source_counts':raw.groupby('archive_date').size().to_dict(),
        'same_schema_typology_main5km':summary.loc[summary.radius_km.eq(5)].catalogue_type.value_counts().to_dict(),
        'same_schema_limit':'44-day source-catalogue interval; not a long-term settlement-system change; source flags remain raw classifications, not independently confirmed client PVZ; no openings/closures inferred',
        'no_typePoint_backcast':True}
(OUT/'independent_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))

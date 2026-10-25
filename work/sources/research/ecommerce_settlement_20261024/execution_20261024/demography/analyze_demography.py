"""Descriptive placement selection; never an estimated marketplace treatment effect.
Run: PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 analyze_demography.py
All inputs are retained; writes are confined to this script's directory.
"""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
BASE = OUT.parent.parent
NATIONAL = BASE / 'national'
INPUT = NATIONAL / 'ozon_WB_comparison_main_target_experimental.parquet'
d = pd.read_parquet(INPUT)
assert len(d) == 144151
assert d.source_record_id_2021.is_unique
assert d.root_accepted20261022.is_unique
assert (d.population_2021.dropna() >= 0).all()
assert d.analysis_population.nunique() == 1

def records(frame):
    return json.loads(frame.to_json(orient='records'))

def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

quality = {
    'rows': len(d), 'regions': d.region_2021.nunique(),
    'unique_source2021': bool(d.source_record_id_2021.is_unique),
    'population_nulls': {str(y): int(d[f'population_{y}'].isna().sum()) for y in [2002,2010,2021]},
    'quality_counts': {str(y): d[f'population_value_quality_{y}'].fillna('NULL').value_counts().to_dict() for y in [2002,2010,2021]},
    'wb_status_counts': d.WB_evidence_status.value_counts().to_dict(),
    'input_sha256': hashlib.sha256(INPUT.read_bytes()).hexdigest(),
    'boundary_comparability': 'not_independently_verified',
    '2010_primary_filter': 'exclude secondary_confidentiality_protected_value_exact_scope_unverified and reviewed_context_specific_dash_interpretation',
}
wb_known = ~d.WB_evidence_status.str.contains('unknown', na=True)
d['wb_positive'] = d.WB_focus20261021_count.gt(0)
d['rural_urban'] = np.where(d.type_2021.isin(['город','пгт']), 'urban', 'rural')
for radius in [1,5,10]:
    d[f'ozon_{radius}km_positive'] = d[f'ozon_pickup_inferred_accepted_{radius}km_count'].gt(0)
    d[f'either_{radius}km_positive'] = d.wb_positive | d[f'ozon_{radius}km_positive']

strict02 = d.population_value_quality_2002.eq('direct_published_census_value')
strict21 = d.population_value_quality_2021.eq('direct_published_census_value')
strict10 = d.population_value_quality_2010.notna() & ~d.population_value_quality_2010.isin([
    'secondary_confidentiality_protected_value_exact_scope_unverified',
    'reviewed_context_specific_dash_interpretation',
])
# Avoid fabricated ratios for zero baselines; retain zero endpoint as separate state.
quality['endpoint02_21_direct_with_both_values'] = int((strict02 & strict21 & d.population_2002.notna() & d.population_2021.notna()).sum())
quality['endpoint02_21_direct_positive2002'] = int((strict02 & strict21 & d.population_2002.gt(0)).sum())
quality['2010_primary_valid_three_values'] = int((strict02 & strict10 & strict21 & d[['population_2002','population_2010','population_2021']].notna().all(axis=1)).sum())

summary = []
strata_results = []
stratum_rows = []
trajectory_rows = []
for start,end,quality_filter in [
    (2002,2021,strict02 & strict21),
    (2002,2010,strict02 & strict10),
    (2010,2021,strict10 & strict21),
]:
    sample = d.loc[quality_filter & d[f'population_{start}'].gt(0) & d[f'population_{end}'].notna()].copy()
    sample['decline'] = sample[f'population_{end}'].lt(sample[f'population_{start}'])
    sample['change_pct'] = 100*(sample[f'population_{end}']/sample[f'population_{start}']-1)
    sample['zero_endpoint'] = sample[f'population_{end}'].eq(0)
    period = f'{start}_{end}'
    for exposure in ['wb_positive','ozon_1km_positive','ozon_5km_positive','ozon_10km_positive',
                     'either_1km_positive','either_5km_positive','either_10km_positive']:
        x = sample.copy()
        # Unknown WB bridge is not an accepted-zero comparator.
        if exposure == 'wb_positive':
            x = x.loc[wb_known.loc[x.index]]
        elif exposure.startswith('either'):
            x = x.loc[wb_known.loc[x.index] | x[exposure]]
        for group, g in x.groupby(exposure):
            summary.append({
                'period': period, 'exposure': exposure, 'positive_evidence': bool(group),
                'n': len(g), 'decline_n': int(g.decline.sum()),
                'decline_share_pct': 100*g.decline.mean(),
                'median_population_change_pct': g.change_pct.median(),
                'mean_population_change_pct': g.change_pct.mean(),
                'zero_endpoint_n': int(g.zero_endpoint.sum()),
                'median_population_2021': g.population_2021.median(),
                'population_2021_sum': g.population_2021.sum(),
            })
        # Positive current population avoids mechanically contrasting depopulated settlements.
        x = x.loc[x.population_2021.gt(0)]
        for strata_name, keys in [
            ('size2021', ['size2021']),
            ('region_size2021', ['region_2021','size2021']),
            ('region_size2021_type', ['region_2021','size2021','rural_urban']),
        ]:
            grouped = x.groupby(keys + [exposure], observed=True).agg(
                n=('decline','size'), decline=('decline','mean'),
                mean_change_pct=('change_pct','mean')).reset_index()
            pos=grouped.loc[grouped[exposure]].drop(columns=exposure)
            neg=grouped.loc[~grouped[exposure]].drop(columns=exposure)
            common=pos.merge(neg,on=keys,suffixes=('_positive','_no_positive'))
            common=common.loc[(common.n_positive>=5)&(common.n_no_positive>=5)].copy()
            if common.empty:
                continue
            common['n_pooled']=common.n_positive+common.n_no_positive
            w=common.n_pooled/common.n_pooled.sum()
            pp=100*float((w*common.decline_positive).sum())
            pn=100*float((w*common.decline_no_positive).sum())
            strata_results.append({
                'period':period,'exposure':exposure,'strata':strata_name,
                'min_n_per_group':5,'common_strata_n':len(common),
                'eligible_n':len(x),'supported_n':int(common.n_pooled.sum()),
                'positive_supported_n':int(common.n_positive.sum()),
                'no_positive_supported_n':int(common.n_no_positive.sum()),
                'positive_total_n':int(x[exposure].sum()),
                'no_positive_total_n':int((~x[exposure]).sum()),
                'supported_pct':100*common.n_pooled.sum()/len(x),
                'raw_inhabited_decline_positive_pct':100*x.loc[x[exposure],'decline'].mean(),
                'raw_inhabited_decline_no_positive_pct':100*x.loc[~x[exposure],'decline'].mean(),
                'common_support_crude_positive_pct':100*float((common.n_positive*common.decline_positive).sum()/common.n_positive.sum()),
                'common_support_crude_no_positive_pct':100*float((common.n_no_positive*common.decline_no_positive).sum()/common.n_no_positive.sum()),
                'standardized_decline_positive_pct':pp,
                'standardized_decline_no_positive_pct':pn,
                'difference_percentage_points':pp-pn,
            })
            if exposure in ['wb_positive','either_5km_positive'] and period=='2002_2021' and strata_name=='region_size2021_type':
                common['exposure']=exposure
                common['period']=period
                stratum_rows.extend(records(common))
        if period=='2002_2021' and exposure=='either_5km_positive':
            for size,g in x.groupby('size2021',observed=True):
                for decline,h in g.groupby('decline'):
                    trajectory_rows.append({
                        'size2021':size,'decline_2002_2021':bool(decline),'n':len(h),
                        'positive_n':int(h[exposure].sum()),
                        'positive_share_pct':100*h[exposure].mean(),
                    })

# Primary placement comparison conditions on population at START of trajectory.
# End-size stratification above is supplementary and can be mechanically endogenous.
d['size2002'] = pd.cut(d.population_2002,
    bins=[0,100,500,1000,3000,10000,50000,100000,500000,np.inf],
    labels=['01_1_100','02_101_500','03_501_1000','04_1001_3000',
            '05_3001_10000','06_10001_50000','07_50001_100000',
            '08_100001_500000','09_over_500000'],right=True)
baseline_results=[]
baseline_strata=[]
for exposure in ['wb_positive','ozon_1km_positive','ozon_5km_positive','ozon_10km_positive',
                 'either_1km_positive','either_5km_positive','either_10km_positive']:
    x=d.loc[strict02 & strict21 & d.population_2002.gt(0)].copy()
    x['decline']=x.population_2021.lt(x.population_2002)
    if exposure=='wb_positive':
        x=x.loc[wb_known.loc[x.index]]
    elif exposure.startswith('either'):
        x=x.loc[wb_known.loc[x.index] | x[exposure]]
    for endpoint_filter in ['all_observed2021','positive_population2021']:
        z=x if endpoint_filter=='all_observed2021' else x.loc[x.population_2021.gt(0)]
        for strata_name,keys in [('region_size2002',['region_2021','size2002']),
                                ('region_size2002_current_type',['region_2021','size2002','rural_urban'])]:
            g=z.groupby(keys+[exposure],observed=True).agg(n=('decline','size'),decline=('decline','mean')).reset_index()
            c=g.loc[g[exposure]].drop(columns=exposure).merge(
                g.loc[~g[exposure]].drop(columns=exposure),on=keys,suffixes=('_positive','_no_positive'))
            for min_n in [5,10,20]:
                a=c.loc[(c.n_positive>=min_n)&(c.n_no_positive>=min_n)].copy()
                if a.empty:
                    continue
                pooled=a.n_positive+a.n_no_positive
                w=pooled/pooled.sum()
                pp=100*float((w*a.decline_positive).sum())
                pn=100*float((w*a.decline_no_positive).sum())
                overlap=a.n_positive*a.n_no_positive/pooled
                ow=overlap/overlap.sum()
                op=100*float((ow*a.decline_positive).sum())
                on=100*float((ow*a.decline_no_positive).sum())
                baseline_results.append({'exposure':exposure,'strata':strata_name,
                    'endpoint_filter':endpoint_filter,'min_n_per_group':min_n,
                    'common_strata_n':len(a),'eligible_n':len(z),'supported_n':int(pooled.sum()),
                    'supported_pct':100*pooled.sum()/len(z),
                    'positive_supported_n':int(a.n_positive.sum()),
                    'no_positive_supported_n':int(a.n_no_positive.sum()),
                    'raw_decline_positive_pct':100*z.loc[z[exposure],'decline'].mean(),
                    'raw_decline_no_positive_pct':100*z.loc[~z[exposure],'decline'].mean(),
                    'standardized_decline_positive_pct':pp,
                    'standardized_decline_no_positive_pct':pn,
                    'difference_percentage_points':pp-pn,
                    'overlap_weighted_decline_positive_pct':op,
                    'overlap_weighted_decline_no_positive_pct':on,
                    'overlap_weighted_difference_pp':op-on})
                if exposure=='either_5km_positive' and min_n==5:
                    a['endpoint_filter']=endpoint_filter
                    a['strata']=strata_name
                    baseline_strata.extend(records(a))
pd.DataFrame(baseline_results).to_csv(OUT/'trajectory_baseline2002_standardized.csv',index=False)
pd.DataFrame(baseline_strata).to_csv(OUT/'baseline2002_common_strata.csv',index=False)

pd.DataFrame(summary).to_csv(OUT/'trajectory_raw.csv',index=False)
pd.DataFrame(strata_results).to_csv(OUT/'trajectory_standardized.csv',index=False)
pd.DataFrame(stratum_rows).to_csv(OUT/'common_support_strata.csv',index=False)
pd.DataFrame(trajectory_rows).to_csv(OUT/'presence_by_size_and_decline.csv',index=False)

# Urban official annual panel: descriptive only, future 2026 network state.
u=pd.read_parquet(NATIONAL/'urban_population_panel_main_wide.parquet')
assert u.source_record_id_2021.is_unique
u=u.merge(d[['source_record_id_2021','ozon_5km_positive','either_5km_positive']],on='source_record_id_2021',validate='one_to_one')
u['wb_positive']=u.WB_focus20261021_count.gt(0)
u=u.loc[u.complete_2023_2025 & u.population_2023.gt(0)].copy()
u['change_2023_2025_pct']=100*(u.population_2025/u.population_2023-1)
u['decline_2023_2025']=u.population_2025.lt(u.population_2023)
urban=[]
for exposure in ['wb_positive','ozon_5km_positive','either_5km_positive']:
    x=u
    if exposure=='wb_positive':
        x=x.loc[~x.WB_evidence_status.str.contains('unknown',na=True)]
    elif exposure.startswith('either'):
        x=x.loc[~x.WB_evidence_status.str.contains('unknown',na=True)|x[exposure]]
    for group,g in x.groupby(exposure):
        urban.append({'exposure_2026':exposure,'positive_evidence':bool(group),
                      'n':len(g),'decline_n':int(g.decline_2023_2025.sum()),
                      'decline_share_pct':100*g.decline_2023_2025.mean(),
                      'median_change_2023_2025_pct':g.change_2023_2025_pct.median(),
                      'median_population_2023':g.population_2023.median(),
                      'interpretation':'descriptive_association_future_network_not_treatment_effect',
                      'boundaries':'unknown_not_independently_verified'})
pd.DataFrame(urban).to_csv(OUT/'urban_2023_2025_descriptive.csv',index=False)
quality['urban_complete_rows']=2149
quality['urban_complete_positive2023_rows']=len(u)
quality['urban_complete_zero2023_rows']=2149-len(u)
quality['urban_missing_or_incomplete']=104
# Support and value checks for output hygiene.
s=pd.DataFrame(strata_results)
assert s.supported_pct.between(0,100).all()
assert s.standardized_decline_positive_pct.between(0,100).all()
assert s.standardized_decline_no_positive_pct.between(0,100).all()
assert (s.supported_n==s.positive_supported_n+s.no_positive_supported_n).all()
quality['checks']='PASS: unique identities, nonnegative population, common support reconciliation, bounded probabilities'
dump('audit.json',quality)
print(json.dumps({'quality':quality,'raw_key':records(pd.DataFrame(summary).query("period=='2002_2021' and exposure in ['wb_positive','either_5km_positive']")),
                  'standardized_key':records(s.query("period=='2002_2021' and exposure in ['wb_positive','either_5km_positive']")),
                  'urban':urban},ensure_ascii=False,indent=2))

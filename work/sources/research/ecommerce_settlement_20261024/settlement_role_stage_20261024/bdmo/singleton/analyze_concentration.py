"""Functional concentration of shops: internal singleton centre C / whole district S.
Municipal totals are never allocated among multiple settlements.
Run after build_singleton.py using the same PYTHONPATH.
"""
from pathlib import Path
from collections import Counter
import json
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
KEY='source_record_id_2021'
upper='Муниципальное образование верхнего уровня'
lower='Муниципальное образование нижнего уровня'
full=pd.read_parquet(OUT.parent/'shop_object_counts_all_municipal_levels.parquet')
w=pd.read_csv(OUT/'singleton_stability_candidates.csv',dtype={'oktmo':str},keep_default_na=False)
centres=pd.read_csv(BASE/'history_stage_20261024/centres/centres_20200110.csv',
                    dtype={'municipality_oktmo8':str},keep_default_na=False)
counts=centres.loc[centres.source_record_id_2021.ne('')].source_record_id_2021.value_counts()
valid_centres=centres.loc[centres.source_record_id_2021.ne('')&
                         centres.source_record_id_2021.map(counts).eq(1)]
child=w.loc[w.mun_level.eq(lower)&w.stable2020_2026_singleton_candidate.eq(True)].copy()
child['parent_oktmo']=child.oktmo.str[:5]+'000'
candidates=child.merge(valid_centres[['municipality_oktmo8','source_record_id_2021','municipality_name']],
    left_on=['parent_oktmo','stable2020_2026_source_record_id_2021'],
    right_on=['municipality_oktmo8','source_record_id_2021'],validate='many_to_one')
assert candidates.source_record_id_2021.is_unique
candidates.to_csv(OUT/'internal_singleton_centre_district_candidates.csv',index=False)
system=pd.read_csv(BASE/'settlement_role_stage_20261024/system/centre_system_demography.csv')

results=[];panels=[];issues=[]
categories=['Магазины','Специализированные непродовольственные магазины']
for category in categories:
    raw=full.loc[full.obroz.eq(category)&full.year.isin([2022,2023,2024])&
                 full.indicator_period.eq('IV квартал')].copy()
    keys=['oktmo','mun_level','year']
    keycounts=raw.groupby(keys).indicator_value.nunique(dropna=False)
    badkeys=keycounts.loc[keycounts.ne(1)].reset_index()[keys]
    raw=raw.merge(badkeys.assign(conflict=True),on=keys,how='left',validate='many_to_one')
    raw=raw.loc[~raw.conflict.eq(True)].drop_duplicates(keys)
    assert not raw.duplicated(keys).any()
    children=raw.loc[raw.mun_level.eq(lower),['oktmo','year','indicator_value','mun_type','municipality']].rename(
        columns={'indicator_value':'centre_singleton_municipal_shops','mun_type':'centre_mun_type',
                 'municipality':'centre_municipality'})
    parents=raw.loc[raw.mun_level.eq(upper),['oktmo','year','indicator_value','mun_type','municipality']].rename(
        columns={'oktmo':'parent_oktmo','indicator_value':'district_shops','mun_type':'parent_mun_type',
                 'municipality':'parent_municipality'})
    x=candidates[['oktmo','parent_oktmo',KEY]].merge(children,on='oktmo',how='inner',validate='one_to_many')
    x=x.merge(parents,on=['parent_oktmo','year'],how='inner',validate='many_to_one')
    x['category']=category
    x['period']='IV квартал'
    x['denominator_valid']=x.district_shops.gt(0)&x.district_shops.ge(x.centre_singleton_municipal_shops)
    x['lower_municipal_type_valid']=x.centre_mun_type.isin(['Городское поселение','Сельское поселение'])
    x['upper_municipal_type_valid']=x.parent_mun_type.eq('Муниципальный район')
    x['year_specific_singleton_composition_independently_verified']=False
    x['actual_settlement_shop_inventory_geolocated']=False
    x['centre_share_pct']=100*x.centre_singleton_municipal_shops/x.district_shops.where(x.district_shops.gt(0))
    x['valid_observation']=x.denominator_valid&x.lower_municipal_type_valid&x.upper_municipal_type_valid
    invalid=x.loc[~x.valid_observation].copy()
    if len(invalid):issues.append(invalid)
    x=x.merge(system[[KEY,'name_2021','region_2021','population_2002','population_2021','medium_primary2002']],
              on=KEY,how='left',validate='many_to_one')
    x.to_csv(OUT/('shops_concentration_observations.csv' if category=='Магазины' else
                  'specialized_nonfood_concentration_observations.csv'),index=False)
    valid=x.loc[x.valid_observation]
    completeness=valid.groupby(KEY).year.nunique()
    complete_ids=completeness.index[completeness.eq(3)]
    complete=valid.loc[valid[KEY].isin(complete_ids)]
    assert not complete.duplicated([KEY,'year']).any()
    for centre,g in complete.groupby(KEY):
        g=g.set_index('year')
        first=g.loc[2022];last=g.loc[2024]
        stockdiff=last.centre_singleton_municipal_shops-first.centre_singleton_municipal_shops
        sharediff=last.centre_share_pct-first.centre_share_pct
        typ=('centre_stock_decline_share_loss' if stockdiff<0 and sharediff<0 else
             'centre_stock_decline_share_not_lost' if stockdiff<0 else
             'centre_stock_growth_share_loss' if stockdiff>0 and sharediff<0 else
             'centre_stock_growth_share_not_lost' if stockdiff>0 else
             'centre_stock_stable_share_loss' if sharediff<0 else 'centre_stock_stable_share_not_lost')
        record={KEY:centre,'name_2021':first.name_2021,'region_2021':first.region_2021,
            'category':category,'period':'IV квартал','centre_oktmo':first.oktmo,
            'district_oktmo':first.parent_oktmo,'medium_primary2002':first.medium_primary2002,
            'centre_stock_change2022_2024':stockdiff,'centre_share_change2022_2024_pp':sharediff,
            'functional_stock_share_typology':typ,
            'singleton_status':'same_one_NP_in_available2020_2021_2022_2026_registers_not_year_specific',
            'boundaries_verified':False,'causal_effect_identified':False}
        for year in [2022,2023,2024]:
            record['centre_shops_'+str(year)]=g.loc[year,'centre_singleton_municipal_shops']
            record['district_shops_'+str(year)]=g.loc[year,'district_shops']
            record['centre_share_pct_'+str(year)]=g.loc[year,'centre_share_pct']
        panels.append(record)
    selected=[r for r in panels if r['category']==category]
    for scope in ['all_candidate_centres','medium2002']:
        selection=[r for r in selected if scope=='all_candidate_centres' or r['medium_primary2002']]
        results.append({'category':category,'scope':scope,'candidate_centres_n':len(candidates),
            'source_conflicting_keys_excluded_n':len(badkeys),'valid_complete_panel_n':len(selection),
            'centre_stock_decline_n':sum(r['centre_stock_change2022_2024']<0 for r in selection),
            'centre_stock_growth_n':sum(r['centre_stock_change2022_2024']>0 for r in selection),
            'centre_stock_stable_n':sum(r['centre_stock_change2022_2024']==0 for r in selection),
            'centre_share_loss_n':sum(r['centre_share_change2022_2024_pp']<0 for r in selection),
            'median_centre_share_change_pp':pd.Series([r['centre_share_change2022_2024_pp'] for r in selection],dtype=float).median(),
            'typology':dict(Counter(r['functional_stock_share_typology'] for r in selection))})
pd.DataFrame(panels).to_csv(OUT/'internal_centre_district_common_panels2022_2024.csv',index=False)
if issues:pd.concat(issues).to_csv(OUT/'concentration_invalid_observations.csv',index=False)
report={'status':'PASS_conditional_singleton_identity','candidate_internal_centres_n':len(candidates),
    'scope':'internal singleton lower-level municipality is official centre of exactly one upper district2020; exact first5 parent; no external-centre sums or municipal allocation',
    'periods':'IV quarter2022/2023/2024 only; category labels exact; no annual or2025 combinations',
    'identity_limit':'Full composition2023/2024 unavailable. Singleton across available four vintages is candidacy, not verified observation-year territorial equivalence. Metric is lower-municipality share of whole district physical stock, conditionally assigned to its sole named NP.',
    'no_opening_closure_or_platform_effect_inference':True,'results':results}
(OUT/'concentration_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:v.item())+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:v.item()))

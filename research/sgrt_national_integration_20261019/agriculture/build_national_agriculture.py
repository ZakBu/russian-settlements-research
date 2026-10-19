"""Nationwide native-code agricultural context; no historical SGRT geometry."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[2]
GROUPS=['grain','technical','fodder','potato','vegetables','melon']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def code(x):
    s=x.astype('string').str.strip()
    return s.where(s.str.fullmatch(r'\d{7,8}',na=False)).str.zfill(8)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=ROOT);ap.add_argument('--out',type=Path,default=Path(__file__).parent);a=ap.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
    old=a.base/'restored/extracted/research/sgrt_recovered_20261019/agriculture';panelpath=a.base/'anchor_research_20261019/data/point_axis.parquet';panel=pd.read_parquet(panelpath)
    r=pd.read_parquet(old/'municipal_series_2006_2024.parquet');r['oktmo']=code(r.oktmo)
    # Already extracted official categories, reapply duplicate quarantine at native key.
    key=['oktmo','year','group'];dup=r.duplicated(key,False);r[dup].to_csv(out/'source_duplicates_quarantined.csv.gz',index=False);clean=r[~dup].copy()
    counts=clean.groupby(['year','group','indicator_unit'],dropna=False).agg(rows=('oktmo','size'),nonmissing=('indicator_value','count'),municipalities=('oktmo','nunique')).reset_index();counts.to_csv(out/'series_coverage.csv',index=False)
    x=clean[clean.group.ne('production')].pivot(index=['oktmo','year'],columns='group',values='indicator_value').reset_index()
    for g in ['total']+GROUPS:
        if g not in x:x[g]=np.nan
    x['observed_groups']=x[GROUPS].notna().sum(axis=1)
    x['observed_sum']=x[GROUPS].sum(axis=1,min_count=1)
    x['tolerance_ha']=np.maximum(1e-8,x.total.abs()*.02)
    x['inconsistent']=x.total.lt(0)|x[GROUPS].lt(0).any(axis=1)|x.observed_sum.gt(x.total+x.tolerance_ha)|(x.total.eq(0)&x[GROUPS].gt(0).any(axis=1))
    vals=x[GROUPS].fillna(0).to_numpy();tot=x.total.to_numpy();shares=np.divide(vals,tot[:,None],out=np.zeros_like(vals),where=tot[:,None]>0)
    x['dominance']=shares.max(axis=1);x['dominant_group']=[GROUPS[i] for i in shares.argmax(axis=1)];x['known_share']=np.divide(vals.sum(axis=1),tot,out=np.zeros(len(x)),where=tot>0)
    x['profile']=np.select([x.inconsistent|x.total.isna(),x.total.eq(0),x.dominance.ge(.5),x[GROUPS].notna().all(axis=1)&x.known_share.ge(.9)],['missing','zero_sown',x.dominant_group,'mixed'],default='missing')
    # Exact equal observed maxima must not depend on the order of GROUPS.
    # Classification ties are a subset: valid records satisfying dominance>=.5.
    largest=x[GROUPS].max(axis=1)
    equal=x[GROUPS].eq(largest,axis=0)&x[GROUPS].notna()
    x['largest_observed_group_tie']=largest.gt(0)&equal.sum(axis=1).gt(1)
    x['dominance_tie']=x.profile.isin(GROUPS)&x.largest_observed_group_tie
    x['equally_dominant_profiles']=['|'.join(g for g in GROUPS if bool(equal.loc[i,g])) if bool(x.loc[i,'dominance_tie']) else '' for i in x.index]
    x['dominant_group_informative']=x.total.gt(0)&largest.gt(0)&~x.inconsistent&~x.largest_observed_group_tie
    x.loc[~x.dominant_group_informative,'dominant_group']=pd.NA
    x.loc[x.dominance_tie,'profile']='ambiguous'
    for i,g in enumerate(GROUPS):x[g+'_share']=np.where(x.total.gt(0)&x[g].notna(),shares[:,i],np.where(x.total.eq(0)&~x.inconsistent,0,np.nan))
    meta=clean[clean.group.eq('total')][['oktmo','year','municipality','region_name','oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to','indicator_unit']]
    assert not meta.duplicated(['oktmo','year']).any()
    x=x.merge(meta,on=['oktmo','year'],how='left',validate='one_to_one');x.to_parquet(out/'municipal_crop_annual_profiles.parquet',index=False)
    x[x.dominance_tie].to_csv(out/'dominance_tie_cases.csv',index=False)
    # Use the frozen, previously checked 2021 profiles; preserve exact original values.
    f=pd.read_csv(old/'municipal_crop_profiles_2021.csv',dtype={'oktmo':'string','oktmo_stable':'string','oktmo_year_from':'string','oktmo_year_to':'string'});f['oktmo']=code(f.oktmo);assert f.oktmo.is_unique
    compare=f[['oktmo','municipal_profile']].merge(x[x.year.eq(2021)][['oktmo','profile']],on='oktmo',how='outer',indicator=True,validate='one_to_one')
    compare['same']=compare.municipal_profile.eq(compare.profile)&compare._merge.eq('both');compare.to_csv(out/'profile2021_frozen_recalculation_comparison.csv',index=False)
    maincols={'oktmo':'municipality_code','municipal_profile':'municipal_profile_2021','total':'total_ha_2021','municipality':'source_municipality_name_2021','oktmo_stable':'source_stable_code_2021','oktmo_history':'source_code_history_2021','oktmo_year_from':'source_code_year_from_2021','oktmo_year_to':'source_code_year_to_2021','inconsistent':'profile2021_inconsistent','complete':'profile2021_complete','municipal_dominance':'dominance_2021','sum_known_share':'sum_known_share_2021'}
    snap=f[list(maincols)+GROUPS].rename(columns=maincols)
    ties2021=x[x.year.eq(2021)][['oktmo','dominance_tie','equally_dominant_profiles']].rename(columns={'oktmo':'municipality_code','dominance_tie':'dominance_tie_2021','equally_dominant_profiles':'equally_dominant_profiles_2021'})
    snap=snap.merge(ties2021,on='municipality_code',how='left',validate='one_to_one')
    for g in GROUPS:
        snap.rename(columns={g:g+'_ha_2021'},inplace=True)
        snap[g+'_share_2021']=np.where(snap.total_ha_2021.gt(0),snap[g+'_ha_2021']/snap.total_ha_2021,np.where(snap.total_ha_2021.eq(0)&~snap.profile2021_inconsistent,0,np.nan))
    # Last observed total and last valid classification are intentionally different.
    latest=x[x.total.notna()].sort_values('year').drop_duplicates('oktmo',keep='last')
    cols=['oktmo','year','profile','total','observed_groups','inconsistent','oktmo_history','oktmo_year_from','oktmo_year_to','dominant_group','dominance_tie','equally_dominant_profiles','largest_observed_group_tie','dominant_group_informative']
    rename={'oktmo':'municipality_code','year':'latest_crop_year','profile':'latest_crop_profile','total':'latest_crop_total_ha','observed_groups':'latest_crop_observed_groups','inconsistent':'latest_crop_inconsistent','oktmo_history':'latest_crop_code_history','oktmo_year_from':'latest_crop_code_year_from','oktmo_year_to':'latest_crop_code_year_to','dominant_group':'latest_crop_dominant_group','dominance_tie':'latest_crop_dominance_tie','equally_dominant_profiles':'latest_crop_equally_dominant_profiles','largest_observed_group_tie':'latest_crop_largest_observed_group_tie','dominant_group_informative':'latest_crop_dominant_group_informative'}
    latest=latest[cols].rename(columns=rename)
    valid=x[~x.profile.isin(['missing','ambiguous'])].sort_values('year').drop_duplicates('oktmo',keep='last')[['oktmo','year','profile']].rename(columns={'oktmo':'municipality_code','year':'latest_valid_profile_year','profile':'latest_valid_profile'})
    production=clean[clean.group.eq('production')&clean.indicator_value.notna()&clean.indicator_value.ge(0)].sort_values('year').drop_duplicates('oktmo',keep='last')[['oktmo','year','indicator_value','indicator_unit']].rename(columns={'oktmo':'municipality_code','year':'latest_production_year','indicator_value':'latest_production_nominal_thousand_rub','indicator_unit':'latest_production_source_unit'})
    municipal=snap.merge(latest,on='municipality_code',how='outer',validate='one_to_one').merge(valid,on='municipality_code',how='outer',validate='one_to_one').merge(production,on='municipality_code',how='outer',validate='one_to_one')
    for yr in [2010,2021]:
        prodyr=clean[clean.group.eq('production')&clean.year.eq(yr)][['oktmo','indicator_value']].rename(columns={'oktmo':'municipality_code','indicator_value':f'production_nominal_thousand_rub_{yr}'})
        municipal=municipal.merge(prodyr,on='municipality_code',how='outer',validate='one_to_one')
    baseline=x[x.year.eq(2010)][['oktmo','total','profile']].rename(columns={'oktmo':'municipality_code','total':'total_ha_2010_native_code','profile':'municipal_profile_2010_native_code'})
    municipal=municipal.merge(baseline,on='municipality_code',how='outer',validate='one_to_one')
    annualcov=clean.groupby('oktmo').agg(series_min_year=('year','min'),series_max_year=('year','max'),series_rows=('year','size'),series_observed_values=('indicator_value','count'),series_year_count=('year','nunique')).reset_index().rename(columns={'oktmo':'municipality_code'})
    municipal=municipal.merge(annualcov,on='municipality_code',how='outer',validate='one_to_one');municipal['profile2021_covered']=municipal.municipal_profile_2021.notna()&municipal.municipal_profile_2021.ne('missing');municipal['latest_crop_age_to2026']=2026-municipal.latest_crop_year
    municipal.to_parquet(out/'municipal_agriculture_snapshot.parquet',index=False);municipal.to_csv(out/'municipal_agriculture_snapshot.csv',index=False)
    p=panel[['id','region','municipality_oktmo8_2021','municipality_context_status','municipality_source_row_ambiguous']].copy();p['municipality_code']=code(p.municipality_oktmo8_2021)
    ambiguous=p.municipality_source_row_ambiguous.astype('string').str.lower().eq('true')
    p['bridge_ambiguous']=ambiguous;p['bridge_status']=np.select([ambiguous,p.municipality_code.isna()],['ambiguous_source_claims_validated_parent_code','missing_native_upper_code'],default='exact_native_upper_context_2021')
    p=p.merge(municipal,on='municipality_code',how='left',validate='many_to_one',indicator='agri_merge')
    p['municipality_series_matched']=p.agri_merge.eq('both');p['profile2021_covered']=p.profile2021_covered.astype('boolean').fillna(False).astype(bool);p['latest_crop_observed']=p.latest_crop_year.notna();p['production_observed']=p.latest_production_year.notna();p['context_scale']='municipality_not_point_or_SGRT';p['bridge_reference_year']=2021;p['historical_boundary_equivalence_proven']=False;p['point_agriculture_observed']=False;p['actual_agroservice_flow_observed']=False;p['native_context_repeated_across_points']=True
    p['observed_positive_area_2021']=p.total_ha_2021.gt(0)&p.profile2021_inconsistent.eq(False)
    p['observed_zero_area_2021']=p.total_ha_2021.eq(0)&p.profile2021_inconsistent.eq(False)
    p['area_evidence_status_2021']=np.select([p.observed_positive_area_2021,p.observed_zero_area_2021,p.profile2021_inconsistent.eq(True)],['observed_positive_municipal_total','observed_zero_municipal_total','inconsistent_municipal_profile'],default='unobserved_municipal_total')
    lo=pd.to_numeric(p.latest_crop_code_year_from,errors='coerce');hi=pd.to_numeric(p.latest_crop_code_year_to,errors='coerce')
    p['latest_crop_declared_interval_known']=lo.notna()&hi.notna()
    p['latest_crop_year_in_declared_interval']=pd.Series(pd.NA,index=p.index,dtype='boolean');known=p.latest_crop_declared_interval_known&p.latest_crop_year.notna();p.loc[known,'latest_crop_year_in_declared_interval']=p.loc[known,'latest_crop_year'].between(lo[known],hi[known])
    p.drop(columns=['municipality_oktmo8_2021','agri_merge'],inplace=True)
    p.rename(columns={c:'agri_'+c for c in p if c!='id'},inplace=True)
    for c in ['agri_profile2021_inconsistent','agri_profile2021_complete','agri_latest_crop_inconsistent','agri_dominance_tie_2021','agri_latest_crop_dominance_tie','agri_latest_crop_largest_observed_group_tie','agri_latest_crop_dominant_group_informative']:p[c]=p[c].astype('boolean')
    for c in p.select_dtypes(include='object'):p[c]=p[c].astype('string')
    p.to_parquet(out/'point_municipal_agriculture.parquet',index=False)
    p.to_csv(out/'point_municipal_agriculture.csv.gz',index=False)
    coverage=p.groupby('agri_region',dropna=False).agg(points=('id','size'),matched=('agri_municipality_series_matched','sum'),profile2021_covered=('agri_profile2021_covered','sum'),latest_crop_observed=('agri_latest_crop_observed','sum'),production_observed=('agri_production_observed','sum'),bridge_ambiguous=('agri_bridge_ambiguous','sum')).reset_index();coverage['unmatched']=coverage.points-coverage.matched;coverage['profile2021_coverage']=coverage.profile2021_covered/coverage.points;coverage.to_csv(out/'coverage_by_region.csv',index=False)
    p[~p.agri_municipality_series_matched|p.agri_bridge_ambiguous][['id','agri_region','agri_municipality_code','agri_bridge_status','agri_municipality_series_matched']].to_csv(out/'unmatched_or_ambiguous_points.csv.gz',index=False)
    # Never sum duplicated municipality context as if each point owned that amount.
    matchedcodes=set(p.loc[p.agri_municipality_series_matched,'agri_municipality_code']);balances=[]
    numeric=['total_ha_2021']+[g+'_ha_2021' for g in GROUPS]+['latest_crop_total_ha','latest_production_nominal_thousand_rub','total_ha_2010_native_code','production_nominal_thousand_rub_2010','production_nominal_thousand_rub_2021']
    unique=p[p.agri_municipality_series_matched].drop_duplicates('agri_municipality_code').set_index('agri_municipality_code')
    ms=municipal[municipal.municipality_code.isin(matchedcodes)].set_index('municipality_code')
    for c in numeric:
        before=ms[c].sum(min_count=1);after=unique['agri_'+c].sum(min_count=1)
        balances.append({'measure':c,'municipalities':len(ms),'source_unique_municipality_sum':before,'linked_deduplicated_municipality_sum':after,'difference':after-before,'same':bool(np.isclose(before,after,equal_nan=True)),'point_repeated_context_sum_intentionally_not_used':True})
    bal=pd.DataFrame(balances);bal.to_csv(out/'municipal_mass_balance.csv',index=False)
    # Territorial time audit is regenerated from real source rows, no old zones.
    yrfrom=pd.to_numeric(clean.oktmo_year_from,errors='coerce');yrto=pd.to_numeric(clean.oktmo_year_to,errors='coerce');interval=yrfrom.notna()&yrto.notna();clean['code_interval_available']=interval;clean['within_declared_code_interval']=np.where(interval,clean.year.between(yrfrom,yrto),'unknown')
    clean.groupby(['year','indicator_code','oktmo_history','code_interval_available','within_declared_code_interval'],dropna=False).size().rename('rows').reset_index().to_csv(out/'territorial_time_audit.csv',index=False)
    checks=[]
    def ck(name,v):checks.append({'name':name,'pass':bool(v)})
    ck('all_axis_points_preserved',len(p)==len(panel)==142570);ck('unique_point_UID',p.id.is_unique);ck('UID_set_equal',set(p.id)==set(panel.id));ck('municipal_unique',municipal.municipality_code.is_unique);ck('annual_unique',not x.duplicated(['oktmo','year']).any());ck('frozen2021_recalculation_exact_profile',compare.same.all());ck('no_old_zone_fields',not any('zone' in c or 'center_id' in c or 'nearest' in c for c in p));ck('coverage_balance_regions',coverage.points.sum()==len(p));ck('matched_unmatched_balance',(coverage.matched+coverage.unmatched).sum()==len(p));ck('all_municipal_mass_balances',bal.same.all());ck('full_extracted_series_balance',len(r)==len(clean)+int(dup.sum()));ck('all_output_context_flags',not p.agri_point_agriculture_observed.any() and not p.agri_historical_boundary_equivalence_proven.any());ck('known_units_hectares',set(clean[clean.group.ne('production')].indicator_unit)=={'Гектар'});ck('known_units_thousandrub',set(production.latest_production_source_unit)=={'Тысяча рублей'})
    ck('five_classification_ties_explicit',x.dominance_tie.sum()==5)
    ck('ties_never_given_unique_dominant_group',x.loc[x.largest_observed_group_tie,'dominant_group'].isna().all())
    ck('ties_classified_ambiguous',x.loc[x.dominance_tie,'profile'].eq('ambiguous').all())
    ck('no_classification_ties2021',not x.loc[x.year.eq(2021),'dominance_tie'].any())
    ck('latest_valid_excludes_ambiguous',not valid.latest_valid_profile.isin(['missing','ambiguous']).any())
    ck('no_dominant_group_for_zero_unknown_or_inconsistent',x.loc[x.total.isna()|x.total.le(0)|x.inconsistent|largest.isna()|largest.le(0),'dominant_group'].isna().all())
    ck('dominant_group_only_when_informative',x.dominant_group.notna().eq(x.dominant_group_informative).all())
    ck('point_latest_group_informative_agrees',p.agri_latest_crop_dominant_group.notna().eq(p.agri_latest_crop_dominant_group_informative.fillna(False)).all())
    pd.testing.assert_frame_equal(p,pd.read_parquet(out/'point_municipal_agriculture.parquet'));ck('parquet_full_readback',True)
    paths=[panelpath,old/'municipal_series_2006_2024.parquet',old/'municipal_crop_profiles_2021.csv',old/'source_manifest.json',old/'territorial_time_audit.csv']
    audit={'status':'NATIONAL_POINT_NATIVE_MUNICIPAL_AGRICULTURAL_CONTEXT_COMPUTED','points':len(p),'columns':len(p.columns),'source_series_rows':len(r),'duplicate_rows_quarantined':int(dup.sum()),'municipal_snapshots':len(municipal),'annual_crop_profiles':len(x),'matched_points':int(p.agri_municipality_series_matched.sum()),'unmatched_points':int((~p.agri_municipality_series_matched).sum()),'covered2021_points':int(p.agri_profile2021_covered.sum()),'ambiguous_source_claims':int(p.agri_bridge_ambiguous.sum()),'latest_crop_observed_points':int(p.agri_latest_crop_observed.sum()),'production_observed_points':int(p.agri_production_observed.sum()),'checks_passed':sum(c['pass'] for c in checks),'checks_total':len(checks),'all_pass':all(c['pass'] for c in checks),'inputs':[{'path':str(f.relative_to(a.base)),'bytes':f.stat().st_size,'sha256':sha(f)} for f in paths],'code_sha256':sha(Path(__file__)),'primary_evidence':'official_municipal_statistics_joined_by_native_2021_context_not_settlement_farm_measurement','old_geometric_membership_used':False}
    audit.update({'annual_classification_dominance_ties':int(x.dominance_tie.sum()),'annual_largest_observed_group_ties_including_invalid_and_mixed':int(x.largest_observed_group_tie.sum()),'latest_crop_tie_points':int(p.agri_latest_crop_dominance_tie.fillna(False).sum()),'latest_valid_profile_excludes':'missing|ambiguous','tie_rule':'exact_equal_positive_observed_maxima;classification_ambiguous_only_if_prior_valid_dominance_at_least0.5;no_input_area_changed'})
    (out/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(out/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n');(out/'SCHEMA.json').write_text(json.dumps({c:str(t) for c,t in p.dtypes.items()},ensure_ascii=False,indent=2)+'\n');assert audit['all_pass'];print(json.dumps({k:v for k,v in audit.items() if k not in ['inputs']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

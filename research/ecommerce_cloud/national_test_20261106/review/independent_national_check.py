"""Independent raw-data arithmetic. No imports from any production analyzer."""
from pathlib import Path
import argparse,base64,hashlib,json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PHASE=HERE.parent
checks=0

def eq(a,b,label):
    global checks
    checks+=1
    assert np.isclose(a,b,rtol=1e-9,atol=1e-7,equal_nan=True),(label,a,b)

def group_mask(d,definition,group,k):
    v=d[f'I04_04_0{k}']
    if definition=='all':return pd.Series(True,index=d.index)
    if definition=='any_goods_binary':
        a=d[[f'I04_04_0{i}' for i in (1,2,3)]]
        yes=a.isin([1,2]).any(axis=1);no=a.isin([3,4]).all(axis=1)
        return yes if group=='positive' else no if group=='negative' else ~(yes|no)
    if definition=='same_goods_binary':return v.isin([1,2]) if group=='positive' else v.isin([3,4]) if group=='negative' else ~v.isin([1,2,3,4])
    assert definition=='same_goods_frequency'
    return v.eq({'regular':1,'occasional':2,'no_aware':3,'no_unaware':4,'unknown':-7}[group])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-ict-raw',action='store_true',help='Check only published ICT arithmetic/benchmarks; do not read SAV. All other raw-data checks remain enabled.')
    args=parser.parse_args()
    out={};frames={}
    for year in (2018,2022,2024):
        cols=['R_1','R_1_1','H01_01','H01_02','H01_12','KVZV']+[f'I04_0{i}_0{j}' for i in (3,4) for j in (1,2,3)]
        raw=pd.read_csv(ROOT/f'work/ecommerce_flows_20261026/{year}_individual.csv',sep=';',usecols=cols)
        rural=raw.loc[raw.R_1.eq(2)&raw.H01_02.ge(15)].copy();d=rural.loc[rural.H01_12.ne(99)].copy()
        assert d.KVZV.gt(0).all()
        d['age4']=np.select([d.H01_02.le(29),d.H01_02.le(44),d.H01_02.le(59)],[0,1,2],default=3)
        frames[year]=d
        row=pd.read_csv(PHASE/'purchase_microdata/denominators.csv').set_index('year').loc[year]
        for col,value in dict(rural15_roster_n=len(rural),rural15_roster_weight=rural.KVZV.sum(),information_available_n=len(d),information_available_weight=d.KVZV.sum(),information_unavailable_n=len(rural)-len(d),information_unavailable_weight=rural.loc[rural.H01_12.eq(99),'KVZV'].sum()).items():eq(row[col],value,f'{year}:{col}')
    cats={1:'own_locality_or_residential_district',2:'nearby_localities_or_districts',3:'other_russian_region',4:'abroad',-7:'unknown_place'}
    goods={'clothing_footwear':2,'appliances_electronics_communications':3}
    tab=pd.read_csv(PHASE/'purchase_microdata/purchase_geography_by_channel.csv')
    for age_scope,table in [('15plus',tab),('15_74',pd.read_csv(PHASE/'purchase_microdata/purchase_geography_age15_74.csv'))]:
        for r in table.to_dict('records'):
            d=frames[r['year']]
            if age_scope=='15_74':d=d.loc[d.H01_02.le(74)]
            k=goods[r['goods']];g=d.loc[group_mask(d,r['group_definition'],r['group'],k)];w=g.KVZV;total=w.sum();loc=g[f'I04_03_0{k}'];external=loc.isin([2,3,4])
            exp=dict(n=len(g),weight=total,group_share_rural_pct=100*total/d.KVZV.sum(),external_n=external.sum(),external_pct=100*w[external].sum()/total,joint_external_share_all_rural_pct=100*w[external].sum()/d.KVZV.sum())
            for code,label in cats.items():
                hit=loc.eq(code);exp.update({label+'_n':hit.sum(),label+'_weight':w[hit].sum(),label+'_pct':100*w[hit].sum()/total})
            for col,val in exp.items():eq(r[col],val,f"{r['year']}:{r['goods']}:{r['group_definition']}:{r['group']}:{col}")
    std=pd.read_csv(PHASE/'purchase_microdata/same_wave_standardised.csv')
    for r in std.to_dict('records'):
        d=frames[r['year']];k=goods[r['goods']];target=d.groupby(['R_1_1','age4','H01_01']).KVZV.sum();target=target/target.sum();g=d.loc[group_mask(d,r['group_definition'],r['group'],k)]
        present=g.groupby(['R_1_1','age4','H01_01']).size();missing=target.index.difference(present.index)
        eq(r['strata_present'],len(present),'support');eq(r['min_cell_n'],present.min(),'min_n');eq(r['uncovered_target_weight_pct'],100*target.reindex(missing).sum(),'uncovered')
        if len(missing):
            assert all(pd.isna(r[c]) for c in ('own_locality_pct','external_pct','unknown_place_pct'))
        else:
            z=g.copy();z['adjusted']=z.KVZV*z.set_index(['R_1_1','age4','H01_01']).index.map(target).to_numpy()/z.set_index(['R_1_1','age4','H01_01']).index.map(g.groupby(['R_1_1','age4','H01_01']).KVZV.sum()).to_numpy()
            loc=z[f'I04_03_0{k}']
            for label,mask in [('own_locality_pct',loc.eq(1)),('external_pct',loc.isin([2,3,4])),('unknown_place_pct',loc.eq(-7))]:eq(r[label],100*z.loc[mask,'adjusted'].sum(),label)
    out['kouzh']=dict(geography_rows=len(tab),age15_74_geography_rows=len(table),standardised_rows=len(std),numeric_checks=checks,discrepancies=0,full_support_standardised_rows=int(std.strata_present.eq(32).sum()),partial_support_rows_withheld=int(std.strata_present.lt(32).sum()))
    ict=pd.read_csv(PHASE/'ict_survey/ict_estimates.csv')
    for r in ict.to_dict('records'):
        eq(r['pct'],100*r['weighted_numerator_persons']/r['weighted_denominator_persons'],'published ICT arithmetic')
        assert 0<=r['unweighted_numerator_n']<=r['unweighted_denominator_n']
        assert 0<=r['weighted_numerator_persons']<=r['weighted_denominator_persons']+1e-6
    benchmark=pd.read_csv(PHASE/'ict_survey/official_reproduction.csv')
    for r in benchmark.to_dict('records'):
        q=ict.loc[ict.year.eq(r['year'])&ict.geography.eq(r['geography'])&ict.age_universe.eq(r['age_universe'])&ict.metric.eq('online_any_goods_or_services_last12m')].iloc[0]
        eq(q.pct,r['calculated_pct'],'published benchmark bridge')
        eq(round(q.pct,1),r['official_pct'],'official rounded benchmark')
    out['ict_verification']=dict(mode='published_aggregates_only_raw_skipped' if args.skip_ict_raw else 'full_local_SAV',published_rows_checked=len(ict),official_benchmarks_checked=len(benchmark),raw_read=not args.skip_ict_raw)
    if not args.skip_ict_raw:
        import pyreadstat
        phys_cols=[f'IntP2_{i}' for i in (1,2,5,17,8,9,12,16)]
        sav=ROOT/'work/ecommerce_national_test_20261106/ict_survey/IKT-2024.sav'
        assert base64.b32encode(hashlib.sha1(sav.read_bytes()).digest()).decode().rstrip('=')=='F4GMAGVWKYCUV3MY67RLQRNIYKMVUDHY'
        raw,meta=pyreadstat.read_sav(sav,usecols=['POSEL','NAS_VOZR','VESA_SVOD','IntP1','IntP5_2']+phys_cols)
        rural=raw.loc[raw.POSEL.eq(2)&raw.NAS_VOZR.ge(15)]
        for scope,x in [('15–74',rural.loc[rural.NAS_VOZR.le(74)]),('15+',rural)]:
            w=x.VESA_SVOD;assert w.gt(0).all()
            buyers=x.IntP1.isin([1,2]);physical=x[phys_cols].gt(0).any(axis=1);pickup=x.IntP5_2.gt(0)
            assert not (physical&~buyers).any() and not (pickup&~buyers).any()
            for c in phys_cols:assert set(x[c].unique())<={0.,float(c.split('_')[1])}
            assert set(x.IntP5_2.unique())<={0.,2.}
            masks={'online_any_goods_or_services_last12m':buyers,'physical8_any_last12m':physical,'physical8_and_pickup_same_person':physical&pickup}
            for metric,mask in masks.items():
                q=ict.loc[ict.geography.eq('rural')&ict.age_universe.eq(scope)&ict.metric.eq(metric)&ict.denominator.eq('all_persons_in_age_and_geography')].iloc[0]
                for col,value in dict(unweighted_denominator_n=len(x),unweighted_numerator_n=mask.sum(),weighted_denominator_persons=w.sum(),weighted_numerator_persons=w[mask].sum(),pct=100*w[mask].sum()/w.sum()).items():eq(q[col],value,'raw ICT '+scope+':'+metric+':'+col)
            out['ikt2024_rural_'+scope]=dict(n=len(x),weight=float(w.sum()),buyers12months_pct=float(100*w[buyers].sum()/w.sum()),any_eight_physical_categories_pct=float(100*w[physical].sum()/w.sum()),physical_and_reported_pickup_pct=float(100*w[physical&pickup].sum()/w.sum()),same_order_or_local_receipt_identified=False)
    sdir=ROOT/'work/ecommerce_national_20261106/sber';p=sdir/'consumption.parquet'
    assert hashlib.sha256(p.read_bytes()).hexdigest()=='9833ddaaee7b2a182ed4cceeed16469031700ea87d508bd976150c6770ef8a61'
    s=pd.read_parquet(p);assert not s.duplicated(['territory_id','date','category']).any()
    wide=s.pivot(index=['territory_id','date'],columns='category',values='value')
    assert not wide.isna().any().any()
    counts=wide.groupby(level=0).size()
    out['sber']=dict(rows=len(s),municipality_ids=s.territory_id.nunique(),municipality_months=len(wide),categories=len(wide.columns),all24months_municipalities=int(counts.eq(24).sum()),incomplete_municipalities=int(counts.lt(24).sum()),zero_all_category_cells=int(wide['Все категории'].eq(0).sum()),negative_values_n=int(s.value.lt(0).sum()),marketplace_exceeds_all_n=int(wide['Маркетплейсы'].gt(wide['Все категории']).sum()),sum_five_exceeds_all_n=int(wide.drop(columns='Все категории').sum(axis=1).gt(wide['Все категории']).sum()))
    dictionary=pd.read_excel(sdir/'dictionary.xlsx');active=dictionary.loc[dictionary.year_from.le(2024)&dictionary.year_to.gt(2024)].set_index('territory_id')
    assert active.index.is_unique
    balanced_ids=counts.loc[counts.eq(24)].index
    b=wide.loc[balanced_ids].reset_index();b['year']=b.date.str[:4].astype(int)
    annual=b.groupby(['territory_id','year'])[['Маркетплейсы','Все категории']].sum()
    published=pd.read_csv(PHASE/'sber_consumption/balanced_municipal_annual.csv')
    assert len(published)==len(balanced_ids) and published.territory_id.is_unique
    independent=[]
    for r in published.to_dict('records'):
        ident=r['territory_id'];y23=annual.loc[(ident,2023)];y24=annual.loc[(ident,2024)]
        ratios=[];rest=[]
        for year,v in [(2023,y23),(2024,y24)]:
            total=float(v['Все категории']);mp=float(v['Маркетплейсы']);ratio=mp/total;residual=total-mp;ratios.append(ratio);rest.append(residual)
            for col,val in {f'all_model_monthly_means_sum_{year}_rub':total,f'marketplace_model_monthly_means_sum_{year}_rub':mp,f'marketplace_ratio_{year}':ratio,f'non_marketplace_nominal_model_means_sum_{year}_rub':residual}.items():eq(r[col],val,col)
        eq(r['marketplace_ratio_change_pp'],100*(ratios[1]-ratios[0]),'ratio_pp')
        eq(r['non_marketplace_nominal_change_pct'],100*(rest[1]/rest[0]-1),'residual_pct')
        eq(r['all_nominal_change_pct'],100*(y24['Все категории']/y23['Все категории']-1),'all_pct')
        eq(r['marketplace_nominal_change_pct'],100*(y24['Маркетплейсы']/y23['Маркетплейсы']-1),'mp_pct')
        q=active.loc[ident]
        for col in ['region_code','region_name','municipal_district_name_short','municipal_district_type','oktmo']:assert r[col]==q[col]
        independent.append((ratios[0]*100,ratios[1]*100,(ratios[1]-ratios[0])*100,100*(rest[1]/rest[0]-1)))
    vals=np.asarray(independent)
    summary=pd.read_csv(PHASE/'sber_consumption/municipality_distribution_summary.csv');globalrow=summary.loc[summary.group.eq('all_balanced')].iloc[0]
    for j,prefix in enumerate(['share_2023_pct','share_2024_pct','share_change_pp']):
        for quant in [10,25,50,75,90]:eq(globalrow[prefix+f'_q{quant}'],np.quantile(vals[:,j],quant/100),prefix)
    eq(globalrow.share_increased_n,int((vals[:,2]>0).sum()),'increased')
    eq(globalrow.nonmarketplace_nominal_increased_n,int((vals[:,3]>0).sum()),'residual_increased')
    eq(globalrow.nonmarketplace_nominal_growth_median_pct,np.median(vals[:,3]),'residual_median')
    out['sber']['annual_rows_checked']=len(published)
    out['sber']['model_ratio_increased_n']=int((vals[:,2]>0).sum())
    out['sber']['median_ratio2023_pct']=float(np.median(vals[:,0]))
    out['sber']['median_ratio2024_pct']=float(np.median(vals[:,1]))
    out['sber']['median_within_municipality_change_pp']=float(np.median(vals[:,2]))
    out['all_numeric_checks']=checks
    ep=PHASE/'employment_panel'
    salaryfile=ROOT/'work/ecommerce_national_20261106/employment_panel/raw/sber_bdmo_salary.parquet'
    assert hashlib.sha256(salaryfile.read_bytes()).hexdigest()=='f9a8956ad68c7ec81fac7b2e61ac2494b02b489887ce06204621b5dff29e62f2'
    salaries=pd.read_parquet(salaryfile)
    skeys=['territory_id','year','period','okved_letter']
    wage_table=pd.read_csv(ep/'sector_wages_ytd_2023_2024.csv',dtype={'okved_letter':str})
    for r in wage_table.to_dict('records'):
        mask=np.ones(len(salaries),dtype=bool)
        for col in skeys:mask &= salaries[col].eq(r[col]).to_numpy()
        hit=salaries.loc[mask]
        assert len(hit)>0 and hit.value.nunique()==1
        eq(r['value'],hit.value.iloc[0],'sector wage raw')
    changes=pd.read_csv(ep/'sector_wage_same_period_changes.csv',dtype={'okved_letter':str})
    for r in changes.to_dict('records'):
        hit=wage_table.loc[wage_table.territory_id.eq(r['territory_id']) & wage_table.period.eq(r['period']) & wage_table.okved_letter.eq(r['okved_letter'])].set_index('year')
        eq(r['value_2023'],hit.loc[2023,'value'],'wage2023');eq(r['value_2024'],hit.loc[2024,'value'],'wage2024')
        eq(r['change_pct'],100*(hit.loc[2024,'value']/hit.loc[2023,'value']-1),'wage growth')
    panel=pd.read_csv(ep/'employment_wage_panel.csv').set_index(['city','indicator','year'])
    table=pd.read_csv(ep/'changes.csv')
    for r in table.to_dict('records'):
        before=panel.loc[(r['city'],r['indicator'],r['start']),'value'];after=panel.loc[(r['city'],r['indicator'],r['end']),'value']
        eq(r['start_value'],before,'book before');eq(r['end_value'],after,'book after');eq(r['change'],after-before,'book difference');eq(r['change_pct'],100*(after/before-1),'book pct')
    out['employment']=dict(book_panel_rows=len(panel),sector_wage_rows_checked_against_raw=len(wage_table),same_period_changes_checked=len(changes),book_changes_arithmetic_checked=len(table),full_original_books_read=False)
    out['all_numeric_checks']=checks
    print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()

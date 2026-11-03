"""Joint reported purchasing locations and within-household school links.

Only public anonymised KOUZh records and aggregate output. Purchasing location
is neither a trip nor the receipt location of an Internet order. Household
links are used only within the 2024 file with documented hhId, never across waves.
"""
from pathlib import Path
import importlib.util
import json
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=HERE.parent/'flows_20261026'
spec=importlib.util.spec_from_file_location('purchase_source',OLD/'analyze_purchase_geography.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
PATTERNS=['LLL','LLE','LEL','LEE','ELL','ELE','EEL','EEE','unknown']


def classify(d):
    loc=d[[f'I04_03_0{i}' for i in (1,2,3)]]
    valid=loc.isin([1,2,3,4]).all(axis=1)
    pattern=pd.Series('',index=d.index)
    for col in loc:pattern+=np.where(loc[col].eq(1),'L','E')
    d['pattern']=pattern.where(valid,'unknown')
    rem=d[[f'I04_04_0{i}' for i in (1,2,3)]]
    d['remote_group']=np.select([rem.isin([1,2]).any(axis=1),rem.isin([3,4]).all(axis=1)],
        ['any_internet_or_postal' if int(d['year'].iloc[0])<2024 else 'any_internet','none'],default='unknown')
    return d


def summarise(g,year,scope,group):
    w=g.KVZV;total=float(w.sum())
    r=dict(year=year,scope=scope,group=str(group),n=len(g),weight=total)
    for p in PATTERNS:
        mask=g.pattern.eq(p)
        r[p+'_n']=int(mask.sum());r[p+'_weight']=float(w[mask].sum())
        r[p+'_pct']=100*r[p+'_weight']/total
    assert np.isclose(sum(r[p+'_pct'] for p in PATTERNS),100)
    r['mixed_pct']=sum(r[p+'_pct'] for p in PATTERNS if p not in ['LLL','EEE','unknown'])
    r['any_external_pct']=100-r['LLL_pct']-r['unknown_pct']
    return r


def main():
    frames={};rows=[];cells=[];receipts=[]
    for year in (2024,2022,2018):
        d,receipt=source.load(year);receipts.append(receipt)
        d=d.loc[d.locality.eq('rural')].copy();d['year']=year;classify(d);frames[year]=d
        groups=[('rural_all','all',d)]+[('rural_size',str(k),g)for k,g in d.groupby('R_1_1')]
        groups += [('remote_group',k,g)for k,g in d.groupby('remote_group')]
        if year==2024:
            for match in ('тверск','краснодар','саха (якутия)'):
                g=d.loc[d.region.str.casefold().str.contains(match,regex=False)]
                assert g.region.nunique()==1
                groups.append(('pilot_region',g.region.iloc[0],g))
        for scope,k,g in groups:rows.append(summarise(g,year,scope,k))
        for k,g in d.groupby(['R_1_1','age_band','H01_01'],observed=True):
            cells.append(summarise(g,year,'stratum','|'.join(map(str,k))))
    pd.DataFrame(rows).to_csv(HERE/'joint_purchase_profiles.csv',index=False)
    strata=pd.DataFrame(cells);std=[]
    target=strata.loc[strata.year.eq(2022)].set_index('group')
    weights=target.weight/target.weight.sum()
    for year in (2018,2022,2024):
        g=strata.loc[strata.year.eq(year)].set_index('group').reindex(target.index)
        assert len(g)==32 and g.n.notna().all()
        r=dict(year=year,target_year=2022,strata_n=len(g),min_stratum_n=int(g.n.min()))
        for p in PATTERNS:r[p+'_pct']=float((g[p+'_pct']*weights).sum())
        r['mixed_pct']=sum(r[p+'_pct']for p in PATTERNS if p not in ['LLL','EEE','unknown'])
        r['any_external_pct']=100-r['LLL_pct']-r['unknown_pct'];std.append(r)
    pd.DataFrame(std).to_csv(HERE/'joint_purchase_standardised.csv',index=False)
    # Same-file household grouping: supplied weight occurs once per household.
    columns=['hhId','respNum','H00_02','H00_04','R_1_1','KVZV','H01_02','H01_12','D03_23','D03_31']
    columns += [f'I04_0{i}_0{j}'for i in (3,4)for j in (1,2,3)]
    allrows=pd.read_csv(source.RAW/'2024_individual.csv',sep=';',usecols=columns)
    assert not allrows.duplicated(['hhId','respNum']).any()
    hhgroup=allrows.groupby('hhId')
    for field in ['H00_02','H00_04','R_1_1','KVZV']:assert hhgroup[field].nunique().eq(1).all()
    rural=allrows.loc[allrows.H00_04.eq(2)].copy();hh=[]
    for key,g in rural.groupby('hhId'):
        children=g.loc[g.H01_02.between(7,14)&g.D03_23.eq(1)]
        if children.empty:continue
        adults=g.loc[g.H01_02.ge(15)].copy()
        informed=adults.loc[adults.H01_12.ne(99)].copy()
        if not informed.empty:
            informed['year']=2024;classify(informed)
        remote='unknown'
        if not informed.empty and informed.remote_group.eq('any_internet').any():remote='any_internet'
        elif len(informed)==len(adults) and len(adults)>0 and informed.remote_group.eq('none').all():remote='none'
        school='external' if children.D03_31.eq(2).any() else ('local' if children.D03_31.eq(1).all() else 'unknown')
        # Strict: all adult roster members have information and all three
        # reported main locations local; no-information adults prevent it.
        local_all=(len(adults)>0 and len(informed)==len(adults) and informed.pattern.eq('LLL').all())
        hh.append(dict(weight=float(g.KVZV.iloc[0]),size=int(g.R_1_1.iloc[0]),
            school=school,remote=remote,all_adults_all_local=bool(local_all),
            adult_information_complete=len(informed)==len(adults),
            n_adults=len(adults),n_informed=len(informed),n_schoolchildren=len(children)))
    h=pd.DataFrame(hh);out=[]
    groups=[('school_households','all',h)]+[('remote_group',k,g)for k,g in h.groupby('remote')]
    groups += [('rural_size',str(k),g)for k,g in h.groupby('size')]
    groups += [('all_adults_all_local','yes',h.loc[h.all_adults_all_local])]
    for scope,k,g in groups:
        if g.empty:continue
        w=g.weight;total=float(w.sum())
        r=dict(year=2024,scope=scope,group=k,n_households=len(g),weight=total)
        masks={f'school_{s}':g.school.eq(s)for s in ['local','external','unknown']}
        masks.update(any_internet=g.remote.eq('any_internet'),remote_unknown=g.remote.eq('unknown'),
            internet_and_external_school=g.remote.eq('any_internet')&g.school.eq('external'),
            all_adults_all_local=g.all_adults_all_local,
            all_local_and_external_school=g.all_adults_all_local&g.school.eq('external'),
            incomplete_adult_information=~g.adult_information_complete)
        for label,mask in masks.items():
            r[label+'_n']=int(mask.sum());r[label+'_weight']=float(w[mask].sum());r[label+'_pct']=100*float(w[mask].sum())/total
        out.append(r)
    pd.DataFrame(out).to_csv(HERE/'joint_household_school2024.csv',index=False)
    metadata=dict(unit_purchase='Rural persons aged15+ with individual information; proxy answers included.',
        pattern='L=own settlement; E=any external category2,3,4; order food+hygiene, clothing, technology. E categories need not be the same destination.',
        unknown='Any one of three location answers unknown => whole profile unknown.',
        remote='At least one of three goods groups ordered remotely; no means all three explicitly nonuser. Unknown is not no.',
        household_unit='2024 rural households with at least one attending schoolchild age7–14. One KVZV per hhId. Household id not used across waves.',
        household_integrity=dict(all_households_n=len(hhgroup),duplicate_person_keys_n=0,within_household_weight_or_region_or_size_conflicts_n=0),
        source_waves=receipts,not_identified=['Named destination','Travel frequency','Internet-order receipt location','WB/Ozon effect','Design-based standard errors'])
    (HERE/'joint_analysis_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(pd.DataFrame(rows).query("scope=='rural_all'")[[ 'year','n','LLL_pct','LEE_pct','EEE_pct','mixed_pct','unknown_pct']].round(3).to_string(index=False))
    print(pd.DataFrame(std)[['year','LLL_pct','LEE_pct','EEE_pct','mixed_pct']].round(3).to_string(index=False))
    print(pd.DataFrame(out)[['scope','group','n_households','school_external_pct','internet_and_external_school_pct','all_local_and_external_school_pct']].round(3).to_string(index=False))


if __name__=='__main__':main()

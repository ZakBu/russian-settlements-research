"""Independent aggregate checks; no imports from analysis scripts or respondent output."""
from pathlib import Path
import itertools
import json
import numpy as np
import pandas as pd
import openpyxl

HERE=Path(__file__).resolve().parent
RAW=HERE.parents[2]/'work/ecommerce_flows_20261026'
PATTERNS=[''.join(x) for x in itertools.product('LE',repeat=3)]+['unknown']
checks=0

def check(actual,expected,label):
    global checks
    checks+=1
    assert np.isclose(float(actual),float(expected),rtol=1e-9,atol=1e-7),(label,actual,expected)

def classify(d):
    a=d[[f'I04_03_0{i}' for i in range(1,4)]].to_numpy()
    p=[''.join('L' if v==1 else 'E' for v in row) if all(v in (1,2,3,4) for v in row) else 'unknown' for row in a]
    r=d[[f'I04_04_0{i}' for i in range(1,4)]].to_numpy()
    remote=['any' if any(v in (1,2) for v in row) else 'none' if all(v in (3,4) for v in row) else 'unknown' for row in r]
    return np.array(p),np.array(remote)

def stats(d):
    w=d.KVZV
    out={'n':len(d),'weight':w.sum()}
    for p in PATTERNS:
        hit=d.pattern.eq(p)
        out.update({p+'_n':hit.sum(),p+'_weight':w[hit].sum(),p+'_pct':100*w[hit].sum()/w.sum()})
    out['mixed_pct']=sum(out[p+'_pct'] for p in PATTERNS if p not in ('LLL','EEE','unknown'))
    out['any_external_pct']=sum(out[p+'_pct'] for p in PATTERNS if 'E' in p)
    return out

def compare(row,expected,prefix):
    for k,v in expected.items(): check(row[k],v,prefix+':'+k)

def main():
    profiles=pd.read_csv(HERE/'joint_purchase_profiles.csv',dtype={'group':str})
    standard=pd.read_csv(HERE/'joint_purchase_standardised.csv')
    household=pd.read_csv(HERE/'joint_household_school2024.csv',dtype={'group':str})
    frames={}; full2024=None
    for year in (2018,2022,2024):
        cols=['hhId','respNum','H00_02','H00_04','R_1','R_1_1','H01_01','H01_02','H01_12','KVZV','D03_23','D03_31'] if year==2024 else ['H00_02','H00_04','R_1','R_1_1','H01_01','H01_02','H01_12','KVZV']
        cols += [f'I04_0{i}_0{j}' for i in (3,4) for j in (1,2,3)]
        raw=pd.read_csv(RAW/f'{year}_individual.csv',sep=';',usecols=cols)
        assert raw.R_1.eq(raw.H00_04).all()
        assert raw.KVZV.gt(0).all()
        if year==2024: full2024=raw
        d=raw.loc[raw.H01_02.ge(15)&raw.H01_12.ne(99)&raw.R_1.eq(2)].copy()
        d['pattern'],d['remote']=classify(d)
        d['age']=np.select([d.H01_02.le(29),d.H01_02.le(44),d.H01_02.le(59)],[0,1,2],default=3)
        frames[year]=d
        labels={}
        if year==2024:
            book=openpyxl.load_workbook(RAW/'2024_codebook.xlsx',read_only=True,data_only=True)
            for sheet in book:
                for row in sheet.iter_rows(values_only=True):
                    if len(row)>=3 and row[0]=='H00_02':
                        try: labels[int(row[1])]=str(row[2])
                        except (TypeError,ValueError): pass
            book.close()
        for _,row in profiles.loc[profiles.year.eq(year)].iterrows():
            if row.scope=='rural_all': g=d
            elif row.scope=='rural_size': g=d.loc[d.R_1_1.eq(float(row.group))]
            elif row.scope=='remote_group': g=d.loc[d.remote.eq('any' if row.group.startswith('any_') else row.group)]
            elif row.scope=='pilot_region': g=d.loc[d.H00_02.map(labels).eq(row.group)]
            else: raise AssertionError(row.scope)
            compare(row,stats(g),f'{year}/{row.scope}/{row.group}')
    dims=['R_1_1','age','H01_01']
    target=frames[2022].groupby(dims).KVZV.sum()
    target=target/target.sum()
    assert len(target)==32
    for _,row in standard.iterrows():
        d=frames[int(row.year)]
        expected={p+'_pct':0.0 for p in PATTERNS}
        ns=[]
        for key,share in target.items():
            mask=np.ones(len(d),dtype=bool)
            for col,value in zip(dims,key): mask &= d[col].eq(value).to_numpy()
            cell=d.loc[mask];ns.append(len(cell));s=stats(cell)
            for p in PATTERNS: expected[p+'_pct']+=share*s[p+'_pct']
        expected.update(strata_n=len(target),min_stratum_n=min(ns))
        expected['mixed_pct']=sum(expected[p+'_pct'] for p in PATTERNS if p not in ('LLL','EEE','unknown'))
        expected['any_external_pct']=sum(expected[p+'_pct'] for p in PATTERNS if 'E' in p)
        compare(row,expected,str(row.year)+'/standardised')
    assert not full2024.duplicated(['hhId','respNum']).any()
    for col in ['KVZV','R_1_1','H00_02','H00_04']: assert full2024.groupby('hhId')[col].nunique().eq(1).all()
    records=[]
    for _,g in full2024.loc[full2024.H00_04.eq(2)].groupby('hhId'):
        children=g.loc[g.H01_02.between(7,14)&g.D03_23.eq(1)]
        if len(children)==0: continue
        adults=g.loc[g.H01_02.ge(15)]
        informed=adults.loc[adults.H01_12.ne(99)]
        patterns,remotes=classify(informed)
        complete=len(adults)==len(informed)
        remote='any_internet' if 'any' in remotes else ('none' if complete and len(adults)>0 and all(remotes=='none') else 'unknown')
        school='external' if 2 in children.D03_31.values else ('local' if children.D03_31.eq(1).all() else 'unknown')
        local=bool(complete and len(adults)>0 and all(patterns=='LLL'))
        records.append(dict(weight=g.KVZV.iloc[0],size=g.R_1_1.iloc[0],remote=remote,school=school,local=local,complete=complete))
    h=pd.DataFrame(records)
    for _,row in household.iterrows():
        if row.scope=='school_households': g=h
        elif row.scope=='rural_size': g=h.loc[h['size'].eq(float(row.group))]
        elif row.scope=='remote_group': g=h.loc[h.remote.eq(row.group)]
        elif row.scope=='all_adults_all_local': g=h.loc[h.local]
        else: raise AssertionError(row.scope)
        expected={'n_households':len(g),'weight':g.weight.sum()}
        masks={f'school_{v}':g.school.eq(v) for v in ('local','external','unknown')}
        masks.update(any_internet=g.remote.eq('any_internet'),remote_unknown=g.remote.eq('unknown'),internet_and_external_school=g.remote.eq('any_internet')&g.school.eq('external'),all_adults_all_local=g.local,all_local_and_external_school=g.local&g.school.eq('external'),incomplete_adult_information=~g.complete)
        for k,mask in masks.items():
            expected[k+'_n']=mask.sum();expected[k+'_weight']=g.loc[mask,'weight'].sum();expected[k+'_pct']=100*g.loc[mask,'weight'].sum()/g.weight.sum()
        compare(row,expected,str(row.scope)+'/'+str(row.group))
    d=frames[2024]
    observed_external=d[[f'I04_03_0{i}' for i in (1,2,3)]].isin([2,3,4]).any(axis=1)
    partial_external=d.pattern.eq('unknown') & observed_external
    diagnostic=dict(any_observed_external_pct=float(100*d.loc[observed_external,'KVZV'].sum()/d.KVZV.sum()),partial_unknown_with_external_n=int(partial_external.sum()),partial_unknown_with_external_pct=float(100*d.loc[partial_external,'KVZV'].sum()/d.KVZV.sum()))
    print(json.dumps(dict(checks=checks,discrepancies=0,diagnostic2024=diagnostic,profile_rows=len(profiles),standardised_rows=len(standard),household_rows=len(household),school_households_n=len(h),households_with_no_adults_n=int(sum((full2024.groupby('hhId').H01_02.max()<15))),note='All outputs aggregate only; no respondent records emitted.'),ensure_ascii=False))

if __name__=='__main__': main()

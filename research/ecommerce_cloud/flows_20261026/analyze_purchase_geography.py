"""Weighted self-reported purchase geography, not trips or WB/Ozon effects.

Public anonymised KOUZH records are used only for aggregates. No settlement is
identified from anonymised IDs. Year-specific questions and periods differ;
the geography question is kept separate from remote-ordering responses.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RAW = ROOT/'work/ecommerce_flows_20261026'
GOODS = {1:'food_and_personal_hygiene',2:'clothing_and_footwear',3:'appliances_electronics_communications'}
PLACE = {1:'own_locality_or_urban_district',2:'nearby_localities_or_districts',
         3:'other_russian_region',4:'abroad',-7:'dont_know'}
REMOTE = {1:'regular',2:'occasional',3:'no_aware',4:'no_unaware',-7:'dont_know'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def labels(year, field):
    import openpyxl
    result={}
    book=openpyxl.load_workbook(RAW/f'{year}_codebook.xlsx',read_only=True,data_only=True)
    for sheet in book:
        for values in sheet.iter_rows(values_only=True):
            if len(values)>=3 and values[0]==field:
                try:code=int(values[1])
                except (ValueError,TypeError):continue
                result[code]=str(values[2])
    book.close()
    return result


def load(year):
    manifest=json.loads((HERE/'kouzh_source_members.json').read_text())['members']
    p=RAW/f'{year}_individual.csv'
    pin=next(r for r in manifest if r['filename']==p.name)
    assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256']
    codebook=RAW/f'{year}_codebook.xlsx'
    cp=next(r for r in manifest if r['filename']==codebook.name)
    assert codebook.stat().st_size==cp['bytes'] and sha(codebook)==cp['sha256']
    columns=['H01_01','H01_02','H01_12','R_1','R_1_1','H00_02','KVZV']+[
        f'I04_0{i}_0{j}' for i in (3,4) for j in (1,2,3)]
    d=pd.read_csv(p,sep=';',usecols=columns)
    assert d.KVZV.notna().all() and d.KVZV.gt(0).all()
    assert d.R_1.isin([1,2]).all()
    adults=d.loc[d.H01_02.ge(15)].copy()
    # 2024 retains adults for whom no individual information was obtained.
    # Other members can answer by proxy. No-information is never a zero answer.
    interviewed=adults.loc[adults.H01_12.ne(99)].copy()
    for code in range(1,4):
        assert interviewed[f'I04_03_0{code}'].isin(PLACE).all()
        assert interviewed[f'I04_04_0{code}'].isin(REMOTE).all()
    reglabels=labels(year,'H00_02')
    if year==2024:
        assert set(interviewed.H00_02.astype(int))<=set(reglabels)
    # Earlier public codebooks do not provide the regional value labels. Do
    # not transfer a numeric-to-name dictionary backwards without evidence.
    interviewed['region']=interviewed.H00_02.astype(int).map(
        lambda code:reglabels.get(code,f'undecoded_code_{code}_year_{year}'))
    interviewed['locality']=interviewed.R_1.map({1:'urban',2:'rural'})
    interviewed['size_label']=interviewed.R_1_1.astype(int).map(labels(year,'R_1_1'))
    interviewed['age_band']=pd.cut(interviewed.H01_02,[14,29,44,59,np.inf],labels=['15–29','30–44','45–59','60+'])
    assert interviewed.size_label.notna().all() and interviewed.age_band.notna().all()
    receipt={'year':year,'source_rows_n':len(d),'adults15plus_roster_n':len(adults),
        'adults15plus_information_received_n':len(interviewed),
        'no_individual_information15plus_n':len(adults)-len(interviewed),
        'no_information_weight':float(adults.loc[adults.H01_12.eq(99),'KVZV'].sum()),
        'information_received_weight':float(interviewed.KVZV.sum()),'regions_n':interviewed.region.nunique(),
        'raw_sha256':pin['sha256']}
    return interviewed,receipt


def summary(g,year,goods,scope,group):
    loc=g[f'I04_03_0{goods}'];remote=g[f'I04_04_0{goods}'];w=g.KVZV
    total=float(w.sum());valid=loc.isin([1,2,3,4])
    row={'year':year,'goods':GOODS[goods],'scope':scope,'group':str(group),
         'sample_n':len(g),'base_weight':total,'valid_location_n':int(valid.sum()),
         'valid_location_weight':float(w[valid].sum())}
    for code,name in PLACE.items():
        mask=loc.eq(code);row[name+'_n']=int(mask.sum())
        row[name+'_weight']=float(w[mask].sum());row[name+'_pct']=100*row[name+'_weight']/total
    assert np.isclose(sum(row[name+'_weight'] for name in PLACE.values()),total)
    row['remote_any_n']=int(remote.isin([1,2]).sum())
    row['remote_any_pct']=100*float(w[remote.isin([1,2])].sum())/total
    row['remote_regular_pct']=100*float(w[remote.eq(1)].sum())/total
    row['remote_unknown_pct']=100*float(w[remote.eq(-7)].sum())/total
    row['own_among_valid_pct']=100*float(w[loc.eq(1)].sum())/float(w[valid].sum())
    row['remote_wording']='Internet or postal ordering' if year<2024 else 'Internet ordering'
    return row


def main():
    HERE.mkdir(parents=True,exist_ok=True)
    frames={};receipts=[];pilots=[]
    for year in (2024,2018,2022):
        d,receipt=load(year);frames[year]=d;receipts.append(receipt)
        # Three contrasting regions are checked first, using published labels,
        # never treating year-specific numeric region codes as stable keys.
        for match in (('тверск','краснодар','саха (якутия)') if year==2024 else ()):
            p=d.loc[d.region.str.casefold().str.contains(match,regex=False)&d.locality.eq('rural')]
            assert len(p)>0 and p.region.nunique()==1
            for goods in GOODS:pilots.append(summary(p,year,goods,'pilot_region_rural',p.region.iloc[0]))
    pd.DataFrame(pilots).to_csv(HERE/'purchase_pilot_regions.csv',index=False)
    rows=[];joint=[];strata=[]
    for year,d in frames.items():
        groups=[('national','all',d)]
        groups += [('locality',k,g) for k,g in d.groupby('locality')]
        groups += [('settlement_size',str(k),g) for k,g in d.groupby('R_1_1')]
        if year==2024:
            groups += [('rural_region',k,g) for k,g in d.loc[d.locality.eq('rural')].groupby('region')]
        for scope,key,g in groups:
            for goods in GOODS:rows.append(summary(g,year,goods,scope,key))
        for local,g in [('all',d)]+list(d.groupby('locality')):
            for goods in GOODS:
                loc=g[f'I04_03_0{goods}'];rem=g[f'I04_04_0{goods}']
                state=np.select([rem.isin([1,2]),rem.isin([3,4])],['remote_any','no_remote'],default='dont_know')
                for group in ('remote_any','no_remote','dont_know'):
                    s=g.loc[state==group]
                    if not len(s):continue
                    r=summary(s,year,goods,'remote_group_'+local,group)
                    r['group_share_base_pct']=100*float(s.KVZV.sum())/float(g.KVZV.sum())
                    joint.append(r)
        rural=d.loc[d.locality.eq('rural')]
        for key,g in rural.groupby(['R_1_1','age_band','H01_01'],observed=True):
            for goods in GOODS:
                r=summary(g,year,goods,'rural_stratum','|'.join(map(str,key)))
                r.update(size_code=int(key[0]),age_band=str(key[1]),sex=int(key[2]))
                strata.append(r)
    result=pd.DataFrame(rows);joint=pd.DataFrame(joint);strata=pd.DataFrame(strata)
    result.to_csv(HERE/'purchase_geography.csv',index=False)
    joint.to_csv(HERE/'purchase_geography_by_remote_use.csv',index=False)
    strata.to_csv(HERE/'purchase_rural_strata.csv',index=False)
    # Descriptive standardisation to the 2022 rural age/sex/size composition.
    # No platform treatment, control, counterfactual or causal design is used.
    standard=[]
    for goods in GOODS.values():
        g=strata.loc[strata.goods.eq(goods)].copy()
        common=set.intersection(*(set(g.loc[g.year.eq(y),'group']) for y in frames))
        target=g.loc[g.year.eq(2022)&g.group.isin(common)].set_index('group')
        target_weight=target.base_weight/target.base_weight.sum()
        for year in frames:
            s=g.loc[g.year.eq(year)&g.group.isin(common)].set_index('group').reindex(target.index)
            r={'year':year,'goods':goods,'common_strata_n':len(common),
               'target_year':2022,'target_sample_n':int(target.sample_n.sum()),
               'target_weight_coverage_pct':100*float(target.base_weight.sum())/float(g.loc[g.year.eq(2022),'base_weight'].sum()),
               'min_source_stratum_n':int(s.sample_n.min())}
            for field in ('own_locality_or_urban_district_pct','nearby_localities_or_districts_pct','remote_any_pct'):
                r[field]=float((s[field]*target_weight).sum())
            standard.append(r)
    pd.DataFrame(standard).to_csv(HERE/'purchase_rural_standardised.csv',index=False)
    # The 2024 cross section has one wording for all respondents. Compare
    # remote/nonremote groups descriptively at a common age/sex/size mix.
    group_standard=[]
    rural=frames[2024].loc[frames[2024].locality.eq('rural')].copy()
    rural['stratum']=rural.R_1_1.astype(str)+'|'+rural.age_band.astype(str)+'|'+rural.H01_01.astype(str)
    for goods in GOODS:
        eligible=rural.loc[rural[f'I04_04_0{goods}'].isin([1,2,3,4])].copy()
        eligible['remote_group']=np.where(eligible[f'I04_04_0{goods}'].isin([1,2]),'remote_any','no_remote')
        cellrows=[]
        for (key,group),s in eligible.groupby(['stratum','remote_group']):
            cellrows.append(dict(stratum=key,remote_group=group,n=len(s),
                weight=float(s.KVZV.sum()),
                own_pct=100*float(s.loc[s[f'I04_03_0{goods}'].eq(1),'KVZV'].sum())/float(s.KVZV.sum())))
        cells=pd.DataFrame(cellrows)
        support=cells.groupby('stratum').remote_group.nunique().eq(2)
        keys=list(support[support].index)
        target=eligible.groupby('stratum').KVZV.sum().reindex(keys)
        total_weight=float(eligible.KVZV.sum())
        weights=target/target.sum()
        for group in ('remote_any','no_remote'):
            cells_group=cells.loc[cells.remote_group.eq(group)].set_index('stratum').reindex(keys)
            source=eligible.loc[eligible.remote_group.eq(group)]
            group_standard.append(dict(year=2024,goods=GOODS[goods],remote_group=group,
                common_strata_n=len(keys),pooled_weight_coverage_pct=100*float(target.sum())/total_weight,
                min_group_stratum_n=int(cells_group.n.min()),sample_n=len(source),
                raw_own_pct=100*float(source.loc[source[f'I04_03_0{goods}'].eq(1),'KVZV'].sum())/float(source.KVZV.sum()),
                standardised_own_pct=float((cells_group.own_pct*weights).sum())))
    pd.DataFrame(group_standard).to_csv(HERE/'purchase_groups_standardised2024.csv',index=False)
    info={'unit':'Persons aged15+ for whom individual information was obtained, including proxy answers; repeated cross sections, not a person panel.',
          'weight':'KVZV supplied weight; unknown responses are explicit, not recoded as no.',
          'waves':receipts,'standardisation':'2022 rural settlement-size × age4 × sex composition, common support only.',
          'not_estimated':['Actual trips','Named destinations','WB/Ozon-specific use','Causal effect','Design-based standard errors'],
          'wording_change':'Earlier remote channel includes postal ordering; 2024 form asks Internet only. 2018 fieldwork season differs.',
          'regional_labels':'Regional names decoded from 2024 codebook only; earlier codes are not assigned these names.'}
    (HERE/'purchase_analysis_metadata.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    print(result.loc[result.scope.eq('locality')&result.group.eq('rural'),
        ['year','goods','sample_n','own_locality_or_urban_district_pct','nearby_localities_or_districts_pct','remote_any_pct']].round(3).to_string(index=False))


if __name__=='__main__':main()

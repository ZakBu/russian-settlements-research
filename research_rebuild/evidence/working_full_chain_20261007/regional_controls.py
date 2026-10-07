"""Explicit 2010 region-name/code mapping; no fuzzy or substring assignment."""
from pathlib import Path
import pandas as pd

# Codes and names transcribed from the official control labels and selected
# region_norm enumeration. The CSV output retains both labels for review.
REGION_CODES = {
'белгородская':14000000,'брянская':15000000,'владимирская':17000000,
'воронежская':20000000,'ивановская':24000000,'калужская':29000000,
'костромская':34000000,'курская':38000000,'липецкая':42000000,
'московская':46000000,'орловская':54000000,'рязанская':61000000,
'смоленская':66000000,'тамбовская':68000000,'тверская':28000000,
'тульская':70000000,'ярославская':78000000,'москва':45000000,
'карелия':86000000,'коми':87000000,'архангельская':11000000,
'ненецкий':11800,'вологодская':19000000,'калининградская':27000000,
'ленинградская':41000000,'мурманская':47000000,'новгородская':49000000,
'псковская':58000000,'санкт петербург':40000000,'адыгея':79000000,
'калмыкия':85000000,'краснодарский':3000000,'астраханская':12000000,
'волгоградская':18000000,'ростовская':60000000,'дагестан':82000000,
'ингушетия':26000000,'кабардино балкарская':83000000,
'карачаево черкесская':91000000,'северная осетия алания':90000000,
'чеченская':96000000,'ставропольский':7000000,'башкортостан':80000000,
'марий эл':88000000,'мордовия':89000000,'татарстан':92000000,
'удмуртская':94000000,'чувашская':97000000,'пермский':57000000,
'кировская':33000000,'нижегородская':22000000,'оренбургская':53000000,
'пензенская':56000000,'самарская':36000000,'саратовская':63000000,
'ульяновская':73000000,'курганская':37000000,'свердловская':65000000,
'тюменская':71000000,'ханты мансийский югра':71800,'ямало ненецкий':71900,
'челябинская':75000000,'алтай':84000000,'бурятия':81000000,'тыва':93000000,
'хакасия':95000000,'алтайский':1000000,'забайкальский':76000000,
'красноярский':4000000,'иркутская':25000000,'кемеровская':32000000,
'новосибирская':50000000,'омская':52000000,'томская':69000000,
'саха якутия':98000000,'камчатский':30000000,'приморский':5000000,
'хабаровский':8000000,'амурская':10000000,'магаданская':44000000,
'сахалинская':64000000,'еврейская':99000000,'чукотский':77000000,
}
FOLDS={'ненецкий':'архангельская','ханты мансийский югра':'тюменская','ямало ненецкий':'тюменская'}

def reconcile(ordinary, fed, controls, scopeunion, out):
    controls=pd.read_csv(controls)
    table=ordinary[ordinary.census_year.eq(2010)].copy()
    assert set(table.region_norm)==set(REGION_CODES)-{'москва','санкт петербург'}
    assert len(set(REGION_CODES.values()))==len(REGION_CODES)==83
    assert set(REGION_CODES.values())==set(controls.OKTMO_code)-{643}
    table['control_region']=table.region_norm.map(lambda r:FOLDS.get(r,r))
    table['scope_joint_population']=table.population.where(table.source_record_id.isin(scopeunion),0)
    table['zero']=table.population.eq(0);table['unknown']=table.population.isna()
    grouped=table.groupby('control_region').agg(selected_population=('population','sum'),strict_joint_population=('strict_joint_population','sum'),qualified_union_population=('scope_joint_population','sum'),selected_rows=('source_record_id','count'),zero_population_rows=('zero','sum'),unknown_population_rows=('unknown','sum')).reset_index()
    extra=[]
    for row in fed[fed.census_year.eq(2010)].to_dict('records'):
        extra.append({'control_region':row['region_norm'],'selected_population':row['territory_population'],'strict_joint_population':row['territory_population'],'qualified_union_population':row['territory_population'],'selected_rows':1,'zero_population_rows':0,'unknown_population_rows':0})
    grouped=pd.concat([grouped,pd.DataFrame(extra)],ignore_index=True)
    grouped['control_code']=grouped.control_region.map(REGION_CODES)
    assert grouped.control_code.nunique()==len(grouped)==80
    grouped=grouped.merge(controls[['OKTMO_code','OKTMO_description','population']],left_on='control_code',right_on='OKTMO_code',validate='one_to_one').rename(columns={'OKTMO_description':'official_control_label','population':'official_population'})
    grouped['control_minus_selected_population']=grouped.official_population-grouped.selected_population
    grouped['control_minus_strict_joint_population']=grouped.official_population-grouped.strict_joint_population
    grouped['control_minus_qualified_union_population']=grouped.official_population-grouped.qualified_union_population
    grouped['qualified_union_percent_of_official_control']=100*grouped.qualified_union_population/grouped.official_population
    assert int(grouped.official_population.sum())==142856536
    assert int(grouped.control_minus_selected_population.sum())==493512
    grouped['strict_joint_gap_rank']=grouped.control_minus_strict_joint_population.rank(method='min',ascending=False).astype(int)
    grouped.sort_values('strict_joint_gap_rank').to_csv(out/'regional_official_2010_joint_gap_rank.csv',index=False)
    mapping=[{'region_norm':r,'official_control_code':c,'official_control_label':controls.loc[controls.OKTMO_code.eq(c),'OKTMO_description'].iloc[0],'disjoint_parent_control_code':REGION_CODES[FOLDS.get(r,r)],'folded_parent_region':FOLDS.get(r,r)} for r,c in REGION_CODES.items()]
    pd.DataFrame(mapping).to_csv(out/'official_2010_region_mapping.csv',index=False)
    return {'status':'recalculated_explicit_region_code_mapping_verified_complete','selected_regions_mapped':83,'disjoint_control_regions':80,'sum_official_disjoint_controls':142856536,'national_gap_preserved':493512,'parent_folds':FOLDS,'ordinary_region_rows':len(table),'federal_regions_separate_territory_counts':2}

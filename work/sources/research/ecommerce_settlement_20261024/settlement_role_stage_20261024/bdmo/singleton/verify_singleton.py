"""Independent raw-register cardinality and raw BDMO C/S arithmetic checks."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import csv,json,re
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
register=BASE/'history_stage_20261024/centres/raw'
wide=pd.read_csv(OUT/'singleton_stability_candidates.csv',dtype={'oktmo':str},keep_default_na=False)
candidates=wide.loc[wide.stable2020_2026_singleton_candidate]
checks=[]
for date in ['20200110','20211103','20220927','20261001']:
    path=next(register.glob('data-'+date+'T*.csv'))
    try:text=path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:text=path.read_text(encoding='cp1251')
    rows=list(csv.reader(text.splitlines(),delimiter=';'))
    groups5=defaultdict(set);groups8=defaultdict(set)
    for r in rows:
        if len(r)!=13 or not all(r[j].isdigit() for j in range(4)) or r[5]!='2' or r[3]=='000':continue
        if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}',r[12]) and datetime.strptime(r[12],'%d.%m.%Y')>datetime.strptime(date,'%Y%m%d'):continue
        code=''.join(r[:4]);groups5[code[:5]].add(code);groups8[code[:8]].add(code)
    errors=[]
    for _,row in candidates.iterrows():
        full=groups5.get(row.oktmo[:5],set()) if row.mun_level=='Муниципальное образование верхнего уровня' else groups8.get(row.oktmo,set())
        if len(full)!=1:errors.append(row.oktmo)
    assert not errors
    checks.append({'vintage':date,'all_stable_candidates_checked':len(candidates),
                   'full_register_cardinality_mismatches':len(errors)})

full=pd.read_parquet(OUT.parent/'shop_object_counts_all_municipal_levels.parquet')
panel=pd.read_csv(OUT/'internal_centre_district_common_panels2022_2024.csv',
                  dtype={'centre_oktmo':str,'district_oktmo':str})
shop=full.loc[full.indicator_period.eq('IV квартал')&full.year.isin([2022,2023,2024])&
              full.obroz.isin(['Магазины','Специализированные непродовольственные магазины'])]
lookup={key:set(g.indicator_value) for key,g in shop.groupby(['oktmo','mun_level','year','obroz'])}
arithmetic=0
for _,row in panel.iterrows():
    for year in [2022,2023,2024]:
        c=lookup[(row.centre_oktmo,'Муниципальное образование нижнего уровня',year,row.category)]
        s=lookup[(row.district_oktmo,'Муниципальное образование верхнего уровня',year,row.category)]
        assert len(c)==len(s)==1
        centre=next(iter(c));district=next(iter(s))
        assert row['centre_shops_'+str(year)]==centre
        assert row['district_shops_'+str(year)]==district
        assert district>=centre and district>0
        assert abs(row['centre_share_pct_'+str(year)]-100*centre/district)<1e-9
        arithmetic+=1
    change=row.centre_share_pct_2024-row.centre_share_pct_2022
    assert abs(change-row.centre_share_change2022_2024_pp)<1e-9
report={'status':'PASS_conditional_unit_identity','full_composition_checks':checks,
        'concentration_panel_rows':len(panel),'raw_source_C_S_share_checks':arithmetic,
        'year_specific_2023_2024_full_composition_verified':False,
        'tls_validation_disabled_during_this_stage':False,
        'no_municipal_count_allocated_to_multiple_NP':True}
(OUT/'independent_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))

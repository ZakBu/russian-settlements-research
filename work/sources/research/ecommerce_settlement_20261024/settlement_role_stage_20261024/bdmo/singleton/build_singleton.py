"""Strict full-register singleton candidacy; no allocation of multi-settlement totals.
Run: PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 build_singleton.py
No network access or changes to prior stages.
"""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime
import csv,hashlib,json,re,unicodedata
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
REGISTER=BASE/'history_stage_20261024/centres/raw'
BDMO=OUT.parent/'shop_object_counts_all_municipal_levels.parquet'
AXIS=BASE/'national/national_target_source2021.parquet'
LONG=BASE/'pilot/inputs/data/population/settlements_census_long.parquet'
axis=pd.read_parquet(AXIS)
target=set(axis.source_record_id_2021)
census=pd.read_parquet(LONG)
census=census.loc[census.census_year.eq(2021)]
upper='Муниципальное образование верхнего уровня'
lower='Муниципальное образование нижнего уровня'
fields=['TER','KOD1','KOD2','KOD3','KC','RAZDEL','NAME1','Centrum','NomDescr',
        'NomAkt','Status','DateUtv','DateVved']


def norm(s):
    s=unicodedata.normalize('NFKC',str(s or '')).casefold().replace('ё','е')
    return re.sub(r'\s+',' ',re.sub(r'[^\w\s-]',' ',s)).strip()


def parse_name(s):
    parts=s.strip().split(maxsplit=1)
    types={'г':'город','с':'село','д':'деревня','п':'поселок','рп':'пгт','пгт':'пгт',
           'гп':'пгт','кп':'пгт','дп':'пгт','х':'хутор','ст-ца':'станица','аул':'аул',
           'сл':'слобода','нп':'населенный пункт','ст':'станция','рзд':'разъезд',
           'у':'улус','починок':'починок'}
    if len(parts)!=2 or parts[0].strip('.').lower() not in types:return '',''
    return norm(parts[1]),types[parts[0].strip('.').lower()]


def code11(v):
    value=str(v or '')
    return value.zfill(11) if value.isdigit() and len(value) in [10,11] else ''


bycode=defaultdict(list)
for r in census.to_dict('records'):
    if code11(r['oktmo']):bycode[code11(r['oktmo'])].append(r)
bridge=[];register_audit=[];inputs=[]
for path in sorted(REGISTER.glob('data-*.csv')):
    data=path.read_bytes()
    try:text=data.decode('utf-8-sig');enc='utf8'
    except UnicodeDecodeError:text=data.decode('cp1251');enc='cp1251'
    vintage=re.search(r'data-(\d{8})T',path.name).group(1)
    date=datetime.strptime(vintage,'%Y%m%d').date()
    raw=list(csv.reader(text.splitlines(),delimiter=';'))
    rows=[dict(zip(fields,r),source_row=i+1) for i,r in enumerate(raw)
          if len(r)==13 and all(r[j].isdigit() for j in range(4))]
    future=[r for r in rows if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}',r['DateVved']) and
            datetime.strptime(r['DateVved'],'%d.%m.%Y').date()>date]
    rows=[r for r in rows if r not in future]
    np_rows=[r for r in rows if r['RAZDEL']=='2' and r['KOD3']!='000']
    groups5=defaultdict(list);groups8=defaultdict(list)
    for r in np_rows:
        code=r['TER']+r['KOD1']+r['KOD2']+r['KOD3']
        r['np_code11']=code
        groups5[code[:5]].append(r);groups8[code[:8]].append(r)
    assert len({r['np_code11'] for r in np_rows})==len(np_rows)
    real=[r for r in rows if r['RAZDEL']=='1' and r['KOD3']=='000' and
          r['KOD1']!='000' and bool(r['Centrum'].strip()) and not r['KOD1'].endswith('00')]
    for r in real:
        level=upper if r['KOD2']=='000' else lower
        if level==lower and r['KOD2'].endswith('00'):continue
        code8=r['TER']+r['KOD1']+r['KOD2']
        full=groups5.get(code8[:5],[]) if level==upper else groups8.get(code8,[])
        singleton=full[0] if len(full)==1 else None
        candidates=[]
        if singleton:
            name,typ=parse_name(singleton['NAME1'])
            candidates=[c for c in bycode.get(singleton['np_code11'],[]) if
                        norm(c['settlement_name'])==name and c['type_norm']==typ and
                        c['population_scope']=='settlement' and c['is_additive_settlement_record']]
        linked=candidates[0] if len(candidates)==1 and candidates[0]['source_record_id'] in target else None
        status=('singleton_exact_np_axis2021' if linked else
                'singleton_no_unique_exact_main_axis_link' if singleton else
                'multiple_settlements_not_allocated' if len(full)>1 else 'no_np_roster_unknown')
        bridge.append({'register_vintage':vintage,'oktmo':code8,'mun_level':level,
            'municipality_official':r['NAME1'],'full_official_np_count':len(full),
            'singleton_official_np_code':singleton['np_code11'] if singleton else '',
            'singleton_official_np_name':singleton['NAME1'] if singleton else '',
            'source_record_id_2021':linked['source_record_id'] if linked else '',
            'name_2021':linked['settlement_name'] if linked else '',
            'region_2021':linked['region_norm'] if linked else '',
            'bridge_status':status,'source_row':r['source_row'],
            'full_count_includes_unlinked_and_zero_population':True})
    register_audit.append({'vintage':vintage,'raw_rows':len(raw),'all_official_np_rows':len(np_rows),
        'real_municipality_rows_with_explicit_centre':len(real),'future_rows_excluded':len(future),'encoding':enc})
    inputs.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
b=pd.DataFrame(bridge)
assert not b.duplicated(['register_vintage','oktmo','mun_level']).any()
b.to_parquet(OUT/'municipality_full_composition_bridge.parquet',index=False)
b.loc[b.full_official_np_count.eq(1)].to_csv(OUT/'singleton_bridge_all_available_vintages.csv',index=False)
wide=[]
vintages=sorted(b.register_vintage.unique())
for (code,level),g in b.groupby(['oktmo','mun_level']):
    table=g.set_index('register_vintage')
    record={'oktmo':code,'mun_level':level}
    for date in vintages:
        r=table.loc[date] if date in table.index else None
        record['full_np_count_'+date]=int(r.full_official_np_count) if r is not None else None
        record['source_record_id_2021_'+date]=r.source_record_id_2021 if r is not None else ''
    for name,required in [('stable2020_2026',['20200110','20211103','20220927','20261001']),
                          ('stable2015_2026',vintages)]:
        ids=[record['source_record_id_2021_'+v] for v in required]
        valid=all(ids) and len(set(ids))==1 and all(record['full_np_count_'+v]==1 for v in required)
        record[name+'_singleton_candidate']=valid
        record[name+'_source_record_id_2021']=ids[0] if valid else ''
    wide.append(record)
w=pd.DataFrame(wide)
w.to_csv(OUT/'singleton_stability_candidates.csv',index=False)

# Exact category only; no sum of food/nonfood subcategories, markets or catering.
full=pd.read_parquet(BDMO)
shops=full.loc[full.obroz.eq('Магазины')&full.mun_level.isin([upper,lower])].copy()
shops['source_row_index']=shops.index
raw_n=len(shops)
keys=['oktmo','mun_level','year','indicator_period']
groups=shops.groupby(keys,dropna=False).indicator_value.agg(['size','nunique']).reset_index()
conflict=groups.loc[groups['nunique'].gt(1),keys]
equalduplicates=groups.loc[groups['size'].gt(1)&groups['nunique'].eq(1),keys]
shops=shops.merge(conflict.assign(conflicting_key=True),on=keys,how='left',validate='many_to_one')
excluded=shops.loc[shops.conflicting_key.eq(True)]
excluded.to_csv(OUT/'conflicting_municipal_shop_values_excluded.csv',index=False)
shops=shops.loc[~shops.conflicting_key.eq(True)].drop_duplicates(keys)
assert not shops.duplicated(keys).any()
joined=shops.merge(w,on=['oktmo','mun_level'],how='left',validate='many_to_one')
joined['bridge_temporal_status']='not_verified_at_each_observation_date'
joined['observation_is_actual_settlement_shop_inventory']=False
annual=joined.loc[joined.year.between(2015,2021)&
                  joined.indicator_period.eq('Значение показателя за год')&
                  joined.stable2015_2026_singleton_candidate.eq(True)].copy()
quarter=joined.loc[joined.year.isin([2022,2023,2024])&joined.indicator_period.eq('IV квартал')&
                   joined.stable2020_2026_singleton_candidate.eq(True)].copy()
annual['source_record_id_2021']=annual.stable2015_2026_source_record_id_2021
quarter['source_record_id_2021']=quarter.stable2020_2026_source_record_id_2021
annual.to_parquet(OUT/'annual2015_2021_singleton_candidate_observations.parquet',index=False)
quarter.to_parquet(OUT/'quarterIV2022_2024_singleton_candidate_observations.parquet',index=False)
audit={'status':'PASS_with_temporal_identity_limit','register_audit':register_audit,
       'full_np_count_rule':'upper first5; lower first8; all official section2 NP rows, before any census-axis linkage; include unlinked/zero-population records',
       'available_vintages':vintages,'missing_observation_specific_vintages':[2023,2024],
       'real_municipality_rule':'section1,nonzero KOD1,zero KOD3,explicitCentrum; non-group code; empty-centre actual units conservatively excluded',
       'bridge_status_counts':b.groupby('register_vintage').bridge_status.value_counts().to_dict() and
          b.groupby(['register_vintage','bridge_status']).size().rename('municipalities_n').reset_index().to_dict('records'),
       'stable2020_2026_singleton_municipalities_n':int(w.stable2020_2026_singleton_candidate.sum()),
       'stable2015_2026_singleton_municipalities_n':int(w.stable2015_2026_singleton_candidate.sum()),
       'shops_exact_category_source_rows':raw_n,'conflicting_keys_excluded_n':len(conflict),
       'conflicting_rows_excluded_n':len(excluded),'equal_value_duplicate_keys_collapsed_n':len(equalduplicates),
       'annual_candidate_rows':len(annual),'quarterIV_candidate_rows':len(quarter),
       'limits':['No2023/2024 verified full-register rosters downloaded; TLS validation kept enabled and failed.',
                 'Singleton at available vintages is stability candidacy, not verified boundaries or per-year membership.',
                 'One named settlement in municipality does not geolocate each outlet inside its built-up boundary.',
                 'Exact shops category and time periods retained; annual series and quarterIV series never concatenated.',
                 'No physical openings/closures or marketplace causal effects inferred.'],
       'inputs':inputs+[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [BDMO,AXIS,LONG]]}
(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in audit.items() if k not in ['inputs','bridge_status_counts','register_audit']},ensure_ascii=False,indent=2))

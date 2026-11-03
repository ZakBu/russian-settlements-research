"""Check published named places against the unchanged census and fixed cohort.

Name, region and explicit settlement type are retrieval conditions, never a
nearest-coordinate assignment. This checks geography, not truth of trip reports.
"""
from pathlib import Path
import hashlib,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
RAW=ROOT/'work/sources/research/ecommerce_settlement_20261024'
def main():
    axis=RAW/'national/national_target_source2021.parquet'
    centres=RAW/'settlement_role_stage_20261024/system/centre_system_demography.csv'
    assert hashlib.sha256(axis.read_bytes()).hexdigest()=='89fce76fe330dd33bd3b5f8496f3e46e7faffaf55d045193bd4070f8a2d017f2'
    assert hashlib.sha256(centres.read_bytes()).hexdigest()=='c2fa7ab6874ebe32709a8737599e3a0c9d02305501a2a85104f76eaba29ae57e'
    a=pd.read_parquet(axis);c=pd.read_csv(centres)
    assert c.medium_primary2002.sum()==1273
    specs=[('Луга','ленинградская','город'),('Толмачево','ленинградская','пгт'),
        ('Енисейск','красноярский','город'),('Верхнепашино','красноярский','село'),
        ('Вагай','тюменская','село'),('Лукоянов','нижегородская','город'),
        ('Сосновское','нижегородская','пгт'),('Павлово','нижегородская','город'),
        ('Вача','нижегородская','пгт'),('Семенов','нижегородская','город'),
        ('Ворсма','нижегородская','город'),('Дивеево','нижегородская','село'),
        ('Кашин','тверская','город'),('Верхняя Троица','тверская','деревня'),
        ('Серебрянский','ленинградская','посёлок')]
    out=[]
    for name,reg,typ in specs:
        g=a.loc[a.name_2021.eq(name)&a.region_2021.eq(reg)&a.type_2021.eq(typ)]
        # Vagai is not unique by name in the region; the published district
        # is an explicit additional condition, not inferred from closeness.
        if name=='Вагай':g=g.loc[g.district_2021.eq('Вагайский муниципальный район')]
        assert len(g)==1,(name,len(g))
        q=g.iloc[0];match=c.loc[c.source_record_id_2021.eq(q.source_record_id_2021)]
        assert len(match)<=1
        in_cohort=bool(match.medium_primary2002.iloc[0])if len(match)else False
        out.append(dict(source_record_id_2021=q.source_record_id_2021,name_2021=name,
            region_2021=reg,type_2021=typ,district_2021=q.district_2021,
            population_2002=q.population_2002,population_2021=q.population_2021,
            passes_population_range2002=5000<=q.population_2002<50000,
            in_fixed_admin_centre_table=bool(len(match)),in_fixed1273=in_cohort))
    pd.DataFrame(out).to_csv(HERE/'named_place_cohort_audit.csv',index=False)
    print(json.dumps(dict(named_places_checked=len(out),fixed_cohort_n=1273,
        not_a_flow_or_effect_check=True),ensure_ascii=False))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Recompute transitions and separate demographic from membership axes."""
from pathlib import Path
import json
import pandas as pd
from decomposition import decompose, self_test

ROOT=Path(__file__).resolve().parent.parent
PANEL=ROOT.parent/'anchor_research_20261019/data/point_axis.parquet'

def build(out=None):
    h=pd.read_csv(ROOT/'history/edges_by_year.csv')
    p=pd.read_parquet(PANEL).set_index('id')
    out=Path(out) if out is not None else ROOT/'model/results';out.mkdir(exist_ok=True)
    rows=[];changes=[];checks=[]
    pairs=[('Nizhneturinsky',2023,2025,h),('Nizhneturinsky',2025,2026,h)]
    kona=ROOT/'history/konakovo_edges_by_year.csv'
    if kona.exists():pairs.append(('Konakovo_selected_three_provider_groups',2021,2026,pd.read_csv(kona)))
    for family,a,b,table in pairs:
        rawx=table[table.year.eq(a)];rawy=table[table.year.eq(b)]
        x=rawx[rawx.origin_uid.notna()&rawx.destination_uid.notna()];y=rawy[rawy.origin_uid.notna()&rawy.destination_uid.notna()]
        assert x.origin_uid.is_unique and y.origin_uid.is_unique
        universe=set(x.origin_uid)&set(y.origin_uid)
        # Only positively named origins in both acts are comparable; extra explicit names unknown before.
        xx=x[x.origin_uid.isin(universe)].set_index('origin_uid')
        yy=y[y.origin_uid.isin(universe)].set_index('origin_uid')
        for u in sorted(universe):
            changes.append(dict(comparison_scope=family,from_document_year=a,to_document_year=b,origin_uid=u,origin_name=p.loc[u,'name'],old_provider_uid=xx.loc[u,'destination_uid'],old_provider_name=xx.loc[u,'provider_settlement'],new_provider_uid=yy.loc[u,'destination_uid'],new_provider_name=yy.loc[u,'provider_settlement'],normative_provider_changed=xx.loc[u,'destination_uid']!=yy.loc[u,'destination_uid'],actual_demand_transfer_measured=False,positive_assignment_both_dates=True))
        for dest in sorted(set(xx.destination_uid)|set(yy.destination_uid)):
            old=set(xx[xx.destination_uid.eq(dest)].index);new=set(yy[yy.destination_uid.eq(dest)].index)
            r=decompose(old,new,p.population_2010.to_dict(),p.population_2021.to_dict())
            rows.append(dict(comparison_scope=family,from_document_year=a,to_document_year=b,population_old_year=2010,population_new_year=2021,destination_uid=dest,destination_name=p.loc[dest,'name'],comparable_origin_universe_n=len(universe),comparison='two_independent_axes_not_contemporaneous_document_year_population_change',**r))
            assert r['accounting_residual']==0
        checks.append(dict(comparison_scope=family,pair=f'{a}_{b}',common_origins=len(universe),common_literal_origin_names=len(set(rawx.origin_name)&set(rawy.origin_name)),newly_explicit_not_reassigned=len(set(y.origin_uid)-set(x.origin_uid)),unknown_after=len(set(x.origin_uid)-set(y.origin_uid))))
    res=pd.DataFrame(rows);c=pd.DataFrame(changes)
    for n,d in [('history_two_axis_accounting',res),('history_positive_assignment_transitions',c)]:
        d.to_csv(out/f'{n}.csv',index=False);d.to_parquet(out/f'{n}.parquet',index=False)
    # The whole shared universe is constant, so reassignment effects across all providers cancel exactly.
    balances=res.groupby(['from_document_year','to_document_year']).boundary_effect_at_new_population.sum()
    assert balances.eq(0).all()
    expected={(2023,2025):1,(2025,2026):0}
    if kona.exists():expected[(2021,2026)]=0
    assert c.groupby(['from_document_year','to_document_year']).normative_provider_changed.sum().to_dict()==expected
    audit={'status':'PASS','arithmetic_self_tests':self_test(),'pairs':checks,'reallocation_balance_2021':{f'{a}_{b}':v for (a,b),v in balances.to_dict().items()},'accounting_rows':len(res),'transition_rows':len(c),'changed_2023_2025':1,'changed_2025_2026':0,'all_accounting_residuals_zero':bool(res.accounting_residual.eq(0).all()),'contemporaneous_population_2023_2025_claim':False}
    (out/'HISTORY_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':build()

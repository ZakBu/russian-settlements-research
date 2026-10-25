"""Final checks plus independent, bounded checks against the original tables."""
from pathlib import Path
import hashlib,json,math
import pandas as pd
import pyarrow.dataset as ds
import nbformat

OUT=Path(__file__).resolve().parent
BASE=OUT.parent
KEY='source_record_id_2021'


def main():
    protected=json.loads((BASE/'execution_20261024/input_manifest.json').read_text())
    for r in protected['inputs']:
        assert hashlib.sha256((BASE/r['path']).read_bytes()).hexdigest()==r['sha256']
    trade=pd.read_csv(OUT/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv',
                      dtype={'centre_oktmo':str,'district_oktmo':str})
    assert not trade.duplicated([KEY,'category']).any()
    medium=trade.loc[trade.medium_primary2002]
    g=medium.loc[medium.category.eq('Магазины')]
    assert len(g)==174
    assert [int(g.centre_stock_change2022_2024.lt(0).sum()),
            int(g.centre_stock_change2022_2024.gt(0).sum()),
            int(g.centre_stock_change2022_2024.eq(0).sum())]==[55,84,35]
    assert int((g.centre_stock_change2022_2024.lt(0)&
                g.centre_share_change2022_2024_pp.ge(-1e-9)).sum())==23
    for year in [2022,2023,2024]:
        c=trade[f'centre_shops_{year}'];s=trade[f'district_shops_{year}']
        assert c.ge(0).all() and s.gt(0).all() and s.ge(c).all()
        assert c.eq(c.round()).all() and s.eq(s.round()).all()
        assert ((100*c/s-trade[f'centre_share_pct_{year}']).abs()<1e-8).all()
    # Deterministic independent checks against the full acquired section, not the
    # already-extracted shop or concentration outputs.
    sample=trade.sort_values([KEY,'category']).iloc[::max(1,len(trade)//12)].head(12)
    codes=sorted(set(sample.centre_oktmo)|set(sample.district_oktmo))
    source=next((OUT/'bdmo/raw').glob('*.parquet'))
    expr=(ds.field('indicator_code')=='Y48002001') & ds.field('oktmo').isin(codes) & \
         ds.field('year').isin([2022,2023,2024]) & (ds.field('indicator_period')=='IV квартал')
    rows=ds.dataset(source,format='parquet').to_table(filter=expr,columns=[
        'oktmo','mun_level','year','obroz','indicator_value']).to_pylist()
    index={}
    for r in rows:
        k=(r['oktmo'],r['mun_level'],r['year'],r['obroz'])
        index.setdefault(k,set()).add(r['indicator_value'])
    source_checks=0
    for r in sample.to_dict('records'):
        for year in [2022,2023,2024]:
            for code,level,field in [
                (r['centre_oktmo'],'Муниципальное образование нижнего уровня','centre_shops_'),
                (r['district_oktmo'],'Муниципальное образование верхнего уровня','district_shops_')]:
                values=index[(code,level,year,r['category'])]
                assert values=={r[field+str(year)]},(code,year,values,r[field+str(year)])
                source_checks+=1
    dem=pd.read_csv(OUT/'system/centre_system_demography.csv')
    h=dem.loc[dem.medium_primary2002&dem.demographic_comparison_supported]
    assert len(h)==1195
    assert int((h.centre_change2002_2021_pct.lt(0)&h.centre_population_share_change_pp.ge(1)).sum())==752
    pop=pd.read_parquet(BASE/'national/national_target_source2021.parquet').set_index(KEY)
    admin=pd.read_parquet(BASE/'history_stage_20261024/centres/settlement_admin_context_main2021.parquet')
    centre_col='administrative_centre_source_record_id_2021_20200110'
    valid=admin.context_status_20200110.eq('accepted_administrative_parent_and_centre')
    demographic_checks=0
    for r in h.sort_values(KEY).iloc[::100].to_dict('records'):
        identifier=r[KEY]
        ids=set(admin.loc[valid&admin[centre_col].eq(identifier),KEY])|{identifier}
        p=pop.loc[sorted(ids)]
        q=p.loc[p.population_value_quality_2002.eq('direct_published_census_value')&
                p.population_value_quality_2021.eq('direct_published_census_value')&
                p.population_2002.notna()&p.population_2021.notna()]
        s0=100*pop.loc[identifier,'population_2002']/q.population_2002.sum()
        s1=100*pop.loc[identifier,'population_2021']/q.population_2021.sum()
        assert math.isclose(s1-s0,r['centre_population_share_change_pp'],abs_tol=1e-8)
        demographic_checks+=1
    choya=pd.read_csv(OUT/'choya_functional_concentration.csv')
    for r in choya.to_dict('records'):
        assert r['centre_listed_entries']+r['surrounding_listed_entries']==r['total_listed_entries']
        assert math.isclose(100*r['centre_listed_entries']/r['total_listed_entries'],r['centre_share_pct'],abs_tol=1e-8)
    n=nbformat.read(OUT/'settlement_roles.ipynb',as_version=4)
    nbformat.validate(n)
    code=[c for c in n.cells if c.cell_type=='code']
    assert [c.execution_count for c in code]==list(range(1,len(code)+1))
    assert not any(o.output_type=='error' for c in code for o in c.outputs)
    assert sum('image/png' in o.get('data',{}) for c in code for o in c.outputs)==3
    assert (OUT/'settlement_roles.html').read_text().count('data:image/png;base64,')==3
    result={
        'status':'PASS_with_explicit_source_and_identity_limits',
        'previous_input_hashes_unchanged':True,
        'independent_source_count_checks':source_checks,
        'independent_demographic_context_checks':demographic_checks,
        'main_trade_panel_n':174,'main_historical_demographic_panel_n':1195,
        'all_trade_panel_counts_nonnegative_integers_and_shares_reconciled':True,
        'choya_category_rows_verified':len(choya),
        'notebook':{'executed_code_cells':len(code),'error_outputs':0,'figures':3},
        'html_preview_contains_saved_figures':True,
        'not_established':['causal influence of marketplaces','actual shop closures',
                           'year-specific singleton composition2023/2024','national uniform Ozon history'],
    }
    (OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()

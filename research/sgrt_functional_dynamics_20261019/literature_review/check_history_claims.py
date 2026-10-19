"""Recalculate historical statements without importing the history/model builders."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
R=Path(__file__).resolve().parents[1];O=Path(__file__).parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    e=pd.read_csv(R/'history/edges_by_year.csv');schools=pd.read_csv(R/'history/school_inventory_by_year.csv')
    p=pd.read_parquet(R.parent/'anchor_research_20261019/data/point_axis.parquet').set_index('id')
    claims=[];checks=[]
    def ch(n,v):checks.append({'check':n,'pass':bool(v)})
    ch('origins_unique_each_year',not e.duplicated(['year','origin_uid']).any())
    keys={y:set(g.school_key) for y,g in schools.groupby('year')}
    ch('same_nine_named_school_keys',all(len(x)==9 for x in keys.values()) and len(set(map(frozenset,keys.values())))==1)
    for y,g in e.groupby('year'):
        for cy in [2002,2010,2021]:ch(f'census_readback_{y}_{cy}',np.allclose(g[f'population_{cy}'],p.loc[g.origin_uid,f'population_{cy}'],rtol=0,atol=1e-9,equal_nan=True))
    summary=[]
    for y0,y1 in [(2023,2025),(2025,2026)]:
        a=e[e.year.eq(y0)].set_index('origin_uid');b=e[e.year.eq(y1)].set_index('origin_uid')
        common=sorted(set(a.index)&set(b.index));changed=a.loc[common,'destination_uid'].ne(b.loc[common,'destination_uid'])
        positive_changes=[]
        for uid in np.asarray(common)[changed]:
            positive_changes.append({'origin_uid':uid,'name':p.loc[uid,'name'],'old_provider':a.loc[uid,'provider_settlement'],'new_provider':b.loc[uid,'provider_settlement'],'population_2021':p.loc[uid,'population_2021']})
        summary.append({'year0':y0,'year1':y1,'common':len(common),'changed_provider_settlement':int(changed.sum()),'newly_explicit_not_proven_new_function':len(set(b.index)-set(a.index)),'lost_explicit_not_proven_closed':len(set(a.index)-set(b.index)),'changes':positive_changes})
        for cy in [2002,2010,2021]:
            old=p.loc[common,f'population_{cy}'].groupby(a.loc[common,'destination_uid']).sum()
            new=p.loc[common,f'population_{cy}'].groupby(b.loc[common,'destination_uid']).sum()
            reallocation=new.reindex(old.index.union(new.index),fill_value=0)-old.reindex(old.index.union(new.index),fill_value=0)
            ch(f'fixed_census_reallocation_sum_zero_{y0}_{y1}_{cy}',abs(reallocation.sum())<1e-9)
    ch('one_change_2023_2025',summary[0]['changed_provider_settlement']==1)
    ch('no_change_2025_2026',summary[1]['changed_provider_settlement']==0)
    case=summary[0]['changes'][0]
    ch('new_tura_city_to_platina_case',case['name']=='Новая Тура' and case['old_provider']=='Нижняя Тура' and case['new_provider']=='Платина' and case['population_2021']==95)
    plans=schools.groupby('year').first_grade_plan.sum(min_count=1)
    ch('first_grade_plans_310_to278',plans.loc[2025]==310 and plans.loc[2026]==278)
    account=R/'model/results/history_two_axis_accounting.csv'
    if account.exists():
        aa=pd.read_csv(account)
        for i,r in aa.iterrows():
            ch('two_axis_accounting_common_added_removed_'+str(i),np.isclose(r.two_axis_total_difference,r.common_members_population_change+r.added_members_new_population-r.removed_members_old_population,rtol=0,atol=1e-9))
            ch('two_axis_accounting_fixed_boundary_'+str(i),np.isclose(r.two_axis_total_difference,r.fixed_old_boundary_population_change+r.boundary_effect_at_new_population,rtol=0,atol=1e-9))
    result={'status':'PASS' if all(z['pass'] for z in checks) else 'FAIL','checks':checks,'checks_passed':sum(z['pass'] for z in checks),'checks_total':len(checks),'summary':summary,'first_grade_plan_totals':plans.where(plans.notna(),None).to_dict(),'source_PDF_visual_review':{'2023_p3':'Новая Тура listed under school7; read independently','2026_p3':'Новая Тура listed under Платинская school; read independently','scope_warning':'rows6-9 also include blanket НижняяТура city assertion; rural extraction is not a complete all-resident graph'},'claim_scope':'normative_provider_change_not_observed_demand; census_reallocation_not_population_change; plans_not_total_capacity','inputs_sha256':{str(x.relative_to(R)):sha(x) for x in [R/'history/edges_by_year.csv',R/'history/school_inventory_by_year.csv',R/'history/raw/NT2023_order65.pdf',R/'history/raw/NT2026_order79.pdf']}}
    (O/'HISTORY_CLAIM_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n')
    assert result['status']=='PASS'
    print(json.dumps({'status':'PASS','checks':len(checks),'summary':summary},ensure_ascii=False))

if __name__=='__main__':main()

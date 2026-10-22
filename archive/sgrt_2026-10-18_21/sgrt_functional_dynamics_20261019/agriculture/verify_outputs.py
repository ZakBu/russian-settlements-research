"""Read-back invariant checks, authored with module; not independent review."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd

root=Path(__file__).resolve().parent
c=pd.read_csv(root/'functional_municipal_crosswalk.csv',dtype={'municipality_code':str})
m=pd.read_csv(root/'municipal_legal_membership.csv',dtype={'municipality_code':str})
s=pd.read_parquet(root/'documented_scope_members.parquet')
w=pd.read_parquet(root/'agro_legal_witnesses_2016_2021.parquet')
ag=pd.read_parquet(root/'functional_agro_legal_aggregates.parquet')
raw=pd.read_parquet(root/'official_municipal_series.parquet')
checks=[]
def ck(name,truth):checks.append({'name':name,'pass':bool(truth)})
ck('crosswalk_scope_weights_sum1',np.allclose(c.groupby('scope').scope_population_share_in_municipality.sum(),1))
ck('complete_legal_membership_6plus5',m.groupby('municipality_code').size().to_dict()=={'80653410':6,'80653491':5})
ck('legal_missing_name_explicit',m.loc[~m.matched_axis,'name'].tolist()==['Кучуково-Маяк'])
ck('contemporaneous_boundary_equivalence_not_asserted',not c.contemporaneous_boundary_equivalence_proven.any())
ck('no_territorial_equivalence_asserted',not c.scope_equals_municipality.any())
ck('observed_people5594112225',s.groupby('scope').population_2021.sum().to_dict()=={'lower_school_1_9':559.,'lower_shared_school_health':411.,'upper_school_10_11_documented_fragment':2225.})
ck('only_known_points_in_witnesses',set(w.id)<=set(s.id))
ck('all_agro_witnesses_uralsk',set(w.name)=={'Уральск'})
ck('raw_unique_rows',not raw.duplicated().any())
low=raw[raw.oktmo.isin(['80653410','80653491'])]
ck('raw_lower31',len(low)==31)
ck('units_household_sown_hectares',set(low[low.indicator_code.eq('Y48007001')].indicator_unit)=={'Гектар'})
ck('units_household_livestock_heads',set(low[low.indicator_code.eq('Y48007002')].indicator_unit)=={'Голова'})
for year,expected in [(2016,6),(2021,4)]:
    z=w[w.year.eq(year)];ck(f'unique_entities_{year}',z.inn.nunique()==expected)
    ck(f'strict_entities_{year}',z.loc[z.strict_house_5km,'inn'].nunique()==2)
for _,row in ag.iterrows():
    ids=set(s[s.scope.eq(row.scope)].id)
    filt=w.year.eq(row.year)&w.id.isin(ids)&w.group.eq(row.group)
    filt &= w.strict_house_5km if row.quality_mode=='exact_code_strict_house5km' else w.section_consistent
    ck(f'count_recomputed_{row.scope}_{row.year}_{row.group}_{row.quality_mode}',w.loc[filt,'inn'].nunique()==row.unique_legal_entities)
ck('apparently_lost_not_present_anywhere2021',len(pd.read_csv(root/'missing2016_2021_targeted_followup.csv'))==0)
tr=pd.read_csv(root/'agro_identity_transition_2016_2021.csv',dtype={'inn':str})
ck('four_persist_two_unexplained',int((tr.agro_witness2016&tr.agro_witness2021).sum())==4 and int((tr.agro_witness2016&~tr.agro_witness2021).sum())==2)
ck('no_closure_claimed',not tr.physical_site_closure_observed.any())
law=(root/'law126z_uchaly_excerpt.txt').read_text()
for name in m.name: ck('legislation_named_place_'+name,name in law)
audit={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks_passed':sum(c['pass'] for c in checks),'checks_total':len(checks),'independence':'module_author_readback_not_external_review','checks':checks}
(root/'READBACK_VERIFICATION.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
assert audit['status']=='PASS';print(audit['status'],audit['checks_passed'],'/',audit['checks_total'])

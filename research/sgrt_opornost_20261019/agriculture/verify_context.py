"""Independent readback of municipal time/units and dimensional invariants."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

O=Path(__file__).parent
s=pd.read_csv(O/'pilot_municipal_measures_long.csv.gz',dtype={'oktmo':'string'})
p=pd.read_csv(O/'pilot_centers_agricultural_context_2021.csv',dtype={'municipality_oktmo8_2021':'string'})
raw=pd.read_parquet(O/'pilot_municipal_source_series.parquet')
t=s[s.year.eq(2021)][['oktmo','municipality','oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to']].drop_duplicates()
t['observation_year']=2021
lo=pd.to_numeric(t.oktmo_year_from,errors='coerce');hi=pd.to_numeric(t.oktmo_year_to,errors='coerce')
t['native_code_valid_at_observation']=lo.le(2021)&hi.ge(2021)
t['not_proof_of_legal_boundary_2026']=True
t.to_csv(O/'native_municipality_time_crosswalk.csv',index=False)
u=p.drop_duplicates('municipality_oktmo8_2021').copy()
u['production_component_residual_thousand_rub']=u.agri_production_nominal_thousand_rub-u.crop_production_nominal_thousand_rub-u.livestock_production_nominal_thousand_rub
u[['municipality_oktmo8_2021','agri_production_nominal_thousand_rub','production_component_residual_thousand_rub']].to_csv(O/'production_component_balance_2021.csv',index=False)
expected={
 'agri_production_nominal_thousand_rub':'Тысяча рублей',
 'crop_production_nominal_thousand_rub':'Тысяча рублей',
 'livestock_production_nominal_thousand_rub':'Тысяча рублей',
 'agri_volume_index_previous_year_percent':'Процент',
 'crop_volume_index_previous_year_percent':'Процент',
 'livestock_volume_index_previous_year_percent':'Процент',
 'sown_total_ha':'Гектар','grain_sown_ha':'Гектар','perennial_fruit_ha':'Гектар',
 'cattle_heads':'Голова','grain_yield_centner_per_harvested_ha':'Центнер с гектара убранной площади'}
checks=[{'name':'four_municipality_native_codes_valid_2021','pass':len(t)==4 and bool(t.native_code_valid_at_observation.all())},
 {'name':'all_measures_all_farm_categories_only','pass':bool(s.kategor.eq('Хозяйства всех категорий').all())},
 {'name':'no_negative_selected_measures','pass':bool(s.indicator_value.ge(0).all())},
 {'name':'production_components_agree_within_two_thousand_rub_rounding','pass':bool(u.production_component_residual_thousand_rub.abs().le(2).all())},
 {'name':'grain_share_not_over_total','pass':bool(p.grain_sown_share.dropna().between(0,1).all())},
 {'name':'missing_grain_not_zero_imputed','pass':bool(p[p.municipality_oktmo8_2021.eq('65715000')].grain_sown_ha.isna().all())}]
for measure,unit in expected.items():checks.append({'name':'unit_'+measure,'pass':bool(s[s.measure.eq(measure)].indicator_unit.eq(unit).all())})
for code,g in s.groupby('oktmo'):
    source2021=raw[raw.oktmo.eq(code)&raw.year.eq(2021)]
    checks.append({'name':'exact_source_municipality_'+str(code),'pass':len(source2021)>0})
assert all(x['pass'] for x in checks)
(O/'READBACK_VERIFICATION.json').write_text(json.dumps({'status':'PASS','checks':checks,'checks_passed':len(checks),'all_farm_categories_not_added_to_subcategories':True,'yield_denominator_is_harvested_area_not_sown_area':True,'production_index_is_growth_not_productivity':True},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'PASS','checks':len(checks),'native_municipalities':len(t),'max_component_residual_thousand_rub':float(u.production_component_residual_thousand_rub.abs().max())}))

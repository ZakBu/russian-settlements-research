"""Independent vectorized source recomputation; never imports the analysis code."""
from pathlib import Path
import pandas as pd, json
root=Path(__file__).resolve().parents[3]; b=root/'work/sources/research/ecommerce_settlement_20261024'; h=root/'research/ecommerce_cloud/dependency_20261026'
k='source_record_id_2021'
a=pd.read_parquet(b/'national/ozon_WB_comparison_main_target_experimental.parquet').set_index(k)
c=pd.read_parquet(b/'history_stage_20261024/centres/settlement_admin_context_main2021.parquet').set_index(k)
s=pd.read_csv(b/'settlement_role_stage_20261024/system/centre_system_demography.csv'); ids=set(s.loc[s.medium_primary2002,k])
r=pd.read_csv(h/'national_options_summary.csv'); detailed=pd.read_csv(root/'work/ecommerce_dependency_20261026/national_options_contexts.csv')
checks=0
for t in r.itertuples(index=False):
 v=str(t.vintage); par='administrative_centre_source_record_id_2021_'+v
 accepted=c['context_status_'+v].eq('accepted_administrative_parent_and_centre') & c[par].isin(ids)
 m=a.join(c[[par]],how='inner').loc[accepted]
 o=m.loc[m.index.to_series().ne(m[par]) & m.population_2021.gt(0)].copy()
 assert len(o)==t.periphery_inhabited_np_n; assert int(o.population_2021.sum())==t.periphery_population2021; checks+=2
 wbcol='WB_evidence_status'+('_sensitivity' if t.wb_rule!='baseline' else '')
 masks={'wb':o[wbcol].eq('positive'),'ozon':o[f'ozon_pickup_inferred_accepted_{t.ozon_identity_radius_km}km_count'].gt(0)}
 masks['either']=masks['wb']|masks['ozon']
 details=detailed.loc[detailed.vintage.eq(t.vintage)&detailed.ozon_identity_radius_km.eq(t.ozon_identity_radius_km)&detailed.wb_rule.eq(t.wb_rule)].set_index('centre_id')
 assert set(details.index)==ids; checks+=1
 for source,mask in masks.items():
  counts=o.loc[mask].groupby(par).size().reindex(details.index,fill_value=0)
  pops=o.loc[mask].groupby(par).population_2021.sum().reindex(details.index,fill_value=0)
  assert (counts==details[source+'_positive_np_n']).all()
  assert (pops==details[source+'_positive_population2021']).all()
  assert int(mask.sum())==getattr(t,source+'_positive_np_n')
  assert int(o.loc[mask,'population_2021'].sum())==getattr(t,source+'_positive_population2021')
  assert int((counts>0).sum())==getattr(t,source+'_contexts_positive_periphery_n')
  checks+=5
  central = a.reindex(details.index)
  cw=central[wbcol].eq('positive'); cz=central[f'ozon_pickup_inferred_accepted_{t.ozon_identity_radius_km}km_count'].gt(0)
  cm={'wb':cw,'ozon':cz,'either':cw|cz}[source]
  assert (cm==details[source+'_centre_positive']).all()
  assert int(cm.sum())==getattr(t,source+'_centres_positive_n')
  assert int(((counts>0)&cm).sum())==getattr(t,source+'_contexts_positive_centre_and_periphery_n')
  checks+=3
 unknown=o[wbcol].str.startswith('unknown')
 assert int(unknown.sum())==t.wb_unknown_np_n
 assert int(o.loc[unknown,'population_2021'].sum())==t.wb_unknown_population2021
 checks+=2
print(json.dumps({'source_configs':len(r),'all_config_checks':checks,'context_rows':len(detailed),'independent_source_recomputation':True,'max_discrepancy':0},ensure_ascii=False))

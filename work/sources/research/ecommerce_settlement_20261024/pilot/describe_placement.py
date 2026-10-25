"""Current WB positive-record coverage by prior trajectory; never an impact estimate.
Run: PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 <this file>
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
P=Path(__file__).resolve().parent
# Resolve inputs from this script, independently of the working directory.
S=P.parents[2] # work/sources
assert (S/'commerce_current.parquet').exists(),str(S)
base=pq.read_table(P/'inputs/data/population/ordinary_full3.parquet').to_pandas()
old=pq.read_table(S/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',columns=['id','source_record_id_2021','lat','lon']).to_pandas()
commerce=pq.read_table(S/'commerce_current.parquet',columns=['id','commerce_wb20261021_baseline_focus_count','commerce_wb20261021_baseline_focus_within5km_count']).to_pandas()
assert base['root'].is_unique
assert base['source_record_id_2021'].notna().all() and base['source_record_id_2021'].is_unique
assert commerce['id'].is_unique and old['id'].is_unique
bridge=old.loc[old.source_record_id_2021.notna()].copy()
# Ambiguous source IDs are held out rather than arbitrarily choosing an old row.
ambiguous=bridge.source_record_id_2021.duplicated(keep=False)
ambiguous_n=int(ambiguous.sum());bridge=bridge.loc[~ambiguous]
bridge=bridge.merge(commerce,on='id',how='left',validate='one_to_one')
x=base.merge(bridge,on='source_record_id_2021',how='left',validate='one_to_one')
pop=x.effective_population_2021
assert pop.notna().all() and (pop>=0).all()
x['size_2021']=pd.cut(pop,[-1,0,99,999,2999,9999,np.inf],labels=['0','1–99','100–999','1 000–2 999','3 000–9 999','10 000+'])
c='commerce_wb20261021_baseline_focus_count'
x['wb_status']=np.select([x[c].isna(),x[c]>0],['unknown_join','positive_record'],default='zero_accepted_records')
x['trend_2002_2021']=np.select([x.effective_population_2021>x.effective_population_2002,x.effective_population_2021<x.effective_population_2002],['growth','decline'],default='unchanged')
x['legacy_point_offset_km']=2*6371*np.arcsin(np.sqrt(np.clip(np.sin(np.radians(x.lat-x.accepted_latitude_2021)/2)**2+np.cos(np.radians(x.lat))*np.cos(np.radians(x.accepted_latitude_2021))*np.sin(np.radians(x.lon-x.accepted_longitude_2021)/2)**2,0,1)))
# A source-record bridge transfers a prior spatial linkage, not a fresh geocoding validation.
# Report how many positive joins would require rechecking after a change of representative point.
summary=[]
for (size,trend),g in x.groupby(['size_2021','trend_2002_2021'],observed=True):
 n=len(g);positive=int((g.wb_status=='positive_record').sum());zero=int((g.wb_status=='zero_accepted_records').sum());unknown=int((g.wb_status=='unknown_join').sum())
 summary.append({'size_2021':str(size),'trend_2002_2021':trend,'settlements':n,'wb_positive_record':positive,'zero_accepted_records_not_confirmed_absence':zero,'unknown_join':unknown,'positive_share_all_percent':100*positive/n})
out=pd.DataFrame(summary);out.to_csv(P/'placement_by_size_and_prior_trend.csv',index=False)
def describe_subset(g,field):
 positive=g.loc[g[field].fillna(0)>0]
 return {'settlements':len(g),'positive_record_settlements':len(positive),'positive_record_prior_trends':positive.trend_2002_2021.value_counts().to_dict()}
robustness={
 'focus5km_all':describe_subset(x,'commerce_wb20261021_baseline_focus_within5km_count'),
 'focus5km_inhabited2021_unchanged_point_within1km':describe_subset(x.loc[(pop>0)&(x.legacy_point_offset_km<=1)],'commerce_wb20261021_baseline_focus_within5km_count')}
x.loc[(x.wb_status=='positive_record')&((pop==0)|(x.legacy_point_offset_km>1)),['source_record_id_2021','settlement_name_2021','region_norm_2021','effective_population_2021','legacy_point_offset_km',c]].to_csv(P/'placement_linkage_review.csv',index=False)
meta={'population_release':'sgrt-census-population-20261022-v1','wb_snapshot':'2026-10-21','sample':'ordinary_full3: three own effective census counts and accepted representative points; boundary equivalence still unproven','strict_sample_rows':len(base),'old_bridge_ambiguous_rows_held_out':ambiguous_n,'counts':x.wb_status.value_counts().to_dict(),'positive_record_prior_trends':x.loc[x.wb_status=='positive_record'].trend_2002_2021.value_counts().to_dict(),'positive_record_point_offset_over_1km':int(((x.wb_status=='positive_record')&(x.legacy_point_offset_km>1)).sum()),'positive_record_point_offset_over_5km':int(((x.wb_status=='positive_record')&(x.legacy_point_offset_km>5)).sum()),'limits':['Current positive records, not all functioning PVZ or all accessible settlements.','Zero accepted records are not confirmed absence; unmatched rows are separate.','Prior population trajectory does not estimate effects of current WB, and may overlap early e-commerce adoption.','The old spatial linkage is transferred only by exact source_record_id2021, not by root or name.','This strict complete-series sample is selected and is not the entire settlement system.']}
assert sum(meta['counts'].values())==len(base)
meta['robustness']=robustness
assert out.settlements.sum()==len(base)
(P/'placement_description.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
print(json.dumps(meta,ensure_ascii=False,indent=2))
print(out.groupby('size_2021',sort=False)[['settlements','wb_positive_record','unknown_join']].sum().to_string())

"""Recompute fixed historical WB-profile context counts from individual cases."""
from pathlib import Path
import csv,json
R=Path(__file__).resolve().parents[4];H=R/'research/ecommerce_cloud/extension/history';O=Path(__file__).resolve().parent
with (H/'wb_profile_medium_contexts_2022_2024_5km.csv').open()as f:cases=list(csv.DictReader(f))
with (H/'wb_profile_medium_contexts_summary.csv').open()as f:summary=list(csv.DictReader(f))
key='source_record_id_2021';assert len(cases)==1273 and len({x[key]for x in cases})==1273
true=lambda x:x=='True'
for x in cases:
 assert true(x['centre_positive_both'])==(true(x['centre_positive0'])and true(x['centre_positive1']))
 assert true(x['other_footprint_expands'])==(int(x['other_positive1'])>int(x['other_positive0']))
 assert int(x['other_positive0'])<=int(x['other_members']) and int(x['other_positive1'])<=int(x['other_members'])
a=sum(true(x['centre_positive0'])for x in cases);b=sum(true(x['centre_positive1'])for x in cases);both=sum(true(x['centre_positive_both'])for x in cases);expanded=sum(true(x['centre_positive_both'])and int(x['other_positive1'])>int(x['other_positive0'])for x in cases)
z=next(s for s in summary if s['date0']=='2022-09-29'and s['date1']=='2024-03-11'and s['radius_km']=='5'and s['profile']=='raw_code_profile')
for field,val in [('centre_positive0',a),('centre_positive1',b),('centre_positive_both',both),('centre_positive_both_and_other_footprint_expands',expanded)]:assert int(z[field])==val
res={'case_rows':len(cases),'positive_20220929':a,'positive_20240311':b,'centre_positive_both':both,'retained_centre_and_other_footprint_expands':expanded,'among_retained_pct':100*expanded/both,'among_all_medium_pct':100*expanded/len(cases),'failures':0,'scope':'Individual saved cases verified against summary; not a new raw geographic linkage audit. Fixed raw code catalogue profile is not all functioning pickup points, functional centrality, openings or customer trips.'}
(O/'independent_wb_context_results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n');print(json.dumps(res,ensure_ascii=False,indent=2))

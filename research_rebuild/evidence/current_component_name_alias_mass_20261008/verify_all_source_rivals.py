import sys,json
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;R=O.parents[1];sys.path.insert(0,str(R/'evidence/native2010_remaining_county_rule_mass_20261008'))
from scan import cn
f=pd.read_csv(O/'accepted_native_source_witnesses.csv.gz',keep_default_na=False);rv=pd.read_csv(O/'all_regional_native_name_rivals.csv.gz',keep_default_na=False);ctx=pd.read_csv(R/'evidence/secondary_2010_county_context_application_20261007/all_selected_competitor_county_context.csv.gz',keep_default_na=False).set_index('source_record_id').to_dict('index');tcol='accepted_historical_component_source_record_id' if 'accepted_historical_component_source_record_id' in rv else 'target2010_source_record_id'
for z in f.to_dict('records'):
 g=rv[rv[tcol].eq(z['existing_historical_native_source_record_id'])&rv.year.eq(2010)].copy();g['cc']=g.apply(lambda r:cn(r.county_raw) or cn(ctx.get(r.source_record_id,{}).get('inferred_county_key','')),axis=1);ids=set(g[g.cc.eq(z['current_county_key'])&g.is_additive_settlement_record.eq(True)].source_record_id);assert ids=={z['new_native_source_record_id']},(z['name'],ids)
print('All accepted native2010 county rivals checked before credited/UF/type filters:',len(f))

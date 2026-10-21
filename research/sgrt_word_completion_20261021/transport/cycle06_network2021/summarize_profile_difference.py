"""Source-only size of declared static-direction changes relative to inherited 2026 rules."""
from pathlib import Path
import json
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent
rows=[];counts={'road_source_ways':0,'accepted_both_profiles':0,'accepted_both_direction_changed':0,'legacy_only_accepted_due_to_unsupported_or_conditional_direction':0}
for f in sorted((H/'profile_ledger').glob('*.parquet')):
 d=pd.read_parquet(f);counts['road_source_ways']+=len(d);ow=d.oneway_raw.fillna('');legacy=np.select([ow.eq('-1'),ow.isin(['yes','true','1'])|d.junction_raw.eq('roundabout')|(d.highway.isin(['motorway','motorway_link'])&~ow.isin(['no','0','false']))],[-1,1],default=0)
 common=d.accepted.fillna(False);change=common&d.static_direction.ne(legacy);counts['accepted_both_profiles']+=int(common.sum());counts['accepted_both_direction_changed']+=int(change.sum());z=d.loc[change,['way_id','highway','oneway_raw','oneway_motor_vehicle_raw','oneway_motorcar_raw','junction_raw','static_direction']].copy();z['legacy_direction']=legacy[change];z['difference']='explicit_car_oneway_precedence_or_explicit_no_over_roundabout_default';rows.append(z)
 for reasons in d.loc[~common,'exclusion_reasons_json']:
  v=json.loads(reasons)
  if v and all(x.startswith('unsupported_oneway_') or x in ['oneway:conditional','oneway:motor_vehicle:conditional','oneway:motorcar:conditional'] for x in v):counts['legacy_only_accepted_due_to_unsupported_or_conditional_direction']+=1
pd.concat(rows,ignore_index=True).to_csv(H/'source_only_static_direction_policy_changes.csv',index=False)
(H/'profile_difference_receipt.json').write_text(json.dumps({'status':'QUANTIFIED_DECLARED_PROFILE_CONFOUND_WITHOUT_MODEL_OUTPUT_READ',**counts,'not_a_year_only_treatment':'New2021 versus frozen2026 graph includes declared static direction corrections and deterministic snap tie choice; cannot attribute every difference only to chronology.'},indent=2)+'\n');print(counts)

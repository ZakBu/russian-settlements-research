import sys,json,math
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
O=Path(__file__).parent;s=load(30);d=pd.read_csv(O/'dated_count_native02_potential.csv.gz',dtype=str);rows=[];counts={};members={}
for x in s.by_id.index:members.setdefault(s.uf.find(x),[]).append(x)
for z in d.to_dict('records'):
 a,b=z['old_source_record_id'],z['current_source_record_id'];ra,rb=s.uf.find(a),s.uf.find(b);ya,yb=s.years[ra],s.years[rb];status='already_same_native_component' if ra==rb else 'actual_repeated_year' if ya&yb else 'immediate_full3_candidate' if ya|yb=={2002,2010,2021} else 'requires_native2010_binding';counts[status]=counts.get(status,0)+1
 if status in ['already_same_native_component','actual_repeated_year']:continue
 z.update(old_component_years=str(sorted(ya)),current_component_years=str(sorted(yb)),native2010_in_component=';'.join(x for r in {ra,rb} for x in members[r] if int(s.by_id.loc[x].census_year)==2010),current_admitted_point=json.dumps(s.point_rows.get(b,{}),ensure_ascii=False),old_admitted_point=json.dumps(s.point_rows.get(a,{}),ensure_ascii=False),status=status);rows.append(z)
f=pd.DataFrame(rows);f.to_csv(O/'actual30_remaining_native02_current_candidates.csv.gz',index=False);r={'baseline_stage':30,'status_counts':counts,'remaining_pairs':len(f),'immediate_full3_count':int(f.status.eq('immediate_full3_candidate').sum()) if len(f) else 0,'immediate_old2002_population_potential':int(pd.to_numeric(f[f.status.eq('immediate_full3_candidate')].drop_duplicates('old_source_record_id').native2002_population).sum()) if len(f) else 0,'remaining_old2002_population_potential':int(pd.to_numeric(f.drop_duplicates('old_source_record_id').native2002_population).sum()) if len(f) else 0,'status':'Actual30 component screen only; date/rawownQcode/native county and all competitors validation pending'};(O/'actual30_potential_counts.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False));print(f.assign(p=pd.to_numeric(f.native2002_population)).sort_values('p',ascending=False)[['old_name','current_name','region','old_county','current_county','native2002_population','native2021_population','status']].head(40).to_string(index=False))

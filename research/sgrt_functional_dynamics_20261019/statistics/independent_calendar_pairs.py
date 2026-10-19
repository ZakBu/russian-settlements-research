#!/usr/bin/env python3
"""All annual and benchmark point transitions from independent annual stocks."""
from pathlib import Path
import json,hashlib
import pandas as pd
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent/'wave2'
def main():
 a=pd.read_csv(R/'economy/pinned_calendar/annual_and_benchmark_transitions.csv');s={y:pd.read_parquet(O/f'calendar_{y}.parquet').set_index('id') for y in range(2011,2026)};checks=[];rows=[]
 for r in a.itertuples(index=False):
  col='diversity' if r.feature=='direct_consumer_function_diversity' else r.feature.removesuffix('_legal_entities')
  x=s[r.from_year][col].gt(0);y=s[r.to_year][col].gt(0).reindex(x.index);vals={'n':len(x),'observed_from':int(x.sum()),'observed_to':int(y.sum()),'unobserved_both':int((~x&~y).sum()),'witness_lost':int((x&~y).sum()),'witness_gained':int((~x&y).sum()),'witness_retained':int((x&y).sum()),'net_change':int(y.sum()-x.sum())}
  for k,v in vals.items():checks.append({'name':f'{r.from_year}_{r.to_year}_{r.feature}_{k}','pass':v==getattr(r,k)})
  rows.append(dict(from_year=r.from_year,to_year=r.to_year,feature=r.feature,**vals))
 pd.DataFrame(rows).to_csv(O/'independent_annual_benchmark_transitions.csv',index=False)
 audit={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','n_checks':len(checks),'checks':checks,'source_author_sha256':hashlib.sha256((R/'economy/pinned_calendar/annual_and_benchmark_transitions.csv').read_bytes()).hexdigest(),'independent_year_tables_sha256':{str(y):hashlib.sha256((O/f'calendar_{y}.parquet').read_bytes()).hexdigest() for y in s},'interpretation':'Transitions in point-level legal witnesses. Not legal births/deaths, physical opening/closure or measured functional capture.'};(O/'CALENDAR_PAIR_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit['status'],len(checks));assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

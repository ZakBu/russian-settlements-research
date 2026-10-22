#!/usr/bin/env python3
"""Check the explicitly selected report example without treating it as validation."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;N=H.parent;O=H/'independent_sources/illustrative_case';O.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=N/'report_tables/illustrative_cases.csv';q=N/'screening/support_point_profiles.parquet';before={str(x):sha(x) for x in [p,q]};case=pd.read_csv(p);cols=[c for c in case if c!='selection_scope'];source=pd.read_parquet(q,columns=cols).set_index('id').reindex(case.id);checks=[]
 for c in cols:
  if c=='id':continue
  x=case[c].reset_index(drop=True);y=source[c].reset_index(drop=True);good=np.allclose(x,y,equal_nan=True,rtol=0,atol=0) if pd.api.types.is_numeric_dtype(x) else x.fillna('').eq(y.fillna('')).all();checks.append({'name':'source_value_'+c,'pass':bool(good)})
 checks.append({'name':'selected_not_blind_label','pass':bool(case.selection_scope.eq('selected_illustrative_case_not_blind_validation').all())});checks.append({'name':'inputs_stable','pass':all(sha(Path(x))==v for x,v in before.items())});result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'meaning':'Exact selected-example arithmetic, not independent population-representative validation or evidence of flows.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks');assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

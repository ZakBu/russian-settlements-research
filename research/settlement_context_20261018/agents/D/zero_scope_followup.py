#!/usr/bin/env python3
"""Append-only follow-up audit, no edits to existing audit receipt."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
P=ROOT/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
x=pd.read_csv(P,dtype=str,keep_default_na=False);p={y:pd.to_numeric(x[f'population_{y}'],errors='coerce') for y in [2002,2010,2021]}
q=x.population_value_quality_2010.replace('','<MISSING>')
rows=[]
for quality,idx in q.groupby(q).groups.items():
 mask=x.index.isin(idx)
 for cond,name in [(np.ones(len(x),dtype=bool),'all'),(p[2002]>0,'positive_own2002'),(p[2002]==0,'zero_own2002')]:
  m=mask&cond
  for a,b,event in [(2002,2010,'positive_to_zero'),(2010,2021,'positive_to_zero'),(2002,2010,'zero_to_positive'),(2010,2021,'zero_to_positive')]:
   risk=m&(p[a]>0 if event=='positive_to_zero' else p[a]==0)&p[b].notna()
   hit=risk&(p[b]==0 if event=='positive_to_zero' else p[b]>0)
   n=int(risk.sum());k=int(hit.sum())
   rows.append({'quality2010':quality,'condition_2002':name,'interval':f'{a}-{b}','event':event,'n_stratum':int(m.sum()),'risk':n,'events':k,'proportion':k/n if n else None,'interval_status':'descriptive finite-panel proportion; no independence-based CI'})
pd.DataFrame(rows).to_csv(OUT/'evidence/zero_transitions_quality_own2002.csv',index=False)
# Explicit three-way patterns; every population count numeric, so no missing recode.
patterns=pd.DataFrame({'quality2010':q,'positive2002':p[2002]>0,'positive2010':p[2010]>0,'positive2021':p[2021]>0})
patterns.groupby(list(patterns.columns),dropna=False).size().reset_index(name='n').to_csv(OUT/'evidence/zero_three_way_patterns.csv',index=False)
ep=ROOT/'publication/stage71/ordinary_population_scope_equivalence_exclusions.csv';e=pd.read_csv(ep,dtype=str,keep_default_na=False)
uidset=set(e.from_historic_part_UID)|set(e.to_joint_report_UID)
sourcecols=['source_record_id_2002','source_record_id_2010','source_record_id_2021','population_source_record_id_2010','original_source_record_id_2010']
matched=x[sourcecols].isin(uidset).any(axis=1)
# Exact mask, linked by source UID; unknown comparability is not exclusion.
pd.DataFrame({'entity_uid':x.entity_uid,'exclude_explicit_joint_scope':matched}).to_csv(OUT/'evidence/explicit_joint_scope_mask.csv.gz',index=False)
report={'input_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'scope_exclusion_sha256':hashlib.sha256(ep.read_bytes()).hexdigest(),'scope_exclusion_rows':len(e),'distinct_scopes':int(e.scope_id.nunique()),'unique_source_UIDs':len(uidset),'join_columns':sourcecols,'matched_panel_rows':int(matched.sum()),'policy':'No panel row removed by this explicit scope-exclusion ledger. Universal unknown boundary comparability is not a filter. Coordinate drift sensitivity is separate from source-scope comparability.'}
(OUT/'evidence/explicit_scope_join.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(pd.DataFrame(rows).query("condition_2002 == 'all'").to_string(index=False));print(json.dumps(report,ensure_ascii=False))

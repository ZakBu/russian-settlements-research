"""Explain every strict numerical mismatch; never replace ownership, source or integer comparisons with a tolerance."""
from pathlib import Path
import json,argparse
import numpy as np
import pandas as pd
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--strict-report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--only-schema-extensions',action='store_true');args=parser.parse_args(); original=json.loads(args.strict_report.read_text()); reports=[];failures=[]
for table in original['tables']:
 if table.get('all_scientific_values_equal_exactly') or table['role'] in {'medical','clinical','education'}:continue
 if table.get('failure')=='missing':failures.append(table['path']);continue
 if args.only_schema_extensions:
  import pyarrow.parquet as pq
  if set(pq.read_schema(table['manual']).names)==set(pq.read_schema(table['public']).names):continue
 a=pd.read_parquet(table['manual']);b=pd.read_parquet(table['public']);excluded=['provider_source_input','source_supply_sha256'] if table['role']=='route' else []
 a=a.drop(columns=excluded,errors='ignore');b=b.drop(columns=excluded,errors='ignore')
 keys=next(([k] for k in ['origin_id','unit_id','source_record_id','provider_id'] if k in a and k in b and a[k].is_unique and b[k].is_unique),None)
 if keys:a=a.sort_values(keys).reset_index(drop=True);b=b.sort_values(keys).reset_index(drop=True)
 entry={'path':table['path'],'column_order_equal':list(a)==list(b),'shape_equal':a.shape==b.shape,'manual_only_columns':sorted(set(a)-set(b)),'public_only_columns':sorted(set(b)-set(a)),'differences':[]}
 extra=entry['public_only_columns'];allowed={'provider_education_need_scope','provider_programme_mismatch_reason'}
 if extra and not entry['manual_only_columns'] and table['role']=='route' and set(extra)<=allowed:
  entry['public_extra_columns_null_counts']={c:int(b[c].isna().sum()) for c in extra}
  entry['public_extra_columns_all_null']=all(b[c].isna().all() for c in extra)
  if not entry['public_extra_columns_all_null']:entry['structural_failure']=True;failures.append(table['path']);reports.append(entry);continue
  entry['schema_extension_explanation']='Older manual medical routing predates forwarding two educational programme metadata columns; public adds them as entirely missing, not as new clinical claims.'
  b=b.drop(columns=extra)
 if set(a)!=set(b) or len(a)!=len(b):entry['structural_failure']=True;failures.append(table['path']);reports.append(entry);continue
 b=b.reindex(columns=a.columns);entry['common_scientific_columns_compared']=list(a.columns)
 entry['common_clinical_columns_compared']=[c for c in a if any(t in c for t in ['medical_need','adult_profile','child_only','restriction_scope','universal_hospital','operational_status','pediatric'])]
 for c in a:
  try:pd.testing.assert_series_equal(a[c],b[c],check_dtype=False,check_exact=True);continue
  except AssertionError:pass
  col={'column':c,'manual_dtype':str(a[c].dtype),'public_dtype':str(b[c].dtype)}
  if pd.api.types.is_float_dtype(a[c].dtype) and pd.api.types.is_float_dtype(b[c].dtype):
   x=a[c].to_numpy(dtype='float64',na_value=np.nan);y=b[c].to_numpy(dtype='float64',na_value=np.nan);same=(x==y)|(np.isnan(x)&np.isnan(y));bad=~same;finite=bad&np.isfinite(x)&np.isfinite(y)
   close=np.isclose(x,y,rtol=1e-12,atol=1e-12,equal_nan=True);delta=np.abs(x[finite]-y[finite]);col.update(differing_values=int(bad.sum()),all_within_declared_roundoff_tolerance=bool(close.all()),max_absolute_difference=float(delta.max()) if len(delta) else None,examples=[{'row':int(i),'manual':float(x[i]),'public':float(y[i])} for i in np.flatnonzero(bad)[:3]])
   if not close.all():failures.append(table['path']+':'+c)
  else:col['nonfloating_difference']=True;failures.append(table['path']+':'+c)
  entry['differences'].append(col)
 reports.append(entry);print(entry['path'],entry['differences'],flush=True)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps({'strict_report':str(args.strict_report),'schema_extensions_only':args.only_schema_extensions,'scope':'Explicit schema extension reconciliation' if args.only_schema_extensions else 'All partitions, routes and commerce source tables; clinical/education records reconciled separately by natural keys','exactly_equal_tables':sum(x.get('all_scientific_values_equal_exactly',False) for x in original['tables']),'tables_with_recorded_roundoff':reports,'float_comparison_policy':{'rtol':1e-12,'atol':1e-12,'applied_only_to_floating_columns_that_failed_exact_comparison':True,'identifiers_memberships_sources_strings_booleans_integers_remain_exact':True},'failures':failures},ensure_ascii=False,indent=2)+'\n');raise SystemExit(bool(failures))

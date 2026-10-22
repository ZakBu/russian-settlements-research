"""Versioned semantic correction: unknown nonadditive metropolitan members prevent whole completeness.
Reuses accepted additive arithmetic, never changes population values, memberships, Mi or rural sums.
"""
import argparse,hashlib,json,os
from pathlib import Path
import pandas as pd
CTX={'ctx:RU-FED-MOW','ctx:RU-FED-SPB'}
YEARS=(2002,2010,2021)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args();src=Path(a.source);out=Path(a.output)
 assert not out.exists();r=json.loads((src/'receipt.json').read_text());u=pd.read_parquet(src/'normalized_units.parquet');m=pd.read_parquet(src/'memberships_scoped.parquet');n=pd.read_parquet(src/'effective_population_source_view.parquet',columns=['id','population_2002','population_2010','population_2021']).set_index('id');before=u.copy();idx=u.set_index('unit_id').index
 cm=m[m.id.isin(CTX)].copy();assert set(cm.id)<=CTX
 records=[];allowed=[]
 for y in YEARS:
  unknown=cm[cm.id.map(n[f'population_{y}'].isna())].copy();unknown['focal']=unknown.id.eq(unknown.unit_id.map(u.set_index('unit_id').core_id))
  for label,sub in [('all',unknown),('focal',unknown[unknown.focal]),('nonfocal',unknown[~unknown.focal])]:
   col=f'unknown_nonadditive_metropolitan_{label}_population_slots_{y}';u[col]=u.unit_id.map(sub.groupby('unit_id').size()).fillna(0).astype(int)
  mask=u[f'unknown_nonadditive_metropolitan_all_population_slots_{y}'].gt(0)
  for col in [f'system_population_complete_{y}',f'system_population_exact_primary_supported_{y}',f'classification_population_exact_primary_supported_{y}']:
   allowed.append(col);changed=mask & u[col].fillna(False).astype(bool)
   for _,row in u.loc[changed,['unit_id','name','core_id']].iterrows():records.append({**row.to_dict(),'column':col,'old':True,'new':False,'reason':'unknown_own_population_of_nonadditive_metropolitan_member'})
   u.loc[mask,col]=False
 for col in before.columns:
  if col not in allowed:pd.testing.assert_series_equal(before[col],u[col],check_exact=True)
 out.mkdir(parents=True);u.to_parquet(out/'normalized_units.parquet',index=False);pd.DataFrame(records,columns=['unit_id','name','core_id','column','old','new','reason']).to_csv(out/'semantic_changes.csv',index=False)
 for f in ['raw_units_scoped.parquet','memberships_scoped.parquet','effective_population_source_view.parquet','applied_primary2010_ids.csv']:
  if (src/f).exists():os.link(src/f,out/f)
 r.update(status='COMPUTED_NORMALIZATION_V3_ANY_UNKNOWN_METROPOLITAN_MEMBER_PENDING_INDEPENDENT_ADMISSION',normalized_units_sha256=sha(out/'normalized_units.parquet'),prior_normalization_receipt_path=str((src/'receipt.json').resolve()),prior_normalization_receipt_sha256=sha(src/'receipt.json'),prior_normalized_units_sha256=sha(src/'normalized_units.parquet'),semantic_repair_code_sha256=sha(__file__),semantic_repair_scope='whole_completeness_any_unknown_nonadditive_metropolitan_member',n_changed_boolean_cells=len(records),n_changed_units=len(set(x['unit_id'] for x in records)),population_values_memberships_Mi_rural_sums_changed=False,code_sha256=sha(__file__))
 r['files']={p.name:sha(p) for p in out.iterdir() if p.is_file()};(out/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({'n_units':len(u),'n_changed_boolean_cells':len(records),'n_changed_units':r['n_changed_units'],'units_sha256':r['normalized_units_sha256']},ensure_ascii=False))
if __name__=='__main__':main()

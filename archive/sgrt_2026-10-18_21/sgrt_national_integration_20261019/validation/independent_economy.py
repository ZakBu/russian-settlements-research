#!/usr/bin/env python3
"""Independent native financial aggregation and all pinned annual field joins.

No source-owner module imports. Prior independent raw fifteen-year stock and
cohort audit remains separate; this audit tests newly added financial fields.
"""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/economy';O.mkdir(parents=True,exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()
def codes(s):
 s=s.astype('string').str.strip();return s.where(s.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
def main():
 paths=[B/'anchor_research_20261019/data/point_axis.parquet',N/'economy/economy_features.parquet',B/'functional_dynamics_20261019/economy/pinned_calendar/point_exact_code_witnesses_2011_2025.parquet']
 axis=pd.read_parquet(paths[0]);e=pd.read_parquet(paths[1]);before={str(p):sha(p) for p in paths};checks=[];balances=[]
 def ck(n,v,d=None):checks.append({'name':n,'pass':bool(v),'detail':d})
 ck('full_unique_axis_142570',len(e)==142570 and e.id.is_unique and e.id.equals(axis.id));e=e.set_index('id').reindex(axis.id)
 annual=pq.ParquetFile(paths[2]);metrics=[c for c in annual.schema_arrow.names if c not in ['id','name','region','lat','lon','population_2021','year','quality_mode']]
 for y in range(2011,2026):
  d=pq.read_table(paths[2],columns=['id']+metrics,filters=[('year','=',y)]).to_pandas().set_index('id').reindex(axis.id)
  for c in metrics:
   try:pd.testing.assert_series_equal(d[c],e[f'econ_native_{y}_{c}'],check_names=False,check_dtype=False,check_exact=True);ok=True
   except AssertionError:ok=False
   ck(f'annual_{y}_{c}',ok)
  ck(f'annual_{y}_positive_flags',(d.legal_entities.gt(0).to_numpy()==e[f'econ_native_{y}_has_accepted_legal_witness'].to_numpy()).all() and (d.direct_consumer_function_diversity.gt(0).to_numpy()==e[f'econ_native_{y}_has_accepted_direct_service_witness'].to_numpy()).all())
 lookup=pd.Series(axis.id.to_numpy(),index=codes(axis.oktmo_2021));fields={'line_1150':'fixed_assets','line_1600':'total_assets','line_2110':'revenue','line_2400':'net_profit'}
 for y in [2016,2021]:
  p=B/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{y}_selected.parquet';before[str(p)]=sha(p);counts={k:pd.Series(0,index=axis.id,dtype='int64') for k in fields};sums={k:pd.Series(0.,index=axis.id) for k in fields};consistent=pd.Series(0,index=axis.id,dtype='int64');legal=pd.Series(0,index=axis.id,dtype='int64');scanned=0
  columns=['inn','oktmo','eligible','filed','articulated','outlier']+list(fields)
  for batch in pq.ParquetFile(p).iter_batches(batch_size=125000,columns=columns):
   d=batch.to_pandas();scanned+=len(d);d['code']=codes(d.oktmo);d['uid']=d.code.map(lookup);accepted=d.inn.str.fullmatch(r'\d{10}',na=False)&d.uid.notna()&~d.code.str[:2].isin(['45','40']);good=accepted&d.eligible.eq(1)&d.filed.eq(1)&d.articulated.eq(1)&d.outlier.eq(0);legal=legal.add(d.loc[accepted].groupby('uid').size(),fill_value=0);consistent=consistent.add(d.loc[good].groupby('uid').size(),fill_value=0)
   for field in fields:
    amount=pd.to_numeric(d[field],errors='coerce');take=good&np.isfinite(amount)
    if field!='line_2400':take &= amount.ge(0)
    tmp=pd.DataFrame({'uid':d.loc[take,'uid'],'amount':amount[take]});g=tmp.groupby('uid').amount;counts[field]=counts[field].add(g.size(),fill_value=0);sums[field]=sums[field].add(g.sum(),fill_value=0)
  legal=legal.reindex(axis.id);consistent=consistent.reindex(axis.id)
  ck(f'finance_native_attached_legal_stock_{y}',np.array_equal(legal.to_numpy(),e[f'econ_native_{y}_legal_entities'].to_numpy()));ck(f'finance_native_consistent_count_{y}',np.array_equal(consistent.to_numpy(),e[f'econ_native_{y}_financial_consistent_filing_entities'].to_numpy()))
  for field,label in fields.items():
   stem=f'econ_native_{y}_legal_registered_{label}';n=counts[field].reindex(axis.id);total=sums[field].reindex(axis.id).mask(n.eq(0));actual=e[stem+'_thousand_rub'];ck(f'{stem}_reporting_count',np.array_equal(n.to_numpy(),e[stem+'_reporting_entities'].to_numpy()));ck(f'{stem}_sum',np.allclose(total,actual,rtol=1e-12,atol=1e-5,equal_nan=True));ck(f'{stem}_known',np.array_equal(n.gt(0).to_numpy(),e[stem+'_known'].to_numpy()));expected=n.div(legal.where(legal.gt(0))).reindex(axis.id);ck(f'{stem}_reporting_share',np.allclose(expected,e[stem+'_reporting_share_of_attached_entities'],rtol=1e-12,atol=1e-12,equal_nan=True));balances.append({'year':y,'field':field,'rows_scanned':scanned,'attached_legal_entities':int(legal.sum()),'usable_reports':int(n.sum()),'UID_with_usable_reports':int(n.gt(0).sum()),'known_finite_zeros':int(total.eq(0).sum()),'unknown_UID':int(total.isna().sum()),'nominal_thousand_rub_sum':float(total.sum())})
  print(json.dumps({'year':y,'rows_scanned':scanned,'native_financial_checks_complete':True}),flush=True)
 ck('inputs_unchanged',all(sha(Path(p))==v for p,v in before.items()));pd.DataFrame(balances).to_csv(O/'native_financial_balances.csv',index=False)
 result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'scope':'All national native annual joins and new native financial raw aggregates. Legacy geographic alternatives and conditional code training are explicitly outside this new financial audit, retained in prior audits. Financial values are nominal thousand RUB legal-address reporting, not jobs, physical sites, or actual SGRT flows.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks',flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

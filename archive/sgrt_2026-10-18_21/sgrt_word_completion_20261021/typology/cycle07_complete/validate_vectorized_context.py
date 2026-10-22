"""All actual-unit context cells vs independently admitted scalar source reference.
Reads the wide reference in small batches; no classifier or demographic results are fitted.
"""
import argparse,gc,hashlib,json,math,time
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from vectorized_context_cache import ContextCache

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal(a,b):
 if pd.isna(a) or pd.isna(b):return bool(pd.isna(a) and pd.isna(b))
 if isinstance(a,(bool,np.bool_)) or isinstance(b,(bool,np.bool_)):return type(a) in (bool,np.bool_) and type(b) in (bool,np.bool_) and bool(a)==bool(b)
 if isinstance(a,(int,float,np.number)) and isinstance(b,(int,float,np.number)):return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-12)
 return a==b

def main():
 p=argparse.ArgumentParser();p.add_argument('--contract',required=True);p.add_argument('--normalized',required=True);p.add_argument('--source-admission',required=True);p.add_argument('--output',required=True);a=p.parse_args();cp=Path(a.contract);c=json.loads(cp.read_text());d=Path(a.normalized);reviewp=Path(a.source_admission);review=json.loads(reviewp.read_text());assert review['all_checks_passed'] and str(review['status']).startswith('ACCEPTED') and review['accepted_units_sha256']==sha(d/'normalized_units.parquet');out=Path(a.output);assert not out.exists();start=time.monotonic()
 n=pd.read_parquet(d/'effective_population_source_view.parquet').set_index('id',drop=False);cache=ContextCache(n,c);m=pd.read_parquet(d/'memberships_scoped.parquet',columns=['unit_id','id']);members=m.groupby('unit_id',sort=False).id.agg(list).to_dict();del m;gc.collect()
 columns=['unit_id','core_id','central_object_ids_json'];prefixes=[w['output_column'] for w in c['context_projection']]+[w['output_prefix'] for w in c['context_numeric_projection']];allcols=pq.read_schema(d/'normalized_units.parquet').names;contextcols=[col for col in allcols if any(col==x or col.startswith(x+'_') for x in prefixes)];columns+=contextcols;bad=[];nunits=ncells=0
 for batch in pq.ParquetFile(d/'normalized_units.parquet').iter_batches(batch_size=256,columns=columns):
  for r in batch.to_pandas().to_dict('records'):
   core=json.loads(r['central_object_ids_json']);ids=members[r['unit_id']];raw=n.loc[ids];rural=raw.loc[raw._population_axis_row.fillna(False)&~raw.index.isin(core)&raw.accepted_statistical_rural_role2021.eq(True).fillna(False)].index.tolist();actual=cache.apply(core,rural,ids);assert set(actual)==set(contextcols)
   for col,v in actual.items():
    ncells+=1
    if not equal(r[col],v):bad.append({'unit_id':r['unit_id'],'column':col,'reference':repr(r[col]),'fast':repr(v)})
   nunits+=1
   if len(bad)>1000:raise ValueError('More than1000mismatches; refuse full run')
 out.mkdir(parents=True);pd.DataFrame(bad).to_csv(out/'differences.csv',index=False);receipt={'status':'COMPUTED_ALL_ACTUAL_CONTEXT_CELL_EQUIVALENCE_CHECK','n_units':nunits,'n_fields':len(contextcols),'n_compared_cells':ncells,'n_differences':len(bad),'all_cells_match':not bad,'relative_numeric_tolerance':1e-12,'absolute_numeric_tolerance':1e-12,'source_reference_units_sha256':sha(d/'normalized_units.parquet'),'source_admission_path':str(reviewp.resolve()),'source_admission_sha256':sha(reviewp),'contract_sha256':sha(cp),'fast_context_code_sha256':sha(Path(__file__).with_name('vectorized_context_cache.py')),'validation_code_sha256':sha(__file__),'source_view_sha256':sha(d/'effective_population_source_view.parquet'),'seconds':time.monotonic()-start,'peak_rss_kb':__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss,'not_independent_of_fast_implementation_author':True,'reference_scalar_result_has_separate_independent_source_admission':True};(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt))
 if bad:raise ValueError('Fast context mismatch')
if __name__=='__main__':main()

"""Source-bound full actual060 cell comparison; batched to bound memory."""
import argparse,json,hashlib,time,resource
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from normalize_unit_populations_source477_v7_fast import aggregate
from validate_vectorized_context import equal

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',required=True);ap.add_argument('--normalized',required=True);ap.add_argument('--admission',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();out=Path(a.output);assert not out.exists();d=Path(a.normalized);c=json.loads(Path(a.contract).read_text());rp=Path(a.admission);review=json.loads(rp.read_text());assert review['all_checks_passed'] and review['accepted_units_sha256']==sha(d/'normalized_units.parquet')
 start=time.monotonic();n=pd.read_parquet(d/'effective_population_source_view.parquet');u=pd.read_parquet(d/'raw_units_scoped.parquet');m=pd.read_parquet(d/'memberships_scoped.parquet');u=u.set_index('unit_id',drop=False);bad=[];ncells=nunits=0
 for batch in pq.ParquetFile(d/'normalized_units.parquet').iter_batches(batch_size=512):
  ref=batch.to_pandas().set_index('unit_id',drop=False);ids=ref.index;actual=aggregate(u.loc[ids].reset_index(drop=True),m.loc[m.unit_id.isin(ids)],n,c).set_index('unit_id',drop=False);assert set(actual.columns)==set(ref.columns)
  for col in ref:
   l=ref[col];r=actual[col];ok=(l.eq(r)|(l.isna()&r.isna())).fillna(False)
   for ident in ok.index[~ok]:
    if not equal(l.loc[ident],r.loc[ident]):bad.append({'unit_id':ident,'column':col,'expected':repr(l.loc[ident]),'actual':repr(r.loc[ident])})
  ncells+=ref.size;nunits+=len(ref)
  assert len(bad)<100,'Actual mismatch'
 out.mkdir(parents=True);pd.DataFrame(bad).to_csv(out/'differences.csv',index=False);r={'status':'COMPUTED_V7_ALL_ACTUAL060_CELL_EQUIVALENCE','n_units':nunits,'n_compared_cells':ncells,'n_differences':len(bad),'all_cells_match':not bad,'reference_units_sha256':sha(d/'normalized_units.parquet'),'source_sha256':sha(d/'effective_population_source_view.parquet'),'reference_admission_sha256':sha(rp),'v7_code_sha256':sha(Path(__file__).with_name('normalize_unit_populations_source477_v7_fast.py')),'validation_code_sha256':sha(__file__),'contract_sha256':sha(a.contract),'seconds':time.monotonic()-start,'peak_rss_kb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'author_equivalence_not_independent_review':True};(out/'receipt.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));assert not bad
if __name__=='__main__':main()

"""Finite actual-source singleton/nonfocal-context counterexamples, V6 vs V7."""
import hashlib,json
from pathlib import Path
import pandas as pd
from normalize_unit_populations_source477_v6_fast import aggregate as old
from normalize_unit_populations_source477_v7_fast import aggregate as new
from validate_vectorized_context import equal
B=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=B/'v7_context_counterexamples_v1';assert not out.exists();d=B/'normalized_source477_v1/cap060_supported_end_forest';n=pd.read_parquet(d/'effective_population_source_view.parquet');u=pd.read_parquet(d/'raw_units_scoped.parquet');c=json.loads((B/'contracts_source477_v1/normalize_cap060_supported_end_forest.json').read_text());c['context_projection']=[];c['context_numeric_projection']=[]
 ordinary=n.loc[n._population_axis_row.eq(True).fillna(False),'id'].iloc[0];ctx=['ctx:RU-FED-MOW','ctx:RU-FED-SPB'];template=u.loc[u.kind.eq('functional_union')].iloc[0].to_dict();records=[];checks=0
 for j,(core,ids,kind) in enumerate([(ordinary,[ordinary],'atomic_residual'),(ctx[0],[ctx[0]],'external_context_anchor'),(ctx[1],[ctx[1]],'external_context_anchor'),(ordinary,[ordinary,ctx[0]],'functional_union'),(ordinary,[ordinary,ctx[1]],'functional_union'),(ordinary,[ordinary,*ctx],'functional_union'),(ctx[0],[ordinary,*ctx],'functional_union'),(ctx[1],[ordinary,*ctx],'functional_union')]):
  r={**template,'unit_id':str(j),'core_id':core,'kind':kind,'central_object_ids_json':json.dumps([core]),'central_object_definition':'own_atomic' if kind=='atomic_residual' else 'one_focal_core'};units=pd.DataFrame([r]);m=pd.DataFrame({'unit_id':[str(j)]*len(ids),'id':ids});a=old(units,m,n,c).iloc[0];b=new(units,m,n,c).iloc[0];bad=[k for k in a.index if not equal(a[k],b[k])];assert not bad,bad;checks+=len(a);records.append({'case':j,'core':core,'members':ids,'n_fields':len(a),'n_differences':len(bad)})
 out.mkdir();receipt={'status':'COMPUTED_FINITE_V7_V6_ACTUAL_SOURCE_CTX_COUNTEREXAMPLES','n_cases':len(records),'n_compared_fields':checks,'n_differences':0,'cases':records,'v7_sha256':sha(B/'normalize_unit_populations_source477_v7_fast.py'),'v6_sha256':sha(B/'normalize_unit_populations_source477_v6_fast.py'),'source_sha256':sha(d/'effective_population_source_view.parquet'),'code_sha256':sha(__file__),'not_independent_author_comparison':True};(out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()

"""Byte-canonical V6/V7 serialization of admitted compact20-column source.
Values, row order and types are checked exactly; no scientific source change.
"""
import json,hashlib
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
B=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=B/'population_only_sensitivity_source477_v1/population_only_nodes.parquet';out=B/'population_only_sensitivity_runtime_view_v1';assert not out.exists();base=pd.read_parquet(p);cols=['id','_population_axis_row','accepted_statistical_rural_role2021']+[f'{pre}_{y}' for y in (2002,2010,2021) for pre in ('population','population_value_quality')]+[x for x in ('source_record_id_2021','name','region') if x in base];n=base[cols].copy();n['population2010_effective_source_uid']=base['population2010_effective_source_uid'];n['population2010_prior_source_uid']=n.population2010_effective_source_uid;n['population2010_effective_source_admission_sha256']=pd.NA;n['population_2010_prior']=n.population_2010;n['population_value_quality_2010_prior']=n.population_value_quality_2010
 for k in ('primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed'):n[k]=False
 n=n.set_index('id',drop=False);v=base.set_index('id',drop=False)
 for col in ['population_2010','population_value_quality_2010','population_2010_prior','population_value_quality_2010_prior','population2010_prior_source_uid','population2010_effective_source_uid','population2010_effective_source_admission_sha256','primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed']:n[col]=v.loc[n.index,col]
 n=n.reset_index(drop=True);pd.testing.assert_frame_equal(n,base,check_exact=True,check_dtype=True);out.mkdir();target=out/'runtime_source_view.parquet';n.to_parquet(target,index=False);pd.testing.assert_frame_equal(pd.read_parquet(target),base,check_exact=True,check_dtype=True)
 a=pq.read_table(p);b=pq.read_table(target);assert a.equals(b,check_metadata=False);receipt={'status':'COMPUTED_EXACT20COLUMN_RUNTIME_SERIALIZATION','input_sha256':sha(p),'runtime_sha256':sha(target),'n_rows':len(base),'n_columns':len(base.columns),'all_values_nulls_order_types_equal':True,'arrow_data_equal_excluding_serialization_metadata':True,'scientific_source_changed':False,'purpose':'all31 V7 outputs hardlink only after asserting exact generated parquet bytes','code_sha256':sha(__file__)};(out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()

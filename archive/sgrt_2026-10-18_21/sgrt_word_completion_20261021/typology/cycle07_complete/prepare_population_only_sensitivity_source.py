"""Exact column-only Arrow projection of admitted current population/source metadata."""
import argparse,hashlib,json
from pathlib import Path
import pyarrow.parquet as pq
COLUMNS=['id','_population_axis_row','accepted_statistical_rural_role2021','population_2002','population_value_quality_2002','population_2010','population_value_quality_2010','population_2021','population_value_quality_2021','source_record_id_2021','name','region','population2010_effective_source_uid','population2010_prior_source_uid','population2010_effective_source_admission_sha256','population_2010_prior','population_value_quality_2010_prior','primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--source-admission',required=True);p.add_argument('--output',required=True);a=p.parse_args();src=Path(a.source);reviewp=Path(a.source_admission);review=json.loads(reviewp.read_text());assert str(review['status']).startswith('ACCEPTED') and review['all_checks_passed'] and review['nodes_sha256']==sha(src);out=Path(a.output);assert not out.exists();out.mkdir(parents=True)
 table=pq.read_table(src,columns=COLUMNS);metadata=dict(table.schema.metadata or {})
 if b'pandas' in metadata:
  pm=json.loads(metadata[b'pandas']);pm['columns']=[c for c in pm['columns'] if c['field_name'] in COLUMNS];metadata[b'pandas']=json.dumps(pm).encode();table=table.replace_schema_metadata(metadata)
 pq.write_table(table,out/'population_only_nodes.parquet',compression='snappy');readback=pq.read_table(out/'population_only_nodes.parquet');assert readback.equals(table);assert len(readback.column_names)==20 and readback.num_rows==173864
 r={'status':'COMPUTED_EXACT_POPULATION_ONLY_COLUMN_PROJECTION_PENDING_INDEPENDENT_READBACK','source_sha256':sha(src),'source_admission_path':str(reviewp.resolve()),'source_admission_sha256':sha(reviewp),'projection_sha256':sha(out/'population_only_nodes.parquet'),'code_sha256':sha(__file__),'rows':readback.num_rows,'columns':COLUMNS,'n_columns':20,'values_nulls_order_types_exactly_preserved':True,'no_geometry_or_mass_or_functions_claimed_in_compact_projection':True,'source353_metadata_preserved':True,'bytes':(out/'population_only_nodes.parquet').stat().st_size}
 (out/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r))
if __name__=='__main__':main()

"""Exact membership+focal persistence QC across9 current-source views.
Population/context fingerprints exclude transport/level/view metadata. JSON key order
is canonicalized; numeric values use12 significant figures for floating reductions.
"""
import argparse,hashlib,json,math
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
B=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canon(v):
 if pd.isna(v):return None
 if isinstance(v,(bool,np.bool_)):return bool(v)
 if isinstance(v,(int,float,np.number)):return format(float(v),'.12g')
 if isinstance(v,str) and v.startswith(('{','[')):
  try:return json.loads(v)
  except ValueError:pass
 return v

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--summary',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();out=Path(a.output);assert not out.exists();bindings=json.loads((Path(a.summary)/'source_binding.json').read_text());seen={};bad=[];counts=[];watched={};nrepeated=0
 for entry in bindings:
  d=Path(entry['normalized_path']);tp=Path(entry['classification_path'])/'complete_typology.parquet';assert sha(d/'normalized_units.parquet')==entry['normalized_units_sha256'] and sha(tp)==entry['types_sha256'];receipt=json.loads((d/'receipt.json').read_text());assert receipt['effective_nodes_sha256']=='66fe7cf6228b8256ab84480982fb143fc9d7fdc0b30f1aae6fbd9b333725ed1a';watched[str(d/'normalized_units.parquet')]=sha(d/'normalized_units.parquet');watched[str(tp)]=sha(tp)
  m=pd.read_parquet(d/'memberships_scoped.parquet',columns=['unit_id','id']);members=m.groupby('unit_id',sort=False).id.agg(lambda ids:hashlib.sha256(json.dumps(sorted(ids),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()).to_dict();del m
  rawcols=set(pq.read_schema(d/'raw_units_scoped.parquet').names);cols=[x for x in pq.read_schema(d/'normalized_units.parquet').names if x not in rawcols and x not in ('raw_kind','raw_central_object_definition','level','operational_view_id','display_retained','empirical_resolution_supported')];cols=sorted(set(cols)|{'unit_id','core_id','central_object_definition','kind'});types=pd.read_parquet(tp).set_index('unit_id');typecols=sorted(set(types.columns)-{'unit_name','level','central_object_ids','central_object_definition','unit_role'});nmatched=0
  for batch in pq.ParquetFile(d/'normalized_units.parquet').iter_batches(batch_size=256,columns=cols):
   for row in batch.to_pandas().to_dict('records'):
    ident=row['unit_id'];key=(members[ident],row['core_id'],row['central_object_definition'],row['kind']);values={k:canon(v) for k,v in row.items() if k not in ('unit_id','core_id')};values.update({'type:'+k:canon(types.loc[ident,k]) for k in typecols});fingerprint=hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
    if key in seen:
     nmatched+=1;nrepeated+=1
     if seen[key]['fingerprint']!=fingerprint:bad.append({'view_id':entry['view_id'],'unit_id':ident,'prior_view':seen[key]['view_id'],'prior_unit':seen[key]['unit_id'],'membership_sha256':key[0],'focal':key[1]})
    else:seen[key]={'fingerprint':fingerprint,'view_id':entry['view_id'],'unit_id':ident}
  counts.append({'view_id':entry['view_id'],'n_units':len(types),'n_repeated_membership_focal':nmatched})
 out.mkdir();pd.DataFrame(counts).to_csv(out/'view_counts.csv',index=False);pd.DataFrame(bad).to_csv(out/'fingerprint_disagreements.csv',index=False);r={'status':'COMPUTED_CROSSVIEW_PERSISTENCE_QC','n_views':len(bindings),'n_unique_membership_focal_kind_keys':len(seen),'n_repeated_keys_compared':nrepeated,'n_fingerprint_disagreements':len(bad),'all_fingerprints_match':not bad,'numeric_fingerprint_precision_significant_digits':12,'not_inferential_evidence_of_geographic_rank':True,'files_sha256':watched,'code_sha256':sha(__file__)};(out/'receipt.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='files_sha256'}))
if __name__=='__main__':main()

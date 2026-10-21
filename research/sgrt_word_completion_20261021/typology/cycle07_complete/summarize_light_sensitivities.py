"""Actual31 lightweight population-type view counts; no functional-profile claims."""
import argparse,json,hashlib
from pathlib import Path
import pandas as pd
B=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--progress',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();p=Path(a.progress);d=json.loads(p.read_text());assert d['n_closed']==d['n_requested']==31;out=Path(a.output);assert not out.exists();rows=[];freq=[]
 for e in d['entries']:
  folder=Path(e['classification_output_path']);assert sha(folder/'complete_typology.parquet')==e['types_sha256'] and sha(folder/'receipt.json')==e['receipt_sha256'];scope=json.loads((folder/'PROFILE_SCOPE.json').read_text());assert scope['full_functional_profile_comparison_allowed'] is False;f=pd.read_parquet(folder/'complete_typology.parquet');assert f.primary_type_id.notna().all() and f.unit_id.is_unique;view=f"{e['scenario']}_cap{e['cap_minutes']:03}";rows.append({'view_id':view,'scenario':e['scenario'],'cap_minutes':e['cap_minutes'],'n_units':len(f),'n_territorial_units':int(f.unit_role.eq('territorial_unit').sum()),'n_protected_carry':int(f.unit_role.eq('protected_carry').sum()),'n_primary_measured_population_types':f.primary_type_id.nunique(),'all_units_typed':True,'functional_context_projection_status':'NOT_PROJECTED_NOT_ABSENCE','full_functional_profile_comparison_allowed':False,'types_sha256':e['types_sha256']})
  for (role,code,name),g in f.groupby(['unit_role','primary_type_id','primary_type_name']):freq.append({'view_id':view,'unit_role':role,'primary_type_id':code,'primary_type_name':name,'n_units':len(g)})
 out.mkdir();pd.DataFrame(rows).to_csv(out/'all31_view_counts.csv',index=False);pd.DataFrame(freq).to_csv(out/'all31_type_codes_counts_by_role.csv',index=False);r={'status':'COMPUTED_ALL31_LIGHT_TYPE_COUNTS_PENDING_INDEPENDENT_TYPE_ADMISSION','n_views':31,'all_actual_produced_supported_forests_fully_typed':True,'do_not_pool_views_as_independent_units':True,'full_functional_profiles_not_projected':True,'source_progress_sha256':sha(p),'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()},'code_sha256':sha(__file__)};(out/'receipt.json').write_text(json.dumps(r,indent=2));print(json.dumps({'n_views':31,'n_scenarios':len(set(x['scenario'] for x in rows)),'all_units_typed':True,'receipt_sha256':sha(out/'receipt.json')}))
if __name__=='__main__':main()

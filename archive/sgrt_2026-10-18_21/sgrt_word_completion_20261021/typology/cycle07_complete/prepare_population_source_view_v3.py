"""Actual versioned population-only view from independently accepted full-axis overlay."""
import argparse,json,hashlib
from pathlib import Path
import pandas as pd
from classify_complete import admitted

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal_series(a,b):return (a.eq(b)|(a.isna()&b.isna())).fillna(False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--base-nodes',required=True);p.add_argument('--base-manifest',required=True);p.add_argument('--overlay',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh source projection required')
 paths=[Path(x).resolve() for x in (a.base_nodes,a.base_manifest,a.overlay,a.review)];watched={str(x):sha(x) for x in paths};basep,manifestp,op,rp=paths
 review=json.loads(rp.read_text());admitted(review);assert review['accepted_overlay_sha256']==sha(op)
 manifest=json.loads(manifestp.read_text());digest=sha(basep)
 assert digest in manifestp.read_text(),'Base node bytes not pinned by supplied accepted model manifest'
 b=pd.read_parquet(basep).set_index('id',drop=False);o=pd.read_parquet(op).set_index('id',drop=False);assert b.index.is_unique and o.index.is_unique and set(o.index)<=set(b.index)
 for bc,oc in [('population_2010','prior_effective_population2010'),('population_value_quality_2010','prior_effective_quality2010')]:assert equal_series(b.loc[o.index,bc],o[oc]).all(),'Full prior source differs'
 cols=['id','_population_axis_row','accepted_statistical_rural_role2021']+[f'{prefix}_{y}' for y in (2002,2010,2021) for prefix in ('population','population_value_quality')]+[k for k in ('source_record_id_2021','source_record_id_2010','name','region') if k in b]
 v=b[cols].copy();v['population_2010_prior']=v.population_2010;v['population_value_quality_2010_prior']=v.population_value_quality_2010
 v['population2010_prior_source_uid']=pd.NA;v['population2010_effective_source_uid']=pd.NA
 v.loc[o.index,'population2010_prior_source_uid']=o.prior_effective_sourceUID2010
 v.loc[o.index,'population2010_effective_source_uid']=o.prior_effective_sourceUID2010
 # Explicit new169 mask; original axis columns in the overlay are historical provenance, NOT final effective values.
 newmask=o.actual_override_applied.fillna(False).astype(bool);newids=o.index[newmask]
 for target,col in [('population_2010','reviewed_primary2010_population'),('population_value_quality_2010','reviewed_primary2010_quality'),('population2010_effective_source_uid','reviewed_primary2010_sourceUID')]:v.loc[newids,target]=o.loc[newids,col]
 for target,col in [('primary2010_overlay_applied','actual_override_applied'),('primary2010_numeric_changed','changed_population'),('primary2010_quality_changed','changed_quality')]:
  v[target]=False;v.loc[o.index,target]=o[col].fillna(False).astype(bool)
 cumulative=o.reviewed_primary2010_override_allowed.fillna(False).astype(bool);accepted=o.index[cumulative]
 for target,col in [('population_2010','reviewed_primary2010_population'),('population_value_quality_2010','reviewed_primary2010_quality'),('population2010_effective_source_uid','reviewed_primary2010_sourceUID')]:assert equal_series(v.loc[accepted,target],o.loc[accepted,col]).all(),'Cumulative accepted primary value/quality/sourceUID lost'
 untouched=o.index[~newmask]
 for target,col in [('population_2010','prior_effective_population2010'),('population_value_quality_2010','prior_effective_quality2010'),('population2010_effective_source_uid','prior_effective_sourceUID2010')]:assert equal_series(v.loc[untouched,target],o.loc[untouched,col]).all(),'Previously accepted source changed'
 v['population2010_effective_source_admission_sha256']=pd.NA;v.loc[o.index,'population2010_effective_source_admission_sha256']=o.source_primary2010_admission_sha256
 actual_numeric_changed=~equal_series(v.population_2010,v.population_2010_prior)
 actual_quality_changed=~equal_series(v.population_value_quality_2010,v.population_value_quality_2010_prior)
 assert actual_numeric_changed.equals(v.primary2010_numeric_changed) and actual_quality_changed.equals(v.primary2010_quality_changed),'Reported change flags differ from actual changed values'
 for y in (2002,2021):assert equal_series(v[f'population_{y}'],b[f'population_{y}']).all() and equal_series(v[f'population_value_quality_{y}'],b[f'population_value_quality_{y}']).all()
 for col in ('_population_axis_row','accepted_statistical_rural_role2021'):assert equal_series(v[col],b[col]).all()
 assert v.loc[v.primary2010_overlay_applied,'population2010_effective_source_uid'].notna().all()
 for f,s in watched.items():assert sha(f)==s
 out.mkdir(parents=True);v.reset_index(drop=True).to_parquet(out/'effective_population_source_view.parquet',index=False)
 v.loc[v.primary2010_overlay_applied].reset_index(drop=True).to_parquet(out/'new_primary2010_rows.parquet',index=False)
 receipt={'status':'COMPUTED_ACCEPTED_SOURCE_PROJECTION_PENDING_INDEPENDENT_READBACK','base_nodes_path':str(basep),'base_nodes_sha256':digest,'base_manifest_sha256':sha(manifestp),'accepted_overlay_sha256':sha(op),'overlay_admission_sha256':sha(rp),'effective_nodes_sha256':sha(out/'effective_population_source_view.parquet'),'supersedes_rejected_projection_v1':True,'v2_numeric_correct_but_source_admission_field_refined_in_v3':True,'cumulative_accepted_primary_rows_preserved':int(cumulative.sum()),'n_nodes':len(v),'n_source_axis_rows':len(o),'n_new_primary2010':int(v.primary2010_overlay_applied.sum()),'n_numeric_changed':int(v.primary2010_numeric_changed.sum()),'n_quality_changed':int(v.primary2010_quality_changed.sum()),'all_old2002_2021_population_and_all_roles_unchanged':True,'no_coordinates_or_services_or_mi_in_population_view':True,'not_new_primary2021_for_historical_only_rows':True,'watched_inputs':watched,'code_sha256':sha(__file__),'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()

"""Finish interrupted old-source bootstrap with unchanged frozen scientific code.
Only execution lifetime changes: read saved baseline labels, clear caches/trees
at every cap, retain label/curve witnesses for newly computed repetitions.
"""
import argparse,gc,json,hashlib,sys,ctypes
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.metrics import adjusted_rand_score
HERE=Path(__file__).resolve().parent;ENGINE=HERE.parent;sys.path.insert(0,str(ENGINE))
from run import binding,get_field,native_source_ids,BASE
from forest import Forest
from select_cuts import accept_stable_cut
from matrix_query import sha

def release(field,forest):
 forest.member_masks.clear();forest.attachment_events.clear()
 field.graph_cache.clear()
 if hasattr(field,'origin_mask_cache'):field.origin_mask_cache.clear()
 gc.collect()
 try:ctypes.CDLL(None).malloc_trim(0)
 except (AttributeError,OSError):pass

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--old-output',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--admission',type=Path,required=True);a=ap.parse_args()
 if a.output.exists() and any(a.output.iterdir()):raise ValueError('fresh continuation output required')
 a.output.mkdir(parents=True,exist_ok=True)
 old=json.loads((a.old_output/'pre_execution_binding.json').read_text())
 if binding('primary',a.cache)!=old:raise ValueError('original source/code/cache bytes changed')
 admit=json.loads(a.admission.read_text())
 if admit.get('all_checks_passed') is not True or admit.get('accepted_continuation_code_sha256')!=sha(Path(__file__)) or admit.get('accepted_old_binding_sha256')!=sha(a.old_output/'pre_execution_binding.json'):raise ValueError('independent continuation admission mismatch')
 checkpoint=a.old_output/'all_50_bootstrap_ledger_checkpoint.csv';prefix=pd.read_csv(checkpoint)
 caps=old['protocol']['extent']['candidate_caps_minutes'];completed=[int(x) for x in sorted(prefix.replicate_id.unique().astype(int))]
 if completed!=list(range(len(completed))) or len(completed)>=50:raise ValueError('prefix is not consecutive interrupted run')
 if len(prefix)!=len(completed)*len(caps):raise ValueError('incomplete cap prefix')
 for rep,g in prefix.groupby('replicate_id'):
  if sorted(g.candidate_cap.tolist())!=caps:raise ValueError('duplicate or missing prefix cap')
 field,cache_receipt=get_field(a.cache)
 nodes=pd.read_parquet(BASE/old['protocol']['source_nodes']);native=native_source_ids(nodes);del nodes
 baseline_summary=pd.read_csv(a.old_output/'candidate_knee_summary.csv').set_index('candidate_cap')
 baselabels={cap:np.load(a.old_output/f'cap_{cap:03}_provider_knee_labels.npy',allow_pickle=False) for cap in caps}
 p=field.providers;ordinary=~p.documented_external_context_anchor.fillna(False);regions=sorted(set(p.loc[ordinary,'region'].dropna().astype(str)));regindex={x:i for i,x in enumerate(regions)}
 mapped=p.region.astype(str).map(regindex);known=ordinary&mapped.notna();rng=np.random.default_rng(old['protocol']['seed']);rows=[];witnesses=[]
 start=dict(status='CONTINUATION_STARTED_ORIGINAL_FULL_RUN_EXIT137_INCOMPLETE',old_binding_sha256=sha(a.old_output/'pre_execution_binding.json'),old_prefix_sha256=sha(checkpoint),prefix_completed_replicates=completed,continuation_code_sha256=sha(Path(__file__)),unchanged_scientific_code=old['execution_sources'],memory_changes='savedbaseline labels only; no baseline/previous-replicate trees retained; evict recalculable per-cap memoizations and leafevent log')
 (a.output/'continuation_start_receipt.json').write_text(json.dumps(start,indent=2))
 for rep in range(50):
  draw=rng.multinomial(len(regions),np.full(len(regions),1/len(regions)))
  if rep in completed:
   for value in prefix.loc[prefix.replicate_id==rep,'region_weight_draw_json']:
    if json.loads(value)!=draw.tolist():raise ValueError('prefix RNG draw differs from exact original seed')
   continue
  weights=np.ones(len(p));weights[known]=draw[mapped[known].astype(int)]
  forest=Forest(field,native,old['protocol_sha256'],60.,1.,weights,'reciprocal')
  for cap in caps:
   s=forest.one_cap(cap);compare=weights>0;coverage=int(compare.sum());base=baselabels[cap]
   assess=s['knee']['status']=='candidate_knee' and baseline_summary.loc[cap,'status']=='candidate_knee' and coverage>=20 and len(np.unique(base[compare]))>=2 and len(np.unique(s['labels'][compare]))>=2
   ari=float(adjusted_rand_score(base[compare],s['labels'][compare])) if assess else None
   rec=dict(replicate_id=rep,candidate_cap=cap,status=s['knee']['status'],assessable=assess,ari=ari,n_compared_provider_seeds=coverage,compared_provider_fraction=coverage/len(p),n_positive_weight_regions=int((draw>0).sum()),selected_merge=s['knee'].get('selected_merge'),n_merges=len(s['events']),knee_fraction=s['knee']['selected_merge']/len(s['events']) if assess and s['events'] else None,region_weight_draw_json=json.dumps(draw.tolist()))
   rows.append(rec)
   fn=a.output/f'rep_{rep:02}_cap_{cap:03}_numeric_witnesses.npz';np.savez_compressed(fn,provider_labels=s['labels'],objective_curve=np.asarray(s['objective_curve'],float),positive_weight_provider_mask=compare,region_weights=draw)
   witnesses.append(dict(path=fn.name,sha256=sha(fn)))
   pd.DataFrame(rows).to_csv(a.output/'remaining_replicates_checkpoint.csv',index=False)
   del s;release(field,forest)
  del forest;gc.collect();print(f'Completed original geographic replicate {rep+1}/50 (continuation)',flush=True)
 new=pd.DataFrame(rows);combined=pd.concat([prefix,new],ignore_index=True).sort_values(['replicate_id','candidate_cap']).reset_index(drop=True)
 if len(combined)!=250 or combined.duplicated(['replicate_id','candidate_cap']).any():raise AssertionError('all50 ledger incomplete')
 combined.to_parquet(a.output/'all_50_bootstrap_ledger.parquet',index=False)
 retained=[]
 for cap,g in combined.groupby('candidate_cap'):
  test=accept_stable_cut(pd.to_numeric(g.ari,errors='coerce'),pd.to_numeric(g.knee_fraction,errors='coerce'));retained.append(dict(candidate_cap=int(cap),**test))
 pd.DataFrame(retained).to_csv(a.output/'retained_resolution_stability.csv',index=False)
 if binding('primary',a.cache)!=old or sha(checkpoint)!=start['old_prefix_sha256']:raise ValueError('original source/cache/prefix changed during continuation')
 receipt=dict(status='COMPUTED_ALL50_VIA_FROZEN41_PREFIX_PLUS9_CONTINUATION_NOT_ORIGINAL_FULLRUN_SUCCESS',completed_replicates=50,combined_rows=250,old_run_exit_code=137,old_checkpoint_immutable=True,original_scientific_policy_and_sources_unchanged=True,old_prefix_sha256=start['old_prefix_sha256'],continuation_code_sha256=sha(Path(__file__)),independent_admission_sha256=sha(a.admission),new_replicate_numeric_witnesses=witnesses,prefix0_to40_provider_labels_not_saved_by_original_driver=True,independent_result_review_pending=True,files=[dict(path=x.name,sha256=sha(x)) for x in sorted(a.output.iterdir()) if x.is_file()])
 (a.output/'continuation_completion_receipt.json').write_text(json.dumps(receipt,indent=2));print(pd.DataFrame(retained).to_string(index=False))
if __name__=='__main__':main()

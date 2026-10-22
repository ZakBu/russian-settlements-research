import pyarrow.parquet as pq, csv,gzip,json,math,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[2];folder=root/'research_staging/final';out=root/'research_staging/replication'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
eval=json.loads((folder/'evaluation.json').read_text());commit=json.loads((folder/'prediction_commitment.json').read_text());d=pq.read_table(folder/'predictions.parquet').to_pydict();before=pq.read_table(folder/'predictions_before_labels.parquet').to_pydict();errors=[];n=len(d['entity_uid']);assert len(set(d['entity_uid']))==n;assert d['entity_uid']==before['entity_uid'];assert sha(folder/'predictions_before_labels.parquet')==commit['prediction_sha256'];assert not any(c.startswith('observed') for c in before)
for k in before:
 if d[k]!=before[k]:errors.append(['commit_final_difference',k])
reports=[]
for r in eval['results']:
 cid=r['id'];metric='brier' if r['task']=='zero' else 'mae';y=d['observed_zero' if metric=='brier' else 'observed_change'];pb=d[cid+'_baseline'];pa=d[cid+'_augmented'];bl=[(a-b)**2 if metric=='brier' else abs(a-b) for a,b in zip(y,pb)];al=[(a-b)**2 if metric=='brier' else abs(a-b) for a,b in zip(y,pa)];b=math.fsum(bl)/n;a=math.fsum(al)/n;delta=math.fsum(v-w for v,w in zip(bl,al))/n
 diffs={'baseline':b-r['baseline'][metric],'augmented':a-r['augmented'][metric],'delta':delta-r['interval']['delta'],'relative_gain':(b-a)/b-r['relative_gain']}
 if any(abs(x)>1e-12 for x in diffs.values()):errors.append([cid,diffs])
 reports.append({'id':cid,'metric':metric,'n':n,'baseline':b,'augmented':a,'delta':delta,'relative_gain':(b-a)/b,'reported_abs_difference_max':max(abs(x) for x in diffs.values())})
ind=[]
with gzip.open(out/'independent_fit/e1_predictions.csv.gz','rt') as f:
 rr=list(csv.DictReader(f));assert [x['entity_uid'] for x in rr]==d['entity_uid']
 for col in ['baseline','augmented']:
  diffs=[abs(float(r[col])-v) for r,v in zip(rr,d['E1_primary_'+col])];ind.append({'model':col,'max_abs_difference':max(diffs),'tol_before_comparison':1e-12,'mismatch_count':sum(x>1e-12 for x in diffs)})
  if max(diffs)>1e-12:errors.append(['independent_fit',col,max(diffs)])
report={'status':'reviewed' if not errors else 'needs_revision','final_predictions_sha256':sha(folder/'predictions.parquet'),'prediction_commitment_sha256':sha(folder/'predictions_before_labels.parquet'),'commitment_contains_no_observed_labels':True,'committed_predictions_unchanged_after_label_addition':not any(x[0]=='commit_final_difference' for x in errors),'n':n,'blocks':len(set(d['block_id'])),'metrics':reports,'independent_E1_fit':ind,'errors':errors,'limits':['Standalone independent E1 uses same sklearn library/data, independent source implementation.','Intervals not independently calibrated; metrics reproduction does not validate scientific assumptions.','Prediction commitment is local disk SHA, not external timestamp.']}
(out/'final_replication_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
# For alternate stdlib script/independent bootstrap output: derive CSV from final committed predictions.
with gzip.open(out/'final_predictions_for_stdlib.csv.gz','wt',newline='') as f:
 cols=['entity_uid','block_id','observed_zero','observed_change','E1_primary_baseline','E1_primary_augmented','E2_primary_baseline','E2_primary_augmented'];w=csv.writer(f);w.writerow(cols);w.writerows(zip(*(d[k] for k in cols)))

import pyarrow.parquet as pq,json,math,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[2];results=[]
for label,metric in [('e1','brier'),('e2','mae')]:
 folder=root/'research_staging'/label/'development';path=folder/'predictions.parquet';d=pq.read_table(path).to_pydict();n=len(d['entity_uid']);assert len(set(d['entity_uid']))==n
 baseline=[];augmented=[]
 for y,b,a in zip(d['observed'],d['baseline'],d['augmented']):
  baseline.append((y-b)**2 if metric=='brier' else abs(y-b));augmented.append((y-a)**2 if metric=='brier' else abs(y-a))
 mb=math.fsum(baseline)/n;ma=math.fsum(augmented)/n;reported=json.loads((folder/'result.json').read_text())
 diffs={'baseline':mb-reported['baseline'][metric],'augmented':ma-reported['augmented'][metric],'delta':(mb-ma)-reported['paired_interval']['delta']}
 assert all(abs(v)<1e-12 for v in diffs.values())
 folds=[]
 for k in sorted(set(d['fold'])):
  ix=[i for i,v in enumerate(d['fold']) if v==k];folds.append({'fold':k,'n':len(ix),'blocks':len({d['block_id'][i] for i in ix}),'baseline':math.fsum(baseline[i] for i in ix)/len(ix),'augmented':math.fsum(augmented[i] for i in ix)/len(ix)})
 results.append({'direction':label,'status':'reviewed','input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'n':n,'blocks':len(set(d['block_id'])),'metric':metric,'baseline':mb,'augmented':ma,'delta':mb-ma,'relative_gain':(mb-ma)/mb,'reported_differences':diffs,'folds':folds})
report={'method':'Independent PyArrow input, stdlib math.fsum metrics, no model_executor/statistical_utils imports; compares saved dev predictions not independently refit devCV','results':results}
(root/'research_staging/replication/development_metric_comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

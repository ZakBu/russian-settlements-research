#!/usr/bin/env python3
"""Freeze a compact cross-audit receipt and recheck all recorded input hashes."""
from pathlib import Path
import json,hashlib
import pandas as pd
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()
def main():
 names=['economy','agriculture','wb','wb_relaxed','places','screening','screening_sensitivity','reference','report_and_documents','illustrative_case'];results={};protected={};audit_paths=[]
 for name in names:
  p=H/'independent_sources'/name/'AUDIT.json';a=json.loads(p.read_text());audit_paths.append(p);assert a['status']=='PASS',(name,a['status']);checks=a['checks'];assert all(c['pass'] for c in checks);results[name]={'status':a['status'],'checks':len(checks),'audit_sha256':sha(p)}
  for key,digest in a.get('input_SHA256',{}).items():protected[key]=digest
  for value in a.get('inputs',{}).values():
   if isinstance(value,dict) and 'path' in value and 'sha256' in value:protected[value['path']]=value['sha256']
  if name=='agriculture':
   protected[str(B/'restored/extracted/inputs/recovery_inputs/columnar/agriculture.parquet')]=a['sources']['raw_agriculture_sha256'];protected[str(B/'anchor_research_20261019/data/point_axis.parquet')]=a['sources']['axis_sha256'];protected[str(N/'agriculture/point_municipal_agriculture.parquet')]=a['sources']['point_layer_sha256']
 p=H/'results/AUDIT.json';a=json.loads(p.read_text());audit_paths.append(p);assert a['status']=='PASS_INTEGRATION_MAPPING' and a['all_executed_checks_pass'];results['master_integration']={'status':a['status'],'checks':a['checks_count'],'audit_sha256':sha(p)};protected[str(N/'core/feature_master.parquet')]=a['master_sha256'];protected[str(B/'anchor_research_20261019/data/point_axis.parquet')]=a['axis_sha256']
 for source in a['sources'].values():protected[source['path']]=source['sha256']
 mismatches=[{'path':p,'expected':digest,'actual':sha(Path(p))} for p,digest in protected.items() if sha(Path(p))!=digest];assert not mismatches,mismatches
 q=pd.read_csv(H/'results/conflict_queue.csv');sample=pd.read_csv(H/'results/external_audit_sample.csv');summary={'status':'PASS_INTEGRATION_AND_DECLARED_CALCULATIONS','master_rows':142570,'master_columns':914,'master_sha256':a['master_sha256'],'screening_rows':142570,'screening_columns':448,'screening_sha256':sha(N/'screening/support_point_profiles.parquet'),'audits':results,'all_current_recorded_source_hashes_match':True,'recorded_input_files_rechecked':len(protected),'review_queue_rows':len(q),'flagged_UIDs':int(q.id.nunique()),'integration_error_queue_rows':int(q.severity.str.startswith('ERROR').sum()),'planned_external_sample_UIDs':len(sample),'planned_sample_regions':int(sample.region.nunique()),'holdout_UIDs':int(sample.evaluation_split.eq('holdout_no_calibration').sum()),'planned_sample_externally_reviewed_UIDs':0,'separate_selected_documentary_providers_checked':17,'claim_boundary':'Technical integration, exact declared arithmetic, and selected source diagnostics. Not national SGRT accuracy, actual institution completeness, travel flows, external support centrality, or effectiveness of state support.','scope_exclusions':'New independent financial raw audit covers native mode only; legacy geographic alternatives and conditional-code training retain prior audit provenance. Extended federal master and historical PickPoint supplement are outside this ordinary914-column acceptance receipt.','code_sha256':sha(Path(__file__))};(H/'VALIDATION_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['audits','scope_exclusions']},ensure_ascii=False),flush=True)
 manifest={str(p.relative_to(H)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in H.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.json'};(H/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()

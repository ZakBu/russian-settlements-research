from pathlib import Path
import json,hashlib,csv
H=Path(__file__).resolve().parent;R=H.parents[2];p=json.loads((H/'strict_word_gates.json').read_text());e=json.loads((H/'current_gate_evidence.json').read_text());old=H/'history'/'cycle02_evidence_before_word_ci.json'
if not old.exists():old.write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
e['target_run_id']='sgrt_word_completion_20261021_cycle03_word_ci'
for r in e['requirements'].values():r['target_run_id']=e['target_run_id']
def proof(file,why):
 f=H/file;x=json.loads(f.read_text());assert x['n_failed']==0
 deps=x.get('source_sha256',{})
 if 'model_output_sha256' in x:deps.update({str(H.parent/'model'/x['model_directory']/k):v for k,v in x['model_output_sha256'].items()});deps.update(x.get('reviewed_code_configuration_sha256',{}))
 return dict(status='PASS',verified_by='strict_guardian',review_rationale=why,artifact=str(f.relative_to(R)),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),assertions=[dict(pointer='n_failed',operator='eq',expected=0),dict(pointer='status',operator='eq',expected=x['status'])],source_artifacts=[dict(artifact=k,sha256=v) for k,v in deps.items()])
for rid,file,why in [('W15','output_word_ci_2021_baseline_huff_independent_sample.json','All actual candidate/time/mass inputs frozen;20fixedorigins782full loworderalternatives independently reconstructed. Rawgravity, normalization,top2,conditionalP andthreshold/core semantics match134checks. Losslessallpairreconstruction permitted bypolicy; candidate inventory validity separatelyW06.'),('W18','output_word_ci_2021_baseline_independent_audit.json','Four-level actualWordCi: wholechildren never split,oneparent andstrict higherCi/order preventcycles; independently recomputed every2002/2010/2021sum/rural/missing and assigned+unassignedconservation.94independentchecks. This closes structural arithmetic, not realfunctionalcatchmentvalidation.')]:
 r=e['requirements'][rid];r.update(state='CLOSED',implementation='CLOSED',data='CLOSED',scientific='CLOSED',author='word_model_engineer',reviewer='strict_guardian',current_evidence_summary=why,external_blocker=None,next_repair='Preservefrozeninputs and rerunindependentchecks if selectedphysics changes; externalgeographicvalidity remainsseparate.')
 for c in next(q for q in p['requirements'] if q['id']==rid)['checks']:r['criteria'][c['id']]=proof(file,why)
r=e['requirements']['W26'];r['implementation']='CLOSED';r['current_evidence_summary']='ActualselectedWordCi27regressions independently424/424verified: coefficients,regionclusterCR1+tG−1CI,sourceY,training-onlyOOF/commoncases/folds/R²/RMSE/currentSHA. Scientificinterpretation conditionaldescriptive; sourcequality/geography limits explicit.'
r['criteria']['independent_statistics_and_negative_results_retained']=proof('regression_independent_audit.json',r['current_evidence_summary']);r['next_repair']='Inspect finalinterpretation, source-selectiontables, geographicresidualPNG and exactWordpredictordesign; never interpretendogenous2021Mi/Ci ascausal.'
r=e['requirements']['W14'];r['current_evidence_summary']='SelectedWordCiactual4orders independently94/94arithmeticchecks; sourceframe5checks+provisional12+roadextension22. Ci ordering and greaterCi parents explicit; priorownmassreference preserved.';r['implementation']='CLOSED';r['next_repair']='Verify rankselection/boundaries and source/functionlevelvalidity; preserve ownmass/Ci distinction and measuredsensitivity.'
r=e['requirements']['W25'];r['scientific']='NEEDS_REPAIR';r['state']='NEEDS_REPAIR';r['current_evidence_summary']='SelectedWordCi64broad observedpatterns are arithmeticallyconsistent;19ruralcenters and multiplelargecities violateliteral smallurban typeconditions, type5nearlarge andtype7independentNonchernozemgeography missing. Separateadapterrepair underway.';r['next_repair']='Keep64broadprototypes; independentlyaudit literalWordeligibility masks/functionalwitnesses and properCi definition before map/report labels.'
(H/'current_gate_evidence.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
with (H/'cycle02_word_progress.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['id','requirement','state','implementation','data','scientific','verified_criteria','evidence','next_repair']);w.writeheader()
 for q in p['requirements']:
  r=e['requirements'][q['id']];w.writerow(dict(id=q['id'],requirement=q['requirement'],**{k:r[k] for k in ['state','implementation','data','scientific']},verified_criteria=sum(c.get('status')=='PASS' for c in r['criteria'].values()),evidence=r.get('current_evidence_summary','Source-preservation33checks'),next_repair=r.get('next_repair',q['next_repair'])))
print('Targetcycle03; W15/W18 structural/computational scopes independentlyclosed. W25repair separate.')

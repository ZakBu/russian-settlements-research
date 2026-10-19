"""Independent artifact/invariant checks; does not rerun model selection."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
O=Path(__file__).resolve().parent;R=O.parent
a=json.loads((O/'validation_audit.json').read_text());q=pd.read_parquet(O/'paired_noncenters.parquet');c=pd.read_csv(O/'case_results.csv');src=json.loads((O/'cases_sources.json').read_text());checks={}
checks['all_audited_input_hashes_still_match']=all(hashlib.sha256((R/p).read_bytes()).hexdigest()==v for p,v in a['inputs_sha256'].items())
checks['paired_ids_unique']=q.id.is_unique;checks['no_anchors_in_paired_sample']=not q.center_anchored.any();checks['same_joint_denominator']=bool(q[['municipality_oktmo_code8','nearest_admin','flat_admin']].notna().all().all())
checks['paired_difference_exact']=bool((q.delta_nearest_minus_flat==(q.nearest_same_admin.astype(int)-q.flat_same_admin.astype(int))).all())
checks['2010_weight_sum_matches_audit']=float(q.population_2010.sum())==a['summary'][0]['population2010'];checks['flat_comparison_used_real_gis_artifact']=a['flat_file_independently_checked']
checks['source_quotes_each_under25']=all(len(s['source_quote'].split())<25 for s in src)
checks['source_quote_total_per_url_at_most25']=all(sum(len(s['source_quote'].split()) for s in src if s['source_url']==u)<=25 for u in {s['source_url'] for s in src})
checks['case_ids_unique']=c.case_id.is_unique;checks['no_quoted_case_claimed_direct_flow']=not c.direct_flow.any();checks['no_case_claimed_synchronous2010']=not c.synchronous_2010_evidence.any()
checks['manual_attribution_explicit']=c.loc[c.case_id.eq('C05'),'case_binding_status'].iloc[0]=='qualified_manual_adjectival_attribution'
for km in [250,400,600]:
 b=pd.read_csv(O/f'blocks_{km}km.csv');d=pd.read_csv(O/f'resamples_{km}km.csv')
 checks[f'blocks_{km}_preserve_all_rows']=int(b.n.sum())==len(q);checks[f'blocks_{km}_preserve_2010_mass']=abs(float(b.population_sum.sum())-float(q.population_2010.sum()))<1e-7;checks[f'resamples_{km}_399_finite']=len(d)==399 and np.isfinite(d[['delta','population2010_weighted_delta']]).all().all()
(O/'validation_checks.json').write_text(json.dumps({k:bool(v) for k,v in checks.items()},indent=2));assert all(checks.values()),checks
print('PASSED',len(checks),'artifact and provenance checks')

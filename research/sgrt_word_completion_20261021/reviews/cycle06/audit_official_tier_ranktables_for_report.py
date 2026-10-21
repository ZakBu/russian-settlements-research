#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=ROOT/'robustness/cycle06_access_v2_official_tiers';diag=source/'candidate_official_org_witness_diagnostic.parquet';prior=H/'official_tier_math_independent/audit.json';correct=H/'official_tier_exact_tail_correction_independent_readback.json';j=json.loads(prior.read_text());assert sha(diag) in prior.read_text() and json.loads(correct.read_text())['all_checks_passed'];x=pd.read_parquet(diag);checks=[];out={}
for sector in ['vpo','spo']:
 p=source/(sector+'_rank_witness_table.csv');saved=pd.read_csv(p).set_index('intrinsic_empirical_rank');expected=x.groupby('intrinsic_empirical_rank').agg(candidate_centers=('id','size'),positive_org_witness_centers=(sector+'_positive_witness','sum'),positive_reporting_org_rows=(sector+'_positive_org_witness_count','sum'));expected['unwitnessed_centers_unknown_presence']=expected.candidate_centers-expected.positive_org_witness_centers
 assert saved[expected.columns].astype('int64').equals(expected.astype('int64'));checks.append(dict(sector=sector,all4009_candidate_counts_and_rank_groups_equal=True));out[str(p)]=sha(p)
receipt=dict(status='ACCEPTED_RANK_TABLE_HASH_BINDING_FROM_INDEPENDENTLY_ADMITTED_DIAGNOSTIC_ROWS',all_checks_passed=True,n_checks=2,n_failed=0,checks=checks,ranktable_sha256=out,diagnostic_source_sha256=sha(diag),prior_source_count_audit_sha256=sha(prior),corrected_exact_tail_admission_sha256=sha(correct),source_model_and_reporting_witnesses_unchanged=True,not_functional_service_hierarchy_validation=True,code_sha256=sha(Path(__file__)))
(H/'official_tier_ranktables_report_binding_independent_admission.json').write_text(json.dumps(receipt,indent=2)+'\n')

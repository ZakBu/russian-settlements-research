"""Promote only the exact independently reviewed historical identity application."""
import argparse
import json
from pathlib import Path
import pandas as pd
from .apply_identity_rules import _sha

def promote(staging, review, output):
    if output.exists():raise FileExistsError('New immutable output required')
    decision=json.loads(review.read_text());receipt=json.loads((staging/'receipt.json').read_text())
    pins=decision['pins']
    if not decision['verdict'].startswith('APPROVE '):raise ValueError('Application not approved')
    if _sha(staging/'receipt.json')!=pins['application_receipt_sha256']:raise ValueError('Application receipt mismatch')
    for file,key in [('application_checks.parquet','application_checks_sha256'),('source_row_checks.parquet','source_row_checks_sha256'),('staged_identity_edges.parquet','staged_identity_edges_sha256')]:
        if _sha(staging/file)!=pins[key]:raise ValueError('Reviewed file changed: '+file)
    edges=pd.read_parquet(staging/'staged_identity_edges.parquet')
    pending=edges.decision_status.eq('pending_independent_application_review')
    if int(pending.sum())!=decision['scope']['staged_new_pairs']:raise ValueError('Reviewed count differs')
    if not edges.loc[pending,'relation'].eq('same_place').all():raise ValueError('Wrong relation')
    edges.loc[pending,'decision_status']='checked_rule_accepted'
    edges.loc[pending,'independent_application_review_sha256']=_sha(review)
    output.mkdir(parents=True)
    path=output/'accepted_identity_edges.parquet';edges.to_parquet(path,index=False)
    result={'status':'independently_reviewed_identity_application_accepted','review_sha256':_sha(review),
            'application_receipt_sha256':_sha(staging/'receipt.json'),'staging_edge_sha256':pins['staged_identity_edges_sha256'],
            'accepted_edges':len(edges),'new_accepted_pairs':int(pending.sum()),'baseline_edges_preserved':len(edges)-int(pending.sum()),
            'population_admissions':0,'coordinate_admissions':0,'boundary_comparability_admissions':0,
            'output':{'path':str(path),'sha256':_sha(path)}}
    (output/'acceptance_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['staging','review','output']:p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();print(json.dumps(promote(a.staging,a.review,a.output),ensure_ascii=False,indent=2))

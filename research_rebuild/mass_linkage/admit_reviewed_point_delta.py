"""Append a hash-bound independently reviewed point delta to an immutable ledger."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from .coverage import sha


def admit(base: Path, staged: Path, review_path: Path, output: Path):
    if output.exists():
        raise FileExistsError('New immutable output required')
    review=json.loads(review_path.read_text())
    if review.get('verdict')!='APPROVE_BOUNDED_POINT_DELTA':
        raise ValueError('Explicit independent bounded approval required')
    if review.get('decision_author')=='primary_agent_after_independent_validation':
        independent=Path(review['independent_review_path'])
        if sha(independent)!=review['independent_review_sha256']:
            raise ValueError('Independent validation artifact changed')
    for key,p in [('base_point_uses_sha256',base),('staged_point_uses_sha256',staged)]:
        if review.get(key)!=sha(p):raise ValueError('Review input hash differs: '+key)
    original=pd.read_parquet(base);candidates=pd.read_parquet(staged)
    allowed=review.get('approved_target_source_record_ids',[])
    if not allowed or len(allowed)!=len(set(allowed)):
        raise ValueError('Nonempty unique explicit reviewed target list required')
    if not set(allowed).issubset(set(candidates.target_source_record_id)):
        raise ValueError('Approved targets absent from reviewed candidate ledger')
    delta=candidates[candidates.target_source_record_id.isin(allowed)].copy()
    if delta.target_source_record_id.duplicated().any() or set(delta.target_source_record_id)&set(original.target_source_record_id):
        raise ValueError('New point-use targets collide')
    if not delta.coordinate_admission_status.eq('staged_candidate_pending_root_review').all():
        raise ValueError('Delta must contain only staged pending candidates')
    if delta.admission_allowed.fillna(False).any():
        raise ValueError('Candidate ledger already admits points')
    for c in ['boundary_comparability_asserted','population_scope_comparability_asserted','direct_historical_coordinate_measurement']:
        if c in delta and delta[c].fillna(False).any():raise ValueError('Unreviewed temporal/population assertion: '+c)
    if not (pd.to_numeric(delta.latitude,errors='coerce').between(-90,90)&pd.to_numeric(delta.longitude,errors='coerce').between(-180,180)).all():
        raise ValueError('Invalid admitted point')
    for c in ['point_origin_file','point_origin_sha256','point_origin_locator']:
        if delta[c].fillna('').astype(str).eq('').any():raise ValueError('Missing canonical origin: '+c)
    for file,hashval in delta[['point_origin_file','point_origin_sha256']].drop_duplicates().itertuples(index=False,name=None):
        if sha(Path(file))!=hashval:raise ValueError('Raw origin hash differs')
    delta['coordinate_admission_status']='reviewed_extension_rule_accepted'
    delta['coordinate_quality']='automatically_accepted_checked_rule'
    delta['admission_allowed']=True
    delta['application_gate_status']='accepted_after_independent_bounded_application_review'
    delta['coordinate_application_review_sha256']=sha(review_path)
    delta['review_id']=review.get('review_id') or review_path.stem
    accepted=pd.concat([original,delta],ignore_index=True)
    # Equality of values, including nulls, is mandatory; pandas may widen the
    # union's storage dtype for newly introduced columns.
    pd.testing.assert_frame_equal(accepted.iloc[:len(original)][original.columns].reset_index(drop=True),original.reset_index(drop=True),check_dtype=False)
    if accepted.target_source_record_id.duplicated().any():raise ValueError('Accepted ledger has duplicate targets')
    output.mkdir(parents=True)
    p=output/'accepted_point_uses.parquet';accepted.to_parquet(p,index=False)
    receipt={'status':'bounded_reviewed_point_delta_accepted','review_path':str(review_path),'review_sha256':sha(review_path),
             'inputs':{'base':{'path':str(base),'sha256':sha(base)},'staged':{'path':str(staged),'sha256':sha(staged)}},
             'builder_sha256':sha(Path(__file__)),'accepted_before':len(original),'accepted_added':len(delta),
             'accepted_after':len(accepted),'base_values_unchanged':True,
             'added_by_year':delta.target_year.value_counts().to_dict(),
             'unadmitted_staged_targets':sorted(set(candidates.target_source_record_id)-set(allowed)),
             'output':{'path':str(p),'sha256':sha(p)}}
    (output/'acceptance_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


def quarantine(base: Path, review_path: Path, output: Path):
    """Retain disputed assertions while excluding them from accepted coverage."""
    if output.exists():raise FileExistsError('New immutable output required')
    review=json.loads(review_path.read_text())
    if review.get('verdict')!='QUARANTINE_BOUNDED_POINT_USES' or sha(base)!=review.get('base_point_uses_sha256'):
        raise ValueError('Explicit hash-bound quarantine decision required')
    if sha(Path(review['independent_review_path']))!=review.get('independent_review_sha256'):
        raise ValueError('Independent dispute review changed')
    original=pd.read_parquet(base);targets=review.get('quarantine_target_source_record_ids',[])
    if not targets or len(targets)!=len(set(targets)) or not set(targets).issubset(original.target_source_record_id):
        raise ValueError('Quarantine target IDs not an exact unique selected subset')
    mask=original.target_source_record_id.isin(targets)
    accepted=original[~mask].copy();held=original[mask].copy()
    held['coordinate_admission_status']='quarantined_pending_specific_point_resolution'
    held['admission_allowed']=False
    held['quarantine_reason']=review['reason']
    output.mkdir(parents=True)
    for name,d in [('accepted_point_uses.parquet',accepted),('quarantined_point_uses.parquet',held)]:
        d.to_parquet(output/name,index=False)
    receipt={'status':'disputed_point_uses_quarantined','base':{'path':str(base),'sha256':sha(base)},
             'decision_path':str(review_path),'decision_sha256':sha(review_path),'builder_sha256':sha(Path(__file__)),
             'accepted_before':len(original),'quarantined':len(held),'accepted_after':len(accepted),
             'remaining_accepted_scientific_values_unchanged':True,
             'outputs':{p.name:sha(p) for p in output.glob('*.parquet')}}
    (output/'quarantine_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['base','staged','review','output']:ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args();print(json.dumps(admit(a.base,a.staged,a.review,a.output),ensure_ascii=False))

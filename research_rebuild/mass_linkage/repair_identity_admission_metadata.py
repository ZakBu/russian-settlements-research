"""Correct optional candidate-state fields for an exact accepted identity batch."""
import argparse
import json
from pathlib import Path
import pandas as pd
from .coverage import sha
from .promote_historical_identity import _validate_review, _approved_pairs, mark_admitted_metadata


def repair(source, review_path, output):
    if output.exists():
        raise FileExistsError('New immutable correction directory required')
    review=json.loads(review_path.read_text());_validate_review(review)
    approved=_approved_pairs(review)
    if not approved:
        raise ValueError('Exact approved identity pairs required')
    original=pd.read_parquet(source)
    mask=pd.Series([(a,b) in approved for a,b in original[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None)],index=original.index)
    if int(mask.sum())!=len(approved) or not original.loc[mask,'decision_status'].eq('checked_rule_accepted').all():
        raise ValueError('Correction only covers the exact already accepted edge set')
    if not original.loc[mask,'relation'].eq('same_place').all():
        raise ValueError('Wrong relation')
    if not original.loc[mask,'independent_application_review_sha256'].eq(sha(review_path)).all():
        raise ValueError('Edge approval pin differs')
    for column,value in [('candidate_status','candidate_pending_independent_application_review'),
                         ('admission_status','not_admitted'),('candidate_only',True)]:
        if not original.loc[mask,column].eq(value).all():
            raise ValueError('Unexpected source state for metadata correction: '+column)
    corrected=original.copy();mark_admitted_metadata(corrected,mask)
    changed_columns=['candidate_status','admission_status','candidate_only']
    pd.testing.assert_frame_equal(original.drop(columns=changed_columns),corrected.drop(columns=changed_columns))
    pd.testing.assert_frame_equal(original.loc[~mask],corrected.loc[~mask])
    output.mkdir(parents=True)
    destination=output/'accepted_identity_edges.parquet';corrected.to_parquet(destination,index=False)
    receipt={'status':'metadata_correction_pending_independent_check','input':{'path':str(source),'sha256':sha(source)},
             'review':{'path':str(review_path),'sha256':sha(review_path)},'builder_sha256':sha(Path(__file__)),
             'rows':len(corrected),'changed_rows':int(mask.sum()),'changed_columns':changed_columns,
             'scientific_decision_and_endpoint_values_unchanged':True,'new_scientific_admissions':False,
             'output':{'path':str(destination),'sha256':sha(destination)}}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['source','review','output']:
        parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args();print(json.dumps(repair(a.source,a.review,a.output)))

#!/usr/bin/env python3
"""Independent normative medical relation audit; never fit gravity parameters here."""
from pathlib import Path
import argparse
import hashlib
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(model):
    source=ROOT/'validation/medical_territories_2024_all_rows.parquet'
    membership=model/'memberships.parquet';candidates=model/'candidate_centers.parquet'
    if not membership.exists():raise FileNotFoundError('Actual routed memberships required; preparation is not an assignment')
    s=pd.read_parquet(source);m=pd.read_parquet(membership);c=pd.read_parquet(candidates)
    # Published attachment is a relation set, not one exclusive destination per village.
    resolved=s[s.origin_id.notna()&s.destination_id.notna()&~s.origin_is_partial_address_scope.fillna(True)].copy()
    relation=resolved[['origin_id','destination_id']].drop_duplicates()
    prediction_cols=['id','assigned_center_id','assignment_status']+[x for x in m if x.startswith('center_id_l')]
    relation=relation.merge(m[prediction_cols],left_on='origin_id',right_on='id',how='left',validate='many_to_one')
    relation['provider_is_candidate']=relation.destination_id.isin(c.id)
    relation['lowest_level_agreement']=relation.destination_id.eq(relation.assigned_center_id)
    levels=[x for x in relation if x.startswith('center_id_l')]
    relation['any_ancestor_agreement']=relation.lowest_level_agreement
    for col in levels:relation['any_ancestor_agreement']|=relation.destination_id.eq(relation[col])
    travel=ROOT/'transport/independent_medical_validation_travel.parquet'
    if travel.exists():
        t=pd.read_parquet(travel)
        relation=relation.merge(t,on=['origin_id','destination_id'],how='left',validate='one_to_one')
    external=relation[relation.origin_id.ne(relation.destination_id)]
    eligible=external[external.provider_is_candidate]
    byorigin=external.groupby('origin_id').agg(documented_destinations=('destination_id','nunique'),any_documented_lowest_level_agreement=('lowest_level_agreement','any'),any_documented_ancestor_agreement=('any_ancestor_agreement','any'),any_documented_provider_eligible=('provider_is_candidate','any'))
    relation.to_parquet(model/'independent_medical_relation_audit.parquet',index=False)
    byorigin.reset_index().to_csv(model/'independent_medical_origin_audit.csv',index=False)
    receipt={'status':'COMPUTED_EXTERNAL_NORMATIVE_RELATION_AUDIT','source_rows':len(s),'source_origin_resolved_rows':int(s.origin_id.notna().sum()),'source_provider_resolved_rows':int(s.destination_id.notna().sum()),'source_partial_address_rows_excluded':int(s.origin_is_partial_address_scope.fillna(True).sum()),'unique_external_resolved_pairs':len(external),'unique_external_origin_count':len(byorigin),'documented_external_provider_candidate_recall':float(external.provider_is_candidate.mean()) if len(external) else None,'exact_lowest_agreement_all_resolved_pairs':float(external.lowest_level_agreement.mean()) if len(external) else None,'exact_lowest_agreement_eligible_pairs':float(eligible.lowest_level_agreement.mean()) if len(eligible) else None,'any_documented_provider_lowest_agreement_by_origin':float(byorigin.any_documented_lowest_level_agreement.mean()) if len(byorigin) else None,'any_ancestor_agreement_is_not_lowest_agreement':True,'any_documented_ancestor_agreement_by_origin':float(byorigin.any_documented_ancestor_agreement.mean()) if len(byorigin) else None,'used_for_training_or_threshold_selection':False,'blind_preregistered_holdout':False,'generalization_to_national_service_system_proven':False,'scope':'2024 normative primary-care territorial attachments in Leningrad oblast; not observed trips, not all-function catchment ground truth','source_sha256':sha(source),'membership_sha256':sha(membership),'candidate_sha256':sha(candidates)}
    (model/'independent_medical_validation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);a=p.parse_args();run(a.model)

#!/usr/bin/env python3
"""Independent normative medical relation audit; never fit gravity parameters here."""
from pathlib import Path
import argparse
import hashlib
import json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(model):
    source=ROOT/'validation/medical_territories_2024_all_rows.parquet'
    membership=model/'memberships.parquet';candidates=model/'candidate_centers.parquet'
    if not membership.exists():raise FileNotFoundError('Actual routed memberships required; preparation is not an assignment')
    mr=model/'run_receipt.json';manifest_path=model/'output_manifest.json'
    run_receipt=json.loads(mr.read_text());manifest=json.loads(manifest_path.read_text())
    if not run_receipt.get('status','').startswith('COMPUTED') or manifest['run_receipt_sha256']!=sha(mr):raise ValueError('Committed completed model snapshot required')
    model_inputs=[mr,membership,candidates,model/'function_specific_memberships.parquet',model/'own_mass_components.parquet']
    model_before={str(p):sha(p) for p in model_inputs}
    for p in model_inputs[1:]:
        if manifest['files'][p.name]['sha256']!=model_before[str(p)]:raise ValueError('Model artifact differs from completed snapshot: '+p.name)
    s=pd.read_parquet(source);m=pd.read_parquet(membership);c=pd.read_parquet(candidates)
    # Published attachment is a relation set, not one exclusive destination per village.
    resolved=s[s.origin_id.notna()&s.destination_id.notna()&~s.origin_is_partial_address_scope.fillna(True)].copy()
    relation=resolved[['origin_id','destination_id']].drop_duplicates()
    prediction_cols=['id','assigned_center_id','assignment_status']+[x for x in m if x.startswith('center_id_l')]
    relation=relation.merge(m[prediction_cols],left_on='origin_id',right_on='id',how='left',validate='many_to_one')
    relation['provider_is_candidate']=relation.destination_id.isin(c.id)
    relation['lowest_level_agreement']=relation.destination_id.eq(relation.assigned_center_id)
    functional=model/'function_specific_memberships.parquet'
    masspath=model/'own_mass_components.parquet'
    if functional.exists() and masspath.exists():
        f=pd.read_parquet(functional)
        f=f[f.function_group.eq('healthcare')][['id','assigned_center_id','assignment_status','raw_model_center_id']].rename(columns={'id':'origin_id','assigned_center_id':'healthcare_assigned_center_id','assignment_status':'healthcare_assignment_status','raw_model_center_id':'healthcare_raw_leader_id'})
        relation=relation.merge(f,on='origin_id',how='left',validate='many_to_one')
        mass=pd.read_parquet(masspath,columns=['id','physical_healthcare_count_proxy'])
        provider_ids=set(mass.loc[mass.physical_healthcare_count_proxy.gt(0),'id'])
        relation['provider_has_observed_healthcare']=relation.destination_id.isin(provider_ids)
        relation['healthcare_assignment_agreement']=relation.destination_id.eq(relation.healthcare_assigned_center_id)
        relation['healthcare_raw_leader_agreement']=relation.destination_id.eq(relation.healthcare_raw_leader_id)
        # Independent nearest-network-provider comparator; no fitted parameter or holdout selection.
        manifest_path=ROOT/'transport/candidate_travel_times_manifest.json'
        manifest=json.loads(manifest_path.read_text());base=manifest_path.parent
        om=pd.read_parquet(base/manifest['origin_mapping']['path']);dm=pd.read_parquet(base/manifest['destination_mapping']['path'])
        def canonical(frame):return frame['canonical_id'].fillna(frame.id) if 'canonical_id' in frame else frame.id
        om['resolved_id']=canonical(om);dm['resolved_id']=canonical(dm)
        origins=om[om.resolved_id.isin(relation.origin_id)];destinations=dm[dm.resolved_id.isin(provider_ids)]
        best=[]
        for part in manifest['parts']:
            p=pd.read_parquet(base/part['path'],filters=[('origin_index','in',origins.origin_index.tolist()),('destination_index','in',destinations.destination_index.tolist())])
            if p.empty:continue
            p=p.merge(origins[['origin_index','resolved_id','snap_km']].rename(columns={'resolved_id':'origin_id','snap_km':'origin_snap_km'}),on='origin_index',validate='many_to_one').merge(destinations[['destination_index','resolved_id','snap_km']].rename(columns={'resolved_id':'nearest_provider_id','snap_km':'destination_snap_km'}),on='destination_index',validate='many_to_one')
            p['travel_minutes']=p.network_minutes+4*(p.origin_snap_km+p.destination_snap_km)
            p.loc[p.origin_id.eq(p.nearest_provider_id),'travel_minutes']=0
            p=p[p.travel_minutes.le(180+1e-4)]
            best.append(p.sort_values(['travel_minutes','nearest_provider_id']).drop_duplicates('origin_id')[['origin_id','nearest_provider_id','travel_minutes']])
        if best:
            nearest=pd.concat(best).sort_values(['travel_minutes','nearest_provider_id']).drop_duplicates('origin_id')
            relation=relation.merge(nearest,on='origin_id',how='left',validate='many_to_one')
            relation['nearest_healthcare_provider_agreement']=relation.destination_id.eq(relation.nearest_provider_id)
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
    if model_before!={p:sha(Path(p)) for p in model_before}:raise ValueError('Model inputs changed during independent medical comparison')
    relation.to_parquet(model/'independent_medical_relation_audit.parquet',index=False)
    byorigin.reset_index().to_csv(model/'independent_medical_origin_audit.csv',index=False)
    receipt={'status':'COMPUTED_EXTERNAL_NORMATIVE_RELATION_AUDIT','source_rows':len(s),'source_origin_resolved_rows':int(s.origin_id.notna().sum()),'source_provider_resolved_rows':int(s.destination_id.notna().sum()),'source_partial_address_rows_excluded':int(s.origin_is_partial_address_scope.fillna(True).sum()),'unique_external_resolved_pairs':len(external),'unique_external_origin_count':len(byorigin),'documented_external_provider_candidate_recall':float(external.provider_is_candidate.mean()) if len(external) else None,'exact_lowest_agreement_all_resolved_pairs':float(external.lowest_level_agreement.mean()) if len(external) else None,'exact_lowest_agreement_eligible_pairs':float(eligible.lowest_level_agreement.mean()) if len(eligible) else None,'any_documented_provider_lowest_agreement_by_origin':float(byorigin.any_documented_lowest_level_agreement.mean()) if len(byorigin) else None,'any_ancestor_agreement_is_not_lowest_agreement':True,'any_documented_ancestor_agreement_by_origin':float(byorigin.any_documented_ancestor_agreement.mean()) if len(byorigin) else None,'used_for_training_or_threshold_selection':False,'blind_preregistered_holdout':False,'generalization_to_national_service_system_proven':False,'scope':'2024 normative primary-care territorial attachments in Leningrad oblast; not observed trips, not all-function catchment ground truth','source_sha256':sha(source),'membership_sha256':sha(membership),'candidate_sha256':sha(candidates)}
    if functional.exists():
        observed=external[external.provider_has_observed_healthcare]
        receipt.update(healthcare_provider_observation_recall=float(external.provider_has_observed_healthcare.mean()),healthcare_assignment_agreement_all_pairs=float(external.healthcare_assignment_agreement.mean()),healthcare_raw_leader_agreement_all_pairs=float(external.healthcare_raw_leader_agreement.mean()),healthcare_assignment_agreement_observed_provider_pairs=float(observed.healthcare_assignment_agreement.mean()) if len(observed) else None,nearest_healthcare_provider_agreement_all_pairs=float(external.nearest_healthcare_provider_agreement.mean()) if 'nearest_healthcare_provider_agreement' in external else None,healthcare_function_assignments_sha256=sha(functional),nearest_provider_comparator_scope='all observed healthcare providers in same frozen route matrix, <=180 minutes, ties canonical ID; no fitting')
    (model/'independent_medical_validation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);a=p.parse_args();run(a.model)

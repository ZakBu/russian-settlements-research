"""Stage own 2021 NP provider points supported by concordant historical objects.

Past statistical inclusion affects historical population attribution. It does
not, alone, invalidate a separate 2021 record's own point. Historical graph reuse
requires a separate temporal/event gate and is not performed here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from .coverage import sha
from .apply_coordinate_extensions import base_use
from .stage_historical_city_points import relevant_event_roles, SELECTED, POINTS, EVIDENCE, EVENTS

W=Path('/workspace')
COHORT=W/'settlements-work/continuation_20261003/coordinate_rule_v4/coordinate_rule_v4_candidates.parquet'
RECEIPT=COHORT.parent/'run_receipt.json'
RAW=W/'settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'


def stage(output):
    if output.exists():raise FileExistsError('New immutable output required')
    pins={k:{'path':str(p),'sha256':sha(p)} for k,p in {'candidate_cohort':COHORT,'candidate_receipt':RECEIPT,'raw_provider_source':RAW,
           'selected':SELECTED,'accepted_base_points':POINTS,'source_evidence':EVIDENCE,'events':EVENTS}.items()}
    candidate_receipt=json.loads(RECEIPT.read_text())
    if pins['candidate_cohort']['sha256']!=candidate_receipt['candidate_sha256']:raise ValueError('Candidate cohort changed')
    cohort=pd.read_parquet(COHORT)
    if not cohort.source_record_id.is_unique or not cohort.candidate_rule_v4_both_history_plus_admin_geo_point.all():raise ValueError('Candidate rule cohort inconsistent')
    if cohort.coordinate_admission.any() or cohort.external_fias_binding_admission.any():raise ValueError('Candidates already claim admissions')
    selected=pd.read_parquet(SELECTED).set_index('source_record_id')
    base=pd.read_parquet(POINTS,columns=['target_source_record_id'])
    if set(base.target_source_record_id)&set(cohort.source_record_id):raise ValueError('Candidate already has an accepted point')
    evidence=pd.read_parquet(EVIDENCE,columns=['source_record_id','source_evidence_json'])
    ev=dict(zip(evidence.source_record_id,evidence.source_evidence_json.map(json.loads)))
    raw=pd.read_parquet(RAW,columns=['latitude_dadata','longitude_dadata','object_level','object_name','population','oktmo'])
    events=json.loads(EVENTS.read_text());proposals=[];ledger=[]
    statistical={'included_in_historical_parent_aggregate','separate_statistical_publication','census_component_of_settlement'}
    for r in cohort.itertuples(index=False):
        rid=r.source_record_id;s=selected.loc[rid];se=ev.get(rid,{})
        reasons=[]
        if s.census_year!=2021 or s.population_scope in {'federal_city_region','territorial_aggregate','municipality','region'} or not s.is_additive_settlement_record:
            reasons.append('current_census_source_not_individual_physical_np')
        if not se or se.get('legacy_identity_conflict') or se.get('legacy_same_year_collision') or se.get('is_federal_aggregate'):
            reasons.append('current_source_identity_conflict_or_aggregate')
        index=int(str(rid).rsplit(':',1)[1]);rr=raw.iloc[index-1]
        if float(rr.latitude_dadata)!=r.provider_latitude or float(rr.longitude_dadata)!=r.provider_longitude:
            raise ValueError('Point differs from exact raw provider row')
        roles=relevant_event_roles(events,s.oktmo,2002)
        for e in roles:
            e['historical_point_reuse_requires_separate_event_review']=True
            e['current_2021_point_veto']=e['point_veto'] and e['event_type'] not in statistical
        if any(e['current_2021_point_veto'] for e in roles):reasons.append('relevant_physical_lineage_event_needs_specific_point_review')
        ledger.append({'target_source_record_id':rid,'population':r.population,'gate_passed':not reasons,
                       'hold_reasons_json':json.dumps(reasons,ensure_ascii=False),'lineage_event_roles_json':json.dumps(roles,ensure_ascii=False)})
        if reasons:continue
        locator=f'parquet_row_1based={index};latitude_dadata,longitude_dadata'
        use=base_use(rid,2021,r.provider_latitude,r.provider_longitude,rid,r.provider_settlement_name,r.provider_settlement_type_full,
                     r.raw_region,str(RAW),index,pins['raw_provider_source']['sha256'],locator,
                     'Own named typed 2021 NP provider point; exact historical OKATO named object and administrative context in 2009+2011, expected region and <=1km GeoKladr agreement',
                     'current_np_own_point_concordant_2009_2011_named_code_admin_1km_v1',{
                        'admission_allowed':False,'coordinate_application_family':'A_current_own_point_two_historical_code_witnesses_admin',
                        'coordinate_provider_family':'tochno_dadata','coordinate_provider':'DaData via Tochno',
                        'provider_query_receipt_missing':True,
                        'application_inference_kind':'modern_own_np_representative_point_historical_object_concordance_screen',
                        'direct_historical_coordinate_measurement':False,'population_scope_comparability_asserted':False,
                        'point_origin_file':str(RAW),'point_origin_sha256':pins['raw_provider_source']['sha256'],
                        'point_origin_locator':locator,'point_origin_kind':'raw_2021_own_provider_named_point',
                        'point_claim_artifact_file':str(COHORT),'point_claim_artifact_sha256':pins['candidate_cohort']['sha256'],
                        'source_okato_raw':str(r.raw_okato_dadata),'source_oktmo_raw':s.oktmo,
                        'historical_okato_comparison_key':r.source_okato_text,'historical_okato_comparison_basis':r.source_okato_serialization,
                        'historical_geo_source_sha256':r.geo_source_sha256,'historical_classifier_source_sha256':r.class_source_sha256,
                        'historical_geo_to_provider_km':r.geo_provider_distance_km,
                        'lineage_event_roles_json':json.dumps(roles,ensure_ascii=False),
                        'provider_binding_status':'named provider point use accepted separately from external legal identifier binding',
                        'provider_fias_binding_status':'not_certified_by_point_rule; raw own/general provider identifiers retained in candidate evidence'})
        proposals.append(use)
    output.mkdir(parents=True)
    p=output/'staged_point_uses.parquet';d=pd.DataFrame(proposals);d.to_parquet(p,index=False)
    l=output/'gate_ledger.parquet';pd.DataFrame(ledger).to_parquet(l,index=False)
    receipt={'status':'candidate_only_pending_independent_review','inputs':pins,'builder_sha256':sha(Path(__file__)),
             'candidate_rows':len(cohort),'staged_rows':len(d),'held_rows':len(ledger)-len(d),
             'staged_population':int(pd.DataFrame(ledger).query('gate_passed').population.sum()),
             'outputs':{p.name:sha(p),l.name:sha(l)},
             'limits':['Current own-point admission only; no cross-year links created.','Past statistical inclusion is preserved without upgrading old population or temporal coordinate reuse.',
                       'Identifier legality, measurement date and boundary comparability remain unverified.']}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return {k:v for k,v in receipt.items() if k not in ['inputs','outputs','limits']}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    print(json.dumps(stage(ap.parse_args().output),ensure_ascii=False))

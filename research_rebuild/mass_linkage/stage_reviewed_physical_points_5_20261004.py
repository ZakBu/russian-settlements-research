"""Stage five independently reviewed named GeoKLADR point uses as an immutable packet.

This does not edit accepted ledgers. The targets intersect a global historical
point-route blocklist; applying them requires the receiving applier to authorize
only these exact reviewed target/origin/coordinate tuples while leaving the
blocklist itself intact.
"""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
import pandas as pd

BASE=Path('/workspace/settlements-work/continuation_20261004')
REVIEW=BASE/'independent_review/fullchain134_points_review'
SOURCE=REVIEW/'eligible_point_use_candidates.csv'
RECEIPT=REVIEW/'receipt.json'
BLOCK=Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')
OUT=BASE/'R4/reviewed_physical_points_5'
DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')


def sha(p):
    with open(p,'rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    if OUT.exists() and any(OUT.iterdir()): raise FileExistsError(OUT)
    source_rows=list(csv.DictReader(SOURCE.open(encoding='utf-8',newline='')))
    if len(source_rows)!=5: raise ValueError(f'expected five independently eligible point uses; got {len(source_rows)}')
    review=json.loads(RECEIPT.read_text(encoding='utf-8'))
    if review.get('status')!='independent_candidate_point_review_no_admission': raise ValueError('unexpected review status')
    if review.get('outputs',{}).get('eligible_point_use_candidates.csv')!=sha(SOURCE): raise ValueError('eligible file differs from review output pin')
    if review.get('summary',{}).get('eligible_point_use_candidates')!=5: raise ValueError('review receipt does not approve five rows')
    block=json.loads(BLOCK.read_text(encoding='utf-8'))
    blocked=set(map(str,block.get('blocked_target_source_record_ids',[])))
    target_ids=[r['target_source_record_id'] for r in source_rows]
    if len(set(target_ids))!=5: raise ValueError('duplicate point targets')
    overlap=set(target_ids)&blocked
    if overlap!=set(target_ids): raise ValueError('unexpected changed blocklist intersection; all five reviewed targets must remain globally blocked')
    rows=[]
    for r in source_rows:
        if r['decision_status']!='candidate_requires_independent_review' or r['candidate_independent_disposition']!='eligible_point_use_candidate':
            raise ValueError(f"unexpected disposition: {r['target_source_record_id']}")
        if r['provider_identifier_binding_asserted']!='False' or r['boundary_population_comparability_asserted']!='False':
            raise ValueError('packet must not claim provider ID binding or population boundary comparability')
        if r['point_origin_sha256']!=sha(DBF): raise ValueError('raw DBF hash mismatch')
        row=dict(r)
        row.update({
            'target_source_record_id':r['target_source_record_id'],
            'target_year':str(int(r['census_year'])),
            'point_origin_kind':'raw_named_typed_GeoKLADR_2011_physical_point_reviewed',
            'coordinate_source':'independently reviewed named typed raw GeoKLADR 2011 physical point; exact 2021 target point correctness only',
            'coordinate_source_record_id':'',
            'coordinate_source_file':str(DBF),
            'coordinate_source_sha256':sha(DBF),
            'coordinate_source_locator':r['point_origin_locator'],
            'coordinate_provider':'',
            'coordinate_provider_id':'',
            'provider_binding_status':'unresolved_not_claimed',
            'coordinate_measurement_date_unknown':True,
            'direct_historical_coordinate_measurement':False,
            'boundary_comparability_asserted':False,
            'population_scope_comparability_asserted':False,
            'admission_allowed':False,
            'coordinate_admission_status':'candidate_only_independently_reviewed_not_applied',
            'blocked_target_exception_scope':'exact reviewed target ID + raw DBF hash + record/byte locator + literal coordinates only; all other global blocks remain active',
            'blocked_target_resolution_review_sha256':sha(RECEIPT),
        })
        rows.append(row)
    OUT.mkdir(parents=True)
    candidate=OUT/'candidate_point_uses.parquet'
    pd.DataFrame(rows).to_parquet(candidate,index=False)
    approved_csv=OUT/'approved_point_uses.csv'
    fields=['target_source_record_id','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','census_year','settlement_name','settlement_type','region_norm','modern_current_source_record_id','quarantine_resolution_basis']
    with approved_csv.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k:r.get(k,'') for k in fields})
    exceptions=[]
    for r in rows:
        exceptions.append({
            'target_source_record_id':r['target_source_record_id'],
            'origin_file':str(DBF), 'origin_sha256':sha(DBF),
            'origin_locator':r['point_origin_locator'],
            'latitude':float(r['latitude']), 'longitude':float(r['longitude']),
            'review_receipt_sha256':sha(RECEIPT),
            'scope':'point use only; no provider-ID binding; no population/boundary comparability; does not remove target from global blocklist',
        })
    manifest_fragment={
        'point_source':{
            'candidate':{'path':str(candidate),'sha256':sha(candidate)},
            'approved':{'path':str(approved_csv),'sha256':sha(approved_csv)},
            'review_receipt':{'path':str(RECEIPT),'sha256':sha(RECEIPT)},
            'candidate_columns':{'target':'target_source_record_id','latitude':'latitude','longitude':'longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'},
            'approved_columns':{'target':'target_source_record_id','latitude':'latitude','longitude':'longitude','origin_file':'point_origin_file','origin_sha256':'point_origin_sha256','origin_locator':'point_origin_locator'},
            'origin':{'path':str(DBF),'sha256':sha(DBF)},
            'output_columns':{
                'target_year':'target_year','point_origin_kind':'point_origin_kind','coordinate_source':'coordinate_source','coordinate_source_record_id':'coordinate_source_record_id','coordinate_source_file':'coordinate_source_file','coordinate_source_sha256':'coordinate_source_sha256','coordinate_source_locator':'coordinate_source_locator','coordinate_provider':'coordinate_provider','coordinate_provider_id':'coordinate_provider_id','provider_binding_status':'provider_binding_status','coordinate_measurement_date_unknown':'coordinate_measurement_date_unknown','direct_historical_coordinate_measurement':'direct_historical_coordinate_measurement','boundary_comparability_asserted':'boundary_comparability_asserted','population_scope_comparability_asserted':'population_scope_comparability_asserted'
            },
            'reviewed_global_block_exceptions_exact_tuple_only':exceptions,
            'global_blocklist_mutated':False,
        },
        'input_pins':{
            'independent_eligible_csv':{'path':str(SOURCE),'sha256':sha(SOURCE)},
            'independent_review_receipt':{'path':str(RECEIPT),'sha256':sha(RECEIPT)},
            'raw_GeoKLADR_2011_DBf':{'path':str(DBF),'sha256':sha(DBF)},
            'historical_2009_classifier_SQL':{'path':'/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql','sha256':sha('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')},
            'global_blocklist':{'path':str(BLOCK),'sha256':sha(BLOCK)},
        },
        'summary':{'candidate_rows':5,'eligible_rows':5,'blocked_target_intersections':5,'new_identity_edges':0,'population_values_added':0,'point_uses_only':True,'application_status':'staged_for_receiving_applier; not applied'},
        'candidate_sha256':sha(candidate),'approved_csv_sha256':sha(approved_csv),
        'generator_script_sha256':sha(__file__),
        'status':'candidate_packet_ready_for_root_applier',
    }
    (OUT/'manifest_fragment.json').write_text(json.dumps(manifest_fragment,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    receipt={
        'status':'candidate_packet_ready_for_root_applier',
        'candidate_rows':5,'approved_rows':5,'blocked_target_intersections':5,
        'source_review_receipt_sha256':sha(RECEIPT),
        'source_eligible_csv_sha256':sha(SOURCE),
        'raw_origin_sha256':sha(DBF),
        'blocklist_sha256':sha(BLOCK),
        'manifest_fragment_sha256':sha(OUT/'manifest_fragment.json'),
        'candidate_sha256':sha(candidate),'approved_csv_sha256':sha(approved_csv),
        'target_ids':target_ids,
        'no_graph_or_accepted_point_ledger_mutation':True,
    }
    (OUT/'packet_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

"""Stage narrowly corroborated historical city points, without admitting them.

Coordinates are the named 2011 GeoKladr object, corroborated by an already
accepted modern carrier over a collision-free accepted same-place path. Boundary
events remain explicit. Only a receiving city's absorption event is distinguished
from disappearance, split, relocation or unknown event roles.
"""
from __future__ import annotations
import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path
import pandas as pd
from .apply_coordinate_extensions import base_use, source_is_physical, valid_point, verify_path
from .coverage import identity_sets, sha
from .coordinate_ledger import haversine_array
from .propagate_accepted_points import STATUS_OK

W = Path('/workspace')
SELECTED = W/'settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet'
POINTS = W/'settlements-work/coordinates/accepted_final_v1/accepted_point_uses.parquet'
GRAPH = W/'settlements-work/identity/accepted_historical_v2/accepted_identity_edges.parquet'
CANDIDATES = W/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
EVIDENCE = W/'settlements-work/candidates/optimized_run/source_evidence.parquet'
EVENTS = W/'settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json'
GEO_RAW = W/'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
CLASS_RAW = W/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
PRIOR_POINT_REVIEW = W/'settlements-work/coordinates/independent_review_v1/review.json'


def relevant_event_roles(events, native_code, year):
    """Exact native-code roles only; no code padding, date or legal certification."""
    result = []
    if not native_code or pd.isna(native_code):
        return result
    key = 'RU-OKTMO-' + str(native_code)
    for e in events:
        roles = [k for k,v in e.items() if 'settlement_id' in k and v == key]
        if not roles:
            continue
        date = str(e.get('source_asserted_effective_date') or '')
        match = re.search(r'(?:19|20)\d{2}', date)
        if match and not year <= int(match.group()) <= 2021:
            continue
        kind = e.get('event_type', '')
        # Only the receiver role is exempted from the point veto. Boundary
        # comparability remains unasserted even for such an exempted event.
        receiving = roles == ['to_settlement_id_legacy_candidate'] and kind in {'absorbed', 'absorbed_into_city', 'merged_into_city'}
        result.append({'event_id': e.get('event_id'), 'event_type': kind,
                       'native_code_roles': roles, 'point_veto': not receiving,
                       'boundary_comparability': 'not_asserted',
                       'event_evidence_status': 'legacy_candidate_not_newly_verified'})
    return result


def stage(output: Path):
    if output.exists():
        raise FileExistsError('New immutable output required')
    inputs = {'selected':SELECTED,'accepted_points':POINTS,'accepted_graph':GRAPH,
              'historical_candidates':CANDIDATES,'source_evidence':EVIDENCE,
              'lineage_candidates':EVENTS,'raw_geo2011':GEO_RAW,'raw_classifier2009':CLASS_RAW}
    inputs['prior_point_conflict_review']=PRIOR_POINT_REVIEW
    pins = {k:{'path':str(v),'sha256':sha(v)} for k,v in inputs.items()}
    selected = pd.read_parquet(SELECTED)
    points = pd.read_parquet(POINTS)
    graph = pd.read_parquet(GRAPH)
    if not graph.decision_status.isin(STATUS_OK).all() or not graph.relation.eq('same_place').all():
        raise ValueError('All graph edges must be accepted same-place decisions')
    _,_,components = identity_sets(selected,graph)
    component_of = {rid:c for c in components for rid in c}
    modern = points[points.target_year.eq(2021)].set_index('target_source_record_id')
    source = selected.set_index('source_record_id')
    evidence = pd.read_parquet(EVIDENCE,columns=['source_record_id','source_evidence_json'])
    ev = dict(zip(evidence.source_record_id,evidence.source_evidence_json.map(json.loads)))
    adj = defaultdict(list)
    by_decision = {}
    for e in graph.itertuples(index=False):
        adj[e.from_source_record_id].append((e.to_source_record_id,e.decision_id))
        adj[e.to_source_record_id].append((e.from_source_record_id,e.decision_id))
        by_decision[e.decision_id] = e._asdict()
    def path(a,b):
        queue=deque([(a,[])]);seen={a}
        while queue:
            node,edges=queue.popleft()
            if node==b:return edges
            for nxt,d in adj[node]:
                if nxt not in seen:seen.add(nxt);queue.append((nxt,edges+[d]))
        raise ValueError('No accepted path to component carrier')
    all_candidates = pd.read_parquet(CANDIDATES)
    located=all_candidates[all_candidates.historical_name_exact.eq(True)&all_candidates.historical_type_exact.eq(True)&all_candidates.is_additive_settlement_record.eq(True)&all_candidates.latitude_from_lat.notna()&all_candidates.longitude_from_long.notna()].copy()
    collision_counts=located.groupby(['census_year','latitude_from_lat','longitude_from_long']).historical_okato.nunique()
    ambiguous_points=set(collision_counts[collision_counts.gt(1)].index)
    candidates = all_candidates[all_candidates.census_year.isin([2002,2010]) & all_candidates.type_norm.eq('город') & all_candidates.historical_named_point_candidate.eq(True) & ~all_candidates.source_record_id.isin(points.target_source_record_id)]
    prior=json.loads(PRIOR_POINT_REVIEW.read_text())
    unresolved_carriers={r['source_record_id'] for r in prior['targeted_holds']['known_city_coordinate_conflicts'] if str(r.get('interpretation','')).startswith('hold_')}
    events = json.loads(EVENTS.read_text())
    proposals=[];gates=[]
    for r in candidates.itertuples(index=False):
        reasons=[];rid=r.source_record_id
        ok,why=source_is_physical(r)
        reasons.extend(why)
        se=ev.get(rid,{})
        if not se or se.get('legacy_identity_conflict') or se.get('legacy_same_year_collision') or se.get('is_federal_aggregate'):
            reasons.append('historical_source_identity_conflict_or_aggregate_or_missing_evidence')
        if r.code_join_basis!='typed_urban_8digit_plus_zero_third_geo_group' or str(r.kod3_raw_text)!='000' or str(r.settlement_type_raw)!='г':
            reasons.append('typed_raw_city_code_certificate_failed')
        if r.source_sha256_2011!=pins['raw_geo2011']['sha256'] or r.source_sha256_2009!=pins['raw_classifier2009']['sha256']:
            reasons.append('raw_source_hash_mismatch')
        if not valid_point(r.latitude_from_lat,r.longitude_from_long):
            reasons.append('historical_point_invalid')
        if (int(r.census_year),r.latitude_from_lat,r.longitude_from_long) in ambiguous_points:
            reasons.append('within_year_shared_historical_point_for_distinct_typed_coded_objects')
        carriers=sorted(component_of.get(rid,set()) & set(modern.index))
        carrier=carriers[0] if len(carriers)==1 else None
        distance=None;edge_ids=[];roles=[]
        if carrier is None:
            reasons.append('no_unique_accepted_modern_component_carrier')
        else:
            if carrier in unresolved_carriers:reasons.append('known_unresolved_carrier_point_conflict_not_reconciled')
            ce=ev.get(carrier,{})
            if not ce or ce.get('legacy_identity_conflict') or ce.get('legacy_same_year_collision') or ce.get('is_federal_aggregate') or not ce.get('is_additive_settlement_record'):
                reasons.append('modern_carrier_source_identity_conflict_or_aggregate_or_missing_evidence')
            cr=modern.loc[carrier]
            distance=float(haversine_array(pd.Series([r.latitude_from_lat]),pd.Series([r.longitude_from_long]),pd.Series([cr.latitude]),pd.Series([cr.longitude]))[0])
            if not distance<=1:reasons.append('historical_to_accepted_modern_point_exceeds_1km')
            edge_ids=path(rid,carrier)
            ok,why=verify_path(json.dumps(edge_ids),rid,carrier,by_decision)
            if not ok:raise ValueError(why)
            roles=relevant_event_roles(events,source.loc[carrier,'oktmo'],int(r.census_year))
            if any(e['point_veto'] for e in roles):reasons.append('relevant_lineage_event_has_nonreceiving_or_unknown_role')
        record={'target_source_record_id':rid,'year':int(r.census_year),'settlement_name':r.settlement_name,
                'population':r.population,'carrier_source_record_id':carrier,'point_distance_km':distance,
                'identity_path_decision_ids_json':json.dumps(edge_ids),'lineage_event_roles_json':json.dumps(roles,ensure_ascii=False),
                'gate_passed':not reasons,'hold_reasons_json':json.dumps(reasons,ensure_ascii=False)}
        gates.append(record)
        if reasons:continue
        locator=f'DBF_record_1based={int(r.record_number_1based)};DBF_byte_offset_0based={int(r.record_byte_offset_0based)};OKATO2011_raw={r.historical_okato_2011_raw}'
        same_origin=bool(str(modern.loc[carrier].point_origin_file)==str(GEO_RAW) and f'record_number_1based={int(r.record_number_1based)};' in str(modern.loc[carrier].point_origin_locator))
        provenance='Named coded city GeoKladr 2011 representative point; explicit spatial continuity to historical census; accepted 2021 source consistency within 1km, not automatically an independent measurement; population boundaries not harmonized'
        use=base_use(rid,int(r.census_year),r.latitude_from_lat,r.longitude_from_long,
                     'GEOKLADR2011:'+str(r.historical_okato_2011_raw),str(r.name_raw_2011),'город',str(r.region_norm),
                     str(GEO_RAW),int(r.record_number_1based),pins['raw_geo2011']['sha256'],locator,provenance,
                     'historical_city_typed_code_and_accepted_modern_point_1km_v1',{
                       'admission_allowed':False,'coordinate_application_family':'H_historical_city_2011_named_point_modern_corroboration',
                       'application_inference_kind':'historical_spatial_continuity_from_2011_named_point',
                       'direct_historical_coordinate_measurement':False,'population_scope_comparability_asserted':False,
                       'point_origin_file':str(GEO_RAW),'point_origin_sha256':pins['raw_geo2011']['sha256'],
                       'point_origin_locator':locator,'point_origin_kind':'raw_named_typed_geo2011_object',
                       'point_claim_artifact_file':str(CANDIDATES),'point_claim_artifact_sha256':pins['historical_candidates']['sha256'],
                       'inference_modern_point_use_target_source_record_id':carrier,
                       'inference_identity_path_decision_ids_json':json.dumps(edge_ids),
                       'inference_identity_path_from_source_record_id':rid,'inference_identity_path_to_source_record_id':carrier,
                       'inference_identity_path_edge_count':len(edge_ids),
                       'corroborating_modern_point_distance_km':distance,
                       'modern_carrier_uses_same_geo_origin':same_origin,
                       'historical_classifier2009_file':str(CLASS_RAW),'historical_classifier2009_sha256':pins['raw_classifier2009']['sha256'],
                       'historical_classifier2009_locator':f'line_1based={int(r.source_line_1based)};OKATO2009_raw={r.historical_okato_2009_raw}',
                       'lineage_event_roles_json':json.dumps(roles,ensure_ascii=False)})
        proposals.append(use)
    output.mkdir(parents=True)
    ledger=pd.DataFrame(gates);staged=pd.DataFrame(proposals)
    ledger.to_parquet(output/'gate_ledger.parquet',index=False)
    staged.to_parquet(output/'staged_point_uses.parquet',index=False)
    receipt={'status':'candidate_only_pending_independent_rule_and_application_review','inputs':pins,
             'builder_sha256':sha(Path(__file__)),'candidates':len(ledger),'staged':len(staged),
             'staged_population_by_year':ledger[ledger.gate_passed].groupby('year').population.sum().to_dict(),
             'outputs':{p.name:sha(p) for p in output.glob('*.parquet')},
             'limitations':['No admission and no existing point replacement.','Native identifiers and event candidate evidence retained without legal-date certification.',
                            'Population accuracy and boundary comparability are independent of spatial continuity.','Legacy coordinate conflict claims require independent review before admission.']}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return {k:v for k,v in receipt.items() if k not in ['inputs','outputs','limitations']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    print(json.dumps(stage(parser.parse_args().output),ensure_ascii=False))

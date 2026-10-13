"""Build a source-traceable candidate ledger for modern points and identity propagation.

This staging builder never accepts a new coordinate without an independent
coordinate-family review. It preserves the reviewed R5b coordinate assertions
as a byte-identical baseline and represents retrospective point reuse as an
inference, not a historical measurement or boundary-comparability claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping

import duckdb
import numpy as np
import pandas as pd

from .coordinate_rules import haversine_km, valid_wgs84

V4 = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_04')
V6 = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_06')
V7 = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_07')
LEDGER = Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet')
BASELINE = Path('/workspace/settlements-baseline/output')
BASELINE_DB = Path('/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb')
BASELINE_ASSET_MANIFEST = Path('/workspace/settlements-assets/baseline/asset_manifest.json')
DATA_CHECKOUT = Path('/workspace/settlements-data')
R5B_RELEASE = DATA_CHECKOUT / 'research_rebuild/evidence/releases/national_reviewed_admissions_r5b_yearbook_20260930'
R5B_COORDINATES = R5B_RELEASE / 'coordinate_admissions.csv'
ACCEPTED_GRAPH_DIR = Path('/workspace/settlements-work/identity/accepted_ordinary_v4')
ACCEPTED_GRAPH = ACCEPTED_GRAPH_DIR / 'accepted_identity_edges.parquet'
ACCEPTED_GRAPH_RECEIPT = ACCEPTED_GRAPH_DIR / 'acceptance_receipt.json'
OUTPUT = Path('/workspace/settlements-work/coordinates/admission_staging_v1')

R5B_COORDINATES_SHA256 = 'c58c3a573ddc7878f948b69ab53696bb94583408b8368fbef34f1b385b56c07e'
ACCEPTED_GRAPH_SHA256 = 'ef034c0282fa877ba8820c3706f069a740ce5d4330bc80cba3e44f9898780eef'


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def stable_id(prefix: str, value: str) -> str:
    return prefix + '-' + hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


def is_null(value: Any) -> bool:
    if value is None: return True
    try: return bool(pd.isna(value))
    except (TypeError,ValueError): return False


def txt(value: Any) -> str:
    return '' if is_null(value) else str(value).strip()


def boolv(value: Any) -> bool:
    return False if is_null(value) else bool(value)


def safe_json_list(value: Any) -> list[Any]:
    if is_null(value) or not txt(value): return []
    try:
        decoded=json.loads(str(value))
        return decoded if isinstance(decoded,list) else []
    except (TypeError,ValueError,json.JSONDecodeError):return []


def num(value: Any) -> float | None:
    if is_null(value): return None
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError): return None


def normalized_code(value: Any) -> str | None:
    """Remove a terminal numeric .0 only; never pad, truncate, or repair zeros."""
    s=txt(value)
    if not s: return None
    if s.isdigit(): return s
    if s.endswith('.0') and s[:-2].isdigit(): return s[:-2]
    return None


def norm_text(value: Any) -> str:
    if is_null(value): return ''
    s=unicodedata.normalize('NFKC',str(value)).casefold().replace('ё','е')
    return ' '.join(s.split())


def region_key(value: Any) -> str:
    s=norm_text(value)
    for phrase in ['автономный округ','автономная область','область','край','республика']:
        s=s.replace(phrase,' ')
    return ' '.join(s.split())


def name_key(value: Any) -> str:
    s=norm_text(value)
    # GeoKLADR's raw name commonly has only a short settlement-type prefix.
    prefixes=('г. ','г ','город ','д. ','д ','деревня ','с. ','с ','село ','п. ','п ','пос. ','пос ','поселок ','посёлок ','х. ','х ','аул ')
    for prefix in prefixes:
        if s.startswith(prefix):
            s=s[len(prefix):].strip(); break
    return ' '.join(s.split())


def type_key(value: Any) -> str:
    s=norm_text(value).replace('.','').strip()
    aliases={
        'г':'город','гор':'город','город':'город',
        'с':'село','село':'село','д':'деревня','деревня':'деревня',
        'п':'поселок','пос':'поселок','пгт':'поселок городского типа',
        'поселок городского типа':'поселок городского типа','поселок':'поселок',
        'х':'хутор','хутор':'хутор','аул':'аул','ст':'станица','станица':'станица',
    }
    return aliases.get(s,s)


def physical_scope(row: Mapping[str,Any]) -> tuple[bool,list[str]]:
    """Use explicit source grain/aggregate flags; population_scope alone cannot override them."""
    holds=[]
    scope=norm_text(row.get('population_scope'))
    if scope in {'federal_city_region','municipality','municipal_aggregate','region','administrative_area','territorial_aggregate'}:
        holds.append('source_population_scope_is_aggregate')
    for key in ('source_is_aggregate_scope','is_territorial_aggregate','federal_city_region_scope'):
        if boolv(row.get(key)): holds.append(f'explicit_{key}')
    raw_level=norm_text(row.get('raw_object_level') or row.get('object_level'))
    if raw_level and raw_level not in {'населенный пункт','населённый пункт','settlement','locality'}:
        holds.append('source_raw_object_level_not_physical_settlement')
    typ=norm_text(row.get('settlement_type'))
    if typ in {'муниципальный район','город федерального значения','регион','муниципалитет'}:
        holds.append('source_type_is_aggregate_or_admin_unit')
    # Older 2010 records can carry bad scope labels; explicit aggregate flags/statuses win.
    coverage=norm_text(row.get('coverage_status'))
    if coverage in {'derived_sum_city_districts','federal_city_region_aggregate'}:
        holds.append('source_coverage_status_identifies_aggregate')
    if row.get('retained_in_legacy_snapshot') is False and coverage=='derived_sum_city_districts':
        holds.append('source_row_is_unselected_derived_aggregate')
    return not holds,sorted(set(holds))


def point_key(latitude: Any, longitude: Any) -> tuple[float,float] | None:
    lat,lon=num(latitude),num(longitude)
    if lat is None or lon is None or not valid_wgs84(lat,lon): return None
    return round(lat,7),round(lon,7)


def union_candidate_points(points: Iterable[Mapping[str,Any]], *, force_hold: bool=False) -> dict[str,Any]:
    """Collapse only identical coordinates; retain every provider/evidence row."""
    rows=list(points)
    coordinates=sorted({point_key(r.get('latitude'),r.get('longitude')) for r in rows if point_key(r.get('latitude'),r.get('longitude')) is not None})
    if force_hold:
        return {'proposed_latitude':None,'proposed_longitude':None,'distinct_point_count':len(coordinates),
                'point_choice_status':'hold_ambiguous_multipoint_family','admission_allowed':False}
    if len(coordinates)==1:
        lat,lon=coordinates[0]
        return {'proposed_latitude':lat,'proposed_longitude':lon,'distinct_point_count':1,
                'point_choice_status':'single_distinct_point_candidate_pending_review','admission_allowed':False}
    if len(coordinates)>1:
        return {'proposed_latitude':None,'proposed_longitude':None,'distinct_point_count':len(coordinates),
                'point_choice_status':'hold_multiple_distinct_coordinate_claims','admission_allowed':False}
    return {'proposed_latitude':None,'proposed_longitude':None,'distinct_point_count':0,
            'point_choice_status':'hold_no_valid_coordinate_claim','admission_allowed':False}


def build_dsu(edges: pd.DataFrame) -> tuple[dict[str,str],dict[str,list[dict[str,Any]]],dict[str,list[tuple[str,str]]]]:
    parent:dict[str,str]={}; size:dict[str,int]={}; adjacency:dict[str,list[tuple[str,str]]]=defaultdict(list)
    def find(x:str)->str:
        parent.setdefault(x,x); size.setdefault(x,1)
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a:str,b:str)->None:
        ra,rb=find(a),find(b)
        if ra==rb:return
        if size[ra]<size[rb]:ra,rb=rb,ra
        parent[rb]=ra;size[ra]+=size[rb]
    for e in edges.itertuples(index=False):
        a,b=txt(e.from_source_record_id),txt(e.to_source_record_id)
        if not a or not b: continue
        decision=txt(getattr(e,'decision_id',''))
        find(a);find(b);union(a,b)
        adjacency[a].append((b,decision));adjacency[b].append((a,decision))
    members:dict[str,list[str]]=defaultdict(list)
    for node in parent: members[find(node)].append(node)
    comp_by_node={}; component_members={}; component_adj={}
    for nodes in members.values():
        stable=stable_id('COORD-COMP','|'.join(sorted(nodes)))
        component_members[stable]=sorted(nodes)
        for node in nodes:comp_by_node[node]=stable
    for node,links in adjacency.items():component_adj[node]=links
    return comp_by_node,component_members,component_adj


def edge_path(start:str,target:str,adjacency:Mapping[str,list[tuple[str,str]]]) -> list[str] | None:
    if start==target:return []
    queue=deque([start]);prev={start:(None,None)}
    while queue:
        node=queue.popleft()
        for neighbor,edge_id in adjacency.get(node,[]):
            if neighbor in prev:continue
            prev[neighbor]=(node,edge_id)
            if neighbor==target:
                path=[];cur=target
                while cur!=start:
                    prior,eid=prev[cur];path.append(eid);cur=prior
                return list(reversed(path))
            queue.append(neighbor)
    return None


def _provider_point_records(frame: pd.DataFrame) -> list[dict[str,Any]]:
    family_cols={
        'A_rural_exact_code_and_own_name_type':'candidate_rule_family_a_rural_exact_code_and_own_name_type',
        'B_strict_name_code_and_independent_context':'candidate_rule_family_b_strict_name_code_and_independent_context',
    }
    result=[]
    for r in frame.to_dict('records'):
        families=[name for name,col in family_cols.items() if boolv(r.get(col))]
        if not families: continue
        physical,scope_holds=physical_scope(r)
        # The v4 packet has its own source-grain classifier; require it for this
        # provider family rather than inferring physicality from a populated row.
        if not boolv(r.get('source_is_physical_np')):
            physical=False
            scope_holds.append('v4_source_is_physical_np_gate_false_or_missing')
        lat,lon=num(r.get('provider_latitude')),num(r.get('provider_longitude'))
        if not physical or not valid_wgs84(lat,lon): continue
        raw_fias=txt(r.get('raw_fias_id_dadata'))
        settlement_fias=txt(r.get('raw_settlement_fias_id_dadata'))
        source_id=txt(r.get('source_record_id'))
        provider_id=raw_fias or settlement_fias or None
        point_id=stable_id('COORD-POINT',f'{source_id}|tochno_dadata|{provider_id}|{lat:.7f}|{lon:.7f}')
        locator=txt(r.get('source_locator')) or f"{txt(r.get('source_file'))}#{txt(r.get('source_sheet'))}:{txt(r.get('source_row'))}"
        result.append({
            'candidate_point_id':point_id,'source_record_id':source_id,'target_year':int(r.get('census_year') or 2021),
            'coordinate_source_record_id':source_id,'coordinate_source_locator':locator,
            'coordinate_provider':'tochno_dadata','coordinate_provider_family':'tochno_dadata',
            'coordinate_provider_id':provider_id,'provider_general_fias_id':raw_fias or None,
            'settlement_provider_id':settlement_fias or None,'latitude':lat,'longitude':lon,
            'source_name':txt(r.get('settlement_name')),'source_type':txt(r.get('settlement_type')),
            'source_region':txt(r.get('region_raw')),'population_scope':txt(r.get('population_scope')),
            'source_native_id':txt(r.get('source_native_id')),'source_file':txt(r.get('source_file')),
            'source_row':r.get('source_row'),'source_sha256':txt(r.get('source_sha256')),
            'source_oktmo_raw':txt(r.get('raw_oktmo')),'provider_oktmo_raw':txt(r.get('raw_oktmo_dadata')),
            'source_okato_raw':txt(r.get('okato')),'provider_okato_raw':txt(r.get('raw_okato_dadata')),
            'source_provider_oktmo_exact':boolv(r.get('source_provider_oktmo_exact_match')),
            'provider_fias_level':txt(r.get('raw_fias_level_dadata')),
            'provider_own_name_exact':boolv(r.get('provider_name_exact_selected_name')),
            'provider_own_type_exact':boolv(r.get('provider_type_exact_selected_type')),
            'candidate_families_json':json.dumps(families,ensure_ascii=False),
            'coordinate_evidence_lineage_id':'TOCHNO_DADATA_2021_PARQUET_PROVIDER_RESPONSE',
            'coordinate_evidence_locator_note':'coordinates and FIAS fields are projected from exact raw Tochno 2021 source row; response/query receipt and measurement date absent',
            'provider_id_binding_status':'exact_source_provider_code_and_fias_level_candidate' if boolv(r.get('source_provider_oktmo_exact_match')) else 'provider_id_binding_incomplete',
            'coordinate_admission_status':'candidate_unreviewed','admission_allowed':False,
            'review_flags_json':json.dumps(scope_holds,ensure_ascii=False),
        })
    return result


def _wikidata_point_records(point_frame: pd.DataFrame, city_frame: pd.DataFrame) -> list[dict[str,Any]]:
    city_by_id=city_frame.set_index(city_frame.source_record_id.astype(str)).to_dict('index')
    records=[]
    for r in point_frame.loc[point_frame.point_coordinate_candidate_gate.fillna(False).astype(bool)].to_dict('records'):
        sid=txt(r.get('source_record_id'));ctx=city_by_id.get(sid,{})
        lat,lon=num(r.get('wikidata_latitude')),num(r.get('wikidata_longitude'))
        if not valid_wgs84(lat,lon):continue
        qid=txt(r.get('wikidata_qid'))
        point_id=stable_id('COORD-POINT',f'{sid}|wikidata|{qid}|{lat:.7f}|{lon:.7f}')
        obs=json.loads(r.get('wikidata_point_evidence_json') or '[]')
        locators=[]
        for fact in obs:
            file=txt(fact.get('source_file'));line=txt(fact.get('truthy_line') or fact.get('line_number'))
            if file:locators.append(f'{file}:{line}' if line else file)
        records.append({
            'candidate_point_id':point_id,'source_record_id':sid,'target_year':2021,
            'candidate_families_json':json.dumps((['C_wikidata_physical_source_city_point']+
                (['A_urban_level4_physical_code_name_point_in_region'] if boolv(ctx.get('candidate_rule_family_a_urban_level4_physical_code_name_point_in_region')) else [])),ensure_ascii=False),
            'coordinate_source_record_id':sid,'coordinate_source_locator':json.dumps(sorted(set(locators)),ensure_ascii=False),
            'coordinate_provider':'wikidata_p625','coordinate_provider_family':'wikimedia_wikidata_one_evidence_family',
            'coordinate_provider_id':qid,'provider_general_fias_id':txt(ctx.get('raw_fias_id_dadata')) or None,
            'settlement_provider_id':txt(ctx.get('raw_settlement_fias_id_dadata')) or None,
            'latitude':lat,'longitude':lon,'source_name':txt(r.get('source_name')),'source_type':txt(r.get('source_type')),
            'source_region':txt(r.get('source_region_raw')),'population_scope':txt(r.get('source_population_scope')),
            'source_native_id':txt(ctx.get('source_native_id')),'source_file':txt(ctx.get('source_file')),
            'source_row':ctx.get('source_row'),'source_sha256':txt(ctx.get('source_sha256')),
            'source_oktmo_raw':txt(r.get('source_oktmo_raw')),'provider_oktmo_raw':txt(ctx.get('raw_oktmo_dadata')),
            'source_okato_raw':txt(ctx.get('okato')),'provider_okato_raw':txt(ctx.get('raw_okato_dadata')),
            'source_provider_oktmo_exact':boolv(ctx.get('source_provider_oktmo_exact_match')),
            'wikidata_qid':qid,'wikidata_p31_qids_json':r.get('wikidata_p31_qids_json'),
            'wikidata_physical_lineage_qids_json':r.get('wikidata_physical_lineage_qids_json'),
            'wikidata_point_evidence_json':r.get('wikidata_point_evidence_json'),
            'wikidata_unique_qid_binding':boolv(r.get('wikidata_unique_qid_binding')),
            'point_inside_expected_physical_source_region':boolv(r.get('point_inside_expected_physical_source_region')),
            'wikidata_provider_distance_km':num(r.get('wikidata_provider_point_distance_km')),
            'coordinate_evidence_lineage_id':'WIKIMEDIA_WIKIDATA_P625_ONE_EVIDENCE_FAMILY',
            'coordinate_evidence_locator_note':'P625 point arrays are retained with source-kind/file/line/retrieval details; TSV/module/truthy are one lineage family',
            'provider_id_binding_status':'exact_source_oktmo_name_physical_type_candidate_qid',
            'coordinate_admission_status':'candidate_unreviewed','admission_allowed':False,
            'review_flags_json':'[]',
        })
    return records


def _build_raw_geokladr_matches(candidates: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """Exact-code raw 2011 GeoKLADR diagnostics; never reads the enriched crosswalk table."""
    if candidates.empty:return pd.DataFrame()
    con=duckdb.connect(str(db_path),read_only=True)
    try:
        geo=con.execute('SELECT historical_okato,name_raw,settlement_type_raw,kladr,oktmo_2011_raw,source_status,source_updated_at,latitude,longitude,coordinate_valid_russia_bbox,historical_okato_unique,source_page,source_archive_url,source_snapshot_date FROM historical_geokladr_coordinates_2011').df()
        classifier=con.execute('SELECT historical_okato,name,name_full,status,is_settlement_raw,historical_region_raw,snapshot_revision,snapshot_url,historical_okato_unique AS classifier_okato_unique FROM historical_okato_142_2009').df()
    finally:con.close()
    classifier['code_norm']=classifier.historical_okato.map(normalized_code)
    cls_by_code={k:g.to_dict('records') for k,g in classifier[classifier.code_norm.notna()].groupby('code_norm',sort=False)}
    geo['okato_norm']=geo.historical_okato.map(normalized_code); geo['oktmo_norm']=geo.oktmo_2011_raw.map(normalized_code)
    geo_by_code={}
    for key in ('oktmo_norm','okato_norm'):
        geo_by_code[key]={code:g.drop(columns=['okato_norm','oktmo_norm']).to_dict('records') for code,g in geo[geo[key].notna()].groupby(key,sort=False)}
    rows=[]
    for r in candidates.to_dict('records'):
        sid=txt(r.get('source_record_id')); keys=[]
        for route,column,key in [('source_oktmo_exact','source_oktmo_raw','oktmo_norm'),('provider_oktmo_exact','provider_oktmo_raw','oktmo_norm'),('source_okato_exact','source_okato_raw','okato_norm'),('provider_okato_exact','provider_okato_raw','okato_norm')]:
            code=normalized_code(r.get(column))
            if code:keys.append((route,key,code,r.get(column)))
        seen=set()
        for route,key,code,raw in keys:
            matches=geo_by_code.get(key,{}).get(code,[])
            for g in matches:
                token=(route,str(g.get('historical_okato')),str(g.get('kladr')),str(g.get('oktmo_2011_raw')))
                if token in seen:continue
                seen.add(token)
                ctx=cls_by_code.get(normalized_code(g.get('historical_okato')) or '',[])
                source_name=name_key(r.get('source_name')); raw_name=name_key(g.get('name_raw'))
                classifier_name_exact=any(source_name and name_key(c.get('name'))==source_name for c in ctx)
                region_norm=region_key(r.get('source_region')); classifier_region_exact=any(region_norm and region_key(c.get('historical_region_raw'))==region_norm for c in ctx)
                type_norm=type_key(r.get('source_type')); raw_type=type_key(g.get('settlement_type_raw'))
                classifier_type_exact=any(type_norm and type_key(c.get('status'))==type_norm for c in ctx)
                # For raw abbreviated types, prefer type equivalence through classifier status.
                type_exact=bool(type_norm and (raw_type==type_norm or classifier_type_exact))
                distance=haversine_km(r.get('latitude'),r.get('longitude'),g.get('latitude'),g.get('longitude'))
                rows.append({
                    'source_record_id':sid,'candidate_point_id':r.get('candidate_point_id'),'candidate_provider_family':r.get('coordinate_provider_family'),
                    'geokladr_match_route':route,'matched_candidate_code_raw':raw,'matched_candidate_code_exact_digits':code,
                    'geokladr_historical_okato_raw':g.get('historical_okato'),'geokladr_oktmo_2011_raw':g.get('oktmo_2011_raw'),
                    'geokladr_kladr_raw':g.get('kladr'),'geokladr_name_raw':g.get('name_raw'),'geokladr_type_raw':g.get('settlement_type_raw'),
                    'geokladr_source_status_raw':g.get('source_status'),'geokladr_source_updated_at_raw':g.get('source_updated_at'),
                    'geokladr_snapshot_date':g.get('source_snapshot_date'),'geokladr_latitude':g.get('latitude'),'geokladr_longitude':g.get('longitude'),
                    'geokladr_source_page':g.get('source_page'),'geokladr_source_archive_url':g.get('source_archive_url'),
                    'exact_historical_classifier_context_json':json.dumps([{k:c.get(k) for k in ['name','name_full','status','is_settlement_raw','historical_region_raw','snapshot_revision','snapshot_url','classifier_okato_unique']} for c in ctx],ensure_ascii=False),
                    'source_name_context_match':bool(source_name and (raw_name==source_name or classifier_name_exact)),
                    'source_type_context_match':type_exact,'source_region_context_match':classifier_region_exact,
                    'complete_exact_code_name_type_region_context':bool(source_name and (raw_name==source_name or classifier_name_exact) and type_exact and classifier_region_exact),
                    'candidate_to_raw_geokladr_point_distance_km':distance,
                    'point_agrees_within_0_5km_screen':bool(distance is not None and distance<=0.5),
                    'independence_note':'dated raw GeoKLADR 2011-era coordinates; exact code route preserved; crosswalk-enriched historical_geokladr_coordinate_validation table was not used',
                })
    return pd.DataFrame(rows)


def _proposal_rows(point_evidence: pd.DataFrame, family_flags: pd.DataFrame,
                   frozen_r5b: pd.DataFrame) -> pd.DataFrame:
    baseline_by_source={str(r.target_source_record_id):r._asdict() for r in frozen_r5b.itertuples(index=False)}
    flags_by_source=family_flags.set_index(family_flags.source_record_id.astype(str)).to_dict('index')
    proposals=[]
    if point_evidence.empty:return pd.DataFrame()
    for sid,g in point_evidence.groupby(point_evidence.source_record_id.astype(str),sort=True):
        recs=g.to_dict('records'); coords={point_key(r.get('latitude'),r.get('longitude')) for r in recs};coords.discard(None)
        f=flags_by_source.get(sid,{})
        p625_distinct={point_key(r.get('latitude'),r.get('longitude')) for r in recs if r.get('coordinate_provider_family')=='wikimedia_wikidata_one_evidence_family'}
        p625_distinct.discard(None)
        forced_multi=(bool(f.get('wikidata_multipoint_review_hold',False)) or len(p625_distinct)>1
                      or bool(f.get('holds')))
        choice=union_candidate_points(recs,force_hold=forced_multi)
        frozen=baseline_by_source.get(sid)
        if frozen:
            status='frozen_r5b_reviewed_coordinate_assertion'
            choice.update({'proposed_latitude':num(frozen.get('latitude')),'proposed_longitude':num(frozen.get('longitude')),
                           'point_choice_status':'frozen_published_assertion_preserved','admission_allowed':False})
        else:
            status=choice['point_choice_status']
        families=sorted({family for r in recs for family in safe_json_list(r.get('candidate_families_json'))})
        evidence_ids=sorted({txt(r.get('candidate_point_id')) for r in recs if txt(r.get('candidate_point_id'))})
        first=recs[0]
        proposals.append({
            'coordinate_candidate_id':stable_id('COORD-CANDIDATE',sid),
            'source_record_id':sid,'target_source_record_id':sid,'target_year':int(first.get('target_year') or 2021),
            'entity_component_id':f.get('entity_component_id'),'identity_graph_component_status':f.get('identity_graph_component_status'),
            'coordinate_source_record_id':first.get('coordinate_source_record_id'),
            'coordinate_source_locator_json':json.dumps(sorted({txt(r.get('coordinate_source_locator')) for r in recs if txt(r.get('coordinate_source_locator'))}),ensure_ascii=False),
            'coordinate_provider_families_json':json.dumps(sorted({txt(r.get('coordinate_provider_family')) for r in recs}),ensure_ascii=False),
            'coordinate_provider_object_ids_json':json.dumps(sorted({txt(r.get('coordinate_provider_id')) for r in recs if txt(r.get('coordinate_provider_id'))}),ensure_ascii=False),
            'provider_general_fias_ids_json':json.dumps(sorted({txt(r.get('provider_general_fias_id')) for r in recs if txt(r.get('provider_general_fias_id'))}),ensure_ascii=False),
            'settlement_provider_ids_json':json.dumps(sorted({txt(r.get('settlement_provider_id')) for r in recs if txt(r.get('settlement_provider_id'))}),ensure_ascii=False),
            'candidate_families_json':json.dumps(sorted(set(families)|set(f.get('candidate_families',[]))),ensure_ascii=False),
            'candidate_point_evidence_ids_json':json.dumps(evidence_ids),
            'source_name':first.get('source_name'),'source_type':first.get('source_type'),'source_region':first.get('source_region'),
            'source_native_id':first.get('source_native_id'),'source_file':first.get('source_file'),'source_row':first.get('source_row'),
            'source_sha256':first.get('source_sha256'),'source_oktmo_raw':first.get('source_oktmo_raw'),'source_okato_raw':first.get('source_okato_raw'),
            'population_scope':first.get('population_scope'),'proposed_latitude':choice['proposed_latitude'],'proposed_longitude':choice['proposed_longitude'],
            'distinct_coordinate_count_across_candidate_families':int(len(coords)),'wikidata_distinct_p625_point_count':int(len(p625_distinct)),
            'point_choice_status':status if frozen else choice['point_choice_status'],
            'coordinate_admission_status':'frozen_reviewed_baseline_preserved' if frozen else 'candidate_only_pending_independent_coordinate_review',
            'admission_allowed':False,'review_hash_required_for_new_mass_admission':True,
            'provider_id_binding_status':f.get('provider_id_binding_status','separate_per_family_review_required'),
            'provider_id_binding_is_coordinate_admission':False,
            'coordinate_measurement_date_unknown':True,'provider_query_receipt_missing':True,
            'coordinate_uncertainty_flags_json':json.dumps(sorted(set(f.get('holds',[]))|set(f.get('reviews',[]))),ensure_ascii=False),
            'coordinate_source_evidence_role':'modern 2021 representative point candidate; retrospective reuse requires distinct continuity inference',
        })
    return pd.DataFrame(proposals)


def build(output: Path=OUTPUT) -> dict[str,Any]:
    if output.exists():raise FileExistsError(f'immutable output already exists: {output}')
    started=time.monotonic();output.mkdir(parents=True,exist_ok=False)
    # Verify frozen manifests/receipts without rebuilding their inputs.
    v4_manifest=json.loads((V4/'manifest.json').read_text(encoding='utf-8'))
    v6_manifest=json.loads((V6/'manifest.json').read_text(encoding='utf-8'))
    v7_manifest=json.loads((V7/'manifest.json').read_text(encoding='utf-8'))
    graph_receipt=json.loads(ACCEPTED_GRAPH_RECEIPT.read_text(encoding='utf-8'))
    if graph_receipt.get('status')!='checked_rule_application_accepted':raise ValueError('accepted identity graph receipt status mismatch')
    if sha256(ACCEPTED_GRAPH)!=ACCEPTED_GRAPH_SHA256:raise ValueError('accepted graph hash mismatch')
    if sha256(R5B_COORDINATES)!=R5B_COORDINATES_SHA256:raise ValueError('R5b coordinate baseline hash mismatch')
    if graph_receipt.get('outputs',{}).get('accepted_identity_edges.parquet')!=ACCEPTED_GRAPH_SHA256:raise ValueError('accepted graph receipt output hash mismatch')
    r5b_bytes=R5B_COORDINATES.read_bytes();(output/'frozen_r5b_coordinate_admissions.csv').write_bytes(r5b_bytes)
    if sha256(output/'frozen_r5b_coordinate_admissions.csv')!=R5B_COORDINATES_SHA256:
        raise ValueError('byte-identical R5b coordinate assertion copy failed SHA verification')
    frozen_r5b=pd.read_csv(R5B_COORDINATES)
    if len(frozen_r5b)!=81:raise ValueError('frozen R5b coordinate assertions do not contain expected 81 rows')

    v4=pd.read_parquet(V4/'coordinate_candidate_rule_coverage.parquet')
    city=pd.read_parquet(V6/'city_coordinate_candidate_coverage.parquet')
    city_points=pd.read_parquet(V6/'wikidata_city_point_candidates.parquet')
    sample_a=pd.read_parquet(V7/'a_urban_level4_validation_sample.parquet')
    ledger=pd.read_parquet(LEDGER)
    if len(v4)!=155414 or v4.source_record_id.astype(str).duplicated().any():raise ValueError('v4 row coverage must be exact unique 155,414 selected rows')
    if len(city)!=1117 or city.source_record_id.astype(str).duplicated().any():raise ValueError('v6 city coverage must be unique source-city rows')
    if not sample_a.candidate_rule_family.eq('A_urban_level4_physical_code_name_point_in_region').all():raise ValueError('v7 review sample is not the A-city family')

    fam_cols=['candidate_rule_family_a_rural_exact_code_and_own_name_type','candidate_rule_family_b_strict_name_code_and_independent_context']
    provider_records=_provider_point_records(v4)
    provider_points=pd.DataFrame(provider_records)
    eligible_city_points=city_points.loc[city_points.point_coordinate_candidate_gate.fillna(False).astype(bool)].copy()
    wiki_records=_wikidata_point_records(eligible_city_points,city)
    wiki_points=pd.DataFrame(wiki_records)
    point_evidence=pd.concat([provider_points,wiki_points],ignore_index=True,sort=False) if len(provider_points) or len(wiki_points) else pd.DataFrame()
    if not point_evidence.empty and point_evidence.candidate_point_id.duplicated().any():raise ValueError('candidate point IDs are not unique')

    # Overlapping A/B/A-city/C flags collapse by source observation, while evidence points remain separate.
    all_source_ids=sorted(set(point_evidence.source_record_id.astype(str)))
    v4_ix=v4.set_index(v4.source_record_id.astype(str))
    city_ix=city.set_index(city.source_record_id.astype(str))
    quality=pd.read_parquet(BASELINE/'observation_quality.parquet',columns=[
        'source_record_id','federal_city_region_scope','provider_coordinate_conflict','duplicate_point_group_size',
        'duplicate_point','population_scope','coverage_status','is_territorial_aggregate',
        'coordinate_review_required','in_legacy_snapshot','in_audited_snapshot','screened_candidate_point',
    ])
    quality=quality.drop_duplicates('source_record_id').set_index('source_record_id').to_dict('index')
    family_rows=[]
    for sid in all_source_ids:
        families=[];holds=[];reviews=[];bind_status=[];wikidata_points=set()
        r=v4_ix.loc[sid] if sid in v4_ix.index else None
        c=city_ix.loc[sid] if sid in city_ix.index else None
        if r is not None:
            for fam,col in [('A_rural_exact_code_and_own_name_type',fam_cols[0]),('B_strict_name_code_and_independent_context',fam_cols[1])]:
                if boolv(r.get(col)):families.append(fam)
            if boolv(r.get('baseline_provider_coordinate_conflict')):holds.append('baseline_known_provider_coordinate_conflict')
            if num(r.get('provider_general_fias_duplicate_count')) and num(r.get('provider_general_fias_duplicate_count'))>1:holds.append('provider_general_fias_id_not_unique')
            if num(r.get('provider_coordinate_duplicate_count')) and num(r.get('provider_coordinate_duplicate_count'))>1:holds.append('provider_point_duplicate')
            if boolv(r.get('provider_query_receipt_missing')):reviews.append('provider_query_receipt_and_measurement_date_missing_soft_provenance')
            bind_status.append('DaData FIAS binding candidate' if boolv(r.get('source_provider_oktmo_exact_match')) else 'DaData FIAS binding not code-confirmed')
        if c is not None and boolv(c.get('candidate_rule_family_c_wikidata_physical_source_city_point')):
            families.append('C_wikidata_physical_source_city_point')
        if c is not None and boolv(c.get('candidate_rule_family_a_urban_level4_physical_code_name_point_in_region')):
            families.append('A_urban_level4_physical_code_name_point_in_region')
        if c is not None:
            if boolv(c.get('wikidata_city_any_qid_competition')):holds.append('Wikidata_QID_competition')
            if boolv(c.get('wikidata_city_any_source_code_competition')):holds.append('Wikidata_source_code_observation_competition')
            if num(c.get('wikidata_city_candidate_qid_count'))>1:holds.append('multiple_exact_QID_bindings_require_resolution')
            if boolv(c.get('wikidata_city_physical_settlement_source_gate')) is False and num(c.get('wikidata_city_pre_scope_context_inside_region_points')):
                holds.append('source_is_aggregate_or_not_physical_settlement')
            bind_status.append('Wikidata exact source-code/name/physical-type QID binding candidate' if boolv(c.get('wikidata_city_any_candidate_point_inside_source_region')) else 'Wikidata object binding unresolved')
            subset=eligible_city_points.loc[eligible_city_points.source_record_id.astype(str).eq(sid)]
            wikidata_points={point_key(r0.wikidata_latitude,r0.wikidata_longitude) for r0 in subset.itertuples(index=False)}
            wikidata_points.discard(None)
            if len(wikidata_points)>1:holds.append('multiple_distinct_P625_points_hold_all_alternatives')
            for d in eligible_city_points.loc[eligible_city_points.source_record_id.astype(str).eq(sid),'wikidata_provider_point_distance_km']:
                if num(d) is not None and num(d)>5:reviews.append('Wikidata_to_provider_distance_over_5km_review_only_large_city_context')
        q=quality.get(sid,{})
        if boolv(q.get('provider_coordinate_conflict')):holds.append('baseline_coordinate_conflict')
        if boolv(q.get('duplicate_point')) or (num(q.get('duplicate_point_group_size')) or 0)>1:holds.append('baseline_duplicate_point_review')
        families=sorted(set(families))
        # Distinct point choices only include exact eligibility-family evidence.
        family_rows.append({'source_record_id':sid,'candidate_families':families,'candidate_families_json':json.dumps(families,ensure_ascii=False),
                            'holds':sorted(set(holds)),'reviews':sorted(set(reviews)),'provider_id_binding_status':' | '.join(sorted(set(bind_status))) or 'unresolved',
                            'wikidata_multipoint_review_hold':len(wikidata_points)>1,
                            'entity_component_id':None,'identity_graph_component_status':None,
                            'population_scope':(r.get('population_scope') if r is not None else c.get('population_scope') if c is not None else None)})
    family_flags=pd.DataFrame(family_rows)

    # Add exact census metadata to candidate evidence and leave source/provider IDs in distinct columns.
    source_cols=['source_record_id','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_scope','raw_object_level','raw_object_name','raw_oktmo','oktmo','okato','raw_okato_dadata','raw_oktmo_dadata','raw_fias_id_dadata','raw_settlement_fias_id_dadata','raw_fias_level_dadata','source_locator','source_sha256','source_is_aggregate_scope']
    source_context=ledger[[c for c in source_cols if c in ledger.columns]].copy()
    source_context=source_context.drop_duplicates('source_record_id').set_index(source_context.source_record_id.astype(str)).to_dict('index')
    if not point_evidence.empty:
        enriched=[]
        for r in point_evidence.to_dict('records'):
            ctx=source_context.get(txt(r.get('source_record_id')),{})
            for key in ['source_name_raw','district_raw','municipality_raw','population','source_locator','source_sha256','source_is_aggregate_scope','raw_object_level','raw_object_name','raw_oktmo','oktmo','okato','raw_okato_dadata','raw_oktmo_dadata','raw_fias_id_dadata','raw_settlement_fias_id_dadata','raw_fias_level_dadata']:
                if key not in r or is_null(r.get(key)):r[key]=ctx.get(key)
            r['source_physical_scope_confirmed']=not boolv(ctx.get('source_is_aggregate_scope')) and norm_text(ctx.get('population_scope'))=='settlement' and norm_text(ctx.get('raw_object_level')) in {'населенный пункт','населённый пункт'}
            enriched.append(r)
        point_evidence=pd.DataFrame(enriched)

    # Raw historical GeoKLADR exact-code context only; no crosswalk-enriched validation table.
    geokladr=_build_raw_geokladr_matches(point_evidence,BASELINE_DB)
    if not geokladr.empty:
        geokladr.to_parquet(output/'raw_geokladr_exact_code_evidence.parquet',index=False)
    else:
        geokladr.to_parquet(output/'raw_geokladr_exact_code_evidence.parquet',index=False)

    graph=pd.read_parquet(ACCEPTED_GRAPH)
    graph=graph.loc[graph.relation.astype(str).eq('same_place')].copy()
    comp_by_node,component_members,adjacency=build_dsu(graph)
    years_by_component=defaultdict(lambda:defaultdict(list))
    for r in graph.itertuples(index=False):
        for source_id,year in [(txt(r.from_source_record_id),int(float(r.from_year))),(txt(r.to_source_record_id),int(float(r.to_year)))]:
            component=comp_by_node.get(source_id)
            if component:years_by_component[component][year].append(source_id)
    for row in family_rows:
        sid=row['source_record_id'];comp=comp_by_node.get(sid)
        row['entity_component_id']=comp
        row['identity_graph_component_status']='accepted_identity_component' if comp else 'no_accepted_identity_graph_edge'
    family_flags=pd.DataFrame(family_rows)
    point_evidence=point_evidence.merge(family_flags[['source_record_id','candidate_families_json','entity_component_id','identity_graph_component_status','provider_id_binding_status']],on='source_record_id',how='left',suffixes=('','_family'),validate='many_to_one')
    proposals=_proposal_rows(point_evidence,family_flags,frozen_r5b)

    # Explicitly calculate the broad exact-name/type point family but keep it out of proposals.
    name_only=v4.loc[(v4.provider_own_name_and_type_exact.fillna(False).astype(bool))
                     &(~v4.source_provider_oktmo_exact_match.fillna(False).astype(bool))
                     &v4.source_is_physical_np.fillna(False).astype(bool)
                     &v4.provider_primary_fias_level_4_or_6.fillna(False).astype(bool)
                     &v4.provider_point_valid_wgs84.fillna(False).astype(bool)].copy()
    name_only['rule_status']='held_pending_independent_rule_family_review'
    name_only['admission_allowed']=False
    name_only['hold_reason']='exact own provider name/type without exact source-provider OKTMO; no mass admission rule enabled'
    name_only_cols=[c for c in ['source_record_id','source_file','source_row','source_native_id','settlement_name','settlement_type','region_raw','population','population_scope','raw_oktmo','raw_oktmo_dadata','raw_fias_id_dadata','raw_fias_level_dadata','provider_latitude','provider_longitude','provider_general_fias_duplicate_count','provider_coordinate_duplicate_count','baseline_provider_coordinate_conflict','rule_status','hold_reason','admission_allowed'] if c in name_only.columns]
    name_only=name_only[name_only_cols]
    name_only.to_parquet(output/'name_type_without_code_rule_review_queue.parquet',index=False)

    # Attach raw candidate ids and make one proposal row per source observation.
    if not point_evidence.empty:
        point_evidence.to_parquet(output/'coordinate_point_evidence.parquet',index=False)
    else:
        point_evidence.to_parquet(output/'coordinate_point_evidence.parquet',index=False)
    if not proposals.empty:
        proposals.to_parquet(output/'coordinate_proposals.parquet',index=False)
    else:proposals.to_parquet(output/'coordinate_proposals.parquet',index=False)

    # Selected observations and aggregate flags from source audits guard propagation.
    graph_nodes=set(comp_by_node)
    source_obs_frame=pd.read_parquet(BASELINE/'source_observations.parquet')
    source_obs_frame=source_obs_frame.loc[source_obs_frame.source_record_id.astype(str).isin(graph_nodes)].copy()
    source_obs=source_obs_frame.drop_duplicates('source_record_id').set_index(source_obs_frame.source_record_id.astype(str)).to_dict('index')
    obs_quality_frame=pd.read_parquet(BASELINE/'observation_quality.parquet',columns=[
        'source_record_id','federal_city_region_scope','is_territorial_aggregate','population_scope',
        'coverage_status','coordinate_source_record_id','candidate_latitude','candidate_longitude',
        'in_legacy_snapshot','in_audited_snapshot','screened_candidate_point',
    ])
    obs_quality_frame=obs_quality_frame.loc[obs_quality_frame.source_record_id.astype(str).isin(graph_nodes)].copy()
    obs_quality=obs_quality_frame.drop_duplicates('source_record_id').set_index(obs_quality_frame.source_record_id.astype(str)).to_dict('index')
    proposals_by_source=proposals.set_index(proposals.source_record_id.astype(str)).to_dict('index') if not proposals.empty else {}
    point_lookup={}
    for sid,p in proposals_by_source.items():
        if p.get('proposed_latitude') is not None and p.get('proposed_longitude') is not None and p.get('point_choice_status') in {'single_distinct_point_candidate_pending_review','frozen_published_assertion_preserved'}:
            point_lookup[sid]=p
    # Audit potentially mis-tagged 2010 federal-city aggregates explicitly.
    # Keep physical-city records and territorial aggregates distinguishable by
    # source grain and flags; a label or population_scope alone is not enough.
    all_2010=pd.read_parquet(BASELINE/'source_observations.parquet')
    all_2010=all_2010.loc[all_2010.census_year.eq(2010)].copy()
    city_norm=all_2010.settlement_name.fillna('').map(norm_text)
    raw_name_norm=all_2010.source_name_raw.fillna('').map(norm_text)
    region_norm=all_2010.region_raw.fillna('').map(norm_text)
    moscow=city_norm.isin({'москва','город москва'}) | raw_name_norm.isin({'москва','г. москва','город москва'})
    petersburg=city_norm.isin({'санкт петербург','санкт-петербург'}) | raw_name_norm.isin({'санкт петербург','санкт-петербург','г. санкт-петербург'})
    relevant=(moscow & region_norm.str.contains('москва',regex=False)) | (petersburg & region_norm.str.contains('санкт',regex=False))
    historic_city=all_2010.loc[relevant].copy()
    historic_city['source_record_id']=historic_city.source_record_id.astype(str)
    historic_audit=[]
    for r in historic_city.to_dict('records'):
        sid=txt(r.get('source_record_id'));q=obs_quality.get(sid,{})
        historic_audit.append({
            'source_record_id':sid,'settlement_name':r.get('settlement_name'),'source_name_raw':r.get('source_name_raw'),
            'settlement_type':r.get('settlement_type'),'region_raw':r.get('region_raw'),'population':r.get('population'),
            'population_scope_source_observation':r.get('population_scope'),'coverage_status':r.get('coverage_status'),
            'in_accepted_identity_graph':sid in graph_nodes,'is_territorial_aggregate':q.get('is_territorial_aggregate'),
            'federal_city_region_scope':q.get('federal_city_region_scope'),'in_legacy_snapshot':q.get('in_legacy_snapshot'),
            'in_audited_snapshot':q.get('in_audited_snapshot'),'screened_candidate_point':q.get('screened_candidate_point'),
            'population_scope_quality':q.get('population_scope'),
            'explicit_source_aggregate_or_derived_sum':boolv(q.get('is_territorial_aggregate')) or boolv(q.get('federal_city_region_scope')) or norm_text(r.get('coverage_status')) in {'derived_sum_city_districts','federal_city_region_aggregate'},
            'modern_candidate_point_available':sid in point_lookup,
            'classification_basis':'source coverage status + observation-quality aggregate flags + accepted endpoint membership; population_scope alone is not dispositive',
        })
    pd.DataFrame(historic_audit).to_parquet(output/'2010_moscow_st_petersburg_source_grain_audit.parquet',index=False)
    year_by_node={}
    for r in graph.itertuples(index=False):
        year_by_node[txt(r.from_source_record_id)]=int(float(r.from_year))
        year_by_node[txt(r.to_source_record_id)]=int(float(r.to_year))
    propagation=[];same_year_collision_components=[]
    for component,nodes in component_members.items():
        source_2021=[sid for sid in years_by_component[component].get(2021,[]) if sid in point_lookup]
        unique_2021=sorted(set(source_2021))
        if len(unique_2021)!=1:continue
        modern_id=unique_2021[0];modern=point_lookup[modern_id]
        collision={year:sorted(set(ids)) for year,ids in years_by_component[component].items() if len(set(ids))>1}
        if collision:same_year_collision_components.append({'entity_component_id':component,'collisions_json':json.dumps(collision)})
        for node in nodes:
            row=source_obs.get(node,{})
            year=int(num(row.get('census_year')) or year_by_node.get(node,0))
            if year not in {2002,2010}:continue
            q=obs_quality.get(node,{})
            explicit_aggregate=boolv(q.get('is_territorial_aggregate')) or boolv(q.get('federal_city_region_scope'))
            source_grain_hold=(norm_text(q.get('coverage_status')) in {'derived_sum_city_districts','federal_city_region_aggregate'} or explicit_aggregate or norm_text(row.get('population_scope')) in {'federal_city_region','municipality','municipal_aggregate','region','administrative_area','territorial_aggregate'})
            links=edge_path(node,modern_id,adjacency) or []
            holds=[]
            if source_grain_hold:holds.append('historical_endpoint_explicit_aggregate_or_source-grain-hold')
            if collision:holds.append('identity_component_has_same_year_collision')
            if modern.get('point_choice_status') not in {'single_distinct_point_candidate_pending_review','frozen_published_assertion_preserved'}:holds.append('modern_point_source_not_uniquely_resolved')
            propagation.append({
                'coordinate_propagation_id':stable_id('COORD-PROP',f'{node}|{modern_id}|{modern.get("coordinate_candidate_id")}'),
                'source_record_id':node,'target_source_record_id':node,'target_year':year,'source_coordinate_source_record_id':modern_id,
                'coordinate_candidate_id':modern.get('coordinate_candidate_id'),'entity_component_id':component,
                'identity_graph_basis':'accepted_ordinary_v4_union_R5b_1162_preserved_edges',
                'identity_edge_path_decision_ids_json':json.dumps(links),'identity_path_edge_count':len(links),
                'latitude':None if holds else modern.get('proposed_latitude'),'longitude':None if holds else modern.get('proposed_longitude'),
                'claim_origin':'modern_representative_point_retrospective_inference','direct_historical_coordinate_measurement':False,
                'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,
                'temporal_continuity_status':'candidate_inference_pending_review' if not holds else 'hold',
                'coordinate_admission_status':'candidate_only_pending_coordinate_review' if not holds else 'hold',
                'admission_allowed':False,'held_reasons_json':json.dumps(holds,ensure_ascii=False),
                'historical_source_name':row.get('settlement_name'),'historical_source_type':row.get('settlement_type'),
                'historical_source_region':row.get('region_raw'),'historical_population_scope':row.get('population_scope'),
                'historical_explicit_aggregate_flag':explicit_aggregate,'historical_coverage_status':q.get('coverage_status'),
            })
    propagation=pd.DataFrame(propagation)
    propagation.to_parquet(output/'coordinate_propagation.parquet',index=False)
    pd.DataFrame(same_year_collision_components).to_parquet(output/'identity_component_same_year_collisions.parquet',index=False)

    # All 81 R5b rows remain byte-identical. A separate keyed view is diagnostic only.
    frozen_rows=frozen_r5b[['decision_id','coordinate_claim_id','target_source_record_id','target_year','coordinate_source_record_id','latitude','longitude','decision_status','decision_rule','temporal_applicability','evidence_uri','evidence_sha256']].copy()
    frozen_rows['frozen_source_file_sha256']=R5B_COORDINATES_SHA256
    frozen_rows['preserved_without_reinterpretation']=True
    frozen_rows.to_parquet(output/'frozen_r5b_coordinate_assertions.parquet',index=False)

    holds=[]
    if not proposals.empty:
        for p in proposals.to_dict('records'):
            for reason in json.loads(p.get('coordinate_uncertainty_flags_json') or '[]'):
                holds.append({'source_record_id':p.get('source_record_id'),'coordinate_candidate_id':p.get('coordinate_candidate_id'),'hold_or_review_reason':reason,'status':'review_only_no_admission'})
            if p.get('point_choice_status','').startswith('hold_'):
                holds.append({'source_record_id':p.get('source_record_id'),'coordinate_candidate_id':p.get('coordinate_candidate_id'),'hold_or_review_reason':p.get('point_choice_status'),'status':'review_only_no_admission'})
    for r in propagation.to_dict('records'):
        for reason in json.loads(r.get('held_reasons_json') or '[]'):
            holds.append({'source_record_id':r.get('source_record_id'),'coordinate_candidate_id':r.get('coordinate_candidate_id'),'hold_or_review_reason':reason,'status':'review_only_no_admission'})
    pd.DataFrame(holds).to_parquet(output/'coordinate_holds.parquet',index=False)

    # A single source observation gets exactly one proposal row, irrespective of overlapping families.
    if not proposals.empty and proposals.source_record_id.astype(str).duplicated().any():raise ValueError('proposal ledger is not one row per 2021 source record')
    if len(frozen_rows)!=81 or frozen_rows['preserved_without_reinterpretation'].ne(True).any():
        raise ValueError('frozen assertion diagnostic projection is incomplete or altered')
    if not proposals.empty and proposals.admission_allowed.fillna(True).astype(bool).any():
        raise ValueError('candidate staging must never enable new coordinate admissions')

    family_counts={}
    if not proposals.empty:
        for family in ['A_rural_exact_code_and_own_name_type','B_strict_name_code_and_independent_context','A_urban_level4_physical_code_name_point_in_region','C_wikidata_physical_source_city_point']:
            mask=proposals.candidate_families_json.map(lambda s:family in json.loads(s or '[]'))
            family_counts[family]={'unique_source_rows':int(mask.sum()),'population':int(pd.to_numeric(proposals.loc[mask,'source_record_id'].map(lambda s:source_context.get(s,{}).get('population')),errors='coerce').fillna(0).sum())}
    asset=json.loads(BASELINE_ASSET_MANIFEST.read_text(encoding='utf-8'))
    legacy_db_sha=next(a['sha256'] for a in asset['assets'] if a['name']=='legacy_database_20260929.duckdb')
    manifest={
        'status':'candidate_staging_only_no_new_coordinate_admissions','run_version':'coordinate_admission_staging_v1',
        'review_gate':{'coordinate_review_status':'pending','new_mass_admission_allowed':False,'review_hash_required_for_future_finalization':True},
        'input_manifests':{
            'v4_coordinate_packet':{'path':str(V4/'manifest.json'),'sha256':sha256(V4/'manifest.json'),'coordinate_coverage_sha256':sha256(V4/'coordinate_candidate_rule_coverage.parquet')},
            'v6_city_packet':{'path':str(V6/'manifest.json'),'sha256':sha256(V6/'manifest.json'),'city_coverage_sha256':sha256(V6/'city_coordinate_candidate_coverage.parquet'),'point_candidates_sha256':sha256(V6/'wikidata_city_point_candidates.parquet')},
            'v7_city_a_sample':{'path':str(V7/'manifest.json'),'sha256':sha256(V7/'manifest.json'),'sample_sha256':sha256(V7/'a_urban_level4_validation_sample.parquet')},
            'coordinate_ledger':{'path':str(LEDGER),'sha256':sha256(LEDGER),'rows':int(len(ledger))},
            'accepted_identity_graph':{'path':str(ACCEPTED_GRAPH),'sha256':ACCEPTED_GRAPH_SHA256,'receipt_path':str(ACCEPTED_GRAPH_RECEIPT),'receipt_sha256':sha256(ACCEPTED_GRAPH_RECEIPT),'receipt_status':graph_receipt.get('status'),'edges':int(len(graph)),'baseline_migrated_edges_preserved':int(graph_receipt.get('baseline_edges_preserved',0)),'new_distinct_edges':int(graph_receipt.get('new_distinct_edges',0))},
            'r5b_coordinate_assertions':{'path':str(R5B_COORDINATES),'sha256':R5B_COORDINATES_SHA256,'rows':int(len(frozen_r5b)),'byte_identical_copy':True},
            'raw_geokladr_database':{'path':str(BASELINE_DB),'sha256':legacy_db_sha,'raw_table':'historical_geokladr_coordinates_2011','classifier_table':'historical_okato_142_2009','enriched_crosswalk_table_used':False},
        },
        'rules':{
            'new_coordinate_status':'all new coordinates remain candidate-only pending a hash-pinned independent coordinate-family verdict',
            'family_overlap':'A rural/B/C/A-city overlap is unioned by exact source_record_id; the output proposal ledger has one row per modern selected source record, and the point-evidence ledger retains provider-specific records',
            'multiple_wikidata_points':'all alternatives are preserved; distinct P625 coordinates trigger an explicit hold; no averaging or lone nearest-point selection',
            'point_choice':'only a single distinct eligible coordinate is shown as a proposed point; differing provider coordinates are held for review; no scalar qc_geo auto-admission',
            'provider_id_separation':'coordinate_provider_id and provider_general_fias_id/settlement_provider_id are separate from source_record_id and coordinate_source_record_id; a provider-ID duplicate does not silently become a coordinate assertion',
            'r5b_81':'frozen direct assertions are copied byte-for-byte and output separately; source/status/evidence fields are not changed or generalized',
            'retrospective_reuse':'only accepted graph components may receive a 2021 point as an explicit candidate continuity inference; earlier source aggregate flags and same-year graph conflicts hold; no historical polygon or census-date/ boundary equivalence is implied',
            'country_and_scope':'P17 is not used as a veto; source aggregate/nonphysical evidence is checked before any point candidate or propagation',
        },
        'metrics':{
            'v4_unique_source_rows_with_A_or_B_candidate_point':int(len(provider_points)),
            'v6_gated_wikidata_point_evidence_rows':int(len(wiki_points)),
            'unique_2021_coordinate_proposal_rows':int(len(proposals)),
            'overlapping_family_counts_deduplicated':family_counts,
            'wikidata_rows_with_multiple_distinct_p625_coordinates':int(sum(boolv(x) for x in family_flags.wikidata_multipoint_review_hold)),
            'wikidata_multiple_point_source_row_ids_json':json.dumps(family_flags.loc[family_flags.wikidata_multipoint_review_hold,'source_record_id'].astype(str).tolist()),
            'provider_point_evidence_rows':int(len(provider_points)),'wikidata_point_evidence_rows':int(len(wiki_points)),
            'single_distinct_coordinate_candidate_rows':int(proposals.point_choice_status.eq('single_distinct_point_candidate_pending_review').sum()) if len(proposals) else 0,
            'multiple_distinct_point_hold_rows':int(proposals.point_choice_status.str.startswith('hold_').sum()) if len(proposals) else 0,
            'frozen_r5b_coordinate_assertions':int(len(frozen_r5b)),
            'raw_geokladr_exact_code_candidate_point_matches':int(len(geokladr)),
            'raw_geokladr_exact_full_context_matches':int(geokladr.complete_exact_code_name_type_region_context.sum()) if len(geokladr) else 0,
            'identity_graph_components':int(len(component_members)),'identity_graph_vertices':int(len(comp_by_node)),
            'candidate_historical_propagation_rows':int(len(propagation)),
            'candidate_historical_propagations_held':int(propagation.temporal_continuity_status.eq('hold').sum()) if len(propagation) else 0,
            'coordinate_admissions_new':0,
            'broader_exact_provider_name_type_without_code_rows_held_for_rule_family_review':int(len(name_only)),
        },
        'runtime_seconds':time.monotonic()-started,'max_rss_kib':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        'implementation_sha256':sha256(Path(__file__)),
        'outputs':{},
    }
    for file in sorted(output.iterdir()):
        if file.is_file():
            try: rows=len(pd.read_parquet(file)) if file.suffix=='.parquet' else None
            except Exception: rows=None
            manifest['outputs'][file.name]={'path':str(file),'sha256':sha256(file),'bytes':file.stat().st_size,'rows':rows}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    print(json.dumps(build(args.output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()

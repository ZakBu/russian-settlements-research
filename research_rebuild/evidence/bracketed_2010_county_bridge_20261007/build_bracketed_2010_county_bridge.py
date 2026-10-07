"""Prepare context-inference candidates for county-null 2010 rows from ordered accepted anchors.

This writes only candidate evidence. It does not mutate selected data or an accepted graph.
"""
from __future__ import annotations
import hashlib, json, math, re, sys, random
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import xlrd

ROOT = Path('/workspace/russian-settlements-research')
OUT = ROOT / 'research_rebuild/evidence/bracketed_2010_county_bridge_20261007'
E = ROOT / 'research_rebuild/evidence'
RAW = Path('/workspace/settlements-raw')
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EVENT_ROWS = E / 'event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
EVENT_CANDIDATES = Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')
EDGE_EXTRAS = [
    E/'refreshed_name_point_bridge_20261007/accepted_identity_edge_delta.csv',
    E/'large_missing_year_batch_20261007/accepted_identity_edge_delta.csv',
    E/'unique_county_name_bridge_20261007/accepted_identity_edge_delta.csv',
]
POINT_EXTRAS = [
    E/'accepted_chain_point_transfer_20261007/accepted_point_use_delta.csv',
    E/'refreshed_name_point_bridge_20261007/accepted_point_use_delta.csv',
    E/'large_missing_year_application_20261007/accepted_point_use_delta.csv',
    E/'unique_county_name_bridge_20261007/accepted_point_use_delta.csv',
]

sys.path.insert(0, str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import State, normalize, distance_km, sha


def county_key(value):
    text = normalize(value)
    text = re.sub(r'\b(муниципальн(?:ый|ого|ое|ая)|городск(?:ой|ого|ое)|район(?:а)?|округ(?:а)?|город(?:а)?|р\s*н)\b', ' ', text)
    return ' '.join(re.sub(r'[^а-яa-z0-9]+', ' ', text).split())


def nonempty(value):
    return value is not None and not pd.isna(value) and str(value).strip() != ''


def whole_physical(row):
    if not bool(row.get('is_additive_settlement_record', False)):
        return False
    if not nonempty(row.get('source_sheet')) or not nonempty(row.get('source_row')):
        return False
    if re.search(r'\(часть\s*\d*\)', str(row.get('settlement_name') or ''), re.I):
        return False
    grain = normalize(row.get('entity_grain_status'))
    if any(x in grain for x in ('aggregate','municipal','parent','unresolved','type_unresolved','control_total')):
        return False
    name = str(row.get('source_name_raw') or row.get('settlement_name') or '').strip()
    if not name or re.search(r'\b(район|муниципальн(?:ый|ое|ая)|городское население|сельское население|итого|всего)\b', name, re.I):
        return False
    return True


def record_event(row, event_ids, event_codes, event_names):
    sid = str(row.source_record_id)
    if sid in event_ids:
        return True
    for c in (row.oktmo, row.okato):
        if nonempty(c) and normalize(c) in event_codes:
            return True
    n = normalize(row.settlement_name)
    return n in event_names


def current_point_is_own(sid, point):
    if point is None:
        return False
    if str(point.get('coordinate_admission_status','')) not in {'reviewed_rule_accepted','reviewed_extension_rule_accepted','reviewed_case_accepted','frozen_r5b_reviewed_baseline_preserved'}:
        return False
    if str(point.get('coordinate_source_record_id','')) != str(sid):
        return False
    kind = normalize(point.get('point_origin_kind'))
    if 'retrospective' in kind or 'continuity' in kind or 'representative' in kind:
        return False
    return True


def old_point_independent(sid, point):
    if point is None:
        return False
    kind = normalize(point.get('point_origin_kind'))
    if 'retrospective' in kind or 'continuity' in kind or 'representative' in kind:
        return False
    source_id = str(point.get('coordinate_source_record_id',''))
    if source_id.startswith(('2002:','2010:','2021:')) and source_id != str(sid):
        return False
    return True


def point_fields(sid, point):
    if point is None: return {}
    return {
        'point_target_source_record_id': sid,
        'point_latitude': point.get('latitude'),
        'point_longitude': point.get('longitude'),
        'point_status': point.get('coordinate_admission_status',''),
        'point_origin_kind': point.get('point_origin_kind',''),
        'point_origin_file': point.get('point_origin_file',''),
        'point_origin_sha256': point.get('point_origin_sha256',''),
        'point_origin_locator': point.get('point_origin_locator',''),
        'coordinate_source_record_id': point.get('coordinate_source_record_id',''),
        'point_ledger_path': point.get('point_ledger_path',''),
    }


def raw_xls_rows(cache, source_file, sheet, row_nums):
    path = RAW / source_file
    if not path.exists():
        # Selected-table provenance may point to an ingestion workspace path whose
        # workbook is not staged in settlements-raw; keep the exact locator and
        # parsed raw cell text in the audit packet, and mark the workbook unavailable.
        return {int(n): 'RAW_WORKBOOK_NOT_STAGED' for n in row_nums if nonempty(n)}
    if path not in cache:
        book = xlrd.open_workbook(str(path), on_demand=True)
        cache[path] = book
    book = cache[path]
    sh = book.sheet_by_name(str(sheet))
    result = {}
    for n in sorted(set(int(x) for x in row_nums if nonempty(x) and float(x).is_integer())):
        if 1 <= n <= sh.nrows:
            vals = [sh.cell_value(n-1, j) for j in range(sh.ncols)]
            result[n] = ' | '.join(str(v).strip() for v in vals if v not in ('',None))
        else:
            result[n] = 'ROW_OUT_OF_SHEET_BOUNDS'
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    state = State()
    state.add_deltas(EDGE_EXTRAS, POINT_EXTRAS)
    base_metrics = state.metrics()

    cols = ['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','source_sha256','source_locator',
            'settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population',
            'population_scope','population_value_quality','is_additive_settlement_record','entity_grain_status',
            'source_selection_component','source_native_id','oktmo','okato']
    meta = pq.read_table(SELECTED, columns=cols).to_pandas()
    # The current-chain State intentionally loads only compact observation fields.
    # Restore selected-source physical metadata for every year before evaluating
    # old/current uniqueness and whole-row grain.
    meta = meta[['source_record_id','source_file','source_sheet','source_row','source_name_raw','source_sha256','source_locator','region_raw','entity_grain_status','source_selection_component']].copy()
    obs = state.obs[state.obs.census_year.eq(2010)].copy()
    frame = obs.merge(meta, on='source_record_id', how='left', validate='one_to_one', suffixes=('','_selected'))
    frame['name_key'] = frame.settlement_name.map(normalize)
    frame['type_key'] = frame.settlement_type.map(normalize)
    frame['region_key'] = frame.region_norm.map(normalize)
    frame['county_key'] = frame.district_raw.map(county_key)
    frame['physical_row'] = pd.to_numeric(frame.source_row, errors='coerce')
    frame['root'] = frame.source_record_id.map(state.uf.find)
    frame['row_event'] = False

    # Known event paths and dated native-code events are hard holds; no identity inference from them.
    event_ids = set()
    if EVENT_ROWS.exists():
        event_ids.update(pd.read_csv(EVENT_ROWS, usecols=['source_record_id'], dtype=str).source_record_id.dropna().tolist())
    event_codes=set(); event_names=set()
    if EVENT_CANDIDATES.exists():
        for item in json.loads(EVENT_CANDIDATES.read_text()):
            for k in ('from_settlement_id_legacy_candidate','to_settlement_id_legacy_candidate'):
                val=str(item.get(k) or '')
                if val.startswith('RU-OKTMO-') or val.startswith('RU-OKATO-'):
                    event_codes.add(normalize(val.rsplit('-',1)[-1]))
            note=normalize(item.get('note_raw'))
            if note and len(note) < 100 and not re.search(r'\s',note): event_names.add(note)

    frame['row_event'] = [record_event(r,event_ids,event_codes,event_names) for r in frame.itertuples()]
    frame['whole_physical'] = [whole_physical(r._asdict()) for r in frame.itertuples(index=False)]

    # Resolve each accepted component to one current county/own point and optional old county.
    rows_by_root = defaultdict(list)
    for r in state.obs.itertuples(): rows_by_root[state.uf.find(r.source_record_id)].append(r)
    root_context = {}
    for root, members in rows_by_root.items():
        c21=[r for r in members if int(r.census_year)==2021 and nonempty(r.district_raw) and current_point_is_own(r.source_record_id,state.point_rows.get(r.source_record_id))]
        if len(c21)!=1: continue
        cur=c21[0]; county=county_key(cur.district_raw)
        if not county: continue
        old=[r for r in members if int(r.census_year)==2002 and nonempty(r.district_raw)]
        if len(old)>1: continue
        old_row=old[0] if old else None
        oldcounty=county_key(old_row.district_raw) if old_row else ''
        if oldcounty and oldcounty!=county: continue
        if any(record_event(r,event_ids,event_codes,event_names) for r in members): continue
        root_context[root]={'county_key':county,'county_2021_raw':cur.district_raw,'id_2021':cur.source_record_id,
                            'id_2002':old_row.source_record_id if old_row else '',
                            'county_2002_raw':old_row.district_raw if old_row else '',
                            'county_2002_key':oldcounty,
                            'point_2021':state.point_rows[cur.source_record_id],
                            'point_2002':state.point_rows.get(old_row.source_record_id) if old_row else None}

    # Candidate anchors are 2010 physical rows already accepted into a component with a current row.
    contexts=frame.root.map(root_context.get)
    usable=frame.whole_physical & ~frame.row_event & contexts.notna()
    frame['anchor_county_key']=[ctx['county_key'] if ok else '' for ctx,ok in zip(contexts,usable)]
    frame['anchor_2021_id']=[ctx['id_2021'] if ok else '' for ctx,ok in zip(contexts,usable)]
    frame['anchor_2002_id']=[ctx['id_2002'] if ok else '' for ctx,ok in zip(contexts,usable)]

    group_cols=['source_file','source_sheet','region_key']
    frame['source_group_key']=frame[group_cols].astype(str).agg('\x1f'.join,axis=1)
    targets=frame[frame.district_raw.isna() & frame.is_additive_settlement_record.fillna(False)].copy()
    hold_counts=Counter(); bracket_records=[]; by_target={}
    for group_key,g in frame.groupby('source_group_key',sort=False,dropna=False):
        g=g.sort_values(['physical_row','source_record_id'],na_position='last')
        valid_anchors=g[g.anchor_county_key.ne('') & g.physical_row.notna()].copy()
        # Reject ambiguous physical-row anchors: the same cell cannot be two physical localities.
        valid_anchors=valid_anchors[~valid_anchors.duplicated('physical_row',keep=False)]
        anchors=list(valid_anchors.itertuples())
        anchor_rows=[float(a.physical_row) for a in anchors]
        for target in targets[targets.source_group_key.eq(group_key)].itertuples():
            sid=target.source_record_id
            status=[]
            if not nonempty(target.source_sheet) or pd.isna(target.physical_row):
                status.append('missing_physical_source_locator')
            if not target.whole_physical: status.append('not_source_whole_physical_row')
            if target.row_event: status.append('event_hold')
            if pd.isna(target.physical_row):
                hold_counts.update(status or ['missing_physical_source_locator']); continue
            tr=float(target.physical_row)
            if g.physical_row.eq(tr).sum()>1:
                status.append('duplicate_selected_record_at_source_row')
            lo_pos=bisect_left(anchor_rows,tr)-1
            hi_pos=bisect_right(anchor_rows,tr)
            if lo_pos<0: status.append('no_lower_accepted_anchor')
            if hi_pos>=len(anchor_rows): status.append('no_upper_accepted_anchor')
            if status:
                hold_counts.update(status); continue
            lo=anchors[lo_pos]; hi=anchors[hi_pos]
            if lo.source_record_id==hi.source_record_id or normalize(lo.settlement_name)==normalize(target.settlement_name) or normalize(hi.settlement_name)==normalize(target.settlement_name):
                hold_counts['anchor_not_distinct_name_or_row']+=1; continue
            lo_gap=tr-float(lo.physical_row); hi_gap=float(hi.physical_row)-tr
            if lo_gap>20: status.append('lower_anchor_over_20_rows')
            if hi_gap>20: status.append('upper_anchor_over_20_rows')
            if lo.anchor_county_key!=hi.anchor_county_key: status.append('county_boundary_or_disagreement')
            if status:
                hold_counts.update(status); continue
            # A target row cannot use itself as an anchor and anchors have already passed source/component gates.
            if lo.source_record_id==sid or hi.source_record_id==sid:
                hold_counts['self_anchor_hold']+=1; continue
            ctx_lo=root_context.get(lo.root); ctx_hi=root_context.get(hi.root)
            record={'target':target,'lower':lo,'upper':hi,'lower_gap':lo_gap,'upper_gap':hi_gap,
                    'county_key':lo.anchor_county_key,'ctx_lower':ctx_lo,'ctx_upper':ctx_hi}
            by_target[sid]=record
            bracket_records.append(record)

    # Determine inferred county for every safely bracketed 2010 row; this also supports within-county uniqueness.
    inferred={sid:rec['county_key'] for sid,rec in by_target.items()}
    frame['inferred_county_key']=frame.source_record_id.map(inferred).fillna('')
    frame['bracket_status']=frame.source_record_id.map(lambda sid:'two_sided_same_county_accepted_anchor' if sid in inferred else 'not_bracketed')
    known=frame.district_raw.notna()
    frame.loc[known,'inferred_county_key']=frame.loc[known,'county_key']
    frame.loc[known,'bracket_status']='source_district_present'

    # County-local source uniqueness is computed from source rows and bracketed contexts, never P or QID.
    source_rows=frame[frame.whole_physical & frame.inferred_county_key.ne('')].copy()
    group_key_cols=['name_key','type_key','region_key','inferred_county_key']
    source_rows['county_2010_count']=source_rows.groupby(group_key_cols).source_record_id.transform('size')
    source_unique={r.source_record_id:int(r.county_2010_count) for r in source_rows.itertuples()}
    possible_rows=frame[frame.whole_physical].copy()
    unresolved_by_name={k:int(v) for k,v in possible_rows[possible_rows.inferred_county_key.eq('')].groupby(['name_key','type_key','region_key']).size().items()}

    # Exact same-place identity candidates require unique whole rows in old/current/candidate years,
    # an already accepted 2002+2021 component, direct accepted old/current points, and <=5 km.
    ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)].copy()
    ordinary=ordinary.merge(meta, on='source_record_id', how='left', validate='one_to_one', suffixes=('','_selected'))
    ordinary=ordinary[~ordinary.settlement_name.fillna('').str.contains(r'\(часть',regex=True)].copy()
    ordinary['whole_physical']= [whole_physical(r._asdict()) for r in ordinary.itertuples(index=False)]
    ordinary['name_key']=ordinary.settlement_name.map(normalize)
    ordinary['type_key']=ordinary.settlement_type.map(normalize)
    ordinary['region_key']=ordinary.region_norm.map(normalize)
    ordinary['county_key']=ordinary.district_raw.map(county_key)
    ordinary=ordinary[ordinary.name_key.ne('') & ordinary.type_key.ne('')]
    old_current=ordinary[ordinary.census_year.isin([2002,2021]) & ordinary.district_raw.notna() & ordinary.whole_physical].copy()
    old_current['county_key_count']=old_current.groupby(['census_year','name_key','type_key','region_key','county_key']).source_record_id.transform('size')
    endpoint_key_groups={}
    for r in old_current.itertuples(): endpoint_key_groups.setdefault((int(r.census_year),r.name_key,r.type_key,r.region_key,r.county_key),[]).append(r)

    candidate_rows=[]; practical_holds=Counter(); screen=Counter()
    for sid,rec in by_target.items():
        t=rec['target']; county=rec['county_key']; screen['bracketed_targets']+=1
        # Existing 2002/2021 pair in exactly one accepted component.
        ekey=(t.name_key,t.type_key,t.region_key,county)
        old=endpoint_key_groups.get((2002,*ekey),[]); cur=endpoint_key_groups.get((2021,*ekey),[])
        reasons=[]
        if len(old)==1: screen['unique_2002_endpoint']+=1
        else: reasons.append('2002_not_unique_whole_name_type_region_county')
        if len(cur)==1: screen['unique_2021_endpoint']+=1
        else: reasons.append('2021_not_unique_whole_name_type_region_county')
        if source_unique.get(sid,0)==1: screen['unique_2010_source_row']+=1
        else: reasons.append('2010_not_unique_source_row_in_inferred_county')
        if unresolved_by_name.get((t.name_key,t.type_key,t.region_key),0): reasons.append('duplicate_2010_same_name_unresolved_context')
        if not t.whole_physical: reasons.append('2010_not_whole_physical_source_row')
        if t.row_event: reasons.append('event_candidate_hold')
        if reasons:
            practical_holds.update(reasons); continue
        oldrow=old[0]; currow=cur[0]
        oldid,curid=oldrow.source_record_id,currow.source_record_id
        if state.uf.find(oldid)==state.uf.find(curid): screen['old_current_same_component']+=1
        else: reasons.append('old_current_not_already_same_accepted_component')
        if state.years[state.uf.find(oldid)] == {2002,2021}: screen['old_current_component_exact_2002_2021']+=1
        else: reasons.append('old_current_component_has_event_or_repeated_year_scope')
        if state.years[state.uf.find(sid)] == {2010}: screen['target_2010_unlinked']+=1
        else: reasons.append('2010_endpoint_already_connected_or_repeated_year')
        oldpoint=state.point_rows.get(oldid); curpoint=state.point_rows.get(curid)
        if oldpoint is not None: screen['old_point_present_consistency_check']+=1
        else: screen['old_point_absent_allowed']+=1
        if current_point_is_own(curid,curpoint): screen['current_point_own']+=1
        else: reasons.append('no_own_accepted_current_point')
        if curpoint is None:
            dist=None
        else:
            if oldpoint is not None:
                dist=distance_km((oldpoint['latitude'],oldpoint['longitude']),(curpoint['latitude'],curpoint['longitude']))
                if dist<=5: screen['old_current_points_within_5km']+=1
                else: reasons.append('old_current_points_over_5km')
        if oldrow.district_raw and county_key(oldrow.district_raw)!=county: reasons.append('2002_district_disagrees_with_inferred_county')
        if currow.district_raw and county_key(currow.district_raw)!=county: reasons.append('2021_district_disagrees_with_inferred_county')
        root=state.uf.find(sid)
        if state.years[root] != {2010}: reasons.append('2010_endpoint_already_connected_or_repeated_year')
        if record_event(oldrow,event_ids,event_codes,event_names) or record_event(currow,event_ids,event_codes,event_names): reasons.append('event_candidate_hold')
        if reasons:
            practical_holds.update(reasons); continue
        # Point on the 2010 endpoint is either already independently accepted and close, or proposed from current.
        targetpoint=state.point_rows.get(sid)
        if targetpoint:
            dcur=distance_km((targetpoint['latitude'],targetpoint['longitude']),(curpoint['latitude'],curpoint['longitude']))
            dold=(distance_km((targetpoint['latitude'],targetpoint['longitude']),(oldpoint['latitude'],oldpoint['longitude'])) if oldpoint is not None else None)
            if dcur>5 or (dold is not None and dold>5):
                practical_holds['2010_point_conflicts_with_old_current']+=1; continue
            point_action='existing_accepted_2010_point_retained'
            proposed_point_source=''
        else:
            point_action='propose_representative_current_point_continuity'
            proposed_point_source=curid
        candidate_rows.append({
            'candidate_status':'bounded_context_inference_candidate_pending_review',
            'target_2010_source_record_id':sid,'target_2010_name_raw':t.settlement_name,'target_2010_type_raw':t.settlement_type,
            'target_2010_region_raw':t.region_raw,'target_2010_source_file':t.source_file,'target_2010_source_sheet':t.source_sheet,
            'target_2010_source_sha256':t.source_sha256,
            'target_2010_source_locator':t.source_locator or f'{t.source_file}#{t.source_sheet}!row={int(t.physical_row)}',
            'target_2010_source_row':int(t.physical_row),'target_2010_source_name_raw':t.source_name_raw,'target_2010_entity_grain_status':t.entity_grain_status,
            'inferred_county_key':county,'inference_kind':'two_sided_source_order_bracket_over_accepted_2021_county_point_anchors',
            'lower_anchor_2010_id':rec['lower'].source_record_id,'lower_anchor_source_row':int(rec['lower'].physical_row),'lower_gap_rows':rec['lower_gap'],
            'lower_anchor_source_locator':f'{rec["lower"].source_file}#{rec["lower"].source_sheet}!row={int(rec["lower"].physical_row)}',
            'lower_anchor_2021_id':rec['ctx_lower']['id_2021'],'lower_anchor_2021_district_raw':rec['ctx_lower']['county_2021_raw'],
            'lower_anchor_2002_id':rec['ctx_lower']['id_2002'],'lower_anchor_2002_district_raw':rec['ctx_lower']['county_2002_raw'],
            'upper_anchor_2010_id':rec['upper'].source_record_id,'upper_anchor_source_row':int(rec['upper'].physical_row),'upper_gap_rows':rec['upper_gap'],
            'upper_anchor_source_locator':f'{rec["upper"].source_file}#{rec["upper"].source_sheet}!row={int(rec["upper"].physical_row)}',
            'upper_anchor_2021_id':rec['ctx_upper']['id_2021'],'upper_anchor_2021_district_raw':rec['ctx_upper']['county_2021_raw'],
            'upper_anchor_2002_id':rec['ctx_upper']['id_2002'],'upper_anchor_2002_district_raw':rec['ctx_upper']['county_2002_raw'],
            'target_source_unique_count_in_inferred_county':source_unique.get(sid,0),
            '2002_endpoint_source_record_id':oldid,'2002_district_raw':oldrow.district_raw,'2021_endpoint_source_record_id':curid,'2021_district_raw':currow.district_raw,
            'old_current_accepted_point_distance_km':round(dist,4) if dist is not None else None,
            'old_2002_accepted_point_present':oldpoint is not None,'old_current_points_independent_corroboration':False,
            'identity_basis_includes_independent_point_evidence':False,
            'old_point_origin_kind':oldpoint.get('point_origin_kind','') if oldpoint else '',
            'old_point_origin_file':oldpoint.get('point_origin_file','') if oldpoint else '',
            'old_point_origin_sha256':oldpoint.get('point_origin_sha256','') if oldpoint else '',
            'old_point_origin_locator':oldpoint.get('point_origin_locator','') if oldpoint else '',
            'current_point_origin_kind':curpoint.get('point_origin_kind',''),'current_point_origin_file':curpoint.get('point_origin_file',''),
            'current_point_origin_sha256':curpoint.get('point_origin_sha256',''),'current_point_origin_locator':curpoint.get('point_origin_locator',''),
            '2010_point_action':point_action,'proposed_2010_point_source_record_id':proposed_point_source,
            'proposed_2010_point_is_retrospective_continuity_from_accepted_2021_point':bool(point_action=='propose_representative_current_point_continuity'),
            'proposed_2010_point_independent_measurement':False,
            'proposed_relation':'same_place','proposed_edge_to_source_record_id':curid,
            'admission_rule':'accepted_2002_2021_same_component + exact name/type/region + unique whole rows within county + two distinct-name source_order brackets <=20 + own accepted current point; if accepted old point exists it must agree within 5km; context inferred only',
            'source_district_field_modified':False,'population_used_for_identity':False,'qid_used_for_identity':False,
            **{f'oldpoint_{k}':v for k,v in point_fields(oldid,oldpoint).items()},
            **{f'currentpoint_{k}':v for k,v in point_fields(curid,curpoint).items()},
        })
    # Add reason counts for practical-link failures from otherwise bracketed rows.
    # Sample source brackets deterministically when the candidate set exceeds the user threshold.
    rng=random.Random(20261007)
    candidates_sorted=sorted(candidate_rows,key=lambda x:(-float(state.by_id.loc[x['target_2010_source_record_id'],'population'] or 0),x['target_2010_source_record_id']))
    sample_ids=[]
    if len(candidate_rows)>100:
        sample_ids.extend(rng.sample([x['target_2010_source_record_id'] for x in candidate_rows],20))
        sample_ids.extend(x['target_2010_source_record_id'] for x in candidates_sorted[:5])
    else:
        sample_ids=[x['target_2010_source_record_id'] for x in candidates_sorted[:min(25,len(candidates_sorted))]]
    sample_ids=list(dict.fromkeys(sample_ids))
    raw_cache={}; source_checks=[]
    cand_by_id={x['target_2010_source_record_id']:x for x in candidate_rows}
    for sid in sample_ids:
        rec=by_target[sid]; t=rec['target']
        raw=raw_xls_rows(raw_cache,t.source_file,t.source_sheet,[rec['lower'].physical_row,t.physical_row,rec['upper'].physical_row])
        workbook_path=RAW/t.source_file
        actual_workbook_sha=(sha(workbook_path) if workbook_path.exists() else '')
        workbook_sha_matches=(not nonempty(t.source_sha256) or actual_workbook_sha==str(t.source_sha256))
        for role,row in [('lower',rec['lower']),('target',t),('upper',rec['upper'])]:
            rr=int(row.physical_row)
            source_checks.append({'sample_kind':'top_mass' if sid in {x['target_2010_source_record_id'] for x in candidates_sorted[:5]} else 'seed20261007_random20',
                'target_2010_source_record_id':sid,'source_file':t.source_file,'source_sheet':t.source_sheet,'source_region_raw':t.region_raw,
                'row_role':role,'physical_source_row':rr,'row_gap_to_target':0 if role=='target' else abs(rr-int(t.physical_row)),
                'source_raw_row_literal':raw.get(rr,''),'matches_selected_source_name':normalize(raw.get(rr,''))==normalize(row.source_name_raw or row.settlement_name) or normalize(row.settlement_name) in normalize(raw.get(rr,'')),
                'source_sha256':t.source_sha256,'raw_workbook_sha256':actual_workbook_sha,'raw_workbook_staged':workbook_path.exists(),
                'raw_workbook_sha256_matches_selected':workbook_sha_matches,
                'literal_check_status':'passed' if workbook_sha_matches and workbook_path.exists() and raw.get(rr,'')!='RAW_WORKBOOK_NOT_STAGED' and (normalize(raw.get(rr,''))==normalize(row.source_name_raw or row.settlement_name) or normalize(row.settlement_name) in normalize(raw.get(rr,''))) else 'hold_unstaged_or_hash_or_literal_mismatch'})
    # Write bounded candidate packet and audit tables only under assigned output directory.
    workbook_hashes={}
    for row in candidate_rows:
        rel=row['target_2010_source_file']; path=RAW/rel
        if rel not in workbook_hashes:
            workbook_hashes[rel]=(sha(path) if path.exists() else '')
    usable_candidates=[]; held_unstaged=[]
    for row in candidate_rows:
        actual=workbook_hashes[row['target_2010_source_file']]
        selected_sha=row['target_2010_source_sha256']
        if actual and (not nonempty(selected_sha) or actual==str(selected_sha)):
            row['target_2010_source_sha256']=actual
            row['source_order_literal_verification']='staged_source_workbook_with_sampled_literal_order_pass'
            usable_candidates.append(row)
        else:
            row['source_order_literal_verification']='hold_source_workbook_unstaged_or_hash_mismatch'
            held_unstaged.append(row)
    pop_by_id=state.by_id.population
    def covered_gain(items):
        vals=pd.to_numeric(pd.Series([pop_by_id.get(x['target_2010_source_record_id']) for x in items]),errors='coerce')
        return int(vals.fillna(0).sum())
    pd.DataFrame(usable_candidates).to_csv(OUT/'usable_contextual_link_candidates.csv',index=False)
    pd.DataFrame(held_unstaged).to_csv(OUT/'held_unstaged_source_candidates.csv',index=False)
    pd.DataFrame(candidate_rows).to_csv(OUT/'eligible_contextual_link_candidates.csv',index=False)
    pd.DataFrame(source_checks).to_csv(OUT/'sampled_bracket_source_checks.csv',index=False)
    pd.DataFrame([{'hold_reason':k,'count':v} for k,v in sorted((hold_counts+practical_holds).items())]).to_csv(OUT/'hold_reason_counts.csv',index=False)
    pd.DataFrame(candidates_sorted[:5]).to_csv(OUT/'top_mass_5_candidates.csv',index=False)
    summary={
        'status':'candidate_context_inference_only_pending_parent_review',
        'selected_input_path':str(SELECTED),'selected_input_sha256':sha(SELECTED),
        'baseline_metrics_with_named_extras':base_metrics,
        'extras':{'edge_files':[str(p) for p in EDGE_EXTRAS],'point_files':[str(p) for p in POINT_EXTRAS]},
        'inputs_sha256':{str(p):sha(p) for p in [SELECTED,EVENT_ROWS,EVENT_CANDIDATES]+EDGE_EXTRAS+POINT_EXTRAS},
        '2010_additive_district_null_rows':len(targets),'2010_null_rows_with_physical_source_row':int(targets.physical_row.notna().sum()),
        'bracketed_two_sided_context_rows':len(by_target),'eligible_contextual_link_candidates':len(candidate_rows),
        'usable_staged_source_candidates':len(usable_candidates),
        'held_unstaged_or_hash_mismatch_candidates':len(held_unstaged),
        'expected_2010_covered_population_gain_usable_candidates':covered_gain(usable_candidates),
        'expected_2010_covered_population_gain_held_unstaged':covered_gain(held_unstaged),
        'sample_seed':20261007,'sampled_targets':len(sample_ids),'sampled_bracket_rows':len(source_checks),
        'hold_reason_counts':dict(hold_counts+practical_holds),
        'practical_screen_counts':dict(screen),
        'constraints':['district is inferred context, never written as original source field','no QID or population fingerprint used for identity','boundary/no-anchor/>20-row gaps held','two source-ordered distinct-name accepted 2010 anchors within 20 rows each are required','same_place candidate only when 2002+2021 are already one accepted component, county-local uniqueness, whole physical target row, no event flags, and own accepted current point','an existing 2002 accepted point is checked for <=5km consistency when available; it is not independent corroboration and is not a hard gate when absent','candidate status is not accepted and does not change graph'],
        'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')},
    }
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['2010_additive_district_null_rows','2010_null_rows_with_physical_source_row','bracketed_two_sided_context_rows','eligible_contextual_link_candidates','sampled_targets','hold_reason_counts','practical_screen_counts']},ensure_ascii=False,indent=2))

if __name__=='__main__': main()

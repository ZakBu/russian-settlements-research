#!/usr/bin/env python3
"""Stage district-ancestry context candidates from pinned 2009/2011 sources.

No identity or point admission is made here. The legacy OKATO prefix relation
is used only after the actual parent classifier row is found and validated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES
from raw_okato_classifier import read_copy
from verify_geokladr_snapshot import parse_dbf_records

BASE = Path('/workspace')
V2 = BASE / 'settlements-work/continuation_20261004/R4/stable_type_corridor_mass/review_freeze_v2'
AUDIT = BASE / 'settlements-work/continuation_20261004/R4/district_context_semantic_audit'
OUT = BASE / 'settlements-work/continuation_20261004/R4/historical_district_ancestry_recovery'
SELECTED = BASE / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EVIDENCE = BASE / 'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
GRAPH = BASE / 'settlements-work/continuation_20261004/accepted_mass_extensions/accepted_identity_edges.parquet'
POINTS = BASE / 'settlements-work/continuation_20261004/accepted_mass_extensions/accepted_point_uses.parquet'
BLOCKS = [BASE/'settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json',
          BASE/'settlements-work/continuation_20261003/mezhgorye_quarantine_decision.json',
          BASE/'settlements-work/continuation_20261003/podlipkovsky_point_hold_decision_v1.json',
          BASE/'settlements-work/continuation_20261003/rural_shared_point_quarantine_decision.json']
SQL = BASE / 'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
DBF = BASE / 'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
SEED = 20261004


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def txt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ''
    return str(v).strip()


def norm(v) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^а-яa-z0-9]+', ' ', txt(v).casefold().replace('ё', 'е'))).strip()


def region_key(v) -> str:
    x = norm(v)
    for suffix in ('область', 'край', 'республика', 'автономная область', 'автономный округ', 'город федерального значения'):
        x = re.sub(r'\b' + re.escape(suffix) + r'\b', '', x).strip()
    return x


def district_key(v) -> str:
    x = norm(v)
    # Drop only explicit, common classifier/source administrative wrappers.
    prefixes = ('муниципальный район ', 'муниципальное образование ', 'муниципальный округ ', 'городской округ ')
    for prefix in prefixes:
        if x.startswith(prefix):
            x = x[len(prefix):].strip()
            break
    suffixes = (
        'муниципальным районом', 'муниципального района', 'муниципальному району', 'муниципальный район', 'муниципальном районе',
        'муниципальным округом', 'муниципального округа', 'муниципальному округу', 'муниципальный округ', 'муниципальном округе',
        'городским округом', 'городского округа', 'городскому округу', 'городской округ', 'городском округе',
        'административным округом', 'административного округа', 'административному округу', 'административный округ',
        'районом', 'района', 'району', 'район', 'районе', 'округом', 'округа', 'округу', 'округ', 'округе',
    )
    for suffix in suffixes:
        if x.endswith(' ' + suffix):
            x = x[:-(len(suffix) + 1)].strip()
            break
    return x.strip(' "«»')


def type_key(v) -> str:
    x = norm(v)
    return {'пгт': 'поселок городского типа', 'посёлок городского типа': 'поселок городского типа'}.get(x, x)


def haversine(lat1, lon1, lat2, lon2):
    try:
        vals = [float(lat1), float(lon1), float(lat2), float(lon2)]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in vals):
        return None
    if not (-90 <= vals[0] <= 90 and -90 <= vals[2] <= 90 and -180 <= vals[1] <= 180 and -180 <= vals[3] <= 180):
        return None
    p1, p2 = math.radians(vals[0]), math.radians(vals[2])
    dp, dl = math.radians(vals[2] - vals[0]), math.radians(vals[3] - vals[1])
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a)))


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', encoding='utf-8', newline='') as f:
        fields=[]
        seen=set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key); fields.append(key)
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


class YearUF:
    def __init__(self, years):
        self.parent = {x: x for x in years}
        self.ymap = {x: {int(years[x]): x} for x in years}

    def find(self, x):
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return 'already_connected'
        for y in set(self.ymap[ra]) & set(self.ymap[rb]):
            if self.ymap[ra][y] != self.ymap[rb][y]:
                return 'year_constrained_collision'
        lo, hi = sorted((ra, rb))
        self.parent[hi] = lo
        self.ymap[lo].update(self.ymap.pop(hi))
        return 'merged'

    def component_has_point(self, x, point_ids):
        root = self.find(x)
        return any(self.find(pid) == root for pid in point_ids if pid in self.parent)


def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit(f'output dir not empty: {OUT}')
    OUT.mkdir(parents=True, exist_ok=True)
    v2summary = json.loads((V2 / 'summary.json').read_text(encoding='utf-8'))
    v2manifest = json.loads((V2 / 'freeze_manifest.json').read_text(encoding='utf-8'))
    prior_receipt = json.loads((AUDIT / 'receipt.json').read_text(encoding='utf-8'))
    audit_summary = json.loads((AUDIT / 'summary.json').read_text(encoding='utf-8'))
    for n, expected in v2manifest['files'].items():
        if sha(V2 / n) != expected:
            raise SystemExit(f'V2 frozen hash mismatch: {n}')
    audit_classified = AUDIT / 'district_context_all_8174_classified.csv'
    if sha(audit_classified) != prior_receipt['outputs']['district_context_all_8174_classified.csv']:
        raise SystemExit('semantic audit input hash mismatch')
    pins = {
        str(SELECTED): sha(SELECTED), str(EVIDENCE): sha(EVIDENCE), str(GRAPH): sha(GRAPH), str(POINTS): sha(POINTS),
        str(SQL): sha(SQL), str(DBF): sha(DBF), str(V2 / 'all_candidate_dispositions.csv'): sha(V2 / 'all_candidate_dispositions.csv'),
        str(audit_classified): sha(audit_classified),
    }
    block_ids=set()
    for bp in BLOCKS:
        actual=sha(bp); expected=v2summary['sources']['sha256'].get(str(bp))
        if expected and actual!=expected: raise SystemExit(f'quarantine pin mismatch: {bp}')
        pins[str(bp)]=actual
        obj=json.loads(bp.read_text(encoding='utf-8'))
        block_ids.update(obj.get('blocked_target_source_record_ids',[]))
        block_ids.update(obj.get('quarantine_target_source_record_ids',[]))
    for pth in (SELECTED, EVIDENCE, GRAPH, POINTS, SQL, DBF):
        exp = v2summary['sources']['sha256'].get(str(pth))
        if exp and pins[str(pth)] != exp:
            raise SystemExit(f'input pin mismatch: {pth}: {pins[str(pth)]} != {exp}')
    if pins[str(GRAPH)] != '1edc2940a27b38bb60514929f1f9c31abf7419d5e26bf1c00033204491f97557':
        raise SystemExit('accepted graph pin differs from requested current graph')

    with audit_classified.open(encoding='utf-8', newline='') as f:
        audit_rows = [r for r in csv.DictReader(f) if r['district_context_audit_class'] == 'different_named_district_context']
    if len(audit_rows) != 3142:
        raise SystemExit(f'expected 3142 genuine-name context rows, got {len(audit_rows)}')
    focus_ids={x[f'{role}_source_record_id'] for x in audit_rows for role in ('from','to')}
    focus_ids.update(txt(x.get('point_witness_2021_source_record_id')) for x in audit_rows if txt(x.get('point_witness_2021_source_record_id')))

    # Read actual full PostgreSQL COPY classifier once; six declared fields and
    # 8/11 digit width checks are enforced by the shared raw parser.
    classifier = read_copy(SQL)
    cls_by_code = defaultdict(list)
    for r in classifier.to_dict('records'):
        cls_by_code[r['historical_okato']].append(r)
    cls_rows = {c: rows[0] for c, rows in cls_by_code.items() if len(rows) == 1}
    region_by_code = defaultdict(list)
    for c, rows in cls_by_code.items():
        if re.fullmatch(r'\d{2}000000', c):
            region_by_code[c[:2]].extend(rows)
    region_rows = {c: rows[0] for c, rows in region_by_code.items() if len(rows) == 1}
    if not region_rows:
        raise SystemExit('raw classifier has no unique region-level rows')
    parent_for_child = {}
    for r in classifier.to_dict('records'):
        code = r['historical_okato']
        if len(code) in (8, 11):
            pcode = code[:5] + '000'
            parent_for_child[code] = cls_rows.get(pcode)
    # Whole-province classifier counts include every named locality record,
    # including records for which 2011 has no point.
    cls_key_counts = Counter()
    for r in classifier.to_dict('records'):
        code = r['historical_okato']
        if len(code) not in (8, 11) or r['is_settlement_raw'] != 't':
            continue
        region_row = region_rows.get(code[:2])
        if not region_row:
            continue
        key = (region_key(region_row['name_raw']), norm(r['name']), type_key(r['status']))
        cls_key_counts[key] += 1

    # Reopen and parse the complete raw DBF once; preserve one-to-one locator,
    # code, typed name and coordinate fields for all later lookups.
    dbf_meta, dbf_records = parse_dbf_records(DBF)
    dbf_by_record = {int(r['record_number_1based']): r for r in dbf_records}
    short_types = {'д': 'деревня', 'с': 'село', 'г': 'город', 'п': 'поселок', 'пгт': 'поселок городского типа',
                   'х': 'хутор', 'ст': 'станция', 'ст-ца': 'станица', 'аул': 'аул', 'м': 'местечко', 'рзд': 'железнодорожный разъезд'}
    geo_key_counts = Counter()
    for g in dbf_records:
        code = txt(g.get('historical_okato'))
        if not code or len(code) < 2:
            continue
        rr = region_rows.get(code[:2])
        if not rr:
            continue
        raw_name = txt(g.get('name_raw'))
        toks = raw_name.split(maxsplit=1)
        typ = short_types.get(toks[0].casefold(), '') if toks else ''
        nm = toks[1] if len(toks) > 1 else ''
        if nm and typ:
            geo_key_counts[(region_key(rr['name_raw']), norm(nm), type_key(typ))] += 1

    selcols = ['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw',
               'settlement_name','settlement_type','region_raw','district_raw','population','latitude','longitude','population_scope',
               'source_sha256','source_locator','source_raw_line','is_additive_settlement_record','population_value_quality',
               'entity_grain_status','name_norm','type_norm','region_norm','okato','oktmo']
    selected = pd.read_parquet(SELECTED, columns=selcols)
    selected['source_record_id'] = selected.source_record_id.astype(str)
    if selected.source_record_id.duplicated().any():
        raise SystemExit('selected source IDs are not unique')
    selected['_source_name_key']=selected.settlement_name.map(norm)
    selected['_source_type_key']=selected.settlement_type.map(type_key)
    selected['_source_region_key']=selected.region_raw.map(region_key)
    grouped=selected.groupby(['census_year','_source_name_key','_source_type_key','_source_region_key'],dropna=False).size()
    source_key_counts={tuple((int(k[0]),str(k[1]),str(k[2]),str(k[3]))):int(v) for k,v in grouped.items()}
    years=dict(zip(selected.source_record_id,selected.census_year.astype(int)))
    focus=selected[selected.source_record_id.isin(focus_ids)]
    smap = {r['source_record_id']: r for r in focus.to_dict('records')}
    import pyarrow.dataset as ds
    evdf = ds.dataset(EVIDENCE,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],
        filter=ds.field('source_record_id').isin(list(focus_ids))).to_pandas()
    evmap = {str(r.source_record_id): json.loads(r.source_evidence_json) for r in evdf.itertuples(index=False)}

    pts = pd.read_parquet(POINTS, columns=['target_source_record_id','target_year','coordinate_admission_status','latitude','longitude',
        'coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','source_file',
        'source_locator','coordinate_source','coordinate_source_file','coordinate_source_sha256'])
    pts = pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
    current_point_ids = set(pts.target_source_record_id.astype(str))
    direct_2021_pts = pts[pts.target_year == 2021]
    point_map = {}
    for row in direct_2021_pts.to_dict('records'):
        rid = str(row['target_source_record_id'])
        if rid in point_map:
            prior = point_map[rid]
            if (prior['latitude'], prior['longitude']) != (row['latitude'], row['longitude']):
                point_map[rid] = {'conflict': True}
        else:
            point_map[rid] = row

    old_code_normalizer = district_key

    # Build actual raw census source hash set for sample reopening.
    raw_root = BASE / 'settlements-raw'
    source_hashes: dict[str, dict] = {}
    excel_cache: dict[tuple[str,str], pd.DataFrame] = {}
    excel_names: dict[str,list[str]] = {}
    parquet_cache: dict[str,pd.DataFrame] = {}
    pdf_cache: dict[str,list[str]] = {}

    def sample_raw_record(edge_id, stratum, side, source_id, expected_district=''):
        sr = smap.get(source_id)
        if not sr:
            return {'edge_id': edge_id, 'sample_stratum': stratum, 'side': side, 'source_record_id': source_id, 'raw_status': 'selected_id_missing'}
        sf = txt(sr.get('source_file'))
        p = raw_root / sf
        if not p.is_file():
            return {'edge_id': edge_id, 'sample_stratum': stratum, 'side': side, 'source_record_id': source_id, 'source_file': sf, 'raw_status': 'raw_file_missing'}
        sp = str(p)
        if sp not in source_hashes:
            source_hashes[sp] = {'path': sp, 'sha256': sha(p), 'bytes': p.stat().st_size}
        rowno = int(float(sr['source_row']))
        result = {'edge_id':edge_id,'sample_stratum':stratum,'side':side,'source_record_id':source_id,'year':int(sr['census_year']),
                  'source_file':sf,'source_sheet':txt(sr.get('source_sheet')),'source_row_1based':rowno,
                  'actual_source_sha256':source_hashes[sp]['sha256'],'selected_source_sha256':txt(sr.get('source_sha256')) or None,
                  'source_native_id_opaque_retained':txt(sr.get('source_native_id')) or None,
                  'selected_name_raw':txt(sr.get('source_name_raw')),'selected_type_raw':txt(sr.get('settlement_type')),
                  'selected_region_raw':txt(sr.get('region_raw')),'selected_district_raw':txt(sr.get('district_raw')) or None,
                  'candidate_district_raw':expected_district or None,'selected_candidate_district_exact_match':txt(sr.get('district_raw'))==txt(expected_district),
                  'source_evidence_json':json.dumps(evmap.get(source_id,{}),ensure_ascii=False)}
        if sf.lower().endswith('.parquet'):
            if sp not in parquet_cache: parquet_cache[sp] = pd.read_parquet(p)
            df=parquet_cache[sp]; idx=rowno-1
            if idx<0 or idx>=len(df): result['raw_status']='record_index_out_of_range'
            else:
                raw=df.iloc[idx].to_dict()
                result.update({'raw_status':'raw_parquet_row_loaded','raw_cells_json':json.dumps({k:(None if pd.isna(v) else txt(v)) for k,v in raw.items()},ensure_ascii=False)})
        elif sf.lower().endswith('.pdf'):
            if sp not in pdf_cache:
                pdf_cache[sp]=subprocess.run(['pdftotext','-layout',str(p),'-'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True).stdout.split('\f')
            loc=json.loads(txt(sr.get('source_locator')) or '{}'); page=int(loc.get('pdf_page_1based') or rowno); line=int(loc.get('text_line_start_1based') or rowno)
            pages=pdf_cache[sp]; page_text=pages[page-1] if 1<=page<=len(pages) else ''; lines=page_text.splitlines()
            result.update({'raw_status':'raw_pdf_page_line_loaded' if page_text else 'pdf_page_missing','raw_pdf_locator_json':json.dumps(loc,ensure_ascii=False),
                           'raw_pdf_page_1based':page,'raw_pdf_line_1based':line,'raw_pdf_exact_line':lines[line-1] if 1<=line<=len(lines) else '',
                           'raw_pdf_district_locator':loc.get('raw_district'),
                           'raw_pdf_district_locator_matches_selected':bool(loc.get('raw_district') and district_key(loc.get('raw_district'))==district_key(sr.get('district_raw'))),
                           'raw_pdf_all_page_lines_json':json.dumps(lines,ensure_ascii=False)})
        else:
            sheet=txt(sr.get('source_sheet'))
            if sp not in excel_names: excel_names[sp]=pd.ExcelFile(p,engine='xlrd').sheet_names
            selector=sheet if sheet in excel_names[sp] else (int(sheet) if sheet.isdigit() else sheet)
            k=(sp,str(selector))
            if k not in excel_cache: excel_cache[k]=pd.read_excel(p,sheet_name=selector,header=None,dtype=object,engine='xlrd')
            df=excel_cache[k]; idx=rowno-1
            if idx<0 or idx>=len(df): result['raw_status']='record_index_out_of_range'
            else:
                cells=[None if pd.isna(v) else txt(v) for v in df.iloc[idx].tolist()]
                prior=[]
                for ri in range(max(0,idx-8),idx):
                    prior.append({'row_1based':ri+1,'cells':[None if pd.isna(v) else txt(v) for v in df.iloc[ri].tolist()]})
                all_district_markers=[]
                for ri in range(0,idx):
                    vals=[None if pd.isna(v) else txt(v) for v in df.iloc[ri].tolist()]
                    marker_texts=[]
                    for v in vals:
                        low=txt(v).casefold().replace('ё','е')
                        if ' - все сельское население' in low:
                            raw_head=re.split(r'\s+-\s+все сельское население',txt(v),maxsplit=1,flags=re.IGNORECASE)[0]
                            marker_texts.append({'raw_cell':v,'candidate_district_key':district_key(raw_head)})
                    if marker_texts:
                        all_district_markers.append({'row_1based':ri+1,'cells':vals,'marker_cells':marker_texts})
                selected_key=district_key(sr.get('district_raw'))
                matching=[m for m in all_district_markers if any(t['candidate_district_key']==selected_key for t in m['marker_cells']) and selected_key]
                nearest=max(matching,key=lambda m:m['row_1based']) if matching else None
                intervening=[m for m in all_district_markers if nearest and nearest['row_1based']<m['row_1based']<rowno]
                heading_status=('verified_explicit_district_header_block' if nearest and not intervening else
                                'matching_header_interrupted_by_later_district_header' if nearest else
                                'no_matching_explicit_district_header_found')
                result.update({'raw_status':'raw_excel_row_loaded','raw_cells_json':json.dumps(cells,ensure_ascii=False),
                               'raw_preceding_8_rows_json':json.dumps(prior,ensure_ascii=False),
                               'raw_district_exact_cell_columns_json':json.dumps([i for i,v in enumerate(cells) if v and v==txt(sr.get('district_raw'))]),
                               'raw_explicit_district_heading_status':heading_status,
                               'raw_matching_explicit_district_heading_json':json.dumps(nearest,ensure_ascii=False) if nearest else '',
                               'raw_intervening_district_headings_json':json.dumps(intervening,ensure_ascii=False)})
        return result

    staged=[]
    for x in audit_rows:
        reasons=[]
        code=txt(x.get('historical_classifier_okato2009_raw'))
        child=cls_rows.get(code)
        parent_code=code[:5]+'000' if len(code) in (8,11) else ''
        parent=cls_rows.get(parent_code) if parent_code else None
        region_row=region_rows.get(code[:2]) if len(code)>=2 else None
        old_endpoints=[]
        for role in ('from','to'):
            y=int(x[f'{role}_year']); rid=x[f'{role}_source_record_id']
            if y in (2002,2010):
                old_endpoints.append((role,y,rid,txt(x[f'district_{role}_raw']),smap.get(rid)))
        old_context_comparisons=[]
        for role,y,rid,district,sr in old_endpoints:
            key=district_key(district)
            old_context_comparisons.append({'role':role,'year':y,'source_record_id':rid,'source_district_raw':district or None,
                'source_row_district_matches_disposition': bool(sr is not None and txt(sr.get('district_raw'))==district),
                'source_district_key':key,'classifier_parent_name_raw':txt(parent.get('name_raw')) if parent else None,
                'classifier_parent_code':parent_code or None,'classifier_parent_key':district_key(parent.get('name_raw')) if parent else None,
                'exact_district_parent_key_match':bool(key and parent and key==district_key(parent.get('name_raw'))),
                'context_status':'unknown_blank_unasserted' if not key else ('matches_2009_classifier_ancestor' if key and parent and key==district_key(parent.get('name_raw')) else 'explicitly_differs_from_2009_ancestor')})
        has_old_match=any(c['exact_district_parent_key_match'] for c in old_context_comparisons)
        old_explicit_mismatch=any(c['source_district_raw'] and not c['exact_district_parent_key_match'] for c in old_context_comparisons)
        # Every nonblank old census district must agree with the historic 2009 parent.
        old_admin_context_ok=has_old_match and not old_explicit_mismatch
        if not old_admin_context_ok: reasons.append('old_census_district_does_not_uniquely_agree_with_raw_2009_parent')
        if any(not c['source_row_district_matches_disposition'] for c in old_context_comparisons): reasons.append('candidate_old_district_field_differs_from_selected_row')
        hierarchy_ok=bool(child and parent and len(parent_code)==8 and parent['historical_okato']==parent_code and parent['is_settlement_raw']=='f' and parent['status']=='')
        if not hierarchy_ok: reasons.append('actual_classifier_parent_row_not_valid_nonsettlement_8digit_ancestor')
        cls_exact=(bool(child) and child['is_settlement_raw']=='t' and norm(child['name'])==norm(x['name_exact_norm']) and
                   type_key(child['status'])==type_key(x['type_from_raw'])==type_key(x['type_to_raw']))
        if not cls_exact: reasons.append('raw_2009_classifier_child_name_type_code_mismatch')
        province_ok=bool(region_row and region_key(region_row['name_raw'])==region_key(x['region_from_raw']) and
                         region_key(region_row['name_raw'])==region_key(x['region_to_raw']))
        if not province_ok: reasons.append('2009_code_province_does_not_match_census_province')
        child_key=(region_key(region_row['name_raw']),norm(child['name']),type_key(child['status'])) if child and region_row else None
        classifier_unique=bool(child_key and cls_key_counts[child_key]==1)
        if not classifier_unique: reasons.append('2009_whole_province_name_type_has_competitor_including_unlocated_rows')
        # Whole source-row name/type/region keys must be unique for all observed years in the pair and for direct 2021 witness.
        source_ids=[(r,int(x[f'{r}_year'])) for r in ('from','to')]
        witness_id=txt(x.get('point_witness_2021_source_record_id'))
        if witness_id: source_ids.append(('point_witness',2021))
        source_uniqueness=[]
        for role,year in source_ids:
            rid=x['point_witness_2021_source_record_id'] if role=='point_witness' else x[f'{role}_source_record_id']
            sr=smap.get(rid)
            key=(year,norm(sr.get('settlement_name')) if sr else '',type_key(sr.get('settlement_type')) if sr else '',region_key(sr.get('region_raw')) if sr else '')
            count=int(source_key_counts.get(key,0)) if sr else 0
            source_uniqueness.append({'role':role,'source_record_id':rid,'year':year,'name_type_region_record_count':count,'unique':count==1})
        source_unique=bool(source_uniqueness) and all(u['unique'] for u in source_uniqueness)
        if not source_unique: reasons.append('source_name_type_province_not_unique_all_year_endpoints')
        # Validate the actual 2011 DBF target record against the raw 2009 classifier child.
        try: dbf_no=int(float(x['historical_geokladr_row_1based']))
        except (TypeError,ValueError): dbf_no=0
        geo=dbf_by_record.get(dbf_no)
        geo_code=txt(x.get('historical_geokladr_okato2011_raw'))
        expected_geo_code=code if len(code)==11 else (code+'000' if len(code)==8 else '')
        geo_name_raw=txt(geo.get('name_raw')) if geo else ''
        geo_type_raw=txt(geo.get('settlement_type_raw')) if geo else ''
        geo_parts=geo_name_raw.split(maxsplit=1)
        geo_typ=short_types.get(geo_parts[0].casefold(),'') if geo_parts else ''
        geo_name=geo_parts[1] if len(geo_parts)>1 else ''
        geo_key=(region_key(region_row['name_raw']),norm(geo_name),type_key(geo_typ)) if geo and region_row else None
        geo_valid=bool(geo and geo.get('deleted_marker_raw')==' ' and geo_code==expected_geo_code and
                       txt(geo.get('historical_okato'))==geo_code and norm(geo_name)==norm(child['name']) and
                       type_key(geo_typ)==type_key(child['status']) and geo_key_counts[geo_key]==1 and
                       child_key and geo_key==child_key and geo.get('latitude_from_lat') is not None and geo.get('longitude_from_long') is not None)
        if not geo_valid: reasons.append('raw_2011_dbf_not_unique_typed_same_code_classifier_point')
        # Accepted direct 2021 source-row point is rejoined by exact source ID and
        # must be the record's own origin; provider-ID binding is not asserted.
        pt=point_map.get(witness_id)
        direct_point=bool(pt and not pt.get('conflict') and pt.get('coordinate_source_record_id')==witness_id and
                          (pt.get('point_origin_kind')=='tochno_2021_dadata_raw_parquet_point' or
                           str(pt.get('point_origin_file','')).endswith('data_allsettlements_anon_156_v20251217.parquet')))
        if not direct_point: reasons.append('no_exact_accepted_direct_2021_source_coordinate')
        dist=haversine(geo.get('latitude_from_lat') if geo else None,geo.get('longitude_from_long') if geo else None,
                       pt.get('latitude') if pt and not pt.get('conflict') else None,pt.get('longitude') if pt and not pt.get('conflict') else None)
        spatial_ok=dist is not None and dist<=5.0
        if not spatial_ok: reasons.append('2011_to_direct_2021_point_distance_over_5km_or_unknown')
        # Any explicit census code is compared literally to the observed classifier
        # object / parent; opaque native row identifiers are never used here.
        code_conflicts=[]
        for role,y,rid,district,sr in old_endpoints:
            rawcode=txt(x.get(f'{role}_okato_raw'))
            if rawcode:
                normalized_code=re.sub(r'\.0+$','',rawcode)
                if normalized_code not in {code,parent_code,expected_geo_code,geo_code}:
                    code_conflicts.append({'role':role,'year':y,'source_okato_raw':rawcode})
        if code_conflicts: reasons.append('explicit_source_okato_code_contradicts_2009_2011_lineage')
        # Source-side events/collisions/aggregate statuses must be clear.
        source_holds=[]
        for role,y,rid,district,sr in old_endpoints:
            ev=evmap.get(rid,{})
            if not sr: source_holds.append(f'{role}:selected_row_missing')
            if ev.get('is_federal_aggregate') is True: source_holds.append(f'{role}:federal_aggregate')
            if ev.get('legacy_same_year_collision') is True: source_holds.append(f'{role}:legacy_same_year_collision')
            # The legacy matcher labels the exact old-vs-2021 district mismatch
            # as an identity conflict. This stage independently resolves only
            # that administrative-conflict reason through dated raw hierarchy;
            # any additional conflict reason remains a hard hold.
            try: conflict_reasons=set(json.loads(ev.get('legacy_identity_reasons') or '[]'))
            except (TypeError,ValueError): conflict_reasons={'unparsed_conflict_reason'}
            if ev.get('legacy_identity_conflict') is True and conflict_reasons-{'administrative_conflict'}:
                source_holds.append(f'{role}:legacy_identity_conflict_nonadministrative:{sorted(conflict_reasons)}')
            if ev.get('legacy_verified_successor_settlement_id'): source_holds.append(f'{role}:verified_successor_event')
            if ev.get('is_additive_settlement_record') is False: source_holds.append(f'{role}:nonadditive_source_record')
        if witness_id:
            wev=evmap.get(witness_id,{})
            if wev.get('is_federal_aggregate') is True: source_holds.append('2021_witness:federal_aggregate')
            if wev.get('legacy_same_year_collision') is True: source_holds.append('2021_witness:legacy_same_year_collision')
            try: conflict_reasons=set(json.loads(wev.get('legacy_identity_reasons') or '[]'))
            except (TypeError,ValueError): conflict_reasons={'unparsed_conflict_reason'}
            if wev.get('legacy_identity_conflict') is True and conflict_reasons-{'administrative_conflict'}:
                source_holds.append(f'2021_witness:legacy_identity_conflict_nonadministrative:{sorted(conflict_reasons)}')
            if wev.get('is_additive_settlement_record') is False: source_holds.append('2021_witness:nonadditive_source_record')
        if any(rid in block_ids for _,_,rid,_,_ in old_endpoints) or witness_id in block_ids:
            source_holds.append('hard_point_quarantine_or_blocked_target')
        if source_holds: reasons.append('source_evidence_aggregate_collision_event_or_grain_hold')
        prior_holds=json.loads(x['hold_reasons_json'])
        non_district_holds=[h for h in prior_holds if h!='explicit_source_district_context_differs']
        if non_district_holds: reasons.append('stable_v2_other_holds_present')
        # This rule only scopes a dated admin-context change; it does not assert a
        # legal rename date or population-boundary comparability.
        eligible=not reasons
        modern_id=witness_id
        modern=smap.get(modern_id) if modern_id else None
        modern_district=txt(modern.get('district_raw')) if modern else ''
        row={**x,
             'classifier_child_code_2009_raw':code or None,'classifier_child_line_1based':child['source_line_1based'] if child else None,
             'classifier_child_name_raw':child['name_raw'] if child else None,'classifier_child_name_full_raw':child['name_full'] if child else None,
             'classifier_child_status_raw':child['status'] if child else None,'classifier_child_is_settlement_raw':child['is_settlement_raw'] if child else None,
             'classifier_parent_code_2009_raw':parent_code or None,'classifier_parent_line_1based':parent['source_line_1based'] if parent else None,
             'classifier_parent_name_raw':parent['name_raw'] if parent else None,'classifier_parent_name_full_raw':parent['name_full'] if parent else None,
             'classifier_parent_is_settlement_raw':parent['is_settlement_raw'] if parent else None,
             'classifier_parent_is_valid_8digit_nonsettlement_ancestor':hierarchy_ok,
             'province_name_raw_2009':region_row['name_raw'] if region_row else None,
             'old_census_admin_context_comparisons_json':json.dumps(old_context_comparisons,ensure_ascii=False),
             'old_context_matches_2009_ancestor':old_admin_context_ok,
             'classifier_name_type_region_competitor_count_including_unlocated':cls_key_counts[child_key] if child_key else None,
             'geo2011_raw_record_number':geo.get('record_number_1based') if geo else None,
             'geo2011_raw_byte_offset':geo.get('record_byte_offset_0based') if geo else None,
             'geo2011_raw_code':geo_code or None,'geo2011_raw_name':geo_name_raw or None,'geo2011_raw_type':geo_type_raw or None,
             'geo2011_raw_latitude':geo.get('latitude_from_lat') if geo else None,'geo2011_raw_longitude':geo.get('longitude_from_long') if geo else None,
             'geo2011_whole_province_name_type_point_count':geo_key_counts[geo_key] if geo_key else None,
             'geo2011_raw_point_row_unique_same_code_typed_name_region':geo_valid,
             'direct_2021_point_origin_file':pt.get('point_origin_file') if pt and not pt.get('conflict') else None,
             'direct_2021_point_origin_sha256':pt.get('point_origin_sha256') if pt and not pt.get('conflict') else None,
             'direct_2021_point_origin_locator':pt.get('point_origin_locator') if pt and not pt.get('conflict') else None,
             'direct_2021_point_coordinate_latitude':pt.get('latitude') if pt and not pt.get('conflict') else None,
             'direct_2021_point_coordinate_longitude':pt.get('longitude') if pt and not pt.get('conflict') else None,
             'raw_geo2011_to_direct_2021_distance_km':dist,'raw_point_distance_le_5km':spatial_ok,
             'modern_2021_district_raw':modern_district or None,
             'different_2009_and_2021_admin_context_observed':bool(modern_district and parent and district_key(modern_district)!=district_key(parent['name_raw'])),
             'observed_admin_context_interpretation':'2009 ancestor label and selected 2021 district are recorded separately; legal change date unknown; boundary/population comparability not asserted',
             'source_explicit_code_conflicts_json':json.dumps(code_conflicts,ensure_ascii=False),
             'source_evidence_holds_json':json.dumps(source_holds,ensure_ascii=False),
             'stable_v2_non_district_holds_json':json.dumps(non_district_holds,ensure_ascii=False),
             'recovery_candidate_status':'eligible_candidate_for_independent_review' if eligible else 'hold',
             'recovery_hold_reasons_json':json.dumps(reasons,ensure_ascii=False),
             'identity_admitted':False,'legal_rename_claimed':False,'population_boundary_comparability_claimed':False}
        staged.append(row)

    # Select a fixed 20 high-mass + 60 seeded random edge sample from the entire
    # 3,142-row target cohort, irrespective of whether lineage appears to pass.
    sample_rows=[]
    by_edge={r['edge_id']:r for r in staged}
    top=sorted(staged,key=lambda x:max(float(x.get('from_population') or 0),float(x.get('to_population') or 0)),reverse=True)[:20]
    strata={r['edge_id']:'high_mass_top20' for r in top}
    rest=[r for r in staged if r['edge_id'] not in strata]
    rng=random.Random(SEED)
    for r in rng.sample(rest,60): strata[r['edge_id']]='seeded_random60'
    for edge_id,stratum in strata.items():
        x=by_edge[edge_id]
        for role in ('from','to'):
            rid=x[f'{role}_source_record_id']
            if int(x[f'{role}_year']) in (2002,2010):
                sample_rows.append(sample_raw_record(edge_id,stratum,role,rid,x[f'district_{role}_raw']))
        wid=txt(x.get('point_witness_2021_source_record_id'))
        if wid: sample_rows.append(sample_raw_record(edge_id,stratum,'point_witness_2021',wid,''))

    # Year-constrained simulation against the complete canonical graph. Only
    # eligible direct old-year-to-2021 edges enter the conditional graph trial.
    graph_df=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','decision_status'])
    accepted_graph=graph_df[graph_df.decision_status.isin(ACCEPTED_EDGE_STATUSES)]
    if len(accepted_graph)!=321431:
        raise SystemExit(f'accepted graph rows do not match expected 321431: {len(accepted_graph)}')
    uf=YearUF(years)
    for r in accepted_graph.itertuples(index=False):
        if r.from_source_record_id in uf.parent and r.to_source_record_id in uf.parent:
            status=uf.union(r.from_source_record_id,r.to_source_record_id)
            if status=='year_constrained_collision': raise SystemExit('baseline accepted graph has year collision')
    simulated=[]
    candidate_pairs={}
    for r in staged:
        if r['recovery_candidate_status']!='eligible_candidate_for_independent_review': continue
        # Only an exact old-to-direct-2021 pair supplies the proposed historical
        # continuity edge for this audit; 2002-to-2010 edges remain evidence only.
        if int(r['to_year'])!=2021 or int(r['from_year']) not in (2002,2010): continue
        a,b=r['from_source_record_id'],r['to_source_record_id']
        candidate_pairs.setdefault((a,b),r)
    point_ids=set(current_point_ids)
    for (a,b),r in sorted(candidate_pairs.items(),key=lambda kv:(-int(float(kv[1].get('from_population') or 0)),kv[0])):
        status=uf.union(a,b)
        simulated.append({'edge_id':r['edge_id'],'from_source_record_id':a,'to_source_record_id':b,
                          'from_year':r['from_year'],'to_year':r['to_year'],'graph_union_result':status,
                          'from_population':r['from_population'],'to_population':r['to_population'],
                          'direct_point_witness_2021_source_record_id':r['point_witness_2021_source_record_id'],
                          'identity_admitted':False})

    # Conditional coverage treats point-only historical reuse as an explicit
    # candidate continuity inference; populations and boundaries remain as published.
    staged_old_point_ids=set()
    for r in simulated:
        if r['graph_union_result'] in {'merged','already_connected'} and r['from_source_record_id'] not in point_ids:
            staged_old_point_ids.add(r['from_source_record_id'])
    for r in staged:
        r['conditional_graph_union_result']=next((z['graph_union_result'] for z in simulated if z['edge_id']==r['edge_id']), '')
        r['conditional_point_reuse_candidate']=r['from_source_record_id'] in staged_old_point_ids and r['recovery_candidate_status']=='eligible_candidate_for_independent_review'

    # Source scope guard for metrics: additive selected settlement rows only,
    # excluding explicit federal aggregates and known aggregate scopes. Stream
    # source evidence so the full 465k-row JSON column is not retained in memory.
    conditional_point_component_roots={uf.find(pid) for pid in (point_ids | staged_old_point_ids) if pid in uf.parent}
    federal_aggregate_ids=set()
    for batch in ds.dataset(EVIDENCE,format='parquet').scanner(columns=['source_record_id','source_evidence_json'],batch_size=65536).to_batches():
        ids=batch.column(0).to_pylist(); docs=batch.column(1).to_pylist()
        for rid,doc in zip(ids,docs):
            if re.search(r'"is_federal_aggregate"\s*:\s*true',doc or ''): federal_aggregate_ids.add(str(rid))
    # Baseline before any staged edges: reconstruct current component-level point
    # status from the canonical graph, not the mutated simulation above.
    base_uf=YearUF(years)
    for r in accepted_graph.itertuples(index=False):
        if r.from_source_record_id in base_uf.parent and r.to_source_record_id in base_uf.parent:
            base_uf.union(r.from_source_record_id,r.to_source_record_id)
    base_point_component_roots={base_uf.find(pid) for pid in point_ids if pid in base_uf.parent}
    metrics=defaultdict(lambda:Counter())
    for r in selected.itertuples(index=False):
        rid=str(r.source_record_id); year=int(r.census_year)
        if not bool(r.is_additive_settlement_record) or rid in federal_aggregate_ids: continue
        scope=txt(r.population_scope).casefold()
        if scope in {'federal_city_region','territorial_aggregate','regional_aggregate'}: continue
        try: pop=int(float(r.population))
        except (TypeError,ValueError): continue
        if pop<0: continue
        base_root=base_uf.find(rid); cond_root=uf.find(rid)
        cur_point=rid in point_ids; cond_point=cur_point or rid in staged_old_point_ids
        base_joint=len(base_uf.ymap[base_root])>=2 and base_root in base_point_component_roots
        cond_joint=len(uf.ymap[cond_root])>=2 and cond_root in conditional_point_component_roots
        for label,passed in [('scoped_additive_population',True),('point_covered_current',cur_point),
                             ('point_covered_conditional',cond_point),('joint_point_series_current',base_joint),
                             ('joint_point_series_conditional',cond_joint)]:
            if passed:
                metrics[(year,label)]['rows']+=1; metrics[(year,label)]['population_sum']+=pop
    coverage=[]
    for year in (2002,2010,2021):
        for label in ('scoped_additive_population','point_covered_current','point_covered_conditional','joint_point_series_current','joint_point_series_conditional'):
            c=metrics[(year,label)]
            coverage.append({'year':year,'metric':label,'rows':c['rows'],'population_sum':c['population_sum']})

    write_csv(OUT/'historical_district_ancestry_all_3142.csv',staged)
    eligible=[r for r in staged if r['recovery_candidate_status']=='eligible_candidate_for_independent_review']
    write_csv(OUT/'candidate_eligible_for_independent_review.csv',eligible)
    write_csv(OUT/'conditional_year_constrained_union.csv',simulated)
    write_csv(OUT/'fixed_80_raw_context_sample.csv',sample_rows)
    write_csv(OUT/'raw_census_file_hashes.csv',list(source_hashes.values()))
    summary={
      'status':'historical_district_ancestry_candidate_only_no_admissions',
      'scope':'3,142 rows classified as genuinely different named districts in the prior semantic audit; old census source county context is checked against the actual nonsettlement 8-digit ancestor row in the pinned 2009 classifier.',
      'raw_classifier_copy':{'sha256':pins[str(SQL)],'rows':len(classifier),'duplicate_code_values':sum(1 for rows in cls_by_code.values() if len(rows)>1),'unique_code_rows':len(cls_rows),'field_schema':['code','name_raw','name','status','name_full','is_settlement'],'code_width_counts':dict(Counter(classifier.historical_okato.str.len().astype(str))),'parent_rule':'For 8/11-digit locality code, parent candidate is first-five-code-prefix + 000; it is accepted only when that exact unique 8-digit raw SQL row exists, is nonsettlement with empty status, and agrees with explicit old-source district context.'},
      'raw_geokladr_dbf':{'sha256':pins[str(DBF)],'records':dbf_meta['record_count'],'fields':dbf_meta['fields'],'whole_file_parsed_once':True},
      'candidate_counts':{'target_rows':len(staged),'eligible_before_graph_simulation':len(eligible),'hold':len(staged)-len(eligible),'hold_reasons':dict(Counter(reason for r in staged for reason in json.loads(r['recovery_hold_reasons_json']))),'classifier_parent_context':dict(Counter('matches_2009_parent' if r['old_context_matches_2009_ancestor'] else 'does_not_match_or_unknown' for r in staged)),'valid_historical_typed_point':sum(bool(r['geo2011_raw_point_row_unique_same_code_typed_name_region']) for r in staged),'direct_2021_point_within_5km':sum(bool(r['raw_point_distance_le_5km']) for r in staged)},
      'fixed_sample':{'edges':80,'high_mass_top20':20,'seeded_random60':60,'seed':SEED,'raw_source_records':len(sample_rows),'raw_files_sha256_checked':len(source_hashes),'sample_schema':'2002/2010 raw workbook cells + 8 preceding rows where available; 2010 official PDF exact page/line text; direct 2021 raw parquet rows with full cells.'},
      'source_admin_interpretation':{'source_year_2002_classifier_year_2009_gap_years':7,'source_year_2010_classifier_year_2009_gap_years':1,'legal_change_date_claimed':False,'2021_admin_context_recorded_separately':True,'population_boundary_comparability_claimed':False,'opaque_native_source_row_ids_used_as_codes':False},
      'conditional_graph_simulation':{'accepted_graph_rows':len(accepted_graph),'accepted_graph_sha256':pins[str(GRAPH)],'eligible_old_to_2021_unique_pairs':len(simulated),'union_results':dict(Counter(r['graph_union_result'] for r in simulated)),'conditional_old_point_reuse_candidates':len(staged_old_point_ids),'metrics_are_candidate_conditional_not_admitted':True},
      'conditional_coverage_by_year':coverage,
      'inputs':pins,'outputs':{},
      'limitations':['Candidate-only review preparation; no identity or point ledger changed.','A nonblank old-census district must agree with its actual 2009 raw classifier ancestor; blank remains unasserted, never filled.','Different 2021 district text is retained as a dated administrative context observation; it is not a legal rename assertion or population-boundary equivalence.','Geographic proximity is only a corroboration alongside unique exact source/classifier identity; all eligible rows require independent review.']}
    for p in sorted(OUT.iterdir()):
        summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    receipt={'status':summary['status'],'inputs':pins,'outputs':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.name!='receipt.json'},
             'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__).resolve())}
    (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

"""Stage graph-safe mass temporal identity candidates from frozen evidence.

The script writes only its dated work directory and never edits the frozen
delivery. Exact normalized signatures are paired only when unique in both
years. Broad pairs require exact year-local unique typed signatures, additive
source rows, no source conflict, and no gross (>25 km) disagreement when both
accepted points exist; the pre-audited 1,139-pair 2002/2010 alias cohort is carried forward as a
separate rule family with its historical source, classifier, GeoKLADR and
2021 concordance evidence retained.

All rows are proposals pending independent review. Population values and
coordinates are copied only as evidence; this script asserts neither scope
comparability nor boundary comparability.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path('/workspace')
FROZEN = ROOT / 'settlements-delivery/continuation-consolidated-20261003'
AUDIT = ROOT / 'settlements-work/continuation_20261003/audit_99_20261003/older_years'
RESIDUAL = ROOT / 'settlements-work/continuation_20261004/root/full_chain_residual.parquet'
OUT = ROOT / 'settlements-work/continuation_20261004/temporal_mass'
YEARS = (2002, 2010, 2021)
STATUS_OK = {
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
}


def text(v):
    if v is None or pd.isna(v):
        return ''
    return str(v).strip()


def val(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def source_locator(row):
    given=text(row.get('source_locator'))
    if given: return given
    sheet=text(row.get('source_sheet'))
    number=val(row.get('source_row'))
    if sheet and number is not None: return f'{sheet}:row_1based={int(number)}'
    return ''


def norm_admin(value):
    """Conservatively remove declared district-kind suffixes only."""
    s=' '.join(text(value).casefold().replace('ё','е').split())
    s=re.sub(r'\s+(?:муниципальный\s+)?район$', '', s)
    s=re.sub(r'\s+муниципальный\s+район$', '', s)
    return ' '.join(s.split())


def pair_source_locator(row, suffix):
    given=text(row.get('source_locator'+suffix))
    if given: return given
    sheet=text(row.get('source_sheet'+suffix))
    number=val(row.get('source_row'+suffix))
    if sheet and number is not None: return f'{sheet}:row_1based={int(number)}'
    return ''


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    q = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, q)))


class Graph:
    def __init__(self):
        self.parent = {}
        self.years = {}
        self.members = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.years[x] = set()
            self.members[x] = {x}
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def add_node(self, x, year):
        r = self.find(x)
        self.years[r].add(int(year))

    def can_join(self, a, ya, b, yb):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False, 'already_connected'
        y1, y2 = set(self.years[ra]), set(self.years[rb])
        # Endpoint years can be absent from an accepted edge-only graph.
        y1.add(int(ya)); y2.add(int(yb))
        if y1 & y2:
            return False, 'would_create_duplicate_year_component'
        return True, ''

    def join(self, a, ya, b, yb):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        self.parent[rb] = ra
        self.years[ra] |= self.years[rb] | {int(ya), int(yb)}
        self.members[ra] |= self.members[rb]


def source_evidence_for(ids):
    if not ids:
        return {}
    p = FROZEN / 'source_evidence.parquet'
    frame = pd.read_parquet(p, columns=['source_record_id', 'source_evidence_json'],
                            filters=[('source_record_id', 'in', sorted(ids))])
    out = {}
    for r in frame.itertuples(index=False):
        out[text(r.source_record_id)] = json.loads(r.source_evidence_json)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    selected = pd.read_parquet(FROZEN / 'selected_observations.parquet', columns=[
        'source_record_id','census_year','settlement_name','settlement_type','name_norm','type_norm',
        'region_norm','region_raw','district_raw','district_norm','municipality_raw','municipality_norm',
        'population','population_scope','population_value_quality','is_additive_settlement_record',
        'entity_grain_status','source_file','source_sheet','source_sha256','source_locator','source_row','source_native_id',
        'okato','oktmo','latitude','longitude','settlement_id','source_selection_component'])
    selected = selected[selected.census_year.isin(YEARS)].copy()
    selected['source_record_id'] = selected.source_record_id.map(text)
    selected['population'] = pd.to_numeric(selected.population, errors='coerce')
    manifest = pd.read_parquet(FROZEN / 'input_manifest.parquet', columns=['path','sha256'])
    manifest_hash = dict(zip(manifest.path.map(text),manifest.sha256.map(text)))
    selected['source_sha256'] = selected.apply(
        lambda r: text(r.source_sha256) or manifest_hash.get(text(r.source_file),''), axis=1)
    # Accepted point uses carry the underlying independent-origin hashes and locators.
    points = pd.read_parquet(FROZEN / 'accepted_point_uses.parquet', columns=[
        'target_source_record_id','target_year','latitude','longitude','coordinate_admission_status',
        'coordinate_admitted','point_admitted','point_origin_file','point_origin_sha256','point_origin_locator',
        'point_origin_kind','coordinate_source','coordinate_source_sha256','coordinate_source_locator',
        'coordinate_source_file','coordinate_source_date','application_inference_kind',
        'inference_modern_point_use_target_source_record_id'])
    points = points.drop_duplicates('target_source_record_id', keep='first').copy()
    points['target_source_record_id'] = points.target_source_record_id.map(text)
    selected = selected.merge(points, left_on='source_record_id', right_on='target_source_record_id',
                              how='left', suffixes=('', '_point'))
    # Existing accepted graph only.
    edge = pd.read_parquet(FROZEN / 'accepted_identity_edges.parquet', columns=[
        'relation','decision_status','from_source_record_id','from_year','to_source_record_id','to_year','decision_id'])
    edge = edge[edge.relation.eq('same_place') & edge.decision_status.isin(STATUS_OK)]
    g = Graph()
    id_year = dict(zip(selected.source_record_id, selected.census_year.astype(int)))
    for r in edge.itertuples(index=False):
        a, b = text(r.from_source_record_id), text(r.to_source_record_id)
        ya, yb = int(r.from_year), int(r.to_year)
        g.add_node(a, ya); g.add_node(b, yb); g.join(a, ya, b, yb)
    for r in selected[['source_record_id','census_year']].itertuples(index=False):
        g.add_node(text(r.source_record_id), int(r.census_year))

    # Pre-audited 2002/2010 alias edges are verified as direct accepted edges.
    aliases = pd.read_csv(AUDIT / 'interyear_2021_continuation_priorities.csv', dtype='string').fillna('')
    alias_edge_pairs = set(zip(edge.from_source_record_id.astype(str), edge.to_source_record_id.astype(str)))
    proposals = []
    holds = []
    alias_ids = set()
    for r in aliases.to_dict('records'):
        old_id, old10 = r['from_source_record_id'], r['to_source_record_id']
        modern = r['current_2021_source_record_id']
        if not modern or int(float(r['current_2021_row_count'] or 0)) != 1:
            holds.append({'rule_family':'accepted_2002_2010_alias_to_2021','from_source_record_id':old10,
                          'to_source_record_id':modern,'hold_reason':'no_unique_2021_signature_counterpart',
                          'population_2002':r['population_2002'],'population_2010':r['population_2010']})
            continue
        pair = (old_id, old10) if (old_id, old10) in alias_edge_pairs else (old10, old_id)
        if pair not in alias_edge_pairs:
            holds.append({'rule_family':'accepted_2002_2010_alias_to_2021','from_source_record_id':old10,
                          'to_source_record_id':modern,'hold_reason':'old_pair_not_found_as_accepted_same_place_edge',
                          'population_2002':r['population_2002'],'population_2010':r['population_2010']})
            continue
        a = selected[selected.source_record_id.eq(old10)]
        b = selected[selected.source_record_id.eq(modern)]
        if len(a)!=1 or len(b)!=1:
            holds.append({'rule_family':'accepted_2002_2010_alias_to_2021','from_source_record_id':old10,
                          'to_source_record_id':modern,'hold_reason':'endpoint_missing_or_nonunique_in_frozen_observations'})
            continue
        aa, bb = a.iloc[0], b.iloc[0]
        alias_ids.add(old10); alias_ids.add(modern)
        d = None
        if val(aa.latitude_point) is not None and val(bb.latitude_point) is not None:
            d = distance_km((val(aa.latitude_point),val(aa.longitude_point)),
                            (val(bb.latitude_point),val(bb.longitude_point)))
        proposals.append({
            'rule_family':'R_A_accepted_2002_2010_alias_plus_unique_2021_signature',
            'from_source_record_id':old10,'from_year':2010,'to_source_record_id':modern,'to_year':2021,
            'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
            'rule_support_json':json.dumps({
                'accepted_2002_2010_edge_from':old_id,'accepted_2002_2010_edge_to':old10,
                'prior_edge_exists':True,'exact_raw_2010_label':r['raw_label_exact']=='True',
                'exact_raw_2010_population':r['raw_population_exact']=='True',
                'normalized_name_type_region_equal':r['normalized_name_type_region_equal']=='True',
                'raw_alias_context_supported':r['raw_alias_context_supported']=='True',
                'unique_2021_name_type_region_signature':True,
                'classifier_name_type_region_and_geo_object_support':True,
                '2021_legacy_collision':r['legacy_same_year_collision']=='False',
                '2021_legacy_identity_conflict':r['legacy_identity_conflict']=='False',
                'accepted_2021_point':bool(r['current_2021_point_kind']),
                'historic_to_2021_point_distance_km':round(d,4) if d is not None else None,
                'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False,
            },ensure_ascii=False,sort_keys=True),
            'population_from':aa.population,'population_to':bb.population,
            'point_distance_km':d,'point_from_file':text(aa.point_origin_file),
            'point_from_sha256':text(aa.point_origin_sha256),'point_from_locator':text(aa.point_origin_locator),
            'point_to_file':text(bb.point_origin_file),'point_to_sha256':text(bb.point_origin_sha256),
            'point_to_locator':text(bb.point_origin_locator),
            'source_from_file':text(aa.source_file),'source_from_sha256':text(aa.source_sha256),
            'source_from_locator':source_locator(aa),'source_to_file':text(bb.source_file),
            'source_to_sha256':text(bb.source_sha256),'source_to_locator':source_locator(bb),
            'assumptions_json':json.dumps(['same_place continuation inferred from accepted 2002-2010 identity edge plus one unique exact 2021 name/type/region counterpart',
                '2021 population is not assumed comparable to 2002/2010 populations',
                'coordinate origins are contextual evidence, not same-measurement or boundary evidence'],ensure_ascii=False),
        })

    # Exact, unique name/type/region signatures with independent point proximity.
    # This broad rule is generated per adjacent census pair; exact uniqueness is
    # checked over the complete year, not just the residual subset.
    basecols = ['source_record_id','census_year','settlement_name','name_norm','type_norm','region_norm','population',
                'population_scope','population_value_quality','is_additive_settlement_record','source_file',
                'source_sha256','source_locator','source_sheet','source_row','district_raw','district_norm','municipality_raw','municipality_norm','entity_grain_status',
                'latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator',
                'point_origin_kind','coordinate_source','coordinate_source_sha256','coordinate_source_locator',
                'coordinate_source_file','coordinate_source_date','okato','oktmo','settlement_id']
    base = selected[basecols].copy()
    # Use the coordinates from the accepted point-use ledger, not the source
    # observation's often-null direct measurement columns.
    base['latitude'] = selected.latitude_point
    base['longitude'] = selected.longitude_point
    base['name_norm'] = base.name_norm.map(text); base['type_norm'] = base.type_norm.map(text)
    base['region_norm'] = base.region_norm.map(text)
    base['district_join'] = base.district_norm.map(norm_admin)
    base['municipality_join'] = base.municipality_norm.map(text)
    base = base[(base.name_norm!='') & (base.type_norm!='') & (base.region_norm!='')]
    # Exact uniqueness buckets for each census.
    for y1,y2 in [(2002,2010),(2010,2021)]:
        left = base[base.census_year.eq(y1)].copy(); right = base[base.census_year.eq(y2)].copy()
        keys = ['region_norm','name_norm','type_norm']
        lcount=left.groupby(keys).size().rename('n_left'); rcount=right.groupby(keys).size().rename('n_right')
        unique=lcount.to_frame().join(rcount,how='inner'); unique=unique[(unique.n_left==1)&(unique.n_right==1)].reset_index()[keys]
        joined=left.merge(right,on=keys,suffixes=('_from','_to')).merge(unique,on=keys,how='inner')
        # Candidate physicality: additive selected rows, no federal-city aggregate
        # scopes. Null 2002 scope remains an explicit missing metadata field.
        joined=joined[joined.is_additive_settlement_record_from.fillna(False).astype(bool)&
                      joined.is_additive_settlement_record_to.fillna(False).astype(bool)]
        joined=joined[~joined.population_scope_from.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        joined=joined[~joined.population_scope_to.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        for row in joined.to_dict('records'):
            a,b=row['source_record_id_from'],row['source_record_id_to']
            if y1==2010 and (a in alias_ids and b in alias_ids):
                continue
            d=None
            if all(val(row.get(k)) is not None for k in ['latitude_from','longitude_from','latitude_to','longitude_to']):
                d=distance_km((val(row['latitude_from']),val(row['longitude_from'])),
                              (val(row['latitude_to']),val(row['longitude_to'])))
            if d is not None and d>25.0:
                holds.append({'rule_family':f'R_B_unique_exact_signature_stable_context_{y1}_{y2}',
                    'from_source_record_id':a,'to_source_record_id':b,'hold_reason':'accepted_point_distance_over_25km',
                    'point_distance_km':d,'population_from':row['population_from'],'population_to':row['population_to']})
                continue
            proposals.append({
                'rule_family':f'R_B_unique_exact_signature_stable_context_{y1}_{y2}',
                'from_source_record_id':a,'from_year':y1,'to_source_record_id':b,'to_year':y2,
                'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                'rule_support_json':json.dumps({
                    'unique_exact_normalized_name_type_region_signature_each_year':True,
                    'both_selected_rows_additive':True,
                    'neither_population_scope_marked_aggregate':True,
                    'accepted_point_use_each_endpoint':d is not None,'point_distance_km':round(d,4) if d is not None else None,
                    'point_agreement_status':'within_25km' if d is not None else 'not_available',
                    'exact_source_file_hash_and_row_locator_retained':True,
                    'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False,
                },ensure_ascii=False,sort_keys=True),
                'population_from':row['population_from'],'population_to':row['population_to'],
                'point_distance_km':d,'point_from_file':text(row['point_origin_file_from']),
                'point_from_sha256':text(row['point_origin_sha256_from']),
                'point_from_locator':text(row['point_origin_locator_from']),
                'point_to_file':text(row['point_origin_file_to']),
                'point_to_sha256':text(row['point_origin_sha256_to']),
                'point_to_locator':text(row['point_origin_locator_to']),
                'source_from_file':text(row['source_file_from']),'source_from_sha256':text(row['source_sha256_from']),
                'source_from_locator':pair_source_locator(row,'_from'),
                'source_to_file':text(row['source_file_to']),'source_to_sha256':text(row['source_sha256_to']),
                'source_to_locator':pair_source_locator(row,'_to'),
                'assumptions_json':json.dumps(['exact normalized name/type/region and year-local uniqueness identify one candidate',
                    'when both accepted points exist they are within 25 km; absent points remain unknown',
                    'source population periods and boundaries may differ; comparability not asserted'],ensure_ascii=False),
            })

    # Name-stable statutory type changes: require unique region/name on both
    # sides plus independently admitted points within 1 km. This captures
    # locality status transitions without treating type disagreement alone as
    # proof. Exact unique typed matches above retain priority.
    for y1,y2 in [(2002,2010),(2010,2021)]:
        left=base[base.census_year.eq(y1)].copy(); right=base[base.census_year.eq(y2)].copy()
        keys=['region_norm','name_norm']
        lc=left.groupby(keys).size().rename('nl'); rc=right.groupby(keys).size().rename('nr')
        uq=lc.to_frame().join(rc,how='inner'); uq=uq[(uq.nl==1)&(uq.nr==1)].reset_index()[keys]
        joined=left.merge(right,on=keys,suffixes=('_from','_to')).merge(uq,on=keys,how='inner')
        joined=joined[joined.type_norm_from.ne(joined.type_norm_to)]
        joined=joined[joined.is_additive_settlement_record_from.fillna(False).astype(bool)&
                      joined.is_additive_settlement_record_to.fillna(False).astype(bool)]
        joined=joined[~joined.population_scope_from.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        joined=joined[~joined.population_scope_to.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        type_evidence=source_evidence_for(set(joined.source_record_id_from.map(text))|
                                          set(joined.source_record_id_to.map(text)))
        for row in joined.to_dict('records'):
            a,b=row['source_record_id_from'],row['source_record_id_to']
            d=None
            if all(val(row.get(k)) is not None for k in ['latitude_from','longitude_from','latitude_to','longitude_to']):
                d=distance_km((val(row['latitude_from']),val(row['longitude_from'])),
                              (val(row['latitude_to']),val(row['longitude_to'])))
            district_a=text(row.get('district_norm_from')); district_b=text(row.get('district_norm_to'))
            municipality_a=text(row.get('municipality_norm_from')); municipality_b=text(row.get('municipality_norm_to'))
            admin_match=bool(district_a and district_b and district_a==district_b) or \
                        bool(municipality_a and municipality_b and municipality_a==municipality_b)
            ea,eb=type_evidence.get(a,{}),type_evidence.get(b,{})
            legacy_pointer=(text(ea.get('legacy_matched_to_source_record_id'))==b or
                            text(eb.get('legacy_matched_to_source_record_id'))==a)
            spatial_match=d is not None and d<=1.0
            if d is not None and d>25.0:
                holds.append({'rule_family':f'R_C_unique_name_region_type_transition_{y1}_{y2}',
                    'from_source_record_id':a,'to_source_record_id':b,'hold_reason':'accepted_point_distance_over_25km',
                    'point_distance_km':d,'population_from':row['population_from'],'population_to':row['population_to']})
                continue
            if not (spatial_match or admin_match or legacy_pointer):
                holds.append({'rule_family':f'R_C_unique_name_region_type_transition_{y1}_{y2}',
                    'from_source_record_id':a,'to_source_record_id':b,
                    'hold_reason':'type_transition_lacks_close_point_matching_admin_or_direct_legacy_context',
                    'point_distance_km':d,'population_from':row['population_from'],'population_to':row['population_to']})
                continue
            proposals.append({
                'rule_family':f'R_C_unique_name_region_type_transition_with_admin_or_pointer_or_close_point_{y1}_{y2}',
                'from_source_record_id':row['source_record_id_from'],'from_year':y1,
                'to_source_record_id':row['source_record_id_to'],'to_year':y2,
                'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                'rule_support_json':json.dumps({'unique_exact_normalized_name_region_signature_each_year':True,
                    'normalized_type_changed':True,'both_selected_rows_additive':True,
                    'neither_population_scope_marked_aggregate':True,'accepted_point_use_each_endpoint':d is not None,
                    'point_distance_km':round(d,4) if d is not None else None,
                    'source_admin_match':admin_match,'direct_legacy_endpoint_pointer':legacy_pointer,
                    'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False},
                    ensure_ascii=False,sort_keys=True),
                'population_from':row['population_from'],'population_to':row['population_to'],
                'point_distance_km':d,'point_from_file':text(row['point_origin_file_from']),
                'point_from_sha256':text(row['point_origin_sha256_from']),
                'point_from_locator':text(row['point_origin_locator_from']),
                'point_to_file':text(row['point_origin_file_to']),
                'point_to_sha256':text(row['point_origin_sha256_to']),
                'point_to_locator':text(row['point_origin_locator_to']),
                'source_from_file':text(row['source_file_from']),'source_from_sha256':text(row['source_sha256_from']),
                'source_from_locator':pair_source_locator(row,'_from'),
                'source_to_file':text(row['source_file_to']),'source_to_sha256':text(row['source_sha256_to']),
                'source_to_locator':pair_source_locator(row,'_to'),
                'assumptions_json':json.dumps(['name and region are exact and year-local unique while the settlement status changed',
                    'same historical admin context, a direct legacy endpoint pointer plus name evidence, or accepted points within one kilometer support continuity',
                    'population periods and boundaries remain separately interpreted'],ensure_ascii=False),
            })

    # Explicit source-recorded future aliases in parentheses, e.g. “old name
    # (с 2016 г. новое имя)”. The alias phrase itself must exactly match one
    # unique later normalized name in the same region; spatial proximity and
    # point provenance are retained as corroboration.
    rename_re=re.compile(r'\(\s*с\s*(?:19|20)\d{2}\s*г?\.?\s*([^()]+?)\s*\)',re.I)
    def norm_local(v):
        return ' '.join(text(v).casefold().replace('ё','е').split())
    for y1,y2 in [(2002,2010),(2010,2021)]:
        left=base[base.census_year.eq(y1)].copy(); right=base[base.census_year.eq(y2)].copy()
        if y1==2002:
            left_counts=left.groupby(['region_norm','name_norm','type_norm']).size().to_dict()
            for later in right.to_dict('records'):
                if not rename_re.search(text(later.get('settlement_name'))): continue
                former=norm_local(text(later.get('settlement_name')).split('(',1)[0])
                prior=left[(left.region_norm.eq(later['region_norm']))&
                           (left.name_norm.eq(former))&
                           (left.type_norm.eq(later['type_norm']))]
                if len(prior)!=1 or left_counts.get((later['region_norm'],former,later['type_norm']),0)!=1: continue
                earlier=prior.iloc[0]
                if not (bool(earlier['is_additive_settlement_record']) and bool(later['is_additive_settlement_record'])): continue
                if any('federal_city_region' in text(x).casefold() or 'aggregate' in text(x).casefold()
                       for x in (earlier.get('population_scope'),later.get('population_scope'))): continue
                d=None
                if all(val(x) is not None for x in (earlier.get('latitude'),earlier.get('longitude'),later.get('latitude'),later.get('longitude'))):
                    d=distance_km((val(earlier['latitude']),val(earlier['longitude'])),
                                  (val(later['latitude']),val(later['longitude'])))
                if d is not None and d>25.0:
                    holds.append({'rule_family':'R_D_explicit_parenthetical_preserves_prior_name_2002_2010',
                        'from_source_record_id':earlier['source_record_id'],'to_source_record_id':later['source_record_id'],
                        'hold_reason':'explicit_alias_point_disagreement_over_25km','point_distance_km':d,
                        'population_from':earlier['population'],'population_to':later['population']})
                    continue
                proposals.append({
                    'rule_family':'R_D_explicit_parenthetical_preserves_prior_name_2002_2010',
                    'from_source_record_id':earlier['source_record_id'],'from_year':2002,
                    'to_source_record_id':later['source_record_id'],'to_year':2010,
                    'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                    'rule_support_json':json.dumps({'2010_source_label_explicitly_retains_prior_2002_name_before_parenthetical':former,
                        'same_region_norm':True,'same_normalized_type':True,'unique_prior_name_type_region':True,
                        'both_selected_rows_additive':True,'accepted_point_use_each_endpoint':d is not None,
                        'point_distance_km':round(d,4) if d is not None else None,
                        'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False},
                        ensure_ascii=False,sort_keys=True),
                    'population_from':earlier['population'],'population_to':later['population'],'point_distance_km':d,
                    'point_from_file':text(earlier['point_origin_file']),'point_from_sha256':text(earlier['point_origin_sha256']),
                    'point_from_locator':text(earlier['point_origin_locator']),'point_to_file':text(later['point_origin_file']),
                    'point_to_sha256':text(later['point_origin_sha256']),'point_to_locator':text(later['point_origin_locator']),
                    'source_from_file':text(earlier['source_file']),'source_from_sha256':text(earlier['source_sha256']),
                    'source_from_locator':source_locator(earlier),'source_to_file':text(later['source_file']),
                    'source_to_sha256':text(later['source_sha256']),'source_to_locator':source_locator(later),
                    'assumptions_json':json.dumps(['the later source label explicitly carries forward the earlier literal name and adds a dated future name',
                        'same region and typed locality are uniquely identified in both censuses',
                        'no population or boundary comparability inferred'],ensure_ascii=False),
                })
        right_counts=right.groupby(['region_norm','name_norm']).size().to_dict()
        left_alias_rows=[]
        for row in left.to_dict('records'):
            m=rename_re.search(text(row.get('settlement_name')))
            alias=norm_local(m.group(1)) if m else ''
            if alias: row['_explicit_alias_norm']=alias;left_alias_rows.append(row)
        for row in left_alias_rows:
            matches=right[(right.region_norm.eq(row['region_norm'])) & (right.name_norm.eq(row['_explicit_alias_norm']))]
            if len(matches)!=1 or right_counts.get((row['region_norm'],row['_explicit_alias_norm']),0)!=1: continue
            target=matches.iloc[0]
            if not (bool(row['is_additive_settlement_record']) and bool(target['is_additive_settlement_record'])): continue
            if any('federal_city_region' in text(x).casefold() or 'aggregate' in text(x).casefold()
                   for x in (row.get('population_scope'),target.get('population_scope'))): continue
            d=None
            if all(val(x) is not None for x in (row.get('latitude'),row.get('longitude'),target.get('latitude'),target.get('longitude'))):
                d=distance_km((val(row['latitude']),val(row['longitude'])),
                              (val(target['latitude']),val(target['longitude'])))
            if d is not None and d>25.0:
                holds.append({'rule_family':f'R_D_explicit_parenthetical_future_alias_{y1}_{y2}',
                    'from_source_record_id':row['source_record_id'],'to_source_record_id':target['source_record_id'],
                    'hold_reason':'explicit_alias_point_disagreement_over_25km','point_distance_km':d,
                    'population_from':row['population'],'population_to':target['population']})
                continue
            proposals.append({
                'rule_family':f'R_D_explicit_parenthetical_future_alias_{y1}_{y2}',
                'from_source_record_id':row['source_record_id'],'from_year':y1,
                'to_source_record_id':target['source_record_id'],'to_year':y2,
                'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                'rule_support_json':json.dumps({'source_recorded_future_name_alias_exactly_matches_later_name':row['_explicit_alias_norm'],
                    'same_region_norm':True,'unique_source_and_target_name_region':True,
                    'source_type':row['type_norm'],'target_type':target['type_norm'],
                    'both_selected_rows_additive':True,'accepted_point_use_each_endpoint':d is not None,
                    'point_distance_km':round(d,4) if d is not None else None,
                    'population_scope_comparability_asserted':False,
                    'boundary_comparability_asserted':False},ensure_ascii=False,sort_keys=True),
                'population_from':row['population'],'population_to':target['population'],'point_distance_km':d,
                'point_from_file':text(row['point_origin_file']),'point_from_sha256':text(row['point_origin_sha256']),
                'point_from_locator':text(row['point_origin_locator']),'point_to_file':text(target['point_origin_file']),
                'point_to_sha256':text(target['point_origin_sha256']),'point_to_locator':text(target['point_origin_locator']),
                'source_from_file':text(row['source_file']),'source_from_sha256':text(row['source_sha256']),
                'source_from_locator':source_locator(row),'source_to_file':text(target['source_file']),
                'source_to_sha256':text(target['source_sha256']),'source_to_locator':source_locator(target),
                'assumptions_json':json.dumps(['later alias is explicitly recorded in the earlier selected source label',
                    'alias matches one unique later locality in the same region',
                    'accepted point origins have no gross (>25 km) disagreement when both are available; no population or boundary comparability inferred'],ensure_ascii=False),
            })

    # Legacy projected settlement-ID crosswalk as corroboration: exact shared
    # RU-OKTMO pointer, unique within each year, exact region, and either an
    # unchanged typed name or two accepted point uses within 1 km. The pointer
    # alone is never enough to stage a changed-name/type pair.
    projected=pd.read_parquet(FROZEN/'legacy_availability_projected_r5.parquet',
        columns=['source_record_id','settlement_id','legacy_source_record_id_before_publication_binding',
                 'legacy_availability_projection_basis'])
    projected=projected[projected.source_record_id.str.startswith(('2002:','2010:'))].copy()
    projected['source_record_id']=projected.source_record_id.map(text)
    projected['settlement_id']=projected.settlement_id.map(text)
    for y1,y2 in [(2002,2010),(2010,2021)]:
        old=base[base.census_year.eq(y1)].merge(projected[['source_record_id','settlement_id','legacy_source_record_id_before_publication_binding',
            'legacy_availability_projection_basis']],on='source_record_id',how='inner',suffixes=('','_projection'))
        new=base[base.census_year.eq(y2)].copy()
        idcol='settlement_id_projection'
        if idcol not in old.columns: idcol='settlement_id'
        old=old[old[idcol].str.startswith('RU-OKTMO-',na=False)]
        new=new[new.settlement_id.fillna('').str.startswith('RU-OKTMO-')]
        oc=old.groupby(idcol).size(); nc=new.groupby('settlement_id').size()
        unique_codes=set(oc[oc.eq(1)].index.map(text)) & set(nc[nc.eq(1)].index.map(text))
        if not unique_codes: continue
        matches=old.merge(new,left_on=idcol,right_on='settlement_id',suffixes=('_from','_to'))
        matches=matches[matches[idcol].map(text).isin(unique_codes)]
        matches=matches[matches.region_norm_from.eq(matches.region_norm_to)]
        matches=matches[matches.is_additive_settlement_record_from.fillna(False).astype(bool)&
                        matches.is_additive_settlement_record_to.fillna(False).astype(bool)]
        matches=matches[~matches.population_scope_from.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        matches=matches[~matches.population_scope_to.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        for row in matches.to_dict('records'):
            name_equal=text(row['name_norm_from'])==text(row['name_norm_to'])
            type_equal=text(row['type_norm_from'])==text(row['type_norm_to'])
            d=None
            if all(val(row.get(k)) is not None for k in ['latitude_from','longitude_from','latitude_to','longitude_to']):
                d=distance_km((val(row['latitude_from']),val(row['longitude_from'])),
                              (val(row['latitude_to']),val(row['longitude_to'])))
            if not (name_equal and type_equal) and not (d is not None and d<=1.0):
                if (not name_equal or not type_equal):
                    holds.append({'rule_family':f'R_F_unique_legacy_RU_OKTMO_id_plus_region_{y1}_{y2}',
                        'from_source_record_id':row['source_record_id_from'],'to_source_record_id':row['source_record_id_to'],
                        'hold_reason':'projected_code_name_or_type_difference_lacks_point_agreement_within_1km',
                        'point_distance_km':d,'population_from':row['population_from'],'population_to':row['population_to']})
                continue
            proposals.append({
                'rule_family':f'R_F_unique_legacy_RU_OKTMO_id_plus_region_and_name_or_point_{y1}_{y2}',
                'from_source_record_id':row['source_record_id_from'],'from_year':y1,
                'to_source_record_id':row['source_record_id_to'],'to_year':y2,
                'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                'rule_support_json':json.dumps({'same_literal_projected_RU_OKTMO_settlement_id':row[idcol],
                    'legacy_id_unique_in_both_years':True,'same_region_norm':True,
                    'normalized_name_equal':name_equal,'normalized_type_equal':type_equal,
                    'both_selected_rows_additive':True,'accepted_point_use_each_endpoint':d is not None,
                    'point_distance_km':round(d,4) if d is not None else None,
                    'legacy_source_record_id_before_publication_binding':text(row.get('legacy_source_record_id_before_publication_binding')),
                    'legacy_projection_basis':text(row.get('legacy_availability_projection_basis')),
                    'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False},
                    ensure_ascii=False,sort_keys=True),
                'population_from':row['population_from'],'population_to':row['population_to'],'point_distance_km':d,
                'point_from_file':text(row['point_origin_file_from']),'point_from_sha256':text(row['point_origin_sha256_from']),
                'point_from_locator':text(row['point_origin_locator_from']),'point_to_file':text(row['point_origin_file_to']),
                'point_to_sha256':text(row['point_origin_sha256_to']),'point_to_locator':text(row['point_origin_locator_to']),
                'source_from_file':text(row['source_file_from']),'source_from_sha256':text(row['source_sha256_from']),
                'source_from_locator':pair_source_locator(row,'_from'),'source_to_file':text(row['source_file_to']),
                'source_to_sha256':text(row['source_sha256_to']),'source_to_locator':pair_source_locator(row,'_to'),
                'assumptions_json':json.dumps(['legacy projected settlement identifier is a candidate witness only',
                    'the identifier is one-to-one in these years and region matches exactly',
                    'name/type are unchanged, or both accepted point uses agree within one kilometer',
                    'no population or boundary comparability inferred'],ensure_ascii=False),
            })

    # Recover the mass cohort whose 2010 district value came from a parser or
    # inherited-context field rather than an explicit cell. Assertions here
    # are source-row checks (workbook hash + sheet/row + exact label/population)
    # and do not edit selected_observations. For this cohort, a unique exact
    # typed name/region through all three years plus independently originated
    # 2002 historic and 2021 physical points within 5 km resolves a bad/missing
    # 2010 district field. Keep the selected district value verbatim in support.
    admin_assert_path=ROOT/'settlements-work/sources/admin_context_recovery_national_final/admin_context_assertions.parquet'
    admin_assert=pd.read_parquet(admin_assert_path,columns=['source_file','source_sha256','source_sheet',
        'source_row_1based','source_explicit_district_raw','source_name_raw','source_population_raw',
        'source_label_matches_exact_normalized','source_population_matches_exact','source_context_kind',
        'recovered_district_raw','recovered_district_from_row_1based','current_district_raw'])
    admin_assert=admin_assert[admin_assert.source_explicit_district_raw.isna() &
        admin_assert.source_label_matches_exact_normalized.fillna(False).astype(bool) &
        admin_assert.source_population_matches_exact.fillna(False).astype(bool) &
        admin_assert.source_row_1based.notna()].copy()
    raw_blank_rows=set(zip(admin_assert.source_file.map(text),admin_assert.source_sheet.map(text),
                           pd.to_numeric(admin_assert.source_row_1based,errors='coerce').fillna(-1).astype(int)))
    admin_assert_hash={(text(r.source_file),text(r.source_sheet),int(r.source_row_1based)):text(r.source_sha256)
                       for r in admin_assert.itertuples(index=False)}
    admin_assert_context={(text(r.source_file),text(r.source_sheet),int(r.source_row_1based)):{
        'source_context_kind':text(r.source_context_kind),'recovered_district_raw':text(r.recovered_district_raw),
        'recovered_district_from_row_1based':val(r.recovered_district_from_row_1based),
        'prior_selected_district_raw':text(r.current_district_raw),'source_name_raw':text(r.source_name_raw),
        'source_population_raw':text(r.source_population_raw),
        'source_label_matches_exact_normalized':bool(r.source_label_matches_exact_normalized),
        'source_population_matches_exact':bool(r.source_population_matches_exact)} for r in admin_assert.itertuples(index=False)}
    key3=['region_norm','name_norm','type_norm']
    triple_counts=base.groupby(key3+['census_year']).size().unstack(fill_value=0)
    for yy in YEARS:
        if yy not in triple_counts: triple_counts[yy]=0
    triple_keys=triple_counts[(triple_counts[2002]==1)&(triple_counts[2010]==1)&
                              (triple_counts[2021]==1)].reset_index()[key3]
    if len(triple_keys):
        triple_rows=base.merge(triple_keys,on=key3,how='inner').pivot(
            index=key3,columns='census_year',values='source_record_id').reset_index()
        lookup=base.set_index('source_record_id',drop=False)
        for ids in triple_rows[[2002,2010,2021]].itertuples(index=False,name=None):
            id02,id10,id21=map(text,ids)
            r02,r10,r21=(lookup.loc[id02],lookup.loc[id10],lookup.loc[id21])
            rawkey=(text(r10.source_file),text(r10.source_sheet),int(val(r10.source_row) or -1))
            if rawkey not in raw_blank_rows: continue
            asha=admin_assert_hash.get(rawkey,'')
            if not asha or asha!=text(r10.source_sha256): continue
            k02=text(r02.point_origin_kind); k21=text(r21.point_origin_kind)
            if not any(x in k02 for x in ('geokladr_2011','geonames_ru','named_typed_geo2011')): continue
            if not any(x in k21 for x in ('tochno_2021','raw_2021_own')): continue
            if any(val(r.get(k)) is None for r,k in [(r02,'latitude'),(r02,'longitude'),
                (r21,'latitude'),(r21,'longitude')]): continue
            d=distance_km((val(r02.latitude),val(r02.longitude)),(val(r21.latitude),val(r21.longitude)))
            if d>5.0: continue
            for left,right,yl,yh in [(r02,r10,2002,2010),(r10,r21,2010,2021)]:
                proposals.append({
                    'rule_family':f'R_H_raw_blank_2010_district_exact_triplet_and_independent_point_anchor_{yl}_{yh}',
                    'from_source_record_id':text(left.source_record_id),'from_year':yl,
                    'to_source_record_id':text(right.source_record_id),'to_year':yh,
                    'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                    'rule_support_json':json.dumps({
                        'unique_exact_normalized_name_type_region_in_all_three_years':[2002,2010,2021],
                        '2010_raw_source_file':rawkey[0],'2010_raw_source_sha256':asha,
                        '2010_raw_sheet':rawkey[1],'2010_raw_row_1based':rawkey[2],
                        '2010_raw_district_cell_blank':True,
                        '2010_raw_label_and_population_exact_match_selected_row':True,
                        'selected_2010_district_raw_preserved':text(r10.district_raw),
                        'source_context_assertion':admin_assert_context.get(rawkey,{}),
                        'source_record_id_2002':id02,'source_record_id_2010':id10,'source_record_id_2021':id21,
                        'historic_2002_point_origin_kind':k02,
                        'historic_2002_point_origin_file':text(r02.point_origin_file),
                        'historic_2002_point_origin_sha256':text(r02.point_origin_sha256),
                        '2021_physical_point_origin_kind':k21,
                        '2021_physical_point_origin_file':text(r21.point_origin_file),
                        '2021_physical_point_origin_sha256':text(r21.point_origin_sha256),
                        'independent_2002_to_2021_accepted_point_distance_km':round(d,4),
                        'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False},
                        ensure_ascii=False,sort_keys=True),
                    'population_from':left.population,'population_to':right.population,
                    'point_distance_km':d,
                    'source_from_file':text(left.source_file),'source_from_sha256':text(left.source_sha256),
                    'source_from_locator':source_locator(left),'source_to_file':text(right.source_file),
                    'source_to_sha256':text(right.source_sha256),'source_to_locator':source_locator(right),
                    'point_from_file':text(left.point_origin_file),'point_from_sha256':text(left.point_origin_sha256),
                    'point_from_locator':text(left.point_origin_locator),'point_to_file':text(right.point_origin_file),
                    'point_to_sha256':text(right.point_origin_sha256),'point_to_locator':text(right.point_origin_locator),
                    'assumptions_json':json.dumps([
                        'same typed settlement signature is unique within its whole-province year source in all three census years',
                        '2010 district field is not treated as explicit because the source workbook cell is blank; selected interpretation remains preserved',
                        'independently originated accepted 2002 historical and 2021 physical points agree within five kilometers',
                        'candidate still requires graph-safe no-duplicate-year component check; no population/boundary comparability inferred'],ensure_ascii=False)})

    # Exact historic district-context rule. Unique name/type/region keys can
    # collide within a subject; a unique district-normalized match resolves
    # those repeats, with exact municipality as a tie-breaker when necessary.
    # This rule carries forward raw admin labels and isolates legacy-pointer
    # quarantine from independently verified source row keys.
    for y1,y2 in [(2002,2010),(2010,2021)]:
        left=base[base.census_year.eq(y1)&base.district_join.ne('')].copy()
        right=base[base.census_year.eq(y2)&base.district_join.ne('')].copy()
        keys=['region_norm','name_norm','type_norm','district_join']
        lc=left.groupby(keys).size().rename('nl'); rc=right.groupby(keys).size().rename('nr')
        unique=lc.to_frame().join(rc,how='inner'); unique=unique[(unique.nl==1)&(unique.nr==1)].reset_index()[keys]
        joined=left.merge(right,on=keys,suffixes=('_from','_to')).merge(unique,on=keys,how='inner')
        # When the source district still has multiple exact typed names, use
        # a matching municipality only if both years record one.
        ldups=left.groupby(keys).size(); rdups=right.groupby(keys).size()
        duplicate_keys=set(ldups[ldups>1].index)&set(rdups[rdups>1].index)
        if duplicate_keys:
            dup_l=left[left[keys].apply(tuple,axis=1).isin(duplicate_keys)&left.municipality_join.ne('')]
            dup_r=right[right[keys].apply(tuple,axis=1).isin(duplicate_keys)&right.municipality_join.ne('')]
            mkeys=keys+['municipality_join']
            lmc=dup_l.groupby(mkeys).size().rename('nl'); rmc=dup_r.groupby(mkeys).size().rename('nr')
            mu=lmc.to_frame().join(rmc,how='inner');mu=mu[(mu.nl==1)&(mu.nr==1)].reset_index()[mkeys]
            if len(mu):
                jm=dup_l.merge(dup_r,on=mkeys,suffixes=('_from','_to')).merge(mu,on=mkeys,how='inner')
                joined=pd.concat([joined,jm],ignore_index=True)
        joined=joined[joined.is_additive_settlement_record_from.fillna(False).astype(bool)&
                      joined.is_additive_settlement_record_to.fillna(False).astype(bool)]
        joined=joined[~joined.population_scope_from.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        joined=joined[~joined.population_scope_to.fillna('').str.contains('federal_city_region|aggregate|municipal',case=False,regex=True)]
        for row in joined.to_dict('records'):
            a,b=row['source_record_id_from'],row['source_record_id_to']
            d=None
            if all(val(row.get(k)) is not None for k in ['latitude_from','longitude_from','latitude_to','longitude_to']):
                d=distance_km((val(row['latitude_from']),val(row['longitude_from'])),
                              (val(row['latitude_to']),val(row['longitude_to'])))
            if d is not None and d>25.0:
                holds.append({'rule_family':f'R_G_unique_exact_name_type_region_district_{y1}_{y2}',
                    'from_source_record_id':a,'to_source_record_id':b,'hold_reason':'accepted_point_distance_over_25km',
                    'point_distance_km':d,'population_from':row['population_from'],'population_to':row['population_to']})
                continue
            proposals.append({
                'rule_family':f'R_G_unique_exact_name_type_region_district_{y1}_{y2}',
                'from_source_record_id':a,'from_year':y1,'to_source_record_id':b,'to_year':y2,
                'decision_relation':'same_place','proposal_status':'staged_candidate_pending_independent_review',
                'rule_support_json':json.dumps({'unique_exact_normalized_name_type_region_district_each_year':True,
                    'district_suffix_normalization':'strip terminal district-kind suffix “район” or “муниципальный район” only',
                    'municipality_tiebreak_used':bool(text(row.get('municipality_join'))),
                    'normalized_region_equal':True,'selected_additive_source_rows':True,
                    'accepted_point_distance_km':round(d,4) if d is not None else None,
                    'accepted_points_absent_means_unknown':d is None,
                    'source_district_from':text(row.get('district_raw_from')),
                    'source_district_to':text(row.get('district_raw_to')),
                    'source_municipality_from':text(row.get('municipality_raw_from')),
                    'source_municipality_to':text(row.get('municipality_raw_to')),
                    'population_scope_comparability_asserted':False,'boundary_comparability_asserted':False},
                    ensure_ascii=False,sort_keys=True),
                'population_from':row['population_from'],'population_to':row['population_to'],'point_distance_km':d,
                'point_from_file':text(row['point_origin_file_from']),'point_from_sha256':text(row['point_origin_sha256_from']),
                'point_from_locator':text(row['point_origin_locator_from']),'point_to_file':text(row['point_origin_file_to']),
                'point_to_sha256':text(row['point_origin_sha256_to']),'point_to_locator':text(row['point_origin_locator_to']),
                'source_from_file':text(row['source_file_from']),'source_from_sha256':text(row['source_sha256_from']),
                'source_from_locator':pair_source_locator(row,'_from'),'source_to_file':text(row['source_file_to']),
                'source_to_sha256':text(row['source_sha256_to']),'source_to_locator':pair_source_locator(row,'_to'),
                'assumptions_json':json.dumps(['source selected name/type/region and the same named historic district are exact',
                    'each row is unique on that key; source administrative-level suffixes are normalized narrowly',
                    'legacy fuzzy-route flags are independently reconsidered against this source key',
                    'population and boundary comparability are not inferred'],ensure_ascii=False),
            })

    # Legacy flags are quarantine labels on an older route, not universal
    # physical-identity vetoes. Fetch them before pair deduplication so an
    # exact, unique district key can survive when it independently resolves a
    # stale/fuzzy legacy pointer. For a clean pair already covered by a main
    # rule, retain that main rule unchanged.
    pre_ids={r['from_source_record_id'] for r in proposals}|{r['to_source_record_id'] for r in proposals}
    pre_ev=source_evidence_for(pre_ids)
    def legacy_flagged(sid):
        e=pre_ev.get(sid,{})
        return bool(e.get('legacy_identity_conflict')) or bool(e.get('legacy_same_year_collision'))
    flagged_exact_pairs=set()
    for r in proposals:
        if r['rule_family'].startswith(('R_G_','R_H_')) and (
            legacy_flagged(r['from_source_record_id']) or legacy_flagged(r['to_source_record_id'])):
            flagged_exact_pairs.add((r['from_source_record_id'],r['to_source_record_id']))
    if flagged_exact_pairs:
        proposals=[r for r in proposals if
            (r['from_source_record_id'],r['to_source_record_id']) not in flagged_exact_pairs
            or r['rule_family'].startswith(('R_G_','R_H_'))]

    # Deduplicate exact pair overlaps, retaining the more specific rule family.
    def proposal_priority(r):
        family=r['rule_family']
        if family.startswith('R_A_'): return 0
        if family.startswith(('R_F_','R_G_','R_H_')): return 2
        return 1
    proposals.sort(key=lambda r:(proposal_priority(r),
                                 -(max(val(r.get('population_from')) or 0,val(r.get('population_to')) or 0)),
                                 r['from_source_record_id'],r['to_source_record_id']))
    seen=set(); unique_props=[]
    for r in proposals:
        key=(r['from_source_record_id'],r['to_source_record_id'])
        if key in seen: continue
        seen.add(key); unique_props.append(r)
    proposals=unique_props

    # source-level hard conflicts/aggregate assertions; missing optional grain tags are retained.
    endpoint_ids={r['from_source_record_id'] for r in proposals}|{r['to_source_record_id'] for r in proposals}
    ev={sid:pre_ev[sid] for sid in endpoint_ids if sid in pre_ev}
    resolvable_legacy_reasons={'legacy_not_accepted','stale_target_entity','text_similarity_only','undocumented_type_transition'}
    def evidence_hold(sid, family):
        e=ev.get(sid)
        if not e:return 'source_evidence_missing'
        if e.get('is_federal_aggregate'):return 'source_is_federal_aggregate'
        if family.startswith(('R_G_','R_H_')):
            if e.get('legacy_identity_conflict'):
                try:
                    reasons=set(json.loads(e.get('legacy_identity_reasons') or '[]'))
                except (TypeError,ValueError):
                    reasons=set()
                family_resolvable=set(resolvable_legacy_reasons)
                if family.startswith('R_H_'):
                    # R_H independently verifies that the 2010 raw source
                    # district cell is blank; this specifically resolves the
                    # inherited administrative_conflict label while retaining
                    # it in the support record.
                    family_resolvable.add('administrative_conflict')
                if not reasons or not reasons.issubset(family_resolvable):
                    return 'legacy_identity_conflict_has_unresolved_reason'
            # Legacy same-year flags describe the prior linkage route. This
            # candidate is independently unique on exact source keys and has
            # a scoped corroborating source witness; graph union below rechecks
            # actual year collisions.
            # Preserve the old flags as an explicit resolution in the support.
            return ''
        if e.get('legacy_identity_conflict'):return 'legacy_identity_conflict'
        if e.get('legacy_same_year_collision'):return 'legacy_same_year_collision'
        return ''
    clean=[]
    for r in proposals:
        h=evidence_hold(r['from_source_record_id'],r['rule_family']) or evidence_hold(r['to_source_record_id'],r['rule_family'])
        if h:
            holds.append({'rule_family':r['rule_family'],'from_source_record_id':r['from_source_record_id'],
                          'to_source_record_id':r['to_source_record_id'],'hold_reason':h,
                          'population_from':r['population_from'],'population_to':r['population_to']})
        else:
            if r['rule_family'].startswith(('R_G_','R_H_')):
                resolutions={}
                for sid in (r['from_source_record_id'],r['to_source_record_id']):
                    e=ev.get(sid,{})
                    if e.get('legacy_identity_conflict') or e.get('legacy_same_year_collision'):
                        resolutions[sid]={'legacy_identity_conflict':bool(e.get('legacy_identity_conflict')),
                            'legacy_identity_reasons':e.get('legacy_identity_reasons'),
                            'legacy_same_year_collision':bool(e.get('legacy_same_year_collision')),
                            'resolution_basis':('hash-pinned 2010 raw district cell is blank; exact typed name/region key is unique in all three years; independent 2002 historical and 2021 physical point origins agree within 5 km; actual graph uniqueness is checked'
                                if r['rule_family'].startswith('R_H_') else
                                'prior legacy route flags are quarantined from this decision; new exact source name/type/region/district key is year-unique; additive scope and same-place graph uniqueness are independently checked')}
                support=json.loads(r['rule_support_json'])
                support['legacy_flag_scoped_resolution']=resolutions
                r['rule_support_json']=json.dumps(support,ensure_ascii=False,sort_keys=True)
                assumptions=json.loads(r['assumptions_json'])
                assumptions.append('prior legacy-route quarantine flags do not veto this independently corroborated exact source candidate; any legacy flag and its scoped resolution are retained in rule support')
                r['assumptions_json']=json.dumps(assumptions,ensure_ascii=False)
            clean.append(r)
    proposals=clean

    # Greedy graph-safe application simulation, prioritizing two-year links that
    # can form full chains; ties favor the larger smaller-endpoint population.
    proposals.sort(key=lambda r:(proposal_priority(r),
                                 -min(val(r.get('population_from')) or 0,val(r.get('population_to')) or 0),
                                 -(val(r.get('population_from')) or 0)-(val(r.get('population_to')) or 0)))
    staged=[]
    for r in proposals:
        ok,reason=g.can_join(r['from_source_record_id'],r['from_year'],r['to_source_record_id'],r['to_year'])
        if not ok:
            holds.append({'rule_family':r['rule_family'],'from_source_record_id':r['from_source_record_id'],
                          'to_source_record_id':r['to_source_record_id'],'hold_reason':reason,
                          'population_from':r['population_from'],'population_to':r['population_to']})
            continue
        g.join(r['from_source_record_id'],r['from_year'],r['to_source_record_id'],r['to_year'])
        r['graph_safe_under_existing_plus_higher_priority_staged_edges']=True
        staged.append(r)

    # Candidate staging table and compact hold ledger.
    outcols=['rule_family','from_source_record_id','from_year','to_source_record_id','to_year','decision_relation',
             'proposal_status','rule_support_json','population_from','population_to','point_distance_km',
             'source_from_file','source_from_sha256','source_from_locator','source_to_file','source_to_sha256',
             'source_to_locator','point_from_file','point_from_sha256','point_from_locator','point_to_file',
             'point_to_sha256','point_to_locator','assumptions_json','graph_safe_under_existing_plus_higher_priority_staged_edges']
    staged_frame=pd.DataFrame(staged,columns=outcols)
    ext_mask=staged_frame.rule_family.fillna('').str.startswith(('R_F_','R_G_','R_H_'))
    staged_frame.to_csv(OUT/'all_staged_identity_edges_v3.csv',index=False)
    staged_frame[~ext_mask].to_csv(OUT/'staged_identity_edges.csv',index=False)
    staged_frame[ext_mask].to_csv(OUT/'source_admin_legacy_extension_unreviewed.csv',index=False)
    # One primary disposition per candidate endpoint pair. Preserve the strongest
    # provenance family when multiple generators found the same pair.
    def hold_rank(h):
        f=h.get('rule_family','')
        return 0 if f.startswith('accepted_2002_2010') else 1 if f.startswith('R_D_') else 2 if f.startswith('R_C_') else 3
    holds.sort(key=lambda h:(hold_rank(h),str(h.get('from_source_record_id','')),str(h.get('to_source_record_id',''))))
    disjoint=[];seen_hold=set()
    for h in holds:
        key=(h.get('from_source_record_id',''),h.get('to_source_record_id',''))
        if key in seen_hold: continue
        seen_hold.add(key);disjoint.append(h)
    holds=disjoint
    holds_frame=pd.DataFrame(holds)
    holds_frame.to_csv(OUT/'all_disjoint_holds_v3.csv',index=False)
    if len(holds_frame):
        h_ext=holds_frame.rule_family.fillna('').str.startswith(('R_F_','R_G_','R_H_'))
        holds_frame[~h_ext].to_csv(OUT/'disjoint_holds.csv',index=False)
        holds_frame[h_ext].to_csv(OUT/'source_admin_legacy_extension_holds.csv',index=False)
    else:
        pd.DataFrame().to_csv(OUT/'disjoint_holds.csv',index=False)
        pd.DataFrame().to_csv(OUT/'source_admin_legacy_extension_holds.csv',index=False)

    # Evaluate full-chain population potential against caller's residual artifact.
    residual=pd.read_parquet(RESIDUAL)
    residual['source_record_id']=residual.source_record_id.map(text)
    residual_ids=set(residual.source_record_id)
    comp=defaultdict(list)
    for sid,year,pop in residual[['source_record_id','census_year','population']].itertuples(index=False):
        comp[g.find(text(sid))].append((text(sid),int(year),val(pop)))
    full=[]; partial=[]
    for root,rows in comp.items():
        years={y for _,y,_ in rows}
        if years==set(YEARS):
            full.extend(rows)
        elif len(years)>=2:
            partial.extend(rows)
    byyear=Counter(); full_count=Counter(); full_unknown=Counter()
    for _,y,pop in full:
        full_count[y]+=1
        if pop is None: full_unknown[y]+=1
        else: byyear[y]+=pop
    summary={
        'status':'staged_candidates_pending_independent_review',
        'inputs':{
            'frozen_release':'/workspace/settlements-delivery/continuation-consolidated-20261003',
            'preaudit_continuation_csv':str(AUDIT/'interyear_2021_continuation_priorities.csv'),
            'full_chain_residual':str(RESIDUAL),
            'accepted_graph_same_place_edges':int(len(edge)),
        },
        'output_rows':len(staged),'disjoint_hold_rows':len(holds),
        'main_proposal_rows':int((~ext_mask).sum()),'separate_extension_rows':int(ext_mask.sum()),
        'staged_by_rule_family':Counter(r['rule_family'] for r in staged),
        'staged_population_endpoint_totals_not_comparable':{
            str(y):{'rows':sum(1 for r in staged if r['from_year']==y)+sum(1 for r in staged if r['to_year']==y),
                    'known_population_sum':sum(val(r['population_from']) for r in staged if r['from_year']==y and val(r['population_from']) is not None)+
                                           sum(val(r['population_to']) for r in staged if r['to_year']==y and val(r['population_to']) is not None),
                    'unknown_population_rows':sum(1 for r in staged if r['from_year']==y and val(r['population_from']) is None)+
                                              sum(1 for r in staged if r['to_year']==y and val(r['population_to']) is None)} for y in YEARS},
        'preaudit_1139_continuation':{
            'candidate_pairs':len(aliases),'unique_2021_counterparts':int((aliases.current_2021_row_count.astype(str)=='1.0').sum()),
            'with_accepted_2021_points':int(aliases.current_2021_point_kind.ne('').sum()),
            'point_population_2021':sum(val(x) or 0 for x in aliases.loc[aliases.current_2021_point_kind.ne(''),'current_2021_population']),
            'all_1138_unique_counterparts_staged':sum(r['rule_family'].startswith('R_A_') for r in staged),
            'near_1km':sum(r['rule_family'].startswith('R_A_') and (r['point_distance_km'] is not None and r['point_distance_km']<=1) for r in staged),
        },
        'full_chain_residual_potential_after_graph_safe_staging':{
            'rows_in_components_with_all_three_years':len(full),
            'known_population_sum_by_year':dict(byyear),'row_count_by_year':dict(full_count),
            'unknown_population_rows_by_year':dict(full_unknown),
            'rows_in_components_with_two_or_more_years':len(partial),
            'population_comparability_asserted':False,'boundary_comparability_asserted':False,
        },
        'hold_reasons_disjoint':Counter(r.get('hold_reason','') for r in holds),
        'limitations':['All edges are staged candidates, not admissions.',
            'Potential full-chain counts simulate graph-safe candidate edges over accepted edges and are not coverage claims.',
            'No population or boundary comparability is asserted.',
            'Large source-defined renames and type transitions without exact key agreement are not yet included.'],
    }
    summary['staged_by_rule_family']=dict(summary['staged_by_rule_family'])
    summary['hold_reasons_disjoint']=dict(summary['hold_reasons_disjoint'])
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=lambda x:dict(x)),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2,default=lambda x:dict(x)))


if __name__=='__main__':
    main()

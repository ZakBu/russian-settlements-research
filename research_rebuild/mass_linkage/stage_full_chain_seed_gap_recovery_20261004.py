#!/usr/bin/env python3
"""Stage bounded modern point candidates for the largest full-chain seed gaps.

This is a review package only. It consumes already frozen source-point / GeoNames
candidate families, adds a fresh Wikidata full-claim diagnostic snapshot for the
same top-200 targets, and simulates point-seed continuity over the canonical
accepted graph without changing either accepted ledger.
"""
from __future__ import annotations
import csv, hashlib, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path('/workspace/settlements-work')
REPO = Path('/workspace/russian-settlements-research')
BASE = ROOT / 'continuation_20261004'
OUT = BASE / 'R4/wikidata_points/extensions/full_chain_seed_gap_recovery'
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
SOURCE_EVIDENCE = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
EDGES = BASE / 'accepted_mass_extensions/accepted_identity_edges.parquet'
POINTS = BASE / 'accepted_mass_extensions/accepted_point_uses.parquet'
COVERAGE = BASE / 'accepted_mass_extensions/coverage.json'
GAP = BASE / 'root/full_chain_point_gap_diagnostic.parquet'
WD_WIDE = ROOT / 'wikidata/wide_v5/wide_point_bindings.parquet'
GN_DIR = BASE / 'wikidata_points/extensions/source_point_geonames_recovery'
SOURCE_GN = GN_DIR / 'staged_source_point_candidates.csv'
GN_DIRECT = GN_DIR / 'gn_point_recovery_v6/staged_direct_gn_point_candidates.csv'
GN_LEDGER = GN_DIR / 'gn_point_recovery_v6/direct_gn_point_rule_ledger.csv'
MULTI_P625 = BASE / 'wikidata_points/extensions/multi_p625_rank_review.csv'
WIKIDATA_RAW = OUT / 'raw_cache/top200_wikidata_entities.json'
BLOCKED = ROOT / 'continuation_20261003/blocked_point_reuse_targets_v1.json'
WD_RECEIPT = BASE / 'independent_review/wikidata_review_receipt_final.json'
YEARS = (2002, 2010, 2021)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def clean(v):
    if v is None or pd.isna(v): return None
    if hasattr(v, 'item'): return v.item()
    return v

def compact(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
def truth(v): return str(v).strip().casefold() in {'true','1','t','yes'}
def num(v):
    try:
        z = float(v)
        return z if math.isfinite(z) else None
    except (ValueError, TypeError): return None

def haversine_km(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon-a_lon)
    z = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(z))

class DSU:
    def __init__(self, ids, years):
        self.ix = {v:i for i,v in enumerate(ids)}
        self.p = list(range(len(ids))); self.rank = [0]*len(ids)
        self.mask = [1 << {2002:0,2010:1,2021:2}[int(y)] for y in years]
    def find(self, i):
        r=i
        while self.p[r] != r: r=self.p[r]
        while self.p[i] != i:
            n=self.p[i]; self.p[i]=r; i=n
        return r
    def root(self, sid): return self.find(self.ix[sid])
    def union(self, a, b):
        x,y=self.find(self.ix[a]),self.find(self.ix[b])
        if x == y: return
        if self.rank[x] < self.rank[y]: x,y=y,x
        self.p[y]=x; self.mask[x] |= self.mask[y]
        if self.rank[x] == self.rank[y]: self.rank[x]+=1

def p625_summary(entity):
    claims = entity.get('claims', {}).get('P625', [])
    out=[]
    for st in claims:
        snak=st.get('mainsnak',{}); val=snak.get('datavalue',{}).get('value',{})
        if snak.get('snaktype') != 'value' or not isinstance(val,dict): continue
        lat=num(val.get('latitude')); lon=num(val.get('longitude'))
        if lat is None or lon is None: continue
        globe=val.get('globe')
        globe_qid=globe.rsplit('/',1)[-1] if isinstance(globe,str) else None
        rank=st.get('rank','normal')
        out.append({'statement_guid':st.get('id'),'rank':rank,'deprecated':rank=='deprecated','latitude':lat,'longitude':lon,
                    'globe_uri':globe,'globe_qid':globe_qid,'qualifiers':st.get('qualifiers',{}),
                    'references':st.get('references',[]),'earth_live':rank!='deprecated' and globe_qid=='Q2'})
    earth=[x for x in out if x['earth_live']]
    spread=max((haversine_km(a['latitude'],a['longitude'],b['latitude'],b['longitude']) for i,a in enumerate(earth) for b in earth[i+1:]),default=0.0)
    return {'claim_count':len(out),'claims':out,'live_earth_claim_count':len(earth),'max_live_earth_pairwise_km':spread,
            'point_choice_diagnostic':('one_live_earth_claim' if len(earth)==1 else 'bounded_cluster_le_500m' if len(earth)>1 and spread<=0.5 else 'multi_point_choice_unresolved' if len(earth)>1 else 'no_live_earth_claim')}

def main():
    if (OUT/'freeze_manifest.json').exists(): raise SystemExit(f'refusing to overwrite frozen bundle: {OUT}')
    if not WIKIDATA_RAW.exists(): raise SystemExit(f'missing pinned one-batch API cache {WIKIDATA_RAW}')
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_COORDINATE_STATUSES, ACCEPTED_PROJECTION_STATUSES

    # Direct-input hashes are recorded before reading. The raw Wikidata response
    # is a one-time saved 47-QID batch, so script reruns require no network.
    input_paths=[SELECTED,SOURCE_EVIDENCE,EDGES,POINTS,COVERAGE,GAP,WD_WIDE,SOURCE_GN,GN_DIRECT,GN_LEDGER,MULTI_P625,BLOCKED,WD_RECEIPT,WIKIDATA_RAW]
    input_hashes={str(p):sha(p) for p in input_paths}

    selected_cols=['source_record_id','census_year','source_name_raw','settlement_name','settlement_type','region_raw','region_norm','population','population_scope','is_additive_settlement_record','source_sha256','source_locator','oktmo','latitude','longitude','coordinate_source']
    s=pd.read_parquet(SELECTED,columns=selected_cols); s=s[s.census_year.isin(YEARS)].copy()
    s.source_record_id=s.source_record_id.astype(str); s.census_year=s.census_year.astype(int)
    ev=pd.read_parquet(SOURCE_EVIDENCE,columns=['source_record_id','census_year','source_evidence_json']);ev.source_record_id=ev.source_record_id.astype(str)
    s=s.merge(ev,on=['source_record_id','census_year'],how='left',validate='one_to_one')
    if s.source_record_id.duplicated().any(): raise RuntimeError('selected census source IDs are not unique')

    gap=pd.read_parquet(GAP)
    gap=gap[(gap.census_year==2021)&(gap.why=='no_accepted_seed')].copy()
    top=gap.sort_values(['population','source_record_id'],ascending=[False,True],kind='mergesort').head(200).copy()
    top['target_rank_by_2021_population']=range(1,len(top)+1)
    if len(gap)!=2834 or int(gap.population.sum())!=1241523 or int(top.population.sum())!=1021981:
        raise RuntimeError('pinned gap/top-200 cohort differs from assigned diagnostic baseline')

    src_candidates=pd.read_csv(SOURCE_GN,keep_default_na=False,dtype=str)
    gn_candidates=pd.read_csv(GN_DIRECT,keep_default_na=False,dtype=str)
    gn_ledger=pd.read_csv(GN_LEDGER,keep_default_na=False,dtype=str)
    src_candidates=src_candidates[src_candidates.source_record_id.isin(set(top.source_record_id))]
    gn_candidates=gn_candidates[gn_candidates.source_record_id.isin(set(top.source_record_id))]
    src_by={r.source_record_id:r for r in src_candidates.itertuples(index=False)}
    gn_by={r.source_record_id:r for r in gn_candidates.itertuples(index=False)}
    gn_ledger_by={r.source_record_id:r for r in gn_ledger[gn_ledger.source_record_id.isin(set(top.source_record_id))].itertuples(index=False)}

    wd=pd.read_parquet(WD_WIDE)
    wcols=['source_record_id','wikidata_qid','wikidata_truthy_exact_p764_match','wikidata_tsv_exact_p764_value_raw','wikidata_name_exact_label','wikidata_truthy_p31_claims_json','wikidata_truthy_p625_claims_json','wikidata_tsv_admin_qids_json','wikidata_tsv_ru_admin_labels_json','wikidata_tsv_okato_exact_values_json','entity_competition_across_tsv_or_truthy','truthy_p625_point_count','nearest_wide_point_to_dadata_km','farthest_wide_point_to_dadata_km']
    wd=wd[wcols].copy(); wd.source_record_id=wd.source_record_id.astype(str)
    # Multiple Wikidata candidates for a target are retained and marked; no row is
    # selected from a many-QID match.
    wd_counts=wd.groupby('source_record_id').size().to_dict()
    wide_by=defaultdict(list)
    for x in wd.itertuples(index=False): wide_by[x.source_record_id].append(x)
    api=json.loads(WIKIDATA_RAW.read_text())
    entities=api.get('entities',{})
    multi=pd.read_csv(MULTI_P625,keep_default_na=False,dtype=str)
    multi_by={r.source_record_id:r for r in multi[multi.source_record_id.isin(set(top.source_record_id))].itertuples(index=False)}

    blocked_doc=json.loads(BLOCKED.read_text()); blocked=set(blocked_doc['blocked_target_source_record_ids'])
    receipt=json.loads(WD_RECEIPT.read_text())['decision']
    wd_holds=set(receipt['hard_geo_point_choice_hold_ids']) | set(receipt['four_frozen_known_holds_not_in_candidate_pool'])
    all_holds=blocked|wd_holds

    # Canonical accepted ledgers are loaded using canonical status fields only.
    points=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status'])
    if points.coordinate_admission_status.isna().any() or not points.coordinate_admission_status.astype(str).isin(ACCEPTED_COORDINATE_STATUSES).all(): raise RuntimeError('unrecognized accepted point-use status')
    point_targets=set(points.target_source_record_id.astype(str))
    graph=pd.read_parquet(EDGES,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
    if graph.decision_status.isna().any() or not graph.decision_status.astype(str).isin(ACCEPTED_EDGE_STATUSES).all(): raise RuntimeError('unrecognized accepted identity status')
    if graph.selection_projection_status.isna().any() or not graph.selection_projection_status.astype(str).isin(ACCEPTED_PROJECTION_STATUSES).all(): raise RuntimeError('unrecognized accepted endpoint projection status')
    if not graph.relation.eq('same_place').all(): raise RuntimeError('non-same_place relation in canonical accepted graph')
    ids=s.source_record_id.tolist(); years=s.census_year.tolist(); idset=set(ids)
    dsu=DSU(ids,years)
    for e in graph.itertuples(index=False):
        a,b=str(e.from_source_record_id),str(e.to_source_record_id)
        if a not in idset or b not in idset: raise RuntimeError('accepted graph endpoint absent from selected census')
        dsu.union(a,b)
    def cov(seedtargets, propagate_new_seed_components=False):
        full_roots={dsu.find(i) for i in range(len(ids)) if dsu.mask[dsu.find(i)]==7}
        r=defaultdict(lambda:[0,0,0,0])
        seed_roots={dsu.root(x) for x in seedtargets if x in dsu.ix} if propagate_new_seed_components else set()
        for x in s.itertuples(index=False):
            root=dsu.root(x.source_record_id)
            if root not in full_roots: continue
            yy=int(x.census_year); p=0 if pd.isna(x.population) else int(x.population)
            r[yy][0]+=1; r[yy][1]+=p
            # The accepted-coverage baseline counts only actual accepted uses.
            # The scenario additionally propagates newly staged 2021 seeds over
            # their already-accepted full-chain component as an explicit inference.
            if x.source_record_id in point_targets or root in seed_roots:
                r[yy][2]+=1; r[yy][3]+=p
        return r
    baseline=cov(point_targets)
    covdoc=json.loads(COVERAGE.read_text())
    for m in covdoc['census_metrics']:
        y=int(m['year']); row=baseline[y]
        expected=[int(m['axes']['full_census_chain']['rows']),int(m['axes']['full_census_chain']['known_population']),int(m['axes']['joint_admitted_coordinate_and_full_chain']['rows']),int(m['axes']['joint_admitted_coordinate_and_full_chain']['known_population'])]
        if row!=expected: raise RuntimeError(f'canonical baseline mismatch in {y}: actual={row} expected={expected}')

    # Candidate coordinates are actual source-point or actual GeoNames points.
    # When both scoped families apply, keep the source point as proposal and GN as
    # explicit corroboration; never average the coordinates.
    rows=[]; point_uses=[]
    for t in top.itertuples(index=False):
        sid=str(t.source_record_id); source=next(s[s.source_record_id.eq(sid)].itertuples(index=False))
        sr=src_by.get(sid); gr=gn_by.get(sid); wl=wide_by.get(sid,[])
        current_hold=sid in all_holds
        usable_sr=sr is not None and truth(sr.candidate_only) and not truth(sr.existing_hold)
        usable_gr=gr is not None and truth(gr.candidate_only) and not truth(gr.existing_hold)
        route=[]
        if usable_sr: route.append('source_point_unique_exact_name_region_PPL_le_1km')
        if usable_gr: route.append('direct_GN_unique_whole_region_literal_alias_PPL_le_5km')
        status='hold_preserve_existing_quarantine_or_WD_conflict' if current_hold else ('candidate_point_use' if route else 'hold_no_scoped_point_route')
        primary_family=None; lat=lon=None; coord_source=None; raw_locator=None; raw_sha=None; payload_sha=None; alternate={}
        if not current_hold and usable_sr:
            primary_family='source_point_geonames_unique_name_region_PPL_concordance'
            lat=num(sr.source_point_latitude); lon=num(sr.source_point_longitude)
            coord_source='raw 2021 Tochno source point; unique exact GeoNames current physical PPL corroborates within 1 km'
            raw_locator=sr.source_raw_row_locator; raw_sha=sr.source_file_sha256_verified; payload_sha=sr.source_row_payload_sha256
            alternate={'latitude':num(gr.proposed_latitude) if usable_gr else None,'longitude':num(gr.proposed_longitude) if usable_gr else None,'origin':'actual GeoNames PPL representative point' if usable_gr else None,'source_point_to_gn_distance_km':num(gr.source_point_distance_km_diagnostic) if usable_gr else None}
        elif not current_hold and usable_gr:
            primary_family='direct_GN_unique_whole_region_literal_alias_PPL_source_distance_le_5km'
            lat=num(gr.proposed_latitude); lon=num(gr.proposed_longitude)
            coord_source='actual GeoNames RU PPL-family populated-place representative point; upstream measurement lineage unknown'
            raw_locator=gr.source_raw_row_locator; raw_sha=gr.source_raw_file_sha256; payload_sha=gr.source_raw_payload_sha256
            alternate={'latitude':num(gr.source_point_latitude),'longitude':num(gr.source_point_longitude),'origin':'actual raw 2021 Tochno source point diagnostic only','source_point_to_gn_distance_km':num(gr.source_point_distance_km_diagnostic)}
        # Candidate safety: coordinates are never proposed on held records or if
        # the exact witness row was not unique and physically screened.
        if route and not current_hold:
            if (lat is None or lon is None or not (-90<=lat<=90 and -180<=lon<=180)):
                raise RuntimeError(f'invalid candidate coordinates for {sid}')
            use={'point_use_id':'FCG-'+hashlib.sha256((sid+'|'+primary_family).encode()).hexdigest()[:18],
                 'target_source_record_id':sid,'target_year':2021,'latitude':lat,'longitude':lon,
                 'coordinate_source':coord_source,'coordinate_admission_status':'candidate_only_pending_independent_review',
                 'candidate_only':True,'coordinate_admission':False,'candidate_rule_family':primary_family,
                 'origin_raw_file':raw_locator,'origin_file_sha256':raw_sha,'origin_row_payload_sha256':payload_sha,
                 'source_point_latitude':num(sr.source_point_latitude) if sr else num(gr.source_point_latitude),
                 'source_point_longitude':num(sr.source_point_longitude) if sr else num(gr.source_point_longitude),
                 'geo_names_witness_rows_json':gr.gn_current_physical_ppl_rows_json if gr else (sr.geonames_witness_rows_json if sr else '[]'),
                 'source_point_to_selected_GN_distance_km':num(gr.source_point_distance_km_diagnostic) if gr else None,
                 'alternate_actual_point_json':compact(alternate),
                 'provider_id_binding_asserted':False,'upstream_coordinate_measurement_independence_proven':False,
                 'census_date_point_measurement_proven':False,'coordinate_precision_upgraded':False}
            point_uses.append(use)

        # Wikidata is diagnostic in this point-recovery pass. Full API claims
        # preserve statement GUID, rank, globe, qualifiers, references and exact
        # alternatives; claims do not override a currently held coordinate.
        wds=[]
        for w in wl:
            qid=str(w.wikidata_qid); ent=entities.get(qid,{})
            p625=p625_summary(ent)
            wd_claims=ent.get('claims',{})
            p764=[]
            for c in wd_claims.get('P764',[]):
                dv=c.get('mainsnak',{}).get('datavalue',{}).get('value')
                if dv is not None: p764.append({'value':str(dv),'rank':c.get('rank','normal'),'statement_guid':c.get('id')})
            p31=[]
            for c in wd_claims.get('P31',[]):
                dv=c.get('mainsnak',{}).get('datavalue',{}).get('value',{})
                if isinstance(dv,dict) and 'id' in dv: p31.append({'qid':dv['id'],'rank':c.get('rank','normal'),'statement_guid':c.get('id')})
            p131=[]
            for c in wd_claims.get('P131',[]):
                dv=c.get('mainsnak',{}).get('datavalue',{}).get('value',{})
                if isinstance(dv,dict) and 'id' in dv: p131.append({'qid':dv['id'],'rank':c.get('rank','normal')})
            live=[x for x in p625['claims'] if x['earth_live']]
            proposal_dists=[]
            if lat is not None and lon is not None:
                proposal_dists=[{'statement_guid':x['statement_guid'],'distance_to_staged_point_km':haversine_km(lat,lon,x['latitude'],x['longitude'])} for x in live]
            wds.append({'qid':qid,'exact_p764_in_frozen_wide':clean(w.wikidata_truthy_exact_p764_match),
                        'p764_full_claims':p764,'exact_ru_label_in_frozen_wide':clean(w.wikidata_name_exact_label),
                        'p31_full_claims':p31,'p131_full_claims':p131,'full_p625':p625,
                        'distance_from_p625_alternatives_to_staged_point':proposal_dists,
                        'frozen_tsv_admin_labels':w.wikidata_tsv_ru_admin_labels_json,
                        'entity_competition_in_frozen_wide':clean(w.entity_competition_across_tsv_or_truthy)})
        # No automatic WD point selection. Even a single P625 remains a diagnostic
        # unless separately corroborated by a scoped source-point rule.
        source_pop=int(source.population) if not pd.isna(source.population) else 0
        rows.append({'source_record_id':sid,'rank_by_2021_population':int(t.target_rank_by_2021_population),'source_population':source_pop,
                     'settlement_name':source.settlement_name,'settlement_type':source.settlement_type,'region_raw':source.region_raw,'population_scope':source.population_scope,
                     'source_additive':truth(source.is_additive_settlement_record),'source_name_raw':source.source_name_raw,
                     'source_latitude':num(source.latitude),'source_longitude':num(source.longitude),'source_coordinate_source':source.coordinate_source,
                     'source_file_sha256':source.source_sha256,'source_locator':source.source_locator,
                     'raw_source_row_locator':raw_locator,'raw_source_file_sha256':raw_sha,'raw_source_row_payload_sha256':payload_sha,
                     'source_point_rule_candidate':usable_sr,'direct_GN_rule_candidate':usable_gr,'candidate_rule_families_json':compact(route),
                     'candidate_decision':status,'preserved_hold_memberships_json':(gn_ledger_by[sid].hold_memberships_json if sid in gn_ledger_by else '[]'),
                     'prior_GN_ledger_status':(gn_ledger_by[sid].rule_status if sid in gn_ledger_by else None),
                     'proposal_rule_family':primary_family,'proposed_latitude':lat,'proposed_longitude':lon,
                     'proposal_source_and_alternatives_json':compact({'coordinate_source':coord_source,'alternate_actual_point':alternate}),
                     'source_point_to_GN_distance_km':num(gr.source_point_distance_km_diagnostic) if gr else None,
                     'geo_names_source_witness_json':(gr.gn_current_physical_ppl_rows_json if gr else (sr.geonames_witness_rows_json if sr else '[]')),
                     'wikidata_raw_candidates_json':compact(wds),'wikidata_raw_candidate_count':len(wds),
                     'point_measurement_precision_claimed':False,'provider_identifier_binding_claimed':False,'coordinate_admission':False})

    # Aggregate route candidates to current accepted graph components. This is a
    # conditional continuity scenario, never a claim that the historical census
    # rows measured those modern coordinates.
    by_sid={x['source_record_id']:x for x in rows}
    candidate_ids={x['target_source_record_id'] for x in point_uses}
    component_candidates=defaultdict(list)
    for sid in candidate_ids: component_candidates[dsu.root(sid)].append(sid)
    for root, ids_here in component_candidates.items():
        if len(ids_here)>1: raise RuntimeError(f'multiple point proposals in same accepted component: {ids_here}')
    after=cov(candidate_ids,propagate_new_seed_components=True)
    conditional=[]
    for year in YEARS:
        base=baseline[year]; post=after[year]
        conditional.append({'year':year,'baseline_joint_full_chain_rows':base[2],'baseline_joint_full_chain_population':base[3],
                            'candidate_continuity_scenario_joint_full_chain_rows':post[2],'candidate_continuity_scenario_joint_full_chain_population':post[3],
                            'marginal_rows':post[2]-base[2],'marginal_population':post[3]-base[3],
                            'interpretation':'all candidate modern points reused through already-accepted full-chain identity components under an explicit continuity inference; candidate-only, not admitted'})
    direct_2021={'candidate_direct_point_rows':len(point_uses),'candidate_direct_point_population':sum(int(x['source_population']) for x in rows if x['source_record_id'] in candidate_ids)}

    ledger=pd.DataFrame(rows).sort_values('rank_by_2021_population')
    uses=pd.DataFrame(point_uses).sort_values('target_source_record_id')
    ledger_path=OUT/'top200_full_chain_seed_gap_review_ledger.csv'; uses_path=OUT/'staged_point_uses.csv'
    ledger.to_csv(ledger_path,index=False,quoting=csv.QUOTE_MINIMAL)
    uses.to_csv(uses_path,index=False,quoting=csv.QUOTE_MINIMAL)

    # Fixed review sample: deterministic top-30 mass, then seed-filled coverage
    # across candidate/held/no-route and P625 uncertainty strata.
    sample_ids=[]
    for x in ledger.nsmallest(30,'rank_by_2021_population').source_record_id: sample_ids.append(x)
    seed=20261004
    strata=defaultdict(list)
    for x in rows:
        key=(x['candidate_decision'], 'wd_multi' if 'multi_point_choice_unresolved' in str(x['wikidata_raw_candidates_json']) else 'wd_other')
        strata[key].append(x)
    for key, vals in sorted(strata.items(),key=lambda z:str(z[0])):
        vals=sorted(vals,key=lambda x:hashlib.sha256((str(seed)+'|'+x['source_record_id']).encode()).hexdigest())
        for x in vals:
            if len(sample_ids)>=100: break
            if x['source_record_id'] not in sample_ids: sample_ids.append(x['source_record_id'])
    # Fill to 100 deterministically from the remaining population-ranked rows.
    for sid in ledger.source_record_id:
        if len(sample_ids)>=100: break
        if sid not in sample_ids: sample_ids.append(sid)
    sample=ledger[ledger.source_record_id.isin(sample_ids)].copy().sort_values('rank_by_2021_population')
    sample['sample_design']='top30_mass_plus_deterministic_risk_stratum_fill_seed_20261004; descriptive_not_probability_sample'
    sample_path=OUT/'fixed_100_review_sample.csv';sample.to_csv(sample_path,index=False)
    risk=ledger.assign(risk_stratum=ledger.apply(lambda x: x.candidate_decision+' | '+('WD multi-point unresolved' if 'multi_point_choice_unresolved' in str(x.wikidata_raw_candidates_json) else 'WD other or absent'),axis=1))
    risk.groupby('risk_stratum',dropna=False).agg(rows=('source_record_id','size'),population=('source_population','sum'),top_population_rank_min=('rank_by_2021_population','min')).reset_index().to_csv(OUT/'risk_strata.csv',index=False)
    pd.DataFrame(conditional).to_csv(OUT/'conditional_full_chain_gain_by_year.csv',index=False)

    summary={'status':'candidate_only_no_admissions','scope':'largest 200 (by 2021 population) of full-chain no-accepted-seed targets; coordinates staged only for 2021 direct source point or direct GeoNames point; prior identity graph unchanged',
             'diagnostic_cohort':{'2021_no_accepted_seed_rows':len(gap),'2021_no_accepted_seed_population':int(gap.population.sum()),'top200_rows':len(top),'top200_population':int(top.population.sum())},
             'point_candidate_rule':'exact raw source NP/unique native code/name/region plus unique literal whole-region GeoNames PPL-family alias in expected ADM1: direct raw source point if <=1km concordant (source_point family); direct actual GeoNames point if source difference <=5km diagnostic (GN family); no averaging; provider-ID and upstream coordinate lineage not asserted',
             'direct_2021_candidate_use':direct_2021,'conditional_full_chain_gain_by_year':conditional,
             'candidate_status_counts':ledger.candidate_decision.value_counts().to_dict(),
             'candidate_rule_counts':Counter(f for x in rows for f in json.loads(x['candidate_rule_families_json'])),
             'p625_diagnostics':{'targets_with_wikidata_QID':sum(bool(json.loads(x['wikidata_raw_candidates_json'])) for x in rows),'raw_api_qids_returned':len(entities),'targets_with_any_multi_point_choice_unresolved':sum('multi_point_choice_unresolved' in x['wikidata_raw_candidates_json'] for x in rows),'WD_coordinates_staged':0},
             'hard_holds_preserved':{'blocked_legacy_hold_ids':len(blocked),'wikidata_review_hard_hold_ids':len(wd_holds),'top200_rows_intersecting_union':int(ledger.source_record_id.isin(all_holds).sum()),'hold_ids_sha256':hashlib.sha256('\n'.join(sorted(all_holds)).encode()).hexdigest()},
             'candidate_policy_limits':['All staged points remain candidate-only and require independent review.','GeoNames coordinate upstream measurement lineage is unknown; no independence-of-measurement claim.','Raw source point and GeoNames point are actual distinct source claims; use source point when source-point rule passes, otherwise actual GeoNames point; do not average.','Wikidata full P625 rank/globe/deprecated/qualifier/reference alternatives are retained as diagnostics; no Wikidata coordinate is selected automatically.','Source-vs-GN distance is diagnostic and scoped by explicit rule family, not a universal error threshold.','Historical point reuse appears only in the conditional continuity scenario and is not a census-date measurement or boundary comparability claim.'],
             'baseline_canonical_full_and_joint_coverage_by_year':{str(y):{'full_chain_rows':baseline[y][0],'full_chain_population':baseline[y][1],'joint_full_rows':baseline[y][2],'joint_full_population':baseline[y][3]} for y in YEARS},
             'input_hashes':input_hashes,'raw_geonames_input_hashes':json.loads((GN_DIR/'gn_point_recovery_v6/summary.json').read_text())['input_hashes'],'wikidata_api_snapshot':{'path':str(WIKIDATA_RAW),'sha256':input_hashes[str(WIKIDATA_RAW)],'qid_count':len(entities),'retrieval_method':'single saved wbgetentities batch for all QIDs on top-200 target frame; no subsequent network required'},
             'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [ledger_path,uses_path,sample_path,OUT/'risk_strata.csv',OUT/'conditional_full_chain_gain_by_year.csv']},
             'population_interpretation':'Selected source population at the target/year; current graph components are simulated as already accepted. Candidate coordinates add joint full-chain coverage only under explicit modern-point continuity and remain unadmitted.'}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    manifest={'status':'frozen_candidate_only_review_inputs_and_outputs','created_by':str(Path(__file__).resolve()),'generator_sha256':sha(Path(__file__).resolve()),
              'input_hashes':input_hashes,'outputs_sha256':{p.name:sha(p) for p in [ledger_path,uses_path,sample_path,OUT/'risk_strata.csv',OUT/'conditional_full_chain_gain_by_year.csv',OUT/'summary.json']},
              'non_admission_notice':'No accepted identity or point ledger was changed. Review is required before any application.'}
    (OUT/'freeze_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'out':str(OUT),'summary':summary},ensure_ascii=False))

if __name__=='__main__': main()

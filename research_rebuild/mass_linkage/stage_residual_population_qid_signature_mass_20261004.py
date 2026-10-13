#!/usr/bin/env python3
"""Stage and fetch uncached current QIDs for two-year residual identity review.

This is a candidate-only, source-preserving investigation. It never changes the
accepted graph, selected populations, points, or Wikidata overlays.
"""
from __future__ import annotations
import hashlib, json, re, time, urllib.parse, urllib.request, urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np

from research_rebuild.mass_linkage.stage_wide_qid_homonym_fetch_candidates_20261004 import norm, typ, PHYSICAL
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.coordinate_validation_packet import wikidata_type_lineage
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES, ACCEPTED_COORDINATE_STATUSES
from research_rebuild.mass_linkage.fetch_and_replay_wikidata_homonym_entities_20261004 import yearp1082_claim

W=Path('/workspace'); C=W/'settlements-work/continuation_20261004'; R4=C/'R4'
F=W/'settlements-delivery/continuation-consolidated-20261003'
SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
WIDE=W/'settlements-work/wikidata/wide_v5/wide_point_bindings.parquet'
ENT=W/'settlements-work/wikidata/entities.parquet'; CLAIMS=W/'settlements-work/wikidata/claims.parquet'
HIST=C/'federal_and_history/wikidata_secondary_working_series.parquet'
P31_META=W/'settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json'
EVENTS=W/'settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json'
CORE=R4/'final_long_preparation/fifth_canonical_long_v2/source_preserving_core.parquet'
G=C/'accepted_mass_sixth_reviewed/accepted_identity_edges.parquet'
P=C/'accepted_mass_sixth_reviewed/accepted_point_uses.parquet'
COV=C/'accepted_mass_sixth_reviewed/coverage.json'
OUT=R4/'residual_population_qid_signature_mass_20261004_v2'
PAIR_CHECKPOINT=R4/'residual_population_qid_signature_mass_20261004/all_current_exact_binding_old_source_pair_alternatives.csv'
SEED=20261004

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def digits(v): return re.sub(r'\D','',str(v or ''))
def json_load(v,default=None):
    if v is None or pd.isna(v) or not str(v).strip(): return default
    try: return json.loads(str(v))
    except Exception: return default
def p31_qids(raw):
    qids=set()
    for x in json_load(raw,[]) or []:
        q=x.get('value_qid') if isinstance(x,dict) else None
        if q: qids.add(str(q))
    return sorted(qids)
def pop_int(v):
    try:
        f=float(v)
        return int(f) if np.isfinite(f) and f>=0 and f.is_integer() else None
    except Exception: return None
def truth(v):
    return v is True or str(v).casefold() in {'true','1','yes','t'}
def physical_lineage(raw,profiles):
    q=p31_qids(raw)
    return [x for x in q if profiles.get(x,{}).get('physical_settlement_lineage')]
def no_admin_region_contradiction(raw,expected_region,region_keys):
    expected=region_key(expected_region)
    labels=json_load(raw,[]) or []
    if not isinstance(labels,list): labels=[labels]
    for item in labels:
        if isinstance(item,dict): item=item.get('label') or item.get('value') or item.get('name') or ''
        key=region_key(item)
        if key in region_keys and key!=expected: return False
    return True
def fetch_batch(qids):
    params={'action':'wbgetentities','ids':'|'.join(qids),'props':'claims|labels|descriptions','languages':'ru|en','format':'json','formatversion':'2'}
    url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'RussianSettlementsResearch/1.0 (open research data reconciliation)'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req,timeout=45) as response:
                body=response.read(); status=response.status; final=response.geturl()
            if status!=200 or not final.startswith('https://www.wikidata.org/'):
                raise RuntimeError(f'unexpected Wikidata response {status}: {final}')
            return url,final,status,body
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==3: raise
            time.sleep(min(8,2**attempt))
        except Exception:
            if attempt==3: raise
            time.sleep(min(8,2**attempt))

def evaluate_signatures(qids,rawdir,pairs,profiles):
    rows=[]; wanted=set(map(str,qids))
    for qid,ent in entities_for(wanted,rawdir):
        claims=ent.get('claims',{}); per={}
        for st in claims.get('P1082',[]):
            if st.get('rank')=='deprecated': continue
            c=yearp1082_claim(st); y=c.get('year_precision9')
            if y in (2002,2010): per.setdefault(y,[]).append(c)
        c02=per.get(2002,[]); c10=per.get(2010,[])
        if len(c02)!=1 or len(c10)!=1 or c02[0].get('amount_int') is None or c10[0].get('amount_int') is None:
            rows.append({'wikidata_qid':qid,'statement_status':'missing_multivalued_or_noninteger_year_claim','matching_source_pair_count':0})
            continue
        subset=pairs[pairs.wikidata_qid.astype(str).eq(qid)]; matches=[]
        for r in subset.to_dict('records'):
            d02=int(c02[0]['amount_int'])-int(r['old_2002_population']); d10=int(c10[0]['amount_int'])-int(r['old_2010_population'])
            exact=d02==0 and d10==0
            protected=d02==0 and abs(d10)<=10 and truth(r['old_2010_confidentiality_perturbed'])
            if exact or protected: matches.append((r,exact,d02,d10))
        if len(matches)!=1:
            rows.append({'wikidata_qid':qid,'statement_status':'no_match_or_multiple_source_pairs','matching_source_pair_count':len(matches)})
            continue
        r,exact,d02,d10=matches[0]; label=ent.get('labels',{}).get('ru',{}).get('value','')
        p764=[]
        for st in claims.get('P764',[]):
            try:
                if st.get('rank')!='deprecated': p764.append(digits(st['mainsnak']['datavalue']['value']))
            except Exception: pass
        p31=[]
        for st in claims.get('P31',[]):
            try:
                if st.get('rank')!='deprecated': p31.append(str(st['mainsnak']['datavalue']['value']['id']))
            except Exception: pass
        rows.append({'wikidata_qid':qid,'statement_status':'unique_source_pair_signature','matching_source_pair_count':1,'current_source_record_id':r['current_source_record_id'],'current_population':int(r['current_population']),'old_2002_source_record_id':r['old_2002_source_record_id'],'old_2002_source_population':int(r['old_2002_population']),'old_2010_source_record_id':r['old_2010_source_record_id'],'old_2010_source_population':int(r['old_2010_population']),'population_signature_kind':'exact_both_years' if exact else 'exact_2002_protected_2010_within_10','p1082_2002_delta':d02,'p1082_2010_delta':d10,'fetched_ru_label_exact':norm(label)==norm(r['current_name_raw']),'fetched_p764_exact':any(x==digits(r['current_native_oktmo_digits']) for x in p764),'fetched_physical_p31':bool(physical_lineage(json.dumps([{'value_qid':x} for x in p31]),profiles)),'raw_p31_qids_json':json.dumps(p31),'current_to_2002_uf_outcome':r['current_to_2002_uf_outcome'],'current_to_2010_uf_outcome':r['current_to_2010_uf_outcome'],'event_exact_native_code_guard':bool(r['any_event_exact_native_code_guard']),'signature_edge_candidate_eligible':not bool(r['any_event_exact_native_code_guard']) and r['current_to_2002_uf_outcome']!='year_constrained_collision' and r['current_to_2010_uf_outcome']!='year_constrained_collision','current_population_plus_old_population':int(r['current_population'])+int(r['old_2002_population'])+int(r['old_2010_population'])})
    return rows
def source_event_codes():
    data=json.loads(EVENTS.read_text(encoding='utf-8'))
    out=set()
    for e in data:
        for k in ('from_settlement_id_legacy_candidate','to_settlement_id_legacy_candidate'):
            raw=e.get(k)
            if raw and str(raw).startswith('RU-OKTMO-'): out.add(digits(raw))
    return out

def make_pool():
    # Build the exact sixth accepted UF and current point-bearing residual from
    # all selected observations; source-key candidate indexing is physical-only.
    sel=pd.read_parquet(SEL,columns=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_scope','population_value_quality','is_additive_settlement_record','entity_grain_status','okato','oktmo','fias_id','source_sha256','source_locator'])
    sel.source_record_id=sel.source_record_id.astype(str); sel.census_year=sel.census_year.astype(int)
    sel['pop_int']=sel.population.map(pop_int)
    # The selected source series marks the 2010 confidentiality-protected cohort
    # explicitly. Preserve its scope caveat and use ±10 only in a separate replay.
    sel['population_confidentiality_perturbed']=sel.population_value_quality.astype(str).eq('secondary_confidentiality_protected_value_exact_scope_unverified')
    sel['name_key']=sel.settlement_name.map(norm); sel['type_key']=sel.settlement_type.map(typ); sel['region_key']=sel.region_raw.map(region_key)
    sel['key']=list(zip(sel.name_key,sel.type_key,sel.region_key))
    sel['oktmo_digits']=sel.oktmo.map(digits); sel['okato_digits']=sel.okato.map(digits)
    uf=YearUF(sel.source_record_id.tolist(),sel.census_year.tolist())
    graph=pd.read_parquet(G,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
    if not set(graph.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(graph.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES): raise SystemExit('sixth graph status guard failed')
    for e in graph.itertuples(index=False):
        if e.relation!='same_place': raise SystemExit('sixth graph contains a noncanonical accepted relation')
        a,b=str(e.from_source_record_id),str(e.to_source_record_id)
        if a not in uf.idx or b not in uf.idx or int(sel.iloc[uf.idx[a]].census_year)!=int(e.from_year) or int(sel.iloc[uf.idx[b]].census_year)!=int(e.to_year): raise SystemExit('sixth graph endpoint/year guard failed')
        if uf.union_ids(a,b)=='year_constrained_collision': raise SystemExit('sixth graph year collision')
    points=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_admission_status'])
    points=points[points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
    if points.target_source_record_id.astype(str).duplicated().any(): raise SystemExit('duplicate accepted point target in sixth ledger')
    point_ids=set(points.target_source_record_id.astype(str))
    masks=uf.bits_by_row(); sel['uf_year_mask']=masks
    bits=sel.set_index('source_record_id').uf_year_mask.to_dict()
    # The fifth core provides the pinned territorial coverage classification;
    # exclude outside-coverage current observations from this ordinary mass route.
    outside= pd.read_parquet(CORE,columns=['source_record_id','census_2002_status','census_2010_status'])
    outside.source_record_id=outside.source_record_id.astype(str)
    outside_ids=set(outside.loc[outside.census_2002_status.eq('outside_russian_census_scope')|outside.census_2010_status.eq('outside_russian_census_scope'),'source_record_id'])
    s21_all=sel[(sel.census_year==2021)&sel.is_additive_settlement_record.fillna(False)&sel.type_key.isin(PHYSICAL)&sel.name_key.ne('')&sel.region_key.ne('')&sel.population_scope.fillna('').astype(str).str.casefold().eq('settlement')].copy()
    counts=s21_all.groupby('key').source_record_id.nunique().to_dict()
    s21=s21_all.copy()
    s21=s21[s21.source_record_id.isin(point_ids)&(s21.uf_year_mask.astype(int)!=7)&~s21.source_record_id.isin(outside_ids)].copy()
    # Current-year source keys and exact native code competition are retained as
    # separate evidence. A duplicated name/type/province is not an automatic
    # veto when the current 11-digit P764 object is unique.
    s21['current_key_count_2021']=s21.key.map(counts)
    s21['current_population']=s21.pop_int.fillna(0).astype('int64')
    s21['qid_potential_years']=s21.uf_year_mask.map(lambda m:[y for y,b in ((2002,1),(2010,2)) if not int(m)&b])
    widecols=['source_record_id','wikidata_qid','source_oktmo_raw','source_oktmo_exact_digits','source_oktmo_digit_width','source_name','source_type','source_region','wikidata_tsv_exact_p764_value_raw','wikidata_truthy_exact_p764_match','wikidata_truthy_exact_p764_claims_json','wikidata_name_exact_label','wikidata_tsv_ru_labels_json','wikidata_truthy_p31_claims_json','wikidata_truthy_p131_claims_json','wikidata_tsv_ru_admin_labels_json','entity_competition_across_tsv_or_truthy','truthy_entity_competition_for_exact_oktmo','source_observation_competition_for_exact_oktmo','candidate_status']
    wide=pd.read_parquet(WIDE,columns=widecols); wide.source_record_id=wide.source_record_id.astype(str)
    wide=wide.drop_duplicates(['source_record_id','wikidata_qid'])
    cur=s21.merge(wide,on='source_record_id',how='inner',validate='one_to_many')
    cur['physical_p31_lineage_qids_json']='[]'
    p31meta=json.loads(P31_META.read_text(encoding='utf-8')); profiles=wikidata_type_lineage(p31meta)
    cur['physical_p31_lineage_qids_json']=cur.wikidata_truthy_p31_claims_json.map(lambda x:json.dumps(physical_lineage(x,profiles),ensure_ascii=False))
    cur['native_p764_exact']=cur.apply(lambda r: len(str(r.oktmo_digits))==11 and str(r.oktmo_digits)==str(r.source_oktmo_exact_digits) and str(r.source_oktmo_digit_width)=='11' and bool(r.wikidata_truthy_exact_p764_match),axis=1)
    cur['current_qid_label_exact']=cur.apply(lambda r: bool(r.wikidata_name_exact_label) and norm(r.settlement_name)==norm(r.source_name),axis=1)
    cur['current_qid_name_type_region_match']=cur.apply(lambda r:norm(r.settlement_name)==norm(r.source_name) and typ(r.settlement_type)==typ(r.source_type) and region_key(r.region_raw)==region_key(r.source_region),axis=1)
    cur['current_physical_p31_lineage']=cur.physical_p31_lineage_qids_json.map(lambda x:bool(json.loads(x)))
    known_region_keys=set(s21_all.region_key.dropna().astype(str))
    cur['current_admin_region_clear']=cur.apply(lambda r:no_admin_region_contradiction(r.wikidata_tsv_ru_admin_labels_json,r.region_raw,known_region_keys),axis=1)
    cur['current_wide_competition_clear']=~(cur.entity_competition_across_tsv_or_truthy.fillna(True)|cur.truthy_entity_competition_for_exact_oktmo.fillna(True)|cur.source_observation_competition_for_exact_oktmo.fillna(True))
    current_ok=cur[cur.native_p764_exact&cur.current_qid_label_exact&cur.current_qid_name_type_region_match&cur.current_physical_p31_lineage&cur.current_admin_region_clear&cur.current_wide_competition_clear].copy()
    if current_ok.source_record_id.duplicated().any(): raise SystemExit('more than one eligible QID per current source row')
    qid_source_counts=current_ok.groupby(current_ok.wikidata_qid.astype(str)).source_record_id.nunique()
    duplicate_qids=set(qid_source_counts[qid_source_counts.gt(1)].index)
    current_ok=current_ok[~current_ok.wikidata_qid.astype(str).isin(duplicate_qids)].copy()
    # Old pairs use exact normalized physical name/type/province source context.
    # District differences remain evidence fields; they are not a hard veto.
    old=sel[sel.census_year.isin([2002,2010])&sel.is_additive_settlement_record.fillna(False)&sel.type_key.isin(PHYSICAL)&sel.name_key.ne('')&sel.region_key.ne('')].copy()
    old=old[old.pop_int.notna()&~old.source_record_id.isin(outside_ids)]
    old_by_key_year={(k,int(y)):g.to_dict('records') for (k,y),g in old.groupby(['key','census_year'],sort=False)}
    event_codes=source_event_codes()
    # Build the old source-pair alternative ledger only for WIDE-verified current
    # QIDs and retain every whole-key alternative needed for signature uniqueness.
    old_pairs=[]; pair_counts=Counter(); potential=[]
    for r in current_ok.itertuples(index=False):
        a=old_by_key_year.get((r.key,2002),[]); b=old_by_key_year.get((r.key,2010),[])
        if not a or not b: continue
        current_mask=int(r.uf_year_mask); current_root=uf.find(uf.idx[str(r.source_record_id)])
        current_code=str(r.oktmo_digits)
        for x in a:
            for y in b:
                vec=(int(x['pop_int']),int(y['pop_int']))
                pair_counts[(r.wikidata_qid,vec)]+=1
                xroot=uf.find(uf.idx[str(x['source_record_id'])]); yroot=uf.find(uf.idx[str(y['source_record_id'])])
                edge_out=[]
                for xx,yr,root in ((x,2002,xroot),(y,2010,yroot)):
                    oldmask=int(uf.mask[root]);
                    if root==current_root: edge_out.append((yr,'already_connected'))
                    elif current_mask & oldmask: edge_out.append((yr,'year_constrained_collision'))
                    else: edge_out.append((yr,'year_constrained_merge_possible'))
                evt=bool(current_code in event_codes or digits(x.get('oktmo')) in event_codes or digits(x.get('okato')) in event_codes or digits(y.get('oktmo')) in event_codes or digits(y.get('okato')) in event_codes)
                # Direct populations are mandatory; protected 2010 rows are kept
                # for a separate documented ±10 signature comparison downstream.
                pair={'wikidata_qid':str(r.wikidata_qid),'current_source_record_id':str(r.source_record_id),'current_population':int(r.current_population),'current_uf_mask':current_mask,'current_source_key_count_2021':int(r.current_key_count_2021),'current_name_raw':r.settlement_name,'current_type_raw':r.settlement_type,'current_region_raw':r.region_raw,'current_district_raw':r.district_raw,'current_native_oktmo_raw':r.oktmo,'current_native_oktmo_digits':current_code,'current_p764_raw':r.wikidata_tsv_exact_p764_value_raw,'current_p764_exact':bool(r.native_p764_exact),'current_ru_label_exact':bool(r.current_qid_label_exact),'current_physical_p31_lineage_qids_json':r.physical_p31_lineage_qids_json,'current_admin_region_clear':bool(r.current_admin_region_clear),'current_source_sha256':r.source_sha256,'current_source_locator':r.source_locator,'old_2002_source_record_id':str(x['source_record_id']),'old_2002_population':int(x['pop_int']),'old_2002_population_quality':x['population_value_quality'],'old_2002_confidentiality_perturbed':truth(x.get('population_confidentiality_perturbed',False)),'old_2002_name_raw':x['settlement_name'],'old_2002_type_raw':x['settlement_type'],'old_2002_region_raw':x['region_raw'],'old_2002_district_raw':x['district_raw'],'old_2002_municipality_raw':x['municipality_raw'],'old_2002_native_okato_raw':x['okato'],'old_2002_native_oktmo_raw':x['oktmo'],'old_2002_source_sha256':x['source_sha256'],'old_2002_source_locator':x['source_locator'],'old_2010_source_record_id':str(y['source_record_id']),'old_2010_population':int(y['pop_int']),'old_2010_population_quality':y['population_value_quality'],'old_2010_confidentiality_perturbed':truth(y.get('population_confidentiality_perturbed',False)),'old_2010_name_raw':y['settlement_name'],'old_2010_type_raw':y['settlement_type'],'old_2010_region_raw':y['region_raw'],'old_2010_district_raw':y['district_raw'],'old_2010_municipality_raw':y['municipality_raw'],'old_2010_native_okato_raw':y['okato'],'old_2010_native_oktmo_raw':y['oktmo'],'old_2010_source_sha256':y['source_sha256'],'old_2010_source_locator':y['source_locator'],'current_to_2002_uf_outcome':edge_out[0][1],'current_to_2010_uf_outcome':edge_out[1][1],'any_event_exact_native_code_guard':evt,'legacy_identity_flags_used_as_acceptance_signal':False,'candidate_only':True}
                old_pairs.append(pair)
                if not evt and all(o!='year_constrained_collision' for _,o in edge_out): potential.append(pair)
    pairs=pd.DataFrame(old_pairs)
    if len(pairs):
        pairs['source_population_vector_unique_among_old_name_type_province_alternatives']=pairs.apply(lambda r:pair_counts[(r.wikidata_qid,(int(r.old_2002_population),int(r.old_2010_population))) ]==1,axis=1)
        # Unique exact vectors are ranked; if 2010 values are protected, replay
        # separately allows only a published ±10 comparison and requires that
        # the tolerance vector also remain unique across all old pair alternatives.
        pairs['old_row_pair_has_required_exact_population_quality']=pairs.old_2002_population_quality.astype(str).eq('direct_published_census_value')&pairs.old_2010_population_quality.astype(str).isin({'direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'})
        pairs.to_csv(OUT/'all_current_exact_binding_old_source_pair_alternatives.csv',index=False)
    potential_df=pairs[(~pairs.any_event_exact_native_code_guard.fillna(True))&(~pairs.current_to_2002_uf_outcome.eq('year_constrained_collision'))&(~pairs.current_to_2010_uf_outcome.eq('year_constrained_collision'))].copy() if len(pairs) else pd.DataFrame()
    if len(potential_df):
        # Fetch ranking: potential current point population plus actual old-row
        # population, then fixed seeded tie break. First protect province/district
        # representation, then fill the remaining budget by gain proxy.
        potential_df['priority_weight']=potential_df.current_population+potential_df.old_2002_population+potential_df.old_2010_population
        potential_df=potential_df[potential_df.source_population_vector_unique_among_old_name_type_province_alternatives&potential_df.old_row_pair_has_required_exact_population_quality].copy()
        targets=potential_df.sort_values(['priority_weight','current_population','wikidata_qid'],ascending=[False,False,True]).drop_duplicates('wikidata_qid')
        # Per current region/district top-1 frame first, then global fill to 2,000.
        targets['stratum_key']=targets.current_region_raw.fillna('').astype(str)+' | '+targets.current_district_raw.fillna('').astype(str)
        strat=targets.sort_values(['priority_weight','current_population','wikidata_qid'],ascending=[False,False,True]).groupby('stratum_key',sort=True,as_index=False).head(1)
        rest=targets[~targets.wikidata_qid.isin(set(strat.wikidata_qid))].sort_values(['priority_weight','current_population','wikidata_qid'],ascending=[False,False,True])
        request=pd.concat([strat,rest],ignore_index=True).drop_duplicates('wikidata_qid').head(2000).copy()
    else:
        targets=pd.DataFrame(); request=pd.DataFrame()
    # Existing complete-response/full-entity caches are inventory only; no QID
    # is re-requested from any prior raw batch or the current structured cache.
    raw_roots=[R4/'wide_qid_homonym_full_entity_retrieval_20261004/entity_fetch_and_replay',R4/'wide_qid_homonym_full_entity_retrieval_20261004_v2/entity_fetch_and_replay',R4/'ten_digit_oktmo_temporal_recovery_20261004']
    raw_cache={}
    for root in raw_roots:
        for path in sorted(root.glob('raw_entity_batch_*.json')):
            body=path.read_bytes(); ent=json.loads(body.decode('utf-8')).get('entities',{})
            for qid in ent: raw_cache.setdefault(str(qid),{'raw_file':str(path),'sha256':sha_bytes(body),'cache_family':root.name})
    full_cache=set(pd.read_parquet(ENT,columns=['wikidata_qid']).wikidata_qid.astype(str))
    hist=pd.read_parquet(HIST,columns=['qid','year_prefix','rank_is_deprecated','date_ambiguous_hold'])
    hist.year_prefix=hist.year_prefix.astype(str); hist=hist[hist.year_prefix.isin(['2002','2010'])&~hist.rank_is_deprecated.fillna(True)&~hist.date_ambiguous_hold.fillna(True)]
    histcache=hist.groupby('qid').year_prefix.agg(lambda x:','.join(sorted(set(x)))).to_dict()
    if len(request):
        request['existing_raw_full_response_cache']=request.wikidata_qid.astype(str).map(lambda q:raw_cache.get(q,{}).get('cache_family',''))
        request['existing_structured_entity_cache']=request.wikidata_qid.astype(str).isin(full_cache)
        request['existing_history_overlay_years']=request.wikidata_qid.astype(str).map(histcache).fillna('')
        request['fetch_required_uncached_only']=~request.wikidata_qid.astype(str).isin(set(raw_cache)|full_cache)
        request=request[request.fetch_required_uncached_only].copy().head(2000)
        request.insert(0,'fetch_order',range(1,len(request)+1))
    # Candidate outputs are fixed before any network fetch. Keep pair records for
    # requested QIDs and preserve all exact-key alternatives, including holds.
    if len(pairs) and len(request):
        qset=set(request.wikidata_qid.astype(str)); request_pairs=pairs[pairs.wikidata_qid.astype(str).isin(qset)].copy()
    else: request_pairs=pd.DataFrame()
    request.to_csv(OUT/'fetch_request_uncached_top2000.csv',index=False)
    request_pairs.to_csv(OUT/'fetch_request_old_source_pair_alternatives.csv',index=False)
    pool=pd.DataFrame({'source_record_id':current_ok.source_record_id.astype(str),'wikidata_qid':current_ok.wikidata_qid.astype(str),'current_population':current_ok.current_population,'current_region_raw':current_ok.region_raw,'current_district_raw':current_ok.district_raw,'current_uf_mask':current_ok.uf_year_mask,'current_key_count_2021':current_ok.current_key_count_2021,'current_physical_p31_lineage_qids_json':current_ok.physical_p31_lineage_qids_json,'current_oktmo_raw':current_ok.oktmo,'current_oktmo_digits':current_ok.oktmo_digits,'candidate_status_raw_preserved':current_ok.candidate_status})
    pool.to_csv(OUT/'current_exact_native_p764_physical_point_pool.csv',index=False)
    if len(pairs): pairs.to_csv(OUT/'source_pair_signature_candidates_and_holds.csv',index=False)
    pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SEL,EVID,WIDE,ENT,CLAIMS,HIST,P31_META,EVENTS,CORE,G,P,COV]}
    metrics={'current_point_fullchain_residual_targets_before_QID_gates':len(s21),'current_QIDs_exact_P764_label_P31_source_context_and_no_competition':len(current_ok),'current_QID_pool_population':int(current_ok.current_population.sum()),'all_old_pair_alternatives':len(pairs),'potential_old_pairs_no_event_no_collision':len(potential_df),'unique_population_vector_pair_candidates':int(potential_df.source_population_vector_unique_among_old_name_type_province_alternatives.sum()) if len(potential_df) else 0,'fetch_request_uncached_qids':len(request),'fetch_request_target_current_population_sum':int(request.current_population.sum()) if len(request) else 0,'fetch_request_old_population_sum_on_ranked_pairs':int((request.old_2002_population+request.old_2010_population).sum()) if len(request) else 0,'raw_response_cache_qids':len(raw_cache),'structured_entity_cache_qids':len(full_cache),'current_overlay_2002_2010_qids':len(histcache),'current_overlay_both_old_years':sum(1 for v in histcache.values() if v=='2002,2010')}
    manifest={'status':'candidate_and_fetch_plan_only_no_identity_population_or_point_admissions','seed':SEED,'rule':'current exact literal 11-digit OKTMO=P764, exact current Russian label/name/type/province, explicit cached physical P31/P279 ancestry, accepted sixth point, no code/source competition; old rows are additive exact typed-name/type/province publisher rows; two actual dated single-valued P1082 values must select a unique 2002/2010 source pair; P1082 remains secondary corroboration; 2010 protected source value may match only within documented ±10 and only where unique among all old alternatives; exact native event codes, aggregates, year collisions held. Old pair need not already be connected.','baseline_sixth_graph_sha256':sha(G),'baseline_sixth_points_sha256':sha(P),'input_pins':pins,'screen_counts':metrics,'network_policy':'HTTPS Wikidata API, TLS certificate verification enabled, maximum 50 QIDs/request, 1.2 seconds between successful batches, retry only HTTP 429/5xx or transient errors, preserve raw response bytes and exact URL/status/hash.'}
    (OUT/'screen_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return request,request_pairs,manifest,raw_cache,full_cache,histcache,profiles

def load_prepared_pairs():
    """Reuse the complete source-pair screen checkpoint produced before a fetch."""
    pair_path=PAIR_CHECKPOINT
    cols=['wikidata_qid','current_source_record_id','current_population','current_uf_mask','current_source_key_count_2021','current_name_raw','current_type_raw','current_region_raw','current_district_raw','current_native_oktmo_raw','current_native_oktmo_digits','current_p764_raw','current_p764_exact','current_ru_label_exact','current_physical_p31_lineage_qids_json','current_admin_region_clear','current_source_sha256','current_source_locator','old_2002_source_record_id','old_2002_population','old_2002_population_quality','old_2002_confidentiality_perturbed','old_2002_name_raw','old_2002_type_raw','old_2002_region_raw','old_2002_district_raw','old_2002_municipality_raw','old_2002_native_okato_raw','old_2002_native_oktmo_raw','old_2002_source_sha256','old_2002_source_locator','old_2010_source_record_id','old_2010_population','old_2010_population_quality','old_2010_confidentiality_perturbed','old_2010_name_raw','old_2010_type_raw','old_2010_region_raw','old_2010_district_raw','old_2010_municipality_raw','old_2010_native_okato_raw','old_2010_native_oktmo_raw','old_2010_source_sha256','old_2010_source_locator','current_to_2002_uf_outcome','current_to_2010_uf_outcome','any_event_exact_native_code_guard','candidate_only','source_population_vector_unique_among_old_name_type_province_alternatives','old_row_pair_has_required_exact_population_quality']
    if not pair_path.exists(): return make_pool()
    pairs=pd.read_csv(pair_path,usecols=cols,low_memory=False,dtype={'wikidata_qid':str,'current_source_record_id':str,'old_2002_source_record_id':str,'old_2010_source_record_id':str,'current_native_oktmo_digits':str})
    for c in ['any_event_exact_native_code_guard','candidate_only','source_population_vector_unique_among_old_name_type_province_alternatives','old_row_pair_has_required_exact_population_quality','current_p764_exact','current_ru_label_exact','current_admin_region_clear']:
        pairs[c]=pairs[c].map(truth)
    pairs['old_row_pair_has_required_exact_population_quality']=pairs.old_2002_population_quality.astype(str).eq('direct_published_census_value')&pairs.old_2010_population_quality.astype(str).isin({'direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'})
    pairs.current_population=pd.to_numeric(pairs.current_population,errors='coerce').fillna(0).astype('int64')
    pairs.old_2002_population=pd.to_numeric(pairs.old_2002_population,errors='coerce').fillna(-1).astype('int64')
    pairs.old_2010_population=pd.to_numeric(pairs.old_2010_population,errors='coerce').fillna(-1).astype('int64')
    raw_roots=[R4/'wide_qid_homonym_full_entity_retrieval_20261004/entity_fetch_and_replay',R4/'wide_qid_homonym_full_entity_retrieval_20261004_v2/entity_fetch_and_replay',R4/'ten_digit_oktmo_temporal_recovery_20261004']
    raw_cache={}
    for root in raw_roots:
        for path in sorted(root.glob('raw_entity_batch_*.json')):
            body=path.read_bytes(); ent=json.loads(body.decode('utf-8')).get('entities',{})
            for qid in ent: raw_cache.setdefault(str(qid),{'raw_file':str(path),'sha256':sha_bytes(body),'cache_family':root.name})
    full_cache=set(pd.read_parquet(ENT,columns=['wikidata_qid']).wikidata_qid.astype(str))
    hist=pd.read_parquet(HIST,columns=['qid','year_prefix','rank_is_deprecated','date_ambiguous_hold'])
    hist.year_prefix=hist.year_prefix.astype(str); hist=hist[hist.year_prefix.isin(['2002','2010'])&~hist.rank_is_deprecated.fillna(True)&~hist.date_ambiguous_hold.fillna(True)]
    histcache=hist.groupby('qid').year_prefix.agg(lambda x:','.join(sorted(set(x)))).to_dict()
    valid=pairs[(~pairs.any_event_exact_native_code_guard)&(~pairs.current_to_2002_uf_outcome.eq('year_constrained_collision'))&(~pairs.current_to_2010_uf_outcome.eq('year_constrained_collision'))&pairs.source_population_vector_unique_among_old_name_type_province_alternatives&pairs.old_row_pair_has_required_exact_population_quality].copy()
    valid['priority_weight']=valid.current_population+valid.old_2002_population+valid.old_2010_population
    # One high-value old pair per exact-current QID, retaining current region and
    # district in the deterministic stratification key.
    ranked=valid.sort_values(['priority_weight','current_population','wikidata_qid'],ascending=[False,False,True]).drop_duplicates('wikidata_qid')
    ranked=ranked[~ranked.wikidata_qid.astype(str).isin(set(raw_cache)|full_cache)].copy()
    ranked['stratum_key']=ranked.current_region_raw.fillna('').astype(str)+' | '+ranked.current_district_raw.fillna('').astype(str)
    strat=ranked.groupby('stratum_key',sort=True,as_index=False).head(1).sort_values(['priority_weight','current_population','wikidata_qid'],ascending=[False,False,True])
    rest=ranked[~ranked.wikidata_qid.isin(set(strat.wikidata_qid))].sort_values(['priority_weight','current_population','wikidata_qid'],ascending=[False,False,True])
    request=pd.concat([strat,rest],ignore_index=True).drop_duplicates('wikidata_qid').head(2000).copy()
    request.insert(0,'fetch_order',range(1,len(request)+1)); qset=set(request.wikidata_qid.astype(str))
    request_pairs=pairs[pairs.wikidata_qid.astype(str).isin(qset)].copy()
    request.to_csv(OUT/'fetch_request_uncached_top2000.csv',index=False)
    request_pairs.to_csv(OUT/'fetch_request_old_source_pair_alternatives.csv',index=False)
    pool=ranked.drop_duplicates('wikidata_qid')[['current_source_record_id','wikidata_qid','current_population','current_region_raw','current_district_raw','current_uf_mask','current_source_key_count_2021','current_physical_p31_lineage_qids_json','current_native_oktmo_raw','current_native_oktmo_digits']]
    pool.to_csv(OUT/'current_exact_native_p764_physical_point_pool.csv',index=False)
    pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SEL,EVID,WIDE,ENT,CLAIMS,HIST,P31_META,EVENTS,CORE,G,P,COV,pair_path]}
    if pins[str(G)]['sha256']!='cc62fc8d3184c43f6ce09cea0ce71618077347ea4dee0f53ad9709f5c20a8241' or pins[str(P)]['sha256']!='a67529375e63391e7d05e3ab902ff20884ec3fd4483c7b0bbc988ca056b3c994': raise SystemExit('sixth accepted graph/point pin mismatch')
    profiles=wikidata_type_lineage(json.loads(P31_META.read_text(encoding='utf-8')))
    manifest={'status':'candidate_and_fetch_plan_only_no_identity_population_or_point_admissions','seed':SEED,'source_pair_checkpoint':str(pair_path),'source_pair_checkpoint_sha256':pins[str(pair_path)]['sha256'],'baseline_sixth_graph_sha256':pins[str(G)]['sha256'],'baseline_sixth_points_sha256':pins[str(P)]['sha256'],'input_pins':pins,'screen_counts':{'all_old_source_pair_alternatives':len(pairs),'distinct_candidate_current_QIDs_with_two_year_source_pair':int(pairs.wikidata_qid.nunique()),'unique_vector_direct_population_non_event_collision_safe_pairs':len(valid),'fetch_request_uncached_QIDs':len(request),'fetch_request_current_population_sum':int(request.current_population.sum()) if len(request) else 0,'fetch_request_old_pair_population_sum':int((request.old_2002_population+request.old_2010_population).sum()) if len(request) else 0,'raw_response_cache_unique_QIDs':len(raw_cache),'structured_entity_cache_unique_QIDs':len(full_cache),'history_overlay_QIDs_with_2002_or_2010':len(histcache),'history_overlay_QIDs_with_both_old_years':sum(v=='2002,2010' for v in histcache.values())},'rule':'Current source endpoint must have accepted sixth point, exact 11-digit current OKTMO=P764, exact Russian label/name/type/province, explicit cached physical P31/P279 ancestry, no native code/source observation competition. Old endpoints are additive exact typed name/type/province publisher rows with direct source population. Two actual dated single-valued P1082 values must select one old 2002/2010 pair among all exact key alternatives. Secondary P1082 never replaces primary population. A 2010 ±10 match is staged only when the selected source record has explicit protected-value quality, and that tolerance must be unique among alternatives. Exact native event codes, aggregates, same-year collisions are held. Old 2002/2010 pair need not already be connected.'}
    (OUT/'screen_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return request,request_pairs,manifest,raw_cache,full_cache,histcache,profiles

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'raw_entity_batches').exists(): raise SystemExit('raw response directory exists; refusing to repeat network fetch')
    request,pairs,manifest,raw_cache,full_cache,histcache,profiles=load_prepared_pairs()
    qids=request.wikidata_qid.astype(str).tolist() if len(request) else []
    # Fetch in source order, checkpoint candidate-signature receipts every 250
    # responses, and retain one append-only batch directory for final review.
    (OUT/'raw_entity_batches').mkdir()
    batch_meta=[]; metadata_rows=[]; statement_rows=[]; edge_rows=[]; fetch_starts=time.monotonic()
    for ix in range(0,len(qids),50):
        batch_num=ix//50+1; batch=qids[ix:ix+50]
        start=time.monotonic(); url,final,status,body=fetch_batch(batch); elapsed=time.monotonic()-start
        parsed=json.loads(body.decode('utf-8')); entities=parsed.get('entities',{})
        missing=sorted(set(batch)-set(entities))
        if missing: raise SystemExit(f'Wikidata API missing requested QIDs: {missing[:10]}')
        rawpath=OUT/'raw_entity_batches'/f'raw_entity_batch_{batch_num:02d}.json'; rawpath.write_bytes(body)
        rawsha=sha_bytes(body); batch_meta.append({'batch_number':batch_num,'qids_requested':batch,'request_url':url,'final_url':final,'http_status':status,'retrieved_at_utc':utc(),'raw_response_sha256':rawsha,'raw_response_bytes':len(body),'elapsed_seconds':round(elapsed,3),'raw_file':str(rawpath),'missing_qids':missing})
        for qid,e in entities.items():
            p31=[]
            for st in e.get('claims',{}).get('P31',[]):
                try:p31.append(st['mainsnak']['datavalue']['value']['id'])
                except Exception:pass
            metadata_rows.append({'wikidata_qid':qid,'lastrevid':e.get('lastrevid'),'modified':e.get('modified'),'label_ru':e.get('labels',{}).get('ru',{}).get('value'),'label_en':e.get('labels',{}).get('en',{}).get('value'),'description_ru':e.get('descriptions',{}).get('ru',{}).get('value'),'P31_qids_json':json.dumps(p31),'P764_claim_count':len(e.get('claims',{}).get('P764',[])),'P1082_claim_count':len(e.get('claims',{}).get('P1082',[])),'P625_claim_count':len(e.get('claims',{}).get('P625',[])),'raw_entity_file':str(rawpath),'raw_entity_sha256':rawsha})
            for st in e.get('claims',{}).get('P1082',[]):
                rec=yearp1082_claim(st); statement_rows.append({'wikidata_qid':qid,**rec,'entity_lastrevid':e.get('lastrevid'),'entity_modified':e.get('modified'),'raw_entity_file':str(rawpath),'raw_entity_sha256':rawsha,'retrieved_at_utc':batch_meta[-1]['retrieved_at_utc']})
        if batch_num==1:
            pilot_rows=evaluate_signatures(batch,OUT/'raw_entity_batches',pairs,profiles)
            pilot=pd.DataFrame(pilot_rows)
            pilot.to_csv(OUT/'pilot_first50_two_year_signature_results.csv',index=False)
            valid=pilot[(pilot.statement_status=='unique_source_pair_signature')&pilot.fetched_ru_label_exact.fillna(False)&pilot.fetched_p764_exact.fillna(False)&pilot.fetched_physical_p31.fillna(False)&pilot.signature_edge_candidate_eligible.fillna(False)] if len(pilot) else pd.DataFrame()
            pilot_summary={'requested_qid_count':len(batch),'returned_qid_count':len(entities),'http_status':status,'request_url':url,'final_url':final,'raw_entity_file':str(rawpath),'raw_entity_sha256':rawsha,'raw_entity_bytes':len(body),'api_elapsed_seconds':round(elapsed,3),'pilot_result_rows':len(pilot),'unique_two_year_source_signature_count':int((pilot.statement_status=='unique_source_pair_signature').sum()) if len(pilot) else 0,'raw_label_code_physical_p31_valid_signature_count':len(valid),'valid_signature_current_population_sum':int(valid.current_population.sum()) if len(valid) else 0,'valid_signature_old_population_sum':int((valid.old_2002_source_population+valid.old_2010_source_population).sum()) if len(valid) else 0,'valid_signature_current_plus_old_population_gross':int(valid.current_population_plus_old_population.sum()) if len(valid) else 0,'candidate_only':True,'identity_admitted':False,'population_admitted':False}
            (OUT/'pilot_first50_result.json').write_text(json.dumps(pilot_summary,ensure_ascii=False,indent=2)+'\n')
            print('PILOT_FIRST_50 '+json.dumps(pilot_summary,ensure_ascii=False),flush=True)
        # Checkpoint durable review slices after each 250-QID block. No decisions
        # are admitted; the chunk is exactly the fetched qids plus their raw rows.
        if batch_num%5==0 or batch_num==len(range(0,len(qids),50)):
            upto=set(qids[:batch_num*50])
            pref=OUT/f'progress_{min(batch_num*50,len(qids)):04d}'
            pref.mkdir(exist_ok=True)
            mdf=pd.DataFrame(metadata_rows); sdf=pd.DataFrame(statement_rows)
            mdf.to_csv(pref/'fetched_entity_metadata.csv',index=False)
            sdf.to_csv(pref/'fetched_P1082_statements.csv',index=False)
            # Source-signature candidate rows selected only by single year-precision
            # values and unique source population vectors. Full replay follows below.
            status_rows=[]
            pm=pairs[pairs.wikidata_qid.astype(str).isin(upto)].copy()
            for qid, ent in entities_for(qids[:batch_num*50],OUT/'raw_entity_batches'):
                claims=ent.get('claims',{}); per_year={}
                for st in claims.get('P1082',[]):
                    row=yearp1082_claim(st); y=row['year_precision9']
                    if y in (2002,2010) and row['rank']!='deprecated': per_year.setdefault(y,[]).append(row)
                c02=per_year.get(2002,[]); c10=per_year.get(2010,[])
                status='one_single_year_precision_statement_each_year' if len(c02)==len(c10)==1 and c02[0]['amount_int'] is not None and c10[0]['amount_int'] is not None else 'missing_multivalued_or_noninteger_year_claim'
                matches=[]
                if status.startswith('one_'):
                    for rr in pm[pm.wikidata_qid.astype(str).eq(qid)].to_dict('records'):
                        d02=int(c02[0]['amount_int'])-int(rr['old_2002_population']); d10=int(c10[0]['amount_int'])-int(rr['old_2010_population'])
                        exact=(d02==0 and d10==0)
                        protected=(d02==0 and abs(d10)<=10 and bool(rr['old_2010_confidentiality_perturbed']))
                        if exact or protected: matches.append((rr,exact,d02,d10))
                # Only unique population-vector match to one old source pair is a
                # candidate signature. This row still requires independent review.
                if len(matches)==1:
                    rr,exact,d02,d10=matches[0]
                    status_rows.append({'wikidata_qid':qid,'current_source_record_id':rr['current_source_record_id'],'old_2002_source_record_id':rr['old_2002_source_record_id'],'old_2010_source_record_id':rr['old_2010_source_record_id'],'p1082_year_claim_status':status,'p1082_2002_population':int(c02[0]['amount_int']),'p1082_2010_population':int(c10[0]['amount_int']),'old_2002_source_population':int(rr['old_2002_population']),'old_2010_source_population':int(rr['old_2010_population']),'population_signature_kind':'exact_both_years' if exact else 'exact_2002_protected_2010_within_10','p1082_2002_delta':d02,'p1082_2010_delta':d10,'unique_matching_old_source_pair_count':len(matches),'candidate_only':True,'population_admitted':False,'identity_admitted':False,'raw_entity_sha256':next((z['raw_entity_sha256'] for z in metadata_rows if z['wikidata_qid']==qid),'')})
                elif len(matches)>1:
                    status_rows.append({'wikidata_qid':qid,'p1082_year_claim_status':status,'unique_matching_old_source_pair_count':len(matches),'hold_reason':'multiple_old_pairs_match_signature','candidate_only':True,'identity_admitted':False,'population_admitted':False})
            pd.DataFrame(status_rows).to_csv(pref/'unique_two_year_population_signature_candidates.csv',index=False)
            receipt={'status':'progressive_candidate_only_review_checkpoint','qids_fetched':min(batch_num*50,len(qids)),'raw_batch_count':batch_num,'raw_batch_manifest_sha256':sha_bytes(json.dumps(batch_meta,sort_keys=True).encode()),'metadata_sha256':sha(pref/'fetched_entity_metadata.csv'),'statements_sha256':sha(pref/'fetched_P1082_statements.csv'),'candidate_signature_sha256':sha(pref/'unique_two_year_population_signature_candidates.csv'),'fixed_request_sha256':sha(OUT/'fetch_request_uncached_top2000.csv')}
            (pref/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if ix+50<len(qids): time.sleep(1.2)
    # Freeze complete API statement inventory and batch manifest once, after all
    # responses have been stored and verified.
    pd.DataFrame(batch_meta).to_json(OUT/'raw_batch_manifest.json',orient='records',force_ascii=False,indent=2)
    pd.DataFrame(metadata_rows).to_csv(OUT/'fetched_entity_metadata.csv',index=False)
    pd.DataFrame(statement_rows).to_csv(OUT/'fetched_P1082_statements.csv',index=False)
    # Rebuild candidate signature ledger from all raw batches; no candidate is
    # automatically accepted by this script.
    final=[]; entity_cache=entities_for(qids,OUT/'raw_entity_batches'); pmap=pairs.groupby('wikidata_qid') if len(pairs) else {}
    for qid,ent in entity_cache:
        parsed=[yearp1082_claim(s) for s in ent.get('claims',{}).get('P1082',[]) if s.get('rank')!='deprecated']
        c02=[x for x in parsed if x['year_precision9']==2002]
        c10=[x for x in parsed if x['year_precision9']==2010]
        rows=pmap.get_group(qid).to_dict('records') if isinstance(pmap,pd.core.groupby.generic.DataFrameGroupBy) and qid in pmap.groups else []
        if len(c02)!=1 or len(c10)!=1 or c02[0]['amount_int'] is None or c10[0]['amount_int'] is None:
            final.append({'wikidata_qid':qid,'statement_status':'missing_multivalued_or_noninteger_year_claim','matching_source_pair_count':0,'candidate_only':True,'identity_admitted':False,'population_admitted':False}); continue
        matches=[]
        for r in rows:
            d02=int(c02[0]['amount_int'])-int(r['old_2002_population']); d10=int(c10[0]['amount_int'])-int(r['old_2010_population'])
            exact=d02==0 and d10==0
            protected=d02==0 and abs(d10)<=10 and bool(r['old_2010_confidentiality_perturbed'])
            if exact or protected: matches.append((r,exact,d02,d10))
        if len(matches)==1:
            r,exact,d02,d10=matches[0]
            # Recheck fetched raw entity identity anchors; these remain one
            # Wikidata evidence family and candidate-only.
            label=ent.get('labels',{}).get('ru',{}).get('value','')
            p764=[]
            for s in ent.get('claims',{}).get('P764',[]):
                try:
                    if s.get('rank')!='deprecated': p764.append(str(s['mainsnak']['datavalue']['value']))
                except Exception: pass
            currentrow=next((z for z in request.to_dict('records') if str(z['wikidata_qid'])==qid),{})
            p764_exact=any(digits(x)==digits(currentrow.get('current_native_oktmo_digits')) for x in p764)
            raw_p31=[]
            for s in ent.get('claims',{}).get('P31',[]):
                try:
                    if s.get('rank')!='deprecated': raw_p31.append(str(s['mainsnak']['datavalue']['value']['id']))
                except Exception: pass
            raw_physical=any(profiles.get(x,{}).get('physical_settlement_lineage') for x in raw_p31)
            e_sha=next((x['raw_entity_sha256'] for x in metadata_rows if x['wikidata_qid']==qid),'')
            final.append({'wikidata_qid':qid,'current_source_record_id':r['current_source_record_id'],'old_2002_source_record_id':r['old_2002_source_record_id'],'old_2010_source_record_id':r['old_2010_source_record_id'],'p1082_2002_population':int(c02[0]['amount_int']),'p1082_2010_population':int(c10[0]['amount_int']),'old_2002_source_population':int(r['old_2002_population']),'old_2010_source_population':int(r['old_2010_population']),'population_signature_kind':'exact_both_years' if exact else 'exact_2002_protected_2010_within_10','p1082_2002_delta':d02,'p1082_2010_delta':d10,'matching_source_pair_count':len(matches),'current_to_2002_uf_outcome':r['current_to_2002_uf_outcome'],'current_to_2010_uf_outcome':r['current_to_2010_uf_outcome'],'event_exact_native_code_guard':bool(r['any_event_exact_native_code_guard']),'fetched_ru_label_exact':norm(label)==norm(r['current_name_raw']),'fetched_current_P764_exact':p764_exact,'fetched_current_physical_P31_lineage':raw_physical,'fetched_current_P31_qids_json':json.dumps(raw_p31),'raw_entity_sha256':e_sha,'candidate_only':True,'identity_admitted':False,'population_admitted':False})
        else:
            final.append({'wikidata_qid':qid,'statement_status':'no_match_or_multiple_old_source_pairs','matching_source_pair_count':len(matches),'candidate_only':True,'identity_admitted':False,'population_admitted':False})
    finaldf=pd.DataFrame(final)
    if len(finaldf):
        exact_match=finaldf[finaldf.matching_source_pair_count.eq(1)&finaldf.old_2002_source_record_id.notna()]
        paircomp=exact_match.groupby(['old_2002_source_record_id','old_2010_source_record_id']).wikidata_qid.transform('nunique')
        finaldf.loc[exact_match.index,'current_qid_competition_for_old_pair']=paircomp.to_numpy()
        finaldf['current_qid_competition_for_old_pair']=pd.to_numeric(finaldf.current_qid_competition_for_old_pair,errors='coerce').fillna(0).astype(int)
        finaldf['signature_candidate_eligible']=finaldf.matching_source_pair_count.eq(1)&finaldf.fetched_ru_label_exact.fillna(False)&finaldf.fetched_current_P764_exact.fillna(False)&finaldf.fetched_current_physical_P31_lineage.fillna(False)&~finaldf.event_exact_native_code_guard.fillna(True)&~finaldf.current_to_2002_uf_outcome.eq('year_constrained_collision')&~finaldf.current_to_2010_uf_outcome.eq('year_constrained_collision')&finaldf.current_qid_competition_for_old_pair.eq(1)
        finaldf['signature_candidate_hold_reason']=np.select([finaldf.current_qid_competition_for_old_pair.gt(1),finaldf.event_exact_native_code_guard.fillna(False),finaldf.current_to_2002_uf_outcome.eq('year_constrained_collision')|finaldf.current_to_2010_uf_outcome.eq('year_constrained_collision'),~finaldf.fetched_current_physical_P31_lineage.fillna(False),~finaldf.fetched_current_P764_exact.fillna(False),~finaldf.fetched_ru_label_exact.fillna(False)],['same_old_pair_has_competing_current_QIDs','exact_native_event_code_guard','year_constrained_collision','raw_fetched_P31_not_physical','raw_fetched_P764_not_exact','raw_fetched_Russian_label_not_exact'],default='')
    finaldf.to_csv(OUT/'all_fetched_qid_two_year_signature_results.csv',index=False)
    # Candidate temporal edge packet plus exact-source anchors for independent review.
    review_edges=[]
    for r in finaldf[finaldf.matching_source_pair_count.eq(1)&finaldf.fetched_ru_label_exact.fillna(False)&finaldf.fetched_current_P764_exact.fillna(False)&finaldf.fetched_current_physical_P31_lineage.fillna(False)].to_dict('records') if len(finaldf) else []:
        for year,oldid in [(2002,r['old_2002_source_record_id']),(2010,r['old_2010_source_record_id'])]:
            outcome=r.get('current_to_2002_uf_outcome') if year==2002 else r.get('current_to_2010_uf_outcome')
            review_edges.append({'wikidata_qid':r['wikidata_qid'],'from_source_record_id':oldid,'from_year':year,'to_source_record_id':r['current_source_record_id'],'to_year':2021,'relation':'same_place','candidate_rule':'exact_current_P764_physical_type_region_plus_unique_two_year_P1082_source_population_signature','p1082_2002_population':r['p1082_2002_population'],'p1082_2010_population':r['p1082_2010_population'],'old_source_2002_population':r['old_2002_source_population'],'old_source_2010_population':r['old_2010_source_population'],'conditional_baseline_uf_outcome':outcome,'event_exact_native_code_guard':r['event_exact_native_code_guard'],'signature_candidate_eligible':r['signature_candidate_eligible'],'signature_candidate_hold_reason':r['signature_candidate_hold_reason'],'candidate_only':True,'identity_admitted':False,'population_admitted':False})
    pd.DataFrame(review_edges).to_csv(OUT/'independent_review_candidate_temporal_edges.csv',index=False)
    stats={'status':'candidate_only_no_identity_population_or_point_admissions','fetch_qid_count':len(qids),'raw_batch_count':len(batch_meta),'total_elapsed_seconds':round(time.monotonic()-fetch_starts,2),'candidate_signature_rows':int(finaldf.matching_source_pair_count.eq(1).sum()) if len(finaldf) else 0,'candidate_temporal_edges':len(review_edges),'screen_manifest':manifest,'baseline_sixth_graph_sha256':sha(G),'baseline_sixth_points_sha256':sha(P),'raw_batch_manifest_sha256':sha(OUT/'raw_batch_manifest.json'),'raw_response_hashes':{r['raw_file']:r['raw_response_sha256'] for r in batch_meta}}
    (OUT/'final_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
    receipt={'status':stats['status'],'script_sha256':sha(Path(__file__)),'screen_manifest_sha256':sha(OUT/'screen_manifest.json'),'summary_sha256':sha(OUT/'final_summary.json'),'outputs':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}}
    (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in stats.items() if k!='screen_manifest'},ensure_ascii=False,indent=2))

def entities_for(qids,rawdir):
    qset=set(map(str,qids)); out=[]
    for path in sorted(Path(rawdir).glob('raw_entity_batch_*.json')):
        data=json.loads(path.read_text(encoding='utf-8')).get('entities',{})
        out.extend((str(q),e) for q,e in data.items() if str(q) in qset)
    return out

if __name__=='__main__': main()

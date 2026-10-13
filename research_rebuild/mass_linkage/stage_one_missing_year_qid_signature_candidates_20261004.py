#!/usr/bin/env python3
"""Candidate-only one-missing-year recovery using frozen raw entities."""
from pathlib import Path
import hashlib, json, re
import numpy as np
import pandas as pd
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import (
    OUT, SEL, G, P, COV, sha, pop_int, truth, utc
)
from research_rebuild.mass_linkage.stage_wide_qid_homonym_fetch_candidates_20261004 import norm, typ
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.coordinate_validation_packet import wikidata_type_lineage
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES, ACCEPTED_COORDINATE_STATUSES

EXP=OUT/'expanded_fetch'
PK=EXP/'final_candidate_packet_delta_post2000_5000'
OUTPK=EXP/'one_missing_year_population_signature_candidates_v8'
P31_META=Path('/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json')
YEARS=(2002,2010)

def hbytes(b):return hashlib.sha256(b).hexdigest()
def year_claims(claim_df):
    result={}
    for r in claim_df.itertuples(index=False):
        try: s=json.loads(r.claim_json)
        except Exception: continue
        if s.get('rank')=='deprecated': continue
        q=s.get('qualifiers',{}).get('P585',[])
        if len(q)!=1: continue
        try:
            dv=q[0]['datavalue']['value']; precision=int(dv.get('precision',0)); date=dv['time']
            m=re.match(r'^[+-](\d{4})-00-00T',date)
            if not m or precision!=9: continue
            y=int(m.group(1)); value=s['mainsnak']['datavalue']['value']; amount=str(value['amount'])
            pop=float(amount.lstrip('+'))
            if not np.isfinite(pop) or pop<0 or not pop.is_integer(): continue
            result.setdefault((str(r.wikidata_qid),y),[]).append({'population':int(pop),'statement_id':s.get('id'),'rank':s.get('rank'),'claim_json':r.claim_json})
        except Exception: continue
    return result

def main():
    if OUTPK.exists(): raise RuntimeError(f'refusing to overwrite {OUTPK}')
    OUTPK.mkdir(parents=True)
    screen=pd.read_csv(PK/'new_5000_signature_screen.csv',dtype={'wikidata_qid':str},low_memory=False)
    pairs=pd.read_csv(PK/'all_old_source_pair_alternatives.csv',dtype={'wikidata_qid':str,'current_source_record_id':str,'old_2002_source_record_id':str,'old_2010_source_record_id':str},low_memory=False)
    src=pd.read_csv(PK/'literal_selected_source_context.csv',dtype={'source_record_id':str},low_memory=False)
    entities=pd.read_csv(PK/'raw_entity_claim_index.csv',dtype={'wikidata_qid':str},low_memory=False)
    claims=pd.read_csv(PK/'raw_P1082_statements.csv',dtype={'wikidata_qid':str},low_memory=False)
    qclaims=year_claims(claims)
    # Index exact literal selected source rows and all old pair alternatives by QID.
    src['source_record_id']=src.source_record_id.astype(str)
    srcby={str(k):v.to_dict() for k,v in src.drop_duplicates('source_record_id').set_index('source_record_id').iterrows()}
    # Build whole-selected-source old-year competitor lookup, not just source
    # rows that happened to have a cross-year pair in the fetch index.
    allcols=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','population','population_scope','is_additive_settlement_record','population_value_quality','source_path','source_sha256','source_locator','source_native_id','source_population_raw']
    fullsrc=pd.read_parquet(SEL,columns=allcols)
    fullsrc=fullsrc[fullsrc.census_year.isin([2002,2010])].copy()
    fullsrc['source_record_id']=fullsrc.source_record_id.astype(str)
    fullsrc['pop_int']=fullsrc.population.map(pop_int)
    old_lookup={}
    for rr in fullsrc.itertuples(index=False):
        key=(int(rr.census_year),region_key(rr.region_raw),norm(rr.settlement_name),typ(rr.settlement_type))
        old_lookup.setdefault(key,[]).append(rr._asdict())
    profiles=wikidata_type_lineage(json.loads(P31_META.read_text(encoding='utf-8')))
    eidx={str(r.wikidata_qid):r._asdict() for r in entities.itertuples(index=False)}
    candidates=[]; holds=[]; competitor_evidence=[]
    # Process each source QID as an independent evidence bundle.
    for qid,g in pairs.groupby('wikidata_qid',sort=False):
        qid=str(qid)
        if qid not in eidx: continue
        current_ids=set(g.current_source_record_id.dropna().astype(str))
        if len(current_ids)!=1: continue
        curid=next(iter(current_ids)); cur=srcby.get(curid)
        if not cur: continue
        en=eidx[qid]
        try: label=json.loads(en.get('P31_claims_json','[]'))
        except Exception: label=[]
        rawlabel=str(en.get('raw_label_ru') or '')
        if norm(rawlabel)!=norm(cur.get('settlement_name')): continue
        native_digits=re.sub(r'\D','',str(cur.get('source_native_id') or ''))
        p764=[]
        try:
            for s in json.loads(en.get('P764_claims_json','[]')):
                if s.get('rank')=='deprecated': continue
                p764.append(re.sub(r'\D','',str(s.get('mainsnak',{}).get('datavalue',{}).get('value',''))))
        except Exception: pass
        if not native_digits or native_digits not in p764: continue
        p31=[]
        try:
            for s in json.loads(en.get('P31_claims_json','[]')):
                if s.get('rank')=='deprecated': continue
                p31.append(str(s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id','')))
        except Exception: pass
        if not any(profiles.get(x,{}).get('physical_settlement_lineage') for x in p31): continue
        # Reject protected admin/collision conditions for every pair row; the
        # candidate cannot be rescued by a different cross-product alternative.
        if g.any_event_exact_native_code_guard.map(truth).any(): continue
        # Current current-source observation must already be accepted as a point.
        # Candidate pool construction guarantees the accepted current native-point
        # route; the actual accepted-point membership is also checked below.
        for y,other in ((2002,2010),(2010,2002)):
            other_out=g[f'current_to_{other}_uf_outcome'].astype(str)
            miss_out=g[f'current_to_{y}_uf_outcome'].astype(str)
            if not other_out.eq('already_connected').any(): continue
            # Only old rows with exact current-vs-old normalized name/type/region
            # form the full set of source competitors for the missing year.
            oldcol=f'old_{y}_source_record_id'; popcol=f'old_{y}_population'; qcol=f'old_{y}_confidentiality_perturbed'
            competitors={}
            ckey=(y,region_key(cur.get('region_raw')),norm(cur.get('settlement_name')),typ(cur.get('settlement_type')))
            for o in old_lookup.get(ckey,[]):
                quality=str(o.get('population_value_quality',''))
                oid=str(o.get('source_record_id'))
                pv=pop_int(o.get('population'))
                perturbed=(quality=='secondary_confidentiality_protected_value_exact_scope_unverified')
                source_scope=str(o.get('population_scope') or '')
                target_eligible=bool(truth(o.get('is_additive_settlement_record')) and source_scope in {'settlement','settlement_population_2010_census_date'} and ((y==2002 and quality=='direct_published_census_value') or (y==2010 and quality in {'direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'})))
                competitors[oid]={'source':o,'population':pv,'quality':quality,'perturbed':perturbed,'target_eligible':target_eligible}
            if not competitors: continue
            statements=qclaims.get((qid,y),[])
            if len(statements)!=1:
                holds.append({'wikidata_qid':qid,'current_source_record_id':curid,'missing_year':y,'hold_reason':'missing_or_multivalued_exact_year_P1082','exact_name_type_region_competitor_count':len(competitors),'p1082_statement_count':len(statements)})
                continue
            claim=statements[0]
            matches=[]
            for oid,x in competitors.items():
                delta=(claim['population']-x['population']) if x['population'] is not None else None
                exact=delta==0
                protected=delta is not None and y==2010 and x['quality']=='secondary_confidentiality_protected_value_exact_scope_unverified' and x['perturbed'] and abs(delta)<=10
                competitor_evidence.append({'wikidata_qid':qid,'current_source_record_id':curid,'missing_year':y,'historical_competitor_source_record_id':oid,'competitor_name_raw':x['source'].get('source_name_raw'),'competitor_settlement_name':x['source'].get('settlement_name'),'competitor_type_raw':x['source'].get('settlement_type'),'competitor_region_raw':x['source'].get('region_raw'),'competitor_district_raw':x['source'].get('district_raw'),'competitor_population':x['population'],'competitor_population_quality':x['quality'],'competitor_population_scope':x['source'].get('population_scope'),'competitor_is_additive':x['source'].get('is_additive_settlement_record'),'candidate_target_population_eligible':x['target_eligible'],'competitor_matches_P1082':bool(exact or protected),'match_kind':'exact' if exact else ('protected_within_10' if protected else ''),'population_delta':delta,'source_file':x['source'].get('source_file'),'source_sheet':x['source'].get('source_sheet'),'source_row':x['source'].get('source_row'),'source_sha256':x['source'].get('source_sha256'),'source_locator':x['source'].get('source_locator'),'source_record_id':oid})
                if delta is None: continue
                if exact or protected:
                    matches.append((oid,x,delta,exact,protected))
            unknown_population_competitors=sum(x['population'] is None for x in competitors.values())
            if unknown_population_competitors:
                holds.append({'wikidata_qid':qid,'current_source_record_id':curid,'missing_year':y,'hold_reason':'same_key_competitor_missing_population','exact_name_type_region_competitor_count':len(competitors),'unknown_population_competitor_count':unknown_population_competitors,'p1082_statement_count':len(statements)})
                continue
            if len(matches)!=1:
                if matches: reason='multiple_exact_or_protected_population_matches'
                else: reason='no_population_match_among_exact_name_type_region_competitors'
                holds.append({'wikidata_qid':qid,'current_source_record_id':curid,'missing_year':y,'hold_reason':reason,'exact_name_type_region_competitor_count':len(competitors),'p1082_statement_count':len(statements),'population_match_count':len(matches)})
                continue
            oid,x,delta,exact,protected=matches[0]
            if not x['target_eligible']:
                holds.append({'wikidata_qid':qid,'current_source_record_id':curid,'missing_year':y,'hold_reason':'unique_population_match_not_admissible_source_grain_or_scope','exact_name_type_region_competitor_count':len(competitors),'population_match_count':1})
                continue
            candidate_pair_rows=g[g[oldcol].astype(str).eq(oid)]
            missing_outcome=(str(candidate_pair_rows.iloc[0][f'current_to_{y}_uf_outcome']) if not candidate_pair_rows.empty else 'not_in_two_year_pair_index')
            if str(x['source'].get('source_name_raw'))=='': continue
            # The same old record cannot be independently assigned from multiple
            # current QIDs. This cross-QID check runs after candidate creation.
            candidates.append({'wikidata_qid':qid,'current_source_record_id':curid,'historical_source_record_id':oid,'missing_year':y,'accepted_other_historical_year':other,'current_population':pop_int(cur.get('population')),'publisher_historical_population':x['population'],'raw_P1082_population':claim['population'],'population_delta':delta,'population_match_kind':'exact' if exact else 'protected_2010_within_10','population_quality':x['quality'],'source_confidentiality_perturbed':x['perturbed'],'exact_name_type_region_competitor_count':len(competitors),'matching_competitor_count':len(matches),'other_year_UF_outcome':'already_connected','missing_year_UF_outcome':missing_outcome,'current_name_raw':cur.get('source_name_raw'),'current_type_raw':cur.get('settlement_type'),'current_region_raw':cur.get('region_raw'),'current_district_raw':cur.get('district_raw'),'old_name_raw':x['source'].get('source_name_raw'),'old_type_raw':x['source'].get('settlement_type'),'old_region_raw':x['source'].get('region_raw'),'old_district_raw':x['source'].get('district_raw'),'historical_source_file':x['source'].get('source_file'),'historical_source_sheet':x['source'].get('source_sheet'),'historical_source_row':x['source'].get('source_row'),'current_source_sha256':cur.get('source_sha256'),'current_source_locator':cur.get('source_locator'),'historical_source_sha256':x['source'].get('source_sha256'),'historical_source_locator':x['source'].get('source_locator'),'native_current_code_literal':cur.get('source_native_id'),'raw_P1082_statement_id':claim['statement_id'],'raw_P1082_statement_json':claim['claim_json'],'current_raw_entity_sha256':en.get('raw_entity_sha256'),'candidate_only':True,'identity_admitted':False,'population_admitted':False,'point_admitted':False})
    cand=pd.DataFrame(candidates)
    if len(cand):
        cand['qid_count_for_historical_source'] = cand.groupby(['missing_year','historical_source_record_id']).wikidata_qid.transform('nunique')
        cand['candidate_rule_pass'] = cand.qid_count_for_historical_source.eq(1)
    else:
        cand['qid_count_for_historical_source']=pd.Series(dtype=int);cand['candidate_rule_pass']=pd.Series(dtype=bool)
    # Confirm the current targets have actual accepted coordinate uses.
    sel=pd.read_parquet(SEL,columns=['source_record_id','census_year','population','population_scope','is_additive_settlement_record','entity_grain_status','population_value_quality'])
    sel.source_record_id=sel.source_record_id.astype(str);sel.census_year=sel.census_year.astype(int);sel['pop_int']=sel.population.map(pop_int)
    graph=pd.read_parquet(G,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
    if not set(graph.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(graph.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES): raise RuntimeError('baseline graph has nonaccepted statuses')
    uf=YearUF(sel.source_record_id.tolist(),sel.census_year.tolist())
    for e in graph.itertuples(index=False):
        if e.relation!='same_place': raise RuntimeError('noncanonical baseline relation')
        if uf.union_ids(str(e.from_source_record_id),str(e.to_source_record_id))=='year_constrained_collision': raise RuntimeError('baseline graph collision')
    pts=pd.read_parquet(P,columns=['target_source_record_id','coordinate_admission_status'])
    point_ids=set(pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)].target_source_record_id.astype(str))
    if len(cand):
        cand['current_point_already_accepted']=cand.current_source_record_id.isin(point_ids)
        cand['candidate_rule_pass'] &= cand.current_point_already_accepted
        two=pd.read_csv(PK/'single_pair_current_binding_candidates.csv',dtype={'wikidata_qid':str,'old_2002_source_record_id':str,'old_2010_source_record_id':str},low_memory=False)
        two_edges=set()
        for r in two.itertuples(index=False):
            two_edges.add((str(r.wikidata_qid),str(r.old_2002_source_record_id)))
            two_edges.add((str(r.wikidata_qid),str(r.old_2010_source_record_id)))
        cand['overlaps_two_year_packet_edge']=[(str(r.wikidata_qid),str(r.historical_source_record_id)) in two_edges for r in cand.itertuples(index=False)]
        cand['one_missing_year_rule_pass']=cand.candidate_rule_pass
        cand['candidate_rule_pass'] &= ~cand.overlaps_two_year_packet_edge
    # Whole-year graph simulation on the sixth accepted baseline; new edges are
    # sequentially constrained and each eligible target must be unique.
    base=YearUF(sel.source_record_id.tolist(),sel.census_year.tolist())
    for e in graph.itertuples(index=False): base.union_ids(str(e.from_source_record_id),str(e.to_source_record_id))
    base_masks=base.bits_by_row(); base_root=np.fromiter((base.find(i) for i in range(len(sel))),dtype=np.int32,count=len(sel))
    base_point_roots={base.find(base.idx[x]) for x in point_ids if x in base.idx}
    before=np.array([(base_masks[i]==7 and base_root[i] in base_point_roots) for i in range(len(sel))],dtype=bool)
    uf2=YearUF(sel.source_record_id.tolist(),sel.census_year.tolist())
    for e in graph.itertuples(index=False): uf2.union_ids(str(e.from_source_record_id),str(e.to_source_record_id))
    elig=cand[cand.candidate_rule_pass].sort_values(['wikidata_qid','missing_year']) if len(cand) else cand
    edge_rows=[]
    for r in elig.to_dict('records'):
        status=uf2.union_ids(str(r['historical_source_record_id']),str(r['current_source_record_id']))
        edge_rows.append({'wikidata_qid':r['wikidata_qid'],'from_source_record_id':r['historical_source_record_id'],'from_year':r['missing_year'],'to_source_record_id':r['current_source_record_id'],'to_year':2021,'relation':'same_place','conditional_union_status':status,'candidate_only':True,'identity_admitted':False})
    if len(cand):
        edge_status={(x['wikidata_qid'],x['from_source_record_id']):x['conditional_union_status'] for x in edge_rows}
        cand['conditional_union_status']=[edge_status.get((str(r.wikidata_qid),str(r.historical_source_record_id)),'not_simulated') for r in cand.itertuples(index=False)]
        cand.loc[cand.conditional_union_status.eq('year_constrained_collision'),'candidate_rule_pass']=False
    aftmask=uf2.bits_by_row();after_point_roots={uf2.find(uf2.idx[x]) for x in point_ids if x in uf2.idx}
    ids=sel.source_record_id.to_numpy(); years=sel.census_year.to_numpy(); pops=sel.pop_int.to_numpy();scope=sel.population_scope.fillna('').astype(str).str.casefold().eq('settlement').to_numpy()&sel.is_additive_settlement_record.fillna(False).to_numpy()&np.isfinite(pd.to_numeric(sel.pop_int,errors='coerce').to_numpy(dtype=float))
    after=np.array([(aftmask[i]==7 and uf2.find(i) in after_point_roots) for i in range(len(sel))],dtype=bool)&scope
    before &= scope
    gain=after&~before
    gainrows=[]
    for y in [2002,2010,2021]:
        m=gain&(years==y)
        gainrows.append({'year':y,'conditional_new_full_chain_joint_point_rows':int(m.sum()),'conditional_new_full_chain_joint_point_population':int(np.nansum(pops[m]))})
    cand.to_csv(OUTPK/'one_missing_year_candidates.csv',index=False)
    pd.DataFrame(holds).to_csv(OUTPK/'one_missing_year_holds.csv',index=False)
    pd.DataFrame(competitor_evidence).to_csv(OUTPK/'all_exact_name_type_region_source_competitors.csv',index=False)
    pd.DataFrame(edge_rows).to_csv(OUTPK/'conditional_candidate_edges.csv',index=False)
    summary={'status':'candidate_only_independent_review_required_no_admissions','created_utc':utc(),'seed':20261004,'input_packet_receipt_sha256':sha(PK/'receipt.json'),'candidate_source_rows':len(pairs),'candidate_qids_screened':int(pairs.wikidata_qid.nunique()),'candidate_rows_before_UF_collision_and_currentpoint_gates':len(cand),'one_missing_year_rows_before_two_year_packet_overlap_dedup':int(cand.one_missing_year_rule_pass.sum()) if len(cand) else 0,'overlapping_edges_already_in_two_year_candidate_packet':int(cand.overlaps_two_year_packet_edge.sum()) if len(cand) else 0,'incremental_rows_after_two_year_packet_overlap_dedup':int(cand.candidate_rule_pass.sum()) if len(cand) else 0,'incremental_unique_qids_after_overlap_dedup':int(cand.loc[cand.candidate_rule_pass,'wikidata_qid'].nunique()) if len(cand) else 0,'full_source_competitor_rows':len(competitor_evidence),'hold_reason_counts':pd.DataFrame(holds).hold_reason.value_counts(dropna=False).to_dict() if holds else {},'incremental_missing_year_counts':cand[cand.candidate_rule_pass].missing_year.value_counts().to_dict() if len(cand) else {},'incremental_source_quality_counts':cand[cand.candidate_rule_pass].population_quality.value_counts().to_dict() if len(cand) else {},'conditional_edge_status_counts':pd.DataFrame(edge_rows).conditional_union_status.value_counts().to_dict() if edge_rows else {},'conditional_incremental_full_chain_joint_point_gain_by_year':gainrows,'baseline_graph_sha256':sha(G),'baseline_points_sha256':sha(P),'selected_observations_sha256':sha(SEL),'input_pins':{'raw_P1082_statements_sha256':sha(PK/'raw_P1082_statements.csv'),'source_alternatives_sha256':sha(PK/'all_old_source_pair_alternatives.csv'),'selected_source_context_sha256':sha(PK/'literal_selected_source_context.csv'),'raw_entities_sha256':sha(PK/'raw_entity_claim_index.csv')},'admission_flags':{'identity':False,'population':False,'point':False},'limits':['P1082 is secondary corroboration; publication source counts remain authoritative.','All old-source alternatives with exact normalized name/type/province are retained, including rows with missing population or out-of-scope grain; unknown-population alternatives hold a candidate.','Protected 2010 ±10 is retained as protected and requires independent review.','Candidates duplicating an edge in the simultaneous two-year packet are preserved but excluded from incremental gains.','All margins are conditional on the pinned sixth accepted baseline, not on any subsequently promoted graph.']}
    (OUTPK/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    rec={'status':summary['status'],'script_sha256':sha(Path(__file__)),'outputs':{p.name:sha(p) for p in sorted(OUTPK.iterdir()) if p.is_file()}}
    (OUTPK/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

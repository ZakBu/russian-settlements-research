#!/usr/bin/env python3
"""Measure conditional three-year gain from the frozen post-2k QID packet."""
from pathlib import Path
import json,pandas as pd
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import OUT,SEL,G,P,COV,sha,utc,truth
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.coverage import identity_sets
from research_rebuild.mass_linkage.measure_qid_signature_conditional_coverage_20261004 import point_propagation,measure_axes

EXP=OUT/'expanded_fetch'
PK=EXP/'final_candidate_packet_delta_post2000_5000'
SUP=EXP/'conditional_coverage_delta_post2000_5000_v3'
ACCEPTED_POINTS={'reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted'}

def main():
    SUP.mkdir(exist_ok=False)
    selected=pd.read_parquet(SEL,columns=['source_record_id','census_year','population','population_scope','population_value_quality','settlement_id'])
    selected.source_record_id=selected.source_record_id.astype(str);selected.census_year=selected.census_year.astype(int)
    points=pd.read_parquet(P,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','review_id'])
    points=points[points.coordinate_admission_status.isin(ACCEPTED_POINTS)].copy();points.target_source_record_id=points.target_source_record_id.astype(str)
    base=pd.read_parquet(G,columns=['from_source_record_id','to_source_record_id'])
    b_link,b_full,b_comp=identity_sets(selected[['source_record_id','census_year']],base)
    controls={int(x['year']):int(x['official_control']) for x in json.loads(COV.read_text())['census_metrics']}
    direct=set(points.target_source_record_id.astype(str));bm=measure_axes(selected,b_link,b_full,direct,direct,controls)
    cand=pd.read_csv(PK/'single_pair_current_binding_candidates.csv',dtype={'wikidata_qid':str,'current_source_record_id':str,'old_2002_source_record_id':str,'old_2010_source_record_id':str},low_memory=False)
    cand['source_population_quality_reviewable']=cand.old_2002_population_quality.astype(str).eq('direct_published_census_value')&cand.old_2010_population_quality.astype(str).isin(['direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'])
    cand['candidate_identity_rule_pass']=cand.candidate_identity_rule_pass.map(truth)
    cand=cand[cand.candidate_identity_rule_pass].copy()
    out=[]
    for label,cd in [('all_single_pair_candidates',cand),('source_quality_reviewable',cand[cand.source_population_quality_reviewable])]:
        uf=YearUF(selected.source_record_id.tolist(),selected.census_year.tolist())
        for a,b in base[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
            if uf.union_ids(str(a),str(b))=='year_constrained_collision':raise ValueError('baseline graph collision')
        edge_rows=[]
        collision_holds=0
        for r in cd.sort_values('wikidata_qid').to_dict('records'):
            specs=[(2002,r['old_2002_source_record_id']),(2010,r['old_2010_source_record_id'])]
            # Check both edges against the current conditional UF before adding
            # either, so a failed two-edge candidate cannot leave half a chain.
            checks=[]
            for year,oldid in specs:
                ia=uf.idx.get(str(oldid));ib=uf.idx.get(str(r['current_source_record_id']))
                if ia is None or ib is None:status='missing_vertex'
                else:
                    a,b=uf.find(ia),uf.find(ib)
                    status='already_connected' if a==b else ('year_constrained_collision' if uf.mask[a]&uf.mask[b] else 'merge_possible')
                checks.append(status)
            blocked='year_constrained_collision' in checks or 'missing_vertex' in checks
            if blocked: collision_holds+=1
            for (year,oldid),check in zip(specs,checks):
                status=check if blocked else (uf.union_ids(str(oldid),str(r['current_source_record_id'])) if check=='merge_possible' else check)
                edge_rows.append({'wikidata_qid':r['wikidata_qid'],'from_source_record_id':oldid,'from_year':year,'to_source_record_id':r['current_source_record_id'],'to_year':2021,'relation':'same_place','conditional_union_status':status,'pair_candidate_held_atomically':blocked})
        fresh=[e for e in edge_rows if e['conditional_union_status']=='merged']
        add=pd.DataFrame(fresh)[['from_source_record_id','to_source_record_id']] if fresh else pd.DataFrame(columns=['from_source_record_id','to_source_record_id'])
        union=pd.concat([base,add],ignore_index=True)
        linked,full,comps=identity_sets(selected[['source_record_id','census_year']],union)
        affected={str(e[k]) for e in fresh for k in ('from_source_record_id','to_source_record_id')}
        dr,prop,spread=point_propagation(comps,points,affected_targets=affected)
        metrics=measure_axes(selected,linked,full,dr,prop,controls)
        out.append({'scenario':label,'candidate_qids':int(cd.wikidata_qid.nunique()),'collision_or_missing_vertex_pair_holds':collision_holds,'new_year_uf_edges':len(fresh),'baseline_linked_vertices':len(b_link),'after_linked_vertices':len(linked),'baseline_full_chain_vertices':len(b_full),'after_full_chain_vertices':len(full),'candidate_affected_components':len(spread),'components_spread_le_5km':sum(bool(x['spread_le_5km']) for x in spread),'components_held_over_5km':sum(not bool(x['spread_le_5km']) for x in spread),'baseline_direct_point_targets':len(direct),'after_propagated_point_targets':len(prop),'baseline_metrics':bm,'conditional_metrics':metrics})
        pd.DataFrame(edge_rows).to_csv(SUP/f'{label}_conditional_edges.csv',index=False)
        pd.DataFrame(spread).to_csv(SUP/f'{label}_point_spread.csv',index=False)
    result={'status':'candidate_only_conditional_coverage_no_admissions','created_utc':utc(),'baseline_graph_sha256':sha(G),'baseline_points_sha256':sha(P),'source_pair_index_sha256':sha(EXP/'source_pair_signature_eval_index.parquet'),'candidate_packet_receipt_sha256':sha(PK/'receipt.json'),'official_baseline_reproduced':{str(y):{'full_chain_joint_direct':bm[y]['joint_point_and_all_three_censuses_direct_only']} for y in sorted(bm)},'scenarios':out,'limits':['All edges remain unreviewed candidate edges.','Point spreading uses the deterministic latest-2021 accepted point carrier; components whose accepted point seeds are >5 km apart are held.','Wikidata population statements are secondary corroboration, not replacements for publisher counts.','Conditional gains use the sixth accepted graph snapshot and are not the current marginal impact if later graph versions have been promoted.']}
    (SUP/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    receipt={'status':result['status'],'script_sha256':sha(Path(__file__)),'candidate_packet_receipt_sha256':sha(PK/'receipt.json'),'summary_sha256':sha(SUP/'summary.json'),'outputs':{p.name:sha(p) for p in sorted(SUP.iterdir()) if p.is_file()}}
    (SUP/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['official_baseline_reproduced'],ensure_ascii=False,indent=2))
    for s in out:
        print(s['scenario'],s['candidate_qids'],s['new_year_uf_edges'],s['components_spread_le_5km'],s['components_held_over_5km'])
        for y,m in s['conditional_metrics'].items():print(y,m['joint_point_and_all_three_censuses_with_component_propagation'])

if __name__=='__main__':main()

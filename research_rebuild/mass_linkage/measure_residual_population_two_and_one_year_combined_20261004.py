#!/usr/bin/env python3
"""Conditional joint coverage for post-2k two-year plus one-year packets."""
from pathlib import Path
import json,pandas as pd
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import OUT,SEL,G,P,COV,sha,utc,truth
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.coverage import identity_sets
from research_rebuild.mass_linkage.measure_qid_signature_conditional_coverage_20261004 import point_propagation,measure_axes

EXP=OUT/'expanded_fetch';PK=EXP/'final_candidate_packet_delta_post2000_5000'
ONE=EXP/'one_missing_year_population_signature_candidates_v8'
P=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_sixth_point_corrected/accepted_point_uses.parquet')
SUP=EXP/'conditional_coverage_post2k_plus_one_missingyear_v3_corrected_points'
ACCEPTED_POINTS={'reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted'}

def main():
    SUP.mkdir(exist_ok=False)
    s=pd.read_parquet(SEL,columns=['source_record_id','census_year','population','population_scope','population_value_quality','settlement_id'])
    s.source_record_id=s.source_record_id.astype(str);s.census_year=s.census_year.astype(int)
    points=pd.read_parquet(P,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','review_id'])
    points=points[points.coordinate_admission_status.isin(ACCEPTED_POINTS)].copy();points.target_source_record_id=points.target_source_record_id.astype(str)
    base=pd.read_parquet(G,columns=['from_source_record_id','to_source_record_id'])
    link0,full0,comps0=identity_sets(s[['source_record_id','census_year']],base)
    controls={int(x['year']):int(x['official_control']) for x in json.loads(COV.read_text())['census_metrics']}
    direct=set(points.target_source_record_id.astype(str));metrics0=measure_axes(s,link0,full0,direct,direct,controls)
    two=pd.read_csv(PK/'single_pair_current_binding_candidates.csv',dtype={'wikidata_qid':str,'current_source_record_id':str,'old_2002_source_record_id':str,'old_2010_source_record_id':str},low_memory=False)
    two['quality_ok']=two.old_2002_population_quality.astype(str).eq('direct_published_census_value')&two.old_2010_population_quality.astype(str).isin(['direct_published_census_value','secondary_confidentiality_protected_value_exact_scope_unverified'])
    two=two[two.quality_ok].copy()
    one=pd.read_csv(ONE/'one_missing_year_candidates.csv',dtype={'wikidata_qid':str,'current_source_record_id':str,'historical_source_record_id':str},low_memory=False)
    one=one[one.candidate_rule_pass].sort_values(['wikidata_qid','missing_year'])

    uf=YearUF(s.source_record_id.tolist(),s.census_year.tolist())
    for a,b in base[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
        if uf.union_ids(str(a),str(b))=='year_constrained_collision':raise ValueError('baseline collision')
    fresh_two=[];two_hold=0;edge_two=[]
    for r in two.sort_values('wikidata_qid').to_dict('records'):
        specs=[(2002,r['old_2002_source_record_id']),(2010,r['old_2010_source_record_id'])]
        checks=[]
        for y,oldid in specs:
            ia,ib=uf.idx.get(str(oldid)),uf.idx.get(str(r['current_source_record_id']))
            if ia is None or ib is None:st='missing_vertex'
            else:
                x,z=uf.find(ia),uf.find(ib)
                st='already_connected' if x==z else ('year_constrained_collision' if uf.mask[x]&uf.mask[z] else 'merge_possible')
            checks.append(st)
        blocked=any(x in {'missing_vertex','year_constrained_collision'} for x in checks)
        if blocked:two_hold+=1
        for (y,oldid),st in zip(specs,checks):
            if blocked: status=st
            elif st=='merge_possible':status=uf.union_ids(str(oldid),str(r['current_source_record_id']))
            else:status=st
            row={'wikidata_qid':r['wikidata_qid'],'from_source_record_id':oldid,'from_year':y,'to_source_record_id':r['current_source_record_id'],'to_year':2021,'relation':'same_place','conditional_union_status':status,'pair_held_atomically':blocked}
            edge_two.append(row)
            if status=='merged':fresh_two.append(row)
    g2=pd.concat([base,pd.DataFrame(fresh_two)[['from_source_record_id','to_source_record_id']]],ignore_index=True)
    link2,full2,comp2=identity_sets(s[['source_record_id','census_year']],g2)
    affected2={str(r[k]) for r in fresh_two for k in ('from_source_record_id','to_source_record_id')}
    dr2,prop2,spread2=point_propagation(comp2,points,affected_targets=affected2)
    metrics2=measure_axes(s,link2,full2,dr2,prop2,controls)
    fresh_one=[];one_hold=0;edge_one=[]
    for r in one.to_dict('records'):
        status=uf.union_ids(str(r['historical_source_record_id']),str(r['current_source_record_id']))
        edge={'wikidata_qid':r['wikidata_qid'],'from_source_record_id':r['historical_source_record_id'],'from_year':int(r['missing_year']),'to_source_record_id':r['current_source_record_id'],'to_year':2021,'relation':'same_place','conditional_union_status':status}
        edge_one.append(edge)
        if status=='merged':fresh_one.append(edge)
        elif status=='year_constrained_collision':one_hold+=1
    g3=pd.concat([g2,pd.DataFrame(fresh_one)[['from_source_record_id','to_source_record_id']]],ignore_index=True)
    link3,full3,comp3=identity_sets(s[['source_record_id','census_year']],g3)
    affected3=affected2|{str(r[k]) for r in fresh_one for k in ('from_source_record_id','to_source_record_id')}
    dr3,prop3,spread3=point_propagation(comp3,points,affected_targets=affected3)
    metrics3=measure_axes(s,link3,full3,dr3,prop3,controls)
    pd.DataFrame(edge_two).to_csv(SUP/'two_year_conditional_edges.csv',index=False)
    pd.DataFrame(edge_one).to_csv(SUP/'one_missing_year_incremental_edges.csv',index=False)
    pd.DataFrame(spread3).to_csv(SUP/'combined_affected_component_point_spread.csv',index=False)
    summary={'status':'candidate_only_conditional_coverage_no_admissions','created_utc':utc(),'seed':20261004,'baseline_graph_sha256':sha(G),'baseline_points_sha256':sha(P),'two_year_packet_receipt_sha256':sha(PK/'receipt.json'),'one_year_packet_receipt_sha256':sha(ONE/'receipt.json'),'baseline_metrics':metrics0,'after_two_year_reviewable_packet_metrics':metrics2,'after_two_year_plus_incremental_one_year_metrics':metrics3,'two_year_reviewable_qids':int(two.wikidata_qid.nunique()),'two_year_pairs_held_atomically':two_hold,'two_year_new_edges':len(fresh_two),'one_year_incremental_qids':int(one.wikidata_qid.nunique()),'one_year_new_edges_after_two_year_packet':len(fresh_one),'one_year_year_collision_holds_after_two_year_packet':one_hold,'combined_affected_components':len(spread3),'combined_components_within_5km':sum(bool(x['spread_le_5km']) for x in spread3),'combined_components_over_5km_held':sum(not bool(x['spread_le_5km']) for x in spread3),'admission_flags':{'identity':False,'population':False,'point':False},'limits':['Candidate-only scenario, not an accepted graph.','The 2-year source-quality screen excludes 2010 scope-unverified holds beyond the protected review class; the one-year supplemental candidates remain protected 2010 rows.','New two-edge candidates are applied atomically under year constraints; one-year edges are deduplicated against the 2-year candidate packet before this run.','Point propagation uses deterministic latest 2021 accepted carrier and holds components whose existing seeds are more than 5 km apart.']}
    (SUP/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    rec={'status':summary['status'],'script_sha256':sha(Path(__file__)),'summary_sha256':sha(SUP/'summary.json'),'outputs':{p.name:sha(p) for p in sorted(SUP.iterdir()) if p.is_file()}}
    (SUP/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
    for label,m in [('base',metrics0),('two_year',metrics2),('two_plus_one_year',metrics3)]:
        print(label)
        for y,v in m.items():print(y,v['joint_point_and_all_three_censuses_with_component_propagation'])
    print('counts',len(fresh_two),two_hold,len(fresh_one),one_hold,sum(bool(x['spread_le_5km']) for x in spread3),sum(not bool(x['spread_le_5km']) for x in spread3))

if __name__=='__main__':main()

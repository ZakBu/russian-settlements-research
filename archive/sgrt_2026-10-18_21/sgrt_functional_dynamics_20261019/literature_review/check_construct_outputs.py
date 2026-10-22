"""Independent semantic/readback checks on the actual integrated graph outputs."""
from pathlib import Path
import hashlib,json
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'model/results'
O=Path(__file__).parent
PANEL=ROOT.parent/'anchor_research_20261019/data/point_axis.parquet'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=pd.read_parquet(PANEL).set_index('id')
    g=pd.read_parquet(MODEL/'integrated_relations.parquet')
    n=pd.read_parquet(MODEL/'integrated_nodes.parquet')
    m=pd.read_parquet(MODEL/'documented_external_memberships.parquet')
    c=pd.read_parquet(MODEL/'fixed_source_catchment_demography.parquet')
    ov=pd.read_parquet(MODEL/'documented_overlap.parquet')
    checks=[]
    def check(name,value,detail=''):checks.append({'check':name,'pass':bool(value),'detail':detail})
    check('graph_rows_unique',g.edge_uid.is_unique)
    medical=ROOT/'medical/relations.csv'
    if medical.exists():
        mr=pd.read_csv(medical)
        actual_medical=g[g.observation_scope.eq('new_document_corpus')]
        check('medical_input_rows_explicitly_preserved',len(actual_medical)==len(mr),f'input={len(mr)};graph={len(actual_medical)};an adapter must not silently skip unfamiliar schema')
        excluded={'institutional_subdivision','scheduled_mobile_visit','physical_location','local_function_presence'}
        prohibited=actual_medical[actual_medical.relation_kind.isin(excluded)]
        check('organization_schedule_not_invented_service_catchment',not prohibited.counts_as_external_service_evidence.fillna(False).any())
    history=ROOT/'history/edges_by_year.csv'
    if history.exists():
        hh=pd.read_csv(history)
        check('paired_history_input_rows_explicitly_preserved',len(g[g.observation_scope.eq('paired_history_document_corpus')])==len(hh))
    check('nodes_stay_on_immutable_settlement_axis',n.id.is_unique and set(n.id)<=set(p.index))
    check('accepted_memberships_not_self_loops',m.origin_uid.ne(m.destination_uid).all())
    check('accepted_endpoints_exist',set(m.origin_uid)|set(m.destination_uid)<=set(p.index))
    check('no_full_sgrt_claim_from_presence',n.complete_sgrt_asserted.eq(False).all())
    check('graph_no_observed_flow_without_data',not g.actual_flow_observed.fillna(False).any())
    check('no_historical_function_presence_backcast',not c.service_historical_presence_asserted.fillna(False).any())
    check('no_forced_geometric_zone_columns',not any('nearest_center' in x or 'zone_id' in x for x in g.columns))
    expected=m.groupby('destination_uid').function_group.nunique()
    got=n.set_index('id').documented_external_function_diversity.reindex(expected.index)
    check('function_diversity_is_documented_relations_only',expected.eq(got).all())
    gt=pd.read_parquet(MODEL/'canonical_documented_external_memberships.parquet').rename(columns={'canonical_source_id':'group_source_id','canonical_evidence_date':'group_date','canonical_service_level':'group_level'})
    group_keys=['group_source_id','group_date','destination_uid','function_group','group_level']
    expected_groups=gt.groupby(group_keys)
    check('fixed_source_groups_complete',len(c)==len(expected_groups))
    checked_groups=0;checked_zeros=0
    for _,row in c.iterrows():
        key=(row.source_id,row.source_document_date,row.destination_uid,row.function_group,row.service_level)
        gg=expected_groups.get_group(key)
        ids=set(gg.origin_uid)
        check('fixed_external_origins_'+str(checked_groups),int(row.n_origins)==len(ids))
        for y in [2002,2010,2021]:
            v=p.loc[sorted(ids),f'population_{y}']
            e=v.sum(min_count=1);got=row[f'population_{y}']
            equal=(pd.isna(e) and pd.isna(got)) or np.isclose(e,got,rtol=0,atol=1e-9)
            check(f'population_{y}_group_{checked_groups}',equal)
            check(f'zero_count_{y}_group_{checked_groups}',row[f'n_zero_population_{y}']==v.eq(0).sum())
            check(f'missing_count_{y}_group_{checked_groups}',row[f'n_missing_population_{y}']==v.isna().sum())
            checked_zeros+=int(v.eq(0).sum())
        check('fixed_change_'+str(checked_groups),np.isclose(row.fixed_membership_change_2010_2021,row.population_2021-row.population_2010,rtol=0,atol=1e-9))
        checked_groups+=1
    if len(ov):
        check('overlap_not_forced_hierarchy',not ov.functional_hierarchy_asserted.any())
        check('overlap_not_forced_single_time',not ov.single_snapshot_asserted.any())
        for i,row in ov.iterrows():
            ka=(row.source_a,row.date_a,row.provider_a,row.function_a,row.service_level_a)
            kb=(row.source_b,row.date_b,row.provider_b,row.function_b,row.service_level_b)
            aa=set(expected_groups.get_group(ka).origin_uid);bb=set(expected_groups.get_group(kb).origin_uid)
            check(f'overlap{i}_dated_level_sets',len(aa&bb)==row.n_common_origins and set(row.common_origins.split('|'))==aa&bb)
            check(f'overlap{i}_jaccard',np.isclose(len(aa&bb)/len(aa|bb),row.jaccard,rtol=0,atol=1e-12))
            check(f'overlap{i}_subset_flags',(aa<=bb)==row.set_a_inside_b and (bb<=aa)==row.set_b_inside_a)
    check('registered_candidates_are_only_candidate_flag',n.loc[n.registered_multifunction_candidate_with_documented_external_function_2021].documented_external_function_diversity.ge(1).all())
    inputs=[MODEL/x for x in ['integrated_relations.parquet','integrated_nodes.parquet','documented_external_memberships.parquet','canonical_documented_external_memberships.parquet','fixed_source_catchment_demography.parquet','documented_overlap.parquet']]
    report={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','counts':{'relations':len(g),'nodes':len(n),'documented_providers':int(n.documented_external_function_diversity.gt(0).sum()),'multifunction_external_nodes':int(n.documented_external_function_diversity.ge(2).sum()),'registered_multifunction_candidates':int(n.registered_multifunction_candidate_with_documented_external_function_2021.sum()),'fixed_source_groups':checked_groups,'zero_observations_recounted':checked_zeros,'overlaps':len(ov)},'checks_total':len(checks),'checks_passed':sum(x['pass'] for x in checks),'checks':checks,'input_sha256':{str(x.relative_to(ROOT)):sha(x) for x in inputs},'panel_sha256':sha(PANEL),'code_sha256':sha(Path(__file__)),'scope':'independent graph/demography readback and construct audit; not validation of external source truth or national coverage'}
    (O/'ACTUAL_OUTPUT_AUDIT_V2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert report['status']=='PASS'
    print(json.dumps({k:report[k] for k in ['status','counts','checks_total','checks_passed']},ensure_ascii=False))

if __name__=='__main__':main()

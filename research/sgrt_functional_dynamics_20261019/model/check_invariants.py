#!/usr/bin/env python3
"""Read back substantive conservation and evidence-category invariants."""
from pathlib import Path
import json
import pandas as pd
from build_integrated_graph import canonical_membership_key

R=Path(__file__).resolve().parent.parent;O=R/'model/results'

def run():
    checks=[]
    def check(name,ok):checks.append({'name':name,'pass':bool(ok)})
    g=pd.read_parquet(O/'integrated_relations.parquet');n=pd.read_parquet(O/'integrated_nodes.parquet');obj=pd.read_parquet(O/'physical_object_assertions.parquet')
    old=pd.read_csv(R.parent/'anchor_research_20261019/model/documented_graph/service_edges_calculated.csv')
    b=g[g.observation_scope.eq('previous_accepted_document_corpus')].set_index('edge_id')
    check('every_original_assertion_retained',set(b.index)==set(old.edge_id))
    for c in ['origin_uid','destination_uid','geometry_status']:
        check('original_'+c+'_unchanged',b[c].fillna('').sort_index().equals(old.set_index('edge_id')[c].fillna('').sort_index()))
    check('quarantined_coordinate_not_removed_from_document_graph',g.geometry_status.eq('coordinate_conflict_quarantined').sum()==1)
    check('edge_assertion_ids_unique',g.edge_uid.is_unique)
    panel=pd.read_parquet(R.parent/'anchor_research_20261019/data/point_axis.parquet',columns=['id'])
    check('all_resolved_origin_uids_valid',set(g.origin_uid.dropna())<=set(panel.id))
    check('all_resolved_destination_uids_valid',set(g.destination_uid.dropna())<=set(panel.id))
    check('all_resolved_object_uids_valid',set(obj.settlement_uid.dropna())<=set(panel.id))
    check('nodes_unique',n.id.is_unique)
    check('no_automatic_complete_sgrt',not n.complete_sgrt_asserted.any())
    check('no_fabricated_actual_flow',not g.actual_flow_observed.any())
    ext=g[g.counts_as_external_service_evidence]
    check('external_origins_not_same_place',ext.origin_uid.notna().all() and ext.destination_uid.notna().all() and ext.origin_uid.ne(ext.destination_uid).all())
    check('organizational_and_scheduled_not_dependence',not g[g.relation_kind.isin(['institutional_subdivision','scheduled_mobile_visit'])].counts_as_external_service_evidence.any())
    med=R/'medical/relations.csv'
    if med.exists():
        x=pd.read_csv(med)
        check('every_medical_relation_represented',len(g[g.observation_scope.eq('new_document_corpus')])==len(x))
        check('medical_relation_kinds_preserved',g[g.observation_scope.eq('new_document_corpus')].relation_kind.value_counts().sort_index().equals(x.relation_kind.value_counts().sort_index()))
    hist=R/'history/edges_by_year.csv'
    if hist.exists():check('every_history_relation_represented',len(g[g.observation_scope.eq('paired_history_document_corpus')])==len(pd.read_csv(hist)))
    kona=R/'history/konakovo_edges_by_year.csv'
    if kona.exists():
        k=pd.read_csv(kona);kg=g[g.observation_scope.eq('paired_konakovo_document_corpus')]
        check('all_konakovo_paired_assertions_retained',len(k)==len(kg))
        check('konakovo_2026_not_left_out',len(kg[kg.year.eq(2026)])==42)
        old_tv=g[g.observation_scope.eq('previous_accepted_document_corpus')&g.source_id.eq('TV2021')&g.counts_as_external_service_evidence]
        new_tv=kg[kg.year.eq(2021)&kg.counts_as_external_service_evidence]
        check('konakovo_2021_identity_equivalent_to_old_extraction',set(old_tv.canonical_membership_id)==set(new_tv.canonical_membership_id))
        canonical=pd.read_parquet(O/'canonical_documented_external_memberships.parquet')
        check('canonical_memberships_unique',canonical.canonical_membership_id.is_unique)
        check('konakovo_2021_deduplicated',len(canonical[canonical.source_id.eq('TV2021')])==38)
    expected_objects=len(pd.read_csv(R.parent/'anchor_research_20261019/data/school_inventory_linked.csv'))
    for f in [R/'medical/objects.csv',R/'marketplaces/objects.csv']:
        if f.exists():expected_objects+=len(pd.read_csv(f))
    ba=R/'history/uchaly_school_provider_sites_2025.csv'
    if ba.exists():expected_objects+=pd.read_csv(ba).site_status.eq('physical_school_site_explicit').sum()
    check('every_physical_object_assertion_retained',len(obj)==expected_objects)
    provider=n[n.documented_external_function_diversity.gt(0)]
    check('legal_multifunction_candidate_requires_external_witness',n.loc[n.registered_multifunction_candidate_with_documented_external_function_2021,'documented_external_function_diversity'].ge(1).all())
    check('physical_multifunction_candidate_requires_two_local_groups',n.loc[n.multifunction_physical_candidate_with_external_witness,'physical_function_diversity_observed_corpus'].ge(2).all())
    changes=pd.read_parquet(O/'functional_change_evidence.parquet')
    check('only_documented_education_is_provider_change',set(changes.loc[changes.documented_provider_change,'function_group'])=={'education'})
    check('no_reported_legal_or_tariff_loss_is_proven_closure',not changes.physical_closure_proven.any())
    a=pd.read_parquet(O/'history_two_axis_accounting.parquet')
    check('two_axis_accounting_exact',a.accounting_residual.eq(0).all())
    check('membership_effect_conserved_across_providers',a.groupby(['from_document_year','to_document_year']).boundary_effect_at_new_population.sum().eq(0).all())
    demo=O/'centre_periphery_demography.parquet'
    if demo.exists():
        d=pd.read_parquet(demo)
        for y in [2002,2010,2021]:
            check(f'demographic_center_external_total_{y}',d[f'total_population_{y}'].equals(d[f'center_population_{y}']+d[f'external_population_{y}']))
        check('own_center_never_external_demographic_member',all(r.destination_uid not in r.external_origin_uids.split('|') for _,r in d.iterrows()))
        ds=pd.read_parquet(O/'demographic_direction_sensitivity.parquet')
        check('thresholds_explicit_1_5_10',set(ds.stability_threshold_percent)=={1,5,10})
        check('direction_profile_not_claimed_functional_or_migration_type',not ds.functional_type_or_migration_process_identified.any())
        fixed=pd.read_parquet(O/'fixed_source_catchment_demography.parquet')
        check('fixed_source_table_retains_service_level_and_date',{'service_level','source_document_date'}<=set(fixed.columns))
        check('fixed_source_level_count_matches_strict_demographic_profiles',len(fixed)==len(d))
        check('fixed_level_groups_match_demographic_group_identity',set(zip(fixed.source_id,fixed.source_document_date,fixed.destination_uid,fixed.function_group,fixed.service_level))==set(zip(d.canonical_source_id,d.canonical_evidence_date,d.destination_uid,d.function_group,d.canonical_service_level)))
        check('semantic_basic_and_senior_membership_never_deduplicated',canonical_membership_key('same_act','2025-01-01','origin','provider','education','grades_1_9')!=canonical_membership_key('same_act','2025-01-01','origin','provider','education','grades_10_11'))
    if (R/'history/uchaly_school_relations_2025.csv').exists():
        raw=pd.read_csv(R/'history/uchaly_school_relations_2025.csv')
        sub=g[g.observation_scope.eq('uchaly_multilevel_document_corpus')]
        check('all_uchaly_assertions_preserved',len(raw)==len(sub))
        check('uchaly_branch_ambiguity_not_external_physical_link',not sub.loc[~sub.physical_service_destination_accepted.eq(True),'counts_as_external_service_evidence'].any())
        check('known_uchaly_school_levels_not_collapsed',set(sub.service_level)==set(raw.service_level))
        nest=pd.read_parquet(O/'documented_functional_nesting.parquet')
        check('nesting_requires_lower_provider_assignment',nest.lower_provider_itself_normatively_assigned_to_higher.all())
        check('nesting_requires_actual_subset',nest.lower_external_origins_subset_higher.all())
        check('nesting_does_not_claim_all_functions',nest.evidence_scope.eq('documented_education_level_nesting_not_all_function_hierarchy').all())
    result={'passed':sum(x['pass'] for x in checks),'total':len(checks),'checks':checks}
    (O/'INVARIANTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    assert all(x['pass'] for x in checks),result
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':run()

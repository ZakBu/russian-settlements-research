#!/usr/bin/env python3
"""Build an evidence-preserving graph; no geometric territorial allocation."""
from pathlib import Path
import argparse, hashlib, json, re
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=ROOT.parent/'anchor_research_20261019'
GROUPS=['retail47','food56','education85','health86','social8788','repair95','personal96']
EXTERNAL_KINDS={'statutory_school_catchment','provider_reported_service_catchment','provider_reported_service','normative_school_assignment','normative_school_attachment'}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical_membership_key(source,date,origin,destination,function,service_level):
    # Service level is an identity component, so basic and senior service claims
    # can never be removed as duplicate assertions of the same document.
    return hashlib.sha256('|'.join(map(str,[source,date,origin,destination,function,service_level])).encode()).hexdigest()
def norm(x):
    if pd.isna(x):return ''
    return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def resolve(name,region,municipality,panel):
    c=panel[panel['_name'].eq(norm(name))]
    r=norm(region)
    if r:
        c=c[c['_region'].map(lambda z:z in r or r in z)]
    if len(c)>1 and norm(municipality):
        m=norm(municipality)
        stem=m.split()[0]
        c=c[c['_mun'].str.contains(stem,regex=False)]
    return (c.iloc[0].id,'exact_name_region_context') if len(c)==1 else (None,'unresolved_ambiguous_or_absent')

def write(df,name,out):
    df.to_csv(out/f'{name}.csv',index=False)
    df.to_parquet(out/f'{name}.parquet',index=False)

def build(out):
    out.mkdir(parents=True,exist_ok=True)
    watched=[OLD/'data/point_axis.parquet',OLD/'data/school_inventory_linked.csv',OLD/'model/documented_graph/service_edges_calculated.csv']
    watched += [OLD/f'economy/coded_results/{y}/points_economic_features.parquet' for y in [2016,2021]]
    watched += [ROOT/p for p in ['history/edges_by_year.csv','history/konakovo_edges_by_year.csv','history/uchaly_school_relations_2025.csv','history/uchaly_school_provider_sites_2025.csv','medical/objects.csv','medical/relations.csv','medical/object_aliases.csv','marketplaces/objects.csv'] if (ROOT/p).exists()]
    initial_hashes={str(p):sha(p) for p in watched}
    panel=pd.read_parquet(OLD/'data/point_axis.parquet')
    assert panel.id.is_unique
    panel['_name']=panel.name.map(norm);panel['_region']=panel.region.map(norm);panel['_mun']=panel.municipality_upper_2021.map(norm)
    inputs=[OLD/'data/point_axis.parquet',OLD/'model/documented_graph/service_edges_calculated.csv']
    base=pd.read_csv(inputs[-1])
    assert set(base.link_kind)=={'statutory_school_catchment','provider_reported_service_catchment'}
    graph=base.copy()
    graph['function_group']=np.where(graph.link_kind.eq('statutory_school_catchment'),'education','health')
    graph['relation_kind']=graph.link_kind
    graph['observation_scope']='previous_accepted_document_corpus'
    graph['counts_as_external_service_evidence']=graph.both_endpoints_linked & ~graph.endpoint_same_place
    graph['historical_snapshot_claim']=False
    graph['actual_flow_observed']=False
    new_relations=[]
    hist=ROOT/'history/edges_by_year.csv'
    if hist.exists():
        h=pd.read_csv(hist);inputs.append(hist)
        h['edge_id']=['HIST:'+str(i) for i in range(len(h))]
        h['function_group']='education';h['observation_scope']='paired_history_document_corpus'
        h['counts_as_external_service_evidence']=h.origin_uid.notna()&h.destination_uid.notna()&h.origin_uid.ne(h.destination_uid)
        h['historical_snapshot_claim']=True;h['actual_flow_observed']=False
        graph=pd.concat([graph,h],ignore_index=True)
    kona=ROOT/'history/konakovo_edges_by_year.csv'
    if kona.exists():
        h=pd.read_csv(kona);inputs.append(kona)
        h['source_edge_id']=h.edge_id;h['edge_id']='KONA:'+h.year.astype(str)+':'+h.edge_id.astype(str)
        h['function_group']='education';h['observation_scope']='paired_konakovo_document_corpus'
        h['counts_as_external_service_evidence']=h.origin_uid.notna()&h.destination_uid.notna()&h.origin_uid.ne(h.destination_uid)
        h['historical_snapshot_claim']=True;h['actual_flow_observed']=False
        graph=pd.concat([graph,h],ignore_index=True)
    ba_hist=ROOT/'history/uchaly_school_relations_2025.csv'
    if ba_hist.exists():
        h=pd.read_csv(ba_hist);inputs.append(ba_hist)
        for src,dst in [('origin','origin_name'),('destination','provider_settlement'),('destination_name','provider_settlement')]:
            if dst not in h.columns and src in h.columns:h=h.rename(columns={src:dst})
        assert {'origin_name','provider_settlement','service_level'}.issubset(h.columns),h.columns
        for i,r in h.iterrows():
            for col,namecol in [('origin_uid','origin_name'),('destination_uid','provider_settlement')]:
                if col not in h.columns or pd.isna(r.get(col)):
                    # Preserve source unresolved identities; never replace missing within a district
                    # by a globally unique same name outside that district.
                    h.loc[i,col]=None
        h['edge_id']=['BA_HIST:'+str(i) for i in range(len(h))]
        h['function_group']='education';h['observation_scope']='uchaly_multilevel_document_corpus'
        h['counts_as_external_service_evidence']=h.origin_uid.notna()&h.destination_uid.notna()&h.origin_uid.ne(h.destination_uid)&h.physical_service_destination_accepted
        h['historical_snapshot_claim']=True;h['actual_flow_observed']=False
        if 'relation_kind' not in h:h['relation_kind']='normative_school_attachment'
        graph=pd.concat([graph,h],ignore_index=True)
    medical=ROOT/'medical/relations.csv'
    if medical.exists():
        x=pd.read_csv(medical);inputs.append(medical)
        x=x.rename(columns={'origin':'origin_name','destination':'destination_name'})
        assert {'origin_name','destination_name'}.issubset(x.columns)
        # Schema adapter defined once raw collection has frozen its field names.
        if {'origin_name','destination_name'}.issubset(x.columns):
            for i,r in x.iterrows():
                o,os=resolve(r.origin_name,r.get('region',''),r.get('municipality',''),panel)
                d,ds=resolve(r.destination_name,r.get('region',''),r.get('municipality',''),panel)
                kind=r.get('relation_kind',r.get('link_kind','unknown'))
                new_relations.append(dict(edge_id=f'MED:{i}',source_id=r.get('source_id','medical'),source_url=r.get('source_url',''),source_document_date=r.get('source_document_date',''),observed_date=r.get('observed_date',''),origin_name=r.origin_name,provider_settlement=r.destination_name,origin_uid=o,destination_uid=d,origin_match_status=os,destination_match_status=ds,relation_kind=kind,function_group='health',service_level=r.get('service_level','unspecified'),counts_as_external_service_evidence=bool(o and d and o!=d and kind in EXTERNAL_KINDS),evidence_level=r.get('evidence_level','unclassified'),historical_snapshot_claim=False,actual_flow_observed=False,observation_scope='new_document_corpus',relation_semantics=r.get('note','')))
                new_relations[-1].update(region=r.get('region'),municipality=r.get('municipality'),source_relation_id=r.get('relation_id'))
                if kind=='scheduled_mobile_visit':
                    new_relations[-1]['raw_source_document_date_field']=r.get('source_document_date','')
                    new_relations[-1]['planned_service_date']=r.get('scheduled_date',r.get('source_document_date',''))
                    new_relations[-1]['source_document_date']=None
        assert len(new_relations)==len(x), 'Every medical input relation must be represented, including unresolved ones'
    if new_relations:graph=pd.concat([graph,pd.DataFrame(new_relations)],ignore_index=True)
    # Preserve the original 79 records, including unresolved endpoints.
    graph['edge_uid']=graph.source_id.astype(str)+'::'+graph.edge_id.astype(str)
    graph['relation_direction_semantics']=graph.relation_kind.map(lambda k:'site_to_parent_organization_not_resident_trip' if k=='institutional_subdivision' else ('planned_mobile_service_to_destination_not_resident_attraction' if k=='scheduled_mobile_visit' else 'resident_origin_to_normative_or_reported_service_site_not_observed_trip'))
    graph['functional_level_order']=graph.service_level.map({'education_basic_1_9':1,'education_senior_10_11':2,'general_education_grades_1_9':1,'general_education_grades_10_11':2,'grades_1_9':1,'grades_10_11':2})
    graph['canonical_source_id']=graph.source_id.replace({'SV2025':'NT2025','BA_MED':'uch_before_after'})
    graph['canonical_service_level']=graph.service_level.replace({'general_education':'general_education_territorial_attachment','general_education_admission_2025_2026':'first_grade_admission_territorial_priority','feldsher_obstetric_primary_care':'FAP'})
    graph['canonical_evidence_date']=graph.source_document_date
    graph.loc[graph.source_id.eq('BA_MED'),'canonical_evidence_date']='2025-01-09'
    def membership_key(r):
        if not r.counts_as_external_service_evidence:return None
        return canonical_membership_key(r.canonical_source_id,r.canonical_evidence_date,r.origin_uid,r.destination_uid,r.function_group,r.canonical_service_level)
    graph['canonical_membership_id']=graph.apply(membership_key,axis=1)
    graph['membership_assertion_repeats_other_source_extraction']=graph.canonical_membership_id.notna()&graph.canonical_membership_id.duplicated(keep=False)
    assert graph.edge_uid.is_unique
    write(graph,'integrated_relations',out)
    accepted=graph[graph.counts_as_external_service_evidence.fillna(False)].copy()
    canonical=accepted.drop_duplicates('canonical_membership_id')
    write(canonical,'canonical_documented_external_memberships',out)
    # Repeated source assertions never multiply the population of one origin.
    pairs=accepted[['origin_uid','destination_uid','function_group','source_id']].drop_duplicates()
    write(pairs,'documented_external_memberships',out)
    level_pairs=accepted[['origin_uid','destination_uid','function_group','service_level','functional_level_order','source_id','source_document_date']].drop_duplicates()
    write(level_pairs,'documented_function_level_memberships',out)
    nesting=[]
    known=level_pairs[level_pairs.functional_level_order.notna()]
    level_sets={k:set(v.origin_uid) for k,v in known.groupby(['source_id','destination_uid','function_group','service_level','functional_level_order','source_document_date'])}
    for a,sa in level_sets.items():
        for b,sb in level_sets.items():
            if a[2]!=b[2] or a[4]>=b[4] or a[5]!=b[5] or a[1]==b[1]:continue
            if a[1] in sb and sa and sa<=sb:
                nesting.append(dict(lower_provider_uid=a[1],higher_provider_uid=b[1],function_group=a[2],lower_service_level=a[3],higher_service_level=b[3],lower_source=a[0],higher_source=b[0],source_document_date=a[5],n_lower_external_origins=len(sa),n_higher_external_origins=len(sb),lower_provider_itself_normatively_assigned_to_higher=True,lower_external_origins_subset_higher=True,evidence_scope='documented_education_level_nesting_not_all_function_hierarchy',common_origins='|'.join(sorted(sa))))
    write(pd.DataFrame(nesting,columns=['lower_provider_uid','higher_provider_uid','function_group','lower_service_level','higher_service_level','lower_source','higher_source','source_document_date','n_lower_external_origins','n_higher_external_origins','lower_provider_itself_normatively_assigned_to_higher','lower_external_origins_subset_higher','evidence_scope','common_origins']),'documented_functional_nesting',out)
    multifunction=[]
    for u,g in accepted.groupby('destination_uid'):
        groups=sorted(g.function_group.unique())
        for i,a in enumerate(groups):
            for b in groups[i+1:]:
                shared=set(g[g.function_group.eq(a)].origin_uid)&set(g[g.function_group.eq(b)].origin_uid)
                if shared:
                    multifunction.append(dict(provider_uid=u,function_a=a,function_b=b,n_shared_external_origins=len(shared),shared_origins='|'.join(sorted(shared)),document_dates='|'.join(sorted(g.source_document_date.dropna().astype(str).unique())),scope='documented_multifunction_service_fragment_not_complete_sgrt',actual_flow_observed=False))
    write(pd.DataFrame(multifunction,columns=['provider_uid','function_a','function_b','n_shared_external_origins','shared_origins','document_dates','scope','actual_flow_observed']),'documented_multifunction_fragments',out)
    object_rows=[]
    inv=OLD/'data/school_inventory_linked.csv';inputs.append(inv)
    urls=base.groupby('source_id').source_url.first().to_dict()
    for _,r in pd.read_csv(inv).iterrows():
        object_rows.append(dict(object_id=r.inventory_id,canonical_object_id=r.inventory_id,settlement_uid=r.id,settlement=r.provider_settlement,region=r.region,function_group='education',service_level=r.service_level,object_name=r.provider_name,source_id=r.source_id,source_url=urls[r.source_id],source_document_date={'SV2025':'2025-03-05','NV2026':'2026-02-27','TV2021':'2021-01-27'}[r.source_id],object_evidence='listed_physical_institution_no_capacity_or_usage_claim',match_status=r.match_status))
    ba_sites=ROOT/'history/uchaly_school_provider_sites_2025.csv'
    if ba_sites.exists():
        data=pd.read_csv(ba_sites);inputs.append(ba_sites)
        for i,r in data.iterrows():
            if r.site_status!='physical_school_site_explicit':continue
            object_rows.append(dict(object_id=f'BA_SCHOOL_SITE:{i}',canonical_object_id=f'BA_SCHOOL_SITE:{i}',settlement_uid=r.destination_uid,settlement=r.provider_settlement,region='Республика Башкортостан',function_group='education',service_level=r.school_level,object_name=r.provider_name,source_id='UCH2025_03224',source_url=r.source_url,source_document_date=r.source_date,object_evidence='explicit_physical_school_site_in_signed_act',match_status='source_context_uid_preserved' if pd.notna(r.destination_uid) else 'unresolved_source_identity_preserved'))
    for f in [ROOT/'medical/objects.csv',ROOT/'marketplaces/objects.csv']:
        if not f.exists():continue
        inputs.append(f);data=pd.read_csv(f)
        aliases={}
        if f.parent.name=='medical' and (f.parent/'object_aliases.csv').exists():
            af=f.parent/'object_aliases.csv';inputs.append(af);a=pd.read_csv(af);aliases=dict(zip(a.object_id,a.same_physical_unit))
        for _,r in data.iterrows():
            n=r.get('settlement',r.get('settlement_name',''))
            provided=r.get('settlement_uid')
            if pd.notna(provided):
                assert provided in set(panel.id), 'Provided settlement identity must exist in frozen axis'
                u,st=provided,'source_link_preserved:'+str(r.get('link_status','provided_uid'))
            else:u,st=resolve(n,r.get('region',''),r.get('municipality',''),panel)
            row=r.to_dict();row.update(settlement_uid=u,match_status=st,object_evidence='listed_physical_site_not_observed_usage',canonical_object_id=aliases.get(r.object_id,r.object_id))
            object_rows.append(row)
    obj=pd.DataFrame(object_rows)
    # WB publishes several delivery-point subtypes; unknown/partner delivery locations
    # are preserved but do not silently become confirmed public pickup functions.
    obj['candidate_function_group']=obj.function_group
    delivery=obj.function_group.eq('marketplace_pickup')
    is_wb=obj.get('brand',pd.Series(index=obj.index,dtype=object)).eq('Wildberries')
    focus=obj.get('focus_scope',pd.Series(False,index=obj.index)).eq(True)
    obj.loc[delivery&is_wb&~focus,'candidate_function_group']=None
    obj['pickup_scope_status']=np.where(delivery&is_wb&~focus,'provider_delivery_location_not_confirmed_focus_pickup',np.where(delivery,'historical_operator_or_focus_pickup_listing','not_applicable'))
    write(obj,'physical_object_assertions',out)
    node_uids=set(graph.destination_uid.dropna())|set(graph.origin_uid.dropna())|set(obj.settlement_uid.dropna())
    nodes=panel[panel.id.isin(node_uids)].drop(columns=['_name','_region','_mun']).copy()
    def gs(uid):return sorted(accepted.loc[accepted.destination_uid.eq(uid),'function_group'].unique())
    nodes['documented_external_function_groups']=nodes.id.map(lambda u:'|'.join(gs(u)))
    nodes['documented_external_function_diversity']=nodes.id.map(lambda u:len(gs(u)))
    nodes['n_external_origins_unique']=nodes.id.map(lambda u:accepted.loc[accepted.destination_uid.eq(u),'origin_uid'].nunique())
    nodes['document_dates']=nodes.id.map(lambda u:'|'.join(sorted(accepted.loc[accepted.destination_uid.eq(u),'source_document_date'].dropna().astype(str).unique())))
    nodes['evidence_scope']='heterogeneous_document_dates_not_single_historical_snapshot'
    nodes['system_status']=nodes.documented_external_function_diversity.map(lambda n:'documented_multifunction_external_node' if n>=2 else ('documented_external_function_node' if n==1 else 'external_centrality_not_established'))
    nodes['complete_sgrt_asserted']=False
    nodes['physical_function_groups_observed_corpus']=nodes.id.map(lambda u:'|'.join(sorted(obj.loc[obj.settlement_uid.eq(u),'candidate_function_group'].dropna().unique())))
    nodes['physical_function_diversity_observed_corpus']=nodes.physical_function_groups_observed_corpus.map(lambda z:len(z.split('|')) if z else 0)
    nodes['listed_physical_objects_distinct_after_documented_aliases']=nodes.id.map(lambda u:obj.loc[obj.settlement_uid.eq(u),'canonical_object_id'].nunique())
    nodes['all_wb_delivery_location_assertions']=nodes.id.map(lambda u:int((obj.settlement_uid.eq(u)&is_wb).sum()))
    nodes['focus_wb_pickup_location_assertions']=nodes.id.map(lambda u:int((obj.settlement_uid.eq(u)&is_wb&focus).sum()))
    nodes['multifunction_physical_candidate_with_external_witness']=nodes.documented_external_function_diversity.ge(1)&nodes.physical_function_diversity_observed_corpus.ge(2)
    for yr in [2016,2021]:
        f=OLD/f'economy/coded_results/{yr}/points_economic_features.parquet';inputs.append(f)
        cols=['id','quality_mode','legal_entities','direct_consumer_function_diversity']+[g+'_legal_entities' for g in GROUPS]
        e=pd.read_parquet(f,columns=cols);e=e[e.quality_mode.eq('coded_baseline')].drop(columns='quality_mode')
        e=e.rename(columns={c:f'{c}_{yr}' for c in e if c!='id'})
        nodes=nodes.merge(e,on='id',how='left',validate='one_to_one')
    nodes['registered_multifunction_candidate_with_documented_external_function_2021']=nodes.documented_external_function_diversity.ge(1)&nodes.direct_consumer_function_diversity_2021.ge(2)
    nodes['registry_change_2016_2021']=nodes.direct_consumer_function_diversity_2021-nodes.direct_consumer_function_diversity_2016
    write(nodes,'integrated_nodes',out)
    # A second compact node profile retains legal versus physical evidence separately.
    provider=nodes[nodes.documented_external_function_diversity.gt(0)]
    write(provider,'documented_provider_profiles',out)
    catch=[];sets={}
    pop=panel.set_index('id')
    for (src,date,dest,func,level),g in canonical.groupby(['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level'],dropna=False):
        ids=set(g.origin_uid);sets[(src,dest,func,level,date)]=ids
        r=dict(source_id=src,source_document_date=date,destination_uid=dest,destination_name=pop.loc[dest,'name'],function_group=func,service_level=level,n_origins=len(ids),boundary_kind='fixed_canonical_source_date_function_level_membership',service_historical_presence_asserted=False)
        for y in [2002,2010,2021]:
            a=pop.loc[list(ids),f'population_{y}'];r[f'population_{y}']=a.sum() if not a.isna().any() else np.nan;r[f'n_missing_population_{y}']=a.isna().sum();r[f'n_zero_population_{y}']=a.eq(0).sum()
        r['fixed_membership_change_2010_2021']=r['population_2021']-r['population_2010']
        catch.append(r)
    write(pd.DataFrame(catch),'fixed_source_catchment_demography',out)
    overlaps=[]
    keys=list(sets)
    for i,a in enumerate(keys):
        for b in keys[i+1:]:
            shared=sets[a]&sets[b]
            if not shared:continue
            config='cross_function_documented_overlap' if a[2]!=b[2] else ('same_function_different_levels_not_competition' if a[3]!=b[3] else 'same_function_cross_document_overlap_not_simultaneous_competition')
            overlaps.append(dict(source_a=a[0],date_a=a[4],provider_a=a[1],function_a=a[2],service_level_a=a[3],source_b=b[0],date_b=b[4],provider_b=b[1],function_b=b[2],service_level_b=b[3],n_common_origins=len(shared),jaccard=len(shared)/len(sets[a]|sets[b]),set_a_inside_b=sets[a]<=sets[b],set_b_inside_a=sets[b]<=sets[a],configuration=config,functional_hierarchy_asserted=False,single_snapshot_asserted=False,common_origins='|'.join(sorted(shared))))
    write(pd.DataFrame(overlaps,columns=['source_a','date_a','provider_a','function_a','service_level_a','source_b','date_b','provider_b','function_b','service_level_b','n_common_origins','jaccard','set_a_inside_b','set_b_inside_a','configuration','functional_hierarchy_asserted','single_snapshot_asserted','common_origins']),'documented_overlap',out)
    audit=dict(base_rows=len(base),integrated_rows=len(graph),linked_external_evidence_rows=len(accepted),source_specific_documented_memberships=len(pairs),unique_documented_memberships_across_dates_and_sources=len(pairs.drop(columns='source_id').drop_duplicates()),provider_nodes=len(provider),registered_multifunction_candidates_with_external_witness=int(provider.registered_multifunction_candidate_with_documented_external_function_2021.sum()),physical_multifunction_candidates_with_external_witness=int(provider.multifunction_physical_candidate_with_external_witness.sum()),physical_object_assertions=len(obj),physical_object_assertions_linked=int(obj.settlement_uid.notna().sum()),nodes=len(nodes),overlaps=len(overlaps),forced_assignments=0,complete_sgrt_claims=0,inputs={str(p.relative_to(ROOT.parent)):sha(p) for p in inputs},checks={'base_79_preserved':len(graph[graph.observation_scope.eq('previous_accepted_document_corpus')])==79,'membership_identity_preserved':all(pairs.origin_uid.ne(pairs.destination_uid)),'no_forced_coverage':True,'all_census_zeros_retained':True,'no_historical_function_backcast':True,'no_multifunction_claim_from_legal_presence_alone':True,'organization_and_schedule_not_external_dependence':not graph.loc[graph.relation_kind.isin(['institutional_subdivision','scheduled_mobile_visit']),'counts_as_external_service_evidence'].any()})
    assert all(initial_hashes[str(p)]==sha(p) for p in inputs),'Input changed during model build; freeze sources and rerun'
    audit['input_bytes_stable_during_build']=True
    audit['documented_multifunction_fragments']=len(multifunction)
    audit['documented_functional_nestings']=len(nesting)
    audit['multifunction_external_provider_nodes']=int(provider.documented_external_function_diversity.ge(2).sum())
    audit['strict_source_date_function_level_catchments']=len(catch)
    (out/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in audit.items() if k!='inputs'},ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=HERE/'results');args=ap.parse_args();build(args.out)

"""Independent source/construct readback; does not call the model's implementation."""
from pathlib import Path
import hashlib, json
import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent
R = ROOT / 'model/results'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    checks = []
    def ck(name, value, detail=''):
        checks.append(dict(check=name, passed=bool(value), detail=detail))
    panel = pd.read_parquet(ROOT.parent/'anchor_research_20261019/data/point_axis.parquet').set_index('id')
    g = pd.read_parquet(R/'integrated_relations.parquet')
    m = pd.read_parquet(R/'documented_function_level_memberships.parquet')
    nodes = pd.read_parquet(R/'integrated_nodes.parquet').set_index('id')
    objects = pd.read_parquet(R/'physical_object_assertions.parquet')
    fragments = pd.read_parquet(R/'documented_multifunction_fragments.parquet')
    nesting = pd.read_parquet(R/'documented_functional_nesting.parquet')
    audit = json.loads((R/'AUDIT.json').read_text())
    names = {'Малоказаккулово':'np3:yRtjROtH5-LMFi9RQeJfGhdNsoRAZdbcAF7EO1ZV7QI',
             'Калуево':'np3:r0ERT_z52M--ogJkNJzciH0EAJC8RSYqsZxYqyreDL8',
             'Амангильдино':'np3:Z2SuxqUiC-Env3K3xmCLuRcTaFqZW96OueK9Nvj1RZA',
             'Уральск':'np3:fehGpVUFPc8CMcT9zmAn1gaeUALAvKi5g_b6ofV06dc'}
    for name, uid in names.items():
        ck('exact_axis_identity_'+name, panel.loc[uid,'name']==name and panel.loc[uid,'municipality_upper_2021']=='Учалинский муниципальный район')
    ba = pd.read_csv(ROOT/'history/uchaly_school_relations_2025.csv')
    ck('all13_BA_assertions_preserved',len(g[g.source_id.eq('UCH2025_03224')])==len(ba)==13)
    ck('10_BA_physical_destinations',ba.physical_service_destination_accepted.sum()==10)
    ck('8_BA_physical_external_assertions', (ba.physical_service_destination_accepted & ba.external_origin).sum()==8)
    bad = g[g.source_id.eq('UCH2025_03224') & ~g.physical_service_destination_accepted.eq(True)]
    ck('3_organization_territories_excluded',len(bad)==3 and not bad.counts_as_external_service_evidence.any())
    ck('school_assignment_not_exclusive',not ba.assignment_exclusive.any())
    lo = m[(m.source_id=='UCH2025_03224') & (m.destination_uid==names['Малоказаккулово']) & (m.service_level=='grades_1_9')]
    hi = m[(m.source_id=='UCH2025_03224') & (m.destination_uid==names['Уральск']) & (m.service_level=='grades_10_11')]
    lo_ids, hi_ids = set(lo.origin_uid),set(hi.origin_uid)
    ck('BA_lower_two_external_origins',lo_ids=={names['Калуево'],names['Амангильдино']})
    ck('BA_upper_three_external_origins',hi_ids==lo_ids|{names['Малоказаккулово']})
    ck('level_order_not_population_size',set(lo.functional_level_order)=={1} and set(hi.functional_level_order)=={2})
    ck('one_level_nesting',len(nesting)==1)
    for row in nesting.itertuples():
        l = m[(m.destination_uid==row.lower_provider_uid)&(m.function_group==row.function_group)&(m.service_level==row.lower_service_level)&(m.source_id==row.lower_source)&(m.source_document_date==row.source_document_date)]
        h = m[(m.destination_uid==row.higher_provider_uid)&(m.function_group==row.function_group)&(m.service_level==row.higher_service_level)&(m.source_id==row.higher_source)&(m.source_document_date==row.source_document_date)]
        ls,hs=set(l.origin_uid),set(h.origin_uid)
        ck('nesting_recomputed_sets', bool(ls) and ls<=hs and row.lower_provider_uid in hs)
        ck('nesting_recomputed_counts',len(ls)==row.n_lower_external_origins and len(hs)==row.n_higher_external_origins)
        ck('nesting_reported_common_origins',set(row.common_origins.split('|'))==ls&hs)
        ck('nesting_scope_education_only',row.evidence_scope=='documented_education_level_nesting_not_all_function_hierarchy')
    ck('one_shared_external_two_function_fragment',len(fragments)==1)
    for row in fragments.itertuples():
        a=set(m.loc[(m.destination_uid==row.provider_uid)&(m.function_group==row.function_a),'origin_uid'])
        b=set(m.loc[(m.destination_uid==row.provider_uid)&(m.function_group==row.function_b),'origin_uid'])
        ck('fragment_recomputed_intersection',set(row.shared_origins.split('|'))==a&b and len(a&b)==row.n_shared_external_origins)
        ck('fragment_is_Kaluevo_to_Malokazakkulovo',row.provider_uid==names['Малоказаккулово'] and a&b=={names['Калуево']})
        ck('fragment_not_claimed_observed_flow',not row.actual_flow_observed)
        ck('fragment_two_dates_preserved',set(row.document_dates.split('|'))=={'2025-01-09','2025-03-12'})
    cap=ROOT/'medical/captures/uch_news.html'
    doc=html.fromstring(cap.read_bytes())
    articles=doc.xpath('//article[.//a[@href="/ob-uchrezhdenii/bylo-stalo"]]')
    ck('medical_publication_exact_article_match',len(articles)==1)
    article=' '.join(articles[0].text_content().split())
    ck('medical_publication_date_in_same_article','Опубликовано: 09.01.2025 12:15' in article)
    ck('medical_service_territory_same_article',all(x in article for x in ['Малоказаккулово и Калуево','Батталово и Аслаево','330 человек','233 человека']))
    tv=pd.read_csv(ROOT/'history/konakovo_edges_by_year.csv')
    ck('konakovo42_pairs_each_date',tv.groupby('year').size().to_dict()=={2021:42,2026:42})
    a=tv[tv.year==2021];b=tv[tv.year==2026]
    def pairs(d):return set(zip(d.origin_name,d.provider_settlement))
    ck('konakovo42_place_assignments_stable',len(pairs(a))==42 and pairs(a)==pairs(b))
    ck('konakovo_38_resolved_each_date',tv.groupby('year').both_endpoints_linked.sum().to_dict()=={2021:38,2026:38})
    ck('249_source_object_assertions',len(objects)==audit['physical_object_assertions']==249)
    ck('132_nodes',len(nodes)==audit['nodes']==132)
    ck('16_physical_candidates',int(nodes.multifunction_physical_candidate_with_external_witness.sum())==audit['physical_multifunction_candidates_with_external_witness']==16)
    ck('physical_candidates_not_complete_systems',not nodes.complete_sgrt_asserted.any())
    nonfocus=objects[objects.pickup_scope_status.eq('provider_delivery_location_not_confirmed_focus_pickup')]
    ck('WB_nonstrict_types_excluded_from_function_group',len(nonfocus)==46 and nonfocus.candidate_function_group.isna().all())
    wbpath=ROOT/'marketplaces/wb_source_only_ru_20261019.parquet'
    wb=pd.read_parquet(wbpath)
    focus=pd.read_parquet(ROOT/'marketplaces/wb_pvz_focus_ru_20261019.parquet')
    ck('WB_all91136_source_identifiers_unique',len(wb)==91136 and wb.source_object_id.is_unique)
    ck('WB_focus68699_exact_types8_34',len(focus)==68699 and set(focus.source_object_id)==set(wb.loc[wb.typePoint.isin([8,34]),'source_object_id']))
    bb=wb[wb.source_object_id.eq(50080949)]
    ck('WB_source_ru_contains_Barentsburg_counterexample',len(bb)==1 and bb.iloc[0].source_country=='ru' and 'Баренцбург' in bb.iloc[0].address and bb.iloc[0].latitude>78)
    ck('WB_opening_dates_not_invented',wb.opening_date.isna().all())
    ck('WB_no_demand_relations_claim',not wb.external_catchment_evidence.any())
    files=[ROOT/'model/build_integrated_graph.py',R/'integrated_relations.parquet',R/'physical_object_assertions.parquet',R/'documented_multifunction_fragments.parquet',R/'documented_functional_nesting.parquet',ROOT/'history/uchaly_school_relations_2025.csv',ROOT/'history/konakovo_edges_by_year.csv',cap,ROOT/'history/raw/BA2025_order03224.pdf',ROOT/'history/raw/TV_unknown_attachment.pdf',ROOT/'history/raw/TV2026_attachment.pdf']
    files.extend([wbpath,ROOT/'marketplaces/wb_pvz_focus_ru_20261019.parquet'])
    result=dict(status='PASS' if all(c['passed'] for c in checks) else 'FAIL',checks=checks,n_checks=len(checks),n_passed=sum(c['passed'] for c in checks),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},visual_source_reading=['BA2025 original PDFp13/printed11 rows25–27: school physical addresses, grades1–9 vs10–11; reviewed original-derived PNG','Konakovo2021 PDFpp5–6 and2026 PDFp7:18+8+16 external origin names agree; school organization renaming not site closure'],medical_date=dict(primary_url='https://xn--90ad1cm.xn--p1ai/10-ob-uchrezhdenii',exact_article_href='/ob-uchrezhdenii/bylo-stalo',publication_datetime='2025-01-09 12:15',publication_date_not_service_start=True),scope='Independent actual output readback plus original PDF/HTML source inspection; no national or actual-flow completeness claim.')
    (OUT/'FINAL_SOURCE_CONSTRUCT_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','n_checks','n_passed']},ensure_ascii=False))
    assert result['status']=='PASS', [c for c in checks if not c['passed']]

if __name__=='__main__':main()

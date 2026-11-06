"""Independent cohort, register and numerical checks; imports no phase analyzer."""
from pathlib import Path
import argparse,collections,hashlib,json
import pandas as pd
HERE=Path(__file__).resolve().parent
PHASE=HERE.parent
ROOT=HERE.parents[3]
COHORT=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024/system/centre_system_demography.csv'
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registers-only',action='store_true',help='Skip saved page/search-body reads and hashes; retain every register, geography and numerical check.')
    args=parser.parse_args()
    search_hash_checked=0
    d=pd.read_csv(COHORT).set_index('source_record_id_2021')
    assert len(d)==1953 and int(d.medium_primary2002.sum())==1273
    checked=0
    for part,file,idcol,popcol in [('observed_west','primary_extracts.csv','centre_source_record_id_2021','population2002_centre'),('observed_east','positive_extracts.csv','centre_source_record_id','centre_population2002')]:
        rows=pd.read_csv(PHASE/part/file)
        for r in rows.to_dict('records'):
            q=d.loc[r[idcol]]
            assert q.medium_primary2002 and q.population_2002==r[popcol]
            checked+=1
    west=pd.read_csv(PHASE/'observed_west/query_log.csv')
    west_main=west.loc[west.phase.eq('bounded_fixed24')]
    assert len(west)==84 and len(west_main)==72 and west_main.centre.nunique()==24
    east=pd.read_csv(PHASE/'observed_east/query_log.csv')
    main=east.loc[east.phase.eq('planned_ural_siberia_volga')]
    assert len(east)==71 and len(main)==58 and main.centre.nunique()==29
    for row in east.to_dict('records'):
        if row['path']=='conversation_only':
            assert pd.isna(row['raw_sha256']) and row['phase']=='initial_reconnaissance_not_part_of_archived_30_centre_frame'
        elif not args.registers_only:
            raw=ROOT/row['path']
            assert hashlib.sha256(raw.read_bytes()).hexdigest()==row['raw_sha256']
            search_hash_checked+=1
        if pd.notna(row['source_record_id_2021']):
            q=d.loc[row['source_record_id_2021']]
            assert q.medium_primary2002 and q.population_2002==row['population_2002']
        else:
            assert row['phase']!='planned_ural_siberia_volga'
    west_cases=pd.read_csv(PHASE/'observed_west/primary_extracts.csv')
    assert not west_cases.review_id.duplicated().any()
    bounded=west_cases.loc[west_cases.evidence_kind.eq('named_prior_centre_local_receipt')]
    external=west_cases.loc[west_cases.discovery_frame.eq('external_lead_not_fixed24') & west_cases.evidence_kind.str.startswith('named_prior_centre_')]
    assert len(bounded)==1 and bounded.org_id.nunique()==1
    assert len(external)==2 and external.org_id.nunique()==1
    goods=pd.read_csv(PHASE/'goods_routes/goods_edges.csv')
    assert len(goods)==5 and not goods.edge_id.duplicated().any()
    assert not goods.qualified_named_medium_to_village_route.any()
    source_cards=json.loads((PHASE/'goods_routes/sourcecards.json').read_text())
    hashed=set()
    for card in source_cards:
        raw=ROOT/card['raw_path'];pin=card['acquisition']
        if not args.registers_only:
            assert raw.stat().st_size==pin['bytes']
            assert hashlib.sha256(raw.read_bytes()).hexdigest()==pin['sha256']
            hashed.add(str(raw))
    # The exact operators below are independently transcribed from the saved
    # original-domain reading: four headline comparisons, combined flow and six
    # selected regional comparisons. These are not additive OD volumes.
    expected={('Регионы России','Москва'):('=',1.77),('Регионы России','Санкт-Петербург'):('=',1.44),('Москва','Регионы России'):('=',1.44),('Санкт-Петербург','Регионы России'):('=',1.74),('Регионы России','Москва и Санкт-Петербург вместе'):('=',1.6),('Хабаровский край','Москва'):('>',15),('Ярославская область','Москва'):('=',14),('Саратовская область','Москва'):('=',8),('Ярославская область','Санкт-Петербург'):('=',10),('Оренбургская область','Санкт-Петербург'):('=',7),('Тюменская область','Санкт-Петербург'):('=',5)}
    flows=pd.read_csv(PHASE/'identification/regional_operator_flows.csv')
    assert len(flows)==len(expected)
    for r in flows.to_dict('records'):
        operator,factor=expected[(r['origin'],r['destination'])]
        assert r['reported_growth_factor_comparator']==operator
        assert abs(r['reported_growth_factor']-factor)<1e-10
        assert r['normalised_2024_index']==100
        assert abs(r['normalised_2025_index']-100*factor)<1e-10
        assert not r['absolute_volume_public'] and not r['complete_OD_matrix_public']
    pins=json.loads((PHASE/'identification/primary_sources.json').read_text())
    for card in pins['sources']:
        raw=ROOT/card['raw_path']
        if not args.registers_only:
            assert hashlib.sha256(raw.read_bytes()).hexdigest()==card['sha256']
            hashed.add(str(raw))
    combined=pd.read_csv(PHASE/'functional_evidence.csv')
    axis=pd.read_parquet(ROOT/'work/sources/research/ecommerce_settlement_20261024/national/national_target_source2021.parquet').set_index('source_record_id_2021')
    assert len(combined)==7 and combined.current_place_id.nunique()==7 and combined.prior_centre_id.nunique()==6
    assert len(axis)==144151 and axis.index.is_unique
    known_origins={'Верхнепашино','Угольные Копи'}
    old_places={'Толмачево','Серебрянский','Верхняя Троица','Верхнепашино'}
    for r in combined.to_dict('records'):
        cur=axis.loc[r['current_place_id']];prior=d.loc[r['prior_centre_id']]
        for col,field in [('current_receipt_place','name_2021'),('current_place_type','type_2021'),('current_place_region','region_2021'),('current_place_district','district_2021')]:assert r[col]==cur[field]
        assert prior.medium_primary2002 and prior.name_2021==r['prior_centre'] and prior.population_2002==r['prior_centre_population2002']
        known=r['current_receipt_place'] in known_origins
        assert r['origin_status']==('explicit_in_article' if known else 'unknown')
        if known:assert r['residential_origin']==r['current_receipt_place']
        else:assert pd.isna(r['residential_origin'])
        assert r['first_added_in_this_pass']==(r['current_receipt_place'] not in old_places)
        assert not r['after_trip_reduction_measured'] and not r['physical_goods_bypass_proven']
    print(json.dumps(dict(mode='registers_only' if args.registers_only else 'full_local',raw_search_answers_hash_checked=search_hash_checked,cohort_centres_n=len(d),fixed_medium_centres_n=int(d.medium_primary2002.sum()),published_geographic_rows_checked=checked,western_main_queries=len(west_main),western_all_queries=len(west),eastern_main_queries=len(main),eastern_all_queries=len(east),western_new_named_prior_reviews=len(bounded)+len(external),western_new_named_prior_cards=bounded.org_id.nunique()+external.org_id.nunique(),goods_rows=len(goods),qualified_named_medium_to_village_routes=int(goods.qualified_named_medium_to_village_route.sum()),regional_comparisons_checked=len(flows),raw_artifacts_hash_checked=len(hashed),synthesis_current_places=len(combined),synthesis_prior_centres=combined.prior_centre_id.nunique(),synthesis_new_places=int(combined.first_added_in_this_pass.sum()),synthesis_explicit_origins=int(combined.origin_status.eq('explicit_in_article').sum()),discrepancies=0,note='Arithmetic/source consistency only; no causal or geographic-identity verdict from counts.'),ensure_ascii=False))
if __name__=='__main__':main()

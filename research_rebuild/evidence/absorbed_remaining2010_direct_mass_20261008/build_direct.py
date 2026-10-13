"""Freeze direct included_in evidence after the actual51 residual screen."""
import gzip,json,re,subprocess,sys
from pathlib import Path
import pandas as pd
import xlrd
ROOT=Path(__file__).resolve().parents[3];E=ROOT/'research_rebuild/evidence';OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize,distance_km

def main():
    baseline=json.loads((OUT/'baseline51_receipt.json').read_text());pins=dict(baseline['input_pins'])
    pins[str(OUT/'baseline51_receipt.json')]=sha(OUT/'baseline51_receipt.json')
    for filename,expected in baseline['output_pins'].items():assert sha(OUT/filename)==expected;pins[str(OUT/filename)]=expected
    historical=pd.read_csv(OUT/'actual51_top400_historical_native_context.csv.gz',keep_default_na=False)
    cores=pd.read_csv(OUT/'actual51_finite_receiving_urban_NP_context.csv.gz',keep_default_na=False)
    rank=pd.read_csv(OUT/'actual51_remaining2010_native_rank.csv.gz',keep_default_na=False)
    pages=[]
    for path in [OUT/'own_wikipedia_batch.json.gz',OUT/'own_wikipedia_last_title.json.gz']:
        pins[str(path)]=sha(path);d=json.load(gzip.open(path,'rt'))
        pages.extend((page,path) for page in d['query']['pages'].values())
    source=E/'absorbed_residual_direct_events_next_20261008/own_wikipedia_batch.json.gz'
    pins[str(source)]=sha(source);page=next(p for p in json.load(gzip.open(source,'rt'))['query']['pages'].values() if p['title']=='Куровской')
    text=page['revisions'][0]['slots']['main']['*']
    assert 'Микрорайон Куровской входит в состав Ленинского округа города Калуга' in text and 'с 2012 года' in text
    assert 'Статус посёлка городского типа имел с 1954 по 2012 год' in text
    scope='direct_lifecycle_куровской_калуга';locator=f"page{page['pageid']}:revision{page['revisions'][0]['revid']}"
    child=historical[historical.region_norm.eq('калужская')&historical.settlement_name.eq('Куровской')&historical.settlement_type.eq('пгт')]
    receiver=cores[cores.region_norm.eq('калужская')&cores.settlement_name.eq('Калуга')&cores.settlement_type.eq('город')]
    assert len(child)==2 and set(child.census_year)=={2002,2010}
    assert not child.already_original_mixed_credited.any() and not child.already_direct_or_formation_credited.any()
    assert len(receiver)==3 and set(receiver.census_year)=={2002,2010,2021} and receiver.root.nunique()==1
    cid=receiver[receiver.census_year.eq(2021)].iloc[0].source_record_id
    observations=[];points=[];edges=[];native=[];credit=[];contexts=[];rawchecks=[]
    co=page['coordinates'][0];assert len(page['coordinates'])==1
    for row in child.itertuples():
        point=json.loads(row.existing_own_point_json);assert point
        assert distance_km((float(point['latitude']),float(point['longitude'])),(co['lat'],co['lon']))<5
        point_ledger=Path(point['point_ledger_path']);pins[str(point_ledger)]=sha(point_ledger)
        observations.append(dict(scope_id=scope,place=row.settlement_name,year=int(row.census_year),source_record_id=row.source_record_id,
            native_population=row.population,native_population_quality=row.population_value_quality,latitude=point['latitude'],longitude=point['longitude'],own_point=True,
            recipient_city='Калуга',event_date='2012',event_date_precision='year',event_relation='included_in',same_place_identity_asserted=False,
            receiving_city_2021_source_record_id=cid,child_2021_population_assigned=False,is_additive_to_original_final_mixed_census_axis=False,
            already_in_baseline51_direct_plus_formation_native_ID_union=False,new_native_population_if_event_admitted=row.population,
            whole_city_roster_closure_asserted=False,population_boundary_comparability_asserted=False,native_values_quality_preserved=True))
        points.append(dict(scope_id=scope,target_source_record_id=row.source_record_id,latitude=point['latitude'],longitude=point['longitude'],
            point_origin_file=str(point_ledger),point_origin_sha256=sha(point_ledger),point_origin_locator=row.source_record_id,
            point_origin_kind='existing_accepted_own_historical_locality_point_replayed',own_locality_point=True,recipient_point_assigned_to_child=False,
            point_temporal_interpretation='Own historical NP physical point continuity inferred; not a census-day measurement',
            independent_ownarticle_point_source=str(source),independent_ownarticle_point_sha256=sha(source),independent_ownarticle_point_locator=locator+':coordinates[0]',
            independent_ownarticle_latitude=co['lat'],independent_ownarticle_longitude=co['lon']))
        edges.append(dict(scope_id=scope,from_source_record_id=row.source_record_id,to_source_record_id=cid,relation='included_in',event_date='2012',date_precision='year',
            event_source_file=str(source),event_source_sha256=sha(source),event_source_locator=locator,event_source_quality='secondary_own_Wikipedia_literal_microdistrict_since2012_and_formerPGT_status',
            same_place=False,graph_union_allowed=False,whole_city_roster_closure_asserted=False,modern_boundary_reconstruction=False))
        credit.append(dict(scope_id=scope,source_record_id=row.source_record_id,year=int(row.census_year),source_population=row.population,
            new_population_on_separate_transformation_path_axis=row.population,own_historical_point_verified=True,receiving_city_actual_2002_2010_2021_context_verified=True,
            is_additive_to_original_final_mixed_census_axis=False,ordinary_three_census_same_place_claim=False))
        raw_path=Path('/workspace/settlements-raw')/row.source_file;pins[str(raw_path)]=sha(raw_path)
        if row.census_year==2002:
            sheet=xlrd.open_workbook(str(raw_path)).sheet_by_index(0);rn=int(row.source_record_id.rsplit(':',1)[1]);values=sheet.row_values(rn-1)
            assert float(values[1])==row.population and 'Куровской' in values[0];literal=json.dumps(values,ensure_ascii=False);raw_locator=f'0!row_1based={rn}'
        else:
            output=subprocess.check_output(['pdftotext','-f','26','-l','26','-layout',str(raw_path),'-']).decode()
            values=[line for line in output.splitlines() if 'Куровской' in line]
            assert len(values)==1 and '3207' in values[0].replace(' ','');literal=json.dumps(values,ensure_ascii=False);raw_locator='PDFpage26;Table5;Куровской'
        rawchecks.append(dict(source_record_id=row.source_record_id,census_year=int(row.census_year),source_path=str(raw_path),source_sha256=sha(raw_path),
            source_locator=raw_locator,raw_row_json=literal,raw_population=row.population,matches_selected_population=True,native_population_quality=row.population_value_quality))
    for row in receiver.itertuples():
        point=json.loads(row.existing_own_point_json);assert point
        contexts.append(dict(scope_id=scope,recipient_city='Калуга',census_year=int(row.census_year),source_record_id=row.source_record_id,population=row.population,
            population_value_quality=row.population_value_quality,latitude=point['latitude'],longitude=point['longitude'],point_ledger_path=point['point_ledger_path'],
            is_receiving_city_context_only=True,new_national_credit_population=0,child_count_substituted=False))
    events=[dict(scope_id=scope,former_locality='Куровской',recipient_city='Калуга',event_date='2012',date_precision='year',relation='included_in',same_place=False,
        event_source_file=str(source),event_source_sha256=sha(source),event_source_locator=locator,primary_law_source_reopened=False,roster_closed=False,
        native_historical_observations=2,receiving_city_actual3year_context=True,event_date_role='Secondary own article microdistrict_since2012 and former PGT period; cited2012 municipal act not asserted exact legal-operative physical inclusion day')]
    ranked=[]
    for p,path in pages:
        title=p['title'];base=normalize(title.split(' (')[0]);matches=rank[rank.settlement_name.map(normalize).eq(base)]
        body=p.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('*','')
        if 'missing' in p:status='held_missing_qualified_own_article'
        elif 'Неоднозначность' in body:status='held_disambiguation_not_own_NP_proof'
        elif title=='Газ-Сале':status='held_post2021_inclusion2025_does_not_explain_census2021_absence'
        elif title=='Донское (Светлогорский городской округ)':status='separate_ordinary_candidate_explicit2018_PGT_to_rural_change_no_included_in'
        elif re.search(r'включ[её]|присоедин[её]|упраздн[её]',body.lower()):status='held_municipal_or_other_object_event_or_no_uncredited_bound2010_target'
        else:status='held_own_NP_article_no_literal_dated_absorption'
        ranked.append(dict(own_article_title=title,source_file=str(path),source_sha256=sha(path),status=status,
            matching_remaining2010_source_IDs_json=json.dumps(matches.source_record_id.tolist()),remaining2010_population=int(matches.population.sum()),
            source_pageid=p.get('pageid',''),source_revid=p.get('revisions',[{}])[0].get('revid','')))
    ranked.append(dict(own_article_title='Куровской',source_file=str(source),source_sha256=sha(source),status='positive_secondary_direct_included_in_candidate',
        matching_remaining2010_source_IDs_json=json.dumps(child[child.census_year.eq(2010)].source_record_id.tolist()),remaining2010_population=3207,source_pageid=page['pageid'],source_revid=page['revisions'][0]['revid']))
    for name,rows in [('candidate_historical_observations.csv',observations),('candidate_former_locality_own_points.csv',points),
        ('candidate_included_in_event_edges.csv',edges),('candidate_inclusion_events.csv',events),('candidate_direct_event_native_credit_union.csv',credit),
        ('actual_receiving_city_three_census_context.csv',contexts),('actual_native_raw_reopenings.csv',rawchecks),('ranked_positive_and_held.csv',ranked)]:
        pd.DataFrame(rows).to_csv(OUT/name,index=False)
    pd.DataFrame([r for r in ranked if not r['status'].startswith('positive')]).to_csv(OUT/'held_targets.csv',index=False)
    (OUT/'literal_own_inclusion_source_excerpts.txt').write_text('\n'.join(line for line in text.splitlines() if '2012' in line or 'Калуг' in line)+'\n')
    result=dict(status='frozen_bounded_actual51_direct_lifecycle_candidate_root_review_pending',baseline_stage=51,
        actual_uncredited2010_native_population=1027304,own_title_network_budget=50,normal_TLS_API_calls=2,
        positive_events=1,historical_native_observations=2,receiving_context_observations=3,
        conditional_separate_direct_plus_formation_native_UID_net={'2002':3689,'2010':3207,'2021':0},
        ordinary_identity_edges=0,ordinary_point_uses=0,child2021_counts_created=False,receiving_population_substitution=False,
        original_final_mixed_census_population_delta={'2002':0,'2010':0,'2021':0},
        source_populations_quality_unchanged=True,all_prior38_events_and_formation_native_UID_credits_excluded=True,
        requested20_to60_positive_events_or_gt30000_2010_gain_evidenced=False,
        limitations='Bounded mass screen yields one additional direct event; most own pages describe continuing NPs, missing qualified titles, municipal-only changes or a post2021 event. No inferred absorption from absence. Cited municipal2012 act is not asserted exact physical/legal-operative inclusion day.',
        input_pins=pins,output_pins={p.name:sha(p) for p in OUT.glob('*.csv')},code_sha256=sha(Path(__file__)))
    (OUT/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','positive_events','historical_native_observations','conditional_separate_direct_plus_formation_native_UID_net']}))
if __name__=='__main__':main()

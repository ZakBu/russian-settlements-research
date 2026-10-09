"""Integrate accepted lifecycle coverage by native UID, without identity unions."""
from pathlib import Path
import argparse, gzip, hashlib, json
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
CONTROLS = {2002: 145166731, 2010: 142856536, 2021: 144699673}
CENSUS_DATES = {2002: '2002-10-09', 2010: '2010-10-14', 2021: '2021-10-01'}

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def yes(x):
    return str(x).lower() in {'true', '1'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state-dir', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--full-output', required=True)
    args = ap.parse_args()
    state, out, full = map(Path, [args.state_dir, args.output, args.full_output])
    out.mkdir(parents=True, exist_ok=True)
    full.mkdir(parents=True, exist_ok=True)
    pins = {}
    def read(p, **kw):
        p = Path(p); pins[str(p)] = {'sha256': sha(p), 'bytes': p.stat().st_size}
        return pd.read_parquet(p, **kw) if p.suffix == '.parquet' else pd.read_csv(p, keep_default_na=False, **kw)
    obs = read(state/'applied_state_observations.parquet')
    assert obs.source_record_id.is_unique
    original_hash = sha(state/'applied_state_observations.parquet')
    overlay = read(ROOT/'publication/stage71/applied_primary_population_source_overlay_2010.csv.gz').set_index('original_source_record_id')
    assert overlay.index.is_unique
    obs['effective_population'] = obs.population
    obs['effective_population'] = obs.source_record_id.map(overlay.population).combine_first(obs.effective_population)
    native = obs.set_index('source_record_id')
    points = read(state/'applied_point_snapshot.parquet', columns=['target_source_record_id', 'latitude', 'longitude', 'coordinate_admission_status'])
    assert points.target_source_record_id.is_unique
    pointids = set(points.target_source_record_id)
    seed = read(E/'over500_root_20261009/current_target_confirmed_union/confirmed_credited_UID_roster.csv.gz')
    assert seed.source_record_id.is_unique
    ids = set(seed.source_record_id)
    assert ids <= set(native.index)
    routes, edges, events, availability = [], [], [], []
    def verify_event_source(row):
        p = Path(row['event_source_file'])
        pins[str(p)] = {'sha256': sha(p), 'bytes': p.stat().st_size}
        assert pins[str(p)]['sha256'] == row['event_source_sha256']
        assert row.get('event_source_locator') and row.get('event_date')
    def admit(sid, scope, kind, source_packet):
        assert sid in native.index and sid in pointids, (sid, 'actual observation and ownpoint required')
        r = native.loc[sid]
        assert pd.notna(r.population) and float(r.population) >= 0
        assert yes(r.is_additive_settlement_record)
        assert r.region_norm not in {'москва', 'санкт петербург', 'севастополь', 'крым'}
        routes.append(dict(source_record_id=sid, scope_id=scope, route_kind=kind, source_packet=str(source_packet),
                           census_year=int(r.census_year), effective_population=float(r.effective_population),
                           already_in_seed=sid in ids, graph_union_allowed=False, recipient_count_assigned=False))
    for p in sorted(E.glob('over500*/**/accepted_direct_event_native_credit_union.csv')):
        claims = read(p); ep = p.parent/'accepted_included_in_event_edges.csv'
        ef = read(ep)
        event_table = read(p.parent/'accepted_inclusion_events.csv')
        for row in event_table.to_dict('records'):
            verify_event_source(row)
            assert row['relation'] in {'included_in', 'merged_into'} and not yes(row['same_place'])
            events.append(dict(row, integration_source_packet=str(p.parent/'accepted_inclusion_events.csv')))
        for claim in claims.to_dict('records'):
            sid = claim['source_record_id']
            assert yes(claim['own_historical_point_verified'])
            receiver_fields = [k for k in claim if k.startswith('receiving_city_actual')]
            assert receiver_fields and all(yes(claim[k]) for k in receiver_fields)
            matches = ef[ef.from_source_record_id.eq(sid)]
            assert len(matches) == 1, (p, sid)
            row = matches.iloc[0].to_dict(); verify_event_source(row)
            assert row['relation'] in {'included_in', 'merged_into'} and not yes(row['same_place']) and not yes(row['graph_union_allowed'])
            recipient = row['to_source_record_id']
            assert recipient in native.index and recipient in pointids
            assert int(native.loc[sid, 'census_year']) == int(claim['year'])
            assert float(native.loc[sid, 'population']) == float(claim['source_population'])
            assert int(native.loc[recipient, 'census_year']) > int(native.loc[sid, 'census_year'])
            admit(sid, claim['scope_id'], 'dated_' + row['relation'] + '_actual_donor', p)
            edges.append(dict(row, integration_source_packet=str(ep)))
    east = E/'over500_east_20261009/subbatch3'
    for row in read(east/'accepted_typed_lifecycle_event_delta.csv').to_dict('records'):
        verify_event_source(row)
        assert row['relation'] == 'settlement_abolished' and row['decision_status'].startswith('accepted_')
        events.append(dict(row, integration_source_packet=str(east/'accepted_typed_lifecycle_event_delta.csv')))
        for sid in row['affected_source_uids'].split('|'):
            assert int(native.loc[sid, 'census_year']) < int(row['event_date'][:4])
            admit(sid, row['scope_id'], 'dated_abolition_actual_observed_year', east/'accepted_typed_lifecycle_event_delta.csv')
    # A corrected Naro-Fominsk pair has explicit 2012 transfer to Moscow,
    # independently of the rejected Dmitrov full3. Federal totals are not added again.
    source = E/'over500_moscow_20261009/batch7_postnikov_diagnostic/Postnikovo_both_qualified_own_articles.json.gz'
    pins[str(source)] = {'sha256': sha(source), 'bytes': source.stat().st_size}
    article = json.load(gzip.open(source, 'rt'))['query']['pages']['4502517']
    rev = article['revisions'][0]
    text = rev['slots']['main']['*']; literal = text.splitlines()[40]
    assert 'до 1 июля 2012 года' in literal and 'Наро-Фоминский' in literal
    pair = ['2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:3616',
            '2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11384']
    assert native.loc[pair[0], 'root'] == native.loc[pair[1], 'root']
    scope = 'postnikovo_naro_federal_transfer_2012'
    federal_event = dict(scope_id=scope, relation='territorial_jurisdiction_transfer_to_federal_subject',
                         event_date='2012-07-01', date_precision='day_stated_in_secondary_article',
                         event_source_file=str(source), event_source_sha256=sha(source),
                         event_source_locator=f"page4502517:revision{rev['revid']}:line40", same_place=False,
                         graph_union_allowed=False, recipient_population_assigned_to_child=False)
    events.append(federal_event)
    for sid in pair:
        admit(sid, scope, 'actual_two_year_pair_federal_transfer', source)
    # Reconcile the donor timeline without changing frozen generic UNKNOWN files.
    # Later recipient counts supply context only; jurisdiction transfer does not
    # imply the disappearance of the physical settlement.
    effective_statuses = []
    for scope, group in pd.DataFrame(routes).groupby('scope_id'):
        matching = [r for r in events if r['scope_id'] == scope]
        assert len(matching) == 1, (scope, len(matching))
        event = matching[0]
        event_date = str(event['event_date'])
        donated = native.loc[group.source_record_id]
        assert not donated.census_year.duplicated().any()
        for year in CONTROLS:
            actual = donated[donated.census_year.eq(year)]
            if len(actual):
                sid = actual.index[0]; status = 'actual_own_observed_census_year'
                population = actual.iloc[0].population
            elif (year > int(event_date[:4]) if len(event_date) == 4 else event_date < CENSUS_DATES[year]):
                sid = ''; population = None
                status = ('federal_territory_total_only_child_own_count_UNKNOWN' if event['relation'].startswith('territorial_')
                          else 'not_applicable_as_separate_locality_after_dated_' + event['relation'])
            else:
                sid = ''; population = None
                status = ('UNKNOWN_event_year_timing_and_own_count' if len(event_date) == 4 and year == int(event_date)
                          else 'UNKNOWN_missing_own_observation_no_zero_or_birth_inference')
            effective_statuses.append(dict(scope_id=scope, census_year=year, status=status,
                                           source_record_id=sid, own_population=population,
                                           recipient_population_assigned_to_child=False, unknown_is_zero=False,
                                           boundary_comparability='UNKNOWN', event_relation=event['relation'],
                                           event_date=event['event_date'], event_source_sha256=event['event_source_sha256']))
    for p in sorted(E.glob('over500*/**/accepted*statuses.csv')):
        for row in read(p).to_dict('records'):
            availability.append(dict(source_packet=str(p), original_row_json=json.dumps(row, ensure_ascii=False)))
    routeframe = pd.DataFrame(routes)
    assert not routeframe.duplicated(['source_record_id', 'scope_id', 'route_kind']).any()
    added = set(routeframe.source_record_id) - ids
    finalids = ids | set(routeframe.source_record_id)
    credited = obs[obs.source_record_id.isin(finalids)].copy()
    assert credited.source_record_id.is_unique and len(credited) == len(finalids)
    assert not credited.region_norm.isin(['москва', 'санкт петербург', 'севастополь', 'крым']).any()
    scopes = read(state/'accepted_large_record_scope_classification_overlay.csv')
    ordinary = obs[obs.is_additive_settlement_record.fillna(False) & ~obs.region_norm.isin(['москва','санкт петербург','севастополь','крым']) & ~obs.source_record_id.isin(scopes.source_record_id)].copy()
    ordinary['ownpoint'] = ordinary.source_record_id.isin(pointids)
    ordinary['finite'] = ordinary.population.notna()
    stats = ordinary.groupby('root').agg(n=('source_record_id','size'), yrs=('census_year','nunique'), points=('ownpoint','all'), finite=('finite','all'))
    fullroots = set(stats[(stats.n.eq(3)) & (stats.yrs.eq(3)) & stats.points & stats.finite].index)
    assert len(fullroots) == 142696
    credited['component_root'] = credited.root
    credited['finite_ordinary_full3_all_ownpoints'] = credited.root.isin(fullroots)
    credited['point_presence'] = credited.source_record_id.isin(pointids)
    credited['new_lifecycle_integration_credit'] = credited.source_record_id.isin(routeframe.source_record_id)
    route_map = routeframe.groupby('source_record_id').route_kind.agg(lambda x: '|'.join(sorted(set(x))))
    credited['new_lifecycle_route_kind'] = credited.source_record_id.map(route_map).fillna('')
    credited['retained_stage71_or_new_full3_seed_credit'] = credited.source_record_id.isin(ids)
    credited['effective_population_has_primary2010_override'] = credited.source_record_id.isin(overlay.index)
    credited['effective_population_override_origin_sha256'] = credited.source_record_id.map(
        lambda sid: pins[str(ROOT/'publication/stage71/applied_primary_population_source_overlay_2010.csv.gz')]['sha256'] if sid in overlay.index else '')
    fed = read(ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv')
    assert len(fed) == 6 and not fed.duplicated(['territory_key','census_year']).any()
    assert not finalids & set(fed.population_source_record_id)
    coverage = []
    for year, den in CONTROLS.items():
        rows = credited[credited.census_year.eq(year)]
        federal = int(fed.loc[fed.census_year.eq(year), 'territory_population'].sum())
        num = int(rows.effective_population.sum()) + federal
        seedpop = int(seed.loc[pd.to_numeric(seed.census_year).eq(year), 'effective_population'].sum()) + federal
        gain = int(credited.loc[credited.census_year.eq(year) & credited.source_record_id.isin(added), 'effective_population'].sum())
        assert num == seedpop + gain
        coverage.append(dict(year=year, population=num, denominator=den, percent=100*num/den,
                             remaining_population=den-num, integration_gain_population=gain,
                             integration_gain_UIDs=int((credited.census_year.eq(year)&credited.source_record_id.isin(added)).sum())))
    smallcols = ['source_record_id','census_year','effective_population','component_root','finite_ordinary_full3_all_ownpoints','point_presence','new_lifecycle_integration_credit','new_lifecycle_route_kind']
    credited[smallcols].to_csv(out/'integrated_credited_UID_roster.csv.gz', index=False, compression={'method':'gzip','mtime':0})
    credited.to_parquet(full/'integrated_primary_population_spatial_temporal_records.parquet', index=False, compression='zstd')
    routeframe.to_csv(out/'applied_new_lifecycle_credit_routes.csv', index=False)
    pd.DataFrame(events).to_csv(out/'applied_typed_lifecycle_events.csv', index=False)
    pd.DataFrame(edges).to_csv(out/'applied_included_in_edges.csv', index=False)
    pd.DataFrame(availability).to_csv(out/'integrated_source_year_status_assertions.csv.gz', index=False, compression={'method':'gzip','mtime':0})
    pd.DataFrame(effective_statuses).to_csv(out/'effective_lifecycle_available_year_statuses.csv', index=False)
    pd.DataFrame(coverage).to_csv(out/'coverage.csv', index=False)
    assert sha(state/'applied_state_observations.parquet') == original_hash
    receipt = dict(status='applied_lifecycle_union_not_lower_bound_for_these_packets', input_state='fifteenth_application',
                   credited_native_UIDs=len(finalids), accepted_route_UIDs=routeframe.source_record_id.nunique(),
                   added_UIDs=len(added), already_credited_UIDs=routeframe.source_record_id.nunique()-len(added),
                   typed_inclusion_edge_rows=len(edges), typed_event_rows=len(events),
                   ordinary_full3_components_unchanged=len(fullroots), coverage=coverage, input_pins=pins,
                   raw_counts_qualities_and_identity_components_unchanged=True,
                   recipient_population_not_added_or_assigned_to_children=True, unknown_not_zero=True,
                   revoked_false_full3_not_restored_as_full3=True, unresolved_generic_missing_year_not_credited=True,
                   full_output={'path':str(full/'integrated_primary_population_spatial_temporal_records.parquet'), 'sha256':sha(full/'integrated_primary_population_spatial_temporal_records.parquet')})
    (out/'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'input_pins','full_output'}}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

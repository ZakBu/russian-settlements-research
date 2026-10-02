import gzip
import json

import pandas as pd

from research_rebuild.mass_linkage.wide_wikidata_bindings import (
    build,
    parse_point,
    read_truthy,
    read_tsv,
    rdf_text,
)


def test_rdf_literal_and_wgs84_wkt_parsing():
    assert rdf_text('"Село Ёлкино"@ru') == 'Село Ёлкино'
    assert rdf_text('"123"^^<http://www.w3.org/2001/XMLSchema#string>') == '123'
    assert parse_point('POINT(-175.5 67.2)') == (67.2, -175.5)
    assert parse_point('POINT(181 20)') == (None, None)


def test_tsv_index_keeps_raw_values_and_qid_competition(tmp_path):
    path = tmp_path / 'evidence.tsv'
    path.write_text(
        '?item\t?oktmo\t?okato\t?coord\t?label\t?article\t?admin\t?adminLabel\n'
        '<http://www.wikidata.org/entity/Q10>\t"012345"\t"777"\tPOINT(-175 67)\t"Село Ёлкино"@ru\t<https://ru.wikipedia.org/wiki/X>\t<http://www.wikidata.org/entity/Q2>\t"Чукотка"@ru\n'
        '<http://www.wikidata.org/entity/Q11>\t"012345"\t"777"\t\t"Другое"@ru\t\t\t\n',
        encoding='utf-8',
    )
    index, meta = read_tsv(path)
    assert set(index) == {'012345'}
    assert len(index['012345']) == 2
    assert index['012345'][0]['label_ru'] == 'Село Ёлкино'
    assert index['012345'][0]['admin_qid'] == 'Q2'
    assert meta['codes_linking_multiple_qids'] == 1


def test_truthy_cache_exact_code_and_point_lineage(tmp_path):
    batch = tmp_path / 'batch_0000.jsonl.gz'
    rows = [
        {'item': 'http://www.wikidata.org/entity/Q10', 'property': 'http://www.wikidata.org/entity/P764', 'value': '012345', 'retrieved_at_utc': '2026-08-31T00:00:00Z'},
        {'item': 'http://www.wikidata.org/entity/Q10', 'property': 'http://www.wikidata.org/entity/P721', 'value': '777', 'retrieved_at_utc': '2026-08-31T00:00:00Z'},
        {'item': 'http://www.wikidata.org/entity/Q10', 'property': 'http://www.wikidata.org/entity/P625', 'value': 'POINT(-175 67)', 'retrieved_at_utc': '2026-08-31T00:00:00Z'},
        {'item': 'http://www.wikidata.org/entity/Q11', 'property': 'http://www.wikidata.org/entity/P764', 'value': '12345', 'retrieved_at_utc': '2026-08-31T00:00:00Z'},
    ]
    with gzip.open(batch, 'wt', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')
    p764, p721, info, summary, hashes = read_truthy(tmp_path, {'012345': [0]}, {'777': [0]}, pd.DataFrame())
    assert set(p764['012345']) == {'Q10'}
    assert set(p721['777']) == {'Q10'}
    assert info['Q10']['P625'][0]['latitude'] == 67
    assert info['Q10']['P625'][0]['longitude'] == -175
    assert summary['truthy_exact_p764_candidate_qids'] == 1
    assert hashes[0]['path'].endswith('batch_0000.jsonl.gz')


def test_build_is_exact_code_candidate_only_and_keeps_point_lineage(tmp_path):
    selected = tmp_path / 'selected.parquet'
    pd.DataFrame([
        {'census_year': 2021, 'source_record_id': 's1', 'source_row': 1, 'oktmo': '012345', 'okato': '777',
         'settlement_name': 'Село Ёлкино', 'source_name_raw': 'Село Ёлкино', 'settlement_type': 'село',
         'region_raw': 'Чукотка', 'district_raw': None, 'municipality_raw': None, 'population': 25,
         'population_scope': 'settlement', 'latitude': 67.0, 'longitude': -175.0},
        {'census_year': 2021, 'source_record_id': 's2', 'source_row': 2, 'oktmo': '12345', 'okato': '777',
         'settlement_name': 'Село Ёлкино', 'source_name_raw': 'Село Ёлкино', 'settlement_type': 'село',
         'region_raw': 'Чукотка', 'district_raw': None, 'municipality_raw': None, 'population': 26,
         'population_scope': 'settlement', 'latitude': 67.0, 'longitude': -175.0},
    ]).to_parquet(selected, index=False)
    tsv = tmp_path / 'evidence.tsv'
    tsv.write_text(
        '?item\t?oktmo\t?okato\t?coord\t?label\t?article\t?admin\t?adminLabel\n'
        '<http://www.wikidata.org/entity/Q10>\t"012345"\t"777"\tPOINT(-175 67)\t"Село Ёлкино"@ru\t\t<http://www.wikidata.org/entity/Q2>\t"Чукотка"@ru\n',
        encoding='utf-8',
    )
    module = tmp_path / 'module.jsonl.gz'
    with gzip.open(module, 'wt', encoding='utf-8') as stream:
        stream.write(json.dumps({'item': 'http://www.wikidata.org/entity/Q10', 'coord': 'POINT(-175 67)'}) + '\n')
    ledger = tmp_path / 'ledger.parquet'
    pd.DataFrame([
        {'source_record_id': 's1', 'provider_latitude': 67.0, 'provider_longitude': -175.0,
         'raw_oktmo_dadata': '012345.0', 'raw_fias_id_dadata': 'uuid1', 'raw_fias_level_dadata': '6',
         'raw_object_level': 'Населенный пункт', 'raw_settlement_dadata': 'Село Ёлкино',
         'raw_settlement_type_full_dadata': 'село', 'provider_general_fias_duplicate_count': 1,
         'provider_coordinate_duplicate_count': 1, 'baseline_provider_coordinate_conflict': False,
         'provider_name_exact_selected_name': True, 'provider_type_exact_selected_type': True},
        {'source_record_id': 's2', 'provider_latitude': 67.0, 'provider_longitude': -175.0,
         'raw_oktmo_dadata': '012345', 'raw_fias_id_dadata': 'uuid2', 'raw_fias_level_dadata': '6',
         'raw_object_level': 'Населенный пункт', 'raw_settlement_dadata': 'Село Ёлкино',
         'raw_settlement_type_full_dadata': 'село', 'provider_general_fias_duplicate_count': 1,
         'provider_coordinate_duplicate_count': 1, 'baseline_provider_coordinate_conflict': False,
         'provider_name_exact_selected_name': True, 'provider_type_exact_selected_type': True},
    ]).to_parquet(ledger, index=False)
    summary = build(selected, tsv, module, ledger, tmp_path / 'out')
    result = pd.read_parquet(tmp_path / 'out' / 'wide_point_bindings.parquet')
    assert result.source_record_id.tolist() == ['s1']  # no zero-pad fuzzy binding for s2
    assert bool(result.wikidata_name_exact_label.iloc[0])
    assert bool(result.wikidata_admin_context_available.iloc[0])
    assert result.tsv_distinct_point_count.iloc[0] == 1
    assert result.module_point_count_raw.iloc[0] == 1
    assert bool(result.wikimedia_point_sources_same_qid_overlap.iloc[0])
    assert result.identity_admission.eq(False).all()
    assert result.coordinate_admission.eq(False).all()
    assert summary['source_rows_with_any_exact_tsv_p764_candidate'] == 1
    code_screen = pd.read_parquet(tmp_path / 'out' / 'provider_code_candidate_screen.parquet').set_index('source_record_id')
    assert bool(code_screen.loc['s1', 'source_provider_oktmo_exact_match'])  # terminal .0 only
    assert not bool(code_screen.loc['s2', 'source_provider_oktmo_exact_match'])  # never zero-pad
    assert bool(code_screen.loc['s1', 'strict_named_type_provider_code_candidate'])
    assert not bool(code_screen.loc['s1', 'coordinate_or_identity_admission'])

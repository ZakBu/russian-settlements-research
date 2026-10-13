"""Attach verified source provenance to staged and accepted point uses.

This is a provenance normalization pass only. It never changes point-use status,
coordinates, admission decisions, or source-era claims. Raw asset hashes and exact
source row/claim locators are kept separate from auxiliary proof artifacts.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

ROOT = Path('/workspace')
DEFAULT_INPUT = ROOT / 'settlements-work/coordinates/extension_application_v2/staged_proposed_point_uses.parquet'
DEFAULT_ACCEPTED = ROOT / 'settlements-work/coordinates/accepted_modern_v1/accepted_point_uses.parquet'
DEFAULT_FROZEN = ROOT / 'settlements-work/coordinates/admission_staging_v1/frozen_r5b_coordinate_admissions.csv'
DEFAULT_OUT = ROOT / 'settlements-work/coordinates/normalized_extension_v2'
GEO_RAW = ROOT / 'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
GEO_PARSED = ROOT / 'settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet'
DADATA_RAW = ROOT / 'settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
WIKI_DIR = ROOT / 'settlements-raw/data/raw/wikidata_truthy_claims'
FROZEN_SHA = 'c58'  # Full digest is computed and asserted by the frozen input manifest/review receipt.
GEO_SHA = 'd1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650'
GEO_PARSED_SHA = 'c778b841d22a65ac01a8658957044b66390bc32fe7f095cb2ca38489858ce17f'
DADATA_SHA = '86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'

ORIGIN_COLUMNS = ['point_origin_file', 'point_origin_sha256', 'point_origin_locator', 'point_origin_kind',
                  'point_claim_artifact_file', 'point_claim_artifact_sha256']


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


def _num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def exact_point(a_lat: Any, a_lon: Any, b_lat: Any, b_lon: Any) -> bool:
    a, b, c, d = map(_num, (a_lat, a_lon, b_lat, b_lon))
    return None not in (a, b, c, d) and a == c and b == d


def decoded_locator(value: Any) -> list[str]:
    """Extract batch:line tokens despite historical JSON strings nested as strings."""
    result: list[str] = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, str):
            m = re.search(r'(batch_\d{4}\.jsonl\.gz)\s*:\s*(\d+)', item)
            if m:
                result.append(f'{m.group(1)}:{int(m.group(2))}')
            try:
                parsed = json.loads(item)
            except Exception:
                continue
            if isinstance(parsed, (dict, list)):
                pending.append(parsed)
    return sorted(set(result))


def p625_values(entity: dict[str, Any]) -> list[tuple[float, float]]:
    found = []
    # The frozen truthy-claims export is one JSON record per entity/property,
    # with GeoJSON-like WKT strings rather than a Wikibase claims object.
    if str(entity.get('property', '')).endswith('/P625'):
        value = entity.get('value')
        if isinstance(value, str):
            match = re.fullmatch(r'POINT\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)', value)
            if match:
                try:
                    found.append((float(match.group(2)), float(match.group(1))))
                except ValueError:
                    pass
    claims = entity.get('claims', {}).get('P625', [])
    for claim in claims:
        try:
            val = claim['mainsnak']['datavalue']['value']
            found.append((float(val['latitude']), float(val['longitude'])))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def verify_wiki_line(line: str, lat: Any, lon: Any) -> bool:
    try:
        entity = json.loads(line)
    except Exception:
        return False
    target = (_num(lat), _num(lon))
    if target[0] is None or target not in p625_values(entity):
        return False
    return True


def make_origin(file: str, sha: str, locator: str, kind: str,
                artifact_file: str = '', artifact_sha: str = '') -> dict[str, str]:
    return dict(zip(ORIGIN_COLUMNS, [file, sha, locator, kind, artifact_file, artifact_sha]))


def geokladr_origin(raw_file: str, raw_sha: str, parsed_file: str, parsed_sha: str,
                    record_number: int, byte_offset: int) -> dict[str, str]:
    return make_origin(raw_file, raw_sha,
        f'raw_dbf_record_number_1based={int(record_number)};byte_offset_0based={int(byte_offset)}',
        'geokladr_2011_raw_dbf_coordinate', parsed_file, parsed_sha)


def retrospective_origin(carrier: dict[str, str], carrier_id: str,
                         use_lat: Any, use_lon: Any, carrier_lat: Any, carrier_lon: Any) -> dict[str, str]:
    if not exact_point(use_lat, use_lon, carrier_lat, carrier_lon):
        raise ValueError('retrospective point differs from accepted modern carrier')
    out = dict(carrier)
    out['point_origin_kind'] = 'retrospective_continuity_from_' + carrier['point_origin_kind']
    out['point_origin_locator'] = f'carrier_target_source_record_id={carrier_id};' + carrier['point_origin_locator']
    return out


def frozen_origin(csv_file: str, csv_sha: str, target_id: str, decision_id: str,
                  review_source_locator: str) -> dict[str, str]:
    return make_origin('', '',
        f'frozen_target_source_record_id={target_id};decision_id={decision_id};review_source_locator={review_source_locator}',
        'reviewed_frozen_assertion', csv_file, csv_sha)


def _point_index(frame: pd.DataFrame) -> dict[str, Any]:
    return {str(r.target_source_record_id): r for r in frame.itertuples(index=False)}


def _source_token(record_id: Any) -> int:
    m = re.search(r':parquet:(\d+)$', _text(record_id))
    if not m:
        raise ValueError(f'cannot extract one-based provider row from {record_id!r}')
    return int(m.group(1))


def normalize(input_path: Path = DEFAULT_INPUT, accepted_path: Path = DEFAULT_ACCEPTED,
              frozen_path: Path = DEFAULT_FROZEN, output_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f'output directory is not empty: {output_dir}')
    staged = pd.read_parquet(input_path)
    original_columns = list(staged.columns)
    accepted = pd.read_parquet(accepted_path)
    modern = _point_index(accepted)
    frozen = pd.read_csv(frozen_path)
    if frozen.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('frozen baseline contains duplicate target keys')
    frozen_by_target = {str(r.target_source_record_id): r for r in frozen.itertuples(index=False)}
    if set(ORIGIN_COLUMNS) & set(original_columns):
        raise ValueError('input already contains canonical point origin columns')

    # Hash each underlying asset once. The parsed GeoKLADR parquet is a traceable
    # auxiliary artifact; the point origin itself is the raw DBF.
    geo_sha = sha256_file(GEO_RAW)
    dadata_sha = sha256_file(DADATA_RAW)
    frozen_sha = sha256_file(frozen_path)
    geo_aux_sha = sha256_file(GEO_PARSED)
    expected = [(geo_sha, GEO_SHA, 'GeoKLADR DBF'), (dadata_sha, DADATA_SHA, 'Tochno parquet'),
                (geo_aux_sha, GEO_PARSED_SHA, 'GeoKLADR parsed auxiliary')]
    for actual, wanted, label in expected:
        if actual != wanted:
            raise ValueError(f'{label} SHA-256 mismatch: {actual}')
    if not frozen_sha.startswith(FROZEN_SHA):
        raise ValueError(f'frozen baseline CSV SHA does not match the expected c58… prefix: {frozen_sha}')

    # Parse the frozen DBF bytes once and verify every GeoKLADR use against its
    # exact 1-based record and exact numeric coordinate pair.
    from research_rebuild.mass_linkage.verify_geokladr_snapshot import parse_dbf_records
    _, geo_records = parse_dbf_records(GEO_RAW)
    staged_origins: list[dict[str, str]] = []
    wiki_targets: dict[str, set[int]] = {}
    wiki_row_map: dict[int, list[int]] = {}
    moscow_claim: dict[str, Any] = {}
    moscow_batches: set[str] = set()
    for idx, row in staged.iterrows():
        family = _text(row.get('coordinate_application_family'))
        if family.startswith(('F_', 'A_')):
            loc = json.loads(_text(row['coordinate_source_locator']))
            recno = int(loc['record_number_1based'])
            byteoff = int(loc['record_byte_offset_0based'])
            if recno < 1 or recno > len(geo_records):
                raise ValueError(f'GeoKLADR record number out of range at staged row {idx}')
            raw = geo_records[recno - 1]
            if int(raw['record_byte_offset_0based']) != byteoff or not exact_point(row.latitude, row.longitude,
                                                                                   raw['latitude_from_lat'], raw['longitude_from_long']):
                raise ValueError(f'GeoKLADR raw coordinate/locator mismatch at staged row {idx}')
            staged_origins.append(geokladr_origin(str(GEO_RAW), geo_sha, str(GEO_PARSED), geo_aux_sha, recno, byteoff))
        elif family.startswith('R_'):
            carrier_id = _text(row.get('inference_modern_point_use_target_source_record_id'))
            carrier = modern.get(carrier_id)
            if carrier is None or not exact_point(row.latitude, row.longitude, carrier.latitude, carrier.longitude):
                raise ValueError(f'retrospective point has no exact accepted modern carrier at staged row {idx}')
            # Carrier's source kind is resolved below from its direct source claim.
            staged_origins.append({})
        elif family.startswith('M_'):
            loc = _text(row.get('coordinate_source_locator'))
            m = re.search(r'(batch_\d{4}\.jsonl\.gz)#line[_:]?(\d+)', loc)
            if not m:
                raise ValueError(f'Moscow Wikidata locator malformed: {loc}')
            batch, line_no = m.group(1), int(m.group(2))
            wiki_targets.setdefault(batch, set()).add(line_no)
            wiki_row_map.setdefault(idx, []).append(line_no)
            moscow_claim[str(idx)] = (batch, line_no)
            moscow_batches.add(batch)
            staged_origins.append({})
        elif not family:
            # Original accepted rows are independently compared with frozen R5b below.
            staged_origins.append({})
        else:
            raise ValueError(f'unhandled point application family {family!r}')

    # Prepare all modern direct claims. Provider parquet uses one-based row IDs.
    dadata_rows: dict[int, tuple[float, float]] = {}
    wiki_point_targets: dict[str, dict[int, list[tuple[float, float, str]]]] = {}
    for rec_id, row in modern.items():
        provider = _text(getattr(row, 'coordinate_provider', ''))
        if provider == 'tochno_dadata':
            n = _source_token(getattr(row, 'coordinate_source_record_id'))
            dadata_rows[n] = (_num(row.latitude), _num(row.longitude))
        elif provider == 'wikidata_p625':
            for token in decoded_locator(getattr(row, 'source_locator')):
                batch, line = token.split(':')
                wiki_targets.setdefault(batch, set()).add(int(line))
                wiki_point_targets.setdefault(batch, {}).setdefault(int(line), []).append(
                    (_num(row.latitude), _num(row.longitude), _text(getattr(row, 'coordinate_provider_id', ''))))

    # Validate provider coordinates by exact 1-based row. Reading only two columns
    # avoids loading the wide census/provider attributes.
    if dadata_rows:
        source_points = pd.read_parquet(DADATA_RAW, columns=['latitude_dadata', 'longitude_dadata'])
        if max(dadata_rows) > len(source_points):
            raise ValueError('Tochno provider row locator beyond raw parquet length')
        for n, point in dadata_rows.items():
            raw = source_points.iloc[n - 1]
            if not exact_point(*point, raw.latitude_dadata, raw.longitude_dadata):
                raise ValueError(f'Tochno raw coordinate mismatch at one-based row {n}')
        del source_points

    # Hash once per used gzip batch and stream each batch once, collecting targeted
    # lines only. P625 equality is exact; no nearest-point fallback is permitted.
    wiki_hashes: dict[str, str] = {}
    wiki_lines: dict[tuple[str, int], str] = {}
    moscow_physical_city_p31: set[str] = set()
    for batch, wanted in wiki_targets.items():
        path = WIKI_DIR / batch
        if not path.is_file():
            raise FileNotFoundError(path)
        wiki_hashes[batch] = sha256_file(path)
        unmatched = set(wanted)
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line_no, line in enumerate(stream, 1):
                if line_no in unmatched:
                    parsed = json.loads(line)
                    coords = p625_values(parsed)
                    for lat, lon, qid in wiki_point_targets.get(batch, {}).get(line_no, []):
                        if (lat, lon) not in coords or str(parsed.get('item', '')).rsplit('/', 1)[-1] != qid:
                            raise ValueError(f'Wikidata P625 exact coordinate/entity mismatch {batch}:{line_no}: {qid} {(lat, lon)}')
                    wiki_lines[(batch, line_no)] = line
                    unmatched.remove(line_no)
                if batch in moscow_batches and 'Q649' in line and '/P31' in line and 'Q7930989' in line:
                    parsed = json.loads(line)
                    item = str(parsed.get('item', '')).rsplit('/', 1)[-1]
                    prop = str(parsed.get('property', '')).rsplit('/', 1)[-1]
                    value = str(parsed.get('value', '')).rsplit('/', 1)[-1]
                    if item == 'Q649' and prop == 'P31' and value == 'Q7930989':
                        moscow_physical_city_p31.add(batch)
                if not unmatched and batch not in moscow_batches:
                    break
        if unmatched:
            raise ValueError(f'Wikidata source lines not found in {batch}: {sorted(unmatched)[:5]}')

    # Canonical origins for accepted modern points: all 96,335 DaData points and
    # all Wikidata P625 points are checked against raw source bytes/rows.
    modern_origin: dict[str, dict[str, str]] = {}
    for rec_id, row in modern.items():
        provider = _text(getattr(row, 'coordinate_provider', ''))
        base = frozen_by_target.get(rec_id)
        if base is not None:
            if not exact_point(row.latitude, row.longitude, base.latitude, base.longitude):
                raise ValueError(f'frozen R5b target coordinate mismatch: {rec_id}')
            modern_origin[rec_id] = frozen_origin(str(frozen_path), frozen_sha, rec_id,
                _text(base.decision_id), _text(getattr(row, 'source_locator', '')))
        elif provider == 'tochno_dadata':
            n = _source_token(getattr(row, 'coordinate_source_record_id'))
            modern_origin[rec_id] = make_origin(str(DADATA_RAW), dadata_sha,
                f'parquet_row_1based={n};latitude_dadata,longitude_dadata', 'tochno_2021_dadata_raw_parquet_point',
                str(DADATA_RAW), dadata_sha)
        elif provider == 'wikidata_p625':
            token = decoded_locator(getattr(row, 'source_locator'))
            if not token:
                raise ValueError(f'accepted Wikidata point has no source claim locator: {rec_id}')
            batch, line = token[0].split(':')
            modern_origin[rec_id] = make_origin(str(WIKI_DIR / batch), wiki_hashes[batch],
                f'{batch}:line={line};entity={_text(getattr(row, "coordinate_provider_id", ""))};claim=P625',
                'wikidata_truthy_p625_raw_claim', str(WIKI_DIR / batch), wiki_hashes[batch])
        else:
            raise ValueError(f'accepted modern point has unsupported original source: {rec_id} ({provider})')

    # Build each staged row's final fields without modifying the original columns.
    output_origins = []
    for idx, row in staged.iterrows():
        family = _text(row.get('coordinate_application_family'))
        if family.startswith(('F_', 'A_')):
            origin = staged_origins[idx]
        elif family.startswith('R_'):
            carrier_id = _text(row.get('inference_modern_point_use_target_source_record_id'))
            carrier = modern[carrier_id]
            origin = retrospective_origin(modern_origin[carrier_id], carrier_id, row.latitude, row.longitude,
                                          carrier.latitude, carrier.longitude)
        elif family.startswith('M_'):
            loc = _text(row['coordinate_source_locator'])
            m = re.search(r'(batch_\d{4}\.jsonl\.gz)#line[_:]?(\d+)', loc)
            batch, line_no = m.group(1), int(m.group(2))
            path = WIKI_DIR / batch
            # Exact source line was targeted above. Assert point and physical-city
            # class on the cached raw entity line.
            line = wiki_lines.get((batch, line_no), '')
            ent = json.loads(line)
            if not verify_wiki_line(line, row.latitude, row.longitude) or str(ent.get('item', '')).rsplit('/', 1)[-1] != 'Q649':
                raise ValueError('Moscow Wikidata P625 raw point/Q649 mismatch')
            if batch not in moscow_physical_city_p31:
                raise ValueError('Moscow Wikidata raw line lacks reviewed physical-city P31')
            origin = make_origin(str(path), wiki_hashes[batch], f'{batch}:line={line_no};entity=Q649;claim=P625',
                                 'wikidata_truthy_p625_raw_claim', str(path), wiki_hashes[batch])
        else:
            target_id = _text(row.target_source_record_id)
            fr = frozen_by_target.get(target_id)
            if fr is not None:
                if not exact_point(row.latitude, row.longitude, fr.latitude, fr.longitude):
                    raise ValueError(f'frozen R5b target coordinate mismatch: {target_id}')
                origin = frozen_origin(str(frozen_path), frozen_sha, target_id, _text(fr.decision_id), _text(row.source_locator))
            else:
                direct = modern_origin.get(target_id)
                if direct is None or not exact_point(row.latitude, row.longitude,
                                                      modern[target_id].latitude, modern[target_id].longitude):
                    raise ValueError(f'original accepted point has no exact modern direct origin: {target_id}')
                origin = dict(direct)
        output_origins.append(origin)

    origins = pd.DataFrame(output_origins, index=staged.index, columns=ORIGIN_COLUMNS)
    result = pd.concat([staged, origins], axis=1)
    # Semantic roundtrip guard for all input columns.
    if list(result.columns[:len(original_columns)]) != original_columns or not result[original_columns].equals(staged[original_columns]):
        raise AssertionError('normalization changed an original point-use column')
    # Every nonempty asset/hash pair is pinned to the exact same asset bytes.
    hashed: dict[str, str] = {}
    for _, row in result[ORIGIN_COLUMNS].drop_duplicates().iterrows():
        for fcol, hcol in [('point_origin_file', 'point_origin_sha256'), ('point_claim_artifact_file', 'point_claim_artifact_sha256')]:
            path, digest = _text(row[fcol]), _text(row[hcol])
            if path:
                if not digest:
                    raise ValueError(f'canonical source asset has no hash: {path}')
                if path not in hashed:
                    hashed[path] = sha256_file(Path(path))
                if hashed[path] != digest:
                    raise ValueError(f'canonical origin hash/file mismatch: {path}')
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / 'normalized_point_uses.parquet'
    result.to_parquet(out, index=False)
    receipt = {
        'status': 'point_origin_provenance_normalized_no_admissions',
        'input': {'path': str(input_path), 'sha256': sha256_file(input_path), 'rows': len(staged)},
        'accepted_modern': {'path': str(accepted_path), 'sha256': sha256_file(accepted_path), 'rows': len(accepted)},
        'frozen_baseline': {'path': str(frozen_path), 'sha256': frozen_sha, 'rows': len(frozen)},
        'output': {'path': str(out), 'sha256': sha256_file(out), 'rows': len(result)},
        'original_columns_unchanged': True,
        'canonical_source_assets': {'geokladr_raw_dbf': {'path': str(GEO_RAW), 'sha256': geo_sha},
          'geokladr_aux_parsed_artifact': {'path': str(GEO_PARSED), 'sha256': geo_aux_sha},
          'tochno_2021_raw_parquet': {'path': str(DADATA_RAW), 'sha256': dadata_sha},
          'wikidata_batches': {k: v for k, v in sorted(wiki_hashes.items())}},
        'rows_by_point_origin_kind': result.point_origin_kind.value_counts(dropna=False).to_dict(),
        'source_rows_verified': {'geokladr_raw_record_coordinates': sum(_text(x).startswith(('F_', 'A_')) for x in staged.coordinate_application_family.fillna('')),
          'tochno_raw_provider_rows': len(dadata_rows), 'wikidata_exact_p625_claims': sum(map(len, wiki_point_targets.values())) + 1,
          'frozen_reviewed_assertions': len(frozen)},
        'limitations': ['Frozen R5b original point source remains unknown; CSV row and review proof are preserved as an assertion artifact.',
          'Wikidata measurement/query date is unknown and is not inferred.',
          'Retrospective rows link to accepted modern carriers and make no historical measurement claim.',
          'Legacy source_file/source_sha256 and coordinate_source_* fields were preserved unchanged.']}
    (output_dir / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    ap.add_argument('--accepted', type=Path, default=DEFAULT_ACCEPTED)
    ap.add_argument('--frozen', type=Path, default=DEFAULT_FROZEN)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    print(json.dumps(normalize(args.input, args.accepted, args.frozen, args.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

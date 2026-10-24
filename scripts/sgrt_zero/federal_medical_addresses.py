#!/usr/bin/env python3
"""Strict census linkage of F038 actual-care addresses, without geocoding centroids."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.sgrt_mass.match import ReferenceIndex, normalize_name, normalize_district, normalize_region, norm

# Require an explicit locality component; a street/organization name is insufficient.
PLACE = re.compile(r'^(?P<type>город|г|село|с|деревня|д|пос[её]лок(?:\s+городского\s+типа)?|пос|п|пгт|рп|рабочий\s+пос[её]лок|хутор|х|станица|ст-ца|ст|аул|а|слобода|сл|населенный\s+пункт|нп|станция|разъезд|аал|улус|починок|местечко|кордон|заимка|выселки|арбан|стойбище|сумон)(?:\.\s*|\s+)(?P<name>.+)$', re.I)
STREET = re.compile(r'^(?:улица|ул|переулок|пер|проспект|пр-кт|просп|шоссе|ш|дом|дома|проезд|бульвар|тупик|площадь|пл|квартал|кв-л|микрорайон|мкр|набережная|наб)\.?\s', re.I)


def locality_components(address):
    result = []
    # Only comma/semicolon component boundaries; no invented token segmentation.
    for literal in re.split('[,;]', str(address)):
        literal = re.sub(r'^\s*\d{6}\s*', '', literal).strip()
        if STREET.match(literal):
            break
        match = PLACE.match(literal)
        if match:
            name = normalize_name(match['name'])
            if name and re.search('[а-яa-z]', name, re.I) and not re.search(r'\b(?:ул|улица|переулок|проспект)\b', name):
                result.append((norm(match['type']), name))
        # FIAS and some mirrors put locality type after the name.
        else:
            reverse = re.fullmatch(r'(.+?)\s+(город|г|село|с|деревня|д|пос[её]лок|п|пгт|хутор|х)\.?', literal, re.I)
            if reverse:
                result.append((norm(reverse[2]), normalize_name(reverse[1])))
    return list(dict.fromkeys(result))


TYPE_ALIASES = {
 'г':'город','город':'город','с':'село','село':'село','д':'деревня','деревня':'деревня',
 'п':'поселок','пос':'поселок','поселок':'поселок','х':'хутор','хутор':'хутор',
 'ст':'станица','ст ца':'станица','станица':'станица','а':'аул','аул':'аул',
 'сл':'слобода','слобода':'слобода','нп':'населенный пункт','населенный пункт':'населенный пункт',
 'пгт':'пгт','поселок городского типа':'пгт','рабочий поселок':'пгт','рп':'пгт'}


def type_agrees(literal_type, census_type):
    raw_literal = norm(literal_type)
    literal = TYPE_ALIASES.get(raw_literal, raw_literal)
    value = TYPE_ALIASES.get(norm(census_type), norm(census_type))
    if not value:
        return True
    if raw_literal == 'ст':
        return value in {'станция', 'станица'}
    return literal == value


class AddressMatcher:
    def __init__(self, reference):
        self.ref = reference[reference.source_record_id.notna()].copy().reset_index(drop=True)
        self.ref['name_norm'] = self.ref.name.map(normalize_name)
        self.ref['region_norm'] = self.ref.region.map(normalize_region)
        self.ref['district_norm'] = self.ref.district.map(normalize_district)
        self.index = ReferenceIndex(self.ref)
        self.names = defaultdict(list)
        for i, row in self.ref.iterrows():
            self.names[(row.region_norm, row.name_norm)].append(i)

    def one(self, address):
        result = {'source_record_id': None, 'np_identity_basis': 'unresolved_actual_care_address',
                  'identity_candidate_count': 0, 'address_region_normalized': None,
                  'address_locality_literal': None, 'address_district_normalized': None}
        # Exact whole regional components override contained-word regex matches:
        # "Ямало-Ненецкий" must not additionally become "Ненецкий".
        explicit_components = []
        for part in re.split('[,;]', str(address)):
            part = re.sub(r'^\s*\d{6}\s*', '', part).strip()
            if STREET.match(part):
                break
            region_candidate = normalize_region(part)
            if region_candidate in self.index.region_names:
                explicit_components.append(region_candidate)
        regions = sorted(set(explicit_components)) or self.index.regions_in_address(address)
        if len(regions) != 1:
            result['np_identity_basis'] = 'multiple_explicit_regions' if regions else 'no_explicit_actual_care_region'
            return result
        region = regions[0]
        result['address_region_normalized'] = region
        district = self.index.districts_in_address(address, region)
        if len(district) > 1:
            result['np_identity_basis'] = 'multiple_explicit_districts'
            return result
        result['address_district_normalized'] = district[0] if district else None
        literals = locality_components(address)
        # Federal context only if no more specific locality is explicitly supplied.
        if not literals and region in {'москва', 'санкт петербург', 'севастополь'}:
            literals = [('город', region)]
        candidates = set()
        for typ, name in literals:
            for i in self.names.get((region, name), []):
                row = self.ref.iloc[i]
                if district and row.district_norm != district[0]:
                    continue
                if type_agrees(typ, row.get('settlement_type_2021')):
                    candidates.add(i)
        if region in {'москва', 'санкт петербург', 'севастополь'}:
            ordinary_localities = {i for i in candidates if self.ref.iloc[i].name_norm != region}
            if ordinary_localities:
                candidates = ordinary_localities
        result['address_locality_literal'] = ' | '.join(n for _, n in literals) or None
        result['identity_candidate_count'] = len(candidates)
        if len(candidates) == 1:
            row = self.ref.iloc[next(iter(candidates))]
            result.update(source_record_id=row.source_record_id,
                          np_identity_basis='unique_explicit_actual_care_region_locality_type_and_optional_district')
        elif len(candidates) > 1:
            result['np_identity_basis'] = 'homonymous_or_multiple_localities_not_resolved'
        elif not literals:
            result['np_identity_basis'] = 'no_explicit_locality_component'
        return result


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def identity_diagnostics(frame):
    frame = frame.copy()
    frame['census_source_record_id_2021'] = frame.source_record_id
    frame['provider_settlement_id'] = frame.source_record_id
    gar = frame.ADDR_GAR.fillna('').astype(str).str.strip() if 'ADDR_GAR' in frame else pd.Series('',index=frame.index)
    evidence = pd.DataFrame({'gar':gar,'np':frame.source_record_id})
    multiplicity = evidence[evidence.gar.ne('') & evidence.np.notna()].groupby('gar').np.nunique()
    frame['gar_distinct_literal_np_count'] = gar.map(multiplicity).fillna(0).astype(int)
    frame['gar_multiple_literal_np_conflict'] = frame.gar_distinct_literal_np_count.gt(1)
    frame['gar_conflict_resolution'] = 'literal_np_identity_retained_no_gar_geocoding_or_reassignment'
    return frame


def run(source, reference_path, output):
    output.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(source)
    reference = pd.read_parquet(reference_path)
    if 'ADDR' not in frame:
        raise ValueError('F038 actual-care ADDR is required; legal address substitution forbidden')
    matcher = AddressMatcher(reference)
    unique = frame.ADDR.fillna('').drop_duplicates()
    mapping = {addr: matcher.one(addr) for addr in unique}
    links = pd.DataFrame([mapping[a] for a in frame.ADDR.fillna('')], index=frame.index)
    frame = pd.concat([frame, links], axis=1)
    frame['address_role'] = 'F038_actual_medical_care_address'
    frame['default_external_seed_eligible'] = False
    frame['physical_coordinates_observed'] = False
    frame['location_precision'] = 'settlement_identity_only_not_actual_site_coordinate'
    frame = identity_diagnostics(frame)
    frame.to_parquet(output / 'F038_current_np_identity.parquet', index=False, compression='zstd')
    known = frame[frame.source_record_id.notna()]
    # This is address evidence only, not a clinical service assignment or facility count.
    coverage = reference[reference.source_record_id.notna()].groupby('region').source_record_id.nunique().rename('reference_np').to_frame()
    region_of_np = reference[reference.source_record_id.notna()].set_index('source_record_id').region
    by_region = known.source_record_id.map(region_of_np).value_counts()
    np_by_region = known.drop_duplicates('source_record_id').source_record_id.map(region_of_np).value_counts()
    coverage['matched_address_records'] = coverage.index.map(by_region).fillna(0).astype(int)
    coverage['matched_np'] = coverage.index.map(np_by_region).fillna(0).astype(int)
    coverage.to_csv(output / 'F038_np_coverage.csv')
    summary = {'source_rows': len(frame), 'unique_address_literals': len(unique),
               'matched_address_rows': len(known), 'matched_unique_np': known.source_record_id.nunique(),
               'identity_status_counts': frame.np_identity_basis.value_counts().to_dict(),
               'actual_site_coordinates_inferred': False, 'facility_services_assigned': False,
               'gar_conflicting_address_rows': int(frame.gar_multiple_literal_np_conflict.sum()),
               'gar_conflicting_nonempty_ids': frame.loc[frame.gar_multiple_literal_np_conflict,'ADDR_GAR'].nunique() if 'ADDR_GAR' in frame else 0,
               'source_sha256': sha(source), 'reference_sha256': sha(reference_path)}
    (output / 'address_identity_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))
    return frame


def compare_mirrors(source_a, source_b, output):
    a = pd.read_parquet(source_a)
    b = pd.read_parquet(source_b)
    pair = a.merge(b, on=['UIDSPMO', 'IDADDRESS'], how='outer', indicator=True,
                   suffixes=('_a', '_b'), validate='one_to_one')
    common = pair[pair._merge.eq('both')]
    result = {'source_a_sha256': sha(source_a), 'source_b_sha256': sha(source_b),
              'source_a_rows': len(a), 'source_b_rows': len(b),
              'pair_counts': pair._merge.value_counts().to_dict(),
              'common_address_literal_disagreement': int(common.ADDR_a.ne(common.ADDR_b).sum()),
              'common_gar_disagreement': int(common.ADDR_GAR_a.fillna('').ne(common.ADDR_GAR_b.fillna('')).sum()),
              'different_mirror_snapshots_not_silently_unioned': True}
    output.mkdir(parents=True, exist_ok=True)
    pair.to_parquet(output / 'mirror_pair_comparison.parquet', index=False, compression='zstd')
    (output / 'mirror_comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--reference', type=Path)
    p.add_argument('--compare-source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.compare_source:
        compare_mirrors(a.source, a.compare_source, a.output)
    elif a.reference:
        run(a.source, a.reference, a.output)
    else:
        p.error('--reference or --compare-source is required')

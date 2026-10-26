"""Recover literal settlement identities without using nearest settlements.

Only source locality/address fields and explicitly typed place names in the
institution's name are read. A postal addr:city alone is only a candidate; it
requires an independent verified settlement boundary. Region proxies, nearby
census candidates, operator addresses and population are not evidence. A typed
rural locality in the institution's own name is a separate literal basis.
Coordinates reject conflicts; they never resolve homonyms. Raw fields are kept.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
import re

import pandas as pd

from scripts.sgrt_mass.match import (normalize_name, normalize_region,
                                    normalize_district, norm, REGION_ALIASES)

TYPE_WORDS = {
    'г': 'город', 'город': 'город', 'города': 'город',
    'с': 'село', 'село': 'село', 'села': 'село',
    'д': 'деревня', 'деревня': 'деревня', 'деревни': 'деревня',
    'п': 'поселок', 'пос': 'поселок', 'поселок': 'поселок',
    'поселка': 'поселок', 'пгт': 'пгт', 'рп': 'пгт',
    'х': 'хутор', 'хутор': 'хутор', 'станица': 'станица',
    'станицы': 'станица', 'аул': 'аул', 'станция': 'станция',
    'станции': 'станция', 'ст': 'станция',
}
TYPED = re.compile(
    r'(?<!\w)(?P<type>пгт|рп|город(?:а)?|село|села|деревн[яи]|'
    r'пос[её]лок|пос[её]лка|хутор|станиц[аы]|станци[яи]|аул|'
    r'г\.|с\.|д\.|п\.|пос\.|х\.)(?:(?!\w)|(?<=\.))\s*', re.I)
DISTRICT = re.compile(
    r'(?P<name>[а-яёa-z][а-яёa-z-]*)(?:\s+муниципальн(?:ого|ый|ом))?'
    r'\s+(?:район(?:а|е|ом|у)?|р-н(?:а)?)(?!\w)', re.I)
STREET = re.compile(r'(?<!\w)(?:улица|ул\.|проспект|переулок|пер\.|шоссе|набережная)(?!\w)', re.I)
PARENT_INSTITUTION = re.compile(
    r'\b(?:филиал\w*|структурн\w*\s+подразделен\w*|'
    r'обособлен\w*\s+подразделен\w*|отделени[ея]|осп|сп)\b', re.I)


def text(value):
    return '' if value is None or pd.isna(value) else str(value)


def case_key(value):
    value = norm(value)
    return ' '.join(re.sub(r'(?:ская|ской|скую|скою|ский|ского|скому|ским|ском|ские|ских)$',
                          'ск', word) for word in value.split())


def variants(value):
    words = norm(value).split()
    options = [words]
    for i, word in enumerate(words):
        endings = None
        if word.endswith('ская'):
            endings = [word[:-2] + x for x in ['ая', 'ой', 'ую', 'ою']]
        elif word.endswith('ский'):
            endings = [word[:-2] + x for x in ['ий', 'ого', 'ому', 'им', 'ом']]
        if endings:
            options = [o[:i] + [ending] + o[i+1:] for o in options for ending in endings]
    return [' '.join(o) for o in options]


def _km(a, b, c, d):
    try:
        a, b, c, d = map(float, [a, b, c, d])
        if not all(math.isfinite(x) for x in [a, b, c, d]): return None
        q = math.sin(math.radians(c-a)/2)**2 + math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(math.radians(d-b)/2)**2
        return 12742.0176 * math.asin(math.sqrt(min(1., max(0., q))))
    except (ValueError, TypeError):
        return None


class ExplicitLocalityIndex:
    def __init__(self, reference):
        self.reference = reference[reference.source_record_id.notna()].copy()
        if self.reference.source_record_id.duplicated().any():
            raise ValueError('Census identity must be unique')
        self.by_name = defaultdict(list)
        self.first_word = defaultdict(set)
        self.rows = {}
        regions = set()
        for _, row in self.reference.iterrows():
            name = normalize_name(row['name'])
            if not name: continue
            sid = row.source_record_id
            record = row.to_dict()
            record['_region'] = normalize_region(row.get('region'))
            record['_district'] = case_key(normalize_district(row.get('district')))
            record['_type'] = norm(row.get('settlement_type_2021'))
            self.rows[sid] = record
            self.by_name[name].append(sid)
            self.first_word[name.split()[0]].add(name)
            regions.add(record['_region'])
        aliases = {r: r for r in regions if r}
        aliases.update({a:r for a,r in REGION_ALIASES.items() if r in regions})
        self.region_patterns = []
        for alias, region in aliases.items():
            for value in variants(alias):
                phrase = re.escape(value).replace(r'\ ', r'\s+')
                if region in {'москва', 'санкт петербург', 'севастополь'}:
                    pattern = rf'(?<!\w){phrase}(?!\w)'
                else:
                    pattern = rf'(?<!\w)(?:(?:республик[аиуе]|респ|область|обл|край)\s+{phrase}|{phrase}\s+(?:республик[аиуе]|област[ьи]|обл|кра[йяе]|автономн\w*\s+округ\w*))(?!\w)'
                self.region_patterns.append((region, re.compile(pattern)))

    def _typed(self, value):
        results = []
        for marker in TYPED.finditer(value):
            # Initials in a person's name do not name the institution's place.
            before_raw = value[max(0, marker.start()-100):marker.start()]
            after_raw = value[marker.end():]
            before = before_raw.lower()
            if re.search(r'(?<!\w)(?:имени|им\.?)\s*(?:[а-яёa-z]\.\s*)*$', before): continue
            if (len(norm(marker['type']))==1 and marker['type'][0].isupper()
                    and re.search(r'(?<!\w)(?:имени|им)(?:\.|\s|$)', before)):
                continue
            if re.search(r'(?<!\w)[А-ЯЁA-Z]\.\s*$', before_raw): continue
            if re.match(r'\s*[А-ЯЁA-Z]\.', after_raw): continue
            if (len(norm(marker['type']))==1 and marker['type'][0].isupper()
                    and re.search(r'[«"“]\s*$', before_raw)):
                continue
            after = norm(value[marker.end():])
            words = after.split()
            if not words: continue
            names = self.first_word.get(words[0], ())
            found = [n for n in names if words[:len(n.split())] == n.split()]
            if found:
                longest = max(len(n.split()) for n in found)
                kind = TYPE_WORDS.get(norm(marker['type']))
                for name in found:
                    if len(name.split()) == longest:
                        results.append((name, kind))
        return results

    def match(self, row, *, max_validation_distance_km=5.):
        raw = row.get('tags_json')
        try: tags = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
        except (ValueError, TypeError): tags = {}
        if not isinstance(tags, dict): tags = {}
        place_fields = [(k, tags.get(k)) for k in ['addr:city', 'addr:place', 'addr:village', 'addr:town']]
        place_fields.append(('source_address_locality', row.get('source_address_locality')))
        name_fields = [(k, tags.get(k)) for k in ['official_name', 'short_name', 'name']]
        name_fields.append(('source_name', row.get('name')))
        address_fields = [(k, tags.get(k)) for k in ['addr:full', 'addr:full_address']]
        address_fields.append(('source_address_full', row.get('source_address_full')))
        fields = [(k, text(v)) for k,v in place_fields + name_fields + address_fields if text(v)]
        literal_regions = set()
        for value in [row.get('source_address_state'), tags.get('addr:state'), tags.get('addr:region')]:
            normalized_region = normalize_region(value) if text(value) else ''
            if normalized_region: literal_regions.add(normalized_region)
        full_text = ' '.join(v for _,v in fields)
        normalized = norm(full_text)
        literal_regions.update(r for r,p in self.region_patterns if p.search(normalized))
        literal_districts = {case_key(normalize_district(tags[k])) for k in ['addr:district', 'addr:subdistrict'] if text(tags.get(k))}
        literal_districts.update(case_key(normalize_district(x['name'])) for x in DISTRICT.finditer(full_text))
        literal_districts.discard('')
        evidence = []
        for k,v in place_fields:
            if text(v):
                name = normalize_name(v)
                if name in self.by_name:
                    evidence.append((k, name, None))
        for k,v in name_fields + address_fields:
            if not text(v): continue
            value = text(v)
            if k in {x[0] for x in address_fields}:
                street = STREET.search(value)
                if street: value = value[:street.start()]
            evidence.extend((k,n,t) for n,t in self._typed(value))
        result = {'explicit_locality_source_record_id': None,
                  'explicit_locality_candidate_source_record_id': None,
                  'explicit_locality_identity_status': 'no_explicit_locality',
                  'explicit_locality_candidate_count': 0,
                  'explicit_locality_distance_km': None,
                  'explicit_locality_evidence_json': json.dumps({'places': evidence, 'literal_regions':sorted(literal_regions),
                                                               'literal_districts':sorted(literal_districts)}, ensure_ascii=False)}
        existing = text(row.get('source_record_id'))
        if not evidence:
            if existing: result['explicit_locality_identity_status'] = 'existing_identity_preserved'
            return result
        if len(literal_regions)>1:
            result['explicit_locality_identity_status'] = 'held_conflicting_literal_regions'
            return result
        if len(literal_districts)>1:
            result['explicit_locality_identity_status'] = 'held_conflicting_literal_districts'
            return result
        candidates = None
        for _,name,kind in evidence:
            choices = set(self.by_name[name])
            if kind:
                choices = {sid for sid in choices if self.rows[sid]['_type']==kind}
            candidates = choices if candidates is None else candidates & choices
        candidates = candidates or set()
        if literal_regions:
            candidates = {sid for sid in candidates if self.rows[sid]['_region'] in literal_regions}
        if literal_districts:
            candidates = {sid for sid in candidates if self.rows[sid]['_district'] in literal_districts}
        result['explicit_locality_candidate_count'] = len(candidates)
        boundary_owner = text(row.get('verified_boundary_source_record_id'))
        if len(candidates) > 1 and boundary_owner in candidates:
            # Independent named-polygon containment can resolve a literal
            # homonym. Distance is still never used to choose its owner.
            candidates = {boundary_owner}
        if len(candidates)!=1:
            result['explicit_locality_identity_status'] = 'held_ambiguous_literal_identity' if candidates else 'held_literal_context_conflict'
            return result
        sid = next(iter(candidates))
        result['explicit_locality_candidate_source_record_id'] = sid
        if existing:
            result['explicit_locality_identity_status'] = ('existing_identity_literal_agrees' if existing==sid
                                                           else 'held_existing_identity_literal_conflict')
            return result
        reference = self.rows[sid]
        distance = _km(row.get('site_lat', row.get('lat')), row.get('site_lon', row.get('lon')),
                       reference.get('lat'), reference.get('lon'))
        result['explicit_locality_distance_km'] = distance
        # addr:city is often the postal city of a school in a different village.
        # This is not repaired by making a city-distance cutoff more generous.
        boundary_owner = text(row.get('verified_boundary_source_record_id'))
        if boundary_owner and boundary_owner != sid:
            result['explicit_locality_identity_status'] = 'held_literal_boundary_conflict'
            return result
        named_rural = any(k in {'official_name', 'short_name', 'name', 'source_name'}
                          and kind in {'село', 'деревня', 'поселок', 'пгт', 'хутор', 'станица', 'аул'}
                          for k, _, kind in evidence)
        # "Taidakovsky branch of the Shigony village school" explicitly names
        # the parent's village. A more elaborate name is not automatically the
        # activity address of this particular physical site.
        parent_name = any(PARENT_INSTITUTION.search(text(v)) for _,v in name_fields)
        if parent_name and not boundary_owner:
            result['explicit_locality_identity_status'] = 'held_parent_institution_locality_for_branch'
            return result
        if not named_rural and not boundary_owner:
            result['explicit_locality_identity_status'] = 'candidate_address_locality_needs_boundary_confirmation'
            return result
        if not boundary_owner and distance is not None and distance > max_validation_distance_km:
            result['explicit_locality_identity_status'] = 'held_literal_coordinate_conflict'
            return result
        result.update(explicit_locality_source_record_id=sid,
                      explicit_locality_identity_status=('matched_literal_and_verified_boundary' if boundary_owner
                                                          else 'matched_typed_rural_name'))
        return result


def reconcile_explicit_localities(sites, reference, *, max_validation_distance_km=5.):
    """Append literal identity evidence, preserving raw fields and existing IDs."""
    index = ExplicitLocalityIndex(reference)
    evidence = [index.match(row, max_validation_distance_km=max_validation_distance_km)
                for _, row in sites.iterrows()]
    result = sites.copy()
    if not evidence:
        for column in ['explicit_locality_source_record_id', 'explicit_locality_candidate_source_record_id', 'explicit_locality_identity_status',
                       'explicit_locality_candidate_count', 'explicit_locality_distance_km',
                       'explicit_locality_evidence_json']:
            result[column] = pd.Series(index=result.index, dtype='object')
        return result
    for column in pd.DataFrame(evidence, index=sites.index):
        result[column] = [row[column] for row in evidence]
    return result

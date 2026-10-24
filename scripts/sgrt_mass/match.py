#!/usr/bin/env python3
"""Attach dated source addresses to census records without proximity matching.

Only exact settlement codes and normalized literal place names are used. A
shared name without adequate regional/district context remains ambiguous.
Legal addresses must be passed separately from addresses of activity.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

REGION_CODES = dict(zip(
    "01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65 66 67 68 69 70 71 72 73 74 75 76 77 78 79 83 86 87 89 91 92".split(),
    ["адыгея", "башкортостан", "бурятия", "алтай", "дагестан", "ингушетия", "кабардино балкарская", "калмыкия", "карачаево черкесская", "карелия", "коми", "марий эл", "мордовия", "саха якутия", "северная осетия алания", "татарстан", "тыва", "удмуртская", "хакасия", "чеченская", "чувашская", "алтайский", "краснодарский", "красноярский", "приморский", "ставропольский", "хабаровский", "амурская", "архангельская", "астраханская", "белгородская", "брянская", "владимирская", "волгоградская", "вологодская", "воронежская", "ивановская", "иркутская", "калининградская", "калужская", "камчатский", "кемеровская", "кировская", "костромская", "курганская", "курская", "ленинградская", "липецкая", "магаданская", "московская", "мурманская", "нижегородская", "новгородская", "новосибирская", "омская", "оренбургская", "орловская", "пензенская", "пермский", "псковская", "ростовская", "рязанская", "самарская", "саратовская", "сахалинская", "свердловская", "смоленская", "тамбовская", "тверская", "томская", "тульская", "тюменская", "ульяновская", "челябинская", "забайкальский", "ярославская", "москва", "санкт петербург", "еврейская", "ненецкий", "ханты мансийский югра", "чукотский", "ямало ненецкий", "крым", "севастополь"]))

ADMIN_WORDS = {"республика", "респ", "область", "обл", "край", "автономная", "автономный", "автономного", "округ", "ао", "город", "г", "федерального", "значения", "россия", "российская", "федерация"}
REGION_ALIASES = {"удмуртия": "удмуртская", "чувашия": "чувашская", "чувашская чувашия": "чувашская", "саха": "саха якутия", "якутия": "саха якутия", "тува": "тыва", "северная осетия": "северная осетия алания", "кабардино балкария": "кабардино балкарская", "карачаево черкесия": "карачаево черкесская", "чечня": "чеченская", "ханты мансийский": "ханты мансийский югра", "хмао югра": "ханты мансийский югра", "хмао": "ханты мансийский югра", "янао": "ямало ненецкий", "кемеровская кузбасс": "кемеровская", "кузбасс": "кемеровская", "спб": "санкт петербург", "башкирия": "башкортостан"}
PLACE_TYPES = {"город", "г", "гор", "село", "с", "деревня", "д", "дер", "поселок", "поселение", "пос", "п", "пгт", "рп", "хутор", "х", "станица", "стца", "аул", "аал", "улус", "нп", "станция", "станции", "разъезд", "слобода", "участок", "кордон", "местечко", "починок", "заимка", "выселок", "выселки", "зимовье", "арбан", "стойбище", "сумон"}
STREET_RE = re.compile(r"(?<!\w)(?:ул|улица|переулок|пер|проспект|пркт|проезд|бульвар|бульв|площадь|пл|шоссе|ш|набережная|наб|тупик|квартал)(?!\w)")
DISTRICT_STOP = {"муниципальный", "муниципальное", "муниципальная", "район", "р", "н", "городской", "городское", "округ", "округа", "город", "г", "сельский", "поселение", "сельсовет", "сельское", "м", "о", "мо", "мр"}
SUFFIX_ADMIN = {"район", "р", "сельсовет", "сельский", "муниципальный", "муниципальное", "городской", "округ", "область", "обл", "край", "республика", "респ"}
_INDEX_CACHE = {}
FEDERAL_AGGREGATE_IDS = frozenset({
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:64748",
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:126656",
})


def norm(value):
    if value is None or pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKC", str(value)).lower().replace("ё", "е")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).replace("_", " ")
    return " ".join(value.split())


def normalize_region(value):
    raw = norm(value)
    if raw.isdigit() and len(raw) <= 2:
        return REGION_CODES.get(raw.zfill(2), "")
    value = " ".join(w for w in raw.split() if w not in ADMIN_WORDS)
    words = value.split()
    value = " ".join(dict.fromkeys(words))
    return REGION_ALIASES.get(value, value)


def normalize_name(value):
    value = norm(value)
    if re.match(r"^(?:пгт|рабочий поселок|рп|дачный поселок)\s", value):
        value = re.sub(r"\s+(?:рп|дп|кп)$", "", value)
    value = re.sub(r"\bим\b", "имени", value)
    for _ in range(4):
        before = value
        value = re.sub(r"^(?:сельский населенный пункт|населенный пункт|рабочий поселок|дачный поселок|курортный поселок|поселок городского типа|железнодорожная станция|железнодорожной станции|железнодорожный разъезд|дорожный разъезд|железнодорожная платформа|железнодорожный остановочный пункт|железнодорожная будка|железнодорожная казарма|железнодорожный путевой пост|ж д разъезд|ж д станция|ж д станции|жд ст|жд станция)\s+", "", value)
        first, sep, rest = value.partition(" ")
        if first in PLACE_TYPES and sep:
            value = rest
        if value == before:
            break
    return value


def normalize_district(value):
    value = norm(value)
    value = re.sub(r"\b(?:муниципальн(?:ый|ого|ому|ым|ая|ое|ые)|район(?:а|у|ом)?|округ(?:а|у|ом)?|городск(?:ой|ого|ому|им|ая|ое)|сельск(?:ий|ого|ому|им|ая|ое))\b", " ", value)
    return " ".join(w for w in value.split() if w not in DISTRICT_STOP)


def normalize_settlement_oktmo(value):
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    if re.fullmatch(r"\d{10,11}", value):
        return value.zfill(11)
    return None


def build_reference(wide_path):
    source = pd.read_parquet(wide_path)
    result = pd.DataFrame({"root": source.root, "source_record_id": source.source_record_id_2021})
    for output, prefix in [("name", "settlement_name"), ("region", "region_norm"), ("district", "district_raw"), ("oktmo", "oktmo")]:
        result[output] = source[f"{prefix}_2021"].fillna(source[f"{prefix}_2010"]).fillna(source[f"{prefix}_2002"])
    result["oktmo_source_literal"] = result.oktmo
    result["oktmo"] = result.oktmo.map(normalize_settlement_oktmo)
    result["oktmo_leading_zero_restored"] = result.oktmo_source_literal.astype("string").str.fullmatch(r"\d{10}", na=False)
    for year in [2002, 2010, 2021]:
        result[f"population_{year}"] = source[f"effective_population_{year}"]
        result[f"credit_{year}"] = source[f"working_credit_present_{year}"].astype("boolean").fillna(False).astype(bool)
        result[f"source_record_id_{year}"] = source[f"source_record_id_{year}"]
        result[f"population_value_quality_{year}"] = source[f"population_value_quality_{year}"]
        result[f"population_overlay_applied_{year}"] = source[f"population_overlay_applied_{year}"]
    result["lat"] = source.accepted_latitude_2021
    result["lon"] = source.accepted_longitude_2021
    result["accepted_point_present"] = source.accepted_point_present_2021.astype("boolean").fillna(False).astype(bool)
    result["has_2021_record"] = result.source_record_id.notna()
    result["population_role"] = "ordinary_settlement_record"
    result.loc[result.source_record_id.isin(FEDERAL_AGGREGATE_IDS), "population_role"] = "external_context_nonadditive"
    result["ordinary_spatial_2021"] = result.has_2021_record & result.accepted_point_present & result.population_role.eq("ordinary_settlement_record")
    result["name_norm"] = result.name.map(normalize_name)
    result["region_norm"] = result.region.map(normalize_region)
    result["district_norm"] = result.district.map(normalize_district)
    result["name_reference_year"] = source.settlement_name_2021.notna().map({True: 2021, False: pd.NA})
    if result.source_record_id.dropna().duplicated().any():
        raise ValueError("Repeated 2021 source identity in census reference")
    return result


class ReferenceIndex:
    def __init__(self, reference):
        self.reference = reference
        self.names = defaultdict(list)
        self.codes = defaultdict(list)
        self.tries = defaultdict(dict)
        self.district_tries = defaultdict(dict)
        self.region_names = set(reference.region_norm.dropna())
        aliases = {region: region for region in self.region_names}
        aliases.update({alias: region for alias, region in REGION_ALIASES.items() if region in self.region_names})
        self.region_patterns = []
        for alias, region in aliases.items():
            if not alias:
                continue
            phrase = re.escape(alias).replace(r"\ ", r"\s+")
            if region in {"москва", "санкт петербург", "севастополь"}:
                pattern = rf"(?<!\w){phrase}(?!\w)"
            elif alias in {"хмао", "хмао югра", "янао"}:
                pattern = rf"(?<!\w){phrase}(?!\w)"
            else:
                pattern = rf"(?<!\w)(?:(?:республика|респ|область|обл|край)\s+{phrase}|{phrase}\s+(?:республика|респ|область|обл|край|автономный\s+округ|автономная\s+область|ао))(?!\w)"
            self.region_patterns.append((region, re.compile(pattern)))
        for idx, row in reference[reference.source_record_id.notna()].iterrows():
            self.names[(row.region_norm, row.name_norm)].append(idx)
            code = str(row.oktmo).strip()
            if re.fullmatch(r"\d{11}", code):
                self.codes[code].append(idx)
        for (region, name), _ in self.names.items():
            if not name:
                continue
            node = self.tries[region]
            for word in name.split():
                node = node.setdefault(word, {})
            node["$"] = name
        for _, row in reference[reference.source_record_id.notna()].drop_duplicates(["region_norm", "district_norm"]).iterrows():
            if not row.district_norm:
                continue
            node = self.district_tries[row.region_norm]
            for word in row.district_norm.split():
                node = node.setdefault(word, {})
            node["$"] = row.district_norm

    def regions_in_address(self, address):
        text = norm(address)
        if not text:
            return []
        cutoff = STREET_RE.search(text)
        if cutoff:
            text = text[:cutoff.start()]
        return sorted(set(region for region, pattern in self.region_patterns if pattern.search(text)))

    def districts_in_address(self, address, region):
        text = norm(address)
        cutoff = STREET_RE.search(text)
        if cutoff:
            text = text[:cutoff.start()]
        words = text.split()
        found = []
        trie = self.district_tries.get(region, {})
        for i in range(len(words)):
            node = trie
            for j in range(i, len(words)):
                node = node.get(words[j])
                if node is None:
                    break
                if "$" not in node:
                    continue
                before = " ".join(words[max(0, i-3):i])
                after = words[j+1:j+5]
                prefix = any(before.endswith(label) for label in ["район", "р н", "округ", "округ город"])
                suffix = False
                for k, word in enumerate(after):
                    if word in {"район", "округ"} and all(w in {"муниципальный", "городской", "муниципального", "городского", "м"} for w in after[:k]):
                        suffix = True
                if prefix or suffix:
                    found.append(node["$"])
        return sorted(set(found))

    def names_in_address(self, address, region):
        text = norm(address)
        cutoff = STREET_RE.search(text)
        if cutoff:
            text = text[:cutoff.start()]
        words = text.split()
        found = []
        trie = self.tries.get(region, {})
        for i in range(len(words)):
            node = trie
            for j in range(i, len(words)):
                node = node.get(words[j])
                if node is None:
                    break
                if "$" not in node:
                    continue
                if j + 1 < len(words) and words[j + 1] in SUFFIX_ADMIN:
                    continue
                typed = i > 0 and words[i - 1] in PLACE_TYPES
                if i > 0 and words[i - 1] in {"республика", "респ", "область", "обл", "край", "автономный", "автономная"}:
                    continue
                if not typed and region not in {"москва", "санкт петербург", "севастополь"} and normalize_region(node["$"]) == region:
                    continue
                found.append((i, j, node["$"], typed))
        # A complete multiword name wins only over its own contained fragments.
        found = [a for a in found if not any(b[0] <= a[0] and b[1] >= a[1] and (b[0], b[1]) != (a[0], a[1]) for b in found)]
        if any(x[3] for x in found):
            found = [x for x in found if x[3]]
        return sorted(set(x[2] for x in found))


def _district_filter(indices, reference, district, address):
    if not indices:
        return [], False
    if district:
        selected = [idx for idx in indices if reference.loc[idx, "district_norm"] == district]
        return selected, True
    address = " " + norm(address) + " "
    candidates = [idx for idx in indices if reference.loc[idx, "district_norm"] and (" " + reference.loc[idx, "district_norm"] + " ") in address]
    return (candidates, True) if candidates else (indices, False)


def match_addresses(frame, reference, *, address_col="activity_address", region_col="source_region_literal", district_col=None, name_col=None, oktmo_col=None):
    """Return input rows plus census identity and explicit match diagnostics.

    Region literals may be official names or the two-digit FNS region code.
    An 8-digit municipal code never identifies a settlement. Unrecognized or
    malformed source codes do not become geographical coordinates.
    """
    key = id(reference)
    if key not in _INDEX_CACHE or _INDEX_CACHE[key].reference is not reference:
        _INDEX_CACHE[key] = ReferenceIndex(reference)
    index = _INDEX_CACHE[key]
    output = frame.copy()
    results = []
    for _, row in frame.iterrows():
        address = row.get(address_col, "")
        address = "" if pd.isna(address) else str(address)
        source_region = normalize_region(row.get(region_col, ""))
        region = source_region
        district = normalize_district(row.get(district_col, "")) if district_col else ""
        name = normalize_name(row.get(name_col, "")) if name_col else ""
        code = str(row.get(oktmo_col, "")).strip() if oktmo_col and pd.notna(row.get(oktmo_col)) else ""
        if code.endswith(".0"):
            code = code[:-2]
        code_status = "not_supplied" if not code else "valid_11digit" if re.fullmatch(r"\d{11}", code) else "leading_zero_restored_from_10digit_source" if re.fullmatch(r"\d{10}", code) else "not_settlement_11digit_code"
        if code_status == "leading_zero_restored_from_10digit_source":
            code = code.zfill(11)
        record = {"source_record_id": None, "match_status": "unmatched", "match_method": None,
                  "match_reason": None, "candidate_count": 0, "matched_region": None,
                  "source_code_status": code_status, "census_reference_year": 2021,
                  "source_year_not_assumed_census_year": True, "source_region_normalized": source_region,
                  "address_region_normalized": None, "region_inference_source": "source_jurisdiction",
                  "source_region_differs_from_activity_region": False, "source_oktmo_normalized": code if len(code) == 11 else None}
        def hold(reason, status="unmatched", count=0):
            record.update(match_reason=reason, match_status=status, candidate_count=count)
        def assign(indices, method):
            record["candidate_count"] = len(indices)
            if len(indices) == 1:
                idx = indices[0]
                record.update(source_record_id=reference.loc[idx, "source_record_id"], match_status="matched",
                              match_method=method, match_reason="unique_literal_identity_with_context",
                              matched_region=reference.loc[idx, "region_norm"])
            elif len(indices) > 1:
                hold("homonymous_settlements_not_resolved", "ambiguous", len(indices))
            else:
                hold("district_or_literal_context_conflict", "conflict")
        source_grain = str(row.get("source_row_grain", "")).strip()
        if source_grain in {"city_aggregate", "municipal_aggregate", "regional_aggregate", "aggregate_not_settlement"}:
            hold("explicit_source_aggregate_grain_not_allocated_to_settlement", "not_settlement_grain")
            results.append(record)
            continue
        if code and re.fullmatch(r"\d{8}", code):
            hold("municipal_8digit_source_code_not_allocated_to_settlement", "not_settlement_grain")
            results.append(record)
            continue
        if len(code) == 11 and code.endswith("000") and code not in index.codes:
            hold("source_code_aggregate_000_not_a_reference_settlement", "not_settlement_grain")
            results.append(record)
            continue
        address_regions = index.regions_in_address(address)
        if len(address_regions) > 1:
            hold("multiple_explicit_regions_in_activity_address", "ambiguous")
            results.append(record)
            continue
        if address_regions:
            region = address_regions[0]
            record.update(address_region_normalized=region, region_inference_source="explicit_activity_address",
                          source_region_differs_from_activity_region=bool(source_region and region != source_region))
        if region not in index.region_names:
            hold("region_not_resolved_in_accepted_reference")
            results.append(record)
            continue
        if not district:
            district_hints = index.districts_in_address(address, region)
            if len(district_hints) > 1:
                hold("multiple_explicit_districts_in_one_source_address", "ambiguous")
                results.append(record)
                continue
            if district_hints:
                district = district_hints[0]
        if code_status in {"valid_11digit", "leading_zero_restored_from_10digit_source"} and code in index.codes:
            candidates = index.codes[code]
            candidates = [i for i in candidates if reference.loc[i, "region_norm"] == region]
            if not candidates:
                hold("source_code_region_conflict", "conflict")
            elif name and not any(reference.loc[i, "name_norm"] == name for i in candidates):
                hold("source_code_settlement_name_conflict", "conflict", len(candidates))
            elif address and index.names_in_address(address, region) and not any(reference.loc[i, "name_norm"] in index.names_in_address(address, region) for i in candidates):
                hold("source_code_activity_address_name_conflict", "conflict", len(candidates))
            else:
                if name:
                    candidates = [i for i in candidates if reference.loc[i, "name_norm"] == name]
                candidates, used_district = _district_filter(candidates, reference, district, address)
                assign(candidates, "exact_settlement_oktmo11_region" + ("_district" if used_district else "") + ("_name" if name else ""))
            results.append(record)
            continue
        if code_status in {"valid_11digit", "leading_zero_restored_from_10digit_source"}:
            record["source_code_status"] = "11digit_code_not_in_2021_reference"
        names = [name] if name and (region, name) in index.names else index.names_in_address(address, region)
        if not names:
            hold("no_literal_settlement_name_in_source_address_or_name")
        else:
            candidates = sorted(set(i for n in names for i in index.names.get((region, n), [])))
            candidates, used_district = _district_filter(candidates, reference, district, address)
            assign(candidates, "exact_normalized_name_region" + ("_district" if used_district else ""))
        results.append(record)
    columns = ["source_record_id", "match_status", "match_method", "match_reason", "candidate_count", "matched_region",
               "source_code_status", "census_reference_year", "source_year_not_assumed_census_year",
               "source_region_normalized", "address_region_normalized", "region_inference_source",
               "source_region_differs_from_activity_region", "source_oktmo_normalized"]
    diagnostics = pd.DataFrame(results, columns=columns, index=output.index)
    for column in columns:
        output[column] = diagnostics[column]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--address-col", default="activity_address")
    parser.add_argument("--region-col", default="source_region_literal")
    parser.add_argument("--name-col")
    parser.add_argument("--district-col")
    parser.add_argument("--oktmo-col")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reference = build_reference(args.population)
    reference.to_parquet(args.output / "census_reference.parquet", index=False)
    if args.input:
        source = pd.read_parquet(args.input) if args.input.suffix == ".parquet" else pd.read_csv(args.input, dtype=str)
        result = match_addresses(source, reference, address_col=args.address_col, region_col=args.region_col,
                                 name_col=args.name_col, district_col=args.district_col, oktmo_col=args.oktmo_col)
        result.to_parquet(args.output / "matched_records.parquet", index=False)
        print(json.dumps(result.match_status.value_counts().to_dict(), ensure_ascii=False))


if __name__ == "__main__":
    main()

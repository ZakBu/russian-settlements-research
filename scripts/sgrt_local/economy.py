#!/usr/bin/env python3
"""Recalculate a local agricultural context without inventing settlement jobs.

Inputs are the archived row-level RFSD extract, the original BDMO section-7
Parquet (or its verified two-municipality extraction), and the saved first-party
employer website application. No municipal value is allocated to a settlement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

MUNICIPALITIES = {"80653410": "Амангильдинский сельсовет", "80653491": "Уральский сельсовет"}
SOURCE_SHA = "e6ca2906f49fd0fe561ae98f535206990cebc2675884571bced546c3374c198d"
SOURCE_URL = "https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20250918/by_section/data_section7_112_v20250918_section_file.zip"
JS_SHA = "bf6ccf93dd503019c0e64e696b8a0a29f1a0ab4f164f840f4cdc3bc7ac5da134"
JS_URL = "https://bairamgul.ru/assets/index-BB7BIiY9.js?v=20260929"
FNS_SHA = "a4a2972b5d424d49424723cb77837f4605f390ee6edef42f382a0b9504f3f85a"
FNS_URL = "https://file.nalog.ru/opendata/7707329152-sshr2019/data-20260925-structure-20200408.zip"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(frame, out, name):
    frame.to_csv(out / (name + ".csv"), index=False)
    frame.to_parquet(out / (name + ".parquet"), index=False)


def agriculture(path, out):
    """Scan original observations, or rerun the saved exact extraction."""
    is_full_source = sha(path) == SOURCE_SHA
    rows = []
    scanned = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=100000):
        scanned += len(batch)
        mask = pc.is_in(batch.column("oktmo"), value_set=pa.array([*MUNICIPALITIES, "80653000"]))
        selected = batch.filter(mask).to_pandas()
        if len(selected):
            rows.append(selected)
    if not rows:
        raise ValueError("No original municipality observations found")
    selected = pd.concat(rows, ignore_index=True)
    if not is_full_source and (len(selected) != scanned or len(selected) not in [31, 3698]):
        raise ValueError("Unrecognized source; expected exact local extraction")
    key = ["oktmo", "year", "indicator_code", "kultur", "skot", "kategor", "selmash", "okpd2", "okpdst", "okei"]
    if selected.duplicated(key).any():
        raise ValueError("Nonunique raw agricultural observations")
    if selected.indicator_value.dropna().lt(0).any():
        raise ValueError("Negative raw agricultural observation")
    selected["source_id"] = "BDMO_SECTION7_20250918"
    selected["source_observation_grain"] = selected.oktmo.map({**{k: "rural_municipality_households" for k in MUNICIPALITIES},
                                                             "80653000": "whole_municipal_district"})
    save(selected, out, "agriculture_source_rows")
    district = selected[selected.oktmo.eq("80653000")].copy()
    save(district, out, "district_agriculture_source_rows")
    district_summary = recent_district(district, out) if len(district) else {"observations": 0}
    selected = selected[selected.oktmo.isin(MUNICIPALITIES)].copy()
    save(selected, out, "lower_municipal_source_rows")
    result = []
    for (code, year), group in selected.groupby(["oktmo", "year"]):
        def val(indicator, dimension, label):
            z = group[group.indicator_code.eq(indicator) & group[dimension].str.strip().eq(label)]
            if len(z) > 1:
                raise ValueError("Duplicate indicator in municipality-year")
            return float(z.indicator_value.iloc[0]) if len(z) else np.nan
        total = val("Y48007001", "kultur", "Всего")
        components = group[group.indicator_code.eq("Y48007001") & ~group.kultur.str.strip().eq("Всего")].indicator_value
        component_sum = components.sum(min_count=1)
        if pd.notna(total) and not np.isclose(total, component_sum):
            raise ValueError("Reported sown area does not reconcile with components")
        result.append({
            "municipality_code": code, "municipality": MUNICIPALITIES[code], "year": int(year),
            "household_sown_area_ha": total,
            "household_crop_component_sum_ha_not_imputed_total": component_sum,
            "household_potato_ha": val("Y48007001", "kultur", "Картофель"),
            "household_vegetable_ha": val("Y48007001", "kultur", "Овощи открытого и закрытого грунта"),
            "household_cattle_heads": val("Y48007002", "skot", "Крупный рогатый скот"),
            "household_cows_heads_subset_of_cattle": val("Y48007002", "skot", "Коровы"),
            "source_id": "BDMO_SECTION7_20250918", "territorial_grain": "whole_rural_municipality",
            "category": "households_only", "settlement_value_identified": False,
            "allocated_to_functional_zone": False, "boundary_equivalence_with_2025_proven": False,
        })
    profiles = pd.DataFrame(result)
    save(profiles, out, "municipal_profiles")
    return {"original_full_parquet_verified": is_full_source, "rows_scanned": scanned,
            "local_observations": len(selected), "municipality_years": len(profiles), "district": district_summary}


def recent_district(frame, out):
    """Retain distinct categories and units; nominal rubles are not real growth."""
    categories = ["Хозяйства всех категорий", "Сельскохозяйственные организации (все сельхозорганизации)",
                  "Крестьянские (фермерские) хозяйства и индивидуальные предприниматели", "Хозяйства населения (граждане)"]
    specs = [
        ("sown_total_ha", "Y48007018", "kultur", "Вся посевная площадь", "Гектар", False),
        ("grain_sown_ha", "Y48007018", "kultur", "Зерновые и зернобобовые культуры — всего", "Гектар", False),
        ("feed_sown_ha", "Y48007018", "kultur", "Кормовые культуры — всего", "Гектар", False),
        ("technical_sown_ha", "Y48007018", "kultur", "Технические культуры — всего", "Гектар", False),
        ("cattle_heads", "Y48007020", "skot", "Крупный рогатый скот", "Голова", False),
        ("agricultural_output_nominal_thousand_rub", "Y48007010", None, None, "Тысяча рублей", True),
        ("crop_output_nominal_thousand_rub", "Y48007011", None, None, "Тысяча рублей", True),
        ("livestock_output_nominal_thousand_rub", "Y48007012", None, None, "Тысяча рублей", True),
    ]
    records = []
    for metric, indicator, dimension, label, unit, nominal in specs:
        z = frame[frame.indicator_code.eq(indicator)]
        if dimension:
            z = z[z[dimension].str.strip().eq(label)]
        latest = int(z.year.max())
        for role, year in [("2010", 2010), ("2021", 2021), ("latest", latest)]:
            for category in categories:
                value = z[z.year.eq(year) & z.kategor.eq(category)]
                if len(value) > 1:
                    raise ValueError("Duplicate district observation after exact category/metric selection")
                v = float(value.indicator_value.iloc[0]) if len(value) else np.nan
                status = "observed" if np.isfinite(v) else "source_missing" if len(value) else "no_source_row"
                if v == 999999999:
                    status = "suspect_source_code_excluded_pending_dictionary"
                    v = np.nan
                if len(value) and value.indicator_unit.iloc[0] != unit:
                    raise ValueError("Unexpected district measurement unit")
                records.append({"municipality_code": "80653000", "municipality": "Учалинский муниципальный район",
                                "metric": metric, "indicator_code": indicator, "category": category,
                                "year": year, "reference_year_role": role, "value": v, "value_status": status,
                                "unit": unit, "nominal_current_prices": nominal, "source_id": "BDMO_SECTION7_20250918",
                                "territorial_grain": "whole_district_not_local_fragment",
                                "allocated_to_settlement": False, "historical_boundary_equivalence_proven": False})
    result = pd.DataFrame(records)
    save(result, out, "recent_district_agriculture")
    changes = []
    for metric in ["grain_sown_ha", "cattle_heads"]:
        z = result[result.metric.eq(metric) & result.category.eq(categories[0])].set_index("reference_year_role")
        before, after = z.loc["2010", "value"], z.loc["2021", "value"]
        changes.append({"metric": metric, "value_2010": before, "value_2021": after,
                        "change_pct": (after / before - 1) * 100 if pd.notna(before) and before > 0 else np.nan,
                        "geography": "whole_district", "local_function_change_not_established": True})
    save(pd.DataFrame(changes), out, "district_physical_changes_2010_2021")
    return {"observations": len(frame), "snapshot_rows": len(result), "scope": "whole_district_only",
            "nominal_output_not_interpreted_as_real_growth": True}


def entities(archive, out):
    path = archive / "agro_legal_witnesses_2016_2021.csv"
    frame = pd.read_csv(path, dtype={"inn": str, "oktmo": str, "code": str})
    if frame.duplicated(["year", "id", "group", "inn"]).any():
        raise ValueError("Repeated entity in one settlement/year/group")
    if not frame.section_consistent.all():
        raise ValueError("Inconsistent sector coding")
    da = np.radians(frame.lat - frame.lat_point)
    db = np.radians(frame.lon - frame.lon_point)
    h = np.sin(da / 2) ** 2 + np.cos(np.radians(frame.lat)) * np.cos(np.radians(frame.lat_point)) * np.sin(db / 2) ** 2
    frame["coordinate_distance_km_recomputed"] = 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    frame["strict_house5km_recomputed"] = frame.geocoding_quality.eq("house") & frame.coordinate_distance_km_recomputed.le(5)
    if not np.allclose(frame.coordinate_distance_km, frame.coordinate_distance_km_recomputed):
        raise ValueError("Archived entity coordinate distances differ")
    frame["actual_worksite_confirmed"] = False
    frame["headcount"] = np.nan
    frame["source_id"] = "RFSD_ARCHIVED_LOCAL_ROW_EXTRACT_2016_2021"
    save(frame, out, "registered_entities")
    scope = pd.read_csv(archive / "documented_scope_members.csv", dtype={"oktmo_2021": str}).drop_duplicates("id")
    counts = []
    for _, place in scope.iterrows():
        for year in [2016, 2021]:
            for quality in ["exact_code", "exact_code_house5km"]:
                z = frame[frame.id.eq(place.id) & frame.year.eq(year) & frame.group.eq("agriculture01")]
                if quality.endswith("house5km"):
                    z = z[z.strict_house5km_recomputed]
                counts.append({"historical_axis_id": place.id, "name": place["name"],
                               "oktmo_2021": place.oktmo_2021, "year": year, "quality_mode": quality,
                               "agricultural_registered_entity_count": int(z.inn.nunique()),
                               "jobs": np.nan, "zero_means_no_accepted_source_record_not_no_economy": True})
    save(pd.DataFrame(counts), out, "registered_counts")
    return {"row_extract_observations": len(frame), "full_RFSD_microdata_rescanned": False,
            "agriculture_entities_by_year": {str(y): int(g.inn.nunique()) for y, g in frame.groupby("year")}}


def employer(js_path, out):
    if sha(js_path) != JS_SHA:
        raise ValueError("Employer application differs from dated reviewed snapshot")
    text = js_path.read_text()
    address = "453742, Республика Башкортостан, Учалинский район, село Уральск, улица Советская-6"
    if address not in text:
        raise ValueError("Contact address missing from employer source")
    match = re.search(r"P2=\[(.*?)\];function Pp", text, re.S)
    if not match:
        raise ValueError("Reviewed employer vacancy-category list not found")
    categories = re.findall(r'\{name:("(?:\\.|[^"\\])*"),payment:\d+,desc:("(?:\\.|[^"\\])*")', match.group(1))
    vacancies = pd.DataFrame([{"employer_id": "bairamgul", "occupation_label": json.loads(name),
                               "description": json.loads(desc), "observed_on": "2026-10-24",
                               "source_id": "BAIRAMGUL_WEBSITE_20261024", "number_of_open_posts": np.nan,
                               "posting_date_known": False, "site_location_confirmed": False}
                              for name, desc in categories])
    if len(vacancies) != 5:
        raise ValueError(f"Unexpected vacancy category count: {len(vacancies)}")
    save(vacancies, out, "vacancy_categories")
    evidence = pd.DataFrame([{
        "employer_id": "bairamgul", "name": "ООО «Агрофирма Байрамгул»", "settlement_name": "Уральск",
        "address": address, "contact_lon": 59.123512, "contact_lat": 54.122870,
        "coordinate_role": "website_contact_map_not_production_site",
        "coordinates_are_exact_office_entrance": False,
        "headcount": np.nan, "employment_catchment_established": False,
        "actual_production_site_geocoded": False, "observation_year": pd.NA,
        "retrieved_date": "2026-10-24", "source_id": "BAIRAMGUL_WEBSITE_20261024",
        "production_evidence": "employer_website_description_and_occupation_categories",
        "agricultural_employer_evidence_present": True,
        "external_agricultural_service_status": "unknown",
    }])
    save(evidence, out, "employer_evidence")
    quotes = []
    for marker in ["Землепользование хозяйства", "ООО «Агрофирма Байрамгул» создано", "Пшеница фуражная"]:
        p = text.find(marker)
        if p < 0:
            raise ValueError(f"Reviewed text marker missing: {marker}")
        quotes.append({"source_id": "BAIRAMGUL_WEBSITE_20261024", "source_locator": marker,
                       "source_character_offset": p, "excerpt": text[p:p+1500],
                       "meaning": "company_level_self_description_no_local_allocation", "retrieved_date": "2026-10-24"})
    (out / "employer_source_excerpts.json").write_text(json.dumps(quotes, ensure_ascii=False, indent=2) + "\n")
    return {"employers_with_first_party_contact": len(evidence), "vacancy_occupation_categories": len(vacancies),
            "jobs_observed": False, "worker_origins_observed": False}


def organisation_headcount(path, archive, out):
    """Use the FNS primary record; organisation headcount is not settlement jobs."""
    wanted = set(pd.read_csv(archive / "agro_legal_witnesses_2016_2021.csv", dtype={"inn": str}).inn)
    is_archive = zipfile.is_zipfile(path)
    if is_archive and sha(path) != FNS_SHA:
        raise ValueError("FNS archive differs from dated checked original")
    matches, sources = [], []
    total = 0
    def parse(data, member):
        nonlocal total
        total += data.count("<Документ ".encode())
        if not any(inn.encode() in data for inn in wanted):
            return
        root = ET.fromstring(data)
        for document in root.findall("Документ"):
            organisation = document.find("СведНП")
            value = document.find("СведССЧР")
            if organisation is None or organisation.attrib.get("ИННЮЛ") not in wanted:
                continue
            if value is None or not value.attrib.get("КолРаб", "").isdigit():
                raise ValueError("Nonnumeric FNS employee observation")
            matches.append({"inn": organisation.attrib["ИННЮЛ"], "organisation_name": organisation.attrib["НаимОрг"],
                            "reference_date": document.attrib["ДатаСост"], "publication_date": document.attrib["ДатаДок"],
                            "organisation_headcount": int(value.attrib["КолРаб"]),
                            "source_document_id": document.attrib["ИдДок"], "source_member": member,
                            "source_id": "FNS_SSHR_20260925", "reference_year": 2025,
                            "measure": "annual_average_employees_not_instantaneous_jobs",
                            "geography": "whole_legal_entity_no_worksite_addresses_in_source",
                            "settlement_jobs": np.nan, "commuting_origins_observed": False})
            sources.append({"member": member, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            (out / member).write_bytes(data)
    if is_archive:
        with zipfile.ZipFile(path) as bundle:
            for info in bundle.infolist():
                if info.filename.endswith(".xml"):
                    parse(bundle.read(info), info.filename)
    else:
        parse(path.read_bytes(), path.name)
    frame = pd.DataFrame(matches)
    if frame.empty or frame.duplicated(["inn", "reference_date"]).any():
        raise ValueError("Missing or conflicting FNS observations")
    if set(frame.reference_date) != {"31.12.2025"}:
        raise ValueError("Unexpected FNS reference date")
    save(frame, out, "organisation_headcount")
    # Keep actual local jobs unknown; this is a verified company-level measure.
    employer_path = out / "employer_evidence.parquet"
    evidence = pd.read_parquet(employer_path)
    selected = frame[frame.inn.eq("0270015537")]
    if len(selected) != 1:
        raise ValueError("Employer FNS observation not uniquely identified")
    evidence["organisation_inn"] = "0270015537"
    evidence["organisation_headcount_2025"] = int(selected.organisation_headcount.iloc[0])
    evidence["organisation_headcount_source_id"] = "FNS_SSHR_20260925"
    evidence["organisation_headcount_is_settlement_jobs"] = False
    save(evidence, out, "employer_evidence")
    manifest = {"source_url": FNS_URL, "full_archive_sha256": FNS_SHA,
                "whole_archive_scanned": is_archive, "documents_scanned": total,
                "wanted_inn": sorted(wanted), "matches": len(frame), "matched_members": sources,
                "missing_inn_not_interpreted_as_closure": sorted(wanted - set(frame.inn)),
                "geography": "organisation_not_establishment_or_settlement",
                "source_has_worksite_addresses": False}
    (out / "fns_source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def accepted_membership(path, archive, out):
    base = pd.read_parquet(path)
    legal = pd.read_csv(archive / "municipal_legal_membership.csv", dtype={"municipality_code": str})
    records = []
    for _, row in legal.iterrows():
        candidates = base[
            base.oktmo_2021.str.startswith(row.municipality_code, na=False)
            & base.settlement_name_2021.eq(row["name"])
            & base.district_raw_2021.eq("Учалинский муниципальный район")
            & base.region_norm_2021.str.contains("башкортостан", case=False, na=False)
        ]
        if len(candidates) != 1:
            raise ValueError(f"Municipal member not uniquely matched to accepted axis: {row['name']}")
        value = candidates.iloc[0]
        records.append({"name": row["name"], "municipality_code": row.municipality_code,
                        "municipality": row.municipality, "source_record_id_2021": value.source_record_id_2021,
                        "root": value.root, "oktmo_2021": value.oktmo_2021,
                        "population_2021": value.effective_population_2021,
                        "working_credit_present_2021": value.working_credit_present_2021,
                        "lat": value.accepted_latitude_2021, "lon": value.accepted_longitude_2021,
                        "previous_axis_matched": row.matched_axis,
                        "match_method": "legal_municipality_prefix_exact_name_region_district_2021",
                        "membership_source": row.membership_source,
                        "historical_boundary_equivalence_not_proven": True})
    membership = pd.DataFrame(records)
    if membership.source_record_id_2021.duplicated().any():
        raise ValueError("Repeated accepted municipal member")
    save(membership, out, "accepted_municipal_membership")
    mapping = membership.set_index("oktmo_2021").source_record_id_2021
    for name, column in [("registered_entities", "code"), ("registered_counts", "oktmo_2021")]:
        frame = pd.read_parquet(out / (name + ".parquet"))
        frame["source_record_id_2021"] = frame[column].map(mapping)
        if frame.source_record_id_2021.isna().any():
            raise ValueError(f"Unresolved registered evidence: {name}")
        frame["registration_year_not_assumed_actual_activity_year"] = True
        save(frame, out, name)
    evidence = pd.read_parquet(out / "employer_evidence.parquet")
    evidence["source_record_id_2021"] = mapping["80653491101"]
    save(evidence, out, "employer_evidence")
    return {"legal_members": len(legal), "accepted_2021_members": len(membership),
            "members_absent_from_old_axis_now_present": membership.loc[~membership.previous_axis_matched, "name"].tolist(),
            "population_not_used_to_allocate_agriculture": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agriculture-source", type=Path, required=True)
    parser.add_argument("--archive-inputs", type=Path, required=True)
    parser.add_argument("--employer-js", type=Path, required=True)
    parser.add_argument("--fns-source", type=Path, help="Dated full FNS ZIP or published selected original XML member")
    parser.add_argument("--accepted-population", type=Path, help="Accepted settlements_census_wide.parquet")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"scope": "local_agriculture_context_and_employer_evidence_not_jobs_or_flows",
              "agriculture": agriculture(args.agriculture_source, args.output),
              "registered_entities": entities(args.archive_inputs, args.output),
              "employer": employer(args.employer_js, args.output),
              "source_urls": {"agriculture": SOURCE_URL, "employer_js": JS_URL},
              "inputs": [{"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)} for p in
                         [args.agriculture_source, args.archive_inputs / "agro_legal_witnesses_2016_2021.csv",
                          args.archive_inputs / "documented_scope_members.csv",
                          args.archive_inputs / "municipal_legal_membership.csv", args.employer_js]]}
    if args.fns_source:
        result["organisation_headcount"] = organisation_headcount(args.fns_source, args.archive_inputs, args.output)
        result["inputs"].append({"path": str(args.fns_source), "bytes": args.fns_source.stat().st_size, "sha256": sha(args.fns_source)})
    if args.accepted_population:
        result["membership"] = accepted_membership(args.accepted_population, args.archive_inputs, args.output)
        result["inputs"].append({"path": str(args.accepted_population), "bytes": args.accepted_population.stat().st_size,
                                 "sha256": sha(args.accepted_population)})
    (args.output / "economy_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

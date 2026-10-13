"""Bounded registry of already-present population and code-history sources.

This is a discovery/eligibility registry, not a population table or an identity
crosswalk. Source-specific locators and row-level decisions remain in their
own evidence packages.
"""
from __future__ import annotations

from typing import Any, Iterable


REGISTRY_VERSION = "mass-source-registry-r1"

# All paths are root-relative. Callers supply local roots; this keeps the
# registry usable in a different checkout without editing source records.
ROOT_ROLES = {
    "checkout_root": "research repository checkout",
    "raw_root": "extracted raw source tree",
    "data_root": "released/processed data snapshot",
    "baseline_root": "baseline inventory bundle",
}
MANIFEST = {"root_role": "baseline_root", "relative_path": "output/input_manifest.parquet"}

SOURCE_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "source_id": "rosstat_2002_tom1_table_1_4",
        "title": "Всероссийская перепись населения 2002, Том 1, таблица 1.4",
        "source_family": "Rosstat census publication",
        "paths": ["data/raw/2002_official_tom1/1_TOM_01_04.xls",
                  "data/raw/2002_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf"],
        "path_root_roles": {"data/raw/2002_official_tom1/1_TOM_01_04.xls": "raw_root", "data/raw/2002_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf": "raw_root"},
        "hashes": {"data/raw/2002_official_tom1/1_TOM_01_04.xls": "745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3",
                   "data/raw/2002_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf": "50aaf5c73289383df757321871e617e6aafe31ed8a0235e05b213e72dc218c29"},
        "observed_years": [2002], "reference_date": "2002 census", "grain": "published settlement rows plus hierarchical/aggregate rows",
        "population_role": "census_primary_candidate", "may_be_denominator": True,
        "identifier_systems": ["historical OKATO where printed"],
        "source_fields": ["table", "sheet/row or PDF page/row", "raw label", "raw population", "row hierarchy/type"],
        "rights": "Official publication; no blanket redistribution terms recorded.",
        "limits": ["Filter parent totals and non-settlement rows; preserve exact source locator and hierarchy."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "rosstat_2010_tom1_and_tom11",
        "title": "ВПН-2010, Том 1 и Том 11",
        "source_family": "Rosstat census publication",
        "paths": ["data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf",
                  "data/raw/2010_official_tom11/pub-11-1-4.pdf"],
        "path_root_roles": {"data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf": "raw_root", "data/raw/2010_official_tom11/pub-11-1-4.pdf": "raw_root"},
        "hashes": {"data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf": "42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3",
                   "data/raw/2010_official_tom11/pub-11-1-4.pdf": "db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500"},
        "observed_years": [2010], "reference_date": "2010 census", "grain": "published settlement rows plus hierarchical/aggregate rows",
        "population_role": "census_primary_candidate", "may_be_denominator": True,
        "identifier_systems": ["historical OKATO where printed"],
        "source_fields": ["volume/table", "PDF page and printed page", "row label", "population", "sex totals where present", "hierarchy"],
        "rights": "Official publication; no blanket redistribution terms recorded.",
        "limits": ["Regional totals CSV is separate and region-grain only.", "Source-specific dash interpretation is required."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "rosstat_2021_tom1_table_5",
        "title": "ВПН-2020 (перепись 2021), Том 1, таблица 5",
        "source_family": "Rosstat census publication",
        "paths": ["data/raw/rosstat_2021/Tom1_tab-5_VPN-2020.xlsx"],
        "path_root_roles": {"data/raw/rosstat_2021/Tom1_tab-5_VPN-2020.xlsx": "raw_root"},
        "hashes": {"data/raw/rosstat_2021/Tom1_tab-5_VPN-2020.xlsx": "0b232b3d2ab5daa231568acc719ac6fda4fb0979a01a0da6bacc69be6f252474"},
        "observed_years": [2021], "reference_date": "2021 census", "grain": "published settlement rows plus region/municipal/urban subtotals",
        "population_role": "census_primary_candidate", "may_be_denominator": True,
        "identifier_systems": ["publication-native row key; OKTMO where present"],
        "source_fields": ["sheet/table/row", "raw name/type", "population", "men", "women", "source row hierarchy"],
        "rights": "Official publication; no blanket redistribution terms recorded.",
        "limits": ["Row-level scope review remains necessary; do not sum nested totals."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "lingvarium_census_workbooks",
        "title": "Lingvarium regional census workbooks, 2002/2010/2021",
        "source_family": "third-party census extracts",
        "paths": ["data/raw/2002/", "data/raw/2010/", "data/raw/2021/"],
        "path_root_roles": {"data/raw/2002/": "raw_root", "data/raw/2010/": "raw_root", "data/raw/2021/": "raw_root"},
        "hashes": {}, "observed_years": [2002, 2010, 2021], "reference_date": "census years",
        "grain": "mixed settlement and aggregate rows; workbook dependent",
        "population_role": "comparison_candidate", "may_be_denominator": False,
        "identifier_systems": ["varies by workbook; often OKATO/OKTMO"],
        "source_fields": ["workbook/sheet/row, row label/type, population, codes where present"],
        "rights": "Redistribution license not stated in reviewed source register; private baseline pending terms review.",
        "limits": ["Not a default replacement for direct official tables; do not redistribute complete workbooks or derived full extracts."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "tochno_2021_settlement_table",
        "title": "Если быть точным, 2021 settlements dataset v20251217",
        "source_family": "third-party 2021 census-derived dataset",
        "paths": ["data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"],
        "path_root_roles": {"data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet": "raw_root"},
        "hashes": {"data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet": "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14"},
        "observed_years": [2021], "reference_date": "2021 census", "grain": "176232 mixed-grain rows; 155748 rows labelled settlement",
        "population_role": "comparison_candidate", "may_be_denominator": False,
        "identifier_systems": ["OKTMO", "FIAS/Dadata IDs", "OKATO where populated"],
        "source_fields": ["object_level", "object_name", "oktmo", "population", "region", "municipality levels", "settlement", "FIAS/DaData identifiers and QC"],
        "rights": "CC BY 4.0 per SOURCES.md; attribute and version; license does not cover merged inputs.",
        "limits": ["Mixed object levels overlap; select exact settlement grain before any comparison."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "rosstat_yearbook_table_4_9",
        "title": "Российский статистический ежегодник 2024, таблица 4.9",
        "source_family": "Rosstat statistical yearbook",
        "paths": ["research_rebuild/evidence/discovery/official_sources_2010_2021_r2_yearbook/raw/rosstat_russian_statistical_yearbook_2024.pdf",
                  "research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930/manifest.json"],
        "path_root_roles": {"research_rebuild/evidence/discovery/official_sources_2010_2021_r2_yearbook/raw/rosstat_russian_statistical_yearbook_2024.pdf": "checkout_root", "research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930/manifest.json": "checkout_root"},
        "hashes": {}, "observed_years": [2002, 2010, 2021], "reference_date": "census-date columns; publication year 2024",
        "grain": "163 large cities (>=100k) plus 9 held rows in candidate manifest",
        "population_role": "partial_crosscheck", "may_be_denominator": False,
        "identifier_systems": ["city names; no comprehensive settlement key"],
        "source_fields": ["PDF page/printed page, city label, census-date population in thousands"],
        "rights": "Official publication; source-specific reuse terms not stated in project register.",
        "limits": ["Partial large-city series, not annual and not a national settlement denominator; 9 exception rows held."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "wikidata_population_claims",
        "title": "Cached Wikidata full entities and truthy claims",
        "source_family": "community knowledge graph",
        "paths": ["data/raw/wikidata_entities_full/", "data/raw/wikidata_truthy_claims/", "data/processed/wikidata_population_long.parquet"],
        "path_root_roles": {"data/raw/wikidata_entities_full/": "raw_root", "data/raw/wikidata_truthy_claims/": "raw_root", "data/processed/wikidata_population_long.parquet": "data_root"},
        "hashes": {"data/processed/wikidata_population_long.parquet": "cc996ed58b96964ff6db356cd97a3351a4c73de7f5086baf21bbee04936e5d51"},
        "observed_years": [], "reference_date": "claim qualifiers may encode dates; cache retrieval is not an observation date",
        "grain": "entity claims; settlement/aggregate identity and time vary by claim",
        "population_role": "auxiliary_candidate", "may_be_denominator": False,
        "identifier_systems": ["Wikidata QID", "OKTMO claim (P764)", "OKATO claim (P721)", "population claim (P1082)"],
        "source_fields": ["entity revision/modified, statement ID/rank, qualifiers, references; truthy cache only item/property/value/retrieved_at"],
        "rights": "CC0 per SOURCES.md.",
        "limits": ["Use full-entity qualifiers/references for temporal claims; truthy cache drops both. Census-source dependence and row grain may be unknown."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "wikipedia_statistical_modules",
        "title": "Russian Wikipedia statistical modules and extracted observations",
        "source_family": "community-maintained secondary compilation",
        "paths": ["data/raw/wikipedia_statistical/", "data/processed/wikipedia_statistical_population_raw.parquet"],
        "path_root_roles": {"data/raw/wikipedia_statistical/": "raw_root", "data/processed/wikipedia_statistical_population_raw.parquet": "data_root"},
        "hashes": {"data/processed/wikipedia_statistical_population_raw.parquet": "f35b9b8a02a24c33b266949eb8b23769da8fa54894774eb2b19236ca3331882a"},
        "observed_years": [], "reference_date": "module-specific years; revision/date evidence required",
        "grain": "mixed named localities and administrative aggregates",
        "population_role": "auxiliary_candidate", "may_be_denominator": False,
        "identifier_systems": ["region/module code, title; not a stable historic settlement key"],
        "source_fields": ["module code, region, source hash, Wikipedia title, observation year, population, aggregate flag"],
        "rights": "CC BY-SA per SOURCES.md; retain revision/permanent links and attribution; review share-alike.",
        "limits": ["Secondary data; per-page revision and source citation needed; aggregate rows excluded."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "rosstat_municipal_economy_annual",
        "title": "Rosstat municipal economy indicators by year (82 regional codes)",
        "source_family": "Rosstat municipal statistical tables",
        "paths": ["data/raw/rosstat_municipal_economy/", "data/processed/municipal_economic_observations_core.parquet"],
        "path_root_roles": {"data/raw/rosstat_municipal_economy/": "raw_root", "data/processed/municipal_economic_observations_core.parquet": "data_root"},
        "hashes": {"data/processed/municipal_economic_observations_core.parquet": "ea574ff7c2cdba5fc4e5308d43104294f59737931e232a2a77e10e3b2cbc3c6a"},
        "observed_years": [], "year_span": [2007, 2025], "reference_date": "indicator-specific annual periods, with gaps",
        "grain": "municipality × indicator × year, not settlement",
        "population_role": "municipal_covariate", "may_be_denominator": False,
        "identifier_systems": ["municipality OKTMO candidates; regional database code"],
        "source_fields": ["region_database_code, municipality_name_raw, municipality_oktmo, metric_id/series, year, numeric/text value, source row/table, query/result URL and retrieval time"],
        "rights": "Rosstat table terms are source-specific; no blanket project redistribution terms recorded.",
        "limits": ["No population metric in inspected cached catalog; municipal values cannot stand in for settlements; no interpolation."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "historical_okato_dump_2009",
        "title": "Historical OKATO 142 dump dated 2009",
        "source_family": "historical classifier mirror",
        "paths": ["data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql", "data/processed/historical_okato_142_2009.parquet"],
        "path_root_roles": {"data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql": "raw_root", "data/processed/historical_okato_142_2009.parquet": "data_root"},
        "hashes": {"data/processed/historical_okato_142_2009.parquet": "6e1b56aa8f01d3f9fd7f74eb6817b2e92fcd4aea2bc43b6c8860cf7a9413fc82"},
        "observed_years": [], "reference_date": "2009 archive", "grain": "classifier codes; settlement flag/type not guaranteed census grain",
        "population_role": "identifier_history", "may_be_denominator": False,
        "identifier_systems": ["OKATO"], "source_fields": ["code, name/name_full, status, is_settlement, snapshot revision/source URL"],
        "rights": "Historical classifier terms not confirmed; no blanket permission inferred.",
        "limits": ["Do not treat classifier name/status as dated legal lineage or proof of census identity."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "geokladr_okato_oktmo_2011",
        "title": "GeoKLADR/OKATO DBF snapshot with 2011-era OKTMO fields",
        "source_family": "historical geography/classifier mirror",
        "paths": ["data/raw/historical_geography/geokladr_okato_2011/okato.dbf", "data/raw/historical_geography/geokladr_okato_2011/socr_np.dbf", "data/processed/historical_geokladr_coordinates_2011.parquet"],
        "path_root_roles": {"data/raw/historical_geography/geokladr_okato_2011/okato.dbf": "raw_root", "data/raw/historical_geography/geokladr_okato_2011/socr_np.dbf": "raw_root", "data/processed/historical_geokladr_coordinates_2011.parquet": "data_root"},
        "hashes": {"data/raw/historical_geography/geokladr_okato_2011/okato.dbf": "d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650",
                   "data/raw/historical_geography/geokladr_okato_2011/socr_np.dbf": "71d41a34b1f1eb1de7d97d6f1114a024e7210e941336f2e311119721ff8820da"},
        "observed_years": [], "reference_date": "2011 snapshot/update metadata", "grain": "classifier/place records; may include non-settlement units",
        "population_role": "identifier_history", "may_be_denominator": False,
        "identifier_systems": ["OKATO", "KLADR", "OKTMO"],
        "source_fields": ["TER/KOD1-3/name/type/status/update date/OKTMO/coordinates; processed table also stores population_source_value"],
        "rights": "Terms vary by source component, including a CC BY-NC-SA coordinate mirror per SOURCES.md; do not infer blanket license.",
        "limits": ["Population field semantics and object grain need validation; not census population. Codes are dated candidates, not current identity."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "historical_settlement_events",
        "title": "Project historical entity-lineage and settlement-event registries",
        "source_family": "curated project evidence registry",
        "paths": ["config/historical_entity_lineage.csv", "config/settlement_events.csv", "data/processed/census_lineage_events.parquet", "data/processed/historical_relations.parquet"],
        "path_root_roles": {"config/historical_entity_lineage.csv": "checkout_root", "config/settlement_events.csv": "checkout_root", "data/processed/census_lineage_events.parquet": "data_root", "data/processed/historical_relations.parquet": "data_root"},
        "hashes": {}, "observed_years": [], "reference_date": "event effective dates vary",
        "grain": "claimed transition/event edges; legacy evidence not uniformly independently reviewed",
        "population_role": "event_evidence", "may_be_denominator": False,
        "identifier_systems": ["project settlement IDs", "OKATO/OKTMO as evidence when linked"],
        "source_fields": ["event ID/type/effective date/from/to IDs/legal act or evidence URL/note/registry file+row/evidence status"],
        "rights": "Project-curated registry; underlying evidence inherits source-specific terms.",
        "limits": ["Legacy rows remain pending independent review; register does not itself establish successor identity."],
        "manifest_path": MANIFEST,
    },
    {
        "source_id": "rosstat_1989_urban_scan",
        "title": "Candidate 1989 urban population scan",
        "source_family": "historical statistical scan; bibliographic identification pending",
        "paths": ["data/raw/1989/urban_scan.pdf"],
        "path_root_roles": {"data/raw/1989/urban_scan.pdf": "raw_root"},
        "hashes": {"data/raw/1989/urban_scan.pdf": "e0144d44e94b0c324ad573daeb80621265a0ce01e03bdc9c3e676eaf5ec892a9"},
        "observed_years": [1989], "reference_date": "1989 (scan title/coverage still to be verified)",
        "grain": "unknown until scan title, table, hierarchy and page scope are checked",
        "population_role": "unverified_historical_candidate", "may_be_denominator": False,
        "identifier_systems": ["unknown"], "source_fields": ["PDF page/table/row and printed units must be established"],
        "rights": "Unknown pending bibliographic/rights verification.",
        "limits": ["Do not publish extracted counts or use as a denominator until source and row grain are verified."],
        "manifest_path": MANIFEST,
    },
)


def validate_registry(entries: Iterable[dict[str, Any]] = SOURCE_REGISTRY) -> None:
    """Raise ValueError for incomplete provenance or unsafe denominator claims."""
    required = {
        "source_id", "title", "source_family", "paths", "path_root_roles", "observed_years",
        "reference_date", "grain", "population_role", "may_be_denominator",
        "identifier_systems", "source_fields", "rights", "limits", "manifest_path",
    }
    seen: set[str] = set()
    for entry in entries:
        missing = required - entry.keys()
        if missing:
            raise ValueError(f"{entry.get('source_id', '<unknown>')} missing fields: {sorted(missing)}")
        source_id = entry["source_id"]
        if source_id in seen:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        if not entry["paths"] or not entry["rights"] or not entry["source_fields"]:
            raise ValueError(f"{source_id} lacks locator, rights, or source fields")
        if set(entry["path_root_roles"]) != set(entry["paths"]):
            raise ValueError(f"{source_id} has paths without root roles")
        if not set(entry.get("hashes", {})).issubset(entry["paths"]):
            raise ValueError(f"{source_id} pins a hash to an unregistered path")
        if any(role not in ROOT_ROLES for role in entry["path_root_roles"].values()):
            raise ValueError(f"{source_id} references an unknown root role")
        if any(path.startswith("/") for path in entry["paths"]):
            raise ValueError(f"{source_id} contains a nonportable absolute path")
        if entry["may_be_denominator"]:
            if entry["population_role"] != "census_primary_candidate":
                raise ValueError(f"non-primary source cannot be denominator: {source_id}")
            if "census" not in entry["reference_date"].lower():
                raise ValueError(f"denominator candidate lacks census-date basis: {source_id}")
        if entry["grain"].lower().startswith(("municipality ×", "municipal aggregate")) and entry["may_be_denominator"]:
            raise ValueError(f"municipal aggregate cannot be settlement denominator: {source_id}")
        if entry.get("may_interpolate", False):
            raise ValueError(f"registry must never authorize population interpolation: {source_id}")


def registry_payload() -> dict[str, Any]:
    validate_registry()
    return {"registry_version": REGISTRY_VERSION, "input_manifest": MANIFEST,
            "root_roles": ROOT_ROLES, "sources": list(SOURCE_REGISTRY)}

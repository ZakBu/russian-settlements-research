import gzip
import json
from pathlib import Path

import pandas as pd

from research_rebuild.mass_linkage.wikidata_evidence import (
    normalize_code,
    reconstruct,
    _statement_row,
)


def snak(prop, value, datatype="external-id"):
    return {"snaktype": "value", "property": prop,
            "datavalue": {"value": value, "type": "string"}, "datatype": datatype}


def statement(qid, prop, value, rank="normal", refs=None):
    if prop in {"P31", "P131", "P17"}:
        val = {"entity-type": "item", "numeric-id": int(value[1:]), "id": value}
        datatype = "wikibase-entityid"
        dvtype = "wikibase-entityid"
    elif prop == "P625":
        val = value
        datatype = "globe-coordinate"
        dvtype = "globecoordinate"
    else:
        val = value
        datatype = "external-id"
        dvtype = "string"
    mainsnak = {"snaktype": "value", "property": prop,
                "datavalue": {"value": val, "type": dvtype}, "datatype": datatype}
    return {"mainsnak": mainsnak, "type": "statement", "id": f"{qid}${prop}{value}",
            "rank": rank, "qualifiers": {"P585": [{"datavalue": {"value": {"time": "+2021-01-01T00:00:00Z"}}}]},
            "references": refs or [{"snaks": {"P248": [{"datavalue": {"value": {"id": "Q1"}}}]}}]}


def entity(qid, oktmo, okato, label, types, longitude=179.5, oktmo_rank="normal"):
    claims = {
        "P764": [statement(qid, "P764", oktmo, rank=oktmo_rank)],
        "P721": [statement(qid, "P721", okato)],
        "P625": [statement(qid, "P625", {"latitude": 66.0, "longitude": longitude,
                 "precision": 0.01, "globe": "http://www.wikidata.org/entity/Q2"})],
        "P31": [statement(qid, "P31", t) for t in types],
        "P131": [statement(qid, "P131", "Q10")],
        "P17": [statement(qid, "P17", "Q159")],
    }
    return {"id": qid, "lastrevid": 42, "modified": "2026-08-31T00:00:00Z",
            "labels": {"ru": {"value": label}},
            "descriptions": {"ru": {"value": "Населённый пункт"}},
            "aliases": {"ru": [{"value": label + " старое"}]}, "claims": claims}


def test_normalization_does_not_repair_codes_implicitly():
    assert normalize_code("00123456789") == "00123456789"
    assert normalize_code("1234567890") == "1234567890"
    assert normalize_code("1234567890.0") == "1234567890"
    assert normalize_code("12-345") is None
    assert normalize_code(None) is None


def test_statement_rows_keep_raw_claim_lineage_rank_qualifiers_references():
    s = statement("Q11", "P764", "00123456789", rank="normal")
    row = _statement_row("Q11", "P764", s, "batch_0001.json.gz")
    assert row["value_normalized"] == "00123456789"
    assert row["statement_id"] == s["id"]
    assert row["rank"] == "normal" and row["is_nondeprecated"] is True
    assert "P585" in row["qualifiers_json"] and "Q1" in row["references_json"]
    deprecated = _statement_row("Q11", "P764", statement("Q11", "P764", "1", "deprecated"), "b.gz")
    assert deprecated["is_nondeprecated"] is False


def test_reconstruct_requires_exact_codes_preserves_provider_separation_and_flags_competition(tmp_path):
    entity_dir, truthy_dir = tmp_path / "entities", tmp_path / "truthy"
    entity_dir.mkdir(); truthy_dir.mkdir()
    q11 = entity("Q11", "00123456789", "99123456789", "Северное", ["Q486972"], longitude=-175.0)
    q12 = entity("Q12", "00123456789", "99123456789", "Северное район", ["Q56061"])
    # This item only matches if the source value is padded; that repair is
    # diagnostic-only and must not create a binding.
    q13 = entity("Q13", "01234567890", "99123456788", "Короткий код", ["Q486972"])
    payload = {"retrieved_at_utc": "2026-08-31T00:00:00Z", "payload": {"entities": {e["id"]: e for e in [q11, q12, q13]}}}
    with gzip.open(entity_dir / "batch_0001.json.gz", "wt", encoding="utf-8") as f:
        json.dump(payload, f)
    with gzip.open(truthy_dir / "batch_0001.jsonl.gz", "wt", encoding="utf-8") as f:
        for qid, prop, value in [("Q11", "P764", "00123456789"), ("Q11", "P721", "99123456789")]:
            f.write(json.dumps({"item": f"http://www.wikidata.org/entity/{qid}", "property": f"http://www.wikidata.org/entity/{prop}", "value": value}) + "\n")
    source = pd.DataFrame([
        {"source_record_id": "src-a", "census_year": 2021, "oktmo": "00123456789", "okato": "99123456789"},
        {"source_record_id": "src-b", "census_year": 2021, "oktmo": "1234567890", "okato": "99123456788"},
    ])
    source_path = tmp_path / "source.parquet"
    source.to_parquet(source_path, index=False)
    output = tmp_path / "out"
    result = reconstruct(source_path, entity_dir, truthy_dir, output)
    bindings = pd.read_parquet(output / "point_bindings.parquet")
    assert set(bindings.wikidata_qid) == {"Q11", "Q12"}  # short source code is never padded/joined
    q11row = bindings.loc[bindings.wikidata_qid == "Q11"].iloc[0]
    assert q11row.provider_p721_okato_match_same_qid
    assert not q11row.identifier_sources_independent
    assert q11row.coordinate_provider_id == "Q11"
    assert q11row.source_record_id == "src-a" and q11row.coordinate_source_record_id == "wikidata:Q11"
    assert q11row.competing_qids_for_p764_code
    assert q11row.exact_p764_truthy_cache_match and q11row.exact_p721_truthy_cache_match
    assert q11row.p625_valid_wgs84_point_count == 1
    assert "-175.0" in q11row.p625_points_json  # negative Chukotka longitude survives
    q12row = bindings.loc[bindings.wikidata_qid == "Q12"].iloc[0]
    assert q12row.known_admin_only_type
    assert q12row.identity_decision == "candidate_only_no_acceptance"
    claims = pd.read_parquet(output / "claims.parquet")
    raw = claims.loc[(claims.wikidata_qid == "Q11") & (claims.property == "P764")].iloc[0]
    assert raw.statement_id and "P585" in raw.qualifiers_json and raw.references_json
    assert result["counts"]["source_rows_short_or_other_length_oktmo"] == 1

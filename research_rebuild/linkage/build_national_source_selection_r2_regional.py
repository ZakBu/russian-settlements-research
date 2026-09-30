"""Apply independently reviewed 2010 primary source slices for four regions.

This is a source-selection release only. It does not create identity, geometry,
or coordinate decisions. Prior observations are retained in the archive and
prior claims are projected only when their exact endpoints remain selected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT / "research_rebuild/evidence/releases/national_source_selection_r1_20260930"
R1_MANIFEST = R1 / "release_manifest.json"
NW_DIR = ROOT / "research_rebuild/evidence/releases/2010_nw_primary_source_selection_proposals_r4_20260930"
NW_MANIFEST = NW_DIR / "source_manifest_2010_nw_selection_proposals_r4.json"
ARK_DIR = ROOT / "research_rebuild/evidence/releases/arkhangelsk_2010_primary_selection_component_r1_20260930"
ARK_MANIFEST = ARK_DIR / "manifest.json"
R5B = ROOT / "research_rebuild/evidence/releases/national_reviewed_admissions_r5b_yearbook_20260930"
R5B_MANIFEST = R5B / "release_manifest.json"
BASELINE = ROOT / "research_audit/output/audited_census_snapshots.parquet"

R1_MANIFEST_SHA = "37b4bf695087032e13baac88e7c432849bf3aa4543e40bcd2a5df6e8429242f6"
NW_MANIFEST_SHA = "6cd2e9563f93487ecc673a2ff58bf8463543d0022795db120cd2073f2fdba3ad"
ARK_MANIFEST_SHA = "b57b744e418c2bd7216514deac719e4ae614200ecc0d5da64e0be162f587caf2"
R5B_MANIFEST_SHA = "0bf4c442df7e1e3a0c9148c08c7cde2f43235ebde6ca608b762891d8ee26093c"
R1_SELECTED_SHA = "dd8d437c1a1f5cebf2b45c55e7a6e2015f3c1a295cade827a71bb76189a485df"
R1_ARCHIVE_SHA = "86778134f7b9fb3c3af43788d9007c6c8a0d3350d17fc2653d45c224172776ad"
BASELINE_SHA = "b42a1230519c8303079ce2465bb28d3c4af357ece5dbdd26e4f5de2c3de02c2b"
NW_REVIEWS = {
    "murmansk": "2d29494099dfccd0b8120af61a99182173f5dae827d223c3e5cc87743f498b3e",
    "kaliningrad": "24a4debc54cdac4a244aa99467df078a86183616645fb37c3ec233ff1bfd7756",
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def verify(path: Path, expected: str) -> None:
    if not path.is_file() or sha(path) != expected:
        raise ValueError(f"required frozen input missing or changed: {path}")

def clean(v) -> str:
    if pd.isna(v):
        return ""
    return " ".join(str(v).casefold().replace("ё", "е").split())

def load_inputs():
    verify(R1_MANIFEST, R1_MANIFEST_SHA)
    verify(R1 / "selected_observations.parquet", R1_SELECTED_SHA)
    verify(R1 / "excluded_source_rows.csv", R1_ARCHIVE_SHA)
    verify(BASELINE, BASELINE_SHA)
    verify(NW_MANIFEST, NW_MANIFEST_SHA)
    verify(ARK_MANIFEST, ARK_MANIFEST_SHA)
    nw_manifest = json.loads(NW_MANIFEST.read_text(encoding="utf-8"))
    ark_manifest = json.loads(ARK_MANIFEST.read_text(encoding="utf-8"))
    r1_manifest = json.loads(R1_MANIFEST.read_text(encoding="utf-8"))
    for name, rec in r1_manifest["outputs"].items():
        verify(R1 / name, rec["sha256"])
    for name, rec in nw_manifest["outputs"].items():
        verify(NW_DIR / name, rec["sha256"])
    if nw_manifest.get("status") != "review_proposal_only_no_snapshot_mutations_supersedes_r3":
        raise ValueError("NW source package is not the expected proposal release")
    for region, review_sha in NW_REVIEWS.items():
        reviews = nw_manifest["independent_review_evidence"][region]
        if not any(rec["sha256"] == review_sha for rec in reviews.values()):
            raise ValueError(f"{region} independent review hash is not pinned in proposal manifest")
    source_manifest_docs = {}
    for region, rec in nw_manifest["source_manifests"].items():
        source_manifest_path = ROOT / rec["path"]
        verify(source_manifest_path, rec["sha256"])
        source_manifest_docs[region] = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if ark_manifest.get("independent_review_status") != "PASS_PROVISIONAL_OFFICIAL_PRIMARY_SLICE_WITH_VERSION_HISTORY_CAVEAT":
        raise ValueError("Arkhangelsk/NAO slice lacks expected independent source-slice verdict")
    for p, rec in nw_manifest["source_files"]["murmansk"].items():
        verify(ROOT / p, rec["sha256"])
    for p, rec in nw_manifest["source_files"]["kaliningrad"].items():
        verify(ROOT / p, rec["sha256"])
    for region, doc in source_manifest_docs.items():
        # Verify the actual primary files and auxiliary count/legend evidence used to interpret rows.
        for key, path_key, sha_key in [
            ("population_source", "population_source_locator", "population_source_sha256"),
            ("source", "source_locator", "source_sha256"),
            ("grouping_source", "grouping_source_locator", "grouping_source_sha256"),
        ]:
            if path_key in doc and sha_key in doc:
                verify(ROOT / doc[path_key], doc[sha_key])
    for rec in ark_manifest["inputs"].values():
        verify(ROOT / rec["path"], rec["sha256"])
    for name, rec in ark_manifest["outputs"].items():
        verify(ARK_DIR / name, rec["sha256"])
    verify(R5B_MANIFEST, R5B_MANIFEST_SHA)
    r5b_manifest=json.loads(R5B_MANIFEST.read_text(encoding="utf-8"))
    for name, rec in r5b_manifest["outputs"].items():
        verify(R5B / name, rec["sha256"])
    # Pin all machine inputs used below, including proposal tables and the R5b claim ledger.
    paths = {
        "murmansk": NW_DIR / "murmansk_2010_primary_population_selection_proposal.csv",
        "kaliningrad": NW_DIR / "kaliningrad_2010_primary_population_selection_proposal.csv",
        "ark": ARK_DIR / "arkhangelsk_2010_primary_selection_component.csv",
        "r1_selected": R1 / "selected_observations.parquet",
        "r1_archive": R1 / "excluded_source_rows.csv",
        "r1_components": R1 / "component_ledger.csv",
        "r1_assertions": R1 / "source_selection_assertions.csv",
        "baseline": BASELINE,
        "r5b_edges": R5B / "identity_edges_accepted.csv",
        "r5b_coords": R5B / "coordinate_admissions.csv",
        "r5b_bindings": R5B / "publication_bindings.csv",
        "tom11_pdf": ROOT / "data/raw/2010_official_tom11/pub-11-1-4.pdf",
    }
    for p in paths.values():
        if not p.is_file():
            raise FileNotFoundError(f"required release input missing: {p}")
    return paths, nw_manifest, ark_manifest

def std_row(template_columns, *, sid, source_path, source_sha, locator, raw_name,
            name, typ, region, scope, population, raw_population, men=None, women=None,
            district=None, municipality=None, extraction_version, quality, note):
    row = {c: pd.NA for c in template_columns}
    name_norm, type_norm, region_norm = clean(name), clean(typ), clean(region)
    row.update({
        "source_record_id": sid, "census_year": 2010,
        "source_file": source_path, "source_path": source_path, "source_sha256": source_sha,
        "source_sheet": "source-row", "source_row": pd.NA, "source_native_id": sid,
        "source_locator": locator, "source_name_raw": raw_name,
        "source_population_raw": raw_population, "settlement_name": name,
        "settlement_type": typ if pd.notna(typ) else pd.NA, "region_raw": region, "region_norm": region_norm,
        "district_raw": district, "municipality_raw": municipality,
        "district_norm": clean(district), "municipality_norm": clean(municipality),
        "population": population, "men": men, "women": women,
        "latitude": pd.NA, "longitude": pd.NA, "coordinate_source": pd.NA,
        "coordinate_quality": pd.NA, "coverage_status": "selected_reviewed_primary_source_no_identity_or_point_claim",
        "population_scope": scope, "name_norm": name_norm, "type_norm": type_norm,
        "derivation_note": note, "is_additive_settlement_record": True,
        "analysis_population_additive": True, "entity_grain_status": "atomic_settlement_source_row" if type_norm else "named_locality_type_unresolved",
        "population_value_quality": quality, "recovered_official_city_record": type_norm == "город",
        "extraction_version": extraction_version,
        "source_selection_component": "national_2010_regional_primary_r2",
        "identity_admission": "none", "coordinate_admission": "none",
    })
    return row

def make_nw_rows(df, template_columns, region_key):
    conf = {
        "murmansk": {
            "region": "Мурманская область",
            "path": "research_rebuild/evidence/ingestion/sources/murmansk_2010_official/murmansk_population_by_sex_municipalities.doc",
            "sha": "d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57",
            "extractor": "murmansk-2010-population-by-sex-candidate-r1",
            "review": NW_REVIEWS["murmansk"],
        },
        "kaliningrad": {
            "region": "Калининградская область",
            "path": "research_rebuild/evidence/ingestion/sources/kaliningrad_2010_official/kaliningrad_2010_tom1.xlsx",
            "sha": "7e17a4bdb54e3ee8ff014c4311396f84c01b7f3ed38d12f4f9c1f9e6b100705f",
            "extractor": "kaliningrad-2010-tom1-settlements-candidate-r2",
            "review": NW_REVIEWS["kaliningrad"],
        },
    }[region_key]
    rows = []
    for r in df.itertuples(index=False):
        typ = getattr(r, "candidate_source_type")
        pop = int(r.primary_population_proposal) if pd.notna(r.primary_population_proposal) else pd.NA
        # Reviewed derivations are explicit; raw source cell remains in the observation.
        if region_key == "murmansk" and r.candidate_population_status == "raw_dash":
            if r.population_interpretation_method != "closed_universe_zero_bin_count_match":
                raise ValueError(f"unsubstantiated Murmansk dash interpretation: {r.candidate_source_record_id}")
        if region_key == "kaliningrad" and r.candidate_population_status == "source_derived_zero_from_volume_legend":
            if r.population_interpretation_method != "volume_wide_dash_legend":
                raise ValueError(f"unsubstantiated Kaliningrad dash interpretation: {r.candidate_source_record_id}")
        row = std_row(template_columns,
            sid=r.candidate_source_record_id, source_path=conf["path"], source_sha=conf["sha"],
            locator=r.candidate_source_locator, raw_name=r.candidate_raw_label,
            name=r.candidate_normalized_name, typ=typ, region=conf["region"],
            scope="settlement_population_2010_census_date" if pd.notna(typ) else "source_named_locality_population_type_unresolved", population=pop,
            raw_population=r.candidate_raw_population,
            men=int(r.candidate_men_value) if pd.notna(r.candidate_men_value) else pd.NA,
            women=int(r.candidate_women_value) if pd.notna(r.candidate_women_value) else pd.NA,
            district=r.candidate_district_raw, municipality=r.candidate_municipality_raw,
            extraction_version=conf["extractor"],
            quality=("reviewed_primary_reported_value" if r.candidate_population_status == "reported_value"
                     else "reviewed_context_specific_dash_interpretation"),
            note=f"Independent source-selection review {conf['review']}; population source choice only, identity and point remain unadmitted.")
        row["region_norm"] = "мурманская" if region_key == "murmansk" else "калининградская"
        rows.append(row)
        rows[-1]["source_sheet"] = "table1" if region_key == "murmansk" else "4"
        if region_key == "murmansk":
            suffix=str(r.candidate_source_record_id).rsplit(":R",1)[-1]
            rows[-1]["source_row"] = int(suffix)
        else:
            import re
            match=re.search(r"!A(\d+):F\d+",str(r.candidate_source_locator))
            rows[-1]["source_row"] = int(match.group(1)) if match else pd.NA
    return pd.DataFrame(rows, columns=template_columns)

def make_ark_rows(df, template_columns):
    html_hash = "729fecf5845bd9f1e049c85b2659bfd077dfd2d2a01fecbc9d21cb83b7b9e486"
    pdf_hash = "42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3"
    html_path = "research_rebuild/evidence/ingestion/arkhangelsk_2010_archived_page_audit_r2_region_join/arkhangelsk_2010_archived_original.html"
    pdf_path = "data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf"
    rows=[]
    for r in df.itertuples(index=False):
        if not bool(r.in_disjoint_place_slice):
            raise ValueError(f"Ark/NAO source row outside reviewed disjoint place slice: {r.source_record_id}")
        scope = str(r.coverage_admin_scope)
        region = "Ненецкий автономный округ" if scope == "NAO" else "Архангельская область"
        sh = str(r.source_sha256)
        if sh == html_hash:
            source_path = html_path
        elif sh == pdf_hash:
            source_path = pdf_path
        else:
            raise ValueError(f"unrecognized Ark/NAO source hash {sh}")
        pop = int(r.population) if pd.notna(r.population) else pd.NA
        # Source labels carry the name and source type; normalized source fields are preserved.
        row=std_row(template_columns,
            sid=r.source_record_id, source_path=source_path, source_sha=sh,
            locator=r.source_logical_locator, raw_name=r.label_raw,
            name=r.source_name_normalized, typ=r.source_type_normalized, region=region,
            scope="settlement_population_2010_census_date", population=pop,
            raw_population=r.population_raw, extraction_version="arkhangelsk-2010-archived-doc-review-r2",
            quality="reviewed_primary_source_value_or_null", note=(
                "Independently reviewed disjoint Arkhangelsk-exclusive/NAO primary slice; one raw dash remains null. "
                "Known sum is compared with inclusive official control separately; identity/point remain unadmitted."))
        row["region_norm"] = "ненецкий" if scope == "NAO" else "архангельская"
        rows.append(row)
    return pd.DataFrame(rows, columns=template_columns)

def create_binding_candidates(proposals: dict[str, pd.DataFrame], ark: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    """Emit review candidates, never accepted bindings, for one-to-one predecessor keys."""
    allrows=[]
    for key, d in proposals.items():
        for r in d.itertuples(index=False):
            try: ids=json.loads(r.predecessor_source_record_ids_json or "[]")
            except Exception: ids=[]
            for oldid in ids:
                allrows.append({"component":key,"new_source_record_id":r.candidate_source_record_id,
                    "old_source_record_id":oldid,"new_name":r.candidate_normalized_name,
                    "new_type":r.candidate_normalized_type,"new_population":r.primary_population_proposal,
                    "new_population_status":r.candidate_population_status,
                    "old_population":r.predecessor_population,"key_match_status":r.match_status,
                    "candidate_input_locator":r.candidate_source_locator,
                    "new_raw_name":r.candidate_raw_label,
                    "new_source_sha256":("d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57" if key=="murmansk" else "7e17a4bdb54e3ee8ff014c4311396f84c01b7f3ed38d12f4f9c1f9e6b100705f"),
                    "new_source_path":("research_rebuild/evidence/ingestion/sources/murmansk_2010_official/murmansk_population_by_sex_municipalities.doc" if key=="murmansk" else "research_rebuild/evidence/ingestion/sources/kaliningrad_2010_official/kaliningrad_2010_tom1.xlsx"),
                    "new_region_raw":("Мурманская область" if key=="murmansk" else "Калининградская область"),
                    "new_region_norm":{"murmansk":"мурманская","kaliningrad":"калининградская"}[key],"new_admin_context":r.candidate_district_raw if pd.notna(r.candidate_district_raw) else r.candidate_municipality_raw,
                    "new_source_record_grain":"reviewed named locality source row; urban/rural source group preserved"})
    old_lookup=old.drop_duplicates("source_record_id").set_index("source_record_id")
    for r in ark.itertuples(index=False):
        try: ids=json.loads(r.legacy_candidate_source_record_ids_json or "[]")
        except Exception: ids=[]
        for oldid in ids:
            allrows.append({"component":"arkhangelsk_nao","new_source_record_id":r.source_record_id,
                "old_source_record_id":oldid,"new_name":r.source_name_normalized,
                "new_type":r.source_type_normalized,"new_population":r.population_value,
                "new_population_status":"reported_value" if pd.notna(r.population_raw) and str(r.population_raw).strip()!="-" else "raw_dash_or_null",
                "old_population":old_lookup.loc[oldid,"population"] if oldid in old_lookup.index else pd.NA,
                "key_match_status":r.legacy_match_status,
                "candidate_input_locator":r.source_logical_locator,
                "new_raw_name":r.label_raw,"new_source_sha256":r.source_sha256,
                "new_source_path":( "data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf" if r.source_sha256=="42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3" else "research_rebuild/evidence/ingestion/arkhangelsk_2010_archived_page_audit_r2_region_join/arkhangelsk_2010_archived_original.html"),
                "new_region_raw":"Ненецкий автономный округ" if r.coverage_admin_scope=="NAO" else "Архангельская область",
                "new_region_norm":"ненецкий" if r.coverage_admin_scope=="NAO" else "архангельская",
                "new_admin_context":r.coverage_admin_scope,"new_source_record_grain":"independently reviewed disjoint atomic locality row"})
    c=pd.DataFrame(allrows)
    if c.empty: return c
    selected_old=set(old.source_record_id.astype(str))
    c=c[c.old_source_record_id.astype(str).isin(selected_old)].copy()
    old_by_id=old.drop_duplicates("source_record_id").set_index("source_record_id")
    c["old_name"] = c.old_source_record_id.map(old_by_id.settlement_name.map(clean))
    c["old_type"] = c.old_source_record_id.map(old_by_id.settlement_type.map(clean))
    c["old_region"] = c.old_source_record_id.map(old_by_id.region_norm.map(clean))
    c["old_source_locator"] = c.old_source_record_id.map(old_by_id.apply(lambda x: f"{x.source_file}; {x.source_sheet}; row={x.source_row}",axis=1))
    c["old_source_sha256"] = c.old_source_record_id.map(old_by_id.get("source_sha256", pd.Series(dtype="string")))
    # Some pre-existing selected rows did not carry a source hash column value.
    # For the affected Tom 11 endpoints the retained source file is hash-pinned below.
    tom11_ids=c.old_source_record_id.astype(str).str.startswith("2010:pub-11-1-4.pdf:")
    c.loc[tom11_ids & c.old_source_sha256.isna(),"old_source_sha256"]="db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500"
    c["old_raw_name"] = c.old_source_record_id.map(old_by_id.source_name_raw)
    c["old_region_raw"] = c.old_source_record_id.map(old_by_id.region_raw)
    # Source-normalized region tokens match the selected snapshot's historical admin grain.
    c["new_region_norm"] = c.get("new_region_norm", pd.Series(index=c.index,dtype="string"))
    c["old_admin_norm"] = c.old_source_record_id.map(old_by_id.district_norm.fillna(old_by_id.municipality_norm).map(clean))
    c["admin_context_status"] = "district_or_municipality_unavailable_in_one_or_both_publications"
    c.loc[c.old_admin_norm.eq("") & c.new_admin_context.fillna("").map(clean).eq(""),"admin_context_status"]="no_subregional_parent_published_in_either_row"
    c.loc[c.old_admin_norm.eq(c.new_admin_context.fillna("").map(clean)) & c.old_admin_norm.ne(""),"admin_context_status"]="both_source_parent_values_match"
    c["old_admin_context"] = c.old_source_record_id.map(old_by_id.district_raw.fillna(old_by_id.municipality_raw))
    c["new_name"] = c.new_name.map(clean); c["new_type"] = c.new_type.map(clean)
    c["new_population"] = pd.to_numeric(c.new_population,errors="coerce")
    c["old_population"] = pd.to_numeric(c.old_population,errors="coerce")
    newcounts=c.groupby(["component","new_source_record_id"]).old_source_record_id.nunique()
    oldcounts=c.groupby(["component","old_source_record_id"]).new_source_record_id.nunique()
    c["candidate_binding_status"] = "pending_not_one_to_one_or_name_type_mismatch"
    for ix,r in c.iterrows():
        unique=(newcounts.get((r.component,r.new_source_record_id),0)==1 and oldcounts.get((r.component,r.old_source_record_id),0)==1)
        same=(r.new_name==r.old_name and r.new_type==r.old_type and clean(r.new_region_norm)==clean(r.old_region))
        equal=pd.notna(r.new_population) and pd.notna(r.old_population) and int(r.new_population)==int(r.old_population)
        dash_safe = (str(r.new_population_status) == "reported_value")
        if unique and same and equal and dash_safe:
            c.at[ix,"candidate_binding_status"]="strict_unique_name_type_population_candidate_pending_independent_binding_review"
        elif unique and same and equal and not dash_safe:
            c.at[ix,"candidate_binding_status"]="unique_key_zero_derived_from_raw_dash_population_not_binding_proof"
        elif unique and same:
            c.at[ix,"candidate_binding_status"]="unique_name_type_but_population_differs_pending_review"
        elif unique:
            c.at[ix,"candidate_binding_status"]="unique_source_key_but_normalized_name_or_type_differs_pending_review"
    c["relation"]="same_census_publication_equivalence_candidate"
    c["decision_status"]="not_admitted_pending_independent_review"
    c["binding_candidate_origin"]="reviewed_component_predecessor_crosswalk"
    return c.sort_values(["component","candidate_binding_status","new_source_record_id","old_source_record_id"],kind="stable")

def build(output: Path) -> dict:
    output=output.resolve()
    if output.exists(): raise FileExistsError(f"immutable output already exists: {output}")
    paths,nw_manifest,ark_manifest=load_inputs()
    for name,expected in [("r5b_edges",""),("r5b_coords",""),("r5b_bindings","")]:
        # Their binary hashes are recorded at build time; exact schemas/IDs are tested below.
        if not paths[name].is_file(): raise FileNotFoundError(paths[name])
    base=pd.read_parquet(paths["r1_selected"])
    orig=base.copy()
    old_m=base[(base.census_year.eq(2010))&(base.region_norm.eq("мурманская"))].copy()
    old_k=base[(base.census_year.eq(2010))&(base.region_norm.eq("калининградская"))].copy()
    old_a=base[(base.census_year.eq(2010))&(base.region_norm.isin(["архангельская","ненецкий"]))].copy()
    if (len(old_m),int(old_m.population.sum()),len(old_k),int(old_k.population.sum()),len(old_a),int(old_a.population.sum())) != (140,782878,1099,936068,4003,1215288):
        raise ValueError("R1 selected source slice preconditions for Murmansk/Kaliningrad/Arkhangelsk+NAO differ")
    tmpl=list(base.columns)
    m=pd.read_csv(NW_DIR/"murmansk_2010_primary_population_selection_proposal.csv")
    k=pd.read_csv(NW_DIR/"kaliningrad_2010_primary_population_selection_proposal.csv")
    a=pd.read_csv(ARK_DIR/"arkhangelsk_2010_primary_selection_component.csv")
    new_m=make_nw_rows(m,tmpl,"murmansk"); new_k=make_nw_rows(k,tmpl,"kaliningrad"); new_a=make_ark_rows(a,tmpl)
    new_regions=pd.concat([new_m,new_k,new_a],ignore_index=True)
    if (len(new_m),int(new_m.population.sum()),len(new_k),int(new_k.population.sum()),len(new_a),int(new_a.population.sum(min_count=1)),int(new_a.population.isna().sum())) != (140,795409,1099,941873,4004,1227626,1):
        raise ValueError("reviewed regional source candidate controls mismatch")
    old_region_ids=set(pd.concat([old_m,old_k,old_a]).source_record_id.astype(str))
    out=base[~base.source_record_id.astype(str).isin(old_region_ids)].copy()
    out=pd.concat([out,new_regions],ignore_index=True,sort=False).sort_values(["census_year","source_record_id"],kind="stable",ignore_index=True)
    if out.source_record_id.astype(str).duplicated().any(): raise ValueError("selected source IDs are duplicated")
    for yr in (2002,2010,2021):
        bef=set(orig.loc[orig.census_year.eq(yr),"source_record_id"].astype(str)); aft=set(out.loc[out.census_year.eq(yr),"source_record_id"].astype(str))
        if yr==2010: expected=bef-old_region_ids|set(new_regions.source_record_id.astype(str))
        else: expected=bef
        if aft!=expected: raise ValueError(f"exact selected-ID set regression failed for {yr}")
    # Active graph projection is endpoint-based. Displaced decisions remain in their immutable ledger;
    # no unpublished source equivalence is used to keep stale endpoints active.
    selected=set(out.source_record_id.astype(str))
    edges=pd.read_csv(paths["r5b_edges"])
    edge_endpoints=edges.from_source_record_id.astype(str).isin(selected)&edges.to_source_record_id.astype(str).isin(selected)
    edges["selection_projection_status"]="active_endpoints_selected"
    edges.loc[~edge_endpoints,"selection_projection_status"]="held_endpoint_not_selected_pending_publication_binding"
    coords=pd.read_csv(paths["r5b_coords"])
    coord_ok=coords.target_source_record_id.astype(str).isin(selected)&coords.coordinate_source_record_id.astype(str).isin(selected)
    coords["selection_projection_status"]="active_endpoints_selected"
    coords.loc[~coord_ok,"selection_projection_status"]="held_endpoint_not_selected_pending_publication_binding"
    # Legacy rows removed from R1 are archival only; preserve R1 exclusions and add all newly displaced rows.
    archive=pd.read_csv(paths["r1_archive"])
    baseline_all=pd.read_parquet(paths["baseline"])
    old_karelia_2010=baseline_all[(baseline_all.census_year.eq(2010))&(baseline_all.region_norm.eq("карелия"))].copy()
    if len(old_karelia_2010)!=799:
        raise ValueError("baseline archive of legacy Karelia 2010 observations differs from frozen R1 migration precondition")
    old_karelia_2010["release_disposition"]="retained_as_historical_observation_excluded_when_R1_selected_corrected_Karelia_R5"
    old_karelia_2010["decision_evidence"]="national_source_selection_r1_20260930"
    old_karelia_2010["identity_admission"]="none"; old_karelia_2010["coordinate_admission"]="none"
    newly=pd.concat([old_m,old_k,old_a],ignore_index=True,sort=False)
    newly["release_disposition"]="retained_as_historical_observation_excluded_from_r2_selected_release"
    newly["decision_evidence"]="national_source_selection_r2_regional_source_selection"
    newly["identity_admission"]="none"; newly["coordinate_admission"]="none"
    archive=pd.concat([archive,old_karelia_2010,newly],ignore_index=True,sort=False)
    if archive.source_record_id.astype(str).duplicated().any(): raise ValueError("archive contains duplicate source IDs")
    # Preserve all prior version assertions and append versioned supersession/select assertions.
    prior=pd.read_csv(paths["r1_assertions"])
    prior.loc[prior.action.eq("select_for_release"),"action"]="select_for_r1_superseded_by_r2_where_displaced"
    assertions=[prior]
    for comp,olds,news,ev in [
        ("murmansk_2010_primary_source_r4",old_m,new_m,NW_MANIFEST_SHA),
        ("kaliningrad_2010_primary_source_r4",old_k,new_k,NW_MANIFEST_SHA),
        ("arkhangelsk_nao_2010_primary_source_r1",old_a,new_a,ARK_MANIFEST_SHA)]:
        oldassert=olds.copy()
        oldassert["component_id"]=comp; oldassert["action"]="retain_archived_exclude_from_selected_release"
        oldassert["reason"]="superseded by independently reviewed regional primary source slice; archived values unchanged"
        oldassert["evidence_sha256"]=ev
        oldassert["source_locator"]=oldassert.apply(lambda x:f"{x.source_file}; sheet={x.source_sheet}; row={x.source_row}",axis=1)
        assertions.append(oldassert[["component_id","census_year","source_record_id","action","population","source_locator","reason","evidence_sha256"]])
        ns=news.copy(); ns["component_id"]=comp; ns["action"]="select_for_r2_release"
        ns["reason"]="independently reviewed primary source selection; no identity or coordinate claim"
        ns["evidence_sha256"]=ev; ns["source_locator"]=ns.source_locator.astype("string")
        assertions.append(ns[["component_id","census_year","source_record_id","action","population","source_locator","reason","evidence_sha256"]])
    assertions=pd.concat(assertions,ignore_index=True,sort=False).sort_values(["census_year","component_id","action","source_record_id"],kind="stable")
    proposals={"murmansk":m,"kaliningrad":k}
    bindings=create_binding_candidates(proposals,a,pd.concat([old_m,old_k,old_a],ignore_index=True))
    # Arkhangelsk city proper is intentionally absent from the archived regional HTML slice;
    # the reviewed disjoint slice appends its atomic Tom 1 Table 5 row. Bind that exact row
    # to the prior Tom 11 city row as a pending same-census publication-equivalence candidate.
    ark_t5=a[a.table5_reference_id.astype(str).eq("ROSSTAT2010:T5:p58:l12")]
    ark_old=old_a[(old_a.settlement_name.map(clean).eq("архангельск"))&
                  (old_a.settlement_type.map(clean).eq("город"))&old_a.population.eq(348783)]
    if len(ark_t5)!=1 or len(ark_old)!=1:
        raise ValueError("Arkhangelsk city-proper Tom11↔Table5 binding endpoints are not unique")
    tom11_path=ROOT/"data/raw/2010_official_tom11/pub-11-1-4.pdf"
    verify(tom11_path,"db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500")
    nr=ark_t5.iloc[0]; oldr=ark_old.iloc[0]
    manual=pd.DataFrame([{
        "component":"arkhangelsk_nao","new_source_record_id":nr.source_record_id,
        "old_source_record_id":oldr.source_record_id,"new_name":"архангельск","old_name":"архангельск",
        "new_type":"город","old_type":"город","new_population":348783,"old_population":348783,
        "new_population_status":"reported_value","key_match_status":"exact official same-census city row, value and region match",
        "candidate_input_locator":nr.source_logical_locator,"new_raw_name":nr.label_raw,
        "new_source_sha256":nr.source_sha256,"new_source_path":"data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf",
        "new_region_raw":"Архангельская область","new_admin_context":"Arkhangelsk oblast city-proper row; HTML disjoint slice did not contain city proper",
        "new_region_norm":"архангельская","new_source_record_grain":"atomic city-proper value row cited to Table 5 p58:l12",
        "old_source_locator":f"{oldr.source_file}; {oldr.source_sheet}; row={oldr.source_row}",
        "old_source_sha256":sha(tom11_path),"old_raw_name":oldr.source_name_raw,
        "old_region":"архангельская","old_region_raw":oldr.region_raw,"old_type":"город",
        "old_admin_context":pd.NA,"relation":"same_census_publication_equivalence_candidate",
        "decision_status":"not_admitted_pending_independent_review",
        "candidate_binding_status":"strict_unique_name_type_population_candidate_pending_independent_binding_review",
        "binding_candidate_origin":"explicit_Tom11_city_to_Tom1_Table5_atomic_city_crosspublication_candidate",
        "admin_context_status":"no_subregional_parent_published_in_either_row",
        "published_reference_id":"ROSSTAT2010:T5:p58:l12","review_source_manifest_sha256":ARK_MANIFEST_SHA,
    }])
    bindings=pd.concat([bindings,manual],ignore_index=True,sort=False)
    held_edges=edges[edges.selection_projection_status.eq("held_endpoint_not_selected_pending_publication_binding")].copy()
    affected=[]
    for r in held_edges.itertuples(index=False):
        old_id=None; other_id=None; other_year=None
        if int(r.from_year)==2010 and str(r.from_source_record_id) not in selected:
            old_id=str(r.from_source_record_id); other_id=str(r.to_source_record_id); other_year=int(r.to_year)
        elif int(r.to_year)==2010 and str(r.to_source_record_id) not in selected:
            old_id=str(r.to_source_record_id); other_id=str(r.from_source_record_id); other_year=int(r.from_year)
        if old_id is None:
            continue
        affected.append({"affected_decision_id":r.decision_id,"decision_relation":r.relation,
            "decision_status":r.decision_status,"decision_class":r.decision_class,
            "identity_evidence_uri":r.evidence_uri,"identity_evidence_sha256":r.evidence_sha256,
            "displaced_2010_source_record_id":old_id,"other_selected_endpoint_id":other_id,
            "other_endpoint_year":other_year,"migration_action":"hold_until_independent_same_census_publication_binding_review"})
    affected_edges=pd.DataFrame(affected)
    if len(affected_edges)!=54: raise ValueError(f"expected 54 affected accepted identity decisions; found {len(affected_edges)}")
    packet=affected_edges.merge(bindings,left_on="displaced_2010_source_record_id",right_on="old_source_record_id",how="left",validate="many_to_many")
    no_candidate=packet.new_source_record_id.isna()
    packet.loc[no_candidate,"candidate_binding_status"]="no_predecessor_mapping_candidate_found_pending_review"
    packet.loc[no_candidate,"decision_status_y"]="not_admitted_no_candidate"
    # Summaries retain official scope denominators independently of selected non-null sums.
    annual=[]
    for yr in (2002,2010,2021):
        b=orig[orig.census_year.eq(yr)]; z=out[out.census_year.eq(yr)]
        annual.append({"census_year":yr,"r1_selected_rows":len(b),"r2_selected_rows":len(z),
            "row_delta":len(z)-len(b),"r1_nonnull_population_sum":int(b.population.sum()),
            "r2_nonnull_population_sum":int(z.population.sum()),"known_population_delta":int(z.population.sum()-b.population.sum()),
            "r2_population_null_rows":int(z.population.isna().sum()),
            "selected_ids_sha256":hashlib.sha256("\n".join(sorted(z.source_record_id.astype(str))).encode()).hexdigest()})
    annual=pd.DataFrame(annual)
    components=pd.DataFrame([
        {"component_id":"murmansk_2010_primary_source_r4","year":2010,"operation":"replace_full_regional_slice_with_independently_reviewed_primary_population_source","removed_rows":len(old_m),"added_rows":len(new_m),"row_delta":len(new_m)-len(old_m),"removed_known_population":int(old_m.population.sum()),"added_known_population":int(new_m.population.sum()),"known_population_delta":int(new_m.population.sum()-old_m.population.sum()),"added_null_population_rows":int(new_m.population.isna().sum()),"evidence_manifest_sha256":NW_MANIFEST_SHA,"identity_or_coordinate_claims":"none"},
        {"component_id":"kaliningrad_2010_primary_source_r4","year":2010,"operation":"replace_full_regional_slice_with_independently_reviewed_primary_population_source","removed_rows":len(old_k),"added_rows":len(new_k),"row_delta":len(new_k)-len(old_k),"removed_known_population":int(old_k.population.sum()),"added_known_population":int(new_k.population.sum()),"known_population_delta":int(new_k.population.sum()-old_k.population.sum()),"added_null_population_rows":int(new_k.population.isna().sum()),"evidence_manifest_sha256":NW_MANIFEST_SHA,"identity_or_coordinate_claims":"none"},
        {"component_id":"arkhangelsk_nao_2010_primary_source_r1","year":2010,"operation":"replace_disjoint_arkhangelsk_exclusive_plus_nao_slice_with_reviewed_primary_slice","removed_rows":len(old_a),"added_rows":len(new_a),"row_delta":len(new_a)-len(old_a),"removed_known_population":int(old_a.population.sum()),"added_known_population":int(new_a.population.sum()),"known_population_delta":int(new_a.population.sum()-old_a.population.sum()),"added_null_population_rows":int(new_a.population.isna().sum()),"evidence_manifest_sha256":ARK_MANIFEST_SHA,"identity_or_coordinate_claims":"none"},
    ])
    totals={str(r.census_year):{k:(int(v) if isinstance(v,(int,float)) else v) for k,v in r._asdict().items() if k!="Index"} for r in annual.itertuples(index=False)}
    expected={2002:(0,0),2010:(1,30674),2021:(0,0)}
    for r in annual.itertuples(index=False):
        if (r.row_delta,r.known_population_delta)!=expected[r.census_year]: raise ValueError(f"unexpected annual selection delta: {r}")
    staging=Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-",dir=output.parent if output.parent.exists() else ROOT))
    try:
        out.to_parquet(staging/"selected_observations.parquet",index=False)
        archive.to_csv(staging/"archived_source_observations.csv",index=False)
        assertions.to_csv(staging/"source_selection_assertions.csv",index=False)
        components.to_csv(staging/"component_ledger.csv",index=False)
        bindings.to_csv(staging/"publication_binding_migration_candidates_pending_review.csv",index=False)
        packet.to_csv(staging/"affected_identity_edges_publication_binding_review_packet.csv",index=False)
        edges.to_csv(staging/"identity_edge_selection_projection.csv",index=False)
        coords.to_csv(staging/"coordinate_claim_selection_projection.csv",index=False)
        annual.to_csv(staging/"annual_controls.csv",index=False)
        (staging/"scope_controls.json").write_text(json.dumps({
            "Arkhangelsk_oblast_exclusive_known_population":1185536,
            "NAO_known_population":42090,
            "Arkhangelsk_published_parent_inclusive_control":1227626,
            "Arkhangelsk_plus_NAO_selected_known_sum":1227626,
            "Arkhangelsk_plus_NAO_null_population_rows":1,
            "additive_rule":"Arkhangelsk-exclusive + NAO, or parent-inclusive alone; never count both parent and child controls",
            "identity_point_rule":"source selection does not admit identity or coordinates; displaced claim endpoints are inactive until a reviewed publication binding exists"
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        # Store machine manifest with actual hashes of every immutable input/output.
        verified={}
        for label,p in paths.items(): verified[str(p.relative_to(ROOT))]={"sha256":sha(p),"bytes":p.stat().st_size,"role":label}
        for p in [NW_MANIFEST,ARK_MANIFEST,R1_MANIFEST,R5B_MANIFEST]: verified[str(p.relative_to(ROOT))]={"sha256":sha(p),"bytes":p.stat().st_size}
        manifest={"release_id":"national_source_selection_r2_regional_2010_20260930",
            "status":"reviewed_population_source_selection_only_identity_coordinate_claims_projected_only_to_selected_endpoints",
            "builder_sha256":sha(Path(__file__).resolve()),"verified_inputs":verified,
            "supersedes":"national_source_selection_r1_20260930",
            "superseded_mutable_input_incident":"NW R3 manifest was amended in place; R4 is the immutable reviewed replacement and sole input here.",
            "components":components.to_dict(orient="records"),"annual_controls":totals,
            "binding_migration":{"candidate_rows":len(bindings),"accepted":0,"status":"all pending independent publication-equivalence review",
                "affected_accepted_identity_edges":len(affected_edges),"unique_displaced_2010_endpoint_ids":int(affected_edges.displaced_2010_source_record_id.nunique()),
                "affected_edge_packet_rows":len(packet),"affected_edge_candidate_rows":int(packet.new_source_record_id.notna().sum()),
                "affected_edge_unmapped_rows":int(packet.new_source_record_id.isna().sum()),
                "strict_unique_population_match_candidates":int(packet.candidate_binding_status.eq("strict_unique_name_type_population_candidate_pending_independent_binding_review").sum())},
            "identity_claims":{"input_release":"national_reviewed_admissions_r5b_yearbook_20260930","accepted_edges_in_source_ledger":len(edges),"active_in_r2":int(edge_endpoints.sum()),"held_due_to_displaced_or_unselected_endpoint":int((~edge_endpoints).sum())},
            "coordinate_claims":{"source_rows":len(coords),"active_in_r2":int(coord_ok.sum()),"held_due_to_displaced_or_unselected_endpoint":int((~coord_ok).sum())},
            "outputs":{}}
        for p in sorted(staging.iterdir()):
            if p.is_file(): manifest["outputs"][p.name]={"sha256":sha(p),"bytes":p.stat().st_size}
        (staging/"release_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        if output.exists(): raise FileExistsError(f"immutable output already exists: {output}")
        output.parent.mkdir(parents=True,exist_ok=True); staging.rename(output)
        return manifest
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

def main():
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    m=build(a.output)
    print(json.dumps({"release_id":m["release_id"],"annual_controls":m["annual_controls"],"output":str(a.output.resolve())},ensure_ascii=False,indent=2))

if __name__=="__main__": main()

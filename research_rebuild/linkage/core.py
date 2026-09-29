"""Conservative, replayable identity and coordinate decisions for census rows.

The source row is the immutable observation. Place identity and coordinate
admission are separate ledgers. Candidate generation never accepts a link.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

import pandas as pd

RULE_VERSION = "linkage-v1"
COORDINATE_RULE = "dadata-qcgeo-3-singleton-wgs84-v1"


def stable_id(prefix: str, value: object, n: int = 24) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:n]
    return f"{prefix}-{digest}"


def normalize(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).casefold().replace("ё", "е")).strip()


def normalize_region(value: object) -> str:
    key = normalize(value)
    for prefix in ("республика ", "респ. ", "респ "):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    for suffix in (" область", " край"):
        if key.endswith(suffix):
            key = key[:-len(suffix)]
            break
    return key.strip()


def prepare_observations(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"source_record_id", "census_year", "population"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"observations missing columns: {sorted(missing)}")
    out = frame.copy(deep=True)
    out["source_record_id"] = out.source_record_id.astype("string")
    if out.source_record_id.isna().any() or out.source_record_id.duplicated().any():
        raise ValueError("source_record_id must be present and unique")
    out["observation_id"] = out.source_record_id.map(lambda x: stable_id("OBS", x))
    out["census_year"] = pd.to_numeric(out.census_year, errors="raise").astype("int16")
    out["population"] = pd.to_numeric(out.population, errors="coerce").astype("Int64")
    for col in ("settlement_name", "settlement_type", "region_raw", "district_raw", "municipality_raw"):
        if col not in out:
            out[col] = pd.NA
    out["name_key"] = out.settlement_name.map(normalize)
    out["type_key"] = out.settlement_type.map(normalize)
    out["region_key"] = (out.region_norm.map(normalize_region) if "region_norm" in out
                         else out.region_raw.map(normalize_region))
    out["district_key"] = (out.district_norm.map(normalize) if "district_norm" in out
                           else out.district_raw.map(normalize))
    # These are observation-level singleton place IDs until the decision ledger
    # has accepted a cross-observation relation. IDs are not 2021 OKTMO values.
    out["provisional_place_id"] = out.source_record_id.map(lambda x: stable_id("PLACE", x))
    return out


def make_identity_candidates(observations: pd.DataFrame) -> pd.DataFrame:
    """Find exact contextual candidates across adjacent census years only.

    Names are normalized for whitespace/case/ё. Region and settlement type
    must agree. Groups with multiple records on either side are emitted as
    conflicts rather than expanded into guessed pairings.
    """
    usable = observations[
        observations.name_key.ne("") & observations.type_key.ne("") & observations.region_key.ne("")
    ].copy()
    keys = ["region_key", "type_key", "name_key"]
    records: list[dict] = []
    years = sorted(int(y) for y in usable.census_year.unique())
    year_pairs = [(years[i], years[j]) for i in range(len(years)) for j in range(i + 1, len(years))
                  if years[j] - years[i] in (8, 11, 19)]
    for left_year, right_year in year_pairs:
        left = usable[usable.census_year.eq(left_year)]
        right = usable[usable.census_year.eq(right_year)]
        lc = left.groupby(keys, dropna=False).size().rename("left_count")
        rc = right.groupby(keys, dropna=False).size().rename("right_count")
        common = lc.to_frame().join(rc, how="inner").reset_index()
        unique = common[common.left_count.eq(1) & common.right_count.eq(1)][keys]
        left_unique = left.merge(unique, on=keys, how="inner", validate="many_to_one")
        right_unique = right.merge(unique, on=keys, how="inner", validate="many_to_one")
        paired = left_unique.merge(right_unique, on=keys, how="inner", validate="one_to_one", suffixes=("_left", "_right"))
        for r in paired.itertuples(index=False):
            a_id = getattr(r, "observation_id_left")
            b_id = getattr(r, "observation_id_right")
            records.append({
                "candidate_id": stable_id("CAND", f"{a_id}|{b_id}"),
                "from_observation_id": a_id,
                "to_observation_id": b_id,
                "from_year": int(left_year), "to_year": int(right_year),
                "candidate_basis": "unique_exact_region_type_name",
                "candidate_status": "unreviewed",
                "acceptance_allowed": False,
                "conflict_reason": None,
            })
        conflict = common[common.left_count.gt(1) | common.right_count.gt(1)].copy()
        left_conflicts = left.merge(conflict, on=keys, how="inner", validate="many_to_one")
        right_conflicts = right.merge(conflict, on=keys, how="inner", validate="many_to_one")
        left_groups = left_conflicts.groupby(keys, dropna=False).observation_id.agg(list).to_dict()
        right_groups = right_conflicts.groupby(keys, dropna=False).observation_id.agg(list).to_dict()
        for row in conflict.itertuples(index=False):
            key = tuple(getattr(row, k) for k in keys)
            member_ids = list(left_groups.get(key, [])) + list(right_groups.get(key, []))
            for a_id in member_ids:
                records.append({
                    "candidate_id": stable_id("CAND", f"{a_id}|conflict|{left_year}|{right_year}"),
                    "from_observation_id": a_id,
                    "to_observation_id": None,
                    "from_year": int(left_year), "to_year": int(right_year),
                    "candidate_basis": "exact_name_region_type_ambiguous_group",
                    "candidate_status": "conflict",
                    "acceptance_allowed": False,
                    "conflict_reason": f"left={int(row.left_count)},right={int(row.right_count)}",
                    "candidate_group_size_left": int(row.left_count),
                    "candidate_group_size_right": int(row.right_count),
                    "conflict_members": json.dumps(member_ids),
                })
    columns = ["candidate_id", "from_observation_id", "to_observation_id", "from_year", "to_year",
               "candidate_basis", "candidate_status", "acceptance_allowed", "conflict_reason",
               "candidate_group_size_left", "candidate_group_size_right", "conflict_members"]
    return pd.DataFrame(records).reindex(columns=columns)


def _rows(frame: pd.DataFrame) -> Iterable[pd.Series]:
    if isinstance(frame, pd.Series):
        yield frame
    else:
        for _, row in frame.iterrows():
            yield row


def coordinate_claims(observations: pd.DataFrame) -> pd.DataFrame:
    """Normalize every source point claim while preserving source provenance."""
    frame = observations.copy()
    for col in ("latitude", "longitude", "coordinate_source", "coordinate_quality", "population_scope"):
        if col not in frame:
            frame[col] = pd.NA
    frame["latitude"] = pd.to_numeric(frame.latitude, errors="coerce")
    frame["longitude"] = pd.to_numeric(frame.longitude, errors="coerce")
    frame = frame[frame.latitude.notna() | frame.longitude.notna()].copy()
    frame["coordinate_claim_id"] = frame.observation_id.map(lambda x: stable_id("COORD", x))
    frame["claim_origin"] = frame.coordinate_source.astype("string")
    frame["source_precision_code"] = frame.coordinate_quality.astype("string")
    frame["source_year"] = frame.census_year
    frame["admission_status"] = "unresolved"
    frame["admission_class"] = "unresolved"
    frame["admission_rule"] = pd.NA
    frame["admission_reason"] = "coordinate has no year-specific approved decision"
    return frame


def rule_coordinate_decisions(observations: pd.DataFrame, claims: pd.DataFrame,
                              wikidata: pd.DataFrame) -> pd.DataFrame:
    """Propose an evidence-backed 2021 point only when sources co-identify it.

    DaData precision is not enough on its own. Require a unique exact current
    OKTMO+OKATO Wikidata route, exact name agreement, an article and QID, two
    valid coordinate claims within 500m, and a non-shared point. The proposed
    decisions remain pending until blind independent review of this rule
    family. Agreement is corroboration, not proof of source independence.
    """
    if claims.empty:
        return pd.DataFrame(columns=_decision_columns())
    c = claims.copy()
    w = wikidata.copy()
    if "source_record_id" not in w:
        raise ValueError("Wikidata evidence must contain source_record_id")
    w = w.drop_duplicates("source_record_id", keep=False)
    c = c.merge(w, on="source_record_id", how="left", suffixes=("", "_wd"), validate="many_to_one")
    c["qc_geo"] = pd.to_numeric(c.source_precision_code, errors="coerce")
    c["wd_match_accepted"] = c.get("wikidata_match_accepted", pd.Series(False, index=c.index)).eq(True)
    c["wd_route_exact"] = c.get("wikidata_match_method", pd.Series("", index=c.index)).isin(["exact_oktmo_okato_agree"])
    c["wd_name_agrees"] = c.get("wikidata_candidate_name_agrees", pd.Series(False, index=c.index)).eq(True)
    c["wd_item_present"] = c.get("wikidata_id", pd.Series(pd.NA, index=c.index)).notna()
    c["wiki_article_present"] = c.get("wikipedia_url_ru", pd.Series(pd.NA, index=c.index)).notna()
    c["wd_coordinates_present"] = c.get("wikidata_latitude", pd.Series(pd.NA, index=c.index)).notna() & c.get("wikidata_longitude", pd.Series(pd.NA, index=c.index)).notna()
    lat1 = pd.to_numeric(c.latitude, errors="coerce"); lon1 = pd.to_numeric(c.longitude, errors="coerce")
    lat2 = pd.to_numeric(c.get("wikidata_latitude"), errors="coerce"); lon2 = pd.to_numeric(c.get("wikidata_longitude"), errors="coerce")
    # Haversine is used only as a rejection gate for coordinate conflict.
    from numpy import arcsin, cos, radians, sin, sqrt
    c["source_to_wikidata_distance_m"] = 6_371_000 * 2 * arcsin(sqrt(
        sin(radians(lat2-lat1)/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(radians(lon2-lon1)/2)**2
    ))
    eligible = c[
        c.census_year.eq(2021)
        & c.population_scope.astype("string").eq("settlement")
        & c.qc_geo.isin([3, 4])
        & c.latitude.between(-90, 90)
        & c.longitude.between(-180, 180)
        & c.latitude.between(41, 82)
        & (c.longitude.between(19, 180) | c.longitude.between(-180, -169))
        & c.wd_match_accepted & c.wd_route_exact & c.wd_name_agrees
        & c.wd_item_present & c.wiki_article_present & c.wd_coordinates_present
        & c.source_to_wikidata_distance_m.le(500)
    ].copy()
    qid_counts = c[c.wikidata_id.notna()].groupby("wikidata_id").source_record_id.nunique()
    duplicated_qids = set(qid_counts[qid_counts.gt(1)].index)
    eligible = eligible[~eligible.wikidata_id.isin(duplicated_qids)]
    qid_counts = c[c.wikidata_id.notna()].groupby("wikidata_id").source_record_id.nunique()
    duplicated_qids = set(qid_counts[qid_counts.gt(1)].index)
    eligible = eligible[~eligible.wikidata_id.isin(duplicated_qids)]
    all_2021 = c[c.census_year.eq(2021) & c.latitude.notna() & c.longitude.notna()]
    shared_points = set(map(tuple, all_2021.loc[
        all_2021.duplicated(["latitude", "longitude"], keep=False), ["latitude", "longitude"]
    ].drop_duplicates().to_numpy()))
    duplicate = eligible.apply(lambda r: (r.latitude, r.longitude) in shared_points, axis=1)
    eligible = eligible[~duplicate]
    if eligible.empty:
        return pd.DataFrame(columns=_decision_columns())
    indexed = observations.set_index("observation_id")
    rows=[]
    for c_row in eligible.itertuples(index=False):
        obs = indexed.loc[c_row.observation_id]
        sid = str(obs.source_record_id)
        evidence = f"{obs.get('source_file', obs.get('source_path', 'source dataset'))}#{obs.get('source_sheet', '')}:{obs.get('source_row', '')}"
        evidence_digest = obs.get("source_sha256", obs.get("source_file_sha256", pd.NA))
        rationale = ("Proposed rule only: source scope is settlement; source precision qc_geo is 3/4; unique exact OKTMO+OKATO Wikidata route, exact name agreement, linked Russian Wikipedia article, "
                     "valid coordinate claims within 500m, and no exact shared point. DaData/Wikidata source independence is not established. Pending blind review.")
        rows.append({
            "decision_id": stable_id("DEC", f"{COORDINATE_RULE}|{c_row.coordinate_claim_id}"),
            "event_order": 1,
            "event_action": "propose",
            "decision_type": "coordinate_admission",
            "observation_id": c_row.observation_id,
            "from_observation_id": c_row.observation_id,
            "to_observation_id": None,
            "place_id": obs.provisional_place_id,
            "coordinate_claim_id": c_row.coordinate_claim_id,
            "decision_class": "rule",
            "decision_status": "pending_blind_validation",
            "decision_rule": "oktmo_okato_wikidata_coordinate_corroboration_500m_v1",
            "evidence_uri": json.dumps({"source_row": evidence,
                "source_dataset": str(obs.get("source_dataset_url", "https://tochno.st/datasets/allsettlements")),
                "wikidata": f"https://www.wikidata.org/wiki/{c_row.wikidata_id}",
                "wikipedia": str(c_row.wikipedia_url_ru)}, ensure_ascii=False),
            "evidence_sha256": evidence_digest,
            "evidence_source": json.dumps([c_row.claim_origin, "Wikidata P625 / exact administrative identifiers", "Russian Wikipedia article"], ensure_ascii=False),
            "rationale": rationale,
            "reviewer": "automated_rule",
            "reviewed_at": pd.NA,
            "supersedes_decision_id": pd.NA,
        })
    return pd.DataFrame(rows).reindex(columns=_decision_columns())


def _decision_columns():
    return ["decision_id", "event_order", "event_action", "decision_type", "observation_id",
            "from_observation_id", "to_observation_id", "place_id", "coordinate_claim_id",
            "decision_class", "decision_status", "decision_rule", "evidence_uri",
            "evidence_sha256", "evidence_source", "rationale", "reviewer", "reviewed_at",
            "supersedes_decision_id"]


def reviewer_results_to_events(proposals: pd.DataFrame, reviewer_results: pd.DataFrame,
                               prediction_key: pd.DataFrame, reviewer: str,
                               first_event_order: int) -> pd.DataFrame:
    """Translate blinded verdicts into append-only apply/revoke events.

    Fixtures may exercise this function, but only an actual reviewer result
    file creates decisions in a research build.
    """
    if reviewer_results.empty:
        return pd.DataFrame(columns=list(proposals.columns))
    required = {"review_key", "review_result", "reason"}
    missing = required - set(reviewer_results.columns)
    if missing:
        raise ValueError(f"review results missing columns: {sorted(missing)}")
    if reviewer_results.review_key.duplicated().any():
        raise ValueError("review_key must be unique in one reviewer batch")
    key = prediction_key.copy()
    if "decision_id" not in key and "candidate_id" not in key:
        raise ValueError("prediction key must include decision_id or candidate_id")
    if key.review_key.duplicated().any():
        raise ValueError("review_key must be unique in prediction key")
    linked = reviewer_results.merge(key, on="review_key", how="left", validate="one_to_one", indicator=True)
    if linked._merge.ne("both").any():
        raise ValueError("a review_key is absent from the hidden prediction key")
    linked["review_result"] = linked.review_result.astype("string").str.lower().str.strip()
    if not linked.review_result.isin(["accept", "reject", "uncertain"]).all():
        raise ValueError("review_result must be accept, reject, or uncertain")
    linked = linked[~linked.review_result.eq("uncertain")].copy()
    if linked.empty:
        return pd.DataFrame(columns=list(proposals.columns))
    lookup_key = "decision_id" if "decision_id" in linked else "candidate_id"
    if lookup_key not in proposals:
        raise ValueError(f"proposals lack {lookup_key}")
    lookup = {key_value: group for key_value, group in proposals.groupby(lookup_key, dropna=False)}
    rows=[]
    order = int(first_event_order)
    for result in linked.itertuples(index=False):
        source_rows = lookup.get(getattr(result, lookup_key))
        if source_rows is None:
            raise ValueError(f"reviewed item has no proposal: {getattr(result, lookup_key)}")
        for _, source in source_rows.iterrows():
            row = source.to_dict()
            row["decision_id"] = stable_id("REVIEW-DEC", f"{row['decision_id']}|{reviewer}|{result.review_result}|{order}")
            row["event_order"] = order
            row["event_action"] = "apply" if result.review_result == "accept" else "revoke"
            row["decision_status"] = "review_accepted" if result.review_result == "accept" else "review_rejected"
            row["reviewer"] = reviewer
            row["reviewed_at"] = getattr(result, "reviewed_at", pd.NA)
            row["rationale"] = f"{row.get('rationale', '')} Independent reviewer result={result.review_result}; {result.reason}"
            row["supersedes_decision_id"] = source.decision_id if pd.notna(source.decision_id) else pd.NA
            if "review_evidence_urls" in reviewer_results.columns:
                row["evidence_uri"] = json.dumps({"proposal": row.get("evidence_uri"), "reviewer_evidence": getattr(result, "review_evidence_urls", "")}, ensure_ascii=False)
            rows.append(row)
            order += 1
    return pd.DataFrame(rows).reindex(columns=list(proposals.columns))


def identity_components(place_nodes: pd.DataFrame, effective_identity_events: pd.DataFrame,
                        release_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Derive versioned same-place components without renaming stable place nodes."""
    ids = place_nodes.place_id.astype(str).tolist()
    parent = {node: node for node in ids}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left, right):
        a, b = find(left), find(right)
        if a != b:
            # Internal node IDs never change; root ordering only makes the
            # component computation deterministic within this release.
            parent[max(a, b)] = min(a, b)

    if not effective_identity_events.empty:
        accepted = effective_identity_events[
            effective_identity_events.decision_type.eq("identity_link")
            & effective_identity_events.event_action.eq("apply")
            & effective_identity_events.relation_type.eq("same_place")
        ]
        observation_to_place = place_nodes.set_index("observation_id").place_id.astype(str).to_dict()
        for edge in accepted.itertuples(index=False):
            a, b = observation_to_place.get(str(edge.from_observation_id)), observation_to_place.get(str(edge.to_observation_id))
            if a in parent and b in parent:
                union(a, b)
    groups: dict[str, list[str]] = {}
    for node in ids:
        groups.setdefault(find(node), []).append(node)
    mapping=[]; components=[]
    for members in groups.values():
        members = sorted(members)
        signature = hashlib.sha256("\n".join(members).encode()).hexdigest()[:24]
        component_id = f"CMP-{release_id}-{signature}"
        components.append({"component_id": component_id, "component_version": release_id,
                           "member_count": len(members), "place_node_ids": json.dumps(members)})
        for node in members:
            mapping.append({"place_id": node, "component_id": component_id, "component_version": release_id,
                            "identity_status": "reviewed_same_place_component" if len(members) > 1 else "unresolved_single_observation"})
    return pd.DataFrame(components), pd.DataFrame(mapping)


def component_lineage(previous: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    """Record component supersession by overlap; never silently rename a place."""
    cols = ["previous_component_id", "current_component_id", "overlap_node_count", "lineage_relation"]
    if previous.empty or current.empty:
        return pd.DataFrame(columns=cols)
    old_by_node = {}
    for row in previous.itertuples(index=False):
        for node in json.loads(row.place_node_ids):
            old_by_node[node] = row.component_id
    counts: dict[tuple[str, str], int] = {}
    for row in current.itertuples(index=False):
        for node in json.loads(row.place_node_ids):
            old_id = old_by_node.get(node)
            if old_id is not None:
                key = (old_id, row.component_id)
                counts[key] = counts.get(key, 0) + 1
    edges = [{"previous_component_id": old_id, "current_component_id": new_id,
              "overlap_node_count": overlap,
              "lineage_relation": "membership_overlap_pending_manual_alias_decision"}
             for (old_id, new_id), overlap in counts.items()]
    return pd.DataFrame(edges, columns=cols)


def apply_decision_events(events: pd.DataFrame) -> pd.DataFrame:
    """Resolve append-only apply/revoke events; latest target event wins."""
    if events.empty:
        return events.copy()
    needed = {"decision_id", "event_order", "event_action", "decision_type", "observation_id"}
    missing = needed - set(events.columns)
    if missing:
        raise ValueError(f"decision events missing columns: {sorted(missing)}")
    if events.decision_id.duplicated().any():
        raise ValueError("decision_id must be unique")
    order = events.copy()
    order["event_order"] = pd.to_numeric(order.event_order, errors="raise")
    order["event_action"] = order.event_action.astype("string")
    if not order.event_action.isin(["propose", "apply", "revoke"]).all():
        raise ValueError("event_action must be propose, apply, or revoke")
    if "coordinate_claim_id" not in order:
        order["coordinate_claim_id"] = pd.NA
    if "from_observation_id" not in order:
        order["from_observation_id"] = pd.NA
    if "to_observation_id" not in order:
        order["to_observation_id"] = pd.NA
    if "decision_class" not in order:
        order["decision_class"] = pd.NA
    if "decision_status" not in order:
        order["decision_status"] = pd.NA
    order["_target"] = order.apply(lambda r: (
        str(r.decision_type),
        str(r.observation_id) if pd.notna(r.observation_id) else f"{r.from_observation_id}>{r.to_observation_id}",
        str(r.coordinate_claim_id) if pd.notna(r.coordinate_claim_id) else "",
    ), axis=1)
    order = order.sort_values(["event_order", "decision_id"], kind="stable")
    latest = order.drop_duplicates("_target", keep="last")
    return latest[latest.event_action.eq("apply")].copy().drop(columns="_target")

"""Coordinate evidence screening for modern physical-settlement point claims.

This module proposes review candidates. It never admits coordinates or place
identity. A 2021 source-row point may be a useful present-day representative
point; using it for 2002/2010 still needs a separate, reviewed continuity claim.

The current source bundle has DaData-derived FIAS levels and point coordinates,
but does not preserve a per-query API receipt. A missing receipt/date is recorded
as a provenance limitation, not used by itself to reject an otherwise reviewable
claim. ``qc_geo`` is a provider precision label only: it cannot establish that a
point belongs to a settlement or census observation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any, Mapping, Sequence


MODERN_CENSUS_YEAR = 2021
ALLOWED_FIAS_SETTLEMENT_LEVELS = frozenset({4, 6})
ALLOWED_OBJECT_LEVELS = frozenset({
    "населенный пункт",
    "населённый пункт",
    "settlement",
    "locality",
})
NON_SETTLEMENT_LEVEL_FRAGMENTS = (
    "муниципалитет",
    "административный район",
    "внутригородской район",
    "регион",
    "город федерального значения",
    "улица",
    "street",
    "дом",
    "house",
    "квартира",
    "земельный участок",
    "садовод",
    "snt",
)

# A distance match is only a consistency screen. It is not an acceptance radius
# or an estimate of correctness. A separately named settlement geometry may
# corroborate a point by containment instead of another point-to-point distance.
POINT_AGREEMENT_SCREEN_KM = 0.5
KNOWN_CONFLICT_SCREEN_KM = 5.0
BLIND_REVIEW_MINIMUM_PER_RULE_FAMILY = 100


@dataclass(frozen=True)
class CoordinateProposal:
    source_record_id: str | None
    target_year: int | None
    coordinate_source_record_id: str | None
    coordinate_provider: str | None
    coordinate_provider_id: str | None
    settlement_provider_id: str | None
    latitude: float | None
    longitude: float | None
    status: str
    admission_allowed: bool
    validation_gate: str
    independent_corroborator_count: int
    measurement_date_unknown: bool
    provider_query_receipt_missing: bool
    blocking_reasons: tuple[str, ...]
    review_reasons: tuple[str, ...]
    evidence_required: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("blocking_reasons", "review_reasons", "evidence_required"):
            result[key] = list(result[key])
        return result


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _int(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def valid_wgs84(latitude: Any, longitude: Any) -> bool:
    lat, lon = _number(latitude), _number(longitude)
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def in_broad_russia_envelope(latitude: Any, longitude: Any) -> bool:
    """Coarse candidate screen, including the negative-longitude Chukotka edge."""
    lat, lon = _number(latitude), _number(longitude)
    return bool(
        lat is not None and lon is not None and 41 <= lat <= 82
        and (19 <= lon <= 180 or -180 <= lon <= -169)
    )


def haversine_km(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> float | None:
    if not all(valid_wgs84(a, b) for a, b in ((lat1, lon1), (lat2, lon2))):
        return None
    a_lat, a_lon, b_lat, b_lon = map(radians, map(float, (lat1, lon1, lat2, lon2)))
    d_lat, d_lon = b_lat - a_lat, b_lon - a_lon
    a = sin(d_lat / 2) ** 2 + cos(a_lat) * cos(b_lat) * sin(d_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(min(1.0, a)))


def _physical_settlement_scope(candidate: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    population_scope = _text(candidate.get("population_scope")).casefold()
    if population_scope in {
        "federal_city_region", "municipality", "municipal_aggregate",
        "region", "administrative_area", "territorial_aggregate",
    }:
        return False, ["population_scope_is_aggregate_or_admin_unit"]

    object_level = _text(candidate.get("object_level") or candidate.get("source_object_level")).casefold()
    object_kind = _text(candidate.get("object_kind")).casefold()
    if object_kind in {"aggregate", "municipality", "administrative_unit", "street", "house", "snt", "garden_partnership"}:
        return False, ["point_object_is_not_a_physical_settlement"]
    if object_level:
        if any(fragment in object_level for fragment in NON_SETTLEMENT_LEVEL_FRAGMENTS):
            return False, ["source_object_level_is_not_a_settlement"]
        if object_level not in ALLOWED_OBJECT_LEVELS:
            reasons.append("source_object_level_needs_review")
    elif object_kind not in {"physical_settlement", "settlement"}:
        reasons.append("settlement_object_kind_not_explicit")

    fias_level = _int(candidate.get("fias_level_dadata", candidate.get("fias_level")))
    if fias_level is None:
        reasons.append("fias_level_missing_or_unparseable")
    elif fias_level not in ALLOWED_FIAS_SETTLEMENT_LEVELS:
        return False, ["fias_level_is_not_city_or_settlement"]
    return not reasons, reasons


def _corroborator_is_independent(
    primary: Mapping[str, Any], corroborator: Mapping[str, Any]
) -> bool:
    """Require documented distinct lineage; labels/claim kinds alone do not count."""
    primary_lineage = _text(primary.get("coordinate_lineage_id") or primary.get("lineage_group_id"))
    other_lineage = _text(corroborator.get("lineage_group_id"))
    primary_family = _text(primary.get("coordinate_provider_family") or primary.get("provider_family")).casefold()
    other_family = _text(corroborator.get("provider_family")).casefold()
    if not primary_lineage or not other_lineage or primary_lineage == other_lineage:
        return False
    if not primary_family or not other_family or primary_family == other_family:
        return False
    if corroborator.get("lineage_independence_documented") is not True:
        return False
    if not _text(corroborator.get("evidence_uri")) or not _text(corroborator.get("evidence_sha256")):
        return False
    if _text(corroborator.get("name_match")).casefold() != "exact":
        return False
    if _text(corroborator.get("admin_context_match")).casefold() != "exact":
        return False

    # A Wikidata label, fuzzy link, or coordinate proximity alone does not tie a
    # QID to this named census locality. Require an exact code-bound relationship.
    if other_family in {"wikidata", "wikidata_p625"}:
        if _text(corroborator.get("identifier_match_method")).casefold() != "exact_oktmo_and_okato":
            return False
        if not _text(corroborator.get("wikidata_id")):
            return False

    geometry_kind = _text(corroborator.get("evidence_kind")).casefold()
    if geometry_kind == "named_settlement_geometry_containment":
        return (
            _text(corroborator.get("geometry_object_kind")).casefold() in {"settlement_footprint", "physical_settlement"}
            and corroborator.get("contains_primary_point") is True
        )

    other_lat = corroborator.get("latitude")
    other_lon = corroborator.get("longitude")
    distance = haversine_km(primary.get("latitude"), primary.get("longitude"), other_lat, other_lon)
    return distance is not None and distance <= POINT_AGREEMENT_SCREEN_KM


def propose_coordinate_review(candidate: Mapping[str, Any]) -> CoordinateProposal:
    """Classify one modern coordinate claim without admitting it.

    Required input IDs have separate roles:

    * ``source_record_id`` identifies the census observation.
    * ``coordinate_source_record_id`` identifies the source record/locator that
      carries this coordinate claim.
    * ``coordinate_provider_id`` identifies the provider object (for example a
      DaData FIAS object, Wikidata QID, or OSM object). It must never be used as
      a substitute for either source-record ID or as an identity crosswalk.

    A missing query receipt or measurement date is surfaced as a review limit,
    not a standalone blocker. A proposed point for a non-2021 observation is held
    for a separately reviewed temporal-continuity decision.
    """
    source_id = _text(candidate.get("source_record_id")) or None
    coordinate_source_id = _text(candidate.get("coordinate_source_record_id")) or None
    provider = _text(candidate.get("coordinate_provider") or candidate.get("source_provider")) or None
    provider_id = _text(candidate.get("coordinate_provider_id") or candidate.get("fias_id_dadata")) or None
    settlement_provider_id = _text(
        candidate.get("settlement_provider_id") or candidate.get("settlement_fias_id_dadata")
    ) or None
    target_year = _int(candidate.get("target_year", candidate.get("census_year")))
    lat, lon = _number(candidate.get("latitude")), _number(candidate.get("longitude"))
    blocking: list[str] = []
    review: list[str] = []
    required = [
        "source-record ID for the 2021 census observation",
        "separate coordinate source record ID/locator and provider object ID",
        "source object classified as one physical settlement, not an aggregate or address feature",
        "independent dated or captured evidence tying a named settlement object to this point",
        "duplicate/conflict check against all other candidate settlements and provider claims",
        "blind independent validation of the rule family before any mass admission",
    ]

    if not source_id:
        blocking.append("missing_census_source_record_id")
    if not coordinate_source_id:
        blocking.append("coordinate_source_record_or_locator_missing")
    if not provider:
        blocking.append("coordinate_provider_not_named")
    if not provider_id:
        blocking.append("coordinate_provider_object_id_missing")
    if not settlement_provider_id:
        review.append("provider_settlement_component_id_missing")
    if target_year != MODERN_CENSUS_YEAR:
        blocking.append("not_a_2021_modern_point_target")
        review.append("historical_use_requires_separate_reviewed_continuity")

    if lat is None or lon is None:
        blocking.append("coordinate_missing_or_partial")
    elif not valid_wgs84(lat, lon):
        blocking.append("coordinate_outside_wgs84")
    elif not in_broad_russia_envelope(lat, lon):
        blocking.append("coordinate_outside_broad_russia_envelope")

    physical, scope_reasons = _physical_settlement_scope(candidate)
    review.extend(scope_reasons)
    if not physical and not scope_reasons:
        blocking.append("point_object_not_verified_as_physical_settlement")
    elif scope_reasons and any(
        reason in {"population_scope_is_aggregate_or_admin_unit", "point_object_is_not_a_physical_settlement", "source_object_level_is_not_a_settlement", "fias_level_is_not_city_or_settlement"}
        for reason in scope_reasons
    ):
        blocking.extend(scope_reasons)
    # An unknown FIAS level or coarse source label is held for object review.

    if _text(candidate.get("population_scope")).casefold() == "federal_city_region":
        if "federal_city_region_aggregate_excluded" not in blocking:
            blocking.append("federal_city_region_aggregate_excluded")
    if candidate.get("unaccepted_wikidata_fill") is True:
        blocking.append("coordinate_is_unaccepted_wikidata_fill")
    provider_distance = _number(candidate.get("provider_distance_km", candidate.get("wikidata_distance_km")))
    if candidate.get("provider_coordinate_conflict") is True or (
        provider_distance is not None and provider_distance > KNOWN_CONFLICT_SCREEN_KM
    ):
        blocking.append("known_provider_coordinate_conflict")
    if candidate.get("duplicate_point") is True or (_int(candidate.get("duplicate_point_group_size")) or 0) > 1:
        blocking.append("duplicate_point_needs_competitor_review")
    if _int(candidate.get("qc_geo_dadata", candidate.get("qc_geo"))) == 5:
        review.append("provider_qc_geo_reports_no_coordinate_check_claim")
    if candidate.get("measurement_date") in (None, "", "unknown"):
        review.append("coordinate_measurement_date_unknown")
    query_receipt_missing = not _text(
        candidate.get("provider_query_receipt_uri") or candidate.get("query_receipt_uri")
    )
    if query_receipt_missing:
        review.append("provider_query_receipt_missing")
    if not _text(candidate.get("evidence_uri")) or not _text(candidate.get("evidence_sha256")):
        blocking.append("primary_coordinate_evidence_locator_or_hash_missing")

    corroborators = candidate.get("corroborators") or ()
    if not isinstance(corroborators, Sequence) or isinstance(corroborators, (str, bytes)):
        corroborators = ()
        review.append("corroborators_not_a_list")
    independent_count = sum(
        1 for item in corroborators
        if isinstance(item, Mapping) and _corroborator_is_independent(candidate, item)
    )
    if independent_count == 0:
        review.append("no_independent_nonduplicate_corroborator")

    if blocking:
        status = "blocked"
        gate = "coordinate_candidate_blocked_pending_case_evidence"
    elif independent_count:
        status = "candidate_for_blind_validation"
        gate = "rule_family_not_enabled_review_sample_required"
    else:
        status = "candidate_needs_independent_evidence"
        gate = "not_eligible_for_mass_review_yet"

    return CoordinateProposal(
        source_record_id=source_id,
        target_year=target_year,
        coordinate_source_record_id=coordinate_source_id,
        coordinate_provider=provider,
        coordinate_provider_id=provider_id,
        settlement_provider_id=settlement_provider_id,
        latitude=lat,
        longitude=lon,
        status=status,
        admission_allowed=False,
        validation_gate=gate,
        independent_corroborator_count=independent_count,
        measurement_date_unknown=candidate.get("measurement_date") in (None, "", "unknown"),
        provider_query_receipt_missing=query_receipt_missing,
        blocking_reasons=tuple(dict.fromkeys(blocking)),
        review_reasons=tuple(dict.fromkeys(review)),
        evidence_required=tuple(required),
    )

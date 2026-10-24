#!/usr/bin/env python3
"""Descriptive demography of fixed candidate zones; never infer causal Word types.

The centre and its surroundings are disjoint sets. Only comparable histories
are added, while their coverage is kept beside every estimate. All functions
and scenarios are processed separately; totals must not be summed across them.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

YEARS = (2002, 2010, 2021)
DIRECTIONS = {"growth": "рост", "decline": "сокращение", "unchanged": "без изменения", "unknown": "нет сопоставимого ряда"}


def direction(first, last):
    """Exact observed sign, with no invented stability tolerance or NULL=0."""
    if pd.isna(first) or pd.isna(last):
        return "unknown"
    if first < 0 or last < 0:
        raise ValueError("Negative population")
    return "growth" if last > first else "decline" if last < first else "unchanged"


def trajectory(values):
    if any(pd.isna(v) for v in values):
        return "unknown"
    return f"{direction(values[0], values[1])}__{direction(values[1], values[2])}"


def safe_sum(values):
    return values.sum(min_count=1)


def classify_units(assignments, settlements, wide):
    """Input: one primary choice per origin/scenario/function/order, IDs str.

    Required columns assignments: origin_id, center_id, scenario, function,
    service_order. Settlements: source_record_id, root, population. Wide is the
    accepted census_wide table, one row per root. Missing center_id is retained
    in an unassigned origins output, not made into an imaginary centre.
    """
    a = assignments.copy()
    required = ["origin_id", "center_id", "scenario", "function", "service_order"]
    if set(required) - set(a):
        raise ValueError("Missing assignments columns: " + str(set(required) - set(a)))
    keys = ["scenario", "function", "service_order", "origin_id"]
    if a.duplicated(keys).any():
        raise ValueError("More than one primary choice for the same origin/scenario/function/order")
    if settlements.source_record_id.duplicated().any() or wide.root.duplicated().any():
        raise ValueError("Duplicate accepted population key")
    s = settlements.copy().set_index("source_record_id", drop=False)
    w = wide.copy().set_index("root", drop=False)
    if not a.origin_id.isin(s.index).all():
        raise ValueError("Origin outside supplied accepted settlement frame")
    nonnull = a.center_id.dropna()
    if not nonnull.isin(s.index).all():
        raise ValueError("Centre outside supplied accepted settlement frame")
    out = []
    for key, members in a[a.center_id.notna()].groupby(["scenario", "function", "service_order", "center_id"], dropna=False, sort=True):
        scenario, function, service_order, center_id = key
        centre = s.loc[center_id]
        member_records = s.loc[members.origin_id].copy()
        # If two distinct records were mapped to one accepted root, never add twice.
        if member_records.root.duplicated().any():
            raise ValueError("Repeated root within candidate zone")
        centre_root = centre.root
        surroundings = member_records[member_records.root.ne(centre_root)]
        roots = surroundings.root
        periphery_wide = w.reindex(roots)
        cr = w.loc[centre_root] if centre_root in w.index else pd.Series(dtype=object)
        full_columns = [f"effective_population_{y}" for y in YEARS]
        comparable = periphery_wide[full_columns].notna().all(axis=1)
        credit_columns=[f"working_credit_present_{y}" for y in YEARS]
        if set(credit_columns).issubset(periphery_wide):
            comparable &= periphery_wide[credit_columns].astype("boolean").fillna(False).all(axis=1)
        # Coordinate quality is not a condition for temporal numerical comparison;
        # current spatial inclusion is already determined by the accepted point.
        complete = periphery_wide.loc[comparable]
        center_series = [cr.get(c, np.nan) for c in full_columns]
        center_raw = [cr.get(f"population_{y}", np.nan) for y in YEARS]
        for j,y in enumerate(YEARS):
            if f"working_credit_present_{y}" in cr and (pd.isna(cr[f"working_credit_present_{y}"]) or not bool(cr[f"working_credit_present_{y}"])):
                center_series[j]=np.nan
                center_raw[j]=np.nan
        periphery_series = [safe_sum(complete[f"effective_population_{y}"]) for y in YEARS]
        periphery_raw = [safe_sum(complete[f"population_{y}"]) for y in YEARS]
        if complete.empty:
            periphery_series = [np.nan] * 3
            periphery_raw = [np.nan] * 3
        cdir = direction(center_series[0], center_series[2])
        pdir = direction(periphery_series[0], periphery_series[2])
        external_count = len(surroundings)
        ext_credit=surroundings.working_credit_present.astype("boolean").fillna(False) if "working_credit_present" in surroundings else pd.Series(True,index=surroundings.index)
        positive_credited=ext_credit & surroundings.population.notna() & surroundings.population.gt(0)
        positive_count=int(positive_credited.sum())
        unresolved_count=int((~ext_credit | surroundings.population.isna()).sum())
        inhabited_status="known_populated_external_members" if positive_count else "no_external_members" if not external_count else "external_inhabited_zone_unresolved" if unresolved_count else "no_populated_external_zone_in_scenario"
        if external_count == 0:
            type_code = "node_without_external_members"
            type_label = "Локальный узел без внешних участников в данном сценарии"
        elif positive_count == 0:
            type_code="node_without_known_populated_external_members"
            type_label="Узел без известных зачтённых населённых внешних участников в данном сценарии"
        elif cdir == "unknown" or pdir == "unknown":
            type_code = "insufficient_comparable_demography"
            type_label = "Недостаточно сопоставимых данных о центре или окружении"
        else:
            type_code = f"center_{cdir}__surroundings_{pdir}"
            type_label = f"Центр: {DIRECTIONS[cdir]}; окружение: {DIRECTIONS[pdir]}"
        if str(center_id).startswith("ctx:"):
            type_code="external_context_not_ordinary_settlement"
            type_label="Внешний федеральный контекст; отдельный территориальный уровень учёта"
        if type_code not in {"node_without_external_members","insufficient_comparable_demography","external_context_not_ordinary_settlement","node_without_known_populated_external_members"} and len(complete)<external_count:
            type_label+=" (неполный охват рядов)"
        cpath_effective = trajectory(center_series)
        cpath_raw = trajectory(center_raw)
        ppath_effective = trajectory(periphery_series)
        ppath_raw = trajectory(periphery_raw)
        available = all(v != "unknown" for v in [cpath_effective,cpath_raw,ppath_effective,ppath_raw])
        credited=surroundings.working_credit_present.astype("boolean").fillna(False) if "working_credit_present" in surroundings else pd.Series(True,index=surroundings.index)
        current = safe_sum(surroundings.loc[credited,"population"])
        current_comparable = safe_sum(surroundings.loc[credited & surroundings.root.isin(complete.index), "population"])
        row = dict(scenario=scenario, function=function, service_order=service_order,
            center_id=center_id, center_root=None if str(center_id).startswith("ctx:") else centre_root,
            center_name=centre.get("name", centre.get("settlement_name", center_id)),
            center_is_external_context=str(center_id).startswith("ctx:"),
            region=centre.get("region", centre.get("region_norm", "")),
            members_in_primary_partition=len(member_records), external_members=external_count,
            external_positive_credited_settlements=positive_count,external_population_or_credit_unresolved_settlements=unresolved_count,
            inhabited_external_zone_status=inhabited_status,
            center_is_primary_member=bool(member_records.root.eq(centre_root).any()),
            external_comparable_histories=len(complete),
            external_history_coverage_numerator=len(complete), external_history_coverage_denominator=external_count,
            external_current_population=current, external_current_credited_records=int(credited.sum()),
            external_comparable_current_population=current_comparable,
            type_code=type_code,type_label=type_label,
            temporal_coverage_status="external_context_separate_territorial_history" if str(center_id).startswith("ctx:") else "no_external_members" if not external_count else "complete_numeric_history" if len(complete)==external_count and all(pd.notna(v) for v in center_series) else "partial_or_missing_numeric_history",
            center_direction_2002_2021=cdir,surroundings_direction_2002_2021=pdir,
            center_trajectory_raw=cpath_raw,center_trajectory_effective=cpath_effective,
            surroundings_trajectory_raw=ppath_raw,surroundings_trajectory_effective=ppath_effective,
            raw_effective_trajectory_changed=bool(cpath_raw != cpath_effective or ppath_raw != ppath_effective) if available else None,
            unit_status="candidate_functional_zone" if positive_count else "node_without_known_populated_external_members" if external_count else "node_without_external_members",
            functional_level="single_function_service_order_not_sgrt_hierarchy",
            causal_word_type="not_inferred_without_specialization_evidence",
            geography="fixed_scenario_membership_retro_demography_not_historical_boundaries")
        if "settlement_type" in surroundings:
            urban=surroundings.settlement_type.fillna("").astype(str).str.lower().isin(["город","пгт","рабочий поселок","рабочий посёлок","городской поселок","городской посёлок"])
            rural=surroundings.loc[~urban]
            rural_complete=complete.loc[complete.index.isin(rural.root)]
            rural_series=[safe_sum(rural_complete[f"effective_population_{y}"]) for y in YEARS]
            if rural_complete.empty:rural_series=[np.nan]*3
            rural_direction=direction(rural_series[0],rural_series[2])
            rural_credit=ext_credit.reindex(rural.index).astype("boolean").fillna(False)
            rural_positive=int((rural_credit&rural.population.notna()&rural.population.gt(0)).sum())
            row["rural_external_members"]=len(rural)
            row["rural_positive_credited_settlements"]=rural_positive
            row["rural_comparable_histories"]=len(rural_complete)
            row["rural_direction_2002_2021"]=rural_direction
            row["rural_type_code"]="external_context_not_ordinary_settlement" if str(center_id).startswith("ctx:") else "no_rural_external_members" if rural.empty else "node_without_known_populated_rural_members" if not rural_positive else "insufficient_comparable_demography" if cdir=="unknown" or rural_direction=="unknown" else f"center_{cdir}__rural_{rural_direction}"
            for j,y in enumerate(YEARS):row[f"rural_comparable_effective_population_{y}"]=rural_series[j]
        for j,y in enumerate(YEARS):
            row[f"center_effective_population_{y}"]=center_series[j]
            row[f"surroundings_comparable_effective_population_{y}"]=periphery_series[j]
            row[f"center_raw_population_{y}"]=center_raw[j]
            row[f"surroundings_comparable_raw_population_{y}"]=periphery_raw[j]
        out.append(row)
    return pd.DataFrame(out)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assignments",type=Path,required=True)
    p.add_argument("--settlements",type=Path,required=True)
    p.add_argument("--wide",type=Path,required=True)
    p.add_argument("--context-settlements",type=Path,help="Explicit external nonadditive centres; no invented ordinary history")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--reference-only",action="store_true",help="Use exponential half-life30 floor.05 from model outcomes")
    a=p.parse_args()
    def read(path):return pd.read_parquet(path) if path.suffix==".parquet" else pd.read_csv(path)
    assignments=read(a.assignments)
    if "primary_candidate_id" in assignments:
        if "observation_year" in assignments and assignments.observation_year.nunique(dropna=False)>1:
            raise ValueError("Process each observation year in a separate dated case; do not merge temporal scenarios")
        if a.reference_only:
            assignments=assignments[assignments.decay_family.eq("exponential")&np.isclose(assignments.half_life_minutes,30)&np.isclose(assignments.kernel_floor,.05)].copy()
        cols=[c for c in ["source_scenario","supply_transform","model","decay_family","half_life_minutes","kernel_floor"] if c in assignments]
        assignments["scenario"]=assignments[cols].astype(str).agg("|".join,axis=1)
        assignments=assignments.rename(columns={"source_record_id":"origin_id","primary_candidate_id":"center_id"})
    settlements=read(a.settlements)
    if a.context_settlements:
        context=read(a.context_settlements).copy()
        if "source_record_id" not in context:context["source_record_id"]=context.center_id
        else:context["source_record_id"]=context.source_record_id.fillna(context.center_id)
        if "root" not in context:context["root"]="external_context:"+context.source_record_id.astype(str)
        else:context["root"]=context.root.fillna("external_context:"+context.source_record_id.astype(str))
        context["identity_scope"]="external_nonadditive_context_key_not_accepted_source_record"
        context["working_credit_present"]=False
        settlements=pd.concat([settlements,context],ignore_index=True).drop_duplicates("source_record_id",keep="first")
    result=classify_units(assignments,settlements,read(a.wide))
    a.out.mkdir(parents=True,exist_ok=True)
    result.to_parquet(a.out/"candidate_zone_types.parquet",index=False)
    result.to_csv(a.out/"candidate_zone_types.csv",index=False)
    counts=result.groupby(["scenario","function","service_order","type_code"],dropna=False).size().rename("units").reset_index()
    counts.to_csv(a.out/"type_counts.csv",index=False)
    print(json.dumps({"units":len(result),"all_have_type":bool(result.type_code.notna().all()),"candidate_zones":int(result.unit_status.eq("candidate_functional_zone").sum()),"scope":"descriptive_fixed_scenario_zones_not_causal_Word_types"},ensure_ascii=False))

if __name__=="__main__":main()

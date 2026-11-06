"""Recompute economic context from an explicit, current system membership.

Observed Rosstat organisation workers stay a partial 2025 source subset.
Municipal farm observations remain one territorial context per parent and
component: neither a settlement allocation nor an economic attraction mass.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


def _unique(frame, key, label):
    if frame[key].isna().any() or frame[key].duplicated().any():
        raise ValueError(label + ' must have one nonmissing row per ' + key)
    return frame.set_index(key, drop=False)


def _documented_scope(group):
    """Document identity coverage is separate from census-pair completeness."""
    documented = bool(group.membership_basis.astype(str).str.startswith('documented_').all()) if 'membership_basis' in group else False
    complete, held = None, None
    if documented and 'documented_membership_complete' in group:
        flags = group.documented_membership_complete
        def flag(value):
            label = str(value).lower()
            if label not in {'true', '1', '1.0', 'false', '0', '0.0'}:
                raise ValueError('Unknown document completeness flag')
            return label in {'true', '1', '1.0'}
        known = flags.dropna().map(flag)
        if known.nunique() > 1:
            raise ValueError('Conflicting document coverage within system')
        complete = bool(known.iloc[0]) if len(known) == len(group) else None
    if documented and 'documented_held_relation_rows' in group:
        counts = group.documented_held_relation_rows.dropna().astype(float)
        if counts.nunique() > 1 or (counts < 0).any() or any(not v.is_integer() for v in counts):
            raise ValueError('Conflicting held document counts within system')
        held = int(counts.iloc[0]) if len(counts) == len(group) else None
    if complete is True and held is not None and held > 0:
        raise ValueError('Document coverage contradicts held relations')
    return {'membership_is_documented': documented,
            'documented_membership_complete': complete,
            'documented_held_relation_rows': held,
            'summary_describes_accepted_geocoded_subset': documented and complete is not True}


def build_economic_context(members, np_context, municipality_context):
    """Return component summaries, distinct municipal contexts and limitations.

    Membership may overlap across systems, but must be unique inside a system.
    A core cannot also be its own external member. Self-only units are retained
    explicitly; missing source observations never become zero workers.
    """
    required = {'system_id', 'source_record_id', 'role'}
    if not required <= set(members):
        raise ValueError('Membership requires system_id, source_record_id, role')
    if members[list(required)].isna().any().any():
        raise ValueError('Membership identity and role cannot be missing')
    if members.duplicated(['system_id', 'source_record_id']).any():
        raise ValueError('A settlement occurs twice within the same system')
    if not set(members.role) <= {'core', 'external'}:
        raise ValueError('Unknown membership role')
    context = _unique(np_context, 'source_record_id', 'NP context')
    farms = municipality_context.copy()
    farms['municipality_code'] = farms.municipality_code.astype('string')
    farms = _unique(farms, 'municipality_code', 'Municipal context')
    required_context = {'partial_organisation_workforce_2025',
                        'partial_workforce_status', 'settlement_class',
                        'agri_municipality_code'}
    if not required_context <= set(context):
        raise ValueError('Required NP economic fields are missing')
    rows, municipal_rows = [], []
    for system_id, group in members.groupby('system_id', sort=True):
        core = set(group.loc[group.role.eq('core'), 'source_record_id'])
        external = set(group.loc[group.role.eq('external'), 'source_record_id'])
        if not core:
            raise ValueError('A system has no explicit core: ' + str(system_id))
        rural = {sid for sid in external if sid in context.index
                 and context.loc[sid, 'settlement_class'] == 'rural'}
        unknown_external_type = sum(sid not in context.index or context.loc[sid, 'settlement_class']
                                    not in {'rural', 'urban'} for sid in external)
        basis = sorted(set(group['membership_basis'].dropna().astype(str))) if 'membership_basis' in group else []
        document_scope = _documented_scope(group)
        for component, identities in [('centre_union', core),
                                      ('external', external),
                                      ('rural_external', rural)]:
            values, exact_values = [], []
            suppressed = unknown = missing_context = fallback = other_identity = 0
            parents, parents_unknown = {}, 0
            for sid in sorted(identities):
                if sid not in context.index:
                    unknown += 1
                    missing_context += 1
                    parents_unknown += 1
                    continue
                item = context.loc[sid]
                value = item['partial_organisation_workforce_2025']
                status = item['partial_workforce_status']
                if pd.notna(value):
                    value = float(value)
                    if status != 'observed_partial_organisation_workforce' or not math.isfinite(value) or value < 0:
                        raise ValueError('Contradictory worker value/status at ' + sid)
                    values.append(value)
                    precision = item.get('partial_worker_geographic_match_precision')
                    if precision == 'exact_2021_np_oktmo11_region_name':
                        exact_values.append(value)
                    elif precision == 'unique_name_region_with_different_or_missing_code':
                        fallback += 1
                    else:
                        other_identity += 1
                elif status == 'source_suppressed':
                    suppressed += 1
                else:
                    unknown += 1
                code = item['agri_municipality_code']
                if pd.notna(code):
                    parents.setdefault(str(code), []).append(sid)
                else:
                    parents_unknown += 1
            if len(values) + suppressed + unknown != len(identities):
                raise ValueError('Worker observation statuses do not exhaust membership')
            if len(exact_values) + fallback + other_identity != len(values):
                raise ValueError('Numeric worker identity statuses do not reconcile')
            row = {'system_id': system_id, 'component': component,
                   **document_scope,
                   'membership_basis_json': json.dumps(basis),
                   'records': len(identities),
                   'core_records_in_system': len(core),
                   'external_records_in_system': len(external),
                   'external_records_without_established_rural_urban_type': unknown_external_type,
                   'has_external_members': bool(external),
                   'numeric_partial_worker_records': len(values),
                   'source_suppressed_worker_records': suppressed,
                   'unknown_worker_records': unknown,
                   'records_without_np_context': missing_context,
                   'known_subset_partial_organisation_workers_2025': math.fsum(values) if values else None,
                   'numeric_worker_records_with_exact_np_identity': len(exact_values),
                   'numeric_worker_records_with_name_region_fallback': fallback,
                   'numeric_worker_records_with_other_or_unknown_identity': other_identity,
                   'known_subset_workers_with_exact_np_identity_2025': math.fsum(exact_values) if exact_values else None,
                   'all_partial_source_cells_numeric': bool(identities) and len(values) == len(identities),
                   'complete_jobs_or_resident_employment_known': False,
                   'worker_source': 'ROSSTAT_NP2025_PRIMARY_BOOKS',
                   'municipal_agriculture_context_codes_json': json.dumps(sorted(parents)),
                   'distinct_agriculture_context_territories': len(parents),
                   'records_without_agriculture_parent_key': parents_unknown,
                   'parent_keys_without_context_record': len(set(parents) - set(farms.index)),
                   'municipal_values_allocated_or_summed': False,
                   'overlapping_system_components_must_not_be_summed': True,
                   'membership_is_not_reconstructed_historical_service_area': True}
            rows.append(row)
            for code, settlements in sorted(parents.items()):
                item = farms.loc[code].to_dict() if code in farms.index else {'municipality_code': code}
                item.update(system_id=system_id, component=component,
                            member_records_in_municipality=len(settlements),
                            member_ids_json=json.dumps(settlements),
                            municipal_context_record_known=code in farms.index,
                            municipal_values_allocated_or_summed=False,
                            territorial_context_is_not_system_farm_output=True,
                            do_not_sum_over_systems_or_components=True)
                municipal_rows.append(item)
    components = pd.DataFrame(rows)
    municipalities = pd.DataFrame(municipal_rows)
    if len(municipalities) and municipalities.duplicated(['system_id', 'component', 'municipality_code']).any():
        raise ValueError('Repeated municipal observation in component')
    counts = members.groupby('system_id').role.apply(lambda s: int(s.eq('external').sum()))
    summary = {'schema': 'sgrt.saratov.explicit_system_economy.v1',
               'systems': int(members.system_id.nunique()),
               'membership_rows': len(members),
               'distinct_member_settlements': int(members.source_record_id.nunique()),
               'systems_with_external_members': int(counts.gt(0).sum()),
               'self_only_units': int(counts.eq(0).sum()),
               'economic_components': len(components),
               'municipal_context_rows': len(municipalities),
               'complete_jobs_or_observed_commuting_established': False,
               'municipal_farm_output_allocated_to_systems': False,
               'counts_are_compositions_not_confirmed_systems': True,
               'scope': 'Recomputed for supplied explicit memberships, never copied from old candidate unions.',
               'limitations': ['Workers are a partial 2025 organisation statistic, not all workplaces or employed residents.',
                              'Source-suppressed, unknown and out-of-context settlements remain separate.',
                              'Municipal farm observations describe whole parent territories; their rows must not be summed across memberships.',
                              'Members may occur in several systems; component worker sums must not be added across systems.']}
    return components, municipalities, summary


def read_frame(path):
    path = Path(path)
    return pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path, dtype={
        'source_record_id': 'string', 'agri_municipality_code': 'string',
        'municipality_code': 'string'})


def build_demographic_context(members, context):
    """Use the existing evidence/credit-aware helper on the new compositions.

    The current documented school and model comparison units each have one
    physical NP core. A future multicore composition requires an explicit
    multicore population definition, rather than selecting its largest member.
    """
    from scripts.sgrt_saratov.regional_context import aggregate_systems
    if members.duplicated(['system_id', 'source_record_id']).any():
        raise ValueError('Repeated demographic member')
    cores = members[members.role.eq('core')][['system_id', 'source_record_id']]
    if cores.system_id.duplicated().any() or set(cores.system_id) != set(members.system_id):
        raise ValueError('This demographic adapter requires exactly one explicit NP core')
    links = members[['system_id', 'source_record_id']].rename(columns={'source_record_id': 'origin_id'})
    links = links.merge(cores.rename(columns={'source_record_id': 'provider_settlement_id'}),
                        on='system_id', how='left', validate='many_to_one')
    basis = members.groupby('system_id').membership_basis.agg(lambda s: tuple(sorted(set(s.dropna()))))
    if any(len(v) != 1 for v in basis):
        raise ValueError('Demographic unit mixes membership definitions')
    links['family'] = links.system_id.map(basis.apply(lambda v: v[0]))
    links['is_primary'] = True
    links['context_membership_ambiguous'] = False
    components, profiles = aggregate_systems(links, context, context)
    scope = pd.DataFrame([{'system_id': sid, **_documented_scope(group)}
                          for sid, group in members.groupby('system_id', sort=True)])
    components = components.merge(scope, on='system_id', how='left', validate='many_to_one')
    profiles = profiles.merge(scope, on='system_id', how='left', validate='one_to_one')
    # Retain the helper's original joint types for the admitted subset. A
    # complete paired subset does not prove coverage of every document entry.
    profiles['accepted_subset_descriptive_dynamic_type'] = profiles.descriptive_dynamic_type
    profiles['joint_types_describe_accepted_geocoded_members'] = True
    for mode in ('accepted', 'strict'):
        for start, end in ((2002,2010),(2010,2021),(2002,2021)):
            name = f'joint_centre_rural_{start}_{end}_{mode}'
            profiles['accepted_subset_' + name] = profiles[name]
            profiles[f'classifiable_full_documented_system_{start}_{end}_{mode}'] = (
                profiles.membership_is_documented & profiles.documented_membership_complete.eq(True)
                & profiles[name].ne('unknown'))
        profiles[f'classifiable_full_documented_three_census_system_{mode}'] = (
            profiles[f'classifiable_full_documented_system_2002_2010_{mode}']
            & profiles[f'classifiable_full_documented_system_2010_2021_{mode}'])
    profiles['classifiable_full_documented_system'] = profiles.classifiable_full_documented_system_2002_2021_strict
    profiles['full_documented_system_dynamic_type_2002_2021_strict'] = [
        ('not_a_documented_system' if not r.membership_is_documented else
         'document_geography_incomplete' if pd.notna(r.documented_membership_complete) and not bool(r.documented_membership_complete) else
         'document_geography_completeness_unknown' if pd.isna(r.documented_membership_complete) else
         'self_only_without_external_component' if r.regional_external_origins == 0 else
         'census_pair_incomplete' if not r.classifiable_full_documented_system else
         r.joint_centre_rural_2002_2021_strict)
        for r in profiles.itertuples(index=False)]
    components['complete_census_component_with_complete_documented_geography'] = (
        components.membership_is_documented & components.documented_membership_complete.eq(True)
        & components.complete_component)
    components['composition_is_current_document_or_model_not_historical_flow'] = True
    profiles['composition_is_current_document_or_model_not_historical_flow'] = True
    return components, profiles


def run(membership, context, agriculture, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    members, np_context = read_frame(membership), read_frame(context)
    components, municipalities, summary = build_economic_context(
        members, np_context, read_frame(agriculture))
    demography, demographic_profiles = build_demographic_context(members, np_context)
    for name, frame in [('system_economic_components', components),
                        ('system_municipal_context', municipalities),
                        ('system_demographic_components', demography),
                        ('system_demographic_profiles', demographic_profiles)]:
        frame.to_parquet(output / (name + '.parquet'), index=False, compression='zstd')
        frame.to_csv(output / (name + '.csv'), index=False)
    summary['demographic_component_rows'] = len(demography)
    summary['demographic_profile_rows'] = len(demographic_profiles)
    summary['demographic_types_are_reported_record_comparisons_not_causal_classes'] = True
    summary['classifiable_full_documented_system_scope'] = (
        'Geographically complete current document membership plus complete strict 2002-2021 centre/rural comparisons; '
        'not a reconstructed historical service area, all-function system or proven causal type.')
    summary['by_membership_basis'] = {}
    for basis, group in members.groupby('membership_basis', sort=True):
        ids = set(group.system_id)
        sizes = group.groupby('system_id').role.apply(lambda s: int(s.eq('external').sum()))
        selected = demographic_profiles[demographic_profiles.system_id.isin(ids)]
        summary['by_membership_basis'][basis] = {
            'compositions': len(ids), 'member_rows': len(group),
            'external_compositions': int(sizes.gt(0).sum()),
            'self_only_units': int(sizes.eq(0).sum()),
            'joint_centre_rural_2002_2021_strict': selected.joint_centre_rural_2002_2021_strict.value_counts().to_dict(),
            'joint_centre_rural_2002_2021_accepted': selected.joint_centre_rural_2002_2021_accepted.value_counts().to_dict()}
        summary['by_membership_basis'][basis].update(
            classifiable_full_documented_system_2002_2021_strict=int(selected.classifiable_full_documented_system.sum()),
            full_documented_system_dynamic_type_2002_2021_strict=selected.full_documented_system_dynamic_type_2002_2021_strict.value_counts().to_dict(),
            classifiable_full_documented_three_census_system_strict=int(selected.classifiable_full_documented_three_census_system_strict.sum()))
    (output / 'economic_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--membership', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--agriculture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.membership, args.context, args.agriculture, args.output), ensure_ascii=False, indent=2))

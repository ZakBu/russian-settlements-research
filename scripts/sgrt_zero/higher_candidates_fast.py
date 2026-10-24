#!/usr/bin/env python3
"""Exact aggregation alternative to hierarchy.higher_candidates.

Changes execution only: canonical validation, source scenarios, whole-child
coverage, target split, nulls and territorial guards retain original semantics.
The original helper is not patched or selected automatically.
"""
from __future__ import annotations
import pandas as pd
try:
    from .hierarchy import canonical_edges, dumps
except ImportError:
    from hierarchy import canonical_edges, dumps


def higher_candidates_fast(memberships, higher_edges, reference):
    if any(isinstance(memberships[c].dtype, pd.CategoricalDtype) for c in ['unit_id', 'scenario_id']):
        try:
            from .hierarchy import higher_candidates
        except ImportError:
            from hierarchy import higher_candidates
        return higher_candidates(memberships, higher_edges, reference)
    frame = canonical_edges(higher_edges, admission='higher_admitted')
    if not frame.loc[frame.provider_settlement_id.notna(), 'provider_settlement_id'].isin(reference.source_record_id.dropna()).all():
        raise ValueError('A declared higher provider settlement is outside the accepted identity reference')
    if memberships.duplicated(['scenario_id', 'origin_id']).any():
        raise ValueError('Child memberships must form an explicit partition per scenario')
    families = sorted(frame.service_family.unique())
    if frame.scenario_id.nunique() != 1:
        raise ValueError('Choose one explicit higher source scenario per call')
    if 'parent_target_key' not in frame:
        frame['parent_target_key'] = frame.provider_key
    else:
        frame['parent_target_key'] = frame.parent_target_key.fillna(frame.provider_key)
    if 'parent_target_kind' not in frame:
        frame['parent_target_kind'] = 'provider'
    else:
        frame['parent_target_kind'] = frame.parent_target_kind.fillna('provider')
    is_reference = frame.parent_target_key.astype('string').str.startswith('efua:', na=False)
    if (is_reference & frame.parent_target_kind.eq('provider')).any():
        raise ValueError('An external area cannot masquerade as one provider')
    good = frame[frame.higher_admitted].copy()
    # Compute eq(True) in the original dtype. Nullable boolean NA is skipped by
    # Series.all(); object-dtype NA becomes False under eq, just as in original.
    good['_guard_equal_true'] = (good.territorial_merge_admitted.eq(True)
                               if 'territorial_merge_admitted' in good else False)
    has_basis = 'territorial_guard_basis' in good
    fields = ['origin_id', 'service_family', 'parent_target_key', 'provider_key',
              'provider_site_id', 'parent_target_kind', 'cost_minutes',
              '_guard_equal_true', 'source_id', 'source_year']
    if has_basis:
        fields.append('territorial_guard_basis')
    good = good[fields]
    del frame

    def unique(values):
        return dumps(sorted(values))

    result = []
    for scenario, member in memberships.groupby('scenario_id', sort=True):
        children = {}
        aggregates = {}
        for child, origin in member[['unit_id', 'origin_id']].itertuples(index=False, name=None):
            if pd.isna(child):
                continue  # pandas groupby drops null child keys.
            children[child] = children.get(child, 0) + 1
        joined = member[['unit_id', 'origin_id']].merge(good, on='origin_id', how='left', validate='one_to_many')
        for values in joined.loc[joined.service_family.notna(), ['unit_id', *fields]].itertuples(index=False, name=None):
            child, origin, family, target, provider, site, kind, cost, guard, source, year, *basis = values
            if pd.isna(child):
                continue
            aggregate = aggregates.setdefault((child, family), {'covered': set(), 'targets': {}})
            aggregate['covered'].add(origin)
            if pd.isna(target):
                continue
            q = aggregate['targets'].setdefault(target, {'origins': set(), 'rows': 0,
                'providers': set(), 'sites': set(), 'kinds': set(), 'sources': set(),
                'years': set(), 'bases': set(), 'max': float('-inf'), 'guard': True})
            q['origins'].add(origin); q['rows'] += 1; q['max'] = max(q['max'], cost)
            if pd.notna(guard):
                q['guard'] = q['guard'] and bool(guard)
            for field, value in [('providers', provider), ('sites', site), ('kinds', kind),
                                 ('sources', source), ('years', year)]:
                if pd.notna(value):
                    q[field].add(str(value))
            if has_basis and pd.notna(basis[0]):
                q['bases'].add(str(basis[0]))
        for child, n_all in children.items():
            for family in families:
                aggregate = aggregates.get((child, family))
                targets = aggregate['targets'] if aggregate else {}
                keys = sorted(targets)
                n_covered = len(aggregate['covered']) if aggregate else 0
                single_complete = len(keys) == 1 and n_covered == n_all
                status = ('no_known_higher_candidate' if not keys else
                          'split_higher_candidates' if len(keys) > 1 else
                          'partial_higher_coverage' if n_covered < n_all else
                          'complete_single_external_area_candidate' if str(keys[0]).startswith('efua:') else
                          'complete_single_higher_candidate')
                for key in keys or [None]:
                    q = targets.get(key)
                    providers = q['providers'] if q else set()
                    result.append({'child_unit_id': child, 'scenario_id': scenario,
                        'service_family': family, 'parent_target_key': key,
                        'provider_key': next(iter(providers)) if len(providers) == 1 else pd.NA,
                        'real_provider_keys_json': unique(providers),
                        'real_provider_site_ids_json': unique(q['sites']) if q else '[]',
                        'parent_target_kinds_json': unique(q['kinds']) if q else '[]',
                        'external_reference_parent_target': bool(str(key).startswith('efua:')),
                        'coverage_type': status, 'child_member_records': n_all,
                        'higher_covered_member_records': n_covered,
                        'members_for_this_provider': len(q['origins']) if q else 0,
                        'maximum_directed_minutes': q['max'] if q else float('nan'),
                        'complete_single_parent_by_this_function': single_complete,
                        'territorial_merge_admitted_for_all_child_members': bool(single_complete and q is not None and q['rows'] == n_all and q['guard']),
                        'territorial_guard_bases_json': unique(q['bases']) if q else '[]',
                        'source_ids_json': unique(q['sources']) if q else '[]',
                        'source_years_json': unique(q['years']) if q else '[]',
                        'is_observed_commuting_or_patient_flow': False,
                        'rare_service_alone_defines_agglomeration': False})
    return pd.DataFrame(result)

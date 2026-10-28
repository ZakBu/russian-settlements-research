"""Exact demographic and economic context for the complete Saratov roster.

Municipal agricultural/sector observations stay in separate territory tables.
Only published settlement-grain Rosstat worker observations join NP rows. The
national FNS legal-entity headcount table has no workplace-address allocation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_field_pilot.input_inventory import catalog_source
from scripts.sgrt_zero.centre_demographic_readout import OBSERVED_QUALITIES

YEARS = (2002, 2010, 2021)
URBAN = frozenset({'город', 'пгт', 'посёлок городского типа', 'рабочий посёлок'})
RURAL = frozenset({'село', 'посёлок', 'деревня', 'хутор', 'станция',
    'железнодорожный объект', 'железнодорожный разъезд', 'железнодорожная станция'})
PROTECTED = 'secondary_confidentiality_protected_value_exact_scope_unverified'
MEMBERS = {
    'roster': ('data/saratov_isochrones_catalog_20261028.json',
        'sgrt/saratov-isochrones20261028/results/inputs/all_current_settlements.parquet'),
    'agriculture': ('data/mass_catalog_20261024.json',
        'sgrt/mass20261024/context/settlement_agriculture_context.parquet'),
    'partial_workers': ('data/mass_catalog_20261024.json',
        'sgrt/mass20261024/context/settlement_partial_workforce.parquet'),
    'worker_evidence': ('data/mass_catalog_20261024.json',
        'sgrt/mass20261024/context/partial_workforce_source_rows.parquet'),
    'agriculture_snapshots': ('data/mass_catalog_20261024.json',
        'sgrt/mass20261024/context/municipal_agriculture_snapshots.parquet'),
    'parent_crosswalk': ('data/upper_research_catalog_20261027.json',
        'sgrt/upper20261027/results/municipal/reference_parent_crosswalk.parquet'),
    'municipal_workers': ('data/upper_research_catalog_20261027.json',
        'sgrt/upper20261027/results/workforce/data_Y48423005_112_v20260928.parquet'),
}
OPTIONAL_MEMBERS = {'system_reference': ('data/zero_catalog_20261025.json',
    'sgrt/zero20261025/context/analysis_reference.parquet')}


PRIMARY2010_QUALITY='regional_primary_2010_reported_value_frozen_reader_unique_original_identity'
OBSERVED_QUALITIES=OBSERVED_QUALITIES|{PRIMARY2010_QUALITY}


def annualized_change_percent(start,end,years,complete=True):
    """CAGR for two positive populations; zero endpoints keep timing unknown."""
    if not np.isfinite(years) or years<=0:raise ValueError('Annualization needs a positive calendar-year interval')
    if not complete or pd.isna(start) or pd.isna(end) or not np.isfinite(start) or not np.isfinite(end) or start<0 or end<0:
        return np.nan,'unknown_or_incomplete_population_pair'
    if start==0 and end==0:return np.nan,'both_published_zero_without_positive_baseline'
    if start==0:return np.nan,'appearance_from_zero_baseline_timing_unknown'
    if end==0:return np.nan,'depopulation_to_zero_timing_unknown'
    return 100*math.expm1(math.log(float(end)/float(start))/float(years)),'defined_positive_endpoints'


def apply_primary2010_evidence(frame,evidence):
    """A separate analytical variant; preserve every original value and quality."""
    if evidence.source_record_id_2010.duplicated().any():raise ValueError('Primary2010 evidence IDs are not unique')
    out=frame.copy();lookup=evidence.set_index('source_record_id_2010')
    key=out.source_record_id_2010
    out['foundation_population_2010_before_primary_evidence']=out.population_2010
    out['foundation_population_value_quality_2010_before_primary_evidence']=out.population_value_quality_2010
    out['primary2010_identity_match_status']=key.map(lookup.identity_match_status)
    out['primary2010_value_from_publication']=key.map(lookup.primary_population_2010)
    out['primary2010_evidence_original_legacy_value']=key.map(lookup.legacy_population_2010)
    allowed=key.map(lookup.primary_value_admissible_in_separate_derived_variant).eq(True)
    old=out.primary2010_evidence_original_legacy_value
    drift=allowed & ~(out.population_2010.eq(old)|(out.population_2010.isna()&old.isna()))
    if drift.any():raise ValueError('Analysis reference and pinned2010 foundation disagree before primary overlay')
    out['primary2010_derived_evidence_applied']=allowed
    out['primary2010_value_difference_from_foundation']=out.primary2010_value_from_publication-out.population_2010
    out['primary2010_value_equals_foundation']=out.primary2010_value_from_publication.eq(out.population_2010).where(allowed)
    out.loc[allowed,'population_2010']=out.loc[allowed,'primary2010_value_from_publication']
    out.loc[allowed,'population_value_quality_2010']=PRIMARY2010_QUALITY
    out['primary2010_identity_evidence_scope']='unique original2010 typed name in both provincial frames; not independent intercensus-chain or boundary proof'
    out['primary2010_frozen_population_foundation_modified']=False
    out['primary2010_population_scope_comparability_unverified']=True
    out['primary2010_reported_total_scenario_not_complete_temporal_comparability']=True
    return out



def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def verify_source(kind, path):
    catalog, member = {**MEMBERS,**OPTIONAL_MEMBERS}[kind]
    spec = catalog_source(REPO/catalog, member)
    if Path(path).stat().st_size != spec['bytes'] or sha(path) != spec['sha256']:
        raise ValueError('Pinned source bytes differ: '+kind)
    return {'kind': kind, **spec}


def unique_current(frame, name):
    result = frame.loc[frame.source_record_id.notna()].copy()
    if result.source_record_id.duplicated().any():
        raise ValueError(name+' contains duplicate current source_record_id')
    return result


def observation_class(value, quality, source_record_id):
    if pd.isna(source_record_id):
        return 'missing_census_record'
    if pd.isna(value) or not np.isfinite(value) or value < 0:
        return 'missing_or_invalid_population'
    if quality in OBSERVED_QUALITIES:
        return 'primary_reported_value'
    if quality == PROTECTED:
        return 'secondary_confidentiality_value_scope_unverified'
    if pd.notna(quality) and any(token in str(quality).lower()
            for token in ('imput', 'interpol', 'derived', 'split', 'modelled', 'modeled')):
        return 'explicitly_derived_or_imputed_value'
    return 'other_nonprimary_value'


def direction(a, b):
    return 'growth' if b > a else 'decline' if b < a else 'unchanged'


def eligible_record(record, year, mode):
    value = record.get(f'population_{year}')
    credit = record.get(f'credit_{year}')
    budget = record.get('budget_population_credit')
    good = (pd.notna(value) and np.isfinite(value) and value >= 0
        and pd.notna(record.get(f'source_record_id_{year}'))
        and pd.notna(credit) and credit == 1 and pd.notna(budget) and budget == 1)
    return bool(good and (mode == 'accepted' or record.get(f'population_value_quality_{year}') in OBSERVED_QUALITIES))


def settlement_class(value):
    return 'urban' if value in URBAN else 'rural' if value in RURAL else 'type_unknown'


def build_np_context(roster, agriculture, partial_workers, parent_crosswalk):
    """Keep all current roster rows; no population filtering or imputation."""
    out = unique_current(roster, 'roster').copy()
    if len(out) != len(roster):
        raise ValueError('Every roster row needs a current record ID')
    agriculture = unique_current(agriculture, 'agriculture')
    workers = unique_current(partial_workers, 'partial workforce')
    crosswalk = unique_current(parent_crosswalk, 'parent crosswalk')
    if not out.root.is_unique:
        raise ValueError('Current chain roots must be unique')
    # Join only keys/quality, not repeated municipal numbers, into the NP table.
    agri_keys = ['source_record_id', 'agri_municipality_code', 'parent_relation_rule',
        'agri_parent_match_status', 'historical_boundary_equivalence_proven']
    worker_fields = [c for c in workers if c not in {'root', 'ordinary_spatial_2021'}]
    out = out.merge(agriculture[agri_keys], on='source_record_id', how='left', validate='one_to_one')
    out = out.merge(workers[worker_fields], on='source_record_id', how='left', validate='one_to_one')
    out = out.merge(crosswalk, on='source_record_id', how='left', validate='one_to_one')
    if len(out) != len(roster):
        raise ValueError('Context join changed roster cardinality')
    out['settlement_class'] = np.where(out.settlement_type_2021.isin(URBAN), 'urban',
        np.where(out.settlement_type_2021.isin(RURAL), 'rural', 'type_unknown'))
    for year in YEARS:
        out[f'population_observation_class_{year}'] = [observation_class(v, q, sid)
            for v, q, sid in zip(out[f'population_{year}'],
                out[f'population_value_quality_{year}'], out[f'source_record_id_{year}'])]
        valid = (out[f'population_{year}'].notna()
            & np.isfinite(out[f'population_{year}']) & out[f'population_{year}'].ge(0)
            & out[f'source_record_id_{year}'].notna() & out[f'credit_{year}'].eq(True)
            & out.budget_population_credit.eq(True))
        out[f'population_eligible_{year}_accepted'] = valid
        out[f'population_eligible_{year}_strict'] = valid & out[f'population_value_quality_{year}'].isin(OBSERVED_QUALITIES)
    for mode in ('accepted', 'strict'):
        for start, end in ((2002, 2010), (2010, 2021), (2002, 2021)):
            eligible = out[f'population_eligible_{start}_{mode}'] & out[f'population_eligible_{end}_{mode}']
            a, b = out[f'population_{start}'], out[f'population_{end}']
            label = f'{start}_{end}_{mode}'
            result = pd.Series('unknown', index=out.index)
            result.loc[eligible & b.gt(a)] = 'growth'
            result.loc[eligible & b.lt(a)] = 'decline'
            result.loc[eligible & b.eq(a)] = 'unchanged'
            out[f'demographic_direction_{label}'] = result
            out[f'population_change_absolute_{label}'] = (b-a).where(eligible)
            out[f'population_change_percent_{label}'] = (100*(b/a-1)).where(eligible & a.gt(0))
            out[f'change_rate_status_{label}'] = np.where(~eligible, 'unknown_pair',
                np.where(a.gt(0), 'defined_positive_baseline', 'zero_baseline_rate_undefined'))
            annual=[annualized_change_percent(x,y,end-start,bool(ok)) for x,y,ok in zip(a,b,eligible)]
            out[f'annualized_population_change_percent_{label}']=[r[0] for r in annual]
            out[f'annualized_population_change_status_{label}']=[r[1] for r in annual]
            out[f'annualization_calendar_years_{label}']=end-start
        complete = np.logical_and.reduce([out[f'population_eligible_{y}_{mode}'] for y in YEARS])
        out[f'demographic_trajectory_2002_2010_2021_{mode}'] = (
            out[f'demographic_direction_2002_2010_{mode}']+'__'+out[f'demographic_direction_2010_2021_{mode}']).where(complete, 'unknown')
    # No FNS/municipal allocation is smuggled into an unobserved jobs field.
    if out.total_settlement_jobs.notna().any():
        raise ValueError('The pinned context unexpectedly asserts complete NP jobs')
    out['workforce_observation_source'] = np.where(out.partial_organisation_workforce_2025.notna(),
        'ROSSTAT_NP2025_PRIMARY_BOOKS', 'no_numeric_settlement_worker_observation')
    out['fns_legal_entity_headcount_allocated_to_np'] = False
    out['municipal_agriculture_allocated_to_np'] = False
    out['municipal_workers_allocated_to_np'] = False
    out['historical_membership_reconstructed'] = False
    out['underlying_np_boundary_equivalence_established'] = False
    out['population_scope_comparability_unverified']=True
    out['population_direction_is_reported_record_comparison'] = True
    return out.sort_values('source_record_id').reset_index(drop=True)


def attach_worker_source_identity(context, evidence):
    """Keep the original geographic matching precision beside each NP value."""
    selected=evidence[evidence.source_record_id.isin(set(context.source_record_id)) & evidence.match_status.eq('matched')
        & evidence.column_semantics_verified.eq(True) & evidence.observation_year.eq(2025)].copy()
    out=context.copy();rows=[]
    for sid,group in selected.groupby('source_record_id',sort=False):
        values=group[group.value_status.eq('observed')&group.value.notna()]
        methods=sorted(set(values.match_method.dropna().astype(str)))
        row={'source_record_id':sid,
            'partial_worker_geographic_match_methods_json':json.dumps(methods),
            'partial_worker_original_source_oktmo_codes_json':json.dumps(sorted(set(group.source_oktmo.dropna().astype(str)))),
            'partial_worker_original_source_locators_json':json.dumps(sorted(set(str(r.source_file)+'#'+str(r.source_sheet)+':'+str(r.source_excel_row) for r in group.itertuples(index=False))),ensure_ascii=False),
            'partial_worker_numeric_identity_exact_2021_oktmo11':bool(len(values)) and bool(methods) and all(m=='exact_settlement_oktmo11_region_name' for m in methods),
            'partial_worker_numeric_identity_uses_name_region_fallback':any(m=='exact_normalized_name_region' for m in methods)}
        rows.append(row)
    identity_columns=['source_record_id','partial_worker_geographic_match_methods_json','partial_worker_original_source_oktmo_codes_json','partial_worker_original_source_locators_json','partial_worker_numeric_identity_exact_2021_oktmo11','partial_worker_numeric_identity_uses_name_region_fallback']
    out=out.merge(pd.DataFrame(rows,columns=identity_columns),on='source_record_id',how='left',validate='one_to_one')
    numeric=out.partial_organisation_workforce_2025.notna()
    if out.loc[numeric,'partial_worker_geographic_match_methods_json'].isna().any():
        raise ValueError('Numeric worker observation lost its source identity provenance')
    out['partial_worker_geographic_match_precision']=np.where(~numeric,'no_numeric_observation',
        np.where(out.partial_worker_numeric_identity_exact_2021_oktmo11.eq(True),'exact_2021_np_oktmo11_region_name',
            np.where(out.partial_worker_numeric_identity_uses_name_region_fallback.eq(True),'unique_name_region_with_different_or_missing_code','other_source_match_requires_inspection')))
    return out


def territory_agriculture(np_context, agriculture, snapshots):
    """One context row per parent; full dated source rows remain separate."""
    relevant = agriculture[agriculture.source_record_id.isin(np_context.source_record_id)].copy()
    codes = set(relevant.agri_municipality_code.dropna())
    cols = [c for c in relevant if c.startswith('agri_') and c not in
        {'agri_municipality_code', 'agri_parent_match_status'}]
    rows = []
    for code, group in relevant.dropna(subset=['agri_municipality_code']).groupby('agri_municipality_code', sort=True):
        row = {'municipality_code': code, 'regional_current_np_records': len(group),
            'scope': 'municipal_context_not_settlement_allocation',
            'historical_boundary_equivalence_proven': False}
        for c in cols:
            known = group[c].dropna().unique()
            if len(known) > 1:
                raise ValueError('Conflicting municipal observation repeated across NP: '+str(code)+'/'+c)
            row[c] = known[0] if len(known) else None
        rows.append(row)
    selected = snapshots[snapshots.municipality_code.isin(codes)].copy()
    # The same actual row can have both 2021/latest roles; preserve this label,
    # not sum it as a second observation.
    selected['do_not_sum_reference_roles'] = True
    selected['allocated_to_np'] = False
    return pd.DataFrame(rows), selected


def agriculture_demographic_context(np_context, territories):
    """Compare municipality-level farm structure with its current rural roster.

    Each municipality appears once. Counts refer to current NP membership and
    reported census chains, not reconstructed historical municipal boundaries.
    No agricultural total becomes a settlement mass or an attraction score.
    """
    if territories.municipality_code.duplicated().any():raise ValueError('Agriculture contexts must be unique')
    rows=[]
    for row in territories.to_dict('records'):
        code=row['municipality_code']
        group=np_context[np_context.agri_municipality_code.eq(code)]
        rural=group[group.settlement_class.eq('rural')]
        counts=rural.demographic_direction_2002_2021_strict.value_counts()
        known=int(counts.get('growth',0)+counts.get('decline',0)+counts.get('unchanged',0))
        total=row.get('agri_output_nominal_thousand_rub_2021_municipal_context')
        crop=row.get('agri_crop_output_nominal_thousand_rub_2021_municipal_context')
        livestock=row.get('agri_livestock_output_nominal_thousand_rub_2021_municipal_context')
        valid=pd.notna(total) and total>0 and pd.notna(crop) and crop>=0 and crop<=total
        row.update(current_rural_np_records=len(rural),
            current_rural_np_with_strict_reported_2002_2021_comparison=known,
            current_rural_np_decline_2002_2021=int(counts.get('decline',0)),
            current_rural_np_growth_2002_2021=int(counts.get('growth',0)),
            current_rural_np_unchanged_2002_2021=int(counts.get('unchanged',0)),
            current_rural_np_unknown_comparison_2002_2021=int(counts.get('unknown',0)),
            rural_np_decline_share_among_known_record_comparisons=counts.get('decline',0)/known if known else np.nan,
            crop_share_of_published_agriculture_output_2021=crop/total if valid else np.nan,
            crop_plus_livestock_minus_total_thousand_rub_2021=crop+livestock-total if all(pd.notna(v) for v in [crop,livestock,total]) else np.nan,
            agricultural_mass_allocated_to_settlement=False,
            association_is_causal_or_boundary_harmonised=False)
        rows.append(row)
    return pd.DataFrame(rows)


def territory_workforce(np_context, raw):
    codes = set(np_context.matched_2021_parent_code.dropna())
    selected = raw[raw.oktmo.isin(codes) & raw.indicator_code.eq('Y48423005')
        & raw.indicator_period.eq('Январь-декабрь') & raw.year.isin([2021, 2025])].copy()
    key = ['oktmo', 'year', 'okved2', 'indicator_code', 'indicator_period']
    if selected.duplicated(key).any():
        raise ValueError('Duplicate native annual workforce keys')
    if not selected.indicator_unit.eq('Человек').all():
        raise ValueError('Unexpected municipal workforce units')
    selected['workers_allocated_to_np'] = False
    selected['section_A_is_not_pure_agriculture'] = True
    selected['boundary_equality_to_2021_not_proven'] = True
    rows = []
    for (code, year), group in selected.groupby(['oktmo', 'year'], sort=True):
        total = group[group.okved2.eq('Всего по обследуемым видам экономической деятельности')]
        section = group[group.okved2.str.match(r'^Раздел [AА] ', na=False)]
        a = section.indicator_value.iloc[0] if len(section) == 1 else np.nan
        t = total.indicator_value.iloc[0] if len(total) == 1 else np.nan
        if pd.notna(a) and pd.notna(t) and (a < 0 or t < a):
            raise ValueError('Sector A is negative or exceeds the same-scope total')
        rows.append({'municipality_code': code, 'year': int(year),
            'municipality': group.municipality.iloc[0],
            'partial_organisation_workers': t, 'section_A_partial_workers': a,
            'section_A_share_of_partial_workers': a/t if pd.notna(a) and pd.notna(t) and t > 0 else np.nan,
            'scope': 'municipal_organisations_excluding_small_business_not_resident_employment',
            'section_A_includes_forestry_hunting_fishing': True,
            'boundary_equality_to_2021_not_proven': True})
    return pd.DataFrame(rows), selected


def primary_context_links(links):
    # Keep evidence alternatives in separate analyses, never duplicate a
    # settlement because a historical-evidence sensitivity run was appended.
    out=links[links.is_primary.eq(True)].copy()
    if 'evidence_scenario' in out:
        out=out[out.evidence_scenario.eq('all_dated_known')].copy()
    return out


def candidate_context_system_links(links):
    """Retain every equal-nearest system, without calling any unique choice."""
    source=links.copy()
    if 'evidence_scenario' in source:
        source=source[source.evidence_scenario.eq('all_dated_known')]
    rows=[]
    for row in source.to_dict('records'):
        encoded=row.get('coequal_primary_keys_json')
        keys=json.loads(encoded) if isinstance(encoded,str) else []
        ambiguous=bool(row.get('ambiguous_primary',False)) or len(keys)>1
        if ambiguous:
            if len(keys)<2:raise ValueError('Ambiguous outcome lacks its full candidate set')
            for key in keys:
                expanded=dict(row)
                expanded['system_id']='functional:'+hashlib.sha256((str(row['family'])+'|'+str(key)).encode()).hexdigest()[:24]
                expanded['provider_settlement_id']=key[3:] if key.startswith('np:') else None
                expanded['provider_site_id']=key[5:] if key.startswith('site:') else None
                expanded['context_membership_ambiguous']=True
                rows.append(expanded)
        elif row.get('is_primary',False) and pd.notna(row.get('system_id')):
            row['context_membership_ambiguous']=bool(row.get('context_membership_ambiguous',False))
            rows.append(row)
    return pd.DataFrame(rows,columns=list(source.columns)+(['context_membership_ambiguous'] if 'context_membership_ambiguous' not in source else []))


def aggregate_systems(links, context, reference=None):
    """Demography of fixed primary functional systems, allowing overlaps.

    Input needs system_id/origin_id/provider_settlement_id/family/is_primary.
    A system with a physical site whose NP is unresolved has no invented centre
    population. Only in-region origins enter this regional model composition.
    """
    reference = context if reference is None else reference
    ref = unique_current(reference, 'system reference').set_index('source_record_id')
    ref_ids=set(ref.index)
    row_cache={}
    def record(sid):
        if sid not in row_cache:row_cache[sid]=ref.loc[sid].to_dict()
        return row_cache[sid]
    required = {'system_id', 'origin_id', 'provider_settlement_id', 'family', 'is_primary'}
    if not required <= set(links):
        raise ValueError('Functional links missing '+str(sorted(required-set(links))))
    links = candidate_context_system_links(links)
    if 'link_kind' in links:
        links = links[~links.link_kind.eq('unknown')]
    components, classes = [], []
    for system_id, group in links.groupby('system_id', sort=True):
        family = group.family.unique()
        providers = group.provider_settlement_id.dropna().unique()
        if len(family) != 1 or len(providers) > 1:
            raise ValueError('A single-function primary system has conflicting provider identities')
        centre = providers[0] if len(providers) else None
        origins = sorted(set(group.origin_id))
        unknown_origins = set(origins)-ref_ids
        if unknown_origins:
            raise ValueError('Members outside supplied reference')
        external = [sid for sid in origins if sid != centre]
        types = {sid:record(sid).get('settlement_class', settlement_class(record(sid).get('settlement_type_2021')))
            for sid in external}
        rural = [sid for sid in external if types[sid] == 'rural']
        unknown_type = [sid for sid in external if types[sid] not in {'rural', 'urban'}]
        centre_records = [centre] if centre in ref.index else []
        status = 'known_np_provider' if centre_records else 'provider_np_identity_or_population_unknown'
        row = {'system_id': system_id, 'family': family[0], 'centre_id': centre,
            'centre_identity_status': status, 'regional_origins': len(origins),
            'ambiguous_candidate_member_records':int(group.loc[group.context_membership_ambiguous,'origin_id'].nunique()),
            'all_model_memberships_unique':not bool(group.context_membership_ambiguous.any()),
            'regional_external_origins': len(external), 'regional_rural_external_origins': len(rural),
            'regional_external_published_positive_origins': sum(pd.notna(record(sid)['population_2021']) and record(sid)['population_2021']>0 for sid in external),
            'regional_rural_external_published_positive_origins': sum(pd.notna(record(sid)['population_2021']) and record(sid)['population_2021']>0 for sid in rural),
            'regional_unknown_type_external_origins': len(unknown_type),
            'membership_reference_year': None, 'settlement_roster_reference_year':2021,
            'functional_inventory_dates_mixed':True, 'historical_boundaries_reconstructed': False,
            'underlying_np_boundary_equivalence_established': False,
            'population_scope_comparability_unverified':True,
            'causal_word_type_established': False}
        for mode in ('accepted', 'strict'):
            for start, end in ((2002, 2010), (2010, 2021), (2002, 2021)):
                results = {}
                for scope, ids in [('centre', centre_records), ('external', external), ('rural_external', rural)]:
                    complete_ids = [sid for sid in ids if eligible_record(record(sid), start, mode)
                        and eligible_record(record(sid), end, mode)]
                    complete = bool(ids) and len(complete_ids) == len(ids)
                    if scope == 'rural_external' and unknown_type:
                        complete = False
                    a = sum(record(sid)[f'population_{start}'] for sid in complete_ids) if complete_ids else np.nan
                    b = sum(record(sid)[f'population_{end}'] for sid in complete_ids) if complete_ids else np.nan
                    result = direction(a, b) if complete else 'unknown'
                    annual,annual_status=annualized_change_percent(a,b,end-start,complete)
                    components.append({'system_id': system_id, 'family': family[0], 'centre_id': centre,
                        'component': scope, 'start_year': start, 'end_year': end, 'evidence_mode': mode,
                        'records': len(ids), 'paired_eligible_records': len(complete_ids),
                        'complete_component': complete, 'paired_known_population_start': a,
                        'paired_known_population_end': b, 'direction': result,
                        'known_partial_sum_is_not_complete_total': not complete,
                        'annualized_population_change_percent':annual,'annualized_population_change_status':annual_status,
                        'annualization_calendar_years':end-start,'population_scope_comparability_unverified':True,
                        'underlying_np_boundary_equivalence_established':False})
                    results[scope] = result
                    row[f'{scope}_direction_{start}_{end}_{mode}'] = result
                    row[f'{scope}_annualized_change_percent_{start}_{end}_{mode}']=annual
                    row[f'{scope}_annualized_change_status_{start}_{end}_{mode}']=annual_status
                joint = results['centre']+'__'+results['rural_external']
                row[f'joint_centre_rural_{start}_{end}_{mode}'] = joint if 'unknown' not in joint else 'unknown'
        for mode in ('accepted','strict'):
            for scope in ('centre','external','rural_external'):
                a=row[f'{scope}_direction_2002_2010_{mode}']
                b=row[f'{scope}_direction_2010_2021_{mode}']
                row[f'{scope}_trajectory_2002_2010_2021_{mode}']=a+'__'+b if 'unknown' not in (a,b) else 'unknown'
        # Every system has an explicit descriptive type; absence of a complete
        # trajectory is a data-evidence type, not an empty classification cell.
        if not centre_records:
            kind = 'provider_identity_unresolved'
        elif not external:
            kind = 'self_service_without_modelled_external_participant'
        elif not rural:
            kind = 'external_system_without_established_rural_component'
        elif row['joint_centre_rural_2002_2021_strict'] != 'unknown':
            kind = 'primary_observed__'+row['joint_centre_rural_2002_2021_strict']
        elif row['joint_centre_rural_2002_2021_accepted'] != 'unknown':
            kind = 'accepted_values__'+row['joint_centre_rural_2002_2021_accepted']
        else:
            kind = 'incomplete_population_evidence'
        row['descriptive_dynamic_type'] = ('ambiguous_candidate_membership__' if group.context_membership_ambiguous.any() else '')+kind
        row['functional_service_class']=str(family[0])
        row['descriptive_territorial_role']=('provider_np_identity_unresolved' if not centre_records else
            'rural_external_service_candidate' if row['regional_rural_external_published_positive_origins']>0 else
            'external_service_candidate_rural_scope_unresolved' if unknown_type and row['regional_external_published_positive_origins']>0 else
            'nonrural_external_service_candidate' if row['regional_external_published_positive_origins']>0 else
            'self_or_depopulated_external_records_only')
        row['dynamic_evidence_status']=('strict_primary_reported' if row['joint_centre_rural_2002_2021_strict']!='unknown' else
            'accepted_values_only' if row['joint_centre_rural_2002_2021_accepted']!='unknown' else 'insufficient_complete_component_evidence')
        classes.append(row)
    return pd.DataFrame(components), pd.DataFrame(classes)


def aggregate_configurations(configurations, links, context, reference=None,
        families=('school','medical_basic','grocery')):
    """Describe shared basic-service vectors without forcing nested districts."""
    if 'evidence_scenario' in configurations:
        configurations=configurations[configurations.evidence_scenario.eq('all_dated_known')].copy()
    if configurations.origin_id.duplicated().any() or set(configurations.origin_id)!=set(context.source_record_id):
        raise ValueError('Every regional origin needs one configuration/status row')
    ref=unique_current(context if reference is None else reference,'configuration reference').set_index('source_record_id')
    ref_ids=set(ref.index)
    row_cache={}
    def record(sid):
        if sid not in row_cache:row_cache[sid]=ref.loc[sid].to_dict()
        return row_cache[sid]
    primary=primary_context_links(links)
    primary=primary[primary.family.isin(families)].copy()
    components=[];classes=[]
    # Unresolved origins are explicit status records, never counted as completed
    # territorial systems merely to fill a classification table.
    for row in configurations[configurations.basic_configuration_id.isna()].itertuples(index=False):
        classes.append({'configuration_id':None,'origin_status_record_id':row.origin_id,
            'unit_kind':'unresolved_origin_record','regional_origins':1,
            'descriptive_configuration_type':'basic_functional_directions_incomplete',
            'historical_boundaries_reconstructed':False,'causal_word_type_established':False})
    known=configurations[configurations.basic_configuration_id.notna()]
    for identity,group in known.groupby('basic_configuration_id',sort=True):
        origins=sorted(set(group.origin_id));part=primary[primary.origin_id.isin(origins)]
        if set(origins)-ref_ids:
            raise ValueError('Configuration origin is outside supplied reference')
        if part.duplicated(['origin_id','family']).any():
            raise ValueError('More than one primary supplier for an origin/family')
        per_origin_families=part.groupby('origin_id').family.nunique()
        complete_family_rows=all(per_origin_families.get(sid,0)==len(families) for sid in origins)
        signatures=set()
        for sid in origins:
            entries=[]
            for link in part[part.origin_id.eq(sid)].sort_values('family').itertuples(index=False):
                provider=getattr(link,'provider_settlement_id',None)
                site=getattr(link,'provider_site_id',None)
                target='np:'+str(provider) if pd.notna(provider) else 'site:'+str(site) if pd.notna(site) else 'unknown'
                entries.append((link.family,target))
            signatures.add(tuple(entries))
        if len(signatures)!=1:
            raise ValueError('Configuration joins different functional destination vectors')
        providers=sorted(set(part.provider_settlement_id.dropna()))
        unresolved_provider_rows=part.provider_settlement_id.isna()
        missing_families=len(families)-part.family.nunique()
        anchor_missing=set(providers)-ref_ids
        anchors=[sid for sid in providers if sid in ref.index]
        external=[sid for sid in origins if sid not in providers]
        types={sid:record(sid).get('settlement_class',settlement_class(record(sid).get('settlement_type_2021'))) for sid in external}
        rural=[sid for sid in external if types[sid]=='rural']
        unknown_type=[sid for sid in external if types[sid] not in {'rural','urban'}]
        provider_complete=bool(anchors) and not anchor_missing and not unresolved_provider_rows.any() and not missing_families and complete_family_rows
        row={'configuration_id':identity,'origin_status_record_id':None,
            'unit_kind':'complete_basic_service_configuration' if not missing_families and complete_family_rows else 'partial_basic_service_configuration',
            'regional_origins':len(origins),'known_provider_np_count':len(providers),
            'known_provider_ids_json':json.dumps(providers,ensure_ascii=False),
            'regional_external_origins':len(external),'regional_rural_external_origins':len(rural),
            'regional_external_published_positive_origins':sum(pd.notna(record(sid)['population_2021']) and record(sid)['population_2021']>0 for sid in external),
            'regional_rural_external_published_positive_origins':sum(pd.notna(record(sid)['population_2021']) and record(sid)['population_2021']>0 for sid in rural),
            'unresolved_provider_np_identity_rows':int(unresolved_provider_rows.sum()),
            'provider_reference_missing_count':len(anchor_missing),
            'functional_configuration':'single_known_np' if len(providers)==1 and provider_complete else 'multiple_known_np' if len(providers)>1 and provider_complete else 'provider_identity_or_family_incomplete',
            'membership_reference_year':None,'settlement_roster_reference_year':2021,
            'functional_inventory_dates_mixed':True,'historical_boundaries_reconstructed':False,
            'underlying_np_boundary_equivalence_established':False,'population_scope_comparability_unverified':True,'causal_word_type_established':False}
        for mode in ('accepted','strict'):
            for start,end in ((2002,2010),(2010,2021),(2002,2021)):
                directions={}
                for scope,ids in [('centre_union',anchors),('external',external),('rural_external',rural)]:
                    eligible=[sid for sid in ids if eligible_record(record(sid),start,mode) and eligible_record(record(sid),end,mode)]
                    complete=bool(ids) and len(eligible)==len(ids) and provider_complete
                    if scope=='rural_external' and unknown_type:complete=False
                    a=sum(float(record(sid)[f'population_{start}']) for sid in eligible) if eligible else np.nan
                    b=sum(float(record(sid)[f'population_{end}']) for sid in eligible) if eligible else np.nan
                    d=direction(a,b) if complete else 'unknown'
                    annual,annual_status=annualized_change_percent(a,b,end-start,complete)
                    directions[scope]=d
                    components.append({'configuration_id':identity,'component':scope,
                        'start_year':start,'end_year':end,'evidence_mode':mode,'records':len(ids),
                        'paired_eligible_records':len(eligible),'complete_component':complete,
                        'paired_known_population_start':a,'paired_known_population_end':b,
                        'direction':d,'known_partial_sum_is_not_complete_total':not complete,
                        'annualized_population_change_percent':annual,'annualized_population_change_status':annual_status,
                        'annualization_calendar_years':end-start,'population_scope_comparability_unverified':True,
                        'underlying_np_boundary_equivalence_established':False})
                    row[f'{scope}_direction_{start}_{end}_{mode}']=d
                    row[f'{scope}_annualized_change_percent_{start}_{end}_{mode}']=annual
                    row[f'{scope}_annualized_change_status_{start}_{end}_{mode}']=annual_status
                joint=directions['centre_union']+'__'+directions['rural_external']
                row[f'joint_centres_rural_{start}_{end}_{mode}']=joint if 'unknown' not in joint else 'unknown'
        for mode in ('accepted','strict'):
            for scope in ('centre_union','external','rural_external'):
                a=row[f'{scope}_direction_2002_2010_{mode}']
                b=row[f'{scope}_direction_2010_2021_{mode}']
                row[f'{scope}_trajectory_2002_2010_2021_{mode}']=a+'__'+b if 'unknown' not in (a,b) else 'unknown'
        if not provider_complete:kind='provider_identity_or_family_incomplete'
        elif not external:kind='only_provider_np_among_regional_origins'
        elif not rural:kind='without_established_rural_external_component'
        elif row['joint_centres_rural_2002_2021_strict']!='unknown':kind='primary_reported__'+row['joint_centres_rural_2002_2021_strict']
        elif row['joint_centres_rural_2002_2021_accepted']!='unknown':kind='accepted_values__'+row['joint_centres_rural_2002_2021_accepted']
        else:kind='incomplete_population_evidence'
        row['descriptive_configuration_type']=row['functional_configuration']+'__'+kind
        classes.append(row)
    return pd.DataFrame(components),pd.DataFrame(classes)


def aggregate_unit_economic_context(links, configurations, context, workforce, agriculture):
    """Known worker subset and distinct municipality keys for overlapping units.

    Municipal values are never summed or assigned to individual settlements.
    A sum of partial-worker observations is labelled as the known subset even
    when every member has a numeric observation, because the source excludes
    part of employment. Unknown provider identity gives no fictitious centre.
    """
    workers=unique_current(workforce,'economic unit worker source').set_index('source_record_id')
    agriculture=unique_current(agriculture,'economic unit agriculture source').set_index('source_record_id')
    regional=unique_current(context,'economic unit context').set_index('source_record_id')
    primary=primary_context_links(links)
    primary=primary[primary.system_id.notna()].copy()
    units=[]
    for identity,group in candidate_context_system_links(links).groupby('system_id',sort=True):
        centres=sorted(set(group.provider_settlement_id.dropna()))
        origins=sorted(set(group.origin_id))
        units.append(('functional_system',identity,centres,origins))
    if configurations is not None:
        if 'evidence_scenario' in configurations:
            configurations=configurations[configurations.evidence_scenario.eq('all_dated_known')].copy()
        for identity,group in configurations.dropna(subset=['basic_configuration_id']).groupby('basic_configuration_id',sort=True):
            origins=sorted(set(group.origin_id))
            selected=primary[primary.origin_id.isin(origins)&primary.family.isin(['school','medical_basic','grocery'])]
            centres=sorted(set(selected.provider_settlement_id.dropna()))
            units.append(('basic_configuration',identity,centres,origins))
    rows=[]
    for kind,identity,centres,origins in units:
        external=[sid for sid in origins if sid not in centres]
        rural=[sid for sid in external if sid in regional.index and regional.loc[sid,'settlement_class']=='rural']
        for scope,members in [('centre_union',centres),('external',external),('rural_external',rural)]:
            values=[];suppressed=unknown=0;municipal=set();missing_parent=0
            for sid in members:
                value=workers.loc[sid,'partial_organisation_workforce_2025'] if sid in workers.index else np.nan
                status=workers.loc[sid,'partial_workforce_status'] if sid in workers.index else None
                if pd.notna(value):
                    if status!='observed_partial_organisation_workforce' or not np.isfinite(value) or value<0:
                        raise ValueError('Conflicting unit numeric worker observation')
                    values.append(float(value))
                elif status=='source_suppressed':suppressed+=1
                else:unknown+=1
                code=agriculture.loc[sid,'agri_municipality_code'] if sid in agriculture.index else None
                if pd.notna(code):municipal.add(str(code))
                else:missing_parent+=1
            rows.append({'unit_kind':kind,'unit_id':identity,'component':scope,
                'records':len(members),'numeric_partial_worker_records':len(values),
                'source_suppressed_worker_records':suppressed,'unknown_worker_records':unknown,
                'known_subset_partial_organisation_workers_2025':math.fsum(values) if values else np.nan,
                'all_partial_source_cells_numeric':bool(members) and len(values)==len(members),
                'complete_jobs_or_resident_employment_known':False,
                'worker_source':'ROSSTAT_NP2025_PRIMARY_BOOKS',
                'municipal_agriculture_context_codes_json':json.dumps(sorted(municipal),ensure_ascii=False),
                'distinct_agriculture_context_territories':len(municipal),
                'records_without_agriculture_parent_key':missing_parent,
                'municipal_values_allocated_or_summed':False,
                'unit_membership_is_current_model_not_historical_reconstruction':True})
    return pd.DataFrame(rows)


def aggregate_basic_centres(profiles,members,context,reference):
    """One demographic composition per known NP-centre across basic functions.

    The source union is deduplicated within centre. Overlap between centres
    remains explicit and is never turned into a national population budget.
    """
    profiles=profiles[profiles.evidence_scenario.eq('all_dated_known')].copy()
    members=members[members.evidence_scenario.eq('all_dated_known')].copy()
    if profiles.centre_id.duplicated().any() or members.duplicated(['centre_id','origin_id']).any():
        raise ValueError('Basic centre input is not one centre / one external origin within centre')
    if set(profiles.centre_id)!=set(members.centre_id):
        raise ValueError('Basic centre profiles and member unions differ')
    if members.origin_id.eq(members.centre_id).any():raise ValueError('Basic external union contains its centre')
    links=members[['centre_id','origin_id','any_ambiguous_primary']].copy()
    links['system_id']='basic-centre:'+links.centre_id.astype(str)
    links['provider_settlement_id']=links.centre_id
    links['family']='basic_service_union'
    links['is_primary']=True  # each row is one retained candidate membership
    links['evidence_scenario']='all_dated_known'
    links['context_membership_ambiguous']=links.any_ambiguous_primary.eq(True)
    components,classes=aggregate_systems(links,context,reference)
    classes=classes.drop(columns=['family']).merge(profiles,on='centre_id',how='left',validate='one_to_one')
    classes['population_may_not_be_summed_across_centres']=True
    classes['one_record_per_np_centre']=True
    classes['basic_families_deduplicated_before_population_sum']=True
    classes['centre_population_does_not_assign_hierarchical_rank']=True
    if len(classes)!=len(profiles) or not (classes.regional_external_origins==classes.external_positive_origin_count).all():
        raise ValueError('Basic centre demographic member count changed')
    components=components.drop(columns=['family']).merge(
        profiles[['centre_id','evidence_scenario','inventory_scenario']],on='centre_id',how='left',validate='many_to_one')
    ref=unique_current(reference,'basic centre demographic reference').set_index('source_record_id')
    lookup={sid:ref.loc[sid].to_dict() for sid in set(members.origin_id)|set(profiles.centre_id) if sid in ref.index}
    quality=[]
    for profile in profiles.to_dict('records'):
        centre=profile['centre_id'];part=members[members.centre_id.eq(centre)]
        external=list(part.origin_id)
        rural=[sid for sid in external if sid in lookup and settlement_class(lookup[sid].get('settlement_type_2021'))=='rural']
        row={'centre_id':centre,'system_id':'basic-centre:'+str(centre),
            'evidence_scenario':'all_dated_known','inventory_scenario':profile['inventory_scenario'],
            'centre_in_regional_roster':profile['centre_in_regional_roster'],
            'known_own_basic_function_count':profile['known_own_basic_function_count'],
            'external_unique_origin_records':len(external),'external_rural_unique_origin_records':len(rural),
            'ambiguous_candidate_origin_records':int(part.any_ambiguous_primary.eq(True).sum()),
            'unique_population_sum_between_centres_available':False,
            'underlying_np_boundaries_harmonised':False,'population_scope_comparability_unverified':True,'actual_journeys_established':False}
        for year in YEARS:
            row[f'centre_population_value_quality_{year}']=lookup.get(centre,{}).get(f'population_value_quality_{year}')
            for mode in ['accepted','strict']:
                row[f'centre_population_eligible_{year}_{mode}']=centre in lookup and eligible_record(lookup[centre],year,mode)
                row[f'external_rural_population_eligible_records_{year}_{mode}']=sum(sid in lookup and eligible_record(lookup[sid],year,mode) for sid in rural)
        row['external_rural_2010_observation_classes_json']=json.dumps(dict(Counter(
            observation_class(lookup[sid].get('population_2010'),lookup[sid].get('population_value_quality_2010'),lookup[sid].get('source_record_id_2010'))
            for sid in rural)),ensure_ascii=False,sort_keys=True)
        quality.append(row)
    return components,classes,pd.DataFrame(quality),links


def worker_potential(costs, origins, destinations, workforce, horizon=480., half_times=(10.,20.,40.,80.)):
    """Known part of the partial-worker field, not all job opportunities.

    Sparse absent values mean censored/unavailable routes, never zero cost.
    Unknown worker values are retained in the source inventory and excluded
    from the explicitly named known subset, rather than zero-imputed.
    """
    workers = unique_current(workforce, 'partial workforce')
    workers = workers[workers.ordinary_spatial_2021.eq(True)].copy()
    numeric = workers.partial_organisation_workforce_2025.notna()
    known = workers.loc[numeric].copy()
    if (known.partial_organisation_workforce_2025.lt(0).any()
            or not np.isfinite(known.partial_organisation_workforce_2025).all()
            or not known.partial_workforce_status.eq('observed_partial_organisation_workforce').all()):
        raise ValueError('Invalid or conflicting numeric partial-worker observation')
    if list(origins.row_index) != list(range(len(origins))) or list(destinations.destination_index) != list(range(len(destinations))):
        raise ValueError('Cost axes are not explicit consecutive indices')
    if costs.shape != (len(origins),len(destinations)) or not costs.has_sorted_indices:
        raise ValueError('Sparse cost shape or canonical index order differs')
    if not np.isfinite(costs.data).all() or (costs.data<0).any() or (costs.data>horizon+1e-8).any():
        raise ValueError('Invalid finite route cost or wrong censoring horizon')
    axis = destinations[['destination_index','source_record_id','ordinary_spatial_2021']].merge(
        workers[['source_record_id','partial_organisation_workforce_2025','partial_workforce_status']],
        how='left',on='source_record_id',validate='one_to_one').sort_values('destination_index')
    axis['worker_observation_known'] = axis.partial_organisation_workforce_2025.notna() & axis.ordinary_spatial_2021.eq(True)
    axis['worker_source_is_not_fns'] = True
    values = axis.partial_organisation_workforce_2025.to_numpy(dtype=float)
    known_mask = axis.worker_observation_known.to_numpy(dtype=bool)
    ordinary = axis.ordinary_spatial_2021.eq(True).to_numpy(dtype=bool)
    known_sum_on_axis = float(values[known_mask].sum())
    unmatched = known[~known.source_record_id.isin(axis.source_record_id)]
    unmatched_sum = float(unmatched.partial_organisation_workforce_2025.sum())
    known_lookup = known.set_index('source_record_id').partial_organisation_workforce_2025.to_dict()
    destination_lookup = dict(zip(axis.source_record_id, axis.destination_index))
    rows = []
    for origin in origins.itertuples(index=False):
        i = int(origin.row_index);begin,end = costs.indptr[i:i+2]
        indices = costs.indices[begin:end];time = costs.data[begin:end]
        route_known = getattr(origin,'route_row_status',None) != 'origin_endpoint_unavailable'
        # A valid origin must have its own explicit zero entry. Empty sparse
        # rows cannot masquerade as zero potential in the missing-endpoint case.
        self_col = destination_lookup.get(origin.source_record_id)
        self_pos = np.flatnonzero(indices==self_col) if self_col is not None else np.asarray([],dtype=int)
        if route_known and (len(self_pos)!=1 or abs(float(time[self_pos[0]]))>1e-9):
            raise ValueError('Valid origin has no unique explicit self-zero cost')
        mask = known_mask[indices]
        reached_values = values[indices[mask]];reached_cost = time[mask]
        outside_sum = max(0.,known_sum_on_axis-float(reached_values.sum()))
        own_known = origin.source_record_id in known_lookup
        own_value = float(known_lookup[origin.source_record_id]) if own_known else np.nan
        for family in ('exponential','gaussian'):
            for h in half_times:
                exponent = reached_cost/h if family=='exponential' else (reached_cost/h)**2
                k = np.exp2(-exponent)
                field = float(np.dot(reached_values,k)) if route_known else np.nan
                self_contribution = own_value if route_known and own_known else 0. if route_known else np.nan
                tail = outside_sum * 2**(-(horizon/h if family=='exponential' else (horizon/h)**2)) + unmatched_sum
                rows.append({'source_record_id':origin.source_record_id,'row_index':i,
                    'kernel':family,'half_time_minutes':float(h),'route_cost_horizon_minutes':horizon,
                    'known_partial_worker_potential_with_self':field,
                    'known_partial_worker_potential_external':field-self_contribution,
                    'known_subset_self_contribution':self_contribution,
                    'own_partial_worker_observation':own_value,
                    'own_worker_observation_known':own_known,
                    'known_worker_source_np_within_horizon':int(mask.sum()) if route_known else None,
                    'np_with_unknown_worker_observation_within_horizon':int((ordinary[indices]&~known_mask[indices]).sum()) if route_known else None,
                    'known_worker_source_population_is_not_used_as_capacity':True,
                    'known_worker_subset_route_tail_upper':tail if route_known else np.nan,
                    'known_worker_subset_potential_upper':field+tail if route_known else np.nan,
                    'all_workplaces_or_all_workers_potential_upper':None,
                    'complete_workplace_capacity_known':False,
                    'field_status':'known_source_subset_scenario' if route_known else 'unknown_origin_endpoint',
                    'worker_source_year':2025,'road_source_year':2021,
                    'source_scope':'Rosstat_partial_organisation_workers_not_FNS_not_complete_jobs',
                    'kernel_is_empirically_calibrated_to_work_trips':False})
    facts = {'national_current_np_numeric_worker_observations':len(known),
        'national_observed_partial_workers_sum':float(known.partial_organisation_workforce_2025.sum()),
        'known_worker_np_on_routable_destination_axis':int(known_mask.sum()),
        'known_worker_np_without_routable_destination':len(unmatched),
        'known_partial_workers_without_routable_destination':unmatched_sum,
        'overall_jobs_or_workers_field_upper_is_unknown':True,
        'municipal_values_allocated_to_np':False,'fns_legal_entities_used_as_np_capacity':False}
    return pd.DataFrame(rows),axis,unmatched,facts


def audit_worker_potential(fields, costs, origins, axis, unmatched, samples=20):
    """Independent scalar fsum check, with actual directed cost vectors."""
    lookup = fields.set_index(['row_index','kernel','half_time_minutes'])
    valid = origins[~origins.route_row_status.eq('origin_endpoint_unavailable')].row_index.to_numpy(dtype=int)
    selected = sorted(set(valid[np.linspace(0,len(valid)-1,min(samples,len(valid)),dtype=int)])) if len(valid) else []
    worker = axis.partial_organisation_workforce_2025.to_numpy(dtype=float)
    eligible = axis.worker_observation_known.to_numpy(dtype=bool)
    own = dict(zip(axis.source_record_id,axis.partial_organisation_workforce_2025))
    axis_sum = math.fsum(float(v) for v in worker[eligible])
    unmatched_sum = math.fsum(float(v) for v in unmatched.partial_organisation_workforce_2025)
    maximum=0.;checked=0
    for i in selected:
        b,e=costs.indptr[i:i+2];indices=costs.indices[b:e];times=costs.data[b:e]
        pairs=[(float(t),float(worker[j])) for j,t in zip(indices,times) if eligible[j]]
        reached_sum=math.fsum(v for _,v in pairs)
        sid=origins.iloc[i].source_record_id;self_value=own.get(sid,np.nan)
        self_value=float(self_value) if pd.notna(self_value) else 0.
        for family in fields.kernel.drop_duplicates():
            for h in fields.half_time_minutes.drop_duplicates():
                row=lookup.loc[(i,family,h)]
                value=math.fsum(v*math.pow(2.,-(t/h if family=='exponential' else (t/h)**2)) for t,v in pairs)
                horizon=float(row.route_cost_horizon_minutes)
                tail=(axis_sum-reached_sum)*math.pow(2.,-(horizon/h if family=='exponential' else (horizon/h)**2))+unmatched_sum
                for actual,expected in [(row.known_partial_worker_potential_with_self,value),
                    (row.known_partial_worker_potential_external,value-self_value),
                    (row.known_worker_subset_route_tail_upper,tail)]:
                    error=abs(float(actual)-float(expected));maximum=max(maximum,error)
                    if not math.isclose(float(actual),float(expected),rel_tol=1e-12,abs_tol=1e-7):
                        raise ValueError('Independent worker-potential mismatch')
                checked+=1
    observed=fields[fields.field_status.eq('known_source_subset_scenario')]
    for col in ['known_partial_worker_potential_with_self','known_partial_worker_potential_external','known_worker_subset_route_tail_upper']:
        if observed[col].isna().any() or (observed[col]<-1e-7).any():raise ValueError('Invalid known worker-field bound or value')
    if not np.allclose(observed.known_partial_worker_potential_with_self,
            observed.known_partial_worker_potential_external+observed.known_subset_self_contribution,
            rtol=1e-12,atol=1e-7):raise ValueError('Worker self contribution does not reconcile')
    if (observed.known_worker_subset_potential_upper+1e-7<observed.known_partial_worker_potential_with_self).any():
        raise ValueError('Worker subset upper bound is below known field')
    monotonic_groups=0
    for _,group in observed.groupby(['row_index','kernel'],sort=False):
        values=group.sort_values('half_time_minutes').known_partial_worker_potential_with_self.to_numpy()
        if (np.diff(values)<-1e-7).any():raise ValueError('Wider worker kernel reduced a nonnegative field')
        monotonic_groups+=1
    if fields.all_workplaces_or_all_workers_potential_upper.notna().any() or fields.complete_workplace_capacity_known.any():
        raise ValueError('Incomplete worker source became complete workplace capacity')
    missing=fields[fields.field_status.eq('unknown_origin_endpoint')]
    if missing.known_partial_worker_potential_with_self.notna().any():
        raise ValueError('Missing endpoints were zero-filled')
    return {'schema':'sgrt.saratov.partial_worker_field_scalar_comparison.v1',
        'origin_rows_sampled':len(selected),'scenario_rows_checked':checked,
        'maximum_absolute_difference':maximum,'missing_endpoint_scenario_rows_checked':len(missing),
        'independent_math_fsum_used':True,'violations':0,
        'all_known_scenario_rows_invariant_checked':len(observed),
        'monotone_half_time_groups_checked':monotonic_groups,
        'scope':'Arithmetic sample of known partial-worker scenario; not a validation of actual job locations or work trips.'}


def run_worker_field(field_input, workforce_path, output):
    from scipy.sparse import load_npz
    field_input,output=Path(field_input),Path(output)
    proof=verify_source('partial_workers',workforce_path)
    paths={name:field_input/name for name in ('destination_costs.npz','regional_roster.parquet','destinations.parquet')}
    digests={name:sha(path) for name,path in paths.items()}
    origins=pd.read_parquet(paths['regional_roster.parquet'])
    destinations=pd.read_parquet(paths['destinations.parquet'])
    costs=load_npz(paths['destination_costs.npz'])
    fields,axis,unmatched,facts=worker_potential(costs,origins,destinations,pd.read_parquet(workforce_path))
    audit=audit_worker_potential(fields,costs,origins,axis,unmatched)
    output.mkdir(parents=True,exist_ok=True)
    tables={'known_partial_worker_fields.parquet':fields,
        'worker_source_np_axis.parquet':axis,'known_worker_sources_without_route_axis.parquet':unmatched}
    for name,frame in tables.items():frame.to_parquet(output/name,index=False,compression='zstd')
    (output/'worker_field_independent_numeric.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    facts.update(schema='sgrt.saratov.known_partial_worker_potential.v1',
        records=len(origins),scenario_rows=len(fields),source=proof,input_sha256=digests,
        direction='origin_settlement_to_worker_source_settlement',
        travel_cost_scope='2021 static car graph plus two 15kmh endpoint connectors; self exactID cost zero',
        numerical_check=audit,tables={name:{'rows':len(frame),'sha256':sha(output/name)} for name,frame in tables.items()},
        source_np_matching_is_accepted_not_independently_validated=True,
        bounds_conditional_on_accepted_source_np_matching=True,
        main_qualification='This is a scenario conditional on accepted source-to-NP matching: the weighted concentration of the known subset of partial organisation workers, not all workplaces, resident employment or observed work journeys.')
    (output/'worker_field_summary.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
    if digests!={name:sha(path) for name,path in paths.items()}:
        raise ValueError('Regional cost axes changed during worker-potential calculation')
    return facts


def run(paths, output, links=None, system_reference=None,configurations=None,basic_families=('school','medical_basic','grocery'),basic_profiles=None,basic_members=None,primary2010_evidence=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    proofs = [verify_source(kind, path) for kind, path in paths.items()]
    inputs = {kind: pd.read_parquet(path) for kind, path in paths.items()}
    primary_evidence=pd.read_parquet(primary2010_evidence) if primary2010_evidence is not None else None
    primary_evidence_sha=sha(primary2010_evidence) if primary_evidence is not None else None
    if primary_evidence is not None:inputs['roster']=apply_primary2010_evidence(inputs['roster'],primary_evidence)
    ctx = build_np_context(inputs['roster'], inputs['agriculture'], inputs['partial_workers'], inputs['parent_crosswalk'])
    ctx=attach_worker_source_identity(ctx,inputs['worker_evidence'])
    agri, snapshots = territory_agriculture(ctx, inputs['agriculture'], inputs['agriculture_snapshots'])
    municipal, sectors = territory_workforce(ctx, inputs['municipal_workers'])
    tables = {'np_context.parquet': ctx, 'municipal_agriculture_context.parquet': agri,
        'municipal_agriculture_snapshots.parquet': snapshots,
        'municipal_agriculture_demography.parquet':agriculture_demographic_context(ctx,agri),
        'municipal_workforce_summary.parquet': municipal, 'municipal_workforce_sectors.parquet': sectors}
    if links is not None:
        if system_reference is not None:
            proofs.append(verify_source('system_reference',system_reference))
        reference = pd.read_parquet(system_reference) if system_reference else ctx
        if primary_evidence is not None and system_reference is not None:reference=apply_primary2010_evidence(reference,primary_evidence)
        link_frame=pd.read_parquet(links)
        components, classes = aggregate_systems(link_frame, ctx, reference)
        tables.update({'functional_system_demographic_components.parquet': components,
            'functional_system_dynamic_types.parquet': classes})
        tables['functional_unit_economic_context.parquet']=aggregate_unit_economic_context(
            link_frame,pd.read_parquet(configurations) if configurations else None,
            ctx,inputs['partial_workers'],inputs['agriculture'])
        if configurations is not None:
            cfg_components,cfg_classes=aggregate_configurations(pd.read_parquet(configurations),
                pd.read_parquet(links),ctx,reference,basic_families)
            tables.update({'basic_configuration_demographic_components.parquet':cfg_components,
                'basic_configuration_dynamic_types.parquet':cfg_classes})
    if (basic_profiles is None)!=(basic_members is None):raise ValueError('Basic centre profiles and memberships must be supplied together')
    if basic_profiles is not None:
        reference=pd.read_parquet(system_reference) if system_reference else ctx
        if primary_evidence is not None and system_reference is not None:reference=apply_primary2010_evidence(reference,primary_evidence)
        if not any(p['kind']=='system_reference' for p in proofs) and system_reference is not None:
            proofs.append(verify_source('system_reference',system_reference))
        bc_components,bc_types,bc_quality,bc_links=aggregate_basic_centres(
            pd.read_parquet(basic_profiles),pd.read_parquet(basic_members),ctx,reference)
        tables.update({'basic_centre_demographic_components.parquet':bc_components,
            'basic_centre_dynamic_types.parquet':bc_types,'basic_centre_quality.parquet':bc_quality,
            'basic_centre_economic_context.parquet':aggregate_unit_economic_context(
                bc_links,None,ctx,inputs['partial_workers'],inputs['agriculture']).assign(unit_kind='basic_centre_union')})
    for name, frame in tables.items():
        frame.to_parquet(output/name, index=False, compression='zstd')
    agri_comparison=tables['municipal_agriculture_demography.parquet']
    crop='crop_share_of_published_agriculture_output_2021'
    decline='rural_np_decline_share_among_known_record_comparisons'
    agri_pairs=agri_comparison[[crop,decline]].dropna()
    agri_association=float(agri_pairs.corr(method='spearman').iloc[0,1]) if len(agri_pairs)>2 and agri_pairs[crop].nunique()>1 and agri_pairs[decline].nunique()>1 else None
    summary = {'schema': 'sgrt.saratov.regional_context.v1', 'current_np_records': len(ctx),
        'settlement_class_counts': ctx.settlement_class.value_counts().to_dict(),
        'population_qualities': {str(y):ctx[f'population_observation_class_{y}'].value_counts().to_dict() for y in YEARS},
        'demographic_direction_counts': {c:ctx[c].value_counts().to_dict() for c in ctx if c.startswith('demographic_direction_') or c.startswith('demographic_trajectory_')},
        'np_partial_workers_2025_numeric': int(ctx.partial_organisation_workforce_2025.notna().sum()),
        'np_partial_workers_source': 'ROSSTAT_NP2025_PRIMARY_BOOKS_not_FNS',
        'np_partial_worker_geographic_match_precision_counts':ctx.partial_worker_geographic_match_precision.value_counts().to_dict(),
        'np_partial_worker_status_counts': ctx.partial_workforce_status.value_counts(dropna=False).to_dict(),
        'complete_np_jobs_known': int(ctx.total_settlement_jobs.notna().sum()),
        'municipal_parent_known_np_records': int(ctx.matched_2021_parent_code.notna().sum()),
        'agriculture_parent_known_np_records': int(ctx.agri_municipality_code.notna().sum()),
        'agriculture_parent_territories': len(agri),
        'municipal_agriculture_demography_comparison':{
            'municipal_contexts_with_crop_output_share_2021':int(agri_comparison[crop].notna().sum()),
            'complete_pairs':len(agri_pairs),
            'spearman_crop_output_share_vs_rural_np_decline_share':agri_association,
            'scope':'unweighted municipality contexts; rural record count fraction among eligible 2002-2021 comparisons; no causal or harmonised-boundary inference'},
        'np_with_municipal_agriculture_2021_context': {c:int(inputs['agriculture'].loc[inputs['agriculture'].source_record_id.isin(ctx.source_record_id),c].notna().sum())
            for c in inputs['agriculture'] if c.endswith('_2021_municipal_context')},
        'municipal_annual_sector_rows': len(sectors),
        'system_membership_tables_supplied': links is not None,
        'primary2010_separate_derived_variant':primary_evidence is not None,
        'primary2010_evidence_sha256':primary_evidence_sha,
        'primary2010_changes_2021_population_or_functional_membership':False,
        'primary2010_scenario_scope':'primary reported resident totals; institutional population follows census publication rules; cross-source scope and boundaries remain unverified' if primary_evidence is not None else None,
        'regional_current_records_with_primary2010_derived_evidence':int(ctx.primary2010_derived_evidence_applied.sum()) if primary_evidence is not None else 0,
        'regional_current_records_with_changed_primary2010_values':int((ctx.primary2010_derived_evidence_applied&ctx.primary2010_value_difference_from_foundation.ne(0)).sum()) if primary_evidence is not None else 0,
        'basic_centre_units':len(tables['basic_centre_dynamic_types.parquet']) if 'basic_centre_dynamic_types.parquet' in tables else None,
        'basic_centre_units_in_regional_roster':int(tables['basic_centre_dynamic_types.parquet'].centre_in_regional_roster.eq(True).sum()) if 'basic_centre_dynamic_types.parquet' in tables else None,
        'basic_centre_units_outside_regional_roster':int(tables['basic_centre_dynamic_types.parquet'].centre_in_regional_roster.eq(False).sum()) if 'basic_centre_dynamic_types.parquet' in tables else None,
        'basic_centre_dynamic_type_counts':tables['basic_centre_dynamic_types.parquet'].descriptive_dynamic_type.value_counts().to_dict() if 'basic_centre_dynamic_types.parquet' in tables else {},
        'functional_evidence_scenario': 'all_dated_known' if links is not None else None,
        'functional_system_dynamic_type_counts': tables['functional_system_dynamic_types.parquet'].descriptive_dynamic_type.value_counts().to_dict() if 'functional_system_dynamic_types.parquet' in tables else {},
        'basic_configuration_dynamic_type_counts': tables['basic_configuration_dynamic_types.parquet'].descriptive_configuration_type.value_counts().to_dict() if 'basic_configuration_dynamic_types.parquet' in tables else {},
        'basic_configuration_unit_kind_counts': tables['basic_configuration_dynamic_types.parquet'].unit_kind.value_counts().to_dict() if 'basic_configuration_dynamic_types.parquet' in tables else {},
        'sources': proofs, 'tables': {name:{'rows':len(frame),'sha256':sha(output/name)} for name,frame in tables.items()},
        'limitations': ['FNS legal-entity headcounts have no workplace-address allocation to NP.',
            'Settlement worker observations exclude small business and external parttimers and are not resident employment.',
            'Municipal agriculture and sector observations remain separate territorial contexts; no allocation to NP.',
            'Secondary confidentiality values with unverified exact scope are not automatically imputation or primary observed values.',
            'Primary reported population observations do not independently establish unchanged NP boundaries between census years.',
            'Current model membership is fixed for demographic comparison; historical service boundaries and causal Word types are not reconstructed.']}
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (output/'README.md').write_text('# Демография и хозяйственный контекст Саратовской области\n\n'
        'Все текущие переписные записи сохранены. Частичные работники организаций по НП — первичные книги Росстата за 2025 год, не ФНС и не полное число рабочих мест. '
        'Муниципальные сельскохозяйственные и отраслевые данные хранятся отдельно; в таблице НП оставлены ключи для обращения к ним. '
        'Защищённые вторичные значения 2010 года имеют собственный класс и не называются автоматически импутацией. '
        'Строгая динамика использует первично опубликованные числа с правом учёта, расширенная — принятые значения с сохранённым происхождением. '
        'Первичность числа не доказывает неизменность границ населённого пункта; направления описывают связанные опубликованные записи. '
        'Неполные компоненты не получают направление по одной доступной части суммы.\n')
    for proof in proofs:
        verify_source(proof['kind'], system_reference if proof['kind']=='system_reference' else paths[proof['kind']])
    if primary_evidence is not None and sha(primary2010_evidence)!=primary_evidence_sha:
        raise ValueError('Primary2010 evidence changed during the derived variant')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in MEMBERS:
        parser.add_argument('--'+name.replace('_','-'), type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--links', type=Path)
    parser.add_argument('--system-reference', type=Path)
    parser.add_argument('--configurations', type=Path)
    parser.add_argument('--basic-profiles',type=Path)
    parser.add_argument('--basic-members',type=Path)
    parser.add_argument('--primary2010-evidence',type=Path)
    parser.add_argument('--basic-families', nargs='+', default=['school','medical_basic','grocery'])
    parser.add_argument('--field-input', type=Path, help='Completed national-destination cost CSR and explicit axes')
    args = parser.parse_args()
    result = run({k:getattr(args,k) for k in MEMBERS}, args.output, args.links, args.system_reference,args.configurations,args.basic_families,args.basic_profiles,args.basic_members,args.primary2010_evidence)
    if args.field_input:
        run_worker_field(args.field_input,args.partial_workers,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in {'sources','demographic_direction_counts','population_qualities'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

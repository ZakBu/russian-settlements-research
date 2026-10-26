"""Hold explicit narrow or departmental scope without claiming closure."""
import re
import pandas as pd


def review_np_presence_after_site_holds(offers, sites):
    """A held OSM building cannot survive as its own aggregate local presence.

    Independent positive registry records or another admitted building retain
    the offer. Original source claims and their dated evidence remain intact.
    """
    result = offers.copy()
    admitted = sites.supply_status.isin(['observed', 'proxy'])
    for flag in ['eligible', 'route_eligible']:
        if flag in sites:
            admitted &= sites[flag].fillna(False).eq(True)
    keys = list(zip(sites.source_record_id, sites.service_code))
    live = {k for k, ok in zip(keys, admitted) if ok and pd.notna(k[0])}
    held = {k for k, ok in zip(keys, admitted) if not ok and pd.notna(k[0])}
    result['route_eligible'] = result.get('route_eligible', pd.Series(True, index=result.index)).fillna(False).eq(True)
    result['site_hold_np_presence_review_reason'] = ''
    for idx, row in result.iterrows():
        key = (row.source_record_id, row.service_code)
        if key not in held or key in live:
            continue
        independent = any(pd.notna(row.get(f)) and bool(row.get(f)) for f in
                          ['has_official_registry', 'federal_current_2026_evidence_present',
                           'saratov_historical_2021_evidence_present'])
        try:
            import json
            source_ids = json.loads(row.source_id)
        except (ValueError, TypeError):
            source_ids = []
        osm_only = bool(source_ids) and all(str(s).startswith('OSM_') for s in source_ids)
        if osm_only and not independent:
            result.at[idx, 'route_eligible'] = False
            result.at[idx, 'local_supply_eligible'] = False
            result.at[idx, 'site_hold_np_presence_review_reason'] = 'only_mapped_site_evidence_held_no_independent_positive_record'
    return result


def review_medical_need_scope(sites):
    result = sites.copy()
    names = result.get('provider_name', result.get('source_name', pd.Series('', index=result.index)))
    names = names.fillna('').str.lower().str.replace('ё', 'е')
    general_primary = result.service_code.isin(['medical_basic_primary', 'medical_physician_primary'])
    licence = result.get('function_assignment_verified_by_licence', pd.Series(False, index=result.index)).fillna(False).eq(True)
    narrow = general_primary & ~licence & names.str.contains(r'лечени[ея]\s+(?:позвоночника|спины)', regex=True)
    departmental = general_primary & names.str.contains(r'управлени[яею].{0,20}делами.{0,12}президент', regex=True)
    public_verified = result.get('general_public_access_verified', pd.Series(False, index=result.index)).fillna(False).eq(True)
    departmental &= ~public_verified
    result['route_eligible'] = result.get('route_eligible', pd.Series(True, index=result.index)).fillna(False).eq(True)
    result['need_scope_review_reason'] = ''
    result.loc[narrow, 'need_scope_review_reason'] = 'named_spine_treatment_not_evidence_of_general_primary_need'
    result.loc[departmental, 'need_scope_review_reason'] = 'departmental_general_public_access_not_established'
    result.loc[narrow | departmental, 'route_eligible'] = False
    result['scope_review_does_not_establish_closure_or_no_service'] = True
    return result

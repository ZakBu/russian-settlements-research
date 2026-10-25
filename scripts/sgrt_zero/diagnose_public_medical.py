#!/usr/bin/env python3
"""Read-only literal clinical-unit diagnostics against published medical routes.

Not a replacement classifier. Export unit/type/profile evidence and selected-NP
exposure, not a claim all exposed routes are wrong. A parent's name alone never
proves a cohort restriction. Run with --root RELEASE_ROOT --output OUTSIDE_ROOT.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_zero.medical_scope import federal_child_unit_witnesses
PRIMARY = ['medical_basic_primary', 'medical_physician_primary']
SERVICES = PRIMARY + ['medical_day_hospital', 'medical_inpatient', 'medical_specialized', 'medical_hightech_licensed', 'mapped_hospital_service_unknown_level', 'unspecified_healthcare']
WOMEN = r'\bженск[а-я]*\s+(?:консультац|амбулатор)'
def has(s, pattern):
    return s.fillna('').astype(str).str.contains(pattern, case=False, regex=True)
def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--after-health',type=Path,help='Optional fresh integrated offers for actual source-pool delta')
    parser.add_argument('--after-functions',type=Path,help='Optional fresh federal classified/evidence directory')
    parser.add_argument('--after-legacy',type=Path,help='Optional fresh legacy scope directory')
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    if out == root or root in out.parents: raise ValueError('Output must be outside immutable source root')
    out.mkdir(parents=True, exist_ok=True)
    inputs = {}
    def read(relative):
        p = root / relative
        inputs[relative] = sha(p)
        return pd.read_parquet(p)
    care = read('federal_medical/functions/care_rows_classified.parquet')
    fed = read('health/public_scope_corrected/federal_service_evidence_with_identity.parquet')
    phys = read('health/public_scope_corrected/physical_sites.parquet')
    legacy = read('health/legacy_primary_child_scope_corrected/legacy_source_evidence_with_scope.parquet')
    f = fed[fed.service_code.isin(PRIMARY) & fed.np_identity_accepted].copy()
    c = f.merge(care.reset_index(names='source_row_index'), on='source_row_index', suffixes=('_evidence', ''), validate='many_to_one')
    c['diagnostic_class'] = ''
    women = has(c.VID_SPMO, r'^Женские консультации$') | has(c.NAM_SPMO, WOMEN)
    c.loc[women, 'diagnostic_class'] = 'literal_womens_unit_not_universal_all_population'
    c.loc[has(c.NAM_SPMO, r'кабинет\s+медико.психологическ'), 'diagnostic_class'] = 'literal_psychological_cabinet_not_general_primary'
    l = legacy[legacy.current_source_eligible & legacy.service_code.isin(PRIMARY)].copy()
    l['diagnostic_class'] = ''
    l.loc[has(l.subdivision_name, WOMEN), 'diagnostic_class'] = 'literal_womens_unit_not_universal_all_population'
    p = phys[phys.service_code.isin(PRIMARY) & phys.supply_status.eq('proxy')].copy()
    p['diagnostic_class'] = ''
    psychiatric = has(p.source_healthcare_speciality, r'(?:^|;)\s*psychiatry\s*(?:;|$)') & ~has(p.source_healthcare_speciality, r'(?:^|;)\s*(?:general|family|internal)\s*(?:;|$)')
    psychiatric |= has(p.provider_name, r'(?:психотерапевтическ|психоневр[а-я]*ическ)[а-я]*\s+поликлиник')
    p.loc[psychiatric, 'diagnostic_class'] = 'literal_psychiatric_function_not_general_primary'
    p.loc[has(p.provider_name, WOMEN), 'diagnostic_class'] = 'literal_womens_unit_not_universal_all_population'
    witnesses=federal_child_unit_witnesses(l,care)
    witnesses.to_parquet(out/'legacy_exact_federal_child_type_witnesses.parquet',index=False)
    l.loc[l.object_id.isin(set(witnesses.object_id)), 'diagnostic_class']='same_unit_and_address_explicit_federal_child_type'
    physical_review=p[p.diagnostic_class.eq('') & has(p.provider_name,r'псих|санатор|интернат|ветеран')].copy()
    physical_review.to_parquet(out/'physical_parent_or_specialist_word_review.parquet',index=False)
    badf, badl, badp = [d[d.diagnostic_class.ne('')].copy() for d in [c,l,p]]
    for label, d in [('federal_literal_unit_counterexamples',badf),('legacy_literal_unit_counterexamples',badl),('physical_literal_unit_counterexamples',badp)]:
        d.to_parquet(out / (label+'.parquet'), index=False)
    child_review = l[has(l.organization_name, r'\bдетск') & has(l.care_profile_literal, r'педиатр|детск') & ~has(l.care_profile_literal, r'(?<![а-я])терапии\b|общей\s+(?:врачебной\s+)?практике')]
    child_review.to_parquet(out/'legacy_child_parent_profile_review.parquet',index=False)
    parent_review = c[has(c.organization_name,r'психиатр|психоневр|нарколог|санатор|интернат|противотуберк')]
    parent_review.to_parquet(out/'federal_specialist_parent_general_unit_review.parquet',index=False)
    keys=['source_record_id','service_code']
    def keyset(d): return set(map(tuple,d[keys].dropna().drop_duplicates().to_numpy()))
    badkeys=keyset(pd.concat([badf[keys],badl[keys],badp[keys]],ignore_index=True))
    goodkeys=set().union(*[keyset(d[d.diagnostic_class.eq('')]) for d in [c,l,p]])
    exclusive=badkeys-goodkeys
    routes={}; exposures=[]
    for service in SERVICES:
        t=read(f'routes/nearest/{service}.parquet')
        relevant={n for n,s in badkeys if s==service}; only={n for n,s in exclusive if s==service}
        direct=t.selected_provider_id.isin(set(badp.provider_id))
        contaminated=t.selected_provider_source_record_id.isin(relevant)
        exclusive_selected=t.selected_provider_source_record_id.isin(only)
        exposed=direct|contaminated
        q=t.loc[exposed,['origin_id','name','region','population','service_code','selected_provider_id','selected_provider_source_record_id','cost_minutes','known_local_supply']].copy()
        q['direct_bad_physical_selected']=direct[exposed]
        q['np_has_other_nondiagnostic_support']=~exclusive_selected[exposed]
        exposures.append(q)
        physical_hits={name:int(t[name].isin(set(badp.provider_id)).sum()) for name in ['provider_site_id','selected_provider_id','provider_id','unconstrained_nearest_site_provider_id','unconstrained_nearest_provider_id'] if name in t}
        routes[service]={'exact_bad_physical_field_hits':physical_hits,'origins_total':len(t),'direct_bad_physical_selected':int(direct.sum()),'selected_np_contains_diagnostic_evidence_upper_bound':int(contaminated.sum()),'selected_np_without_other_three_family_support':int(exclusive_selected.sum()),'local_zero_assumption_exposed':int((exposed&t.known_local_supply).sum()),'exposed_population':float(t.loc[exposed,'population'].fillna(0).sum())}
    pd.concat(exposures,ignore_index=True).to_parquet(out/'selected_origin_exposure_upper_bound.parquet',index=False)
    summary={'scope':'Read-only published source diagnostic, no altered model or reroutes','source_sha256':inputs,'counterexamples':{'federal_evidence_rows':len(badf),'federal_units':int(badf.UIDSPMO.nunique()),'legacy_evidence_rows':len(badl),'legacy_units':int(badl.object_id.nunique()),'physical_service_rows':len(badp),'physical_objects':int(badp.source_object_id.nunique()),'np_service_keys_containing_diagnostic_evidence':len(badkeys),'np_service_keys_without_other_three_family_support':len(exclusive)},'child_parent_profile_review_rows_not_automatic_errors':len(child_review),'specialist_parent_review_rows_not_automatic_errors':len(parent_review),'np_support_context':[{'source_record_id':n,'service_code':s,'other_nondiagnostic_support_exists':(n,s) in goodkeys} for n,s in sorted(badkeys)],'routes':routes,'limitations':['Selected NP containing suspect evidence is an upper exposure bound; another valid institution can preserve function.','Other nondiagnostic support is not independently verified universal availability.','No alternative routes or revised hierarchy calculated.','Parent-only specialist/child names exported for review, not automatic exclusions.','Historical Saratov evidence not part of three-family support test; inspect exclusive keys before removal.','Population totals overlap across services; do not sum.']}
    if args.after_health:
        before_np=read('health/public_scope_corrected/np_supply.parquet')
        after_np=pd.read_parquet(args.after_health/'np_supply.parquet')
        after_phys=pd.read_parquet(args.after_health/'physical_sites.parquet')
        active=lambda d: d[d.supply_status.isin(['observed','proxy'])]
        np_before,np_after=keyset(active(before_np)),keyset(active(after_np))
        phys_before=set(active(phys).provider_id);phys_after=set(active(after_phys).provider_id)
        summary['actual_offer_delta']={
            'after_np_sha256':sha(args.after_health/'np_supply.parquet'),
            'after_physical_sha256':sha(args.after_health/'physical_sites.parquet'),
            'np_rows_before':len(before_np),'np_rows_after':len(after_np),
            'np_service_keys_removed':[list(k) for k in sorted(np_before-np_after)],
            'np_service_keys_added':[list(k) for k in sorted(np_after-np_before)],
            'physical_active_role_ids_removed':sorted(phys_before-phys_after),
            'physical_active_role_ids_added':sorted(phys_after-phys_before),
            'physical_source_objects_lost':sorted(set(phys.source_object_id)-set(after_phys.source_object_id))}
        historic='historical_evidence_with_time_status.parquet'
        if (args.after_health/historic).exists():
            before_hist=read('health/public_scope_corrected/'+historic)
            after_hist=pd.read_parquet(args.after_health/historic)
            summary['actual_offer_delta']['historical_evidence_and_time_flags_unchanged']=before_hist.equals(after_hist)
    if args.after_functions:
        fresh_care=pd.read_parquet(args.after_functions/'care_rows_classified.parquet')
        source=read('federal_medical/normalized/care_site_profiles_current.parquet')
        # Original columns only: derived classification fields are expected to change.
        raw_equal=source.reset_index(drop=True).equals(fresh_care[source.columns].reset_index(drop=True))
        before_ev=read('federal_medical/functions/service_evidence_by_care_address.parquet')
        fresh_ev=pd.read_parquet(args.after_functions/'service_evidence_by_care_address.parquet')
        evkey=lambda d:set(map(tuple,d[['source_row_index','service_code']].to_numpy()))
        removed=evkey(before_ev)-evkey(fresh_ev);added=evkey(fresh_ev)-evkey(before_ev)
        summary['actual_federal_delta']={'all_original_normalized_columns_and_rows_unchanged':raw_equal,
            'raw_rows_before':len(source),'raw_rows_after':len(fresh_care),
            'removed_evidence_by_service':{s:sum(k[1]==s for k in removed) for s in SERVICES},
            'new_evidence_by_service':{s:sum(k[1]==s for k in added) for s in SERVICES},
            'after_classified_sha256':sha(args.after_functions/'care_rows_classified.parquet')}
    if args.after_legacy:
        fresh_l=pd.read_parquet(args.after_legacy/'legacy_source_evidence_with_scope.parquet')
        source=read('inputs/licensed_sites.parquet')
        raw_copy=args.after_legacy/'legacy_sites_all_rows.parquet'
        evkey=lambda d:set(map(tuple,d[['object_id','service_code']].to_numpy()))
        oldev=evkey(legacy[legacy.current_source_eligible]);newev=evkey(fresh_l[fresh_l.current_source_eligible])
        summary['actual_legacy_delta']={'raw_source_byte_identical':sha(root/'inputs/licensed_sites.parquet')==sha(raw_copy),
            'newly_held_object_service_pairs':len(oldev-newev),'newly_admitted_object_service_pairs':len(newev-oldev)}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['source_sha256','np_support_context']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()

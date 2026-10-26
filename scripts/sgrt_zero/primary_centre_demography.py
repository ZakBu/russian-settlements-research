#!/usr/bin/env python3
"""Descriptive demography of fixed primary memberships, not causal Word types.

Reuse the published component eligibility rules and exact sign classification.
Historical counts describe the fixed current composition, not historical trips.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
try:
    from .centre_demographic_readout import build_readout, OBSERVED_QUALITIES, analyse_component, URBAN_TYPES
except ImportError:
    from centre_demographic_readout import build_readout, OBSERVED_QUALITIES, analyse_component, URBAN_TYPES

MODES = ['strict_direct_observed', 'accepted_values']


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def prepare_primary(units, primary, reference):
    centres = units.loc[units.is_registered_external_serving_centre.fillna(False)].copy()
    if not centres.star_id.is_unique or not centres.centre_settlement_id.is_unique:
        raise ValueError('Registered centre identities must be unique')
    if not primary.origin_id.is_unique:
        raise ValueError('Each primary origin must occur once')
    members = primary.loc[primary.unit_id.isin(centres.unit_id), ['unit_id','origin_id','is_core']].copy()
    members = members.merge(centres[['unit_id','star_id','centre_settlement_id']], on='unit_id', validate='many_to_one')
    members['member_role'] = members.is_core.map({True:'centre',False:'external_primary_member'})
    if members.member_role.isna().any():
        raise ValueError('Missing core status')
    core = members[members.is_core]
    if len(core) != len(centres) or not core.origin_id.eq(core.centre_settlement_id).all():
        raise ValueError('Every registered centre must be its own unique primary core')
    return centres, members


def describe(classes, components):
    classes = classes.copy()
    for start in [2002,2010]:
        rural = components[components.scope.eq('rural_external') & components.start_year.eq(start) & components.end_year.eq(2021)]
        records = rural.set_index(['star_id','evidence_mode']).records
        counts = pd.MultiIndex.from_frame(classes[['star_id','evidence_mode']]).map(records)
        unknown_type = pd.MultiIndex.from_frame(classes[['star_id','evidence_mode']]).map(
            rural.set_index(['star_id','evidence_mode']).unknown_reasons_json.str.contains('external_settlement_type_unknown'))
        no_rural = (counts == 0) & ~unknown_type
        # Empty rural component stays distinct from unobserved rural dynamics.
        direction = classes[f'rural_external_direction_{start}_2021'].where(~no_rural,'no_external_rural')
        classes[f'external_primary_rural_state_{start}_2021'] = direction.to_numpy()
        classes[f'descriptive_primary_type_{start}_2021'] = (
            classes[f'centre_direction_{start}_2021'] + '__' + classes[f'external_primary_rural_state_{start}_2021'])
    return classes


def add_early_interval(centres, members, reference, components, classes):
    ref=reference[reference.source_record_id.notna()].set_index('source_record_id').to_dict('index')
    grouped=members.groupby('star_id',sort=False).origin_id.agg(list).to_dict()
    rows=[]; additions=[]
    for mode in MODES:
        for centre in centres.itertuples(index=False):
            cid=centre.centre_settlement_id
            external=[ref[s] for s in grouped[centre.star_id] if s!=cid]
            unknown_types=sum(pd.isna(r.get('settlement_type_2021')) for r in external)
            rural=[r for r in external if pd.notna(r.get('settlement_type_2021')) and r['settlement_type_2021'] not in URBAN_TYPES]
            results={}
            for scope,records in [('centre',[ref[cid]]),('external',external),('rural_external',rural)]:
                result=analyse_component(records,2002,end=2010,unknown_type_count=unknown_types if scope=='rural_external' else 0,evidence_mode=mode)
                rows.append(dict(star_id=centre.star_id,centre_settlement_id=cid,scope=scope,start_year=2002,end_year=2010,evidence_mode=mode,**result))
                results[scope]=result
            rural_state='no_external_rural' if not rural and not unknown_types else results['rural_external']['direction']
            a=results['centre'];b=results['rural_external']
            additions.append(dict(star_id=centre.star_id,evidence_mode=mode,
                centre_direction_2002_2010=a['direction'],rural_external_direction_2002_2010=b['direction'],
                external_primary_rural_state_2002_2010=rural_state,
                descriptive_primary_type_2002_2010=a['direction']+'__'+rural_state,
                joint_centre_rural_external_2002_2010=a['direction']+'__'+b['direction'] if a['complete'] and b['complete'] else 'unknown'))
    classes=classes.merge(pd.DataFrame(additions),on=['star_id','evidence_mode'],validate='one_to_one')
    for scope in ['centre','rural_external']:
        classes[scope+'_two_interval_trajectory_2002_2010_2021']=(classes[scope+'_direction_2002_2010']+'__'+classes[scope+'_direction_2010_2021'])
    return pd.concat([components,pd.DataFrame(rows)],ignore_index=True),classes


def compute(units, primary, reference):
    centres, members = prepare_primary(units,primary,reference)
    outputs = [build_readout(centres,members,reference,mode) for mode in MODES]
    components = pd.concat([p[0] for p in outputs],ignore_index=True)
    classes = describe(pd.concat([p[1] for p in outputs],ignore_index=True),components)
    components,classes=add_early_interval(centres,members,reference,components,classes)
    counts = {mode:{str(y):g[f'descriptive_primary_type_{y}_2021'].value_counts().sort_index().to_dict()
        for y in [2002,2010]} for mode,g in classes.groupby('evidence_mode')}
    sensitivity = {}
    for year in [2002,2010]:
        col=f'descriptive_primary_type_{year}_2021'
        wide=classes.pivot(index='star_id',columns='evidence_mode',values=col)
        joint=f'joint_centre_rural_external_{year}_2021'
        jointwide=classes.pivot(index='star_id',columns='evidence_mode',values=joint)
        strict=jointwide[MODES[0]];accepted=jointwide[MODES[1]]
        knownboth=strict.ne('unknown') & accepted.ne('unknown')
        sensitivity[str(year)]={'joint_known_both':int(knownboth.sum()),
            'joint_direction_flips_among_known_both':int((knownboth & strict.ne(accepted)).sum()),
            'joint_strict_unknown_accepted_known':int((strict.eq('unknown') & accepted.ne('unknown')).sum()),
            'joint_unknown_both':int((strict.eq('unknown') & accepted.eq('unknown')).sum()),
            'different_strict_vs_accepted':int(wide[MODES[0]].ne(wide[MODES[1]]).sum()),
            'unchanged_strict_vs_accepted':int(wide[MODES[0]].eq(wide[MODES[1]]).sum()),
            'is_raw_vs_effective_comparison':False}
    canonical_components=components[components.evidence_mode.eq('accepted_values') & components.start_year.eq(2002) & components.end_year.eq(2021)]
    coverage={scope:{'centres':len(part),'with_zero_known_members':int(part.records.eq(0).sum()),
        'complete_accepted_component_2002_2021':int(part.complete.sum())}
        for scope,part in canonical_components.groupby('scope')}
    summary={'component_coverage':coverage,'primary_external_member_records':int((~members.is_core).sum()),
        'primary_self_only_centres_are_not_evidence_of_absent_real_external_services':True,
        'registered_centres':len(centres),'reference_origin_records':len(primary),
        'primary_member_pairs_for_registered_centres':len(members),'unique_selected_origins':members.origin_id.nunique(),
        'selected_origins_repeated_between_primary_centres':int(members.origin_id.duplicated().sum()),
        'missing_centre_classes':len(centres)*len(MODES)-len(classes),
        'untyped_centre_records':int(classes.descriptive_primary_type_2002_2021.isna().sum()),
        'descriptive_type_counts':counts,
        'two_interval_direction_counts':{mode:{scope:part[scope+'_two_interval_trajectory_2002_2010_2021'].value_counts().to_dict() for scope in ['centre','rural_external']} for mode,part in classes.groupby('evidence_mode')},
        'descriptive_type_counts_2002_2010':{mode:part.descriptive_primary_type_2002_2010.value_counts().to_dict() for mode,part in classes.groupby('evidence_mode')},'evidence_mode_sensitivity':sensitivity,
        'direction_rule':'exact_sign_of_complete_comparable_end_minus_start_reused_from_published_method',
        'fixed_composition_year':2021,'historical_membership_or_trip_flows_established':False,
        'raw_effective_population_pair_available':False,'quality_overlay_provenance_available':True,
        'accepted_values_are_not_all_primary_observed':True,'causal_word_types_assigned':False,
        'strict_primary_quality_allowlist':sorted(OBSERVED_QUALITIES)}
    return centres,members,components,classes,summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['units','memberships','reference','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--old-star-classes',type=Path)
    args=p.parse_args()
    inputs={'units':args.units,'memberships':args.memberships,'reference':args.reference}
    fingerprints={k:sha(v) for k,v in inputs.items()}
    frames={k:pd.read_parquet(v) for k,v in inputs.items()}
    centres,members,components,classes,summary=compute(frames['units'],frames['memberships'],frames['reference'])
    args.output.mkdir(parents=True,exist_ok=False)
    members.to_parquet(args.output/'primary_centre_memberships.parquet',index=False,compression='zstd')
    components.to_parquet(args.output/'primary_centre_demographic_components.parquet',index=False,compression='zstd')
    classes.to_parquet(args.output/'primary_centre_demographic_classes.parquet',index=False,compression='zstd')
    ref=frames['reference']; cols=['source_record_id','name','settlement_type_2021','budget_population_credit'] + [f'{f}_{y}' for y in [2002,2010,2021] for f in ['population','credit','source_record_id','population_value_quality','population_overlay_applied']]
    # One evidence row per selected origin: no repeated history across modes.
    evidence=ref.loc[ref.source_record_id.isin(members.origin_id),cols]
    evidence.to_parquet(args.output/'primary_population_evidence.parquet',index=False,compression='zstd')
    if args.old_star_classes:
        old=pd.read_parquet(args.old_star_classes)
        comparisons=[]
        for mode in MODES:
            for year in [2002,2010]:
                col=f'joint_centre_rural_external_{year}_2021'
                joined=old[old.evidence_mode.eq(mode)][['star_id',col]].merge(
                    classes[classes.evidence_mode.eq(mode)][['star_id',col]],on='star_id',suffixes=('_old','_primary'),validate='one_to_one')
                if len(joined)!=len(centres):raise ValueError('Old star comparison must cover every registered centre')
                comparisons.append({'evidence_mode':mode,'start_year':year,'centres':len(joined),
                    'changed_joint_class':int(joined[col+'_old'].ne(joined[col+'_primary']).sum()),
                    'known_joint_old_star':int(joined[col+'_old'].ne('unknown').sum()),
                    'known_joint_primary':int(joined[col+'_primary'].ne('unknown').sum()),
                    'comparison_is_membership_change_not_demographic_sensitivity':True})
        summary['old_overlapping_star_vs_primary']=comparisons
        summary['old_star_classes_sha256']=sha(args.old_star_classes)
    summary['input_sha256']=fingerprints
    summary['code_sha256']={'primary':sha(Path(__file__)),'published_component_method':sha(Path(__file__).with_name('centre_demographic_readout.py'))}
    summary['population_quality_2010_counts']=evidence.population_value_quality_2010.fillna('unknown').value_counts().to_dict()
    summary['population_overlay_2010_applied_count']=int(evidence.population_overlay_applied_2010.eq(True).sum())
    if any(sha(path)!=fingerprints[k] for k,path in inputs.items()):raise ValueError('An immutable input changed')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()

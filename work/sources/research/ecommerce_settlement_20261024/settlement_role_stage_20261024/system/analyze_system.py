"""Settlement-system outcomes separate from catalogue geography; descriptive only.
Run: PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 analyze_system.py
"""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib,json
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parent.parent
HIST=BASE/'history_stage_20261024'
KEY='source_record_id_2021'
paths=[BASE/'national/national_target_source2021.parquet',
       HIST/'centres/settlement_admin_context_main2021.parquet',
       HIST/'wb_history_settlement_counts.parquet',
       BASE/'national/urban_population_panel_main_wide.parquet']
d=pd.read_parquet(paths[0]).set_index(KEY)
a=pd.read_parquet(paths[1]).set_index(KEY)
counts=pd.read_parquet(paths[2])
urban=pd.read_parquet(paths[3]).set_index(KEY)
assert d.index.is_unique and a.index.is_unique and urban.index.is_unique
assert set(d.index)==set(a.index) and len(d)==144151
assert not counts.duplicated([KEY,'archive_date','radius_km']).any()
centres=a.index[a.admin_centre_positive_20200110].tolist()
assert len(centres)==1953
parent='administrative_centre_source_record_id_2021_20200110'
known=a.context_status_20200110.eq('accepted_administrative_parent_and_centre')
groups={c:set(g.index) for c,g in a.loc[known].groupby(parent)}
for c in centres:
    groups.setdefault(c,set()).add(c)
membership=Counter(i for c in centres for i in groups[c])
overlap={i:n for i,n in membership.items() if n>1}
strict=d.population_value_quality_2002.eq('direct_published_census_value') & \
       d.population_value_quality_2021.eq('direct_published_census_value') & \
       d.population_2002.notna() & d.population_2021.notna()


def sizeband(pop):
    if pd.isna(pop): return 'unknown'
    if pop<1000: return 'under1000'
    if pop<5000: return '1000_4999'
    if pop<50000: return '5000_49999'
    if pop<100000: return '50000_99999'
    return '100000plus'


def demographic_type(pop_change,share_change,supported):
    if not supported: return 'insufficient_common_roster'
    if share_change>=1:
        return 'growing_centre_population_concentration' if pop_change>=0 else 'shrinking_centre_population_concentration'
    if share_change<=-1:
        return 'growing_centre_relative_deconcentration' if pop_change>=0 else 'shrinking_centre_relative_weight_loss'
    return 'centre_population_growth_stable_share' if pop_change>=0 else 'centre_population_decline_stable_share'


records=[]
for c in centres:
    r=d.loc[c]
    member_ids=sorted(groups[c])
    g=d.loc[member_ids]
    common=g.loc[strict.loc[g.index]]
    other=common.drop(index=c,errors='ignore')
    currenttotal=g.population_2021.sum()
    coverage=(common.population_2021.sum()/currenttotal) if currenttotal>0 else np.nan
    supported=bool(strict.loc[c] and len(other)>0 and common.population_2002.sum()>0 and
                   common.population_2021.sum()>0 and coverage>=.90 and r.population_2002>0)
    share02=100*r.population_2002/common.population_2002.sum() if supported else np.nan
    share21=100*r.population_2021/common.population_2021.sum() if supported else np.nan
    change=100*(r.population_2021/r.population_2002-1) if strict.loc[c] and r.population_2002>0 else np.nan
    row={KEY:c,'name_2021':r.name_2021,'region_2021':r.region_2021,'type_2021':r.type_2021,
         'population_2002':r.population_2002,'population_2021':r.population_2021,
         'size2002':sizeband(r.population_2002),'size2021':sizeband(r.population_2021),
         'medium_primary2002':bool(5000<=r.population_2002<50000) if pd.notna(r.population_2002) else False,
         'medium_alternative2021':bool(5000<=r.population_2021<50000),
         'admin_centres_municipalities_n2020':a.loc[c,'admin_centre_municipalities_n_20200110'],
         'context_members_n':len(g),'context_other_members_n':len(g)-1,
         'context_other_inhabited2021_n':int(g.drop(index=c).population_2021.gt(0).sum()),
         'common_roster_n':len(common),'common_roster_other_n':len(other),
         'common_roster_population2021_coverage':coverage,
         'demographic_comparison_supported':supported,
         'centre_change2002_2021_pct':change,
         'centre_population_share2002_common_roster_pct':share02,
         'centre_population_share2021_common_roster_pct':share21,
         'centre_population_share_change_pp':share21-share02,
         'context_change2002_2021_pct':100*(common.population_2021.sum()/common.population_2002.sum()-1)
             if supported else np.nan,
         'other_members_change2002_2021_pct':100*(other.population_2021.sum()/other.population_2002.sum()-1)
             if supported and other.population_2002.sum()>0 else np.nan,
         'demographic_type':demographic_type(change,share21-share02,supported),
         'boundaries_independently_verified':False}
    u=urban.loc[c] if c in urban.index else None
    uvalid=u is not None and bool(u.complete_2023_2025) and u.population_2023>0
    row.update({'urban_2023_2025_observed':uvalid,
        'population_2023':u.population_2023 if uvalid else np.nan,
        'population_2025':u.population_2025 if uvalid else np.nan,
        'centre_change2023_2025_pct':100*(u.population_2025/u.population_2023-1) if uvalid else np.nan,
        'recent_demographic_type':'decline' if uvalid and u.population_2025<u.population_2023 else
                                  'growth_or_equal' if uvalid else 'unobserved'})
    records.append(row)
systems=pd.DataFrame(records)
systems.to_csv(OUT/'centre_system_demography.csv',index=False)

# Evaluate the same context across every observed catalogue date and linkage radius.
profiles=[]
for radius in [1,5,10]:
    x=counts.loc[counts.radius_km.eq(radius)]
    for date,source in x.groupby('archive_date'):
        source=source.set_index(KEY)
        assert source.index.is_unique
        for profile in ['allcatalog_objects','fitting_positive_objects']:
            values=source[profile].reindex(d.index,fill_value=0)
            for c in centres:
                ids=sorted(groups[c]);other=[i for i in ids if i!=c]
                central=int(values.loc[c]);periphery=values.reindex(other).fillna(0)
                total=central+periphery.sum()
                profiles.append({KEY:c,'archive_date':date,'radius_km':radius,'profile':profile,
                    'centre_objects':central,'other_member_objects':int(periphery.sum()),
                    'other_positive_members_n':int(periphery.gt(0).sum()),
                    'centre_object_share_pct':100*central/total if total>0 else np.nan,
                    'catalogue_absence_is_confirmed_physical_absence':False})
foot=pd.DataFrame(profiles)
foot.to_parquet(OUT/'centre_context_catalogue_profiles.parquet',index=False)
comparisons=[]
for first,last,label in [('2022-11-18','2023-01-01','same_url_v2_short_interval'),
                         ('2022-09-29','2024-03-11','earlier_to_later_observed_schema_not_harmonized'),
                         ('2024-03-11','2026-10-21','cross_schema_not_harmonized')]:
    for radius in [1,5,10]:
        for profile in ['allcatalog_objects','fitting_positive_objects']:
            sub=foot.loc[foot.radius_km.eq(radius)&foot.profile.eq(profile)]
            before=sub.loc[sub.archive_date.eq(first)].set_index(KEY)
            after=sub.loc[sub.archive_date.eq(last)].set_index(KEY)
            for c in centres:
                b=before.loc[c];e=after.loc[c]
                expanded=e.other_positive_members_n>b.other_positive_members_n
                retained=b.centre_objects>0 and e.centre_objects>0
                changedshare=e.centre_object_share_pct-b.centre_object_share_pct
                typ=('centre_retained_and_other_footprint_expands' if retained and expanded else
                     'centre_retained_without_other_footprint_expansion' if retained else
                     'earlier_centre_only_catalogue_record' if b.centre_objects>0 and e.centre_objects==0 else
                     'later_centre_record_not_earlier' if b.centre_objects==0 and e.centre_objects>0 else
                     'no_centre_record_both_dates')
                comparisons.append({KEY:c,'first':first,'last':last,'comparison':label,
                    'radius_km':radius,'profile':profile,
                    'other_positive_member_change_n':int(e.other_positive_members_n-b.other_positive_members_n),
                    'centre_objects_before':int(b.centre_objects),'centre_objects_after':int(e.centre_objects),
                    'centre_object_share_change_pp':changedshare,'catalogue_type':typ,
                    'genuine_new_physical_openings_estimated':False})
changes=pd.DataFrame(comparisons).merge(systems,on=KEY,validate='many_to_one')
changes.to_csv(OUT/'centre_context_typology.csv',index=False)

summary=[]
for scheme,flag in [('medium2002',systems.medium_primary2002),('medium2021',systems.medium_alternative2021),
                    ('all_centres2020',pd.Series(True,index=systems.index))]:
    g=systems.loc[flag]
    valid=g.loc[g.demographic_comparison_supported]
    summary.append({'selection':scheme,'centres_n':len(g),'supported_demographic_n':len(valid),
        'recent_observed_n':int(g.urban_2023_2025_observed.sum()),
        'recent_declining_n':int((g.recent_demographic_type=='decline').sum()),
        'median_recent_change_pct':float(g.centre_change2023_2025_pct.median()),
        'demographic_types':valid.demographic_type.value_counts().to_dict(),
        'median_historical_centre_change_pct':float(valid.centre_change2002_2021_pct.median()),
        'median_historical_centre_share_change_pp':float(valid.centre_population_share_change_pp.median())})
joint=changes.loc[changes.medium_primary2002 & changes.demographic_comparison_supported &
                  changes.radius_km.eq(5) & changes.profile.eq('allcatalog_objects')]
joint.groupby(['comparison','demographic_type','catalogue_type']).size().rename('centres_n').reset_index().to_csv(
    OUT/'medium_centre_joint_typology.csv',index=False)
individual=systems.loc[systems.medium_primary2002 & systems.demographic_comparison_supported].copy()
individual['absolute_share_shift_pp']=individual.centre_population_share_change_pp.abs()
individual.sort_values(['absolute_share_shift_pp',KEY],ascending=[False,True]).head(40).to_csv(
    OUT/'individual_centres_for_review.csv',index=False)

# Human-readable, auditable service-source inventory: actual local files, not README promises.
legacy=BASE.parent/'sgrt_word_completion_20261021/model_inputs_cycle05/relinked_v4'
inventory=[]
for domain in ['medical','education','commerce']:
    path=legacy/domain/'settlement_features_full_axis.parquet'
    t=pd.read_parquet(path)
    info={'domain':domain,'path':str(path),'rows':len(t),'unique_legacy_ids':bool(t.id.is_unique),
          'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
          'grain':'legacy settlement axis; not object register',
          'snapshot_date_assertion':'2021-01-01','source_timestamp_receipt_locally_found':False,
          'current2026_comparable_local_layer_found':False,
          'not_physical_opening_closure_series':True,
          'columns':list(t.columns)}
    baseline=[c for c in t.columns if c.endswith('_baseline_count') or
              c in ['medical_osm_baseline_healthcare_sites_count','medical_osm_baseline_central_district_hospital_name_assertion_count']]
    info['baseline_positive_settlements']={c:int(t[c].gt(0).sum()) for c in baseline}
    scope=[c for c in t.columns if 'scope' in c or 'snapshot_date' in c or 'version' in c]
    info['source_claim_fields']={c:t[c].fillna('NULL').astype(str).value_counts().to_dict() for c in scope}
    inventory.append(info)
(OUT/'service_source_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
audit={'status':'PASS','inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
    'main_axis_n':len(d),'admin_centres2020_n':len(centres),
    'unique_context_member_ids_n':len(membership),'overlapping_member_ids_n':len(overlap),
    'overlapping_member_ids':overlap,'context_roster_membership_definition':'union by unique centre ID of strict main-axis administrative members plus centre once',
    'medium_primary_definition':'administrative centre in official2020 register, population2002 between5000 inclusive and50000 exclusive; threshold is an explicit analytical convention, not a measured functional rank',
    'history_population_definition':'same2020 administrative-context roster projected on accepted inter-census identities; direct2002 and2021 observations only; >=90% of represented2021 population covered; not historical municipal totals',
    'no_causal_interpretation':True,'no_actual_catchments':True,
    'periods_not_aligned_for_effect_estimation':True,'summaries':summary,
    'catalogue_typology_medium2002_main5km':joint.groupby(['comparison','catalogue_type']).size().to_dict() and
       joint.groupby(['comparison','catalogue_type']).size().rename('centres_n').reset_index().to_dict('records')}
(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=lambda x:int(x) if isinstance(x,np.integer) else float(x))+'\n')
assert not overlap
assert foot[[KEY,'archive_date','radius_km','profile']].duplicated().sum()==0
assert changes[[KEY,'comparison','radius_km','profile']].duplicated().sum()==0
print(json.dumps(summary,ensure_ascii=False,indent=2))

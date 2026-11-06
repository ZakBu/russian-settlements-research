"""Fixed documented school frameworks and their direct functional organisation.

The document fixes membership. Functional choices describe internal roles and
external dependencies; they never extend membership transitively. A framework
with only its core remains a documented local site, not an external system.
Population maxima are attached as scenario diagnostics, never admission rules.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

BASIC=('school','medical_basic','grocery')
SCENARIO='all_dated_known'


def stable_id(basis, core):
    return basis+':'+hashlib.sha256(str(core).encode()).hexdigest()[:20]


def truth(value):
    return False if pd.isna(value) else value is True or value==1 or str(value).lower()=='true'


def build_memberships(documented, roster, profiles=None, model_members=None, *,
                      document_basis="documented_school_assignment_2025",
                      document_function="school", document_year=2025, core_column="campus_id",
                      reference_period=None, system_discriminator=None):
    documented=documented.rename(columns={core_column:"campus_id"}).copy() if core_column!="campus_id" else documented.copy()
    if roster.source_record_id.duplicated().any():
        raise ValueError('Repeated settlement identity in regional roster')
    identity=roster.set_index('source_record_id')
    systems=[];members=[];unresolved=[]
    required={'origin_id','campus_id','source_id','relation_type'}
    if not required<=set(documented):raise ValueError('Incomplete documented school relation schema')
    admitted=documented.origin_id.notna()&documented.campus_id.notna()
    if 'accepted' in documented:admitted &= documented.accepted.map(truth)
    accepted=documented[admitted].copy()
    if not set(accepted.origin_id)<=set(identity.index) or not set(accepted.campus_id)<=set(identity.index):
        raise ValueError('Documented identities outside the accepted regional roster')
    for r in documented[~admitted].to_dict('records'):
        unresolved.append({**r,'membership_basis':document_basis,'document_function':document_function})
    for core,g in accepted.groupby('campus_id',sort=True):
        basis=document_basis;sid=stable_id(basis,core if system_discriminator is None else str(core)+'|'+str(system_discriminator))
        held=documented.loc[documented.campus_id.eq(core)&~admitted]
        explicit_external_held=held if 'member_role' not in held else held[~held.member_role.eq('core_self')]
        ids=set(g.origin_id)|{core}
        for member in sorted(ids):
            row=identity.loc[member]
            source=g.loc[g.origin_id.eq(member)]
            members.append({'system_id':sid,'source_record_id':member,'core_id':core,
                'role':'core' if member==core else 'external','membership_basis':basis,
                'name':row['name'],'population_2021':row.population_2021,
                'document_relation_explicit':not source.empty,
                'source_ids_json':json.dumps(sorted(source.source_id.dropna().unique().tolist())),
                'source_urls_json':json.dumps(sorted(source.source_url.dropna().unique().tolist())) if 'source_url' in g else '[]',
                'documented_membership_complete':len(explicit_external_held)==0,
                'documented_held_relation_rows':len(explicit_external_held),
                'observed_trip_flow':False,'membership_expanded_by_functional_links':False})
        systems.append({'system_id':sid,'core_id':core,'core_name':identity.loc[core,'name'],
            'membership_basis':basis,'evidence_year':document_year,'document_function':document_function,
            'membership_definition':'documented_service_locality_and_explicit_assigned_settlements',
            'reference_period':reference_period,
            'documented_held_relation_rows':len(explicit_external_held),
            'documented_membership_complete':len(explicit_external_held)==0,
            'proves_all_function_system':False})
    if profiles is not None and model_members is not None:
        p=profiles[profiles.evidence_scenario.eq(SCENARIO)&profiles.centre_in_regional_roster.eq(True)]
        m=model_members[model_members.evidence_scenario.eq(SCENARIO)]
        if p.centre_id.duplicated().any():raise ValueError('Repeated preferred model candidate')
        for core in sorted(p.centre_id):
            basis='model_basic_union';sid=stable_id(basis,core)
            ids=set(m.loc[m.centre_id.eq(core),'origin_id'])|{core}
            if not ids<=set(identity.index):raise ValueError('Model member outside regional roster')
            for member in sorted(ids):
                row=identity.loc[member]
                members.append({'system_id':sid,'source_record_id':member,'core_id':core,
                    'role':'core' if member==core else 'external','membership_basis':basis,
                    'name':row['name'],'population_2021':row.population_2021,
                    'document_relation_explicit':False,'source_ids_json':'[]','source_urls_json':'[]',
                    'documented_membership_complete':None,'documented_held_relation_rows':None,
                    'observed_trip_flow':False,'membership_expanded_by_functional_links':False})
            systems.append({'system_id':sid,'core_id':core,'core_name':identity.loc[core,'name'],
                'membership_basis':basis,'evidence_year':None,
                'membership_definition':'archived_direct_basic_function_union_no_transitive_expansion',
                'proves_all_function_system':False})
    members=pd.DataFrame(members,columns=['system_id','source_record_id','core_id','role','membership_basis',
        'name','population_2021','document_relation_explicit','source_ids_json','source_urls_json',
        'observed_trip_flow','membership_expanded_by_functional_links',
        'documented_membership_complete','documented_held_relation_rows'])
    if members.duplicated(['system_id','source_record_id']).any():raise ValueError('Double-counted member')
    if not members.loc[members.role.eq('core')].groupby('system_id').size().eq(1).all():
        raise ValueError('Exactly one declared core required in this representation')
    return pd.DataFrame(systems),members,pd.DataFrame(unresolved)


def destination_scope(key, origin, core, member_ids):
    if not key.startswith('np:'):return 'physical_site_np_unresolved',None
    target=key[3:]
    if target==origin:return 'own',target
    if target==core:return 'core',target
    if target in member_ids:return 'other_internal',target
    return 'external',target


def describe_functions(systems,members,links):
    selected=links[links.evidence_scenario.eq(SCENARIO)].copy()
    if selected.duplicated(['origin_id','family']).any():raise ValueError('Repeated preferred functional outcome')
    families=sorted(selected.family.unique())
    index={(r.origin_id,r.family):r for r in selected.itertuples(index=False)}
    outcomes=[];destinations=[]
    for s in systems.itertuples(index=False):
        cohort=members[members.system_id.eq(s.system_id)]
        member_ids=set(cohort.source_record_id)
        for m in cohort.itertuples(index=False):
            for family in families:
                r=index.get((m.source_record_id,family))
                cost=float(r.cost_minutes) if r is not None and pd.notna(r.cost_minutes) else None
                keys=json.loads(r.coequal_primary_keys_json) if r is not None and pd.notna(r.coequal_primary_keys_json) else []
                if len(keys)!=len(set(keys)):raise ValueError('Repeated equal destination')
                if cost is not None and (not np.isfinite(cost) or cost<0):raise ValueError('Invalid stored choice cost')
                if cost is None and keys:raise ValueError('Destination set without finite archived cost')
                if cost is not None and not keys:raise ValueError('Finite cost without destination evidence')
                classified=[(key,*destination_scope(key,m.source_record_id,s.core_id,member_ids)) for key in keys]
                scopes=sorted(set(scope for _,scope,_ in classified))
                state=('accessibility_unknown' if not classified else scopes[0] if len(classified)==1
                    else 'coequal_same_scope' if len(scopes)==1 else 'coequal_mixed_scope')
                outcomes.append({'system_id':s.system_id,'membership_basis':s.membership_basis,
                    'origin_id':m.source_record_id,'origin_name':m.name,'origin_role':m.role,
                    'population_2021':m.population_2021,'family':family,
                    'outcome_status':state,'destination_scopes_json':json.dumps(scopes),
                    'destination_keys_json':json.dumps(keys),'coequal_destination_count':len(keys),
                    'cost_minutes':cost,'known_local_supply':truth(r.known_local_supply) if r is not None else False,
                    'archived_outcome_row_present':r is not None,
                    'source_id':getattr(r,'source_id',None),'source_year':getattr(r,'source_year',None),
                    'provider_operation_verified':truth(getattr(r,'operation_verified',False)),
                    'school_grades_verified':truth(getattr(r,'school_grades_verified',False)),
                    'observed_trip_flow':False,'documented_membership_does_not_validate_other_functions':True,
                    'country_route_scope':'archived_v2_physical_provider_costs_not_globally_country_revalidated'})
                for key,scope,target in classified:
                    destinations.append({'system_id':s.system_id,'membership_basis':s.membership_basis,
                        'origin_id':m.source_record_id,'origin_role':m.role,'family':family,
                        'origin_population_2021':m.population_2021,
                        'destination_key':key,'destination_np_id':target,'destination_scope':scope,
                        'cost_minutes':cost,'choice_unique':len(keys)==1,'observed_trip_flow':False,
                        'changes_system_membership':False})
    o=pd.DataFrame(outcomes)
    edge_columns=['system_id','membership_basis','origin_id','origin_role','family','origin_population_2021',
        'destination_key','destination_np_id','destination_scope','cost_minutes','choice_unique','observed_trip_flow','changes_system_membership']
    e=pd.DataFrame(destinations,columns=edge_columns)
    roles=[]
    # A subcentre needs a direct edge from another member of this fixed cohort.
    internal=e[e.destination_scope.isin(['core','other_internal'])&e.origin_population_2021.gt(0)]
    for (sid,target),g in internal.groupby(['system_id','destination_np_id'],sort=True):
        core=systems.set_index('system_id').loc[sid,'core_id']
        roles.append({'system_id':sid,'source_record_id':target,
            'role':'core_receiving_internal_links' if target==core else 'internal_functional_subcentre_candidate',
            'incoming_distinct_other_inhabited_members':g.origin_id.nunique(),
            'incoming_all_reference_members':e.loc[e.system_id.eq(sid)&e.destination_np_id.eq(target)&e.origin_id.ne(target),'origin_id'].nunique(),
            'incoming_families_json':json.dumps(sorted(g.family.unique().tolist())),
            'all_incoming_choices_unique':bool(g.choice_unique.all()),
            'direct_modeled_role_not_observed_flow':True,'membership_expanded':False})
    return o,e,pd.DataFrame(roles,columns=['system_id','source_record_id','role',
        'incoming_distinct_other_inhabited_members','incoming_all_reference_members',
        'incoming_families_json','all_incoming_choices_unique','direct_modeled_role_not_observed_flow','membership_expanded'])


def apply_identity_overrides(documented,overrides,roster):
    """Resolve reviewed exact district/name identities without rewriting raw evidence."""
    x=documented.copy()
    x['raw_identity_accepted']=x.accepted.map(truth)
    x['identity_override_applied']=False
    identities=roster.set_index('source_record_id')
    keys=['source_id','section_number','member_literal']
    if overrides.duplicated(keys).any():raise ValueError('Repeated medical identity override')
    for r in overrides.itertuples(index=False):
        mask=(x.source_id.eq(r.source_id)&x.section_number.astype(str).eq(str(r.section_number))
            &x.member_literal.eq(r.member_literal))
        if int(mask.sum())!=1:raise ValueError('Override must identify exactly one source statement')
        old=x.loc[mask].iloc[0]
        if truth(old.accepted):raise ValueError('Override unexpectedly changes an already accepted identity')
        if old.get('identity_status')!='held_kind_not_explicit' or pd.notna(old.get('member_kind')):
            raise ValueError('Only an otherwise admissible locality with unspecified kind may be reviewed')
        if old.get('reference_time')!='document_2025_description_active_not_independently_verified2026':
            raise ValueError('Identity review cannot reactivate a closed, planned or temporally held site')
        if old.get('member_role')!='documented_external_member_not_assumed_fap_host':
            raise ValueError('Identity review requires an explicitly named external settlement')
        if pd.notna(old.origin_id) and old.origin_id!=r.origin_id:raise ValueError('Override conflicts with an explicit source identity')
        if r.origin_id not in identities.index:raise ValueError('Override outside accepted regional identities')
        normalize=lambda v:str(v).strip().casefold().replace('ё','е')
        if normalize(identities.loc[r.origin_id,'name'])!=normalize(r.member_literal):
            raise ValueError('Override locality name differs; fuzzy name substitution is forbidden')
        if 'district_norm' not in roster or pd.isna(old.get('rayon')):
            raise ValueError('Explicit source district and regional district identities are required')
        candidates=roster.loc[roster.district_norm.map(normalize).eq(normalize(old.rayon))
            &roster.name.map(normalize).eq(normalize(r.member_literal)),'source_record_id']
        if len(candidates)!=1 or candidates.iloc[0]!=r.origin_id:
            raise ValueError('Reviewed locality must have one exact name identity in the explicit district')
        x.loc[mask,'origin_id']=r.origin_id;x.loc[mask,'accepted']=True
        x.loc[mask,'identity_status']=r.identity_status;x.loc[mask,'identity_override_applied']=True
        x.loc[mask,'identity_override_reason']=r.reason
    return x


def validate_medical_relations(documented,roster,links):
    """Test a new document against unchanged archived functional choices."""
    selected=links[links.evidence_scenario.eq(SCENARIO)]
    index={(r.origin_id,r.family):r for r in selected.itertuples(index=False)}
    identity=roster.set_index('source_record_id')
    result=[]
    for row in documented.to_dict('records'):
        core,origin=row.get('core_id'),row.get('origin_id')
        admitted=truth(row.get('accepted',False)) and pd.notna(core) and pd.notna(origin)
        r=index.get((origin,row['family'])) if admitted else None
        keys=json.loads(r.coequal_primary_keys_json) if r is not None and pd.notna(r.coequal_primary_keys_json) else []
        cost=float(r.cost_minutes) if r is not None and pd.notna(r.cost_minutes) else None
        pop=identity.loc[origin,'population_2021'] if admitted else None
        if not admitted:state='document_identity_or_temporal_scope_held'
        elif origin==core:state='own_documented_site_not_external_validation'
        elif not keys or cost is None:state='model_accessibility_unknown'
        elif 'np:'+str(core) in keys:state='matches_unique_model_choice' if len(keys)==1 else 'matches_coequal_model_choice'
        elif all(not k.startswith('np:') for k in keys):state='model_destination_np_unresolved'
        else:state='different_model_destination'
        result.append({**row,'validation_status':state,'population_2021':pop,
            'is_external_inhabited_validation':bool(admitted and origin!=core and pd.notna(pop) and pop>0),
            'model_destination_keys_json':json.dumps(keys),'model_cost_minutes':cost,
            'model_inventory':'archived_physical_official_enrichment_v2_unchanged',
            'document_used_to_enrich_this_model_inventory':False,
            'observed_trip_flow':False})
    return pd.DataFrame(result)


def population_profiles(members,roster,point_maxima):
    chosen=point_maxima[point_maxima.neighbour_count.eq(6)].copy()
    scenario=['source_record_id','kernel','half_time','include_self']
    if chosen.duplicated(scenario).any():raise ValueError('Repeated k6 population diagnostic')
    chosen['population_concentration_status']=np.where(~chosen.point_comparison_testable,
        'comparison_unknown',np.where(chosen.sampled_point_maximum,'sampled_maximum','not_sampled_maximum'))
    columns=['system_id','source_record_id','role','membership_basis']
    out=members[columns].merge(chosen,on='source_record_id',how='left',validate='many_to_many')
    out['population_maximum_is_functional_centre_proof']=False
    return out


def summarize(systems,members,outcomes,edges,roles,roster):
    r=roster.set_index('source_record_id')
    records=[]
    for s in systems.to_dict('records'):
        sid=s['system_id'];m=members[members.system_id.eq(sid)]
        external=m[m.role.eq('external')];living=external[external.population_2021.gt(0)]
        info={**s,'member_records_including_core':len(m),'external_records_including_zero_population':len(external),
            'external_inhabited_members':len(living),'external_zero_population_members':int(external.population_2021.eq(0).sum()),
            'external_population_unknown_members':int(external.population_2021.isna().sum()),
            'has_external_inhabited_members':len(living)>0,
            'framework_kind':('partial_documented_framework_with_unresolved_external_members'
                if s.get('documented_membership_complete') is False else
                'external_framework' if len(living) else 'local_site_without_external_inhabited_members'),
            'internal_subcentre_candidates':int(((roles.system_id.eq(sid))&(roles.role.eq('internal_functional_subcentre_candidate'))).sum()) if len(roles) else 0,
            'empirical_common_hierarchy_established':False,'no_population_sum_across_frameworks':True}
        for role,ids in [('core',[s['core_id']]),('external',external.source_record_id.tolist())]:
            for year in (2002,2010,2021):
                c='population_'+str(year)
                values=pd.to_numeric(r.reindex(ids)[c],errors='coerce') if c in r else pd.Series(np.nan,index=ids,dtype=float)
                finite=values.notna()&np.isfinite(values)&values.ge(0)
                info[f'{role}_linked_population_{year}_known_records']=int(finite.sum())
                info[f'{role}_linked_population_{year}_records']=len(ids)
                info[f'{role}_linked_population_{year}_known_subset']=float(values[finite].sum()) if finite.any() or not ids else None
                info[f'{role}_linked_population_{year}_accepted_subset_complete_sum']=float(values.sum()) if finite.all() else None
                info[f'{role}_linked_population_{year}_all_primary_observations_verified']=False
        for year in (2002,2010,2021):
            core_sum=info[f'core_linked_population_{year}_accepted_subset_complete_sum']
            external_sum=info[f'external_linked_population_{year}_accepted_subset_complete_sum']
            complete_document=s.get('documented_membership_complete') is True
            info[f'full_documented_system_population_{year}']=(core_sum+external_sum
                if complete_document and core_sum is not None and external_sum is not None else None)
            info[f'full_documented_external_population_{year}']=(external_sum if complete_document else None)
        records.append(info)
    summary=pd.DataFrame(records)
    function_counts=outcomes.groupby(['system_id','membership_basis','family','outcome_status'],dropna=False).agg(
        member_records=('origin_id','size'),
        inhabited_member_records=('population_2021',lambda x:int(x.gt(0).sum()))).reset_index()
    return summary,function_counts


def run(input_root,documented_path,output,medical_documented_path=None,medical_identity_overrides=None):
    root,output=Path(input_root),Path(output);output.mkdir(parents=True,exist_ok=True)
    roster=pd.read_parquet(root/'fields/regional_roster.parquet')
    profiles=pd.read_parquet(root/'physical_official/basic_centre_profiles.parquet')
    model_members=pd.read_parquet(root/'physical_official/basic_centre_members.parquet')
    links=pd.read_parquet(root/'physical_official/functional_links.parquet')
    maxima=pd.read_parquet(root/'organisation/point_maxima.parquet')
    documented=pd.read_csv(documented_path)
    systems,members,unresolved=build_memberships(documented,roster,profiles,model_members)
    medical=None
    if medical_documented_path is not None:
        medical=pd.read_csv(medical_documented_path)
        override_path=Path(medical_identity_overrides) if medical_identity_overrides is not None else Path(__file__).resolve().parents[2]/'sgrt/saratov/medical_identity_overrides_20261106.csv'
        if override_path.is_file():medical=apply_identity_overrides(medical,pd.read_csv(override_path),roster)
        required={'family','reference_time','accepted','core_id','origin_id'}
        if not required<=set(medical):raise ValueError('Medical framework source needs explicit function, period and admission')
        if not set(medical.family)<=set(links.family):raise ValueError('Unknown medical function; do not silently alias')
        for (family,period),group in medical.groupby(['family','reference_time'],dropna=False,sort=True):
            ms,mm,mu=build_memberships(group,roster,document_basis='documented_medical_assignment_2025',
                document_function=family,document_year=2025,core_column='core_id',reference_period=period,
                system_discriminator=str(family)+'|'+str(period))
            if not ms.empty:systems=pd.concat([systems,ms],ignore_index=True)
            if not mm.empty:members=pd.concat([members,mm],ignore_index=True)
            unresolved=pd.concat([unresolved,mu],ignore_index=True)
    outcomes,edges,roles=describe_functions(systems,members,links)
    scales=population_profiles(members,roster,maxima)
    summary,counts=summarize(systems,members,outcomes,edges,roles,roster)
    frames={'systems':summary,'system_members':members,'member_function_outcomes':outcomes,
        'direct_function_destinations':edges,'internal_functional_roles':roles,
        'population_scale_profiles':scales,'system_function_summary':counts,
        'unresolved_documented_members':unresolved}
    if medical is not None:
        frames['documented_medical_relation_validation']=validate_medical_relations(medical,roster,links)
    for name,frame in frames.items():
        frame.to_parquet(output/(name+'.parquet'),index=False,compression='zstd')
    summary.to_csv(output/'systems.csv',index=False)
    members.to_csv(output/'system_members.csv',index=False)
    report={'schema':'sgrt.saratov.fixed_system_structure.v1','systems_by_membership_basis':summary.groupby('membership_basis').size().to_dict(),
        'documented_school_frameworks_with_external_inhabited_members':int((summary.membership_basis.eq('documented_school_assignment_2025')&summary.has_external_inhabited_members).sum()),
        'documented_school_unique_accepted_records':members.loc[members.membership_basis.eq('documented_school_assignment_2025'),'source_record_id'].nunique(),
        'documented_unresolved_relation_rows':len(unresolved),'member_function_outcomes':len(outcomes),
        'external_inhabited_frameworks_by_membership_basis':summary.loc[summary.has_external_inhabited_members].groupby('membership_basis').size().to_dict(),
        'population_scenario_definition':'k=6 outgoing national-neighbour diagnostics; 36 kernel/half-time/self scenarios, not functional levels',
        'membership_transitively_expanded':False,'observed_trip_flows_established':False,
        'new_confirmed_all_function_centre_count':None}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-root',type=Path,required=True);p.add_argument('--documented',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--medical-documented',type=Path)
    p.add_argument('--medical-identity-overrides',type=Path)
    a=p.parse_args();print(json.dumps(run(a.input_root,a.documented,a.output,a.medical_documented,a.medical_identity_overrides),ensure_ascii=False,indent=2))


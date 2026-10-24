#!/usr/bin/env python3
"""Mass service cells, complete descriptive types and non-forced overlap links.

No population or object count is an attraction weight. Screening is a dated
planning scenario, not proof of journeys. Site ownership remains unknown when
an actual geographic school object cannot be identified with a census NP.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit import classify_service_screen, canonical_assignments, CANDIDATE_CLASSES


def save(frame,path,csv=True):
    path.parent.mkdir(parents=True,exist_ok=True)
    frame.to_parquet(path.with_suffix('.parquet'),index=False,compression='zstd')
    if csv:frame.to_csv(path.with_suffix('.csv'),index=False)


def signs(start,end):
    result=pd.Series('unknown',index=start.index)
    known=start.notna()&end.notna()
    result.loc[known&end.gt(start)]='growth'
    result.loc[known&end.lt(start)]='decline'
    result.loc[known&end.eq(start)]='unchanged'
    return result


def provenance_list(value):
    """Keep nullable numeric years and JSON/string source IDs in one encoding."""
    if value is None or value is pd.NA or isinstance(value,float) and np.isnan(value):return None
    if isinstance(value,str):
        try:value=json.loads(value)
        except (ValueError,TypeError):value=[value]
    if not isinstance(value,list):value=[value]
    normalized=[]
    for item in value:
        if item is None:continue
        if isinstance(item,np.integer):item=int(item)
        if isinstance(item,(float,np.floating)) and np.isfinite(item) and float(item).is_integer():item=int(item)
        normalized.append(item)
    return json.dumps(normalized,ensure_ascii=False)


def screen_cache_matches(frame,current):
    """A saved screen may be reused only for the same selected road evidence."""
    fresh=canonical_assignments(current)
    if not frame.origin_id.equals(fresh.origin_id):return False
    for name in ['provider_settlement_id','provider_site_id']:
        if not frame[name].fillna('__NULL__').astype(str).equals(fresh[name].fillna('__NULL__').astype(str)):return False
    if not np.array_equal(frame.cost_minutes.to_numpy(float),fresh.cost_minutes.to_numpy(float),equal_nan=True):return False
    if 'local_supply_status' in fresh and not frame.local_supply_status.equals(fresh.local_supply_status):return False
    return True


def agri_profile(context):
    result=context.copy()
    total=pd.to_numeric(result.agri_sown_area_ha_2021_municipal_context,errors='coerce')
    result['agri_context_profile']='insufficient_municipal_data'
    selected=['grain','feed','technical']
    values=pd.DataFrame({x:pd.to_numeric(result[f'agri_{x}_sown_ha_2021_municipal_context'],errors='coerce') for x in selected})
    positive=total.gt(0)
    valid=positive&values.notna().all(axis=1)&values.ge(0).all(axis=1)&values.sum(axis=1).le(total*1.02)
    result.loc[total.eq(0)&values.fillna(0).sum(axis=1).eq(0),'agri_context_profile']='reported_zero_sown_area_municipality'
    result.loc[valid,'agri_context_profile']='no_dominant_selected_crop_group'
    dominant=values.ge(total*.5,axis=0)&valid.to_numpy()[:,None]
    for name in selected:
        result.loc[dominant[name]&dominant.sum(axis=1).eq(1),'agri_context_profile']=name+'_dominant_municipal_context'
    result.loc[dominant.sum(axis=1).gt(1),'agri_context_profile']='tied_selected_crop_groups'
    result['agri_profile_is_settlement_own_production']=False
    return result


def unit_table(members,reference,service,scenario):
    """Vectorized sums on credited, explicitly comparable source histories."""
    data=members.copy()
    cols=['source_record_id','name','region','population_role']+[f'{x}_{y}' for y in [2002,2010,2021] for x in ['population','credit']]
    extras=[c for c in reference if c.startswith('population_value_quality_')]
    ref=reference[reference.source_record_id.notna()][cols+extras].copy()
    data=data.merge(ref.rename(columns={'source_record_id':'origin_id','name':'origin_reference_name','region':'origin_reference_region','population_role':'origin_population_role'}),on='origin_id',how='left',validate='many_to_one',suffixes=('','_reference'))
    # The immutable reference wins if a transport row also carries populations.
    for y in [2002,2010,2021]:
        if f'population_{y}_reference' in data:data[f'population_{y}']=data[f'population_{y}_reference']
    data['external']=data.provider_settlement_id.notna()&~data.origin_id.eq(data.provider_settlement_id)
    data['center_np_relation_unknown']=data.provider_settlement_id.isna()
    data['known_populated_origin']=data.credit_2021&data.population_2021.gt(0)&data.origin_population_role.eq('ordinary_settlement_record')
    data['known_positive_external']=data.external&data.credit_2021&data.population_2021.gt(0)&data.origin_population_role.eq('ordinary_settlement_record')
    data['external_pop_known']=data.external&data.credit_2021&data.population_2021.notna()&data.origin_population_role.eq('ordinary_settlement_record')
    for y in [2002,2010,2021]:
        data[f'comparable_{y}']=data[f'population_{y}'].notna()&data[f'credit_{y}']&data.origin_population_role.eq('ordinary_settlement_record')
    data['cohort3']=data.external&data[[f'comparable_{y}' for y in [2002,2010,2021]]].all(axis=1)
    data['cohort02_21']=data.external&data.comparable_2002&data.comparable_2021
    data['cohort10_21']=data.external&data.comparable_2010&data.comparable_2021
    data['external_population_contribution']=data.population_2021.where(data.external_pop_known)
    data['origin_population_contribution']=data.population_2021.where(data.credit_2021&data.origin_population_role.eq('ordinary_settlement_record'))
    data['external_unresolved_population']=data.external&~data.external_pop_known
    grouped=data.groupby('center_key',sort=False,dropna=False)
    first=grouped.first()
    out=pd.DataFrame({'center_key':first.index,'center_source_record_id':first.provider_settlement_id.values,
                      'center_site_id':first.provider_site_id.values,'center_name':first.provider_name.values,
                      'center_region':first.provider_region.values,'center_lat':first.provider_lat.values,
                      'center_lon':first.provider_lon.values,'center_identity_status':first.center_identity_status.values})
    out=out.set_index('center_key',drop=False)
    out['member_records']=grouped.size()
    out['known_populated_origin_records']=grouped.known_populated_origin.sum()
    out['external_records']=grouped.external.sum()
    out['n_populated_external']=grouped.known_positive_external.sum()
    out['external_population_unresolved_records']=grouped.external_unresolved_population.sum()
    out['external_population_2021']=grouped.external_population_contribution.sum(min_count=1)
    out.loc[out.external_records.eq(0),'external_population_2021']=0
    out.loc[out.center_source_record_id.isna(),'external_population_2021']=np.nan
    out['external_unknown_local_supply']=grouped.local_supply_unknown.sum()
    out['median_associated_origin_minutes']=grouped.cost_minutes.median()
    out['max_associated_origin_minutes']=grouped.cost_minutes.max()
    out['max_associated_origin_point_km']=grouped.point_separation_km.max()
    for target,options in {
        'provider_source_ids':['selected_source_ids_json','selected_provider_source_id'],
        'provider_source_years':['selected_source_years_json','selected_provider_observation_year'],
        'provider_inventory_completeness':['provider_inventory_completeness'],
        'provider_geometry_kind':['provider_geometry_kind'],
        'screen_source_id':['screen_source_id'],
    }.items():
        available=next((c for c in options if c in first),None)
        out[target]=first[available] if available else None
        if target in ['provider_source_ids','provider_source_years']:
            out[target]=out[target].map(provenance_list).astype('string')
    for stat,fn in [('median',lambda x:x.median()),('p95',lambda x:x.quantile(.95)),('max',lambda x:x.max())]:
        ext=data[data.external].groupby('center_key')
        out[f'{stat}_external_minutes']=fn(ext.cost_minutes)
        out[f'{stat}_external_point_km']=fn(ext.point_separation_km)
    out=out.reset_index(drop=True).merge(ref.rename(columns={c:'center_'+c for c in ref if c!='source_record_id'}),left_on='center_source_record_id',right_on='source_record_id',how='left',validate='many_to_one').drop(columns='source_record_id')
    # Avoid duplicate names/geometry: center_name from the service cell may be
    # a physical object label; census fields are kept under explicit names.
    if 'center_name_y' in out:
        out['center_name']=out.center_name_y.fillna(out.center_name_x)
        out=out.drop(columns=['center_name_x','center_name_y'])
    if 'center_region_y' in out:
        out['center_region']=out.center_region_y.fillna(out.center_region_x)
        out=out.drop(columns=['center_region_x','center_region_y'])
    out['center_population_role']=out.center_population_role.fillna('unknown_center_settlement_identity')
    out=out.set_index('center_key',drop=False)
    for label,years in [('02_21',[2002,2021]),('10_21',[2010,2021])]:
        subset=data[data['cohort'+label]]
        cohort=subset.groupby('center_key')
        out[f'comparable_external_records_{label}']=cohort.size().reindex(out.index).fillna(0).astype(int)
        for y in years:
            out[f'external_comparable_population_{label}_{y}']=cohort[f'population_{y}'].sum(min_count=1)
        a,b=years
        cstart=out[f'center_population_{a}'].where(out[f'center_credit_{a}'].astype('boolean').fillna(False)&out.center_population_role.eq('ordinary_settlement_record'))
        cend=out[f'center_population_{b}'].where(out[f'center_credit_{b}'].astype('boolean').fillna(False)&out.center_population_role.eq('ordinary_settlement_record'))
        cd=signs(cstart,cend)
        pdirection=signs(out[f'external_comparable_population_{label}_{a}'],out[f'external_comparable_population_{label}_{b}'])
        out[f'center_direction_{label}']=cd
        out[f'periphery_direction_{label}']=pdirection
        types='center_'+cd+'__periphery_'+pdirection
        types=types.mask(cd.eq('unknown')|pdirection.eq('unknown'),'insufficient_comparable_demography')
        types=types.mask(out.n_populated_external.eq(0),'node_without_known_populated_external_members')
        types=types.mask(out.external_records.eq(0),'node_without_external_members')
        types=types.mask(out.center_source_record_id.isna(),'center_settlement_identity_unknown')
        types=types.mask(out.center_population_role.eq('external_context_nonadditive'),'external_context_nonadditive')
        out[f'demographic_type_{label}']=types
    out['type_code']=out.demographic_type_02_21
    labels={'growth':'рост','decline':'сокращение','unchanged':'без изменения'}
    special={'insufficient_comparable_demography':'Недостаточно сопоставимых данных',
             'node_without_known_populated_external_members':'Нет известных населённых внешних участников',
             'node_without_external_members':'Узел без внешней зоны в сценарии',
             'center_settlement_identity_unknown':'НП учреждения не установлен',
             'external_context_nonadditive':'Внешний неаддитивный контекст'}
    out['type_label_ru']=out.type_code.map(special)
    for c,clabel in labels.items():
        for p,plabel in labels.items():
            mask=out.type_code.eq('center_'+c+'__periphery_'+p)
            out.loc[mask,'type_label_ru']='Центр: '+clabel+'; окружение: '+plabel
    out['scenario']=scenario;out['service_code']=service
    out['unit_id']=scenario+'|'+service+'|'+out.center_key
    out['is_inhabited_external_candidate_cell']=out.n_populated_external.gt(0)
    out['is_populated_site_service_cell']=out.center_source_record_id.isna()&out.known_populated_origin_records.gt(0)
    out['unit_is_established_sgrt']=False
    out['historical_functional_boundary_equivalence_proven']=False
    out['capacity_feasibility_estimated']=False
    out['type_is_causal_word_type']=False
    out['agro_or_employment_used_as_attraction_weight']=False
    out['center_population2021']=out.center_population_2021
    out['known_function_count']=np.nan
    return out.reset_index(drop=True),data


def build(root,output=None,resume_screened=False):
    root=Path(root);out=Path(output) if output is not None else root/'model';out.mkdir(parents=True,exist_ok=True)
    reference=pd.read_parquet(root/'context/census_reference.parquet')
    nodes=pd.read_parquet(root/'routes/endpoints.parquet')
    nodes=nodes[[c for c in ['source_record_id','root','name','region','lat','lon','settlement_type','population','working_credit_present'] if c in nodes]].copy()
    # Adopt source settlement types from the unchanged prepared census frame.
    if 'settlement_type' not in nodes:
        prepared=pd.read_parquet(root/'inputs/settlements_all_2021.parquet',columns=['source_record_id','settlement_type'])
        nodes=nodes.merge(prepared,on='source_record_id',how='left',validate='one_to_one')
    memberships=[];units=[];raw_summaries=[]
    paths=[('registry_or_address_np',p) for p in sorted((root/'routes/nearest').glob('*.parquet'))]
    paths += [('physical_sites',p) for p in sorted((root/'routes_sites/nearest').glob('*.parquet'))]
    main_records=[]
    for mode,path in paths:
        print('Screening',mode,path.stem,flush=True)
        service=path.stem
        # Official preschool remains an independent 2025 scenario.
        scenario=mode
        cache=out/'screened'/f'{mode}_{service}.parquet'
        if resume_screened and cache.exists():
            frame=pd.read_parquet(cache)
            import pyarrow.parquet as pq
            names=pq.ParquetFile(path).schema_arrow.names
            provenance=['selected_source_ids_json','selected_source_years_json','selected_provider_source_id','selected_provider_observation_year','provider_inventory_completeness']
            extra=[c for c in provenance if c in names and c not in frame]
            choice=['origin_id','service_code','cost_minutes','selected_provider_source_record_id','selected_provider_settlement_id','selected_provider_id','provider_id','primary_candidate_id','local_supply_status']
            columns=list(dict.fromkeys([c for c in choice+extra if c in names]))
            current=pd.read_parquet(path,columns=columns)
            if not screen_cache_matches(frame,current):
                print('Recomputing changed road evidence',mode,service,flush=True)
                frame=classify_service_screen(pd.read_parquet(path),nodes)
                cache.unlink()
            elif extra:
                frame=frame.merge(current[['origin_id']+extra],on='origin_id',how='left',validate='one_to_one')
        else:
            raw=pd.read_parquet(path)
            service=str(raw.service_code.iloc[0])
            frame=classify_service_screen(raw,nodes)
        selected=frame[frame.screened_external_candidate|frame.screen_class.eq('local_known_service_candidate')].copy()
        frame['scenario']=scenario
        essential=['origin_id','service_code','scenario','center_key','provider_settlement_id','provider_site_id',
                   'center_identity_status','cost_minutes','network_minutes','connector_minutes','is_local',
                   'screen_class','screened_external_candidate','local_supply_status','local_supply_unknown',
                   'point_separation_km','benchmark_context','screen_source_id','planning_benchmark_minutes',
                   'raw_nearest_is_established_attachment','provider_geometry_kind','provider_name','provider_region','provider_lat','provider_lon']
        if not resume_screened or not cache.exists():save(frame[[x for x in essential if x in frame]],out/'screened'/f'{mode}_{service}',csv=False)
        raw_summaries.append({'scenario':scenario,'service_code':service,'origin_records':len(frame),
            'known_local':int(frame.is_local.sum()),'screened_external':int(frame.screened_external_candidate.sum()),
            'outside_or_unknown_screen':int((~frame.screened_external_candidate&~frame.is_local).sum()),
            'median_raw_minutes':float(frame.cost_minutes.median()),'max_raw_minutes':float(frame.cost_minutes.max()),
            'screened_external_max_minutes':float(selected.loc[~selected.is_local,'cost_minutes'].max()) if len(selected) else None})
        if selected.empty:continue
        local_units,expanded=unit_table(selected,reference,service,scenario)
        # The primary output uses actual OSM geography, not the small subset
        # that happened to have an address. Address-only results are diagnostic.
        main=(service.startswith('medical_') or service=='preschool_official') and mode=='registry_or_address_np' or mode=='physical_sites'
        if not main:
            save(local_units,out/'diagnostics'/f'{mode}_{service}_units')
            continue
        units.append(local_units)
        keep=['origin_id','service_code','center_key','provider_settlement_id','provider_site_id','cost_minutes','screen_class','is_local','local_supply_unknown','known_positive_external','external_population_contribution','origin_population_contribution','center_np_relation_unknown','point_separation_km']
        m=expanded[keep].copy();m['scenario']=scenario
        m['unit_id']=scenario+'|'+service+'|'+m.center_key
        memberships.append(m)
        main_records.append(frame[['origin_id','service_code','provider_settlement_id','center_key','screened_external_candidate','is_local','screen_class','center_identity_status']].copy())
    u=pd.concat(units,ignore_index=True);m=pd.concat(memberships,ignore_index=True)
    # Sector counts are lower bounds on recorded evidence, never proof of the
    # absence of an unrecorded function and never a new gravitational mass.
    u['sector']=np.where(u.service_code.str.startswith('medical_'),'healthcare','education')
    u['function_channel']=u.service_code.replace({'preschool_official':'preschool'})
    grouped=u[u.center_source_record_id.notna()].groupby('center_source_record_id')
    u['known_function_count']=u.center_source_record_id.map(grouped.function_channel.nunique())
    u['known_sector_count']=u.center_source_record_id.map(grouped.sector.nunique())
    u['function_counts_are_observed_lower_bounds']=True
    if (root/'context/settlement_agriculture_context.parquet').exists():
        context=agri_profile(pd.read_parquet(root/'context/settlement_agriculture_context.parquet'))
        context=context[context.source_record_id.notna()]
        save(context,out/'settlement_agriculture_profiles',csv=False)
        u=u.merge(context[['source_record_id','agri_municipality_code','agri_context_profile']],left_on='center_source_record_id',right_on='source_record_id',how='left',validate='many_to_one').drop(columns='source_record_id')
        # Population exposure to municipal profiles is descriptive; no hectares
        # or livestock are divided or summed repeatedly across settlements.
        exposure=m.merge(context[['source_record_id','agri_context_profile']],left_on='origin_id',right_on='source_record_id',how='left',validate='many_to_one')
        exposure['agri_context_profile']=exposure.agri_context_profile.fillna('insufficient_municipal_data')
        profiles=exposure.groupby(['unit_id','agri_context_profile']).origin_population_contribution.sum(min_count=1).reset_index(name='known_associated_origin_population_in_context')
        profiles['is_production_allocated_to_unit']=False
        save(profiles,out/'unit_agriculture_exposure',csv=False)
        periphery=exposure.groupby(['unit_id','agri_context_profile']).external_population_contribution.sum(min_count=1).reset_index(name='known_external_population_in_context')
        save(periphery,out/'periphery_agriculture_exposure',csv=False)
        totals=periphery.groupby('unit_id').known_external_population_in_context.sum(min_count=1)
        periphery['share_of_known_external_population']=periphery.known_external_population_in_context/periphery.unit_id.map(totals)
        major=periphery[periphery.share_of_known_external_population.gt(.5)].set_index('unit_id').agri_context_profile
        u['periphery_agricultural_context_type']=u.unit_id.map(major).fillna('heterogeneous_or_insufficient_municipal_context')
        u['agricultural_context_is_population_exposure_not_production_allocation']=True
    workforce_path=root/'context/settlement_partial_workforce.parquet'
    if workforce_path.exists():
        workforce=pd.read_parquet(workforce_path)
        workforce=workforce[workforce.source_record_id.notna()]
        fields=['source_record_id','partial_organisation_workforce_2025','partial_workforce_status','partial_workforce_observation_year','partial_workforce_source_id']
        u=u.merge(workforce[fields].rename(columns={c:'center_'+c for c in fields if c!='source_record_id'}),left_on='center_source_record_id',right_on='source_record_id',how='left',validate='many_to_one').drop(columns='source_record_id')
        employment=m[['unit_id','origin_id']].drop_duplicates().merge(workforce[fields],left_on='origin_id',right_on='source_record_id',how='left',validate='many_to_one')
        sums=employment.groupby('unit_id').partial_organisation_workforce_2025.agg([('reported_member_organisation_workers_2025',lambda x:x.sum(min_count=1)),('member_records_with_partial_workforce','count')]).reset_index()
        u=u.merge(sums,on='unit_id',how='left',validate='one_to_one')
        u['employment_type']='partial_workforce_unknown'
        value=u.center_partial_organisation_workforce_2025
        u.loc[value.gt(0),'employment_type']='positive_reported_organisation_workforce_at_centre'
        u.loc[value.eq(0),'employment_type']='reported_zero_in_partial_organisation_scope'
        u['reported_workers_are_total_jobs_or_commuting_flows']=False
    save(u,out/'units')
    save(m,out/'memberships',csv=False)
    save(pd.DataFrame(raw_summaries),out/'source_scenario_comparison')
    main=pd.concat(main_records,ignore_index=True)
    save(main,out/'node_service_states',csv=False)
    overlaps=[]
    a=main[(main.service_code=='medical_basic_primary')&(main.screened_external_candidate|main.is_local)]
    b=main[(main.service_code=='medical_physician_primary')&(main.screened_external_candidate|main.is_local)]
    joined=a[['origin_id','center_key']].merge(b[['origin_id','center_key']],on='origin_id',suffixes=('_basic','_physician'),validate='one_to_one')
    counts=joined.groupby(['center_key_basic','center_key_physician']).size().reset_index(name='shared_origin_records')
    base_sizes=a.groupby('center_key').size()
    counts['all_screened_basic_origin_records']=counts.center_key_basic.map(base_sizes)
    counts['basic_origins_with_known_physician_candidate']=counts.groupby('center_key_basic').shared_origin_records.transform('sum')
    counts['share_of_observed_overlap']=counts.shared_origin_records/counts.basic_origins_with_known_physician_candidate
    counts['share_of_all_basic_origin_records']=counts.shared_origin_records/counts.all_screened_basic_origin_records
    counts['candidate_parent_count']=counts.groupby('center_key_basic').center_key_physician.transform('nunique')
    counts['same_centre_at_both_function_orders']=counts.center_key_basic.eq(counts.center_key_physician)
    counts['complete_single_parent_in_scenario']=counts.candidate_parent_count.eq(1)&counts.basic_origins_with_known_physician_candidate.eq(counts.all_screened_basic_origin_records)
    counts['single_parent_for_all_origins_proven']=False
    counts['observed_patient_referral']=False
    save(counts,out/'basic_physician_overlap_links')
    hierarchy=counts.groupby('center_key_basic').agg(candidate_parent_count=('center_key_physician','nunique'),
        all_basic_origin_records=('all_screened_basic_origin_records','first'),
        higher_function_covered_origin_records=('shared_origin_records','sum'),
        has_distinct_higher_centre=('same_centre_at_both_function_orders',lambda x:(~x).any())).reset_index()
    # Retain basic cells with no accepted higher-order candidate: lack of a
    # link must remain visible instead of removing the lowest systems.
    hierarchy=base_sizes.rename('all_basic_origin_records_base').rename_axis('center_key_basic').reset_index().merge(hierarchy,on='center_key_basic',how='left',validate='one_to_one')
    hierarchy['all_basic_origin_records']=hierarchy.all_basic_origin_records_base
    hierarchy=hierarchy.drop(columns='all_basic_origin_records_base')
    for col in ['candidate_parent_count','higher_function_covered_origin_records']:
        hierarchy[col]=hierarchy[col].fillna(0).astype(int)
    hierarchy['has_distinct_higher_centre']=hierarchy.has_distinct_higher_centre.fillna(False).astype(bool)
    hierarchy['hierarchy_type']='split_higher_function_candidates'
    complete=hierarchy.higher_function_covered_origin_records.eq(hierarchy.all_basic_origin_records)
    hierarchy.loc[hierarchy.candidate_parent_count.eq(1)&complete,'hierarchy_type']='single_parent_in_complete_scenario'
    hierarchy.loc[~complete,'hierarchy_type']='higher_function_coverage_incomplete'
    hierarchy.loc[~hierarchy.has_distinct_higher_centre&complete,'hierarchy_type']='same_centre_serves_both_orders'
    hierarchy.loc[hierarchy.candidate_parent_count.eq(0),'hierarchy_type']='no_known_higher_function_candidate'
    hierarchy['is_observed_referral_hierarchy']=False
    save(hierarchy,out/'medical_functional_hierarchy')
    # Known local nodes remain nodes even if they use a higher function abroad.
    local=main[main.is_local].groupby('origin_id').service_code.agg(lambda x:'|'.join(sorted(set(x))))
    possible=main[main.screened_external_candidate&main.provider_settlement_id.notna()].copy()
    possible['sector']=np.where(possible.service_code.str.startswith('medical_'),'healthcare','education')
    destinations=possible.groupby('origin_id').provider_settlement_id.nunique()
    sectors=possible.groupby('origin_id').sector.nunique()
    states=nodes[['source_record_id','name','region','population','working_credit_present']].copy()
    states['known_local_service_codes']=states.source_record_id.map(local)
    states['screened_distinct_external_np_centres']=states.source_record_id.map(destinations).fillna(0).astype(int)
    states['recorded_external_sectors']=states.source_record_id.map(sectors).fillna(0).astype(int)
    states['functional_state']='no_supported_external_link_or_unknown'
    states.loc[states.screened_distinct_external_np_centres.eq(1),'functional_state']='single_sector_external_candidate'
    states.loc[states.screened_distinct_external_np_centres.eq(1)&states.recorded_external_sectors.ge(2),'functional_state']='two_sector_common_centre_candidate'
    states.loc[states.screened_distinct_external_np_centres.gt(1),'functional_state']='functionally_split_external_candidates'
    site_origins=set(main[main.screened_external_candidate&main.provider_settlement_id.isna()].origin_id)
    states.loc[states.source_record_id.isin(site_origins)&states.screened_distinct_external_np_centres.eq(0),'functional_state']='physical_service_candidate_with_unknown_centre_np'
    states.loc[states.known_local_service_codes.notna(),'functional_state']='known_local_node_with_additional_functional_links'
    states['zero_or_unknown_population_not_automatic_demand']=~states.working_credit_present|states.population.isna()|states.population.eq(0)
    if workforce_path.exists():
        fields=['source_record_id','partial_organisation_workforce_2025','partial_workforce_status']
        states=states.merge(workforce[fields],on='source_record_id',how='left',validate='one_to_one')
        states['positive_partial_employment_observation']=states.partial_organisation_workforce_2025.gt(0)
        states.loc[states.positive_partial_employment_observation&states.known_local_service_codes.isna(),'functional_state']='recorded_employment_node_with_external_service_links'
    states['all_functions_satisfied']=pd.Series(pd.NA,index=states.index,dtype='boolean')
    states['all_functions_satisfaction_estimated']=False
    save(states,out/'settlement_functional_states')
    summary={'ordinary_spatial_settlements':len(nodes),'units_by_service':[],
             'known_np_centres_with_screened_inhabited_external_members':int(u.loc[u.is_inhabited_external_candidate_cell&u.center_source_record_id.notna()&u.center_population_role.eq('ordinary_settlement_record'),'center_source_record_id'].nunique()),
             'site_centres_without_proven_settlement_identity':int(u.loc[u.is_populated_site_service_cell,'center_key'].nunique()),
             'every_unit_typed':bool(u.type_code.notna().all()),'partition_across_services':False,
             'observed_flow_count':0,'complete_general_sgrt_partition_established':False,
             'two_sector_common_centre_candidate_origins':int(states.functional_state.eq('two_sector_common_centre_candidate').sum()),
             'known_local_nodes':int(states.known_local_service_codes.notna().sum()),
             'basic_cells_with_multiple_physician_candidates':int(counts.loc[counts.candidate_parent_count.gt(1),'center_key_basic'].nunique())}
    summary['medical_hierarchy_types']=hierarchy.hierarchy_type.value_counts().to_dict()
    for code,g in u.groupby('service_code'):
        maximum=g.max_external_minutes.max()
        summary['units_by_service'].append({'service_code':code,'units':len(g),'inhabited_external_candidate_cells':int(g.is_inhabited_external_candidate_cell.sum()),'np_identified_candidate_cells':int((g.is_inhabited_external_candidate_cell&g.center_source_record_id.notna()).sum()),'populated_site_cells_with_unknown_np_ownership':int(g.is_populated_site_service_cell.sum()),'max_external_screened_minutes':float(maximum) if pd.notna(maximum) else None})
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--resume-screened',action='store_true',help='Reuse explicitly saved screen tables from the same immutable raw routing inputs')
    args=p.parse_args();print(json.dumps(build(args.root,args.output,args.resume_screened),ensure_ascii=False,indent=2))

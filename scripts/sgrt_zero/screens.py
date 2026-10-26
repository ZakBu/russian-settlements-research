#!/usr/bin/env python3
"""Retain every nearest-service outcome and mark conditional daily candidates.

Travel limits are service-specific scenarios. Far or unroutable settlements
remain in the output and are never labelled independent or without a need.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

SP42 = 'SP42_2016_WEB2024_SERVICE_ACCESS'
SP42_SHA256 = 'f059645cab53219a5825d1fe5a15780926628c1a1e62937e0895b572b302d106'
RAW_CODES = {'medical_basic':'medical_basic_primary','school':'school_general',
             'grocery':'daily_grocery','parcel_pickup':'parcel_pickup_wildberries_current'}
CORE_FAMILIES = ['medical_basic','school','grocery']
SCENARIOS = {
 'daily_20_school30_wb': {'retail_minutes':20.,'school_minutes':30.,'families':[*CORE_FAMILIES,'parcel_pickup'],'role':'main'},
 'daily_10_school15_wb': {'retail_minutes':10.,'school_minutes':15.,'families':[*CORE_FAMILIES,'parcel_pickup'],'role':'cautious_sensitivity'},
 'daily_30_school30_wb': {'retail_minutes':30.,'school_minutes':30.,'families':[*CORE_FAMILIES,'parcel_pickup'],'role':'extended_sensitivity'},
 'core3_20_school30': {'retail_minutes':20.,'school_minutes':30.,'families':CORE_FAMILIES,'role':'no_pickup_channel_sensitivity'},
 'daily_20_school30_yandex': {'retail_minutes':20.,'school_minutes':30.,'families':[*CORE_FAMILIES,'parcel_pickup'],
     'parcel_raw_code':'parcel_pickup_yandex_current','parcel_scope':'Yandex_Market_published_partner_network_only','role':'optional_operator_sensitivity'},
}
DEFAULT_SCENARIOS = ['daily_20_school30_wb','daily_10_school15_wb','daily_30_school30_wb','core3_20_school30']
RURAL_TYPES = {'деревня','село','посёлок','поселок','хутор','железнодорожный объект','станица','станция',
    'разъезд','аул','улус','починок','слобода','участок','выселок','местечко','аал','заимка','кордон','арбан',
    'поселок и(при) станция(и)','казарма','погост'}
URBAN_TYPES = {'город','пгт','рабочий посёлок','рабочий поселок','городской посёлок','городской поселок'}
FEDERAL_CONTEXT_IDS = {'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+s for s in ['64748','126656','121540']}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def metadata_json(value):
    if value is None or value is pd.NA or isinstance(value,(float,np.floating)) and np.isnan(value):return None
    if isinstance(value,str):
        try:value=json.loads(value)
        except (ValueError,TypeError):value=[value]
    if not isinstance(value,list):value=[value]
    def native(item):
        if isinstance(item,np.integer):return int(item)
        if isinstance(item,(float,np.floating)) and np.isfinite(item) and float(item).is_integer():return int(item)
        return item
    return json.dumps([native(x) for x in value if x is not None],ensure_ascii=False)


def get(frame,names,default=None):
    for name in names:
        if name in frame:return frame[name]
    return pd.Series(default,index=frame.index)


def haversine(lon1,lat1,lon2,lat2):
    a,b,c,d=[np.deg2rad(np.asarray(x,dtype=float)) for x in [lon1,lat1,lon2,lat2]]
    q=np.sin((d-b)/2)**2+np.cos(b)*np.cos(d)*np.sin((c-a)/2)**2
    return 12742.0176*np.arcsin(np.sqrt(np.clip(q,0,1)))


def canonical(raw,reference):
    """One outcome per analysis origin; preserve unknown physical-site owners."""
    if 'origin_id' not in raw or raw.origin_id.duplicated().any():raise ValueError('Unique origin_id is required')
    if get(raw,['observed_flow'],False).fillna(False).any() or get(raw,['assignment_established'],False).fillna(False).any():
        raise ValueError('This screen accepts model nearest outcomes, not established observed assignments')
    ref=reference[reference.source_record_id.notna()].copy()
    if ref.source_record_id.duplicated().any():raise ValueError('Reference has repeated source identities')
    active=ref[ref.analysis_origin.fillna(False)] if 'analysis_origin' in ref else ref
    if set(raw.origin_id)!=set(active.source_record_id):raise ValueError('Route origins differ from accepted analysis origins')
    r=ref.set_index('source_record_id').reindex(raw.origin_id).reset_index(drop=True)
    d=pd.DataFrame({'origin_id':raw.origin_id.to_numpy()})
    for target,source in [('origin_name','name'),('origin_region','region'),('origin_lat','lat'),('origin_lon','lon'),
                          ('origin_population_2021','population_2021'),('settlement_type_2021','settlement_type_2021')]:
        d[target]=r[source].to_numpy() if source in r else None
    credit=r.budget_population_credit.fillna(False).astype(bool) if 'budget_population_credit' in r else r.credit_2021.fillna(False).astype(bool)
    d['origin_budget_population_credit']=credit.to_numpy()
    d['origin_population_known']=pd.to_numeric(d.origin_population_2021,errors='coerce').notna()
    d['origin_positive_population']=pd.to_numeric(d.origin_population_2021,errors='coerce').gt(0)
    d['origin_positive_population_credited']=d.origin_positive_population&d.origin_budget_population_credit
    d['origin_credited_population_2021']=pd.to_numeric(d.origin_population_2021,errors='coerce').where(d.origin_budget_population_credit)
    d['origin_is_additional_context']=(~r.ordinary_spatial_2021.fillna(False)).to_numpy() if 'ordinary_spatial_2021' in r else False
    identity=get(raw,['provider_settlement_id','selected_provider_source_record_id']).astype('string').str.strip().replace('',pd.NA)
    d['provider_settlement_id']=identity.astype(object).where(identity.notna(),None).to_numpy()
    d['origin_coordinate_location_held']=(r.coordinate_location_held.fillna(False).to_numpy()
        if 'coordinate_location_held' in r else False)
    coordinate_holds=(ref.set_index('source_record_id').coordinate_location_held
        if 'coordinate_location_held' in ref else pd.Series(False,index=ref.source_record_id))
    d['provider_coordinate_location_held']=d.provider_settlement_id.map(coordinate_holds).fillna(False).astype(bool)
    invalid=d.provider_settlement_id.notna()&~d.provider_settlement_id.isin(ref.source_record_id)
    if invalid.any():raise ValueError('Provider settlement identity is absent from reference')
    d['provider_site_id']=get(raw,['provider_site_id','selected_provider_id','provider_id']).to_numpy()
    d['source_route_service_code']=get(raw,['service_code']).to_numpy()
    d['provider_lat']=pd.to_numeric(get(raw,['provider_lat','selected_provider_site_lat']),errors='coerce').to_numpy()
    d['provider_lon']=pd.to_numeric(get(raw,['provider_lon','selected_provider_site_lon']),errors='coerce').to_numpy()
    d['provider_name']=get(raw,['provider_provider_name','selected_provider_name']).to_numpy()
    d['cost_minutes']=pd.to_numeric(get(raw,['cost_minutes','primary_cost_minutes']),errors='coerce').to_numpy()
    if (d.cost_minutes.notna()&(~np.isfinite(d.cost_minutes)|d.cost_minutes.lt(0))).any():raise ValueError('Invalid finite route cost')
    measured=get(raw,['point_separation_km'])
    d['point_separation_km']=pd.to_numeric(measured,errors='coerce').to_numpy()
    missing=d.point_separation_km.isna()
    d.loc[missing,'point_separation_km']=haversine(d.loc[missing,'origin_lon'],d.loc[missing,'origin_lat'],d.loc[missing,'provider_lon'],d.loc[missing,'provider_lat'])
    if (d.point_separation_km.notna()&(~np.isfinite(d.point_separation_km)|d.point_separation_km.lt(0))).any():raise ValueError('Invalid point separation')
    d['local_service_present']=get(raw,['known_local_supply'],False).fillna(False).astype(bool).to_numpy()
    d['known_local_supply']=d.local_service_present
    d['zero_cost_np_assumption']=get(raw,['zero_cost_np_assumption'],False).fillna(False).astype(bool).to_numpy()
    d['route_status']=get(raw,['route_status'],'unknown').to_numpy()
    d['local_supply_status']=get(raw,['local_supply_status'],'unknown').to_numpy()
    d['origin_road_endpoint_accepted']=get(raw,['road_endpoint_accepted'],False).fillna(False).astype(bool).to_numpy()
    d['provider_identity_known']=d.provider_settlement_id.notna()
    d['origin_provider_np_relation']='unknown_settlement_identity'
    d.loc[d.provider_settlement_id.notna()&d.provider_settlement_id.ne(d.origin_id),'origin_provider_np_relation']='confirmed_external_np_identity'
    d.loc[d.local_service_present|d.provider_settlement_id.eq(d.origin_id),'origin_provider_np_relation']='known_local_service_at_np_scale'
    d['external_np_identity_proven']=d.origin_provider_np_relation.eq('confirmed_external_np_identity')
    for target,names in {
        'evidence_quality':['evidence_quality','provider_evidence_quality'],
        'provider_np_identity_basis':['provider_np_identity_basis'],
        'provider_identity_evidence_tier':['provider_identity_evidence_tier'],
        'provider_cartographic_identity_status':['provider_cartographic_identity_status'],
        'provider_cartographic_source_wof_id':['provider_cartographic_source_wof_id'],
        'provider_cartographic_source_dataset':['provider_cartographic_source_dataset'],
        'provider_cartographic_source_feature_id':['provider_cartographic_source_feature_id'],
        'provider_cartographic_source_snapshot':['provider_cartographic_source_snapshot'],
        'provider_cartographic_currency':['provider_cartographic_currency'],
        'provider_cartographic_raw_geometry_sha256':['provider_cartographic_raw_geometry_sha256'],
        'provider_cartographic_geometry_identity_resolution':['provider_cartographic_geometry_identity_resolution'],
        'provider_cartographic_nested_mask_census_ids_json':['provider_cartographic_nested_mask_census_ids_json'],
        'provider_cartographic_coordinate_hold_census_ids_json':['provider_cartographic_coordinate_hold_census_ids_json'],
        'provider_cartographic_original_other_positive_census_places':['provider_cartographic_original_other_positive_census_places'],
        'location_precision':['location_precision','provider_location_precision'],
        'source_snapshot':['source_snapshot','provider_source_snapshot'],
        'provider_operator':['provider_operator'],
        'provider_grade_evidence_basis':['provider_grade_evidence_basis'],
        'provider_school_program_evidence_json':['provider_school_program_evidence_json'],
        'provider_supply_status':['provider_supply_status'],
        'provider_inventory_completeness':['provider_inventory_completeness']}.items():
        d[target]=get(raw,names).to_numpy()
    d['source_id']=get(raw,['source_id','provider_source_id']).map(metadata_json).to_numpy()
    d['provider_np_identity_is_cartographic']=d.provider_identity_evidence_tier.eq('dated_cartographic_locality_containment')
    cartographic_external=(d.provider_np_identity_is_cartographic & d.provider_settlement_id.notna()
                           & d.provider_settlement_id.ne(d.origin_id))
    d.loc[cartographic_external,'origin_provider_np_relation']='modelled_external_np_cartographic_identity'
    d.loc[cartographic_external,'external_np_identity_proven']=False
    d['source_year']=get(raw,['source_year','provider_source_year','observation_year']).map(metadata_json).to_numpy()
    # A historical address is useful evidence, but its inclusion must not turn
    # an unverified current operation or public-access scope into a known fact.
    # Preserve absent flags as unknown rather than filling them with False.
    for name in ['historical_supply_needs_current_confirmation',
                 'historical_supply_proxy','historical_source_only',
                 'saratov_historical_2021_evidence_present',
                 'restriction_scope_unknown','actual_operational_status_verified',
                 'actual_operational_status_checked','source_status_semantics_verified',
                 'source_public_scope_check','medical_need_scope','education_need_scope','programme_mismatch_reason',
                 'general_adult_profile_evidence','named_child_only_contingent',
                 'universal_hospital_suitability_verified']:
        d['provider_'+name]=get(raw,['provider_'+name,name]).to_numpy()
    d['provider_grades_known']=get(raw,['provider_grades_known'],False).fillna(False).astype(bool).to_numpy()
    d['known_offer_records']=pd.to_numeric(get(raw,['known_offer_records','known_provider_sites']),errors='coerce').to_numpy()
    d['routable_external_provider_seeds']=pd.to_numeric(get(raw,['routable_external_provider_seeds','routable_known_provider_sites']),errors='coerce').to_numpy()
    d['observed_flow']=False
    d['assignment_established']=False
    d['origin_independence_established']=False
    d['population_or_object_count_used_as_attraction_weight']=False
    d['point_distance_is_not_walking_path_length']=True
    return d


def with_admission(frame,family,raw_code,scenario_id,limit_minutes,rule_kind):
    d=frame.copy()
    if raw_code=='parcel_pickup_wildberries_current':
        known_operator=d.provider_operator.notna()&d.provider_operator.astype('string').str.strip().ne('')
        wb=d.provider_operator.astype('string').str.contains(r'wildberries|вайлдберриз|^wb$',case=False,regex=True,na=False)
        if (d.provider_site_id.notna()&known_operator&~wb).any():raise ValueError('Non-Wildberries operator in the Wildberries-specific channel')
    d['service_family']=family;d['source_service_code']=raw_code;d['scenario_id']=scenario_id
    d['admission_limit_minutes']=float(limit_minutes)
    known=d.provider_site_id.notna()
    finite=d.cost_minutes.notna()&np.isfinite(d.cost_minutes)
    local=d.local_service_present&known
    near=~local&known&finite&d.cost_minutes.le(limit_minutes)
    far=~local&known&finite&d.cost_minutes.gt(limit_minutes)
    d['service_status']='unknown_route_or_inventory'
    d.loc[far,'service_status']='far_known_candidate'
    d.loc[near,'service_status']='near_candidate'
    d.loc[local,'service_status']='local_service_present'
    d['status']=d.service_status
    d['l0_admitted']=local|near
    d['admission_basis']=rule_kind
    d.loc[local,'admission_basis']='known_local_service_np_scale_zero_assumption_not_household_accessibility'
    location_held=(d.get('origin_coordinate_location_held',pd.Series(False,index=d.index)).fillna(False)
                   | d.get('provider_coordinate_location_held',pd.Series(False,index=d.index)).fillna(False))
    d.loc[location_held,'l0_admitted']=False
    d.loc[location_held,'service_status']='held_named_settlement_coordinate_conflict'
    d.loc[location_held,'status']='held_named_settlement_coordinate_conflict'
    d.loc[location_held,'admission_basis']='documented_coordinate_conflict_no_territorial_assignment_or_automatic_relocation'
    d['limit_is_fitted_to_observed_trips']=False
    d['limit_is_current_legal_compliance_test']=False
    d['admission_source_id']=SP42 if family in {'medical_basic','school'} else 'AUTHOR_DAILY_RETAIL_TRAVEL_SENSITIVITY_20261024'
    d['school_stage_unknown']=family=='school'
    if family=='school':d['school_stage_unknown']=~d.provider_grades_known
    d['school_screen_is_programme_eligibility_proof']=False
    d['school_car_cost_is_proxy_not_measured_school_bus_time']=family=='school'
    d['dated_rural_transport_reference_transferred_as_national_sensitivity']=family in {'medical_basic','school'}
    d['parcel_operator_scope']='Wildberries_only' if raw_code=='parcel_pickup_wildberries_current' else 'Yandex_Market_published_partner_network_only' if raw_code=='parcel_pickup_yandex_current' else 'mixed_mapped_operators_no_interoperability_proof' if family=='parcel_pickup' else None
    d['pickup_operators_are_interchangeable']=False
    d['unknown_reason']=None
    unknown=d.service_status.eq('unknown_route_or_inventory')
    d.loc[unknown,'unknown_reason']='no_directed_route_or_selected_provider_unknown'
    d.loc[unknown&d.routable_external_provider_seeds.eq(0),'unknown_reason']='no_routable_known_provider_seed'
    d.loc[unknown&d.known_offer_records.eq(0),'unknown_reason']='no_known_provider_in_inventory_not_proven_absence'
    d.loc[unknown&~d.origin_road_endpoint_accepted,'unknown_reason']='origin_road_endpoint_unavailable_other_modes_unknown'
    d.loc[location_held,'unknown_reason']='documented_source_coordinate_conflict_actual_location_unresolved_no_relocation'
    d['far_or_unknown_does_not_prove_absence_of_external_dependency']=True
    return d


def settlement_status(frame):
    raw=frame.settlement_type_2021.fillna('').astype(str).str.strip().str.lower().str.replace('ё','е',regex=False)
    urban={x.replace('ё','е') for x in URBAN_TYPES};rural={x.replace('ё','е') for x in RURAL_TYPES}
    status=pd.Series('unknown_formal_settlement_status',index=frame.index)
    status.loc[raw.isin(urban)]='urban_formal_type'
    status.loc[raw.isin(rural)]='rural_formal_type'
    status.loc[frame.origin_id.isin(FEDERAL_CONTEXT_IDS)]='urban_named_federal_city_context'
    return status


def spatial_diagnostic(frame,family,raw_code,scenario_id,rural_m,urban_m):
    d=frame.copy();d['service_family']=family;d['source_service_code']=raw_code;d['scenario_id']=scenario_id
    d['formal_urban_rural_status']=settlement_status(d)
    d['necessary_point_distance_limit_m']=np.nan
    d.loc[d.formal_urban_rural_status.eq('rural_formal_type'),'necessary_point_distance_limit_m']=float(rural_m)
    d.loc[d.formal_urban_rural_status.str.startswith('urban_'),'necessary_point_distance_limit_m']=float(urban_m)
    tested=d.point_separation_km.notna()&d.necessary_point_distance_limit_m.notna()&d.provider_site_id.notna()
    d['necessary_spatial_condition_met']=pd.Series(pd.NA,index=d.index,dtype='boolean')
    d.loc[tested,'necessary_spatial_condition_met']=d.loc[tested,'point_separation_km']*1000<=d.loc[tested,'necessary_point_distance_limit_m']
    d['admission_basis']='dated_SP42_point_separation_necessary_condition_not_walking_route_or_sufficient_access'
    d['admission_source_id']=SP42;d['is_l0_construction_scenario']=False
    d['walking_access_established']=False;d['walking_route_computed']=False
    d['car_minutes_used_as_walking_minutes']=False
    d['urban_building_form_known']=False
    d['urban_limit_is_conditional_upper_envelope']=family=='grocery'
    d['local_presence_not_tested_as_every_households_walk']=d.local_service_present
    return d


def run(routes_dir,reference_path,output,scenario_ids=None,wb_nearest_path=None,medical_nearest_path=None,yandex_nearest_path=None,grocery_nearest_path=None):
    routes_dir=Path(routes_dir);output=Path(output)
    scenario_ids=list(scenario_ids) if scenario_ids is not None else [*DEFAULT_SCENARIOS,*(['daily_20_school30_yandex'] if yandex_nearest_path else [])]
    if not set(scenario_ids)<=set(SCENARIOS):raise ValueError('Unknown construction scenario')
    def code_for(family,config):return config.get('parcel_raw_code',RAW_CODES[family]) if family=='parcel_pickup' else RAW_CODES[family]
    required={code_for(f,SCENARIOS[sid]) for sid in scenario_ids for f in SCENARIOS[sid]['families']}
    paths={code:Path(wb_nearest_path) if code=='parcel_pickup_wildberries_current' and wb_nearest_path else routes_dir/(code+'.parquet') for code in required}
    if medical_nearest_path and 'medical_basic_primary' in required:
        paths['medical_basic_primary']=Path(medical_nearest_path)
    if yandex_nearest_path and 'parcel_pickup_yandex_current' in required:
        paths['parcel_pickup_yandex_current']=Path(yandex_nearest_path)
    if grocery_nearest_path and 'daily_grocery' in required:
        paths['daily_grocery']=Path(grocery_nearest_path)
    missing=[str(paths[code]) for code in sorted(required) if not paths[code].is_file()]
    if missing:raise FileNotFoundError('Required raw nearest layers absent: '+repr(missing))
    reference=pd.read_parquet(reference_path)
    frames={};inputs={str(reference_path):digest(reference_path)}
    optional={'preschool','parcel_pickup'}
    for code in sorted(required|{x for x in optional if (routes_dir/(x+'.parquet')).is_file()}):
        path=paths.get(code,routes_dir/(code+'.parquet'));before=digest(path)
        raw=pd.read_parquet(path)
        if 'service_code' in raw:
            declared=set(raw.service_code.dropna())
            explicit_grocery_union=(code=='daily_grocery' and grocery_nearest_path is not None
                                    and declared=={'daily_grocery_evidence_union'})
            if declared!={code} and not explicit_grocery_union:
                raise ValueError('Raw service code disagrees with layer filename: '+code)
        frames[code]=canonical(raw,reference)
        if before!=digest(path):raise RuntimeError('Input route layer changed while reading: '+str(path))
        inputs[str(path)]=before
    edges=[];scenario_meta={}
    for sid in scenario_ids:
        config=SCENARIOS[sid];scenario_meta[sid]={
            'role':config['role'],'expected_families':config['families'],'core_families':CORE_FAMILIES,
            'family_limits_minutes':{f:30. if f=='medical_basic' else config['school_minutes'] if f=='school' else config['retail_minutes'] for f in config['families']},
            'parcel_scope':config.get('parcel_scope','Wildberries_only') if 'parcel_pickup' in config['families'] else 'not_used'}
        for family in config['families']:
            limit=scenario_meta[sid]['family_limits_minutes'][family]
            kind='dated_SP42_rural_primary_care_transport_scenario' if family=='medical_basic' else 'dated_SP42_general_school_transport_stage_unknown_scenario' if family=='school' else 'author_selected_car_minutes_sensitivity_not_regulation_or_empirical_trip_fit'
            code=code_for(family,config)
            edges.append(with_admission(frames[code],family,code,sid,limit,kind))
    result=pd.concat(edges,ignore_index=True)
    if result.duplicated(['scenario_id','service_family','origin_id']).any():raise ValueError('Repeated scenario/family/origin')
    if result.l0_admitted.ne(result.service_status.isin(['local_service_present','near_candidate'])).any():raise ValueError('Admission/status inconsistency')
    diagnostics=[]
    if 'preschool' in frames:
        diagnostics.append(spatial_diagnostic(frames['preschool'],'preschool','preschool','diagnostic_preschool_spatial_necessary_300_500m',500,300))
    if 'daily_grocery' in frames:
        diagnostics.append(spatial_diagnostic(frames['daily_grocery'],'grocery','daily_grocery','diagnostic_grocery_spatial_necessary_800_2000m',2000,800))
    output.mkdir(parents=True,exist_ok=True)
    result.to_parquet(output/'daily_edges.parquet',index=False,compression='zstd')
    if diagnostics:pd.concat(diagnostics,ignore_index=True).to_parquet(output/'distance_diagnostics.parquet',index=False,compression='zstd')
    if 'parcel_pickup' in frames:
        alternative=with_admission(frames['parcel_pickup'],'parcel_pickup','parcel_pickup','diagnostic_mixed_operator_pickup_20min',20,
            'author_mixed_operator_access_sensitivity_no_parcel_operator_interchangeability_proof')
        alternative['is_l0_construction_scenario']=False
        alternative.to_parquet(output/'mixed_operator_pickup_alternative.parquet',index=False,compression='zstd')
    counts=result.groupby(['scenario_id','service_family','service_status']).size().rename('origin_records').reset_index()
    counts.to_parquet(output/'scenario_status_counts.parquet',index=False,compression='zstd')
    counts.to_csv(output/'scenario_status_counts.csv',index=False)
    summary={'main_scenario':'daily_20_school30_wb' if 'daily_20_school30_wb' in scenario_ids else None,
        'scenarios':scenario_meta,'ordinary_and_context_analysis_origins':int(result.origin_id.nunique()),
        'construction_outcome_rows':len(result),'status_counts':counts.to_dict('records'),
        'diagnostic_scenarios_are_not_required_core_functions':True,
        'raw_long_distance_and_unknown_route_outcomes_retained':True,
        'no_route_is_not_evidence_of_independence':True,
        'all_limits_are_scenarios_not_observed_flow_boundaries':True,
        'retail_and_pickup_minutes_are_author_sensitivity_not_SP42_norms':True,
        'grocery_spatial_urban_800m_conditional_upper_envelope_rural_2000m':True,
        'grocery_spatial_and_preschool_diagnostics_not_walking_routes':True,
        'normative_source':{'source_id':SP42,'sha256':SP42_SHA256,
            'medical_locator':'SP42.13330.2016 dated webcopy2024 table10.1 footnote**, PDF38: rural polyclinics/ambulatory/FAP/pharmacy transport30min',
            'school_locator':'Section10.5 table10.3 PDF38–39: rural primary15min/basic+secondary30min; designated school transport conditions, not private-car measurements',
            'spatial_locator':'Sections10.3–10.4 table10.1 PDF37–38: local retail urban500/800m by housing form, rural2000m; preschool urban300/rural500m'},
        'source_input_sha256':inputs,'code_sha256':digest(Path(__file__))}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'origins':summary['ordinary_and_context_analysis_origins'],'rows':len(result),'scenarios':scenario_ids},ensure_ascii=False))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--routes',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scenarios',nargs='+',choices=list(SCENARIOS))
    p.add_argument('--wb-nearest',type=Path,help='Separate frozen fresh Wildberries layer; never substitute the generic mixed-operator file')
    p.add_argument('--medical-nearest',type=Path,help='Separate corrected frozen basic-medical layer; preserves the older raw scenario')
    p.add_argument('--yandex-nearest',type=Path,help='Separate frozen Yandex Market network adds an optional operator scenario; does not replace main Wildberries')
    p.add_argument('--grocery-nearest',type=Path,help='Auditable nearest union of dated grocery evidence; raw source layers remain separate')
    a=p.parse_args();run(a.routes,a.reference,a.output,a.scenarios,a.wb_nearest,a.medical_nearest,a.yandex_nearest,a.grocery_nearest)

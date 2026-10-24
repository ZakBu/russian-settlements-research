#!/usr/bin/env python3
"""Describe known functions inside already formed systems; never assign a rank.

Counts refer to deduplicated registered care-address IDs / mapped education
features. They are positive source witnesses, not capacities, buildings, flows,
complete inventories or an input to spatial assignment. Missing evidence is
explicitly unresolved. Population, distance and merge depth are not features.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import duckdb
import pandas as pd


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def describe_systems(members, medical, education, commerce=None):
    """Return every formed unit plus a positive-evidence source audit.

    Input medical rows retain exact UIDSPMO+IDADDRESS and clinical scope; no
    medical profile is copied to other addresses or settlement neighbours.
    Education/commerce require an already accepted literal NP identity.
    """
    keys=['scenario_id','origin_id']
    if members[keys].isna().any().any() or members.unit_id.isna().any():
        raise ValueError('Formed membership identity must be explicit')
    if members.duplicated(keys).any():
        raise ValueError('Formed units must partition member origins per scenario')
    need=['UIDSPMO','IDADDRESS','service_code','source_record_id','np_identity_accepted','medical_need_scope','named_child_only_contingent','general_adult_profile_evidence','restriction_scope_unknown']
    if not set(need).issubset(medical):raise ValueError('Medical source lacks exact address/profile/scope evidence')
    med=medical.loc[medical.np_identity_accepted.eq(True)&medical.source_record_id.notna()].copy()
    conflict_ids=set(med.groupby('IDADDRESS').source_record_id.nunique().loc[lambda s:s.gt(1)].index)
    med['address_np_identity_conflict']=med.IDADDRESS.isin(conflict_ids)
    need=need+['address_np_identity_conflict']
    if med[['UIDSPMO','IDADDRESS']].isna().any().any():raise ValueError('Accepted medical evidence lacks exact address key')
    edu=education.loc[education.eligible_site_supply.eq(True)&education.source_record_id.notna()&education.supply_status.eq('observed')].copy()
    con=duckdb.connect();con.execute("SET memory_limit='1GB'")
    con.register('membership',members[['scenario_id','unit_id','origin_id']])
    con.register('medical',med[need])
    edu_cols=['source_record_id','provider_id','service_code','grades_known']
    con.register('education',edu[edu_cols])
    # One care site may have many services/profiles and one subdivision may
    # operate at several sites. Count each concept separately.
    medsum=con.execute("""SELECT m.scenario_id,m.unit_id,
      count(DISTINCT e.IDADDRESS) AS medical_registered_care_address_ids_known,
      count(DISTINCT e.UIDSPMO) AS medical_registered_subdivisions_known,
      count(DISTINCT e.IDADDRESS) FILTER(WHERE e.address_np_identity_conflict) AS medical_care_address_ids_with_np_conflicts_known,
      count(DISTINCT (e.UIDSPMO,e.IDADDRESS)) AS medical_subdivision_address_pairs_known,
      count(DISTINCT e.medical_need_scope) AS medical_profile_breadth_known,
      count(DISTINCT e.service_code) AS medical_service_channels_known,
      count(DISTINCT e.IDADDRESS) FILTER(WHERE e.service_code IN ('medical_basic_primary','medical_physician_primary')) AS medical_primary_care_address_ids_known,
      count(DISTINCT e.IDADDRESS) FILTER(WHERE e.service_code NOT IN ('medical_basic_primary','medical_physician_primary')) AS medical_nonprimary_function_address_ids_known,
      count(DISTINCT e.IDADDRESS) FILTER(WHERE e.named_child_only_contingent) AS medical_child_only_care_address_ids_known,
      count(DISTINCT e.IDADDRESS) FILTER(WHERE e.general_adult_profile_evidence) AS medical_general_adult_care_address_ids_known,
      count(DISTINCT e.IDADDRESS) FILTER(WHERE e.restriction_scope_unknown) AS medical_unknown_operator_scope_address_ids_known,
      to_json(list(DISTINCT e.medical_need_scope ORDER BY e.medical_need_scope)) AS medical_need_scopes_json,
      to_json(list(DISTINCT e.service_code ORDER BY e.service_code)) AS medical_service_codes_json,
      to_json(list(DISTINCT struct_pack(profile:=e.medical_need_scope,child_only:=e.named_child_only_contingent,general_adult:=e.general_adult_profile_evidence,operator_scope_unknown:=e.restriction_scope_unknown))) AS medical_age_and_sex_scope_evidence_json
      FROM membership m JOIN medical e ON m.origin_id=e.source_record_id GROUP BY m.scenario_id,m.unit_id""").df()
    # DISTINCT aggregate order is unspecified (and may vary with DuckDB's
    # parallel execution). Canonicalise structured scope witnesses so repeated
    # runs retain identical semantics and bytes.
    scope_column='medical_age_and_sex_scope_evidence_json'
    medsum[scope_column]=medsum[scope_column].map(lambda value:json.dumps(
        sorted(json.loads(value),key=lambda row:json.dumps(row,ensure_ascii=False,sort_keys=True)),
        ensure_ascii=False,separators=(',',':')))
    edusum=con.execute("""SELECT m.scenario_id,m.unit_id,
      count(DISTINCT e.provider_id) AS education_mapped_features_known,
      count(DISTINCT e.service_code) AS education_service_channels_known,
      count(DISTINCT e.provider_id) FILTER(WHERE e.service_code='preschool') AS education_preschool_features_known,
      count(DISTINCT e.provider_id) FILTER(WHERE e.service_code='school_general') AS education_school_features_known,
      count(DISTINCT e.provider_id) FILTER(WHERE e.service_code='school_general' AND e.grades_known) AS education_school_features_with_literal_stage_evidence,
      count(DISTINCT e.provider_id) FILTER(WHERE e.service_code='vocational_education') AS education_vocational_features_known,
      count(DISTINCT e.provider_id) FILTER(WHERE e.service_code='higher_education') AS education_higher_features_known,
      to_json(list(DISTINCT e.service_code ORDER BY e.service_code)) AS education_service_codes_json
      FROM membership m JOIN education e ON m.origin_id=e.source_record_id GROUP BY m.scenario_id,m.unit_id""").df()
    out=members.groupby(['scenario_id','unit_id'],sort=False).size().rename('member_np_records').reset_index()
    for data in [medsum,edusum]:out=out.merge(data,on=['scenario_id','unit_id'],how='left',validate='one_to_one')
    audit={'medical_source_rows':len(medical),'medical_accepted_np_evidence_rows':len(med),
      'medical_unique_accepted_care_address_ids':med.IDADDRESS.nunique(),
      'medical_care_address_ids_with_conflicting_np_identity':len(conflict_ids),
      'medical_source_years':sorted(set(str(x) for x in medical.source_year.dropna())) if 'source_year' in medical else ['not_provided'],
      'education_source_years':sorted(set(str(x) for x in education.source_year.dropna())) if 'source_year' in education else ['not_provided'],
      'education_source_features':len(education),'education_observed_eligible_features':int(education.eligible_site_supply.eq(True).sum()),
      'education_observed_features_with_accepted_np':len(edu),
      'education_np_identity_observed_share':len(edu)/max(1,int(education.eligible_site_supply.eq(True).sum())),
      'clustering_or_functional_rank_attempted':False,
      'reason_no_rank':'Source-specific NP identification and inventory completeness are unequal; no comparable negative inventories or validated capacity measurements.',
      'population_used':False,'radii_used':False,'merge_depth_used_as_functional_rank':False,'assignment_modified':False}
    if commerce is not None:
        # This optional source is the selected fresh WB channel. Historical
        # grocery inventories must not silently become current 2026 counts.
        comm=commerce.loc[commerce.source_record_id.notna()&commerce.supply_status.eq('observed')&commerce.service_code.eq('parcel_pickup_wildberries_current')].copy()
        con.register('commerce',comm[['source_record_id','provider_id']])
        cmsum=con.execute("""SELECT m.scenario_id,m.unit_id,count(DISTINCT c.provider_id) AS wildberries_2026_mapped_pickup_features_known FROM membership m JOIN commerce c ON m.origin_id=c.source_record_id GROUP BY m.scenario_id,m.unit_id""").df()
        out=out.merge(cmsum,on=['scenario_id','unit_id'],how='left',validate='one_to_one')
        audit.update(wildberries_source_features=len(commerce),wildberries_observed_features_with_accepted_np=len(comm))
    count_cols=[c for c in out if c.endswith('_known') or c=='education_school_features_with_literal_stage_evidence']
    for c in count_cols:out[c]=out[c].fillna(0).astype('int64')
    for c in out:
        if c.endswith('_json'):out[c]=out[c].fillna('[]')
    medical_positive=out.medical_registered_care_address_ids_known.gt(0)
    education_positive=out.education_mapped_features_known.gt(0)
    out['functional_evidence_quality_class']='insufficient_multidomain_records'
    out.loc[medical_positive&~education_positive,'functional_evidence_quality_class']='medical_positive_education_inventory_unresolved'
    out.loc[~medical_positive&education_positive,'functional_evidence_quality_class']='education_positive_medical_inventory_unresolved'
    out.loc[medical_positive&education_positive,'functional_evidence_quality_class']='multidomain_positive_inventory_still_incomplete'
    primary=out.medical_primary_care_address_ids_known.gt(0)|out.education_school_features_known.gt(0)|out.education_preschool_features_known.gt(0)
    higher=out.medical_nonprimary_function_address_ids_known.gt(0)|out.education_vocational_features_known.gt(0)|out.education_higher_features_known.gt(0)
    out['functional_descriptor']='no_supported_functional_description'
    out.loc[primary&~higher,'functional_descriptor']='known_daily_functions_higher_inventory_unresolved'
    out.loc[~primary&higher,'functional_descriptor']='known_nonprimary_functions_daily_inventory_unresolved'
    out.loc[primary&higher,'functional_descriptor']='known_daily_and_nonprimary_functions'
    if 'wildberries_2026_mapped_pickup_features_known' in out:
        out.loc[~primary&~higher&out.wildberries_2026_mapped_pickup_features_known.gt(0),'functional_descriptor']='known_operator_pickup_other_functions_unresolved'
    out['counts_mean_positive_source_witnesses_not_complete_inventory']=True
    out['zero_means_no_accepted_source_record_not_physical_absence']=True
    out['medical_addresses_are_registry_ids_not_hospital_or_building_counts']=True
    out['complete_institution_inventory_established']=False
    out['functional_rank_established']=False
    out['source_comparability_for_clustering_established']=False
    out['universal_hospital_suitability_verified']=False
    out['functional_description_changes_assignment']=False
    out['observed_flow']=False
    con.close()
    return out,audit


def city_reference_examples(ref):
    # Homonymous villages named Moscow/Engels are not these city examples.
    pairs={('москва','москва'),('санкт-петербург','санкт петербург'),('саратов','саратовская'),('энгельс','саратовская')}
    mask=pd.Series([(str(n).lower(),str(r)) in pairs for n,r in zip(ref['name'],ref['region'])],index=ref.index)
    return ref.loc[mask & ref.source_record_id.notna() & ref.settlement_type_2021.eq('город')].copy()


def education_external_boundary_examples(education, polygons, cities):
    """Count mapped features by coordinates in a published comparison polygon.

    This is a separate observation footprint, not ownership by a settlement,
    an extension of a formed unit, or a new delimitation of its influence.
    Saratov and Engels can consequently have the same comparison polygon.
    """
    try:
        from .logic_checks import locate_external_fua_points
    except ImportError:
        from logic_checks import locate_external_fua_points
    edu=education.loc[education.eligible_site_supply.eq(True)&education.supply_status.eq('observed')].copy()
    points=edu[['provider_id','site_lat','site_lon']].rename(columns={'provider_id':'point_key','site_lat':'lat','site_lon':'lon'})
    links,status=locate_external_fua_points(points,polygons)
    city_points=cities[['source_record_id','lat','lon']].rename(columns={'source_record_id':'point_key'})
    city_links,city_status=locate_external_fua_points(city_points,polygons)
    observations=edu.merge(links,left_on='provider_id',right_on='point_key',how='inner',validate='many_to_many')
    rows=[]
    for city in cities.itertuples(index=False):
        matches=city_links.loc[city_links.point_key.eq(city.source_record_id),'eFUA_ID'].drop_duplicates()
        item={'name':city.name,'source_record_id':city.source_record_id,
              'external_boundary_matches':len(matches),'external_boundary_epoch':2015,
              'physical_features_observation_year':2026,
              'counts_are_inside_external_polygon_not_owned_by_city':True,
              'external_polygon_is_formed_system':False,'functional_rank_established':False}
        if len(matches)==1:
            identifier=matches.iloc[0]
            group=observations[observations.eFUA_ID.eq(identifier)]
            item.update(external_efua_id=int(identifier),external_efua_name=str(polygons.set_index('eFUA_ID').loc[identifier,'eFUA_name']),
                        education_mapped_features_known=int(group.provider_id.nunique()),
                        education_mapped_features_np_identity_unresolved=int(group.loc[group.source_record_id.isna(),'provider_id'].nunique()))
            for channel,label in [('school_general','school'),('preschool','preschool'),('vocational_education','vocational'),('higher_education','higher')]:
                item['education_'+label+'_features_known']=int(group.loc[group.service_code.eq(channel),'provider_id'].nunique())
        rows.append(item)
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser()
    for arg in ['memberships','medical-evidence','education-sites','output']:p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--wildberries-sites',type=Path)
    p.add_argument('--reference',type=Path)
    p.add_argument('--external-fua',type=Path,help='Optional published eFUA2015 geometry; separate coordinate-only observation control')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    members=pd.read_parquet(a.memberships)
    out,audit=describe_systems(members,pd.read_parquet(a.medical_evidence),pd.read_parquet(a.education_sites),pd.read_parquet(a.wildberries_sites) if a.wildberries_sites else None)
    out.to_parquet(a.output/'system_functional_descriptors.parquet',index=False)
    audit.update(input_sha256={str(x):sha(x) for x in [a.memberships,a.medical_evidence,a.education_sites,a.wildberries_sites] if x},code_sha256=sha(Path(__file__)),formed_units=len(out))
    if a.reference:
        ref=pd.read_parquet(a.reference,columns=['source_record_id','name','region','settlement_type_2021','lat','lon'])
        city=city_reference_examples(ref)
        examples=city.merge(members,left_on='source_record_id',right_on='origin_id',how='left').merge(out,on=['scenario_id','unit_id'],how='left',validate='many_to_one')
        examples.to_parquet(a.output/'city_member_system_examples.parquet',index=False)
        examples.to_csv(a.output/'city_member_system_examples.csv',index=False)
        audit['reference_sha256']=sha(a.reference)
        if a.external_fua:
            geographic=education_external_boundary_examples(pd.read_parquet(a.education_sites),pd.read_parquet(a.external_fua),city)
            geographic.to_parquet(a.output/'city_external_boundary_education_examples.parquet',index=False)
            geographic.to_csv(a.output/'city_external_boundary_education_examples.csv',index=False)
            audit['external_fua_sha256']=sha(a.external_fua)
    (a.output/'summary.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()

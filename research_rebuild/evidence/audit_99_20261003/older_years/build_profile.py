#!/usr/bin/env python3
"""Reproducible bounded older-year point-coverage profile; candidate evidence only."""
from pathlib import Path
import hashlib, json
import pandas as pd

ROOT=Path('/workspace')
OUT=ROOT/'settlements-work/continuation_20261003/audit_99_20261003/older_years'
F=ROOT/'settlements-delivery/continuation-consolidated-20261003'
SEL=F/'selected_observations.parquet'; PTS=F/'accepted_point_uses.parquet'; EDGES=F/'accepted_identity_edges.parquet'; LEG=F/'legacy_availability_projected_r5.parquet'
HIST=ROOT/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
CONFLICTS=ROOT/'settlements-work/coordinates/accepted_final_v1/additional_legacy_point_conflict_holds.parquet'

class UF:
    def __init__(self): self.p={}
    def find(self,x):
        if x not in self.p:self.p[x]=x
        if self.p[x]!=x:self.p[x]=self.find(self.p[x])
        return self.p[x]
    def union(self,a,b):
        a=self.find(a);b=self.find(b)
        if a!=b:self.p[b]=a

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    r=pd.read_parquet(SEL); p=pd.read_parquet(PTS); e=pd.read_parquet(EDGES); l=pd.read_parquet(LEG); h=pd.read_parquet(HIST)
    accepted=set(p.target_source_record_id.astype(str)); old=r[r.census_year.isin([2002,2010])].copy()
    old=old[~old.source_record_id.astype(str).isin(accepted)].copy()
    # The user-supplied physical-locality residual excludes one 2002 territorial
    # aggregate (St Petersburg federal-city scope) and two 2010 city-total rows
    # (Moscow and St Petersburg). Keep their exclusions explicit and auditable.
    excluded=(old.population_scope.eq('federal_city_region') | (old.census_year.eq(2010)&old.settlement_name.isin(['Москва','Санкт-Петербург'])&old.settlement_type.eq('город')))
    nonphysical=old[excluded].copy(); q=old[~excluded].copy()
    # Verify the audit stratum is exactly the stated known physical residual.
    expected={2002:(36165,19887379),2010:(72676,23683753)}
    observed={int(y):(int(len(g)),int(g.population.sum())) for y,g in q.groupby('census_year')}
    if observed!=expected: raise ValueError(f'physical residual anchor mismatch {observed} != {expected}')

    # Current admitted same_place components and carriers only. Candidate edges
    # do not enter connectivity. The frozen edge table is the current accepted graph.
    uf=UF()
    for z in e[e.relation.eq('same_place')][['from_source_record_id','to_source_record_id']].itertuples(index=False): uf.union(str(z[0]),str(z[1]))
    c={}
    for z in p[p.target_year.eq(2021)][['target_source_record_id','latitude','longitude']].itertuples(index=False):
        root=uf.find(str(z[0])); c.setdefault(root,[]).append((str(z[0]),float(z[1]),float(z[2])))
    q['identity_graph_node']=q.source_record_id.astype(str).isin(uf.p)
    q['accepted_2021_carrier_count']=q.source_record_id.map(lambda x:len(c.get(uf.find(str(x)),[])) if str(x) in uf.p else 0)
    q['accepted_2021_carrier_id']=q.source_record_id.map(lambda x:c[uf.find(str(x))][0][0] if str(x) in uf.p and len(c.get(uf.find(str(x)),[]))==1 else '')

    # R5 means a legacy point claim exists along the projected exact-source route
    # or a retained legacy pointer route; it is availability, not admission.
    l=l[['source_record_id','any_legacy_point_available','settlement_id','legacy_source_record_id_before_publication_binding','legacy_availability_projection_basis']].drop_duplicates('source_record_id')
    q=q.merge(l,on='source_record_id',how='left',validate='one_to_one')
    q['legacy_availability_status']=q.any_legacy_point_available.map(lambda x:'available' if x is True or str(x).lower()=='true' else ('unavailable' if x is False or str(x).lower()=='false' else 'unknown_no_projected_r5_row'))
    q['legacy_point_available']=q.legacy_availability_status.eq('available')
    hc=['source_record_id','historical_named_point_candidate','historical_name_exact','historical_type_exact','historical_code_structure_compatible','historical_key_region_name_type_count','possible_unlocated_historical_competitor','modern_provider_code_matches_historical_code','modern_numeric_provider_code_agrees_historical_code','historical_okato_2009_raw','historical_okato_2011_raw','historical_okato','historical_point_modern_region','latitude_from_lat','longitude_from_long','code_join_basis','source_region_name_type_count','is_additive_settlement_record','population_scope']
    h=h[hc].drop_duplicates('source_record_id')
    q=q.merge(h,on='source_record_id',how='left',validate='one_to_one',suffixes=('','_hist'))
    conflict=pd.read_parquet(CONFLICTS,columns=['target_source_record_id','target_year','coordinate_source','coordinate_source_file','coordinate_source_sha256','coordinate_source_locator'])
    conflict=conflict.drop_duplicates('target_source_record_id').rename(columns={'target_source_record_id':'source_record_id','target_year':'conflict_candidate_year'})
    q=q.merge(conflict,on='source_record_id',how='left',validate='one_to_one')
    for col in ['historical_named_point_candidate','historical_name_exact','historical_type_exact','historical_code_structure_compatible','possible_unlocated_historical_competitor','modern_provider_code_matches_historical_code','modern_numeric_provider_code_agrees_historical_code']:
        q[col]=q[col].fillna(False).astype(bool)
    q['current_carrier_class']=q.accepted_2021_carrier_count.map(lambda n:'one_current_accepted_2021_carrier' if n==1 else ('multiple_current_accepted_2021_carriers_actual_identity_conflict' if n>1 else 'no_current_accepted_2021_carrier_unknown_or_unaccepted_identity'))
    q['historical_candidate_class']=q.apply(lambda x:'exact_named_typed_historical_point_candidate' if x.historical_named_point_candidate else ('name_type_exact_but_soft_or_structural_gate_missing' if x.historical_name_exact and x.historical_type_exact else ('historical_row_present_but_name_type_not_exact' if pd.notna(x.historical_key_region_name_type_count) else 'no_joined_historical_named_row')),axis=1)
    q['exact_raw_code_witness']=q.code_join_basis.eq('exact_raw_code') & q.historical_code_structure_compatible
    q['code_witness_class']=q.apply(lambda x:'provider_OKATO_exact_raw_code_match' if x.modern_provider_code_matches_historical_code else ('provider_OKATO_explicit_numeric_serialization_match' if x.modern_numeric_provider_code_agrees_historical_code else ('dated_raw_exact_code_without_provider_match' if x.exact_raw_code_witness else 'no_confirmed_code_witness')),axis=1)
    q['conflict_or_hold_class']=q.apply(lambda x:'current_legacy_coordinate_conflict_hold_present' if pd.notna(x.conflict_candidate_year) else ('multiple_current_accepted_2021_carriers_identity_conflict' if x.accepted_2021_carrier_count>1 else ('historical_unlocated_competitor_hold' if x.possible_unlocated_historical_competitor else ('historical_key_nonunique_hold' if pd.notna(x.historical_key_region_name_type_count) and x.historical_key_region_name_type_count!=1 else ('historical_candidate_requires_identity_or_soft_metadata_review' if x.historical_named_point_candidate else 'no_actual_conflict_evidenced_in_current_ledgers')))),axis=1)

    dims=['census_year','current_carrier_class','historical_candidate_class','legacy_availability_status','code_witness_class','conflict_or_hold_class']
    profile=q.groupby(dims,dropna=False).agg(rows=('source_record_id','size'),recorded_population=('population','sum'),source_asset_refs=('source_path','count')).reset_index().sort_values(['census_year','rows'],ascending=[True,False])
    # Keep this table compact by removing duplicated detail categories only when zero.
    profile.to_csv(OUT/'current_residual_profile.csv',index=False)
    pri=q.copy(); pri['priority_tier']=pri.apply(lambda x:'P1 reuse existing accepted 2021 carrier; review continuity and census-chain scope' if x.accepted_2021_carrier_count==1 else ('HOLD actual multiple-carrier conflict' if x.accepted_2021_carrier_count>1 else ('P2 review exact historical raw point + exact code/name/type witnesses' if x.historical_named_point_candidate and x.exact_raw_code_witness else ('P3 recover source identity via raw census ID / dated OKATO-OKTMO / publication crosswalk' if x.legacy_point_available or x.exact_raw_code_witness else 'P4 unresolved identity and coordinate route; check source completeness'))),axis=1)
    pcols=['priority_tier','source_record_id','census_year','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','source_file','source_row','source_native_id','source_name_raw','source_population_raw','oktmo','okato','legacy_point_available','legacy_availability_projection_basis','legacy_source_record_id_before_publication_binding','accepted_2021_carrier_count','accepted_2021_carrier_id','historical_named_point_candidate','historical_name_exact','historical_type_exact','historical_code_structure_compatible','historical_key_region_name_type_count','possible_unlocated_historical_competitor','historical_okato_2009_raw','historical_okato_2011_raw','historical_okato','code_join_basis','modern_provider_code_matches_historical_code','modern_numeric_provider_code_agrees_historical_code','source_region_name_type_count','is_additive_settlement_record']
    tier_order={'P1 reuse existing accepted 2021 carrier; review continuity and census-chain scope':1,'P2 review exact historical raw point + exact code/name/type witnesses':2,'P3 recover source identity via raw census ID / dated OKATO-OKTMO / publication crosswalk':3,'P4 unresolved identity and coordinate route; check source completeness':4,'HOLD actual multiple-carrier conflict':5}
    pri['_tier']=pri.priority_tier.map(tier_order).fillna(9)
    pri.sort_values(['_tier','population'],ascending=[True,False])[pcols].to_csv(OUT/'current_candidate_priorities.csv',index=False)
    # Excluded records recorded for transparent agreement with supplied anchors.
    nonphysical[['source_record_id','census_year','settlement_name','settlement_type','region_raw','population_scope','population']].to_csv(OUT/'excluded_nonphysical_rows.csv',index=False)
    counts=[]
    for y,g in q.groupby('census_year'):
        counts.append({'year':int(y),'physical_missing_point_rows':int(len(g)),'physical_missing_point_population':int(g.population.sum()),
            'legacy_route_available_rows':int(g.legacy_point_available.sum()),'legacy_route_available_population':int(g.loc[g.legacy_point_available,'population'].sum()),
            'legacy_route_unavailable_rows':int(g.legacy_availability_status.eq('unavailable').sum()),'legacy_route_unknown_rows':int(g.legacy_availability_status.eq('unknown_no_projected_r5_row').sum()),
            'exact_historical_point_candidates':int(g.historical_named_point_candidate.sum()),'exact_historical_candidate_population':int(g.loc[g.historical_named_point_candidate,'population'].sum()),
            'one_current_accepted_2021_carrier_rows':int(g.accepted_2021_carrier_count.eq(1).sum()),'one_carrier_population':int(g.loc[g.accepted_2021_carrier_count.eq(1),'population'].sum()),
            'multiple_current_accepted_2021_carriers_rows':int(g.accepted_2021_carrier_count.gt(1).sum()),'multiple_carrier_population':int(g.loc[g.accepted_2021_carrier_count.gt(1),'population'].sum()),
            'historical_exact_code_witness_rows':int(g.exact_raw_code_witness.sum()),'historical_provider_code_exact_or_numeric_match_rows':int((g.modern_provider_code_matches_historical_code|g.modern_numeric_provider_code_agrees_historical_code).sum()),
            'possible_unlocated_historical_competitor_rows':int(g.possible_unlocated_historical_competitor.sum()),'current_legacy_coordinate_conflict_hold_rows':int(g.conflict_candidate_year.notna().sum()),
            'missing_legacy_and_no_historical_candidate_rows':int((~g.legacy_point_available & ~g.historical_named_point_candidate).sum())})
    summary={'status':'bounded_current_candidate_profile_no_admissions','frozen_delivery':str(F),'current_files':{str(z):sha(z) for z in [SEL,PTS,EDGES,LEG]},'candidate_evidence':{str(HIST):sha(HIST)},'physical_population_anchor':{str(k):{'rows':v[0],'population':v[1]} for k,v in expected.items()},'observed_physical_population_anchor':{str(k):{'rows':v[0],'population':v[1]} for k,v in observed.items()},'excluded_rows':nonphysical[['source_record_id','census_year','settlement_name','population']].to_dict('records'),'year_profiles':counts,'source_identifier_profile':{str(y):{'rows':int(len(g)),'source_native_id_nonnull':int(g.source_native_id.notna().sum()),'source_native_id_distinct':int(g.source_native_id.nunique()),'selected_okato_nonnull':int(g.okato.notna().sum()),'selected_oktmo_nonnull':int(g.oktmo.notna().sum()),'source_path_nonnull':int(g.source_path.notna().sum()),'source_sha256_nonnull':int(g.source_sha256.notna().sum()),'source_locator_nonnull':int(g.source_locator.notna().sum())} for y,g in q.groupby('census_year')},'definitions':{'legacy_route_available':'R5 projected legacy point availability; indicates a coordinate inventory route, not point admission or same-location identity','legacy_route_unknown':'source row absent from R5 projection; not treated as unavailable','exact_historical_point_candidate':'v4 unique regional typed raw 2009/2011 classifier/GeoKLADR join with exact name and type, explicit source additive row, and no known unlocated competitor; candidate only','actual_conflict':'multiple distinct currently accepted 2021 point carriers in a connected accepted same_place component; candidate disagreement and soft metadata gaps are reported separately','raw_source_codes':'all source OKATO/OKTMO values are preserved as literal strings; no padding or reserialization is applied by this audit'},'runtime_seconds':None}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'physical_anchor':observed,'year_profiles':counts},ensure_ascii=False))
if __name__=='__main__': main()

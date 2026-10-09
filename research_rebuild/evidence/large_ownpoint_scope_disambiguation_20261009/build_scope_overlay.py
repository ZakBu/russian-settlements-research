from pathlib import Path
from hashlib import sha256
import json
import pandas as pd

ROOT = Path('/workspace/russian-settlements-research/research_rebuild/evidence')
ZONE = ROOT / 'large_existing_credit_missing_ownpoint_20261009'
OUT = ROOT / 'large_ownpoint_scope_disambiguation_20261009'
RAWROOT = Path('/workspace/settlements-raw')

def raw_sha(path):
    if not isinstance(path, str) or not path:
        return ''
    p = RAWROOT / path
    if not p.is_file():
        return ''
    return sha256(p.read_bytes()).hexdigest()
roster = pd.read_csv(ZONE / 'all_raw_or_primary_over1000_without_State_ownpoint.csv', low_memory=False)
classified = pd.read_csv(ZONE / 'classified_missing_ownpoint_inventory.csv', low_memory=False)
parts = classified[classified.literal_part_label.fillna(False).astype(bool)].copy()
parts = parts.merge(roster[['source_record_id','population','settlement_name','settlement_type','region_norm','district_raw','source_file','source_sha256','source_locator']], on='source_record_id', how='left', suffixes=('_classified','_roster'), validate='one_to_one')
# Use the exact frozen Stage68 component and credited-UID ledgers as an audit axis.
stage68 = ROOT / 'main_axis_residual_application68_20261008'
components = pd.read_csv(stage68 / 'applied_component_snapshot.csv.gz', low_memory=False)
credited = pd.read_csv(stage68 / 'applied_primary_credited_UID_roster.csv.gz', usecols=['source_record_id'], low_memory=False)
parts = parts.merge(components[['source_record_id','root','has_own_point']].rename(columns={'root':'stage68_component_root','has_own_point':'stage68_has_own_point'}), on='source_record_id', how='left', validate='one_to_one')
parts = parts.merge(credited.assign(stage68_primary_uid_credited=True), on='source_record_id', how='left', validate='one_to_one')
parts['stage68_primary_uid_credited'] = parts['stage68_primary_uid_credited'].fillna(False)
# Final Stage70 typed associations are evidence pointers only, not new identity edges or point claims.
assoc = pd.read_csv(ROOT / 'main_axis_residual_application70_batch16_20261009' / 'accepted_typed_joint_reporting_scope_spatial_associations.csv', low_memory=False)
assoc = assoc[['scope_id','source_record_id','joint_ownpoint_carrier','spatial_association_kind','historic_part_exact_coordinate','ordinary_identity_edge_or_population_equivalence_asserted','source_count_or_quality_changed']].drop_duplicates()
assoc = assoc.rename(columns={'joint_ownpoint_carrier':'existing_joint_scope_carrier'})
parts = parts.merge(assoc, on='source_record_id', how='left', validate='one_to_one')
parts['review_class'] = 'literal_publisher_part_row'
parts['whole_named_NP_ownpoint_target'] = False
parts['completion_exclusion_reason'] = parts.apply(lambda r: ('Literal source label includes part/часть; keep this source UID and population as a part-level observation. It is not an independently named whole-NP point target.' + (' Existing Stage70 coarse typed scope association is '+str(r.scope_id)+'; exact historic part coordinate remains '+str(r.historic_part_exact_coordinate)+'.' if pd.notna(r.get('scope_id')) else ' No exact Stage70 whole-locality scope carrier row was found for this UID; do not infer a recipient or part point.')), axis=1)
parts['raw_population_retained_unchanged'] = True
parts['population_allocated_or_removed'] = False
parts['ordinary_identity_or_population_equivalence_asserted'] = False
parts['source_record_status'] = 'retained_source_uid; scope_overlay_only'
parts['verified_raw_source_sha256'] = parts.source_file_roster.map(raw_sha)
parts['source_record_locator_exact'] = parts.source_record_id
keep = ['source_record_id','census_year','settlement_name_roster','settlement_type_roster','region_norm_roster','district_raw_roster','population_roster','source_file_roster','verified_raw_source_sha256','source_record_locator_exact','review_class','whole_named_NP_ownpoint_target','completion_exclusion_reason','raw_population_retained_unchanged','population_allocated_or_removed','stage68_component_root','stage68_has_own_point','stage68_primary_uid_credited','scope_id','existing_joint_scope_carrier','spatial_association_kind','historic_part_exact_coordinate','ordinary_identity_edge_or_population_equivalence_asserted','source_count_or_quality_changed','source_record_status']
# Add source axis aliases for clean stable output.
parts = parts.rename(columns={'settlement_name_roster':'settlement_name_roster'})
# pandas suffixes create these exact fields for roster values
parts[keep].to_csv(OUT / 'literal_part_scope_overlay.csv', index=False)

# Additional explicitly scoped rows in this 223-UID universe: one admin aggregate,
# one partial-urban rural count, and four federal-territory aggregates.
extra_ids = {
 '2002:065_392a5859cb_Xakasia.xls:Sheet1:383': ('administrative_aggregate','municipal council aggregate; source header total, not a settlement NP'),
 '2002:074_44f6c88636_Omskaja.xls:Sheet1:1404': ('partial_settlement_population_scope','rural part of a pgt; not the whole pgt and not an independent whole NP'),
 '2002:1_TOM_01_04.xls:0:3218': ('federal_territory_population_total','Federal city total; territory aggregate, not one settlement row'),
 '2010:pub-11-1-4.pdf:pdf_page_15:39': ('federal_territory_population_total','Federal city total; territory aggregate, not one settlement row'),
 '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:126656': ('federal_territory_population_total','Federal city total; territory aggregate, not one settlement row'),
 '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:121540': ('federal_territory_population_total','Federal territory/city total; not an individual settlement row'),
}
ex = roster[roster.source_record_id.isin(extra_ids)].copy()
ex['review_class'] = ex.source_record_id.map(lambda x: extra_ids[x][0])
ex['whole_named_NP_ownpoint_target'] = False
ex['completion_exclusion_reason'] = ex.source_record_id.map(lambda x: extra_ids[x][1])
# Copy exact already-accepted Stage70 scope decisions when available; do not alter underlying values.
scopeov = pd.read_csv(ROOT / 'main_axis_residual_application70_batch16_20261009' / 'accepted_source_scope_interpretation_overlay.csv', low_memory=False)
ex = ex.merge(scopeov[['source_record_id','reviewed_population_scope','decision_status','ordinary_whole_settlement_admission','is_ordinary_additive_settlement','raw_population_modified','source_sha256','source_locator','rule']], on='source_record_id', how='left', suffixes=('_roster','_stage70'), validate='one_to_one')
ex['raw_population_retained_unchanged'] = True
ex['population_allocated_or_removed'] = False
ex['source_record_status'] = 'retained_source_uid; scope_overlay_only'
ex['verified_raw_source_sha256'] = ex.source_file.map(raw_sha)
ex['source_record_locator_exact'] = ex.source_record_id
ex['evidence_scope_status'] = ex['decision_status'].fillna('federal territory aggregate; excluded by source grain')
ex_keep = ['source_record_id','census_year','settlement_name','settlement_type','region_norm','district_raw','population','source_file','verified_raw_source_sha256','source_record_locator_exact','review_class','whole_named_NP_ownpoint_target','completion_exclusion_reason','reviewed_population_scope','evidence_scope_status','ordinary_whole_settlement_admission','is_ordinary_additive_settlement','raw_population_modified','raw_population_retained_unchanged','population_allocated_or_removed','source_record_status']
ex=ex.rename(columns={'source_sha256':'source_sha256_roster'})
# preserve roster source hash under clear alias where scope overlay join added a second hash
ex.to_csv(OUT / 'aggregate_and_partial_scope_overlay.csv',index=False,columns=[c for c in ex_keep if c in ex.columns])

# Yaroslavka is explicitly a whole named NP observation; it is NOT in the scope-exempt set.
yid='2010:011_040325482b_3._20Ryaz_Smol_Tambov_Tula_Jaroslavl_20L1_20ethn_2010.xls:Data Sheet:8452'
y=roster[roster.source_record_id.eq(yid)].copy()
y_assoc=assoc[assoc.source_record_id.eq(yid)]
y=y.merge(y_assoc,on='source_record_id',how='left',validate='one_to_one')
y['scope_review_status']='not_scope_exempt_whole_named_NP'
y['whole_named_NP_ownpoint_target']=True
y['completion_exclusion_reason']='Do not exclude by population scope: source row is whole named село Ярославка, population 1,022. Stage70 scope manifest places it on existing coarse joint physical-NP route with 2021 carrier; exact historic part coordinate unknown. Ownpoint review is assigned to root.'
y['raw_population_retained_unchanged']=True
y['population_allocated_or_removed']=False
y['verified_raw_source_sha256']=y.source_file.map(raw_sha)
y['source_record_locator_exact']=y.source_record_id
y.to_csv(OUT/'whole_NP_not_scope_exempt_root_point_route.csv',index=False)

# One normalized exact-UID overlay for the requested scope-only set. The Yaroslavka
# whole-NP row is deliberately kept in a separate file and is not scope-exempt.
part_master = parts.rename(columns={
    'settlement_name_roster':'source_name', 'settlement_type_roster':'source_type',
    'region_norm_roster':'region_norm', 'district_raw_roster':'district_raw',
    'population_roster':'source_population', 'source_file_roster':'source_file',
    'stage68_primary_uid_credited':'stage68_primary_source_uid_credited'
}).copy()
part_master['scope_class']='literal_part_source_observation'
part_master['scope_review_status']='part-level source count; no whole-NP point claim'
part_master['evidence_basis']='Exact literal part/часть source name + existing Stage68 component and primary UID ledgers; Stage70 typed scope association retained only where exact UID row exists.'
part_master['raw_source_sha256']=part_master['verified_raw_source_sha256']
part_master['source_locator']=part_master['source_record_locator_exact']
part_master['source_scope_exclusion_rationale']=part_master['completion_exclusion_reason']
part_master['source_count_raw_population_retained']=True
part_master['population_value_modified_or_allocated']=False
part_master['ordinary_identity_or_population_equivalence_asserted']=False

extra_master = ex.rename(columns={
    'settlement_name':'source_name','settlement_type':'source_type',
    'population':'source_population','source_file':'source_file',
    'reviewed_population_scope':'stage70_reviewed_population_scope',
    'evidence_scope_status':'stage70_scope_decision'
}).copy()
extra_master['stage68_component_root']=''
extra_master['stage68_has_own_point']=False
extra_master['stage68_primary_source_uid_credited']=False
extra_master['stage70_scope_id']=''
extra_master['existing_joint_scope_carrier']=''
extra_master['spatial_association_kind']=''
extra_master['historic_part_exact_coordinate']=''
extra_master['ordinary_identity_or_population_equivalence_asserted']=False
extra_master['source_count_or_quality_changed']=False
extra_master['scope_review_status']=extra_master['stage70_scope_decision']
extra_master['evidence_basis']='Exact 2021/2002 source UID and source-grain decision from the pinned Stage70 source-scope interpretation overlay or federal-territory aggregate row.'
extra_master['raw_source_sha256']=extra_master['verified_raw_source_sha256']
extra_master['source_locator']=extra_master['source_record_locator_exact']
extra_master['source_scope_exclusion_rationale']=extra_master['completion_exclusion_reason']
extra_master['source_count_raw_population_retained']=True
extra_master['population_value_modified_or_allocated']=False

master_cols=['source_record_id','census_year','source_name','source_type','region_norm','district_raw','source_population','scope_class','whole_named_NP_ownpoint_target','scope_review_status','stage68_component_root','stage68_has_own_point','stage68_primary_source_uid_credited','stage70_reviewed_population_scope','stage70_scope_decision','stage70_scope_id','existing_joint_scope_carrier','spatial_association_kind','historic_part_exact_coordinate','ordinary_identity_or_population_equivalence_asserted','source_count_or_quality_changed','evidence_basis','source_scope_exclusion_rationale','source_count_raw_population_retained','population_value_modified_or_allocated','source_file','raw_source_sha256','source_locator']
part_master['stage70_reviewed_population_scope']=''
part_master['stage70_scope_decision']=''
part_master['stage70_scope_id']=part_master['scope_id'].fillna('')
part_master['existing_joint_scope_carrier']=part_master['existing_joint_scope_carrier'].fillna('')
part_master['spatial_association_kind']=part_master['spatial_association_kind'].fillna('')
part_master['historic_part_exact_coordinate']=part_master['historic_part_exact_coordinate'].fillna('')
part_master['source_count_or_quality_changed']=part_master['source_count_or_quality_changed'].fillna(False)
part_master['source_count_or_quality_changed']=part_master['source_count_or_quality_changed'].astype(bool)
part_master['ordinary_identity_or_population_equivalence_asserted']=False
extra_master['scope_class']=extra_master['review_class']
extra_master['whole_named_NP_ownpoint_target']=False
for c in master_cols:
    if c not in extra_master.columns: extra_master[c]=''
master=pd.concat([part_master[master_cols],extra_master[master_cols]],ignore_index=True)
master.to_csv(OUT/'scope_overlay.csv',index=False)
pins = {}
for sf in sorted(master.source_file.dropna().unique()):
    p = RAWROOT / sf
    if p.is_file(): pins[str(p)] = sha256(p.read_bytes()).hexdigest()
(OUT/'raw_source_file_pins.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary = {
    'scope_overlay_rows': int(len(master)),
    'literal_part_rows': int(len(parts)),
    'literal_part_raw_population_total': int(parts.population_roster.sum()),
    'literal_part_by_year': {str(int(y)): {'rows': int(g.shape[0]),'raw_population_total': int(g.population_roster.sum())} for y,g in parts.groupby('census_year')},
    'stage68_component_snapshot_membership_part_rows': int(parts.stage68_component_root.notna().sum()),
    'stage68_part_rows_with_ownpoint': int(parts.stage68_has_own_point.fillna(False).sum()),
    'stage68_primary_source_uid_credit_part_rows': int(parts.stage68_primary_uid_credited.sum()),
    'stage68_part_rows_without_primary_source_uid_credit': int((~parts.stage68_primary_uid_credited).sum()),
    'stage70_explicit_exact_part_uid_association_rows': int(parts.scope_id.notna().sum()),
    'administrative_aggregate_rows': int((extra_master.scope_class=='administrative_aggregate').sum()),
    'partial_settlement_population_scope_rows': int((extra_master.scope_class=='partial_settlement_population_scope').sum()),
    'federal_territory_population_total_rows': int((extra_master.scope_class=='federal_territory_population_total').sum()),
    'separate_whole_named_np_not_scope_exempt': {'source_record_id': yid,'population': int(y.iloc[0].population),'scope_id': str(y.iloc[0].scope_id),'assigned_to_root_point_review': True},
    'raw_population_values_modified_or_allocated': False,
    'scope_denominator_or_population_credit_changed': False,
    'point_finding_performed': False
}
(OUT/'scope_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

print('literal parts',len(parts),'sum',parts.population_roster.sum())
print(parts.groupby('census_year').population_roster.agg(['count','sum']).to_string())
print('extra scope',len(ex), 'Yaros',len(y))

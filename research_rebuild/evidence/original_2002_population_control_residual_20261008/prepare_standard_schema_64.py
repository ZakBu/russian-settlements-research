"""Prepare supplementary source observations; never instantiate or mutate State."""
from pathlib import Path
import ast,re,json,hashlib,unicodedata
import pandas as pd
E=Path(__file__).resolve().parent
PARSER=Path('/workspace/settlements-baseline/evidence/pipeline_before_20260929.py')
CANDIDATES=E/'explicit_missing_2002_np_observation_candidates.csv.gz'
ACTUAL=E.parent/'main_axis_residual_application63_20261008/applied_component_snapshot.csv.gz'
API=E.parent/'main_axis_residual_application63_20261008/frozen_State_API.py'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
# Only existing pure parser components are evaluated; all source/ingestion actions omitted.
names={'clean_text','norm','region_key','district_key','municipality_key','split_type_name'}
node=ast.parse(PARSER.read_text());chosen=[]
for n in node.body:
 if isinstance(n,ast.FunctionDef) and n.name in names:chosen.append(n)
 elif isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)and t.id in {'TYPE_PATTERNS','REGION_ALIASES'}for t in n.targets):chosen.append(n)
ns={'pd':pd,'re':re,'unicodedata':unicodedata};exec(compile(ast.Module(body=chosen,type_ignores=[]),str(PARSER),'exec'),ns)
d=pd.read_csv(CANDIDATES,keep_default_na=False);a=pd.read_csv(ACTUAL,usecols=['source_record_id'],keep_default_na=False);s=pd.read_parquet(SELECTED)
assert a.source_record_id.is_unique and set(a.source_record_id)==set(s.source_record_id)
assert not set(d.source_record_id)&set(a.source_record_id)
controls=pd.read_csv(E/'regional_control_before_after_source_candidates.csv');closed=set(controls.loc[(controls.official_minus_selected_base_scope>0)&(controls.remaining_control_minus_source_leaf==0),'selected_region_raw']);assert len(closed)==20
w={r['source_record_id']:r for r in json.loads((E/'literal_context_and_competitors.json').read_text())};records=[];meta=[]
api_text=API.read_text();columns=re.search(r'columns = "([^"]+)"',api_text).group(1).split(',');assert len(columns)==20
for r in d.to_dict('records'):
 assert sha(r['source_path'])==r['source_sha256']
 source_prefix=r['settlement_type'];caption=r['source_name_raw'].strip()
 # Whitespace-only parser presentation repairs; untouched literal stays in metadata.
 spaced=(source_prefix+' '+r['settlement_name']).strip() if source_prefix else caption
 typ,name=ns['split_type_name'](spaced)
 method='existing_parser_split_type_name_with_literal_prefix_spacing'
 if source_prefix=='кп':typ='кп';name=r['settlement_name'];method='preserve_literal_kp_rural_census_type_do_not_repeat_original_pgt_misclassification'
 elif not typ:typ=source_prefix or '';name=r['settlement_name'];method='literal_source_type_if_printed_otherwise_blank_with_explicit_roster_leaf_grain'
 # Parent source district caption recognized by the same original parser regex.
 district=r['district_raw']
 for _,_,cap,_ in w[r['source_record_id']]['ancestor_controls']:
  m=re.match(r'^\s*(.+?\b(?:район|улус|кожуун))\s*(?:[-–—]|:)\s*все\s+сельск',cap,re.I)
  if m:district=m.group(1).strip()
 record=dict(source_record_id=r['source_record_id'],census_year=2002,settlement_name=name,settlement_type=typ,name_norm=ns['norm'](name),type_norm=ns['norm'](typ),region_norm=ns['region_key'](r['region_raw']),district_raw=district,population=int(r['population']),population_scope='ordinary_settlement',is_additive_settlement_record=True,population_value_quality='verified_count_in_secondary_census_compilation',latitude=None,longitude=None,oktmo=None,okato=None,source_file=r['source_file'],source_path=r['source_path'],source_sha256=r['source_sha256'],source_locator=r['source_locator'])
 records.append(record)
 status='closed_local_source_batch_candidate' if r['region_raw'] in closed else 'hold_regional_source_control_inconsistency'
 meta.append(dict(source_record_id=r['source_record_id'],source_name_raw=r['source_name_raw'],source_sheet=r['source_sheet'],source_row=r['source_row'],source_type_raw=source_prefix,source_region_raw=r['region_raw'],municipality_raw=r['municipality_raw'],district_norm=ns['district_key'](district),municipality_norm=ns['municipality_key'](r['municipality_raw']),source_grade='secondary_compilation_of_2002_census',source_publisher='Lingvarium',collection_url='https://www.lingvarium.org/russia/Census2002.shtml',independent_official_primary_locality_count_verified=False,census_reference_date='2002-10-09',publication_date=None,source_admission_status=status,record_inventory_status=r['record_inventory_status'],original_parsed_type=r['original_parsed_type'],parser_type_name_method=method,explicit_census_NP_grain=True,canonical_State_present=False,own_point_admitted=False,temporal_identity_admitted=False,regional_source_closure=status=='closed_local_source_batch_candidate'))
r=pd.DataFrame(records,columns=columns);m=pd.DataFrame(meta);assert len(r)==len(m)==128 and r.source_record_id.is_unique
r.to_csv(E/'future64_missing_2002_source_observations_20col.csv',index=False);m.to_csv(E/'future64_missing_2002_admission_metadata.csv',index=False)
ready=set(m.loc[m.regional_source_closure,'source_record_id']);r[r.source_record_id.isin(ready)].to_csv(E/'future64_closed_local_source_batch_98_20col.csv',index=False);r[~r.source_record_id.isin(ready)].to_csv(E/'future64_held_local_source_rows_30_20col.csv',index=False)
assert len(ready)==98 and r[r.source_record_id.isin(ready)].population.sum()==9810
proof=dict(status='schema_and_admission_plan_only_not_applied',actual_State_stage=63,actual_full_State_source_IDs=len(a),candidate_IDs_in_actual_full_State=0,candidates=128,candidate_population=13027,new_to_parsed_inventory=127,existing_parsed_but_excluded=1,closed_local_source_batch_rows=98,closed_local_source_batch_population=9810,held_rows=30,held_population=3217,source_grade_all_rows='secondary_compilation_of_2002_census',official_primary_locality_value_claims=0,exact_standard_schema=columns,raw_counts_modified=False,State_API_modified=False,new_points_or_temporal_links=0,input_pins={str(p):sha(p)for p in [PARSER,CANDIDATES,ACTUAL,API,SELECTED]},publication_dedup_key=['census_year','source_sha256','source_sheet','source_row'],source_ID_recipe='year:original_source_filename:sheet:1-based-row',future_application_rules=['Root must accept the supplemental source grade and admission batch before appending observations; original selected parquet stays immutable.','Read exact finalized full State source-ID roster again; absent candidate IDs required. Existing parsed/excluded IDs are restorations, not new IDs.','Append admitted ordinary NP observations before UF initialization, then add only separately accepted coordinates/identity deltas.','No known primary population numerator credit solely from these secondary compilation values.','Verify source hashes and exact literal cell counts; never substitute a municipality control for a locality count.','Reject same source publication/row admitted via a renamed copy or same source ID; different accepted population claims for one SID must hold.','Regional closure is a count/source diagnostic, not own-point or identity proof. Hold Tver/Astrakhan until source inconsistencies are reviewed.'])
proof['output_pins']={str(p):sha(p)for p in E.glob('future64_*.csv')};(E/'future64_schema_admission_receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps({k:proof[k]for k in ['actual_full_State_source_IDs','candidate_IDs_in_actual_full_State','closed_local_source_batch_rows','closed_local_source_batch_population','held_rows','held_population','official_primary_locality_value_claims']},indent=2))

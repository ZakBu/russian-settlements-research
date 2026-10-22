"""Bind NEW477/adminall/dominant-core hierarchy to admitted current source contexts."""
import argparse,copy,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def layer(path,review,mapping):
 p=BASE/path;r=BASE/review;a=json.loads(r.read_text());assert a['all_checks_passed'] and str(a['status']).startswith('ACCEPTED');assert sha(p) in json.dumps(a)
 return {'path':str(p),'sha256':sha(p),'admission_path':str(r),'admission_sha256':sha(r),'id_column':'id','column_mapping':mapping}
def registry():
 old=json.loads((HERE/'contracts_primary_v1/normalize_cap060_supported_end_forest.json').read_text());layers=copy.deepcopy(old['context_layers']);p=copy.deepcopy(old['context_projection']);num=copy.deepcopy(old['context_numeric_projection'])
 thematic='typology2021_cycle07/recovery477_relink/';tr='reviews/cycle07_thematic477_independent/audit.json';cr='reviews/cycle07_context477_independent/audit.json';replacements={}
 for file,cols in [('settlement_recreation_features_2021.parquet',['recreation_facility_evidence','dacha_landuse_evidence']),('settlement_literal_agro_processing_evidence_2021.parquet',['agro_processing_function_evidence']),('settlement_industry_resource_features_2021.parquet',['mapped_industrial_site_context_evidence','mapped_resource_site_context_evidence']),('settlement_own_function_evidence_2021.parquet',['trade_and_administration_function_evidence','basic_administrative_service_function_evidence','basic_administrative_service_with_physical_admin_evidence','developed_agro_infrastructure_evidence'])]:
  mp={x:'new477_'+x for x in cols};layers.append(layer(thematic+file,tr,mp));replacements.update(mp)
 for file,cols in [('climate_settlement_features.parquet',['climate_gaez_sat_above10_cday_1981_2010','climate_gaez_summer_precipitation_over_pet_1981_2010']),('soil_settlement_features.parquet',['soil_gaez_low_input_most_limiting_rating_class_rating_lower','soil_gaez_low_input_most_limiting_rating_class_rating_upper'])]:
  mp={x:'new477_'+x for x in cols};layers.append(layer('context/cycle07_coordinate_recovery/'+file,cr,mp));replacements.update(mp)
 for spec in p:
  spec['columns']=[replacements.get(x,x) for x in spec['columns']]
  if any(x.startswith('new477_') for x in spec['columns']):spec['source']='Independently admitted477-point thematic source relink; full-axis values incl affected old NP withdrawals'
 for spec in num:
  spec['value_column']=replacements.get(spec['value_column'],spec['value_column'])
  if spec['value_column'].startswith('new477_'):spec['source']='Independently admitted477 coordinate raster samples and all unchanged rows; no old source-point substitution'
 def add(output,col,scope,grain):p.append({'output_column':output,'columns':['new477_'+col],'kind':'boolean','scope':scope,'source':'Accepted477 thematic/ownfunction sidecar; fixed source rules, positive evidence only','year':2021,'grain':grain,'absence_is_unknown':True,'independent_source_unit_columns':['id']})
 for name,col in [('industrial','mapped_industrial_site_context_evidence'),('resource','mapped_resource_site_context_evidence')]:
  for scope,prefix in [('focal','focal'),('rural_members','rural')]:add(f'{prefix}_mapped_{name}_sourcepoint_context2021',col,scope,'nearest_admitted_sourceNP_OSM_proximity_assertion_not_own_economic_dominance_or_decline')
 for output,col in [('focal_trade_administration_copresence2021','trade_and_administration_function_evidence'),('focal_basic_administrative_service_copresence2021','basic_administrative_service_function_evidence'),('focal_basic_service_physical_admin_copresence2021','basic_administrative_service_with_physical_admin_evidence')]:add(output,col,'focal','fixed_strict_site_and_dated_seat_positive_co_presence_not_independent_economic_sectors')
 add('rural_developed_agro_infrastructure_source_evidence','developed_agro_infrastructure_evidence','rural_members','unavailable_unless_explicit_source_evidence_no_inference_from_services_or_grain')
 return {'status':'PROSPECTIVE_SOURCE477_CONTEXT_PROJECTION_REGISTRY','context_layers':layers,'context_projection':p,'context_numeric_projection':num,'no_new_thresholds':True,'no_primary_type_gate_or_mass_changes':True,'unknown_is_not_absence':True,'strict_address_and_geographic_catalogue_channels_separate':True,'municipal_regional_raster_grains_not_independent_NP_observations':True,'ownfunction_composites_not_independent_of_components':True,'classifier_trajectory_rules_unchanged':True,'old_source_context_values_never_substitute_for_available_admitted_new477_sources':True}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--registry-only');ap.add_argument('--registry');ap.add_argument('--registry-admission');ap.add_argument('--raw-admission');ap.add_argument('--cap',type=int,default=60);ap.add_argument('--output');a=ap.parse_args()
 if a.registry_only:
  p=Path(a.registry_only);assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(registry(),ensure_ascii=False,indent=2));print(sha(p));return
 assert a.registry and a.registry_admission and a.raw_admission and a.output
 registry_path=Path(a.registry);reg=json.loads(registry_path.read_text());ra=Path(a.registry_admission);review=json.loads(ra.read_text());assert review['all_checks_passed'] and str(review['status']).startswith('ACCEPTED') and review['accepted_registry_sha256']==sha(registry_path)
 rawreview=Path(a.raw_admission).resolve();ar=json.loads(rawreview.read_text());assert ar['all_checks_passed'] and str(ar['status']).startswith('ACCEPTED')
 c=json.loads((HERE/'contracts_primary_v1/normalize_cap060_supported_end_forest.json').read_text());cap=f'{a.cap:03}';folder=BASE/'model/cycle07_scale_hierarchy/source477_adminall_v2/output_primary_v1'
 for key,file in [('raw_units',f'cap_{cap}_raw_units.parquet'),('memberships',f'cap_{cap}_raw_memberships.parquet')]:c[key+'_path']=str(folder/file);c[key+'_sha256']=sha(folder/file)
 pins=ar.get('accepted_unit_membership_files_sha256',{})
 assert ar.get('accepted_raw_units_sha256',pins.get(c['raw_units_path']))==c['raw_units_sha256'] and ar.get('accepted_raw_memberships_sha256',pins.get(c['memberships_path']))==c['memberships_sha256'],'Raw admission does not bind this actual cap/source'
 c['base_nodes_path']=str(BASE/'model_inputs_cycle07/institutional_mass477_v2/computed/effective_full_nodes.parquet');c['base_nodes_sha256']=sha(c['base_nodes_path']);assert c['base_nodes_sha256']=='e006d91a1250576020131da66a1a420f76f55cf3a9b8cae5fd5009f36889ad04'
 c['require_base_effective2010_already_matches_admitted_view']=True;c['operational_view_id']=f'source477_adminall_v2_cap{cap}_supported_end_forest';c['coordinate_and_function_source_frame']='NEW477coordinates/3institutionfamilies+alllocaladmin17824eligibility+dominantFIXEDMi-beforefeasibility; admitted353primary2010 metadata readthrough; accepted477climate/soil/thematic/ownfunctions explicit layers'
 c.pop('shared_effective_source_view',None);c['context_layers']=reg['context_layers'];c['context_projection']=reg['context_projection'];c['context_numeric_projection']=reg['context_numeric_projection'];c['context_projection_registry_path']=str(registry_path.resolve());c['context_projection_registry_sha256']=sha(registry_path)
 sources=[BASE/'reviews/cycle07_controller_independent/controller_source477_v2_admission.json',rawreview,BASE/'reviews/cycle07_mass_pool477_v2_independent/combined_admission.json',BASE/'reviews/cycle07_institutional_relink477_independent/combined_admission.json',BASE/'reviews/cycle07_population_source353_projection_independent/audit.json',ra]
 c['source_admissions']=[{'path':str(p),'sha256':sha(p)} for p in sources];out=Path(a.output);assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(c,ensure_ascii=False,indent=2));print(json.dumps({'contract_sha256':sha(out),'raw_source_sha256':c['raw_units_sha256'],'base_nodes_sha256':c['base_nodes_sha256'],'context_profiles':len(c['context_projection'])}))
if __name__=='__main__':main()

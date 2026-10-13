"""Compose frozen dated secondary claims against actual final61 main identities."""
import csv,gzip,json,hashlib,sys,collections
from pathlib import Path
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=Path(__file__).parent;D=Path('/workspace/settlements-delivery/working-full-chain-20261007');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import distance_km

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
 with gzip.open(p,'rt') as f:return list(csv.DictReader(f))
def write(p,rows):
 fields=list(dict.fromkeys(k for z in rows for k in z))
 with gzip.GzipFile(filename=str(p),mode='wb',mtime=0) as gf:
  import io
  with io.TextIOWrapper(gf,encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
main=D/'ordinary_full3_all_own_points_complete_numbers.csv.gz';mainhash=sha(main);native={z['source_record_id_2021']:z for z in read(main)};pins={str(main):mainhash,str(Path(__file__)):sha(__file__)};obs=[];bindings={}
receipts=[E/'annual_cached_own_native_history_20261008/receipt.json',E/'annual_cached_own_native_history_v4_20261008/receipt.json',O/'receipt.json']
for rp in receipts:
 receipt=json.loads(rp.read_text());pins[str(rp)]=sha(rp)
 for path,pin in receipt['outputs'].items():
  p=Path(path);h=pin if isinstance(pin,str) else pin['sha256'];assert sha(p)==h;pins[path]=h;rows=read(p)
  if p.name=='observations.csv.gz':obs.extend(rows)
  else:
   for z in rows:
    q=z['wikidata_qid'];assert q not in bindings;bindings[q]=z
assert len(obs)==len({z['statement_guid'] for z in obs})==10963;assert len(bindings)==3204
held={'Q4446819','Q4428922','Q4148815','Q14620671','Q19820596','Q23976086'}
audit=E/'combined_ownpoint_correction_application_20261008/sidecar_exact_identity_and_point_audit.json';pins[str(audit)]=sha(audit)
parentmanifest=O/'frozen_asset_manifest.json';pins[str(parentmanifest)]=sha(parentmanifest)
for p,pin in json.loads(parentmanifest.read_text())['assets'].items():assert sha(p)==pin['sha256']
counters=collections.Counter();risk=[]
for q,z in bindings.items():
 sid=z['current_source_record_id'];z['collected_current_source_record_id']=sid;z['collected_current_latitude']=z.get('current_latitude','');z['collected_current_longitude']=z.get('current_longitude','')
 if not z['collected_current_latitude'] and z.get('current_ownpoint_json'):
  pp=json.loads(z['current_ownpoint_json']);z['collected_current_latitude']=pp['latitude'];z['collected_current_longitude']=pp['longitude']
 z.setdefault('current_region',z.get('region_norm',''));z['entity_uid']='';z['final_main_current_source_record_id']='';z['final_main_latitude']='';z['final_main_longitude']='';z['final_main_current_coordinate_distance_km']='';z['final_main_coordinate_status']='not_projected';z['no_native_census_population_credit']=True
 if q in held:
  z['current_binding_delivery_status']='known_secondary_native_identity_or_point_binding_conflict_held';z['descriptive_summary_eligible']=False;counters['known_held_bindings']+=1;risk.append({'qid':q,'collected_current_source_record_id':sid,'decision':'held_no_final_main_UID_or_coordinate_projection_no_population_transfer'})
 elif sid in native:
  n=native[sid];assert n['source_record_id_2021']==sid;z['entity_uid']=n['entity_uid'];z['final_main_current_source_record_id']=sid;z['final_main_latitude']=n['latitude_2021'];z['final_main_longitude']=n['longitude_2021'];dist=distance_km((float(z['collected_current_latitude']),float(z['collected_current_longitude'])),(float(n['latitude_2021']),float(n['longitude_2021'])));z['final_main_current_coordinate_distance_km']=dist;z['final_main_coordinate_status']='coordinate_changed_disagreement_over5km' if dist>5 else 'matching_current_identity_coordinate_within5km';z['current_binding_delivery_status']='actual_final61_complete_triplet_current_identity';z['descriptive_summary_eligible']=True;counters['main_aligned_bindings']+=1;counters['coordinate_changed_disagreement_over5km']+=dist>5
 else:z['current_binding_delivery_status']='native_current_only_outside_complete_triplet_export';z['descriptive_summary_eligible']=True;counters['outside_main_current_only_bindings']+=1
 # Preserve source-collected coordinates and evidence; final main coordinates are separate representative fields.
 z['current_latitude']=z['collected_current_latitude'];z['current_longitude']=z['collected_current_longitude']
for z in obs:
 assert int(z['observed_year']) not in [2002,2010,2021];b=bindings[z['wikidata_qid']]
 for key in ['entity_uid','current_source_record_id','current_name','current_type','current_region','current_native_oktmo','current_latitude','current_longitude','collected_current_source_record_id','collected_current_latitude','collected_current_longitude','final_main_current_source_record_id','final_main_latitude','final_main_longitude','final_main_current_coordinate_distance_km','final_main_coordinate_status','current_binding_delivery_status','descriptive_summary_eligible','no_native_census_population_credit']:z[key]=b.get(key,'')
 z['primary_verification']='primary_unverified';z['boundary_comparability']='UNKNOWN';z['observation_class']='dated_secondary_population_observation';z['native_census_replacement']=False
 counters['known_held_observations']+=not b['descriptive_summary_eligible']
files={}
for name,rows in [('other_dated_population_observations.csv.gz',obs),('other_dated_population_current_bindings.csv.gz',list(bindings.values()))]:
 p=D/name;write(p,rows);assert len(read(p))==len(rows);files[name]={'sha256':sha(p),'bytes':p.stat().st_size,'rows':len(rows)}
groups=collections.defaultdict(list)
for z in obs:groups[int(z['observed_year'])].append(z)
summary=[]
for year,rows in sorted(groups.items()):
 values=collections.defaultdict(set)
 for z in rows:
  if not z['descriptive_summary_eligible']:continue
  key=z['entity_uid'] or 'current_native:'+z['current_source_record_id'];assert key!='current_native:';values[key].add(int(z['population_value']))
 single=[next(iter(v)) for v in values.values() if len(v)==1];summary.append({'year':year,'literal_observations':len(rows),'entities_with_observation':len(values),'entities_with_one_population_value_in_year':len(single),'entities_with_conflicting_values_in_year':len(values)-len(single),'partial_descriptive_population_sum':sum(single),'held_binding_observations_excluded_from_descriptive_sum':sum(not z['descriptive_summary_eligible'] for z in rows),'native_current_only_observations':sum(z['current_binding_delivery_status']=='native_current_only_outside_complete_triplet_export' for z in rows),'national_coverage_claim':False})
assert len(summary)==180;p=D/'other_dated_population_year_summary.csv'
with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
files[p.name]={'sha256':sha(p),'bytes':p.stat().st_size,'rows':len(summary)};assert sha(main)==mainhash
r={'status':'frozen_secondary_annual_claims_composed_against_actual_final61_native_identity_export','main_stage':61,'native_export_sha256':mainhash,'input_pins':pins,'observations':len(obs),'entities':len(bindings),'observed_years':len(summary),'counters':dict(counters),'known_conflict_exclusions':risk,'extension_current_SIDs':{q:{'current_source_record_id':z['current_source_record_id'],'delivery_status':z['current_binding_delivery_status']} for q,z in bindings.items() if z.get('binding_rule','').startswith('unique_actual_current')},'no_census_population_or_coverage_changes':True,'primary_source_verification':'not_established','boundary_comparability':'UNKNOWN','historical_coordinates_are_continuity_inferences':True,'outputs':files}
p=D/'other_dated_population_delivery_receipt.json';p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');r['delivery_receipt_pin']={str(p):{'sha256':sha(p),'bytes':p.stat().st_size}};(O/'ROOTfinal61merge_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k in ['status','observations','entities','observed_years','counters','extension_current_SIDs']}))

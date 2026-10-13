import sys,json,gzip,hashlib,importlib.util,re,csv
from pathlib import Path
import pandas as pd,xlrd,subprocess
Z=Path(__file__).resolve().parent;E=Z.parent;sys.path.insert(0,str(E.parent/'mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km,normalize
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
spec=importlib.util.spec_from_file_location('finite_helper',E/'working_full_chain_20261007/replay_additional_native_20261008.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
w=json.load(gzip.open(Z/'native_ownpoint_recovery_witnesses.json.gz','rt'));p=pd.read_csv(Z/'accepted_point_use_delta.csv.gz',keep_default_na=False);reject=pd.read_csv(Z/'point_use_rejections.csv.gz',keep_default_na=False);pins=json.loads((Z/'correction_input_pins.json').read_text());assert all(sha(path)==h for path,h in pins.items());review=json.loads((Z/'rule_review_receipt.json').read_text());H=len(w);assert H==review['recovered_histories'] and len(p)==review['corrected_old_point_uses'] and len(reject)>=len(p);assert p.target_source_record_id.is_unique and set(p.target_source_record_id).issubset(set(reject.target_source_record_id))
# Check all fullraw native modern own-code bindings without using a projected OKATO field.
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');raw=pd.read_parquet(RAW,columns=['object_level','object_name','oktmo','population','oktmo_dadata','latitude_dadata','longitude_dadata','mun_upper','mun_lower']);code=lambda x:str(int(float(x))) if pd.notna(x) else '';sql=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql').read_text().splitlines();oldobs=pd.read_csv(Z/'native_extreme_observations.csv.gz',keep_default_na=False).set_index('source_record_id');cloneproof=[];rulecounts={}
for r in w:
 sid=r['carrier_source_record_id'];native=raw.iloc[int(sid.rsplit(':',1)[1])-1];a=r['anchor_proof'];assert native.object_level=='Населенный пункт';assert code(native.oktmo)==a['anchor_code'];assert float(native.population)==r['population_2021'];rulecounts[a['anchor_rule']]=rulecounts.get(a['anchor_rule'],0)+1
 if 'Dadata' in a['anchor_rule']:
  assert code(native.oktmo)==code(native.oktmo_dadata);assert (float(native.latitude_dadata),float(native.longitude_dadata))==(r['anchor_latitude'],r['anchor_longitude'])
 elif 'Wikimedia' in a['anchor_rule']:assert a['own_classifier_literal']==sql[a['own_classifier_line']-1] and a['own_OKATO'] in a['own_classifier_literal']
 else:
  g=a['literal_GeoNames_point_fields'];assert g[6]=='P' and g[7] in ['PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLC'] and g[8]=='RU' and a['external_admin2']=='UNKNOWN';assert (float(g[4]),float(g[5]))==(r['anchor_latitude'],r['anchor_longitude']);assert a['fullraw_current_name_region_NP_rivals']==1 and a['modern_official_code_asserted']==False
 for proof in r['old_native_and_classifier_proofs']:
  assert sql[proof['classifier_literal_line']-1]==proof['classifier_literal_raw'];assert proof['classifier_code'] in proof['classifier_literal_raw'];assert float(oldobs.loc[proof['target_source_record_id']].population)==proof['native_original_count']
 witnessed={q['target_source_record_id'] for q in r['old_native_and_classifier_proofs']}
 for target in set(r['corrected_source_record_ids'])-witnessed:
  obs=oldobs.loc[target];path=Path('/workspace/settlements-raw')/obs.source_file;sheet=target.rsplit(':',2)[1];rowtext=target.rsplit(':',1)[1]
  if target.startswith('ROSSTAT2010:T5:'):
   loc=json.loads(obs.source_locator);page=int(loc['pdf_page_1based']);lines=subprocess.check_output(['pdftotext','-layout','-f',str(page),'-l',str(page),str(path),'-'],text=True).splitlines();matches=[line for line in lines if normalize(obs.settlement_name) in normalize(line)];assert len(matches)==1;line=matches[0];row=[line,*re.findall(r'(?<!\d)\d+(?:[ \u00a0]\d{3})?(?!\d)',line)]
  else:
   n=int(rowtext);row=xlrd.open_workbook(str(path)).sheet_by_name(sheet).row_values(n-1)
  assert any(normalize(obs.settlement_name) in normalize(v) for v in row if isinstance(v,str));values=[]
  for v in row:
   try:values.append(float(str(v).replace(' ','').replace('\u00a0','').replace(',','.')))
   except ValueError:pass
  assert float(obs.population) in values;cloneproof.append(dict(target_source_record_id=target,source_file=str(path),source_sha256=sha(path),literal_native_row=row,population=float(obs.population),source_quality=obs.population_value_quality,clone_relation='Exact coordinates and accepted historical component of contradicted/superseded Geo use; independently literal native row checked.'))
# Explicit intersections with current-carrier quarantine and known event/movement ledgers.
currentids={r['carrier_source_record_id'] for r in w};targetids=set(p.target_source_record_id);ex97=pd.read_csv(E/'corrected_ownpoint_cached_history_followup_20261008/new_Geo_rule_carrier_scope.csv.gz',keep_default_na=False);known=set()
for col in ['carrier_source_record_id','source_record_id','current_source_record_id']:
 if col in ex97:known.update(ex97[col]);break
q194=pd.read_csv(E/'corrected_ownpoint_cached_history_followup_20261008/point_use_rejections.csv.gz');assert not targetids&set(q194.target_source_record_id);assert not currentids&known
signalpaths=[E/'working_full_chain_20261007/named_merger_lineage_observations.csv',E/'further_urban_merger_application_20261007/accepted_group_observations.csv'];events=set()
for path in signalpaths:
 for vals in pd.read_csv(path).source_record_ids_json:events.update(json.loads(vals))
 assert not (targetids|currentids)&events
screen=E/'remaining_large_current_component_point_conflicts_20261008/own_article_component_point_screen.csv';snippets=pd.read_csv(screen,keep_default_na=False);signals=snippets[~snippets.article_history_movement_snippets_json.isin(['','[]'])];assert not currentids&set(signals.current_source_record_id)
s=load(59);before=m.finite(s);native_before=s.obs.copy(deep=True);identity_before=dict(s.uf.parent);current_before={sid:dict(s.point_rows[sid]) for sid in currentids}
components={s.uf.find(sid) for sid in currentids};assert len(components)==H
# Coordinate distances are diagnostics of selected representatives, never a proof of historical relocation.
def geometry():
 out={}
 for root in components:
  g=s.obs[s.obs.root.eq(root)];coords=[(s.point_rows[sid]['latitude'],s.point_rows[sid]['longitude']) for sid in g.source_record_id];out[root]=max(distance_km(a,b) for a in coords for b in coords)
 return dict(histories=len(out),histories_max_distance_above100=sum(v>100 for v in out.values()),histories_max_distance_above5=sum(v>5 for v in out.values()),max_distance_km=max(out.values()))
geometry_before=geometry();s.reject_point_uses(Z/'resolved_representative_supersessions.csv.gz');s.add_deltas(point_paths=[Z/'accepted_point_use_delta.csv.gz']);after_recovery=m.finite(s);geometry_after=geometry();assert before==after_recovery;s.reject_point_uses(Z/'unresolved_old_Geo_point_quarantine.csv.gz');after=m.finite(s);assert native_before.equals(s.obs);assert identity_before==dict(s.uf.parent);assert all(current_before[sid]==s.point_rows[sid] for sid in currentids)
for path in [*signalpaths,screen,E/'corrected_ownpoint_cached_history_followup_20261008/new_Geo_rule_carrier_scope.csv.gz',E/'corrected_ownpoint_cached_history_followup_20261008/point_use_rejections.csv.gz']:pins[str(path)]=sha(path)
(Z/'independent_clone_native_witnesses.json').write_text(json.dumps(cloneproof,ensure_ascii=False,indent=2)+'\n');review=json.loads((Z/'rule_review_receipt.json').read_text());receipt=dict(status='independently_verified_representative_point_supersession_only',source_state_stage=59,recovered_histories=H,corrected_old_point_uses=len(p),held_histories=review['held_histories'],unresolved_point_quarantine_uses=len(pd.read_csv(Z/'unresolved_old_Geo_point_quarantine.csv.gz')),gross_recovered_existing_component_population_by_year=review['recovered_gross_population_by_year'],finite_before=before,finite_after_recovery=after_recovery,finite_after=after,finite_population_gain={y:after['populations_by_year'][y]-before['populations_by_year'][y] for y in ['2002','2010','2021']},geometry_before=geometry_before,geometry_after=geometry_after,anchor_rule_counts=rulecounts,native_obs_full_metadata_unchanged=True,identity_graph_unchanged=True,current_point_uses_unchanged=True,all754_current_conflict_and_all97_components_excluded=True,known_merger_and_movement_ledger_intersections=0,native_old_literal_observations_checked=sum(len(r['old_native_and_classifier_proofs']) for r in w),independent_additional_exact_clone_observations_checked=len(cloneproof),historical_point_accuracy='UNKNOWN; representative continuity inferred, never measured census-day coordinates',raw_Geo_claims_preserved_as_frozen_alternatives=True,rejection_status='reviewed_superseded_representative_point_only for recovered; reviewed_rejected_coordinate_claim_only coordinate_conflict_unresolved for held',input_pins=pins,state59_input_pins={str(path):sha(path) for path in s.inputs},builder_sha256=sha(Z/'build_correction.py'),verifier_sha256=sha(Path(__file__)),output_pins={path.name:sha(path) for path in [Z/'point_use_rejections.csv.gz',Z/'resolved_representative_supersessions.csv.gz',Z/'unresolved_old_Geo_point_quarantine.csv.gz',Z/'accepted_point_use_delta.csv.gz',Z/'native_ownpoint_recovery_witnesses.json.gz',Z/'held_candidates.csv.gz',Z/'all_current_name_region_rivals.csv.gz',Z/'independent_clone_native_witnesses.json']},limitations=['Unknown/unsupported modern code anchors, unresolved native source formats, and actual type changes remain held.','No individual census-day geometry claim or historical relocation inference is made. The selected modern own-coded point is a retrospective representative of an already accepted stable native identity.','Current fullraw code/name/region/subordinate rivals and named accepted merger/movement ledgers checked; this bounded rule does not claim exhaustive historical event discovery.'])
(Z/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');(Z/'verification_receipt.json').write_text(json.dumps({k:receipt[k] for k in ['status','source_state_stage','finite_before','finite_after','geometry_before','geometry_after','native_obs_full_metadata_unchanged','identity_graph_unchanged','current_point_uses_unchanged','all754_current_conflict_and_all97_components_excluded','output_pins','verifier_sha256']},ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['finite_before','finite_after','geometry_before','geometry_after','anchor_rule_counts']},ensure_ascii=False,indent=2))

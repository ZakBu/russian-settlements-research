from pathlib import Path
import pandas as pd, openpyxl, json, hashlib, math
Z=Path(__file__).parent
R=Path('/workspace/settlements-work/continuation_20261004/root')
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
W=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/gks_2014_perepis_krim_pub-01-03_wayback_20150924.xlsx')
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
F=Path('/workspace/settlements-work/continuation_20261004/federal_application/accepted_territory_reference_points.parquet')
files=[W,RAW,S,R/'scoped2014_applied/accepted_scoped_observations_2014.parquet',R/'scoped2014_applied/accepted_scoped_identity_edges_2014_2021.csv',R/'scoped2014_applied/point_provenance_reconciled/accepted_scoped_retrospective_point_uses_2014_actual_carrier_origins.csv',R/'scoped2014_applied/point_provenance_reconciled/receipt.json',R/'scoped2014_applied/application_receipt.json',R/'accepted_scoped_crimea22/accepted_scoped_observations.parquet',R/'accepted_scoped_crimea22/accepted_scoped_identity_links.parquet',R/'accepted_scoped_crimea22/accepted_scoped_point_uses.parquet',R/'accepted_scoped_crimea22/application_receipt.json',F,W.parent/'gks_2014_get_receipt.json']
def sha(f):
 h=hashlib.sha256()
 with open(f,'rb') as s:
  for b in iter(lambda:s.read(1048576),b''):h.update(b)
 return h.hexdigest()
pins={str(f):{'sha256':sha(f),'bytes':f.stat().st_size} for f in files}
a=pd.read_parquet(files[3]);b=pd.read_parquet(files[8]);o=pd.concat([a,b],ignore_index=True)
e=pd.concat([pd.read_csv(files[4]),pd.read_parquet(files[9])],ignore_index=True)
assert len(o)==1016 and o.source_record_id.nunique()==1016 and e.from_source_record_id.nunique()==1016
assert set(e.from_source_record_id)==set(o.source_record_id)
assert set(e.to_source_record_id)==set(o.current_2021_source_record_id)
assert o.current_2021_source_record_id.nunique()==1016
wb=openpyxl.load_workbook(W,data_only=True,read_only=False);ws=wb['pub-01-03']
for x in o.itertuples():
 cells=[ws.cell(int(x.source_row),j).value for j in range(1,5)]
 assert ' '.join(str(cells[0]).split())==' '.join(str(x.source_name_raw).split()),(x.source_record_id,cells[0],x.source_name_raw)
 if pd.notna(x.population_value):assert float(cells[1])==float(x.population_value)
 else:assert cells[1]=='-' and x.population_raw=='-'
sel=pd.read_parquet(S,columns=['source_record_id','census_year','region_norm','settlement_name','settlement_type','population','population_scope'])
cur=sel.set_index('source_record_id').loc[o.current_2021_source_record_id]
assert cur.census_year.eq(2021).all() and cur.population_scope.eq('settlement').all() and cur.region_norm.eq('крым').all()
assert (cur.population.to_numpy()==o.current_2021_population_context.to_numpy()).all()
raw=pd.read_parquet(RAW,columns=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population'])
rawrows=raw.iloc[[int(i.rsplit(':',1)[1])-1 for i in o.current_2021_source_record_id]]
assert rawrows.object_level.eq('Населенный пункт').all()
assert (rawrows.population.to_numpy()==cur.population.to_numpy()).all()
p1=pd.read_csv(files[5]);p2=pd.read_parquet(files[10]);p2=p2.rename(columns={'current_carrier_target_source_record_id':'source_2021_carrier_target_source_record_id'})
p=pd.concat([p1,p2],ignore_index=True)
assert len(p)==1015 and p.target_source_record_id.nunique()==1015
assert p.coordinate_admission_status.eq('reviewed_rule_accepted').all()
assert set(p.target_source_record_id).issubset(set(o.source_record_id))
pointcols=['target_source_record_id','source_2021_carrier_target_source_record_id','latitude','longitude','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','coordinate_provider','coordinate_provenance','review_packet_witness_point_origin_file','review_packet_witness_point_origin_sha256','review_packet_witness_point_origin_locator','source_2021_point_accepted_artifact','source_2021_point_accepted_artifact_sha256']
p[pointcols].to_csv(Z/'existing_accepted_point_references.csv.gz',index=False,compression={'method':'gzip','mtime':0})
obs=[];credits=[]
for ix,x in enumerate(o.itertuples()):
 y=cur.iloc[ix];r=rawrows.iloc[ix];has=x.source_record_id in set(p.target_source_record_id);numeric=pd.notna(x.population_value)
 common={'place_current_source_record_id':x.current_2021_source_record_id,'settlement_name':x.settlement_name,'grain':'physical_settlement','Russian_2002_status':'outside_scope','Russian_2010_status':'outside_scope','strict_NP3_eligible':False,'boundary_comparability':'unknown_not_asserted','coordinate_basis':'reviewed_modern_own_representative_point_retrospective_continuity_date_unknown' if has else 'unpointed','point_reference_target_id':x.source_record_id if has else '', 'existing_identity_review_status':e[e.from_source_record_id.eq(x.source_record_id)].iloc[0].decision_status}
 obs.append(dict(common,year=2014,source_record_id=x.source_record_id,population=x.population_value,population_raw=x.population_raw,population_status='numeric_primary_archived_official' if numeric else 'literal_dash_NULL',source_name_raw=x.source_name_raw,source_path=str(W),source_sha256=pins[str(W)]['sha256'],source_locator='pub-01-03:row='+str(int(x.source_row)),native_code='',source_quality_original=x.population_value_quality))
 obs.append(dict(common,year=2021,source_record_id=x.current_2021_source_record_id,population=y.population,population_raw=str(int(y.population)),population_status='actual_selected_native_2021',source_name_raw=r.object_name,source_path=str(RAW),source_sha256=pins[str(RAW)]['sha256'],source_locator='parquet:row_1based='+x.current_2021_source_record_id.rsplit(':',1)[1],native_code=r.oktmo,source_quality_original='existing_selected_native_source_quality_unchanged'))
 credits.append({'source_record_id':x.current_2021_source_record_id,'population_2021':int(y.population),'population_2014':x.population_value,'numeric_2014':numeric,'accepted_scoped_identity':True,'existing_accepted_ownpoint':has,'complete_numeric_available_census_pair':numeric and has,'population_2014_presence_NULL':not numeric,'settlement_name':x.settlement_name})
# Territorial source rows kept separate; no NP or boundary-equivalence inference.
f=pd.read_parquet(F);sid='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:121540';fy=f[f.source_record_id.eq(sid)].iloc[0]
sev=sel[sel.source_record_id.eq(sid)].iloc[0];assert sev.population==547820 and sev.population_scope=='federal_city_region'
assert ws.cell(1322,1).value=='Город Севастополь' and ws.cell(1322,2).value==393304
for year,pop,sourceid,sourcefile,locator in [(2014,393304,'2014:Q127387785:pub-01-03:1322',W,'pub-01-03:row=1322'),(2021,547820,sid,RAW,'parquet:row_1based=121540')]:
 obs.append({'place_current_source_record_id':sid,'settlement_name':'Севастополь','grain':'federal_city_whole_territory','Russian_2002_status':'outside_scope','Russian_2010_status':'outside_scope','strict_NP3_eligible':False,'boundary_comparability':'unknown_not_asserted','coordinate_basis':'approved_2021_federal_territory_reference_only_no_2014_point_identity_or_boundary_claim','point_reference_target_id':sid if year==2021 else '', 'existing_identity_review_status':'same_named_source_scope_context_only_not_NP_identity_admission','year':year,'source_record_id':sourceid,'population':pop,'population_raw':str(pop),'population_status':'numeric_primary_archived_official' if year==2014 else 'actual_selected_native_2021','source_name_raw':'Город Севастополь' if year==2014 else 'г. Севастополь','source_path':str(sourcefile),'source_sha256':pins[str(sourcefile)]['sha256'],'source_locator':locator,'native_code':'' if year==2014 else '67000000','source_quality_original':'exact_literal_federal_whole_territory_only'})
f[f.source_record_id.eq(sid)].to_csv(Z/'approved_federal_territory_point_reference.csv.gz',index=False,compression={'method':'gzip','mtime':0})
pd.DataFrame(obs).to_csv(Z/'actually_available_census_observations.csv.gz',index=False,compression={'method':'gzip','mtime':0})
c=pd.DataFrame(credits);c.to_csv(Z/'native_2021_available_calendar_coverage.csv.gz',index=False,compression={'method':'gzip','mtime':0})
controls={'Crimea2021':1934630,'Sevastopol2021':547820,'Crimea2014':ws.cell(8,2).value,'Sevastopol2014':393304}
assert sel[sel.census_year.eq(2021)&sel.region_norm.eq('крым')].population.sum()==1934630
conf=Path('/workspace/russian-settlements-research/research_rebuild/evidence/native_mass_raw_roster_point_corrections_20261008/explicit_other_published_NP_point_binding_candidates.csv.gz');pins[str(conf)]={'sha256':sha(conf),'bytes':conf.stat().st_size}
cf=pd.read_csv(conf);intersection=set(cf.source_record_id)&set(c.source_record_id);assert not intersection
receipt={'status':'frozen_reconciliation_existing_accepted_scoped_layer_no_graph_or_population_write','existing_layer_review_state':'initial994 root scoped2014 application plus root accepted supplemental22; point provenance reconciled source ledger; no blanket new provider verification','controls':controls,'Crimea':{'actual_2014_rows':1016,'numeric_2014_rows':int(c.numeric_2014.sum()),'literal_dash_NULL_2014_rows':int((~c.numeric_2014).sum()),'numeric_2014_population_all':int(c.population_2014.sum()),'accepted_identity_unique_current2021_rows':len(c),'accepted_identity_current2021_population':int(c.population_2021.sum()),'ownpoint_paths_current2021_rows':int(c.existing_accepted_ownpoint.sum()),'ownpoint_paths_current2021_population':int(c.loc[c.existing_accepted_ownpoint,'population_2021'].sum()),'numeric2014_and_ownpoint_complete_pairs':int(c.complete_numeric_available_census_pair.sum()),'complete_pair_population_2014':int(c.loc[c.complete_numeric_available_census_pair,'population_2014'].sum()),'complete_pair_population_2021':int(c.loc[c.complete_numeric_available_census_pair,'population_2021'].sum()),'NULL2014_presence_with_ownpoint_current2021_population':int(c.loc[~c.numeric_2014&c.existing_accepted_ownpoint,'population_2021'].sum()),'current_provider_conflict_union_intersection':0},'Sevastopol':{'2014_population':393304,'2021_population':547820,'grain':'federal_city_whole_territory','approved_2021_territory_point':True,'proper_NP_series_created':False,'2014_point_or_boundary_equivalence_asserted':False,'ownNP_children_current2021_population':None},'source_population_modified':False,'fresh_network_used':False,'strict_NP3_gain':0,'original_mixed_or_formation_metrics_modified':False,'additional_identity_or_point_admissions':0,'limits':['Existing accepted review status retained; this packet does not certify all source providers anew or alter native quality.','2014 numerically known pairs and NULL-presence paths must be reported separately.','Current review overlays can remove previously accepted points; this packet pins the existing scoped review state and has zero overlap with the frozen 747 explicit current provider-conflict union.','Sevastopol federal whole territory is a separate scope, not an atomic city count or child-NP allocation.','2014 source reference date is year only; historical measurements and boundary equivalence unknown.']}
receipt['Crimea']['complete_pair_2021_share_of_full_region_percent']=100*receipt['Crimea']['complete_pair_population_2021']/1934630
receipt['Crimea']['ownpoint_available_path_2021_share_of_full_region_percent']=100*receipt['Crimea']['ownpoint_paths_current2021_population']/1934630
(Z/'source_pins.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n')
(Z/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
verify={'source_2014_literal_rows_replayed':1016,'literal_numeric_and_dash_NULL_preserved':True,'source_2021_native_typed_NP_and_pop_rows_replayed':1016,'unique_2014_and_2021_sourceIDs':True,'identity_decision_status_accepted_not_legacy_candidate_flag':True,'primary_source_TLS_receipt_status':json.loads((W.parent/'gks_2014_get_receipt.json').read_text()).get('tls_validation'),'no_current_explicit_provider_conflicts':True,'source_metadata_counts_or_graph_changed':False,'Sevastopol_row1322_whole_territory_verified':True}
(Z/'verification_receipt.json').write_text(json.dumps(verify,ensure_ascii=False,indent=2)+'\n')
manifest={f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(Z.iterdir()) if f.is_file() and f.name!='asset_manifest.json'}
(Z/'asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2));print('bytes',sum(f.stat().st_size for f in Z.iterdir() if f.is_file()),'manifestSHA',sha(Z/'asset_manifest.json'))

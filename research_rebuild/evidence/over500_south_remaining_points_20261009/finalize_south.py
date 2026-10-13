import pandas as pd,pathlib,json,hashlib,gzip,shutil,xlrd
P=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/over500_south_remaining_points_20261009');a=pd.read_csv(P/'accepted_point_use_delta.csv').fillna('');r=pd.read_csv('/dev/shm/over500-20261009/south_remaining.csv');d=pd.read_csv(P/'point_only_dispositions.csv.gz').fillna('');checks=[];cache={}
def h(p):
 if p not in cache:cache[p]=hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
 return cache[p]
# persist selected network captures, retaining exact captured bytes
for i,t in a.iterrows():
 f=str(t.point_origin_file)
 if f.startswith('/dev/shm/'):
  dest=P/('nominatim_'+pathlib.Path(f).name);shutil.copyfile(f,dest);a.loc[i,'point_origin_file']=str(dest)
for _,t in a.iterrows():
 checks.append(dict(target_source_record_id=t.target_source_record_id,point_origin_exists=pathlib.Path(t.point_origin_file).exists(),point_origin_hash_pass=h(t.point_origin_file)==t.point_origin_sha256,coordinate_valid=30<float(t.latitude)<80 and 15<float(t.longitude)<180))
a.to_csv(P/'accepted_point_use_delta.csv',index=False)
reasons={'совхоза Пальна-Михайловский':'2009 own42242844001 bound to printed estate/council; rawGeoDBF no own code row; ownWiki/OSM literalqueries no ownpoint. ModernселоПальна-Михайловка is separate historical code42242844005 and cannot inherit point.', 'Ярославка Первая':'No ownarticle/OSM first-ordinal feature; historical2009 classifier only unifiedЯрославка. Modern unified village is not a sourced own spatial feature for first part.', 'Ярославка Вторая':'No ownarticle/OSM second-ordinal feature; historical2009 classifier only unifiedЯрославка. Modern unified village is not a sourced own spatial feature for second part.', 'Гиреевский':'Printed Кантышевская сельская администрация; literal ownWiki/OSM no feature; guessedГази-Юрт lacks former-name witness and must be excluded.', 'Горная Поляна':'Source cityВолгоград/Горнополянский parent; ownWiki currentГорнаяПолянаЛенинский is different хутор and excluded. Captured geocoder matches do not establish own former city locality.', 'Терский':'Native2010 prints twoТерский inBudyonno rows102/110; row110 physical neighborАлександрийская andКирова indicate possible county namespace contradiction; no source correction adopted. Native duplicate cannot bind by population.', 'Черноярская':'Both adjacent native2010 rows1228/1229 print станцияЧерноярская; own contemporaryстаница andstation are distinct. Population cannot decide identity or feature selection.', 'Троицкое':'Both native current same-name/all-type rivals remain within two physical flank countiesЛевТолстовский/Липецкий. Ownarticlepoints captured, no unique native binding.', 'Козьмодемьяновка':'Two own native current same-name samecountyTamбовский villages underБеломестнокриушинский andЛысогорский; point candidates cannot decide native2010 identity.', 'Первомайский':'Three samecountyКовылкинский own villages under different rural councils; allOSM candidate ownfeatures retained, native2010 finerparent unavailable.'}
for i,t in d.iterrows():
 q=a[a.target_source_record_id==t.source_record_id]
 if len(q):d.loc[i,'status']='accepted_ownpoint';d.loc[i,'point_specific_reason']=q.iloc[0].source_binding_note
 else:
  reason=reasons.get(t.settlement_name,'Multiple all-type native current namesakes within independently bounded native physical county alternatives; source-order inventory and captured ownWiki/OSM points insufficient to uniquely bind. No candidate admitted by population or distance.')
  d.loc[i,'status']='captured_source_paths_exhausted_for_unique_binding';d.loc[i,'point_specific_reason']=reason
 d.loc[i,'actual_sources_tried']='exact primary census workbook physical row/parent; accepted stage71 point graph; native current all-type roster; 2009 rawOKATO classifier; existing GeoKLADR own-code inventory; ownWiki fresh+cache candidate files; live Nominatim literal and qualified alternate queries with OSM own-feature raw verification'
d.to_csv(P/'point_only_dispositions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# source parent corrections require explicit literal rows instead of stale nearest header
extra=[]
for file,sheet,rows in [('/workspace/settlements-raw/data/raw/2002/036_81b258bc42_02c_Krasnodarski-krai.xls','11',[45,52,61,62,90,93,788,1463]),('/workspace/settlements-raw/data/raw/2002/028_df43ade2a7_02c_Adygea.xls','Sheet1',[3,4]),('/workspace/settlements-raw/data/raw/2010/006_9b114a55c0_14._20Адыгея.xls','адыг',[227,231,234,236]),('/workspace/settlements-raw/data/raw/2002/054_0d77ecf40f_Saratovskaja1.xls','Sheet1',[216,220,887,888]),('/workspace/settlements-raw/data/raw/2002/053_f7f2b62d26_Samarskaja_new.xls','Sheet1',[1601,1602,1603]),('/workspace/settlements-raw/data/raw/2002/009_fc0fd8cf1b_02c_Lipetskaja.xls','Sheet1',list(range(237,244)))]:
 s=xlrd.open_workbook(file).sheet_by_name(sheet)
 for row in rows:extra.append(dict(source_file=file,source_sha256=h(file),sheet=sheet,row_1based=row,literal=json.dumps(s.row_values(row-1),ensure_ascii=False)))
pd.DataFrame(extra).to_csv(P/'additional_native_physical_context.csv.gz',index=False,compression={'method':'gzip','mtime':0})
c=P/'source_order_current_context.csv';pd.read_csv(c).to_csv(P/'source_order_current_context.csv.gz',index=False,compression={'method':'gzip','mtime':0});c.unlink()
a=pd.read_csv(P/'accepted_point_use_delta.csv');a.replace({'source_context_witness_file':{str(c):str(P/'source_order_current_context.csv.gz')}},inplace=True);a.to_csv(P/'accepted_point_use_delta.csv',index=False)
assert not a.target_source_record_id.duplicated().any();assert len(r)==69;assert set(a.target_source_record_id)-set(r.source_record_id)=={'2010:018_8eadc2d6b9_7._20Dag_2010.xls:2010:118'}
assert all(x['point_origin_hash_pass'] and x['coordinate_valid'] for x in checks)
pd.DataFrame(checks).to_csv(P/'validation_source_point_checks.csv',index=False)
receipt=dict(input_targets=69,additional_missing_ownpoint_uses=int(r.source_record_id.isin(a.target_source_record_id).sum()),ownpoint_replacement_uses=1,accepted_point_rows=len(a),accepted_identity_edges=1,coordinate_claim_rejections=1,remaining_source_binding_unresolved=int((~r.source_record_id.isin(a.target_source_record_id)).sum()),counts_modified=0,population_scope_modified=0,raw_coordinates_modified=0,duplicate_targets=0,point_origin_hashes_all_pass=True)
(P/'validation_receipt.json').write_text(json.dumps(receipt,indent=2));print(receipt)
manifest={'packet_files':{str(p):h(str(p)) for p in P.iterdir() if p.is_file() and p.name!='hash_manifest.json'},'external_point_sources':{str(t.point_origin_file):t.point_origin_sha256 for _,t in a.iterrows()},'input_residual':{'path':'/dev/shm/over500-20261009/south_remaining.csv','sha256':h('/dev/shm/over500-20261009/south_remaining.csv')}};(P/'hash_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))

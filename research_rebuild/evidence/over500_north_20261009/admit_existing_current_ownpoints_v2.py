from pathlib import Path
import pandas as pd,json,sys,hashlib,re,collections,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;S=Path('/dev/shm/settlements-stage71-20261009');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
f=pd.read_parquet(S/'applied_state_observations.parquet').fillna('');f['county_key']=f.district_raw.map(county_key);b=f.set_index('source_record_id');p=pd.read_parquet(S/'applied_point_snapshot.parquet',columns=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']).fillna('').drop_duplicates('target_source_record_id').set_index('target_source_record_id').to_dict('index');w=pd.read_csv(O/'direct_native_witnesses.csv.gz').fillna('').set_index('source_record_id').to_dict('index');q=R/'research_rebuild/evidence/over500_north_supplemental_native_20261009/recovered_direct_native_witnesses.csv';w.update(pd.read_csv(q).fillna('').set_index('source_record_id').to_dict('index'));a=pd.read_csv(O/'assignment.csv').fillna('');base={str(x):sha(x) for x in [q,S/'applied_state_observations.parquet',S/'applied_point_snapshot.parquet',O/'direct_native_witnesses.csv.gz']};existing=set()
for n in ['accepted_point_use_delta.csv','supplemental_accepted_point_use_delta.csv','supplemental_accepted_point_use_delta_v2.csv']:
 t=pd.read_csv(O/n);existing.update(t.target_source_record_id)
existing.update(pd.read_csv(O/'current_carrier_accepted_point_use_delta.csv').target_source_record_id)
context=pd.read_csv(O/'native_county_context.csv').fillna('').set_index('source_record_id').to_dict('index');rows=[];review=[];rf=pd.read_parquet('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet',columns=['object_name','population','oktmo','mun_upper','mun_lower']);meta=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',columns=['source_record_id','source_row','source_file','source_name_raw']).fillna('').set_index('source_record_id');rawpath=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');base[str(rawpath)]=sha(rawpath)
# Independently recover EVERY Kaliningrad native2010 primary namesake from physical sheet4 hierarchy, not a restricted >500 target set.
kbook=xlrd.open_workbook('/workspace/settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx') if False else None
import openpyxl
kpath=Path('/workspace/settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx');wb=openpyxl.load_workbook(kpath,data_only=True,read_only=True);sh=wb['4'];kalrows=[];county='';sub=''
for rn,vals in enumerate(sh.iter_rows(values_only=True),1):
 non=[str(x).strip() for x in vals if x is not None and str(x).strip()];text=' '.join(non)
 if 'район' in normalize(text) or 'городской округ' in normalize(text):
  raw=next((str(x).strip() for x in vals if isinstance(x,str) and ('район' in normalize(x) or 'городской округ' in normalize(x))), '')
  if raw:
   county=county_key(raw).removeprefix('сельские ');county=re.sub(r'ского$','ский',county);county=re.sub(r'цкого$','цкий',county);sub=''
 if 'сельское поселение' in normalize(text) or 'городское поселение' in normalize(text):sub=next((str(x).strip() for x in vals if isinstance(x,str) and 'поселение' in normalize(x)), '')
 if any(re.match(r'^п(?:ос[её]лок|\.)\s+',str(x).strip(),re.I) for x in vals if isinstance(x,str)):
  lab=next(str(x).strip() for x in vals if isinstance(x,str) and re.match(r'^п(?:ос[её]лок|\.)\s+',str(x).strip(),re.I));name=normalize(re.sub(r'^п(?:ос[её]лок|\.)\s+','',lab,flags=re.I));kalrows.append({'row':rn,'name':name,'county':county,'parent':sub,'raw_label':lab})
# Most labels are plain settlement names incolB; handled by exact native source witnesses below only when no parsed typed rows.
for z in a[a.has_ownpoint==False].to_dict('records'):
 sid=z['source_record_id']
 if sid in existing or sid not in w:continue
 nw=w[sid];why=[];ck=county_key(z['district_raw']) or county_key(nw.get('actual_printed_county','')) or context.get(sid,{}).get('county','');name=z['name_norm'];typ=normalize(nw.get('raw_source_type') or z['type_norm']);typed_note=''
 if not nw['literal_label_population_passed']:why.append('own raw native leaf/count not reopened')
 if not ck:why.append('sourcecounty unknown for current source-point reuse')
 cur=f[(f.census_year==2021)&(f.region_norm==z['region_norm'])&(f.name_norm==name)&(f.county_key==ck)]
 # Native literal object-kind disambiguates a samecounty village from distinct named poselok; preserve any imported type discrepancy.
 curtyped=cur[cur.type_norm==typ]
 if len(curtyped)!=1:why.append('no unique exact named typed current owncode in nativecounty')
 if len(curtyped)==1:
  donor=curtyped.iloc[0];dsid=donor.source_record_id
  if dsid not in p:why.append('matching current own native leaf lacks independently accepted ownpoint')
  if sid.startswith('KAL2010:'):
   kk=[x for x in kalrows if x['name']==name and x['county']==ck]
   if len(kk)!=1:why.append('full original2010county typed namesake not unique')
  else:
   old=f[(f.census_year==z['census_year'])&(f.region_norm==z['region_norm'])&(f.name_norm==name)&(f.type_norm==z['type_norm'])]
   possible=[i for i in old.source_record_id if i==sid or not county_key(b.loc[i,'district_raw']) or county_key(b.loc[i,'district_raw'])==ck]
   if len(possible)>1:why.append('historical typed sourcecounty namesake unresolved')
  if dsid in meta.index:
   rr=rf.iloc[int(meta.loc[dsid,'source_row'])-1];match=normalize(rr.object_name)==normalize(meta.loc[dsid,'source_name_raw']) and float(rr.population)==float(donor.population) and str(rr.oktmo)==str(donor.oktmo)
   if not match:why.append('reopened native2021 owncode/name/count mismatch')
  else:why.append('current donor raw primary metadata missing')
  if nw.get('raw_source_type') and normalize(nw['raw_source_type'])!=normalize(z['type_norm']):typed_note='Actual original native type '+nw['raw_source_type']+' binds the same own physical locality; imported selected type '+str(z['settlement_type'])+' discrepancy explicitly preserved. No type repair, identity edge or count change.'
 else:dsid='';rr=None
 review.append({'target_source_record_id':sid,'name':z['settlement_name'],'native_county':ck,'raw_native_type':typ,'typed_current_namesake_ids_json':json.dumps(curtyped.source_record_id.tolist()),'alltype_current_namesake_ids_json':json.dumps(cur.source_record_id.tolist()),'donor_native_primary_row_json':json.dumps(rr.to_dict(),ensure_ascii=False,default=str) if rr is not None else '', 'disposition':'hold:'+ ';'.join(why) if why else 'accepted_current_ownpoint_continuity_only','type_discrepancy_retained':typed_note})
 if why:continue
 cp=p[dsid];originfile=Path(nw['source_file']);actualsha=sha(originfile);assert actualsha==nw['source_sha256'];base[str(originfile)]=actualsha
 pp={k:cp[k] for k in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']};pp.update(target_source_record_id=sid,coordinate_source_record_id=dsid,coordinate_admission_status='reviewed_extension_rule_accepted',decision_status='checked_rule_accepted',admission_allowed=True,own_locality_point=True,recipient_point_assigned_to_child=False,source_sha256=actualsha,source_locator=nw.get('source_locator') or str(nw.get('source_sheet',''))+':'+str(nw.get('source_row','')),current_ownpoint_carrier_source_record_id=dsid,donor_accepted_point_ledger=cp['point_ledger_path'],native_current_own_OKTMO=donor.oktmo,admission_rule='Original historical native own locality leaf/type/count and explicit physical county independently reopened; full sourcecounty typed namesake screen; unique current literal native own locality name/type/county and own fullcode verified in original2021 source; reuse independently accepted current ownpoint by explicit retrospective continuity inference. Point only, no identity edge or population/boundary equivalence. '+typed_note,point_temporal_interpretation='Modern representative physical own locality point reused historically by explicit continuity inference; direct censusday coordinate measurement and boundaries unknown.',native_population_quality_preserved=True,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,type_discrepancy_retained=typed_note);rows.append(pp)
pd.DataFrame(rows,columns=None if rows else ['target_source_record_id','latitude','longitude','coordinate_admission_status']).to_csv(O/'current_carrier_accepted_point_use_delta_v2.csv',index=False);pd.DataFrame(review).to_csv(O/'current_carrier_point_review_v2.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(kalrows).to_csv(O/'kal2010_all_typed_native_county_namesakes_v2.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'current_carrier_point_manifest_v2.json').write_text(json.dumps({'status':'accepted_ownpoint_only_packet','new_points':len(rows),'identity_edges':0,'input_pins':base,'output_pins':{str(x):sha(x) for x in [O/'current_carrier_accepted_point_use_delta_v2.csv',O/'current_carrier_point_review_v2.csv.gz',O/'kal2010_all_typed_native_county_namesakes_v2.csv.gz']},'population_quality_modified':False},ensure_ascii=False,indent=2));print('newpoints',len(rows),[(b.loc[x['target_source_record_id'],'settlement_name'],b.loc[x['target_source_record_id'],'region_norm']) for x in rows]);print('kalphysicaltypedrows',len(kalrows))

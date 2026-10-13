from pathlib import Path
import pandas as pd,json,hashlib,xlrd,re,math
O=Path(__file__).parent
state=Path('/workspace/scratch/residual-20261013/final/applied_state_observations.parquet')
point=Path('/workspace/scratch/residual-20261013/final/applied_core_point_snapshot.parquet')
f=pd.read_parquet(state);b=f.set_index('source_record_id');p=pd.read_parquet(point).set_index('source_record_id')
sha=lambda q:hashlib.sha256(Path(q).read_bytes()).hexdigest()
cases=[('Совхоз Чаусово','2002:006_1916564aaa_02c_Kaluzhskaja.xls:Sheet1:1036','2010:013_f60b2d2bcf_5._20Belg_Bryan_Vlad_Voron_Ivanov_Kalug_20L1_ethn_2010.xls:Data Sheet:12460',0,'https://ru.wikipedia.org/wiki/Совхоз_«Чаусово»','Geography explicitly distinguishes sovkhoz selo from separate village Chausovo 612m north; own current administrative-center site and 2002 Chausovsky roster have one settlement Chausovo and one distinct village. Ordinary settlement/selo labels retained as different census labels; no competing sovkhoz object.'),('совхоза Сулакский','2002:014_32646337ea_02c_Tambovskaja.xls:Sheet1:2138','2010:011_040325482b_3._20Ryaz_Smol_Tambov_Tula_Jaroslavl_20L1_20ethn_2010.xls:Data Sheet:9315',9,'https://ru.wikipedia.org/wiki/Посёлок_совхоза_«Сулакский»','Explicit current own-site article attributes 2002 924 population/97% Russian to settlement sovkhoza Sulaksky. Original 2002 row is central estate924/97%, sole administrative center of Sulaksky rural council, whose same other four leaves distinguish village Sulak. The additional words central estate are the alias interpretation, not a manufactured native value.')]
edges=[];w=[];rows=[];reviews=[]
for label,a,z,wi,url,rule in cases:
 ids=f[f.root.isin([b.loc[a,'root'],b.loc[z,'root']])].source_record_id.tolist();v=f[f.source_record_id.isin(ids)].sort_values('census_year');assert v.census_year.tolist()==[2002,2010,2021]
 assert all(i in p.index for i in ids)
 reviews.append({'case':label,'status':'proposed_root_review','years':','.join(map(str,v.census_year)),'populations':','.join(map(str,v.population)),'component_source_ids_json':json.dumps(ids),'all_three_existing_accepted_ownpoints':True,'rule':rule})
 for sid in ids:
  row=b.loc[sid].to_dict();row['source_record_id']=sid;rows.append(row)
  x={'case':label,'source_record_id':sid,'native_name':row['settlement_name'],'native_type':row['settlement_type'],'native_count':row['population'],'native_quality':row['population_value_quality'],'accepted_point_json':json.dumps(p.loc[sid].to_dict()),'external_url':url,'external_html':str(O/f'wiki_{wi}.html'),'external_html_sha256':sha(O/f'wiki_{wi}.html'),'external_locator':'Geography and administrative-center own-site description' if wi==0 else 'National composition paragraph explicitly identifying 2002 924/97%; own-site introduction'}
  m=re.match(r'(2002|2010):([^:]+\.xls):(.+):(\d+)$',sid)
  if m:
   y,fn,sheet,rr=m.groups();q=Path('/workspace/settlements-raw/data/raw')/y/fn;bk=xlrd.open_workbook(str(q));ss=bk.sheet_by_index(int(sheet)) if sheet.isdigit() else bk.sheet_by_name(sheet);rr=int(rr);x.update(raw_file=str(q),raw_sha256=sha(q),raw_locator=f'Excel {sheet} physical row {rr}',raw_cells_json=json.dumps(ss.row_values(rr-1),ensure_ascii=False),raw_context_json=json.dumps([{'physical_row':j+1,'cells':ss.row_values(j)} for j in range(max(0,rr-4),min(ss.nrows,rr+12))],ensure_ascii=False))
  else:x.update(raw_file=row['source_file'],raw_sha256=row['source_sha256'],raw_locator=sid)
  
  if wi==0:x.update(official_url='http://chausovo.ru/information/history.html',official_html=str(O/'web_15.html'),official_html_sha256=sha(O/'web_15.html'),official_locator='History final two paragraphs: municipal roster contains с. Чаусово and д. Чаусово separately; center is село Совхоз Чаусово; dated page creation 03.12.2013')
  w.append(x)
 edges.append({'from_source_record_id':a,'to_source_record_id':z,'relation':'same_place','decision_status':'checked_rule_accepted','case':label,'admission_rule':rule+' Full native regional roster screened. Existing observed three census years and accepted ownpoints retained. No merger, census coordinate, unchanged boundary or population comparability claim.','source_context_witness_file':str(O/'source_witnesses.csv.gz'),'boundary_comparability_asserted':False,'historical_census_coordinate_asserted':False})
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False)
pd.DataFrame(reviews).to_csv(O/'reviews.csv',index=False)
pd.DataFrame(rows).to_csv(O/'frozen_observations.csv.gz',index=False,compression={'method':'gzip','mtime':0})
pd.DataFrame(w).to_csv(O/'source_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0})
manifest={'status':'bounded_alias_packet_for_root_review','case_count':len(cases),'edge_count':len(edges),'input_hashes':{str(q):sha(q) for q in [state,point]},'output_hashes':{str(O/q):sha(O/q) for q in ['accepted_identity_edge_delta.csv','reviews.csv','frozen_observations.csv.gz','source_witnesses.csv.gz','name_candidates.csv']},'external_hashes':{str(q):sha(q) for q in [O/'wiki_0.html',O/'wiki_9.html',O/'web_15.html']},'new_population_values':False,'generic_two_year_credit':False,'merger_union_find':False}
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print(pd.DataFrame(reviews).to_string(index=False))

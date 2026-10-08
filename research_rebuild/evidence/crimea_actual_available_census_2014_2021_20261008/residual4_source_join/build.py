from pathlib import Path
import pandas as pd,openpyxl,json,hashlib,re,datetime,unicodedata
Z=Path(__file__).parent
W=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/gks_2014_perepis_krim_pub-01-03_wayback_20150924.xlsx')
R=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
T=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
B=Z.parent
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
cols=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population','settlement_dadata','settlement_type_full_dadata','fias_id_dadata','fias_level_dadata','oktmo_dadata','latitude_dadata','longitude_dadata']
r=pd.read_parquet(R,columns=cols);ws=openpyxl.load_workbook(W,data_only=True).active
wiki=json.loads((Z/'rodnik_current_wiki.json').read_text())['entities']['Q4395945'];article=json.loads((Z/'kizil_current_article.json').read_text())['query']['pages'][0];rev=article['revisions'][0];txt=rev['slots']['main']['content']
aliastext="".join(c for c in unicodedata.normalize("NFD",txt) if not unicodedata.combining(c))
assert "до 2012 года '''Кизиловка'''" in aliastext and 'Перовское сельское поселение' in txt and 'Симферопольский район' in txt
v=lambda p:[x['mainsnak'].get('datavalue',{}).get('value') for x in wiki['claims'].get(p,[])]
assert '35647458101' in v('P764') and any(x.get('id')=='Q532' for x in v('P31')) and any(x.get('id')=='Q12148266' for x in v('P131'))
assert not any(wiki['claims'].get(p) for p in ['P155','P156','P576'])
ts=pd.read_csv(T,sep='\t');tsmatch=ts[ts['?oktmo'].astype(str).str.contains('35647458101')];assert len(tsmatch)==1 and 'Родниковское сельское поселение' in str(tsmatch.iloc[0]['?adminLabel'])
spec=[(50059,962,'Раздольное','пгт','Раздольненский','Раздольненское',True),(50287,1165,'Кизиловое','село','Симферопольский','Перовское',True),(50304,1187,'Родниковое','село','Симферопольский','Родниковское',True),(49854,733,'Заветное','село','Ленинский','Заветненское',False)]
# Parse literal printed hierarchy; no carry-over into Sevastopol.
old=[];county='';parish='';region=''
for i,row in enumerate(ws.values,1):
 caption=str(row[0] or '');norm=' '.join(caption.split())
 if norm=='Республика Крым':region=norm
 if norm=='Город Севастополь':region=norm;county='';parish=''
 if 'муниципальный район' in norm:county=norm
 if 'сельское поселение' in norm or norm.startswith('Городское поселение'):parish=norm
 m=re.match(r'^(село|пгт|поселок|г\.)\s+(.+?)\s*(?:\(цмр\))?$',norm)
 if m:old.append({'row':i,'caption_literal':caption,'name':re.sub(r'\s*\(цмр\)$','',m.group(2)),'type':m.group(1),'region':region,'county':county,'parish':parish,'population_raw':row[1]})
obs=[];edges=[];points=[];witness=[];rivals=[]
for nr,pr,name,ty,cop,pap,new in spec:
 x=r.iloc[nr-1];s=[o for o in old if o['row']==pr][0]
 aliases={name,'Кизиловка'} if name=='Кизиловое' else {name}
 assert s['name'] in aliases and s['type']==ty and s['region']=='Республика Крым' and cop in s['county'] and pap in s['parish']
 assert x.object_level=='Населенный пункт' and x.region=='Республика Крым' and cop in x.mun_upper and pap in x.mun_lower and x.object_name==ty+' '+name
 matches=[o for o in old if o['name'] in aliases and o['region']=='Республика Крым' and cop in o['county'] and pap in o['parish']];assert len(matches)==1
 cur=r[r.object_level.eq('Населенный пункт') & r.region.eq('Республика Крым') & r.mun_upper.eq(x.mun_upper) & r.mun_lower.eq(x.mun_lower) & r.object_name.eq(x.object_name)];assert len(cur)==1
 for y in old:
  if y['name'] in aliases:rivals.append(dict(y,for_current_native_row=nr,selection=y['row']==pr))
 cur_name=r[r.object_level.eq('Населенный пункт') & r.object_name.astype(str).str.replace(r'^(село|пгт|поселок|город|г\.)\s+','',regex=True).isin(aliases)]
 for iy,y in cur_name.iterrows():rivals.append({'for_current_native_row':nr,'current_source_row':iy+1,'name':y.object_name,'region':y.region,'county':y.mun_upper,'parish':y.mun_lower,'native_code':y.oktmo,'population_raw':y.population,'selection':iy==nr-1})
 sid='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(nr);oldid='2014:Q127387785:pub-01-03:'+str(pr)
 if nr!=50304:
  assert str(int(float(x.oktmo_dadata)))==str(x.oktmo) and x.settlement_dadata==name and x.settlement_type_full_dadata==('поселок городского типа' if ty=='пгт' else 'село') and str(x.fias_level_dadata)=='6'
  assert r[r.object_level.eq('Населенный пункт')&r.oktmo.eq(x.oktmo)].shape[0]==1
  lat,lon=x.latitude_dadata,x.longitude_dadata;origin=R;loc='parquet:row_1based='+str(nr)+';latitude_dadata,longitude_dadata';proof='exact published native OKTMO/provider OKTMO + own literal name/type/FIAS6 + printed county/parish; raw values unchanged'
 else:
  c=v('P625');assert len(c)==1;lat,lon=c[0]['latitude'],c[0]['longitude'];origin=Z/'rodnik_current_wiki.json';loc='entities.Q4395945.claims.P625[0]';proof='physical P31 Q532 + exact native P764 + P131 own parish Q12148266, cached TSV parish label; native14 and21 exact name/typed NP; Wiki label Родниково distinct source spelling retained'
 common={'source_2014_record_id':oldid,'current_2021_source_record_id':sid,'name_current_native':name,'current_native_code':x.oktmo,'native2014_code':None,'native2014_code_asserted':False,'source2014_caption_literal':s['caption_literal'],'source2014_county_literal':s['county'],'source2014_parish_literal':s['parish'],'current2021_name_raw':x.object_name,'current2021_county':x.mun_upper,'current2021_parish':x.mun_lower,'current2021_population':int(x.population),'latitude':lat,'longitude':lon,'point_origin_file':str(origin),'point_origin_sha256':sha(origin),'point_origin_locator':loc,'ownpoint_proof':proof,'proper_NP_grain':True,'identity_date':'UNKNOWN','coordinate_measurement_date':'UNKNOWN','historical_measurement_claimed':False,'boundary_comparability':'UNKNOWN','Russian2002':'outside_scope','Russian2010':'outside_scope','strictNP3_gain':0,'alias_binding':"documented Wikipedia literal former name Кизиловка; source2014 retains alias; rename primary effective date not asserted" if nr==50287 else 'exact literal native14/native21 own name'}
 witness.append(common)
 if new:
  obs.append(dict(common,source_record_id=oldid,year=2014,population=int(s['population_raw']),population_raw=s['population_raw'],population_quality='exact_primary_archived_Rosstat_literal_NP_row',source_file=str(W),source_sha256=sha(W),source_locator='pub-01-03:row='+str(pr),admission_status='reviewed_available_calendar_primary_scoped_observation'))
  edges.append({'from_source_record_id':oldid,'from_year':2014,'to_source_record_id':sid,'to_year':2021,'relation':'same_physical_place_scoped_available_calendar','decision_status':'reviewed_available_calendar_identity_accepted','native_source_hierarchy_exact':True,'alias_documented':nr==50287,'source_population_modified':False,'strictNP3_eligible':False,'boundary_comparability_asserted':False})
 points.append(dict(common,target_source_record_id=oldid,target_year=2014,coordinate_admission_status='reviewed_rule_accepted',coordinate_temporal_basis='modern_own_representative_point_retrospective_physical_continuity_inference_date_UNKNOWN'))
# Current point reference for Rodnikovoe and Zavetnoe is explicit; graph root61 is not edited.
for nr in [50304,49854]:
 c=[w for w in witness if w['current_2021_source_record_id'].endswith(':'+str(nr))][0]
 points.append(dict(c,target_source_record_id=c['current_2021_source_record_id'],target_year=2021,coordinate_admission_status='reviewed_rule_accepted',coordinate_temporal_basis='modern_own_representative_point_measurement_date_UNKNOWN'))
for name,data in [('accepted_scoped_2014_observation_delta.csv.gz',obs),('accepted_scoped_identity_delta.csv.gz',edges),('accepted_available_calendar_point_use_delta.csv.gz',points),('native_source_and_point_witnesses.csv.gz',witness),('all_literal_name_type_rivals.csv.gz',rivals)]:pd.DataFrame(data).to_csv(Z/name,index=False,compression={'method':'gzip','mtime':0})
base=json.loads((B/'application_receipt.json').read_text());after=base['Crimea']['complete_pair_population_2021']+sum(w['current2021_population'] for w in witness)
receipt={'status':'frozen_reviewed_available_calendar_only_source_join_not_applied_to_ROOT61','cases':4,'accepted_new_primary2014_observations':3,'existing2014_observation_reused':1,'accepted_scoped_identity_edges':3,'accepted_2014_retrospective_point_uses':4,'current_own_point_references':2,'new2014_numeric_population':sum(o['population'] for o in obs),'available_calendar_complete_numeric_pair_current2021_gain':sum(w['current2021_population'] for w in witness),'complete_numeric_pairs_after':1008,'numeric_primary2014_population_after':1879941+sum(o['population'] for o in obs),'primary2014_whole_Crimea_control':1891465,'all_available_presence_paths_including_NULL_current2021_population_after':1934630,'all_available_presence_paths_including_NULL_current2021_unique_rows_after':1019,'complete_numeric_pair_current2021_population_before':base['Crimea']['complete_pair_population_2021'],'complete_numeric_pair_current2021_population_after':after,'whole_Crimea2021_control':1934630,'numeric_pair_current2021_gap_after':1934630-after,'NULL2014_presence_current2021_population_separate':68,'whole_Crimea2021_numeric_pair_percentage_after':100*after/1934630,'source_population_modified':False,'Russian2002_2010_outside_scope':True,'strictNP3_gain':0,'root_graph_modified':False,'historical_coordinate_measurements_claimed':False,'population_boundary_comparability_claimed':False,'point_rule':'one literal native primary2014 NP + own typed native21 exact county/parish uniqueness across all namesakes/types + independently owncoded modern point; documented exact alias only for Кизиловка','source_year2014_date_precision':'year_only','fresh_network_scope':'two successful normal TLS verified public APIs: Q4395945 actual physical entity properties and Kizilovoe actual revision; no network population counts used','Zavetnoe_Wiki_alternative_conflict':'cached TSV two P625 alternatives retained; selected modern Dadata literal owncode/FIAS6/name/type point45.1212613,36.3963233 corroborates one actualQcoordinate; no automatic first-coordinate selection','limits':['2014 has no native code in published workbook; none invented.','Sevastopol namesakes excluded by actual region and county.','Current federal whole territory observations never mixed with atomic NP rows.','Fresh Wikipedia documents alias; exact legal rename effective date is not primary-verified or asserted.']}
(Z/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
pins={str(f):{'sha256':sha(f),'bytes':f.stat().st_size} for f in [W,R,T,B/'application_receipt.json',Z/'rodnik_current_wiki.json',Z/'kizil_current_article.json']}
(Z/'source_pins.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n')
(Z/'verification_receipt.json').write_text(json.dumps({'primary_literal2014_leaf_rows_reopened':4,'native_current_typed_NP_and_all_namesakes':True,'exact_county_and_parish_unique_match':True,'own_native_codes_verified':4,'physical_Wiki_P31_verified_Rodnik':True,'Kizil_alias_literal_revision':rev['revid'],'Kizil_alias_revision_timestamp':rev['timestamp'],'all_populations_literal':True,'frozen_parent_unchanged':True,'fresh_network_TLS':'Python urllib default certificate verification; http200; no disabledTLS'},indent=2)+'\n')
m={f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in Z.iterdir() if f.is_file() and f.name!='asset_manifest.json'};(Z/'asset_manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2));print('bytes',sum(f.stat().st_size for f in Z.iterdir() if f.is_file()),'manifestSHA',sha(Z/'asset_manifest.json'))

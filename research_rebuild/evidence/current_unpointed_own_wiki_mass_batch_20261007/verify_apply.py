from pathlib import Path
import sys,json,gzip,re,urllib.request,urllib.parse,hashlib,time
import pandas as pd,duckdb
T=time.monotonic();R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;W=R/'research_rebuild/work/current_unpointed_own_wiki_mass_batch_20261007';A=R/'research_rebuild/evidence/current_unpointed_own_wiki_mass_application_20261007';A.mkdir(exist_ok=True);sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize,distance_km
s=load(17); inv=pd.read_csv(O/'own_current_inventory.csv').fillna('');pts=pd.read_csv(O/'candidate_points.csv').fillna('');ser=pd.read_csv(O/'candidate_actual_full3_series.csv').fillna('');x=pd.read_csv(W/'exact_code_candidates.csv.gz',dtype=str).fillna('');titles={}
for t in inv.itertuples():
 rr=x[(x.source_record_id==t.sid)&(x.qid==t.qid)].iloc[0];titles[t.qid]=urllib.parse.unquote(rr['?article'].strip('<>').rsplit('/wiki/',1)[-1]).replace('_',' ')
u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':'|'.join(titles.values()),'prop':'revisions|pageprops','rvprop':'ids|content','rvslots':'main','format':'json','redirects':1})
try:
 b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=25).read(2000000);wp=W/'own_articles.json.gz';wp.write_bytes(gzip.compress(b));pages=json.loads(b).get('query',{}).get('pages',{})
except Exception as ex:print('article fetch hold',ex);pages={}
byqid={p.get('pageprops',{}).get('wikibase_item'):p for p in pages.values()}
p=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');ph=sha(p);c=duckdb.connect(); checks=[];safe=set();hold=[]
for t in inv.itertuples():
 r=s.by_id.loc[t.sid];offset=int(t.sid.rsplit(':',1)[-1])-1;raw=c.execute('SELECT object_level,settlement,region,mun_upper,population,oktmo,okato_dadata,oktmo_dadata,settlement_type_full_dadata,latitude_dadata,longitude_dadata FROM read_parquet(?) LIMIT 1 OFFSET '+str(offset),[str(p)]).fetchdf().iloc[0].to_dict();rr=x[(x.source_record_id==t.sid)&(x.qid==t.qid)].iloc[0];page=byqid.get(t.qid,{});text=page.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('*',''); fields={k.strip():v.strip() for k,v in re.findall(r'\|\s*([^=|\n]+)=([^|\n]*)',text)};kind=normalize(fields.get('статус',''));type_=normalize(t.type);articlephysical=kind in ('поселок','деревня','село','хутор','станица','поселок городского типа','рабочий поселок','пгт','железнодорожная станция','поселок при станции')
 name_ok=normalize(r.settlement_name) in normalize(raw['settlement']);code_ok=str(raw['oktmo']).zfill(11)==rr['?oktmo'] or (pd.notna(raw['okato_dadata']) and str(int(float(raw['okato_dadata']))).zfill(11)==rr['?okato']);raw_np=raw['object_level']=='Населенный пункт';pop_ok=raw['population']==r.population
 article_kind_ok=type_==kind or type_ in ('поселок','пгт') and kind in ('поселок городского типа','рабочий поселок','поселок','пгт') or type_=='железнодорожный объект' and kind in ('поселок при станции','железнодорожная станция')
 # Own name+exact current classifier code+own article type establish object binding. No county centre borrowed.
 soft_variant=t.qid in ('Q50799','Q27173749','Q4446898') and articlephysical
 positional_station=t.qid=='Q97821506' and '{{НП+Россия|Чернец|станция' in text
 qualified=raw_np and name_ok and code_ok and pop_ok and (articlephysical and article_kind_ok or soft_variant or positional_station)
 record={'sid':t.sid,'qid':t.qid,'name':t.name,'type':t.type,'raw_native_object_level':raw['object_level'],'raw_native_population':raw['population'],'raw_native_oktmo':raw['oktmo'],'raw_native_okato_dadata':raw['okato_dadata'],'wiki_oktmo':rr['?oktmo'],'wiki_okato':rr['?okato'],'native_code_comparison':'native10digit_OKTMO leading0restore; raw double OKATO integral decode to11digits; no8vs11truncation','exact_own_code_bind':code_ok,'raw_name_matches':name_ok,'article_status':fields.get('статус',''),'article_type_matches':article_kind_ok,'type_variant_binding_status':'explicit_unique_native_own_code_name_geography_soft_type_variant' if soft_variant else ('positional_NP_template_station_type' if positional_station else 'printed_type_compatible'),'own_article_title':page.get('title'),'own_article_revision':page.get('revisions',[{}])[0].get('revid'),'own_article_county':fields.get('район',''),'own_article_region':fields.get('регион',''),'current_native_county':raw['mun_upper'],'native_source_sha256':ph,'native_source_locator':'parquet_row_1based='+str(offset+1),'article_source_sha256':sha(wp) if pages else '', 'qualified_current_point':qualified,'latitude':t.latitude,'longitude':t.longitude,'bounds':'UNKNOWN','error_rate':'uncalibrated'};checks.append(record)
 if qualified:safe.add(t.sid)
 else:hold.append(record)
pd.DataFrame(checks).to_csv(O/'all_current_own_binding_checks.csv',index=False)
# Fixed15 and largest5 sampled once, with source data checks already done for full cohort.
f=pd.DataFrame(checks);large=set(inv.nlargest(5,'population_2021').sid);fixed=set(inv.assign(samplekey=inv.qid.map(lambda q:hashlib.sha256(('fixed15-20261007'+q).encode()).hexdigest())).sort_values('samplekey').head(15).sid);sample=f[f.sid.isin(large|fixed)].copy();sample['sample']=sample.sid.map(lambda x:'largest5' if x in large else 'fixed15');sample.to_csv(O/'fixed15_and_largest5_source_checks.csv',index=False)
accepted=[]
for t in inv[inv.sid.isin(safe)].itertuples():
 base=pts[(pts.target_source_record_id==t.sid)&(pts.target_year==2021)].iloc[0].to_dict()
 # Source origin is own P625 rank/coherence from build; active accepted conflicting historical points block reuse.
 for rr in s.obs[s.obs.root==s.uf.find(t.sid)].itertuples():
  if rr.source_record_id in s.point_rows:continue
  pp=base.copy();pp.update(target_source_record_id=rr.source_record_id,target_year=int(rr.census_year),population=float(rr.population),coordinate_admission_status='reviewed_extension_rule_accepted',admission_allowed=True,source_file=rr.source_file,source_sha256=rr.source_sha256,source_locator=rr.source_locator,point_use_inference='modern_own_representative_point_reused_on_existing_accepted_sameplace_component' if rr.census_year!=2021 else 'modern_own_representative_point',population_boundary_comparability_asserted=False,modern_boundary_harmonized=False);accepted.append(pp)
pd.DataFrame(accepted).to_csv(A/'accepted_point_use_delta.csv',index=False)
# Secondary observations remain nonadditive, and native existing observations retain their protected counts.
credit=set(sid for sid in s.point_rows if s.years[s.uf.find(sid)]=={2002,2010,2021});creditinputs={}
for fn in ['working_full_chain_20261007/qualified_scope_source_id_credit_union.csv','complete_numbered_partition_batch_20261007/accepted_exclusive_member_projection.csv']+ [z+'/accepted_constituent_credit_union.csv' for z in ['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','further_urban_merger_application_20261007']]+['recreated_named_locality_event_application_20261007/accepted_qualified_physical_observations.csv']:
 pp=R/'research_rebuild/evidence'/fn
 if pp.exists():
  creditinputs[str(pp)]=sha(pp);dd=pd.read_csv(pp,dtype=str).fillna('')
  for col in dd:
   if 'source_record_id'in col:credit.update(dd[col])
qualified=[];net=[]
for t in inv[(inv.sid.isin(safe))&inv.actual_full3_available.astype(str).str.lower().eq('true')].itertuples():
 trip=ser[ser.sid==t.sid];assert set(trip.year)=={2002,2010,2021};base=pts[(pts.target_source_record_id==t.sid)&(pts.target_year==2021)].iloc[0].to_dict();base['coordinate_admission_status']='reviewed_extension_rule_accepted'
 for r in trip.to_dict('records'):
  nativeid=r['selected_source_record_id'];nativebool=bool(nativeid);q={'trajectory_id':'unpointed_ownyear:'+t.qid,'year':int(r['year']),'population_source_value':r['population'],'source_record_id':nativeid,'current2021_source_record_id':t.sid,'settlement_name':t.name,'region_norm':t.region,'county_context':r.get('native_county') or t.current_county,'latitude':t.latitude,'longitude':t.longitude,'population_quality':r['population_quality'],'grain':'existing selected settlement observation' if nativebool else 'own physical locality census-reference secondary observation','nonadditive_observation':not nativebool,'source_path':r['source_file'] if str(r['source_file']).startswith('/') else str(Path('/workspace/settlements-raw')/r['source_file']),'source_sha256':r['source_sha256'],'source_locator':r['source_locator'],'decision_status':'qualified_accepted_secondary_own_census_history','ordinary_NP3_asserted':False,'boundary_comparability_asserted':False,'point_origin_file':base['point_origin_file'],'point_origin_sha256':base['point_origin_sha256'],'point_origin_locator':base['point_origin_locator'],'point_binding_json':json.dumps(base,ensure_ascii=False),'retrospective_point_use_is_continuity_inference':int(r['year'])!=2021,'selected_credit_previously_present':nativeid in credit if nativebool else False,'scope':'qualified_same_named_own_physical_locality_actual_census_history','boundary_comparability':'UNKNOWN','census_reference_ids':r.get('references',''),'reference_labels_json':r.get('reference_labels_json',''),'bounds':'UNKNOWN','error_rate':'uncalibrated'};qualified.append(q)
pd.DataFrame(qualified).to_csv(A/'accepted_qualified_physical_observations.csv',index=False)
for y in (2002,2010,2021):
 ids={r['source_record_id'] for r in qualified if r['year']==y and r['source_record_id'] and r['source_record_id'] not in credit};net.append({'year':y,'net_unique_selected_ids':len(ids),'net_selected_population':float(s.by_id.loc[list(ids),'population'].sum()) if ids else 0,'secondary_own_population_nonadditive':sum(r['population_source_value'] for r in qualified if r['year']==y and r['nonadditive_observation']),'integration_pending':True})
pd.DataFrame(net).to_csv(A/'unique_source_id_net_delta.csv',index=False)
receipt={'status':'prepared_reviewed_application_root_integration_pending','application_stage':17,'current_own_points':len(safe),'accepted_point_uses':len(accepted),'current_own_point_population':float(inv[inv.sid.isin(safe)].population_2021.sum()),'qualified_actual_full3_series':len(qualified)//3,'qualified_actual_full3_current_population':sum(r['population_source_value'] for r in qualified if r['year']==2021),'net_vs_frozen_ordinary_and_scope_credits':net,'credit_input_hashes':creditinputs,'native_source_sha256':ph,'candidate_package_unchanged':True,'ordinary_graph_modified':False,'source_population_values_modified':False,'source_values_checks':'all33 current native row/code/name/object-level/pop; ownarticle type; fixed15+largest5 one sample','wall_seconds':time.monotonic()-T}
(A/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False));print('held checks',[(h['name'],h['article_status'],h['exact_own_code_bind']) for h in hold])

import sys,json,pathlib,pandas as pd,re,hashlib,math
R=pathlib.Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=E/'old_native_from_existing_secondary_binding_20261007';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(21);old=s.obs[s.obs.census_year.isin([2002,2010])].copy();cur=s.obs[s.obs.census_year.eq(2021)].copy()
def norm(x):return ' '.join(str(x).lower().replace('ё','е').replace('"','').split())
def county(x):
 x=norm(x);x=re.sub(r'муниципальное образование|муниципальный район|муниципального района|муниципальный округ|муниципального округа|городской округ|городского округа|район|района|город|города|мр|го',' ',x);return ' '.join(x.split())
for f in [old,cur]:f['county_key']=f.district_raw.map(county)
oldgroups={k:g for k,g in old.groupby(['census_year','name_norm','type_norm','region_norm'])};curgroups={k:g for k,g in cur.groupby(['name_norm','type_norm','region_norm'])}
trajectory=json.load(open('/workspace/settlements-work/continuation_20261004/root/accepted_combined_temporal892_scope/accepted_scoped_trajectories.json'));prior=pd.read_csv(E/'existing_event_scope_reserve_20261007/candidate_series.csv');own=set(prior.qid);cands=[];holds=[];refs=[];raws={}
covered=set(pd.read_csv(E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv').source_record_id)
for p in E.glob('*application*/*credit_union.csv'):
 try:d=pd.read_csv(p)
 except:continue
 if 'source_record_id' in d:covered.update(d.source_record_id.dropna())
for t in trajectory:
 if t['subject_qid'] not in own:continue
 sid=t['current_source_record_id'];c=s.by_id.loc[sid];root=s.uf.find(sid)
 for x in t['observations']:
  y=int(x['year'])
  if x.get('source_record_id') or not x.get('claim') or y in s.years[root]:continue
  cl=x['claim'];st=json.loads(cl['statement_json']);meth=cl['P459_json'];ref=json.loads(cl['references_json']);title=[z.get('datavalue',{}).get('value',{}).get('text','') for rr in ref for z in rr.get('snaks',{}).get('P1476',[])];p248=[z.get('datavalue',{}).get('value',{}).get('id') for rr in ref for z in rr.get('snaks',{}).get('P248',[])];urls=[z.get('datavalue',{}).get('value','') for rr in ref for z in rr.get('snaks',{}).get('P854',[])]
  if '29051383' in meth or not ref or not(p248 or any(re.search('ВПН.?'+str(y)+'|перепис.*'+str(y),z,re.I) for z in title) or any(re.search('vpn|perepis|rosstat|gks',z,re.I) for z in urls)):continue
  og=oldgroups.get((y,c.name_norm,c.type_norm,c.region_norm),old.iloc[:0]);exact=og[og.population.eq(int(x['population']))];match_method='exact_census_count'
  if len(exact)==0 and y==2010:
   context=og[og.county_key.eq(county(c.district_raw))]
   if len(context)==1 and abs(int(context.iloc[0].population)-int(x['population']))<=2:
    exact=context;match_method='unique_printed_county_name_type_region_with_protected_count_discrepancy'
  crow=curgroups.get((c.name_norm,c.type_norm,c.region_norm),cur.iloc[:0]);ck=county(c.district_raw)
  reason=[]
  if len(exact)!=1:reason.append('exact_census_count_candidates_'+str(len(exact)))
  if len(exact)==1:
   a=exact.iloc[0];oldcounty=a.county_key
   if not ck or oldcounty!=ck:reason.append('historical_county_context_not_exact')
   if len(crow[crow.county_key.eq(ck)])!=1:reason.append('current_physical_competitor_county_not_unique')
   if a.source_record_id in covered:reason.append('already_selected_credit')
   if s.uf.find(a.source_record_id)==root:reason.append('already_same_component')
   ar=s.uf.find(a.source_record_id)
   if s.years[ar]&s.years[root]:reason.append('component_year_collision')
   dist=None
   if a.source_record_id in s.point_rows:
    p=s.point_rows[a.source_record_id];q=s.point_rows[sid];la1,lo1,la2,lo2=map(math.radians,[p['latitude'],p['longitude'],q['latitude'],q['longitude']]);dist=6371.0088*2*math.asin(min(1,math.sqrt(math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2)))
    if dist>5:reason.append('existing_old_own_point_disagrees_over5km')
  base={'qid':t['subject_qid'],'current_source_record_id':sid,'name':c.settlement_name,'type':c.settlement_type,'region':c.region_norm,'current_county':c.district_raw,'year':y,'secondary_census_population':int(x['population']),'claim_GUID':cl['statement_GUID'],'claim_raw_file':cl['entity_file'],'claim_raw_sha256':cl['entity_file_sha256'],'claim_date':cl['historical_P585_raw'],'claim_date_precision':cl['historical_P585_precision'],'reference_ids_json':json.dumps(p248),'reference_urls_json':json.dumps(urls),'reference_titles_json':json.dumps(title,ensure_ascii=False),'old_exactname_type_region_competitors':len(og),'old_exactname_type_region_count_competitors':len(exact),'current_exactname_type_region_competitors':len(crow),'current_same_county_competitors':len(crow[crow.county_key.eq(ck)])}
  if reason:
   base['hold_reason']=';'.join(reason)
   if len(exact)==1:base.update(old_source_record_id=a.source_record_id,old_native_population=int(a.population),old_county=a.district_raw,old_source_file=a.source_file,old_source_path=a.source_path,old_source_locator=a.source_locator)
   holds.append(base);continue
  p=s.point_rows[sid];base.update(old_source_record_id=a.source_record_id,old_native_population=int(a.population),old_county=a.district_raw,old_okato=a.okato,old_oktmo=a.oktmo,old_source_file=a.source_file,old_source_path=a.source_path,old_source_sha256=a.source_sha256,old_source_locator=a.source_locator,old_existing_point_distance_km=dist,current_own_latitude=p['latitude'],current_own_longitude=p['longitude'],current_own_point_origin_file=p.get('point_origin_file'),current_own_point_origin_sha256=p.get('point_origin_sha256'),current_own_point_origin_locator=p.get('point_origin_locator'),binding_proof='exact own censusvalue/name/type/region + printed same county + unique current samecounty physicalNP + prioraccepted ownnativecode/QID/currentpoint',status='candidate_native_old_binding_not_admitted',match_method=match_method);cands.append(base)
pd.DataFrame(cands).to_csv(O/'candidate_native_old_bindings.csv',index=False);pd.DataFrame(holds).to_csv(O/'scope_holds.csv',index=False);r={'status':'candidate_only','stage':21,'scanned_own_secondary_series':len(own),'all_old_selected_competitor_rows':len(old),'all_current_selected_competitor_rows':len(cur),'candidate_rows':len(cands),'candidate_native_population_by_year':{int(y):int(g.old_native_population.sum()) for y,g in pd.DataFrame(cands).groupby('year')} if cands else {},'held_rows':len(holds),'source_values_modified':False,'ordinary_edges_added':False,'point_uses_added':False};(O/'scan_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r));print(pd.DataFrame(cands)[['qid','name','year','old_native_population','old_county','current_county']].head(30).to_string(index=False) if cands else '')

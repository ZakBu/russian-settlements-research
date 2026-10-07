"""Source-backed external ownpoint repair and actual selected-year candidates only."""
import sys,json,csv,re
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
sys.path.insert(0,str(ROOT))
from research_rebuild.mass_linkage.wide_wikidata_bindings import qid,rdf_text
OUT=Path(__file__).parent;WORK=Path('/workspace/settlements-work/corrected_own_wiki_point_batch_20261007')
SPATIAL=Path('/workspace/settlements-work/direct_old_geokladr_point_reserve_20261007_spatial_review/all_own_code_spatial_screen.csv')
BASE=Path('/workspace/settlements-work/direct_old_geokladr_point_reserve_20261007/candidate_point_uses.csv')
POP=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_population.tsv')
POINTTSV=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
ART=WORK/'bounded_cached_article_hits.json'
g=pd.read_csv(SPATIAL,dtype={'raw_own_code':str});g=g[g.spatial_review_status.ne('no_qualified_independent_own_object_point')]
base=pd.read_csv(BASE,dtype={'historical_okato_2011_raw':str}).set_index('source_record_id')
s=load(15);before=s.metrics();inputs=list(s.inputs)+[SPATIAL,BASE,POP,POINTTSV,ART]
pinned={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in inputs}
articles={}
for batch in json.loads(ART.read_text())['hits']:
 for req in batch['requested']:
  for page in batch['pages']:
   if page['title']==req['article_title']:
    text=page.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','')
    fields={k.strip():v.strip() for k,v in re.findall(r'\|\s*([^=|\n]+)=([^|\n]*)',text)}
    articles[req['wikidata_id_effective']]={'source_file':batch['path'],'source_sha256':sha(Path(batch['path'])),'title':page['title'],'pageid':page['pageid'],'revisionid':page.get('revisions',[{}])[0].get('revid'),'fields':fields,'explicit_population_lines':[line for line in text.splitlines() if re.search(r'2002|2010|2021',line) and re.search(r'насел|числен|перепис|\|',line,re.I)],'wikitext_excerpt':text[:1100]}
qids=set();own={};holds=[]
for r in g.to_dict('records'):
 witnesses=[w for w in json.loads(r['independent_spatial_witnesses_json']) if w.get('provider')=='Wikidata' and w.get('source_binding_qualified') and w.get('distinct_coordinates')==1]
 if len(witnesses)!=1:holds.append({'source_record_id':r['source_record_id'],'reason':'multiple_or_absent_qualified_own_external_points'});continue
 w=witnesses[0];own[r['source_record_id']]=(r,w);qids.add(w['qid'])
popclaims=defaultdict(list)
with POP.open() as stream:
 for line,row in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  q=qid(row.get('?item'))
  if q not in qids:continue
  date=row.get('?date','');year=int(date[:4]) if re.match(r'^\d{4}',date) else None
  try:pop=float(row['?population'])
  except (ValueError,KeyError):continue
  popclaims[(q,year)].append({'wikidata_qid':q,'year':year,'population':pop,'date_raw':date,'rank_raw':row.get('?rank'),'statement':row.get('?statement'),'source_file':str(POP),'source_sha256':pinned[str(POP)]['sha256'],'source_locator':'line_1based='+str(line),'raw_oktmo':rdf_text(row.get('?oktmo')),'population_source_quality':'dated_secondary_P1082_not_independently_primary_verified','census_assignment_asserted':False})
obs=s.obs[s.obs.is_additive_settlement_record.fillna(False)].copy();obs['n']=obs.name_norm.map(normalize);obs['t']=obs.type_norm.map(normalize);obs['r']=obs.region_norm.map(normalize);obs['d']=obs.district_raw.map(county_key)
idx=defaultdict(list)
for a in obs.to_dict('records'):idx[(a['n'],a['t'],a['r'],a['d'],int(a['census_year']))].append(a)
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
points=[];edges=[];matches=[];actualclaims=[];outcomes=Counter();candidatepointids=set();seenedges=set()
for sid,(r,w) in own.items():
 a=base.loc[sid].to_dict();q=w['qid'];lat,lon=w['coordinates'][0];root=s.uf.find(sid)
 # Own Wikipedia fields expose exact type and location independently where cached.
 article=articles.get(q,{})
 af=article.get('fields',{});article_status=normalize(af.get('статус',''))
 for yr in [2002,2010,2021]:
  claims=popclaims.get((q,yr),[]);unique={v['statement']:v for v in claims};actualclaims.extend(unique.values())
  if yr in s.years[s.uf.find(sid)]:continue
  key=(normalize(a['settlement_name']),normalize(a['settlement_type']),normalize(a['region_norm']),a['county_key'],yr)
  rows=idx.get(key,[])
  if len(rows)!=1:
   matches.append({'origin_source_record_id':sid,'wikidata_qid':q,'missing_year':yr,'actual_dated_secondary_claims':len(unique),'selected_exact_name_type_region_county_matches':len(rows),'status':'missing_actual_selected_census_row' if not rows else 'multiple_actual_selected_census_rows'});continue
  b=rows[0];bid=b['source_record_id'];variants={v['population'] for v in claims};popok=float(b['population']) in variants if pd.notna(b['population']) else False
  distance=None;reason=''
  if bid in s.point_rows:
   p=s.point_rows[bid];distance=distance_km((lat,lon),(p['latitude'],p['longitude']))
   if distance>5:reason='existing_accepted_missing_year_point_conflict'
  if s.uf.find(sid)!=s.uf.find(bid) and s.years[s.uf.find(sid)]&s.years[s.uf.find(bid)]:reason='repeated_year_component_conflict'
  if not claims or not popok:reason=reason or 'no_exact_dated_secondary_population_corroboration'
  matches.append({'origin_source_record_id':sid,'wikidata_qid':q,'missing_year':yr,'actual_dated_secondary_claims':len(unique),'selected_exact_name_type_region_county_matches':1,'matched_source_record_id':bid,'matched_source_population':b['population'],'dated_secondary_population_variants':'|'.join(map(str,sorted(variants))),'actual_population_match':popok,'source_file':b['source_file'],'source_sha256':b['source_sha256'],'source_locator':b['source_locator'] or bid,'existing_point_distance_km':distance,'status':reason or 'candidate_actual_missing_year_selected_row'} )
  if reason:continue
  edgekey=tuple(sorted([sid,bid]))
  if edgekey not in seenedges:
   seenedges.add(edgekey);edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'from_year':int(a['census_year']),'to_year':yr,'relation':'same_place','decision_status':'candidate_only_requires_independent_review','wikidata_qid':q,'evidence_rule':'own_exact_code_label_county_unique_real_selected_row_plus_dated_secondary_population_match','population_or_boundary_comparability_asserted':False})
  if s.uf.find(sid)!=s.uf.find(bid):s.union(sid,bid)
  if bid not in s.point_rows and not occupied.get((yr,lat,lon),set())-{bid}:candidatepointids.add(bid)
 # An external ownpoint replaces the disproven candidate point; accepted baseline is not superseded.
 year=int(a['census_year']);pointreason=''
 if sid in s.point_rows:pointreason='already_accepted_target_no_candidate_supersession'
 if occupied.get((year,lat,lon),set())-{sid}:pointreason='same_year_accepted_coordinate_occupied'
 if pointreason:holds.append({'source_record_id':sid,'reason':pointreason});continue
 points.append({'target_source_record_id':sid,'target_year':year,'latitude':lat,'longitude':lon,'source_name':a['settlement_name'],'source_type':a['settlement_type'],'source_region':a['region_norm'],'source_county':a['county_key'],'population':a['population'],'coordinate_provider':'Wikimedia cached own-object point','coordinate_provider_id':q,'coordinate_source':'raw Wikidata TSV own P721/name and unique coordinate corroborated by own article county','point_origin_file':'/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv','point_origin_locator':'TSV_lines_1based='+','.join(map(str,w['tsv_lines']))+';QID='+q+';own_OKATO='+a['historical_okato_2011_raw'],'point_origin_kind':'direct_external_named_object_coordinate','coordinate_admission_status':'candidate_only_requires_independent_review','admission_allowed':False,'native_census_code_binding_asserted':False,'historical_classifier_own_code':a['historical_okato_2011_raw'],'source_file':a['census_source_file'],'source_sha256':a['census_source_sha256_actual'],'source_locator':a['census_source_locator'],'old_unaccepted_geokladr_latitude':a['latitude'],'old_unaccepted_geokladr_longitude':a['longitude'],'old_geokladr_to_own_point_km':distance_km((lat,lon),(a['latitude'],a['longitude'])),'corrects_geokladr_candidate_spatial_conflict':r['spatial_review_status']=='qualified_spatial_conflict_hold','own_code_label_county_binding':json.dumps(w,ensure_ascii=False),'cached_own_article':json.dumps(article,ensure_ascii=False),'cached_own_article_type_matches':article_status==normalize(a['settlement_type']) if article else None,'direct_census_date_coordinate':False,'population_or_boundary_comparability_asserted':False,'point_use_inference':'retrospective_own_object_representative_external_point'})
 candidatepointids.add(sid)
# A bounded source-order case supplies actual blank-county 2010 and changed-county 2021 rows.
caseids=['2002:007_acff9aa32d_02c_Kostromskaja.xls:Sheet1:1998','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:1746','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:44740']
left=['2002:007_acff9aa32d_02c_Kostromskaja.xls:Sheet1:1996','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:1745','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:44773']
right=['2002:007_acff9aa32d_02c_Kostromskaja.xls:Sheet1:2002','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:1749','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:44747']
assert len({s.uf.find(x) for x in left})==1 and len({s.uf.find(x) for x in right})==1
assert all(s.years[s.uf.find(x)]=={2002,2010,2021} for x in [*left,*right])
assert all(s.by_id.loc[x,'district_raw']=='Мантуровский район' for x in [left[0],right[0],caseids[0]])
assert all(s.by_id.loc[x,'district_raw']=='Городской округ город Мантурово' for x in [left[2],right[2],caseids[2]])
assert [float(s.by_id.loc[x,'population']) for x in caseids]==[1570,1099,672]
assert all(normalize(s.by_id.loc[x,'settlement_name'])=='октябрьский' and normalize(s.by_id.loc[x,'settlement_type'])=='поселок' for x in caseids)
assert any(c['population']==1099 for c in popclaims[('Q4333069',2010)]) and any(c['population']==672 for c in popclaims[('Q4333069',2021)])
case={'source_record_ids':caseids,'population_values':[1570,1099,672],'left_accepted_three_year_anchor_source_ids':left,'right_accepted_three_year_anchor_source_ids':right,'2010_source_order_bracket_rows':[1745,1746,1749],'2002_source_order_bracket_rows':[1996,1998,2002],'explicit_old_county':'Мантуровский район','explicit_current_county':'Городской округ город Мантурово','boundary_comparability_asserted':False,'2010_population_quality_preserved':s.by_id.loc[caseids[1],'population_value_quality'],'external_qid':'Q4333069','external_point':[58.315,44.32],'current_raw_provider_point_distance_km':distance_km((58.315,44.32),(float(s.by_id.loc[caseids[2],'latitude']),float(s.by_id.loc[caseids[2],'longitude'])))}
caseassets={}
for y,sid in zip([2002,2010,2021],caseids):
 b=s.by_id.loc[sid].to_dict();asset=Path('/workspace/settlements-raw')/b['source_file'];caseassets[str(asset)]={'sha256':sha(asset),'bytes':asset.stat().st_size}
 if y<2021:
  sheet,row=sid.rsplit(':',2)[-2:];row=int(row);raw=pd.read_excel(asset,sheet_name=sheet,header=None)
  values=raw.iloc[row-1];numeric=pd.to_numeric(values.astype(str).str.replace(' ','',regex=False),errors='coerce')
  assert numeric.eq(b['population']).any() and 'октябрьский' in normalize(' '.join(map(str,values)))
  case[str(y)+'_raw_row_excerpt']=' | '.join(str(v) for v in values if pd.notna(v))[:600]
  raw.iloc[[int(left[0 if y==2002 else 1].rsplit(':',1)[-1])-1,row-1,int(right[0 if y==2002 else 1].rsplit(':',1)[-1])-1],:5].to_csv(OUT/f'oktyabrsky_{y}_raw_bracket_rows.csv',index=False)
 else:
  # Source ID parquet row is 1-based, independently read the source row itself.
  import duckdb
  raw=duckdb.connect().execute('SELECT object_level,settlement,mun_upper,population,oktmo FROM read_parquet(?) LIMIT 1 OFFSET 44739',[str(asset)]).fetchdf().iloc[0]
  assert raw.object_level=='Населенный пункт' and raw.population==672 and normalize(raw.settlement)=='поселок октябрьский'
  case['2021_raw_row']=raw.to_dict()
 if y in [2010,2021]:
  if sid in s.point_rows:holds.append({'source_record_id':sid,'reason':'case_current_target_already_accepted_hold'});continue
  template=next(p for p in points if p['target_source_record_id']==caseids[0]).copy()
  template.update({'target_source_record_id':sid,'target_year':y,'population':b['population'],'source_file':b['source_file'],'source_sha256':caseassets[str(asset)]['sha256'],'source_locator':sid,'source_county':b['district_raw'],'own_county_binding_source_context':json.dumps(case,ensure_ascii=False),'old_unaccepted_geokladr_latitude':None,'old_unaccepted_geokladr_longitude':None,'old_geokladr_to_own_point_km':None,'corrects_geokladr_candidate_spatial_conflict':False,'corrects_unaccepted_current_provider_point_conflict':y==2021,'raw_current_provider_code_binding_asserted':False})
  assert not occupied.get((y,58.315,44.32),set())-{sid}
  points.append(template);candidatepointids.add(sid)
for bid in caseids[1:]:
 assert not (s.years[s.uf.find(caseids[0])]&s.years[s.uf.find(bid)])
 edges.append({'from_source_record_id':caseids[0],'to_source_record_id':bid,'from_year':2002,'to_year':int(s.by_id.loc[bid,'census_year']),'relation':'same_place','decision_status':'candidate_only_requires_independent_review','wikidata_qid':'Q4333069','evidence_rule':'actual_source_row_two_sided_accepted_three_year_order_context_plus_own_external_code_label_county_dated_population','population_or_boundary_comparability_asserted':False,'source_context_witness':json.dumps(case,ensure_ascii=False)})
 b=s.by_id.loc[bid];matches.append({'origin_source_record_id':caseids[0],'wikidata_qid':'Q4333069','missing_year':int(b.census_year),'actual_dated_secondary_claims':len(popclaims[('Q4333069',int(b.census_year))]),'selected_exact_name_type_region_county_matches':0,'matched_source_record_id':bid,'matched_source_population':b.population,'actual_population_match':True,'source_file':b.source_file,'source_sha256':caseassets[str(Path('/workspace/settlements-raw')/b.source_file)]['sha256'],'source_locator':bid,'status':'candidate_actual_missing_year_source_context_case','source_context_witness':json.dumps(case,ensure_ascii=False)})
 s.union(caseids[0],bid)
pinned.update(caseassets);(OUT/'oktyabrsky_source_context_case.json').write_text(json.dumps(case,ensure_ascii=False,default=str,indent=2)+'\n')
pf=pd.DataFrame(points);pf['point_origin_sha256']=pinned[str(POINTTSV)]['sha256'];ef=pd.DataFrame(edges);mf=pd.DataFrame(matches);cf=pd.DataFrame(actualclaims).drop_duplicates(['wikidata_qid','statement']) if actualclaims else pd.DataFrame()
pf.to_csv(WORK/'candidate_corrected_external_own_point_delta.csv',index=False);ef.to_csv(WORK/'candidate_actual_missing_year_identity_edges.csv',index=False);mf.to_csv(OUT/'actual_missing_year_selected_row_checks.csv',index=False);cf.to_csv(OUT/'raw_dated_secondary_population_observations.csv',index=False);pd.DataFrame(holds).to_csv(OUT/'point_holds.csv',index=False)
pf[['target_source_record_id','target_year','source_name','population','coordinate_provider_id','latitude','longitude','old_geokladr_to_own_point_km','corrects_geokladr_candidate_spatial_conflict','cached_own_article_type_matches']].to_csv(OUT/'corrected_point_inventory.csv',index=False)
after=s.metrics(extra_point_ids=list(candidatepointids));r={'status':'candidate_only_no_admission','working_stage':15,'baseline':before,'candidate_simulation':after,'net_full_three_gain_population_by_year':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'candidate_external_point_rows':len(pf),'candidate_geokladr_conflict_repairs':int(pf.corrects_geokladr_candidate_spatial_conflict.sum()),'candidate_point_population_by_year':{str(y):int(d.population.sum()) for y,d in pf.groupby('target_year')},'candidate_missing_year_identity_edges':len(ef),'missing_year_selected_match_status_counts':mf.status.value_counts().to_dict() if len(mf) else {},'raw_dated_secondary_population_rows':len(cf),'raw_dated_secondary_2021_rows':int(cf.year.eq(2021).sum()) if len(cf) else 0,'cached_own_articles':len(articles),'cached_article_read_failures':len(json.loads(ART.read_text())['read_failures']),'inputs':pinned,'generator_sha256':sha(Path(__file__)),'limitations':['No accepted input changed; candidate statuses never imply admission.','Dated P1082 Jan1 is year context and does not alone prove Russian census-date scope. Only actual selected additive census rows with matching printed own name/type/region/county and population receive cross-year candidates.','No invented children, interpolation, residual allocation or inferred2021 population.','Unique direct external own-object coordinates replace unaccepted incorrect GeoKLADR candidates; baseline point supersession is not performed.','Explicit county and label exclude municipality QID competitors; provider binding and point correctness remain separate claims.','Wikipedia revision type checks exist for16 own articles; no readable cached conflict-object articles were found.']}
r['outputs']={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [*WORK.glob('*.csv'),*OUT.glob('*.csv')]};(OUT/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:r[k] for k in ['baseline','net_full_three_gain_population_by_year','candidate_external_point_rows','candidate_geokladr_conflict_repairs','candidate_missing_year_identity_edges','missing_year_selected_match_status_counts','raw_dated_secondary_population_rows','raw_dated_secondary_2021_rows']},ensure_ascii=False))

"""Bounded primary native-row triplets on explicit stage18; no admission."""
import sys,json,re,gzip
from pathlib import Path
from collections import defaultdict
import pandas as pd,duckdb,xlrd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');CURRENT=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');FORMER=ROOT/'research_rebuild/evidence/wikidata_former_name_bridge_20261007/former_name_witness_inventory.csv'
# Each entry retains the actual old NP row. No part suffix is dropped or summed.
review=pd.read_csv(O/'bounded_native_source_binding_review.csv',dtype=str,keep_default_na=False)
choices={'Зубутли-Миатли (ЦIобокь-Миякьо)':'native_printed_alternate_name_in_parentheses','Халимбек-Аул':'native_hyphenated_same_name','Ленина':'exact_name_own_city_subordination','Сторожовка':'narrow_native_vowel_spelling_same_county','Жаворонки':'exact_name_urban_to_rural_same_county','Дмитровск-Орловский':'own_verified_Q135358_former_name','Дорохово':'exact_name_urban_to_rural_same_county','Октябрьский':'exact_name_urban_to_rural_same_county','Таежный':'exact_name_urban_to_rural_same_county','Беднодемьяновск':'own_verified_Q196443_former_name','Красногвардейское':'own_verified_Q105150_former_name','Южный':'exact_name_own_city_subordination'}
manual_context={'Ленина':(33,'Краснодар'),'Южный':(61,'Белореченск'),'Сторожовка':(2420,'Татищевск')}
renames={'Дмитровск-Орловский':('Q135358','batch_00638.json.gz',14001),'Беднодемьяновск':('Q196443','batch_02263.json.gz',84267),'Красногвардейское':('Q105150','batch_00208.json.gz',508772)}
s=load(18);before=s.metrics();members=defaultdict(list)
for a in s.obs.to_dict('records'):members[s.uf.find(a['source_record_id'])].append(a)
meta=duckdb.connect(config={'threads':1,'memory_limit':'500MB'});books={};inputhash={};witnesses=[];holds=[];edges=[];pointuses=[];extra=set();occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
for a in review[review.old_name.isin(choices)].to_dict('records'):
 sid,tid=a['old_source_record_id'],a['target_source_record_id'];old=s.by_id.loc[sid];ra,rb=s.uf.find(sid),s.uf.find(tid)
 if s.years[ra]!={2002} or s.years[rb]!={2010,2021}:holds.append({'source_record_id':sid,'reason':'actual_component_years_differ'});continue
 peers=members[rb];cur=[r for r in peers if int(r['census_year'])==2021][0];bid=cur['source_record_id'];cp=s.point_rows.get(bid)
 if cp is None:holds.append({'source_record_id':sid,'reason':'no_admitted_current_ownpoint'});continue
 asset=Path(a['source_file']);inputhash[str(asset)]=sha(asset)
 if asset not in books:books[asset]=xlrd.open_workbook(str(asset),on_demand=True)
 book=books[asset]
 try:sh=book.sheet_by_name(a['source_sheet'])
 except:sh=book.sheet_by_index(int(a['source_sheet']))
 rownum=int(a['source_row_1based']);vals=sh.row_values(rownum-1);labelcols=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(str(old.settlement_name)) in normalize(v)]
 if len(labelcols)!=1:raise ValueError('Literal primary NP label is not unique')
 def num(v):
  try:return float(v) if str(v).strip() else None
  except:return None
 counts=[num(v) for v in vals[labelcols[0]+1:] if num(v) is not None]
 if not counts or counts[0]!=float(old.population):raise ValueError('First actual census count differs')
 contextrow=int(float(a['source_county_header_row'])) if a['source_county_header_row'] else None;context=a['source_county_header']
 if a['old_name'] in manual_context:
  contextrow,token=manual_context[a['old_name']];context=' | '.join(str(v) for v in sh.row_values(contextrow-1) if v!='')
  if token not in context:raise ValueError('Primary context header token absent')
 # No new sameyear name competitor in the printed county. Explicit selected county and physical header retained separately.
 official_context=normalize(context)
 if not context:raise ValueError('Historical physical county or city subordination unresolved')
 primaryrename={}
 if a['old_name'] in renames:
  qid,filename,page=renames[a['old_name']];article=Path('/workspace/settlements-raw/data/raw/wikipedia_articles')/filename;inputhash[str(article)]=sha(article);data=json.load(gzip.open(article,'rt'));payload=data['payload'];pages=payload.get('query',{}).get('pages',[])
  if isinstance(pages,dict):pages=list(pages.values())
  chosen=[p for p in pages if int(p.get('pageid',0))==page]
  if len(chosen)!=1:raise ValueError('Own article binding page absent')
  p=chosen[0];revision=p['revisions'][0];text=revision.get('*',revision.get('slots',{}).get('main',{}).get('content',revision.get('slots',{}).get('main',{}).get('*','')));former=[v for v in text.splitlines() if 'прежние имена' in v]
  if not any(normalize(a['old_name']) in normalize(v) for v in former):raise ValueError('Old name absent from own former-name primary infobox')
  if qid not in str(cp.get('point_origin_locator','')):raise ValueError('Current admitted ownpoint does not bind same verified entity')
  primaryrename={'wikidata_id':qid,'article_file':str(article),'article_sha256':inputhash[str(article)],'pageid':page,'revision_id':revision.get('revid'),'former_name_literal_line':' | '.join(former)}
 currentrow=int(bid.rsplit(':',1)[-1]);publisher=meta.execute('WITH q AS (SELECT row_number() OVER () rn,* FROM read_parquet(?)) SELECT object_name,settlement,mun_upper,population FROM q WHERE rn=?',[str(CURRENT),currentrow]).fetchdf().iloc[0]
 if float(publisher.population)!=float(cur['population']):raise ValueError('Current actual published count differs')
 if normalize(str(cur['settlement_name'])) not in normalize(str(publisher.object_name)+' '+str(publisher.settlement)):raise ValueError('Current publisher own label differs')
 relevant=members[ra]+members[rb]
 reasons=[]
 if any(r['source_record_id'] in s.point_rows and distance_km((s.point_rows[r['source_record_id']]['latitude'],s.point_rows[r['source_record_id']]['longitude']),(cp['latitude'],cp['longitude']))>5 for r in relevant):reasons.append('existing_component_point_contradiction')
 if any(r['source_record_id'] not in s.point_rows and occupied.get((int(r['census_year']),cp['latitude'],cp['longitude']),set())-{r['source_record_id']} for r in relevant):reasons.append('sameyear_newpoint_collision')
 if reasons:holds.append({'source_record_id':sid,'reason':';'.join(reasons)});continue
 s.union(sid,tid);members[s.uf.find(sid)]=relevant
 edges.append({'from_source_record_id':sid,'to_source_record_id':tid,'relation':'same_place','decision_status':'candidate_only_requires_review','rule':choices[a['old_name']],'direct_primary_native_source_row':True,'population_boundary_comparability_asserted':False})
 for r in relevant:
  rid=r['source_record_id'];yr=int(r['census_year'])
  if rid in s.point_rows or rid in extra:continue
  p={k:v for k,v in cp.items() if k!='point_ledger_path'};p.update(target_source_record_id=rid,target_year=yr,coordinate_source_record_id=bid,coordinate_admission_status='candidate_only_requires_review',coordinate_origin_ledger=cp['point_ledger_path'],coordinate_origin_ledger_sha256=sha(Path(cp['point_ledger_path'])),direct_historical_measurement=False,population_boundary_comparability_asserted=False);pointuses.append(p);extra.add(rid);occupied[(yr,cp['latitude'],cp['longitude'])].add(rid)
 triplet=sorted(relevant,key=lambda r:int(r['census_year']))
 witnesses.append({'old_name':a['old_name'],'current_name':a['current_name'],'region':a['region'],'identity_rule':choices[a['old_name']],'years':'2002|2010|2021','source_ids_json':json.dumps({int(r['census_year']):r['source_record_id'] for r in triplet},ensure_ascii=False),'actual_population_json':json.dumps({int(r['census_year']):float(r['population']) for r in triplet},ensure_ascii=False),'source_population_quality_json':json.dumps({int(r['census_year']):r['population_value_quality'] for r in triplet},ensure_ascii=False),'primary2002_file':str(asset),'primary2002_sha256':inputhash[str(asset)],'primary2002_sheet':a['source_sheet'],'primary2002_row':rownum,'primary2002_raw_row':' | '.join(str(v) for v in vals if v!=''),'primary2002_context_row':contextrow,'primary2002_context_literal':context,'historical_printed_county_as_selected':str(old.district_raw),'current_printed_county':cur['district_raw'],'primary2021_row':currentrow,'primary2021_object_name':publisher.object_name,'primary2021_settlement':publisher.settlement,'primary2021_county':publisher.mun_upper,'current_admitted_point_ledger':cp['point_ledger_path'],'current_admitted_point_json':json.dumps(cp,ensure_ascii=False,default=str),'rename_own_article_witness_json':json.dumps(primaryrename,ensure_ascii=False),'administrative_eventdate':'UNKNOWN','scope':'ordinary native NP identity candidate; no split-part/group/event aggregate substituted','population_boundary_comparability_asserted':False})
meta.close();after=s.metrics(extra_point_ids=extra)
pd.DataFrame(witnesses).to_csv(O/'candidate_full_triplets.csv',index=False);pd.DataFrame(edges).to_csv(O/'candidate_identity_edges.csv',index=False);pd.DataFrame(pointuses).to_csv(O/'candidate_point_uses.csv',index=False);pd.DataFrame(holds,columns=['source_record_id','reason']).to_csv(O/'hard_holds.csv',index=False)
receipt={'status':'candidate_only_no_admission','stage':18,'actual_bound_triplets':len(witnesses),'candidate_edges':len(edges),'candidate_pointuses':len(pointuses),'baseline':before,'simulation':after,'marginal_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'marginal_full_three_rows':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'inputs':{str(p):sha(p) for p in [*s.inputs,SEL,CURRENT,FORMER,O/'bounded_native_source_binding_review.csv',Path(__file__)]},'raw_primary_source_hashes':inputhash,'outputs':{p.name:sha(p) for p in [O/'candidate_full_triplets.csv',O/'candidate_identity_edges.csv',O/'candidate_point_uses.csv',O/'hard_holds.csv']},'limitations':['Every candidate uses an actual selected2002 NP row and already accepted2010/2021 component; no census population or protected status changed.','Raw original observations were also searched; large missing whole-place2002 rows are split parts, not ordinary whole NP observations.','Historical header binding and narrow primary names/own former-name article witnesses infer stable identity; native legal boundary and event dates UNKNOWN.','Missing point uses are retrospective representative uses of admitted current ownpoints; historical independent points are not claimed.','Candidate-only physical-name/type/county continuity requires review; no acceptance status or loader mutation.']}
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['actual_bound_triplets','candidate_edges','candidate_pointuses','marginal_population_gain','marginal_full_three_rows']}))

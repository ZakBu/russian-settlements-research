from pathlib import Path
import json,gzip,re,sys,pandas as pd
O=Path(__file__).parent;ROOT=O.parents[2];sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'));from current_chain_state_20261007 import distance_km,sha
f=pd.read_csv(O.parent/'additional_uncached_census_histories_application_20261008/largest_hard_point_conflicts.csv').fillna('');d=json.loads(gzip.decompress((O/'own_article_API_response.json.gz').read_bytes()));byq={p.get('pageprops',{}).get('wikibase_item'):p for p in d['query']['pages']};rows=[]
for r in f.to_dict('records'):
 q=r['wikidata_id'];p=byq.get(q,{});rev=p.get('revisions',[{}])[0];text=rev.get('slots',{}).get('main',{}).get('content','');fields={};literal=[]
 for axis in ['lat','lon']:
  for part in ['deg','min','sec']:
   m=re.search(r'\|\s*'+axis+'_'+part+r'\s*=\s*([+-]?[\d.,]+)',text,re.I)
   if m:fields[axis+'_'+part]=float(m[1].replace(',','.'));literal.append(m[0])
 coord=tuple(fields[a+'_deg']+fields.get(a+'_min',0)/60+fields.get(a+'_sec',0)/3600 for a in ['lat','lon']) if 'lat_deg'in fields and 'lon_deg'in fields else None
 points=json.loads(r['active_points_and_origin_provenance_json']);pointchecks=[{**v,'article_distance_km':distance_km(coord,(v['latitude'],v['longitude'])) if coord else None}for v in points];p625=json.loads(r['own_P625_claims_json']);wiki=[]
 for st in p625:
  v=st.get('mainsnak',{}).get('datavalue',{}).get('value',{})
  if 'latitude'in v:wiki.append({'latitude':v['latitude'],'longitude':v['longitude'],'precision':v.get('precision'),'article_distance_km':distance_km(coord,(v['latitude'],v['longitude'])) if coord else None,'statement_id':st.get('id'),'qualifiers':st.get('qualifiers')})
 movements=[text[max(0,m.start()-140):m.end()+200]for m in re.finditer('перенес[её]н|пересел[её]н|затоплен|снесены|перемещ|разрушен',text,re.I)];infobox=text[:text.find('}}')+2];codes=re.findall(r'\|\s*(?:цифровой идентификатор|ОКАТО|ОКТМО|okato|oktmo)\s*=\s*(\d+)',text,re.I)
 rows.append({'wikidata_id':q,'current_source_record_id':r['current_source_record_id'],'name':r['current_name'],'current_population':r['current_population'],'article_title':p.get('title'),'article_page_id':p.get('pageid'),'article_revision_id':rev.get('revid'),'article_revision_timestamp':rev.get('timestamp'),'article_own_QID_pageprops_exact':bool(p),'article_latitude':coord[0]if coord else None,'article_longitude':coord[1]if coord else None,'literal_DMS_fields_json':json.dumps(literal),'article_printed_codes_json':json.dumps(codes),'article_history_movement_snippets_json':json.dumps(movements,ensure_ascii=False),'article_context_infobox_json':json.dumps(infobox,ensure_ascii=False),'active_points_article_distances_json':json.dumps(pointchecks,ensure_ascii=False),'own_P625_article_distances_json':json.dumps(wiki),'all_component_native_context_json':r['all_component_native_context_json'],'source_article_path':str(O/'own_article_API_response.json.gz'),'source_article_sha256':sha(O/'own_article_API_response.json.gz'),'source_article_locator':'query.pages[pageid='+str(p.get('pageid'))+'].revisions[0].slots.main.content','source_entity_path':r['entity_source_path'],'source_entity_sha256':r['entity_source_sha256']})
pd.DataFrame(rows).to_csv(O/'own_article_component_point_screen.csv',index=False)
for r in rows:print(r['name'],r['article_latitude'],r['article_longitude'],[(v['source_record_id'].split(':')[0],round(v['article_distance_km'],2)if v['article_distance_km']is not None else None,v.get('point_origin_kind'))for v in json.loads(r['active_points_article_distances_json'])],r['article_history_movement_snippets_json'])

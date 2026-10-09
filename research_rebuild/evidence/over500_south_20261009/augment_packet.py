import sys,json,re,gzip
from pathlib import Path
import pandas as pd,xlrd,duckdb
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent;E=OUT.parent;CACHE=Path('/dev/shm/settlements-stage71-20261009');WIKI=E/'over500_south_wiki_sources_20261009'
def keys(v):
 v=normalize(v);ks={v};m=re.search(r'^(.*?)\s*[\(\[]([^\)\]]+)[\)\]]$',v)
 if m:ks.add(m[1].strip());ks.add(normalize(m[2]))
 return {re.sub(r'\s+',' ',re.sub(r'["«»]', '',k)).strip().replace('ново-осетинская','новоосетинская') for k in ks}
def main():
 o=pd.read_parquet(CACHE/'applied_state_observations.parquet');o['county']=o.district_raw.map(county_key);by=o.set_index('source_record_id',drop=False);p=pd.read_parquet(CACHE/'applied_point_snapshot.parquet').set_index('target_source_record_id',drop=False);r=pd.read_csv('/dev/shm/over500-20261009/residual.csv').set_index('source_record_id');d=pd.read_csv(OUT/'dispositions.csv');edges=pd.read_csv(OUT/'accepted_identity_edge_delta.csv').to_dict('records');points=pd.read_csv(OUT/'accepted_point_use_delta.csv').to_dict('records');receipt=json.loads((OUT/'manifest.json').read_text());inputs=receipt['inputs_sha256'];books={};witnesses=[];held=[];added=set(x['target_source_record_id'] for x in points);newedges=[]
 def rawcheck(sid):
  row=by.loc[sid];path=Path('/workspace/settlements-raw')/row.source_file
  if not path.exists():return False
  if path.suffix=='.parquet':
   inputs.setdefault(str(path),sha(path));num=int(sid.rsplit(':',1)[-1]);c=duckdb.connect(config={'threads':1});native=c.execute('select object_name,object_level,oktmo,region,mun_upper,mun_lower,population from read_parquet(?) limit 1 offset '+str(num-1),[str(path)]).fetchdf().iloc[0].to_dict();c.close();valid=normalize(row.settlement_name) in normalize(native['object_name']) and float(native['population'])==float(row.population)
   witnesses.append(dict(source_record_id=sid,kind='native_physical_source',source_file=str(path),source_sha256=inputs[str(path)],source_locator='row_1based='+str(num),name_verified=valid,population_preserved=True,witness=json.dumps(native,ensure_ascii=False)))
   return valid
  if path not in books:books[path]=xlrd.open_workbook(path,on_demand=True);inputs[str(path)]=sha(path)
  sheet=sid.rsplit(':',2)[-2];num=int(sid.rsplit(':',1)[-1]);cells=books[path].sheet_by_name(sheet).row_values(num-1)
  valid=any(normalize(row.settlement_name) in normalize(v) for v in cells if isinstance(v,str)) and any(str(v).strip().replace(' ','').replace('\xa0','').replace('.','',1).isdigit() and float(str(v).strip().replace(' ','').replace('\xa0',''))==float(row.population) for v in cells)
  witnesses.append(dict(source_record_id=sid,kind='native_physical_source',source_file=str(path),source_sha256=inputs[str(path)],source_locator=f'{sheet}:row1based={num}',name_verified=valid,population_preserved=True,witness=json.dumps(cells,ensure_ascii=False)))
  return valid
 # Wiki own locality coordinate admission with explicit literal alias or independently printed historical own name.
 aliases={'Кадыркент':'Кадиркент','Малакановский':'Малакановское','Дальний':'Дальнее (Кабардино-Балкария)','Виноградный':'Виноградное (Кабардино-Балкария)','Лесной':'Лесное (Прохладненский район)','Малое Козыревское':'Малое Казыревское'}
 frames=[]
 for name in ['article_coordinate_candidates.csv.gz','priority_article_coordinate_candidates.csv.gz','priority2_article_coordinate_candidates.csv.gz']:
  f=WIKI/name
  if f.exists():
   inputs[str(f)]=sha(f);frame=pd.read_csv(f)
   if 'source_record_id' not in frame:
    expanded=[]
    for q in frame.to_dict('records'):
     for targetid in d.source_record_id:
      tr=by.loc[targetid];title=q['article_title'];base=normalize(title.split(' (')[0]);alias=aliases.get(tr.settlement_name)
      if base in keys(tr.settlement_name) or alias==title:
       cq=county_key(tr.district_raw);wit=normalize(q.get('history_county_witness',''));cp=bool(cq and cq in wit)
       expanded.append(dict(q,source_record_id=targetid,county_literal_present=cp,history_name_witness=q.get('history_county_witness','')))
    frame=pd.DataFrame(expanded)
   frames.append(frame)
 wiki=pd.concat(frames,ignore_index=True).drop_duplicates(['source_record_id','article_title']);wiki=wiki[wiki.latitude.notna()&wiki.longitude.notna()]
 admitted_wiki={}
 for q in wiki.to_dict('records'):
  sid=q['source_record_id'];target=by.loc[sid]
  if sid in p.index or sid in added or sid not in r.index:continue
  if not bool(r.loc[sid,'has_ownpoint']) and re.search(r'\(часть',normalize(target.settlement_name)):continue
  rivals=o[o.census_year.eq(target.census_year)&o.region_norm.eq(target.region_norm)&o.name_norm.eq(target.name_norm)&o.type_norm.eq(target.type_norm)&o.county.eq(county_key(target.district_raw))]
  if len(rivals)>1:held.append(dict(source_record_id=sid,reason='same_year_native_county_name_type_homonyms_no_own_code',article=q['article_title']));continue
  title=q['article_title'];base=normalize(title.split(' (')[0]);ownkeys=keys(target.settlement_name);literal=base in ownkeys or aliases.get(target.settlement_name)==title
  if not literal or normalize(title).startswith(('сельское поселение','городской округ')) or bool(q.get('disambiguation',False)):continue
  source=Path(q['capture']);expected=q['capture_sha256'];actual=sha(source)
  if expected!=actual:raise ValueError('wiki hash mismatch')
  inputs[str(source)]=actual;capture=json.load(gzip.open(source,'rt'));page=capture['query']['pages'][str(int(q['pageid']))];rev=page['revisions'][0];text=rev.get('*',rev.get('slots',{}).get('main',{}).get('*',''));nt=normalize(text)
  # County text plus locality type explicitly distinguished from a municipal object.
  if not bool(q['county_literal_present']):continue
  if not any(w in nt for w in ['— село','— посёлок','— поселок','— деревня','— упразднённый посёлок','— упраздненный поселок','— хутор','— станица']):continue
  if target.settlement_name in aliases and target.settlement_name!='Малое Козыревское' and normalize(target.settlement_name) not in nt:continue
  if target.settlement_name=='Малое Козыревское' and 'малое козыревское' not in nt:continue
  if not rawcheck(sid):continue
  xy=(float(q['latitude']),float(q['longitude']));comp=o[o.root.eq(target.root)];otherpoints=comp[comp.source_record_id.isin(p.index)]
  if any(distance_km(xy,(float(p.loc[s,'latitude']),float(p.loc[s,'longitude'])))>5 for s in otherpoints.source_record_id):held.append(dict(source_record_id=sid,reason='independent_ownwiki_point_contradicts_accepted_component_point',article=title));continue
  points.append(dict(target_source_record_id=sid,latitude=xy[0],longitude=xy[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id='ruwiki:pageid='+str(int(q['pageid'])),point_origin_file=str(source),point_origin_sha256=actual,point_origin_locator='pageid='+str(int(q['pageid']))+';revid='+str(int(q['revid']))+';prop=coordinates;primary=earth',point_origin_kind='own_locality_Wikipedia_primary_coordinate_claim',admission_rule='source_bound_own_name_county_type_and_explicit_printed_alias',direct_historical_coordinate_measurement=False,native_code_binding_asserted=False,boundary_comparability_asserted=False,point_temporal_interpretation='Own locality representative used retrospectively; no census date measurement',own_article_title=title,own_article_revision=q['revid'],source_county=target.district_raw))
  added.add(sid);admitted_wiki[sid]=(q,text);witnesses.append(dict(source_record_id=sid,kind='own_article_binding',source_file=str(source),source_sha256=actual,source_locator='pageid='+str(int(q['pageid']))+';revid='+str(int(q['revid'])),name_verified=True,population_preserved=True,witness=str(q['history_name_witness'])[:3500]))
 # Raw classifier and GeoKLADR own code must be a unique typed county object.
 geo=pd.read_csv('/dev/shm/over500-20261009/south_geo_matches.csv',dtype={'historical_okato':str});SQL=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');inputs[str(SQL)]=sha(SQL);inputs[str(DBF)]=sha(DBF)
 for sid,g in geo.groupby('source_record_id'):
  if sid in p.index or sid in added:continue
  if g.historical_okato.nunique()!=1 or g.raw_record_1based.nunique()!=1:held.append(dict(source_record_id=sid,reason='multiple_historical_own_codes_or_points',article=''));continue
  a=g.iloc[0];target=by.loc[sid]
  rivals=o[o.census_year.eq(target.census_year)&o.region_norm.eq(target.region_norm)&o.name_norm.eq(target.name_norm)&o.type_norm.eq(target.type_norm)&o.county.eq(county_key(target.district_raw))]
  if len(rivals)>1:held.append(dict(source_record_id=sid,reason='same_year_native_county_name_type_homonyms_no_own_code',article=''));continue
  lat,lon=float(a.latitude_y),float(a.longitude_y)
  # Geo raw own label must repeat classifier literal except known singular designator inflection.
  def label(v):return normalize(v).replace('отделения','отделение')
  if label(a.geo_name)!=label(a.name_raw) or a.deleted_marker!=' ':continue
  if not(-90<=lat<=90 and -180<=lon<=180) or (lat,lon)==(0,0):continue
  if not rawcheck(sid):continue
  points.append(dict(target_source_record_id=sid,latitude=lat,longitude=lon,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=a.historical_okato,point_origin_file=str(DBF),point_origin_sha256=inputs[str(DBF)],point_origin_locator='DBF_record_1based='+str(a.raw_record_1based)+';byte_offset_0based='+str(a.raw_byte_offset),point_origin_kind='GeoKLADR_2011_raw_own_settlement_record',admission_rule='unique_exact_historical_classifier_name_type_county_own_code_and_raw_GeoKLADR',classifier_origin_file=str(SQL),classifier_origin_sha256=inputs[str(SQL)],classifier_origin_locator='line_1based='+str(a.source_line_1based),native_code_binding_asserted=False,direct_historical_coordinate_measurement=False,boundary_comparability_asserted=False,point_temporal_interpretation='2011 own locality point reused retrospectively; census-date measurement not asserted'))
  added.add(sid);witnesses.append(dict(source_record_id=sid,kind='raw_classifier_GeoKLADR',source_file=str(DBF),source_sha256=inputs[str(DBF)],source_locator='DBF_record_1based='+str(a.raw_record_1based),name_verified=True,population_preserved=True,witness=json.dumps({k:str(a[k]) for k in ['historical_okato','name_raw','geo_name','geo_type','county','source_line_1based','raw_record_1based','latitude_y','longitude_y']},ensure_ascii=False)))
 # Literal source-declared alternative names and independently checked own article historical aliases.
 edgekeys={(e['from_source_record_id'],e['to_source_record_id']) for e in edges};o['county']=o.district_raw.map(county_key)
 for sid in list(r.index.intersection(d.source_record_id)):
  target=by.loc[sid]
  if '(часть' in normalize(target.settlement_name):continue
  nk=keys(target.settlement_name);alias=aliases.get(target.settlement_name)
  if alias:nk.add(normalize(alias.split(' (')[0]))
  if len(nk)==1 and not alias:continue
  candidates=o[o.region_norm.eq(target.region_norm)&o.county.eq(county_key(target.district_raw))&o.census_year.ne(target.census_year)&o.name_norm.map(normalize).isin(nk)]
  candidates=candidates[candidates.type_norm.eq(target.type_norm)]
  # Gender aliases explicitly witnessed in own article may include printed urban/rural type differences; admitted only same rural physical object.
  if alias and sid in admitted_wiki:candidates=o[o.region_norm.eq(target.region_norm)&o.county.eq(county_key(target.district_raw))&o.census_year.ne(target.census_year)&o.name_norm.map(normalize).isin(nk)&o.type_norm.isin(['поселок','село'])]
  if candidates.census_year.duplicated().any():continue
  for c in candidates.to_dict('records'):
   cid=c['source_record_id']
   if c['root']==target.root:continue
   ya=set(o[o.root.eq(target.root)].census_year);yb=set(o[o.root.eq(c['root'])].census_year)
   if ya&yb:continue
   targetpoint=next((a for a in points if a['target_source_record_id']==sid),None);donor=p.loc[cid] if cid in p.index else targetpoint
   if donor is None:continue
   xy=(float(donor['latitude']),float(donor['longitude']));allmembers=o[o.root.isin([target.root,c['root']])]
   if any(distance_km(xy,(float(p.loc[s,'latitude']),float(p.loc[s,'longitude'])))>5 for s in allmembers.source_record_id if s in p.index):held.append(dict(source_record_id=sid,reason='literal_alias_identity_with_conflicting_accepted_points',article=''));continue
   if not rawcheck(sid) or not rawcheck(cid):continue
   newedges.append(dict(from_source_record_id=sid,to_source_record_id=cid,relation='same_place',decision_status='checked_rule_accepted',admission_rule='unique_explicit_native_literal_alias_or_source_witnessed_historical_own_name_same_county',name_norm=target.name_norm,type_norm=target.type_norm,region_norm=target.region_norm,county_key=county_key(target.district_raw),source_context_witness_file=str(OUT/'admission_witnesses.csv.gz'),population_boundary_comparability_asserted=False));o.loc[o.root.eq(c['root']),'root']=target.root
   if sid not in p.index and sid not in added and cid in p.index:
    points.append(dict(target_source_record_id=sid,latitude=xy[0],longitude=xy[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=cid,coordinate_origin_ledger=str(CACHE/'applied_point_snapshot.parquet'),coordinate_origin_ledger_sha256=inputs[str(CACHE/'applied_point_snapshot.parquet')],coordinate_origin_ledger_locator='target_source_record_id='+cid,admission_rule='own_point_continuity_over_source_verified_explicit_literal_alias',direct_historical_coordinate_measurement=False,boundary_comparability_asserted=False,point_temporal_interpretation='Own representative continuity inference; no historical measurement'));added.add(sid)
 edges.extend(newedges);pd.DataFrame(edges).to_csv(OUT/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(OUT/'accepted_point_use_delta.csv',index=False)
 pd.DataFrame(witnesses).to_csv(OUT/'admission_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(held,columns=['source_record_id','reason','article']).to_csv(OUT/'explicit_conflict_holds.csv',index=False)
 used=set(e['from_source_record_id'] for e in edges)|set(e['to_source_record_id'] for e in edges);checks=pd.read_csv(OUT/'physical_source_context_checks.csv');checks=checks[checks.target_source_record_id.isin(used)];checks.to_csv(OUT/'physical_source_context_checks.csv.gz',index=False,compression={'method':'gzip','mtime':0});(OUT/'physical_source_context_checks.csv').unlink()
 for e in edges:
  if str(e.get('source_context_witness_file','')).endswith('physical_source_context_checks.csv'):e['source_context_witness_file']=str(OUT/'physical_source_context_checks.csv.gz')
 pd.DataFrame(edges).to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
 for i,z in d.iterrows():
  sid=z.source_record_id
  if sid in added or sid in used:d.loc[i,'decision']='accepted_delta';d.loc[i,'reason']='accepted_own_point_or_source_verified_native_identity'
  d.loc[i,'has_ownpoint_after']=sid in p.index or sid in added
 d.to_csv(OUT/'dispositions.csv',index=False);receipt.update(accepted_identity_edges=len(edges),accepted_point_uses=len(points),changed_residual_rows=int(d.decision.eq('accepted_delta').sum()),inputs_sha256=inputs,outputs_sha256={f.name:sha(f) for f in OUT.iterdir() if f.suffix in ['.csv','.gz']});(OUT/'manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['accepted_identity_edges','accepted_point_uses','changed_residual_rows']},ensure_ascii=False))
if __name__=='__main__':main()

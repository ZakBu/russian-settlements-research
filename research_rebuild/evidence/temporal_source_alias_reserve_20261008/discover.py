from pathlib import Path
import pandas as pd,duckdb,re,json,sys,ast,collections,hashlib
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;B=O.parent/'grounded_current_carrier_expansion_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
tree=ast.parse((B/'discover_closed_geometry.py').read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['nm','ty']],type_ignores=[]),'closednames','exec'))
D=Path('/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb');S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=O.parent/'main_axis_residual_application63_20261008/applied_point_snapshot.parquet';V=O.parent/'main_axis_residual_registry_20261008/competitors/all_selected_native_competitors.parquet';G=O.parent/'temporal_after_new_current_points_20261008/resolved_candidate_geometry.parquet';gate=B/'exact_7966_current_grounding_gate_diagnostics.csv.gz';old=pd.read_csv(gate).fillna('');old=old[old.route_gate_reason.str.startswith('no literal compatible')];con=duckdb.connect();f=con.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,oktmo,okato,population,is_additive_settlement_record from read_parquet(?)',[str(S)]).fetchdf().fillna('');ef=con.execute('select source_record_id,effective_region_norm from read_parquet(?)',[str(V)]).fetchdf().set_index('source_record_id').effective_region_norm.to_dict();f.region_norm=f.source_record_id.map(ef);pts=con.execute('select * from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('target_source_record_id').to_dict('index');geom=con.execute('select * from read_parquet(?)',[str(G)]).fetchdf().set_index('source_record_id').to_dict('index');con.close();rd=f.set_index('source_record_id').to_dict('index');c=duckdb.connect(str(D),read_only=True);fields=c.execute("select * from wikipedia_template_fields where lower(field_name_raw) in ('русское название','название','прежние имена','прежние названия','прежнее название','старое название','прошлые названия','код октмо','октмо','lat_deg','lon_deg','статус','регион','район') and article_pageid in (select article_pageid from wikipedia_template_fields where lower(field_name_raw) in ('прежние имена','прежние названия','прежнее название','старое название','прошлые названия') and length(trim(coalesce(field_value_wikitext,'')))>0)").fetchdf();c.close();byarticle=fields.groupby(['article_pageid','revision_id']);codefields={'код октмо','октмо'};codeindex=collections.defaultdict(list);pointarticles=collections.defaultdict(list);aliasindex=collections.defaultdict(list);rawaliases=[]
for sid,z in rd.items():
 if int(z['census_year'])!=2021:continue
 code=str(z['oktmo']).removesuffix('.0');codeindex[code].append(sid)
 if sid in pts:
  refs=' '.join(str(pts[sid].get(k,'')) for k in ['coordinate_source_record_id','point_origin_locator'])
  for pat in [r'ruwiki:(\d+):',r'pageid=(\d+)']:
   m=re.search(pat,refs)
   if m:pointarticles[int(m.group(1))].append(sid)
def clean(v):
 v=re.sub(r'<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>','',v,flags=re.S);v=re.sub(r'\[\[(?:[^]|]+\|)?([^]]+)\]\]',r'\1',v);v=re.sub(r'<br\s*/?>|[;\n]',',',v);v=re.sub(r'<[^>]+>|\{\{.*?\}\}', '',v);return v.replace("''",'')
def angle(df,axis):
 vv=df[df.field_name_raw.str.lower().eq(axis+'_deg')].field_value_wikitext.tolist()
 if not vv:return None
 v=str(vv[0]);m=re.match(r'\s*(-?\d+(?:\.\d+)?)',v)
 if not m:return None
 deg=float(m.group(1));mins=re.search(axis+r'_min\s*=\s*(\d+(?:\.\d+)?)',v);secs=re.search(axis+r'_sec\s*=\s*(\d+(?:\.\d+)?)',v)
 return deg+(float(mins.group(1))/60 if mins else 0)+(float(secs.group(1))/3600 if secs else 0)
currentname=collections.defaultdict(list)
for sid,z in rd.items():
 if int(z['census_year'])==2021 and z['is_additive_settlement_record']:currentname[nm(z['settlement_name'])].append(sid)
for (page,rev),df in byarticle:
 own=df[df.field_name_raw.str.lower().isin(['русское название','название'])]
 former=df[df.field_name_raw.str.lower().isin(['прежние имена','прежние названия','прежнее название','старое название','прошлые названия']) & df.field_value_wikitext.fillna('').ne('')]
 if former.empty or own.empty:continue
 owns={nm(clean(v)) for v in own.field_value_wikitext.dropna()};codes={x for v in df[df.field_name_raw.str.lower().isin(codefields)].field_value_wikitext.dropna() for x in re.findall(r'\b\d{11}\b',v)};carriers=set(pointarticles[int(page)])|{sid for code in codes for sid in codeindex[code]};carriers={sid for sid in carriers if sid in pts and nm(rd[sid]['settlement_name']) in owns}
 status=[normalize(clean(str(v))) for v in df[df.field_name_raw.str.lower().eq('статус')].field_value_wikitext];areg=[normalize(clean(str(v))) for v in df[df.field_name_raw.str.lower().eq('регион')].field_value_wikitext];acounty={county_key(clean(str(v))) for v in df[df.field_name_raw.str.lower().eq('район')].field_value_wikitext};lat,lon=angle(df,'lat'),angle(df,'lon');physicalarticle=any(x in ['село','деревня','поселок','пгт','рабочий поселок','город','хутор','станица','аул','станция','железнодорожная станция'] for x in status);independent=set()
 if physicalarticle and lat is not None and lon is not None:
  for ownname in owns:
   for sid in currentname[ownname]:
    z=rd[sid]
    if sid not in pts or county_key(z['district_raw']) not in acounty or not any(z['region_norm'] in reg or reg in z['region_norm'] for reg in areg) or distance_km((lat,lon),(float(pts[sid]['latitude']),float(pts[sid]['longitude'])))>1:continue
    rivals=[ri for ri in currentname[ownname] if rd[ri]['region_norm']==z['region_norm'] and county_key(rd[ri]['district_raw'])==county_key(z['district_raw']) and (ri not in pts or distance_km((lat,lon),(float(pts[ri]['latitude']),float(pts[ri]['longitude'])))<=1)]
    if rivals==[sid]:independent.add(sid)
 carriers.update(independent)
 for row in former.itertuples():
  for chunk in clean(row.field_value_wikitext).split(','):
   chunk=re.sub(r'^\s*(?:до\s+\d{4}\s*(?:года|г\.?|:)?)\s*','',chunk);chunk=re.sub(r'\s*\((?:до\s+)?\d{4}[^)]*\)\s*','',chunk).strip();name=nm(chunk)
   if not name or len(name)>100 or re.search(r'\b(?:год|года|после|переименован|создан|образован)\b',name):continue
   for sid in carriers:
    proof={'current_source_record_id':sid,'former_literal':chunk,'former_name_key':name,'article_pageid':int(page),'revision_id':int(rev),'canonical_title':row.canonical_title,'former_field':row.field_name_raw,'former_raw_wikitext':row.field_value_wikitext,'permanent_url':row.permanent_url,'source_line_number':int(row.source_line_number),'article_own_native_name':rd[sid]['settlement_name'],'binding':'proper ownNParticle literalname/status/region/county +publishedpoint within1km ofacceptedcurrentownpoint +allrawcurrentnamesakes excluded' if sid in independent else ('acceptedownpoint literalpageID plusowninfoboxname' if sid in pointarticles[int(page)] else 'literal own11digitOKTMO plusowninfoboxname'),'article_latitude':lat,'article_longitude':lon,'article_status_json':json.dumps(status),'article_region_json':json.dumps(areg),'article_county_json':json.dumps(list(acounty))};aliasindex[(rd[sid]['region_norm'],name)].append(proof)
raw=[];holds=[]
for z in old.to_dict('records'):
 sid=z['source_record_id'];hits=aliasindex[(z['region'],nm(z['name']))];g=geom.get(sid);valid=[]
 for h in hits:
  cur=h['current_source_record_id'];d=distance_km((float(g['latitude']),float(g['longitude'])),(float(pts[cur]['latitude']),float(pts[cur]['longitude']))) if g else None
  raw.append({**z,**h,'old_imported_candidate_distance_km':d,'candidate_status':'candidate_only_not_identity_admitted','old_geometry_not_measurement':True})
 for h in hits:
  if h not in rawaliases:rawaliases.append(h)
 if not hits:holds.append({'source_record_id':sid,'name':z['name'],'population':z['native_population'],'held_reason':'no positive current-ownarticle literal former-name field match under closed parser'})
pd.DataFrame(raw).to_csv(O/'source_explicit_former_name_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(holds).to_csv(O/'former_name_route_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0});receipt={'actual_old_reserve_rows':len(old),'old_reserve_population_by_year':old.groupby('year').native_population.sum().to_dict(),'source_positive_former_name_candidate_pairs':len(raw),'candidate_old_distinct_rows':len({z['source_record_id'] for z in raw}),'candidate_old_population_by_year':pd.DataFrame(raw).drop_duplicates('source_record_id').groupby('year').native_population.sum().to_dict() if raw else {},'accepted_edges':0,'accepted_points':0,'candidate_not_applied_gain':True,'next_gate':'final64snapshot membership/pointcompatibility +literal original historical leaf/count +allactualnative same-year rival and lifecycle checks','input_pins':{str(q):sha(q) for q in [D,S,P,V,G,gate]},'output_pins':{q.name:sha(q) for q in O.glob('*.csv.gz')}};(O/'candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))

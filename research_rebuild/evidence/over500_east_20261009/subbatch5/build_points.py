from pathlib import Path
import pandas as pd,json,gzip,re,hashlib,xlrd
O=Path(__file__).parent;D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');R=pd.read_csv(O.parent/'assigned.csv').fillna('');by=D.set_index('source_record_id',drop=False);P=pd.read_parquet('/dev/shm/over500-20261009/points_compact.parquet',columns=['target_source_record_id']);existing=set(P.target_source_record_id)
for z in [O.parent,O.parent/'subbatch2',O.parent/'subbatch3',O.parent/'subbatch4']:existing.update(pd.read_csv(z/'accepted_point_use_delta.csv').target_source_record_id)
C=json.load(gzip.open(O/'cached_own_pages.json.gz'));norm=lambda s:' '.join(re.sub(r'[^а-я0-9 ]',' ',str(s).lower().replace('ё','е')).split());name=lambda s:re.sub(r'^(при станции|железнодорожная станция|станция|станции|поселок) +','',norm(s));index={}
for c in C:index.setdefault(name(c['page']['title'].split('(')[0]),[]).append(c)
books={};points=[];w=[];disp=[]
def owncoords(txt):
 vals={}
 for kind in ['lat','lon']:
  for part in ['deg','min','sec']:
   m=re.search(r'\|\s*'+kind+'_'+part+r'\s*=\s*([\d.]+)',txt);vals[kind+'_'+part]=float(m.group(1))if m else 0
 if not vals['lat_deg']or not vals['lon_deg']:return None
 return vals['lat_deg']+vals['lat_min']/60+vals['lat_sec']/3600,vals['lon_deg']+vals['lon_min']/60+vals['lon_sec']/3600
for r in R.itertuples():
 if r.source_record_id in existing:continue
 t=by.loc[r.source_record_id];nn=name(t.settlement_name);cand=[];county=t.county;sub='';native_file=Path('/workspace/settlements-raw')/t.source_file;rawrow=[]
 if t.census_year==2002 and native_file.exists()and native_file.suffix=='.xls':
  if str(native_file)not in books:books[str(native_file)]=xlrd.open_workbook(str(native_file))
  b=books[str(native_file)];shname=t.source_record_id.rsplit(':',2)[1];s=b.sheet_by_name(shname)if shname in b.sheet_names()else b.sheet_by_index(int(shname));ordinal=int(t.source_record_id.rsplit(':',1)[1])-1;rawrow=s.row_values(ordinal)
  for k in range(ordinal-1,max(-1,ordinal-100),-1):
   v=str(s.cell_value(k,0));
   if re.search('сельсовет|сельское поселение|сельская администрация',v,re.I):sub=v.strip();break
 for c in index.get(nn,[]):
  p=c['page'];txt=p.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','');nt=norm(txt);co=owncoords(txt)
  if not co or not county:continue
  # Own article must literally name native county and effective subject.
  ct=county.split();key=next((z for z in ct if len(z)>4 and z not in ['районное','муниципальное','образование','город','города']),county)
  if key not in nt:continue
  reg=t.region_norm;regs=['саха','якут']if reg=='саха якутия'else['ямало','ненец']if reg=='ямало ненецкий'else[reg.split()[0]]
  if not all(q in nt for q in regs):continue
  natives=D[D.census_year.eq(t.census_year)&D.region_norm.eq(t.region_norm)&D.name_norm.eq(t.name_norm)&D.county.eq(county)]
  if len(natives)>1:
   # Homonyms require a printed historical council AND a literal own census-year value.
   subkey=norm(re.sub(r'сельсовет|сельская администрация|сельское поселение','',sub,flags=re.I)).split()
   if not subkey or subkey[0]not in nt:continue
   if not re.search(r'2002\s*[^\n]{0,40}\b'+str(int(t.population))+r'\b',txt):continue
  m=re.search(r'\|\s*статус\s*=([^\n|]+)',txt);typ=norm(m.group(1))if m else''
  if t.type_norm not in typ:
   if not (t.type_norm in ['село','деревня','поселок'] and any(z in typ for z in ['село','деревня','поселок']) and name(t.settlement_name)==norm(t.settlement_name)):continue
  cand.append((c,co,sub,rawrow))
 if len(cand)!=1:
  disp.append(dict(source_record_id=r.source_record_id,disposition='held_ownarticle_point_not_uniquely_native_bound',candidate_count=len(cand)));continue
 c,co,sub,rawrow=cand[0];p=c['page'];wid=len(w);w.append(dict(target_source_record_id=r.source_record_id,raw_native_name=t.settlement_name,raw_native_type=t.settlement_type,raw_native_county=t.district_raw,effective_county=county,raw_prior_council_heading=sub,raw_target_cells=rawrow,source_file=c['source_path'],source_sha256=c['source_sha256'],pageid=p['pageid'],revision=p['revisions'][0]['revid'],own_article_title=p['title'],own_article_inferred_point=co,all_article_county_candidates=1,interpretation='Independent own locality article name/type/subject/county binding, native rival guard; point used retrospectively as representative own local site, no provider-ID claim.'))
 points.append(dict(target_source_record_id=r.source_record_id,latitude=co[0],longitude=co[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=f'ruwiki:page{p["pageid"]}:revision{p["revisions"][0]["revid"]}',point_origin_file=c['source_path'],point_origin_sha256=c['source_sha256'],point_origin_locator=f'page{p["pageid"]}:revision{p["revisions"][0]["revid"]}:wikitext.infobox.lat_deg/lat_min/lat_sec+lon_deg/lon_min/lon_sec',point_origin_kind='independent_own_named_locality_article_coordinate',coordinate_binding_rule='independent_own_article_literal_name_type_sourcecounty_subject_and_native_rival_guard',point_use_inference='Own locality representative point inferred retrospectively; exact sourceyear censusday measurement and boundaries unknown.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,external_provider_ID_binding_asserted=False,evidence_file=str(O/'point_binding_witnesses.json.gz'),evidence_locator=f'[{wid}]'))
 disp.append(dict(source_record_id=r.source_record_id,disposition='accepted_direct_own_article_representative_point_temporal_route_unchanged',candidate_count=1))
with gzip.open(O/'point_binding_witnesses.json.gz','wt')as f:json.dump(w,f,ensure_ascii=False)
pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(columns=['from_source_record_id','to_source_record_id','relation','decision_status','admission_method','admission_rule','evidence_file','evidence_locator']).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(disp).to_csv(O/'record_dispositions.csv',index=False);print(len(points));print(pd.DataFrame(w)[['target_source_record_id','raw_native_name','own_article_title']].to_string(index=False))

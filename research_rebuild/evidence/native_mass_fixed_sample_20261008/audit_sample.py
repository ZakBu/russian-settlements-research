import hashlib,json,math,re
from pathlib import Path
import pandas as pd,duckdb,xlrd
Z=Path(__file__).resolve().parent;S=Z.parent/'native_singleton_rural_mass_20261008';RAW=Path('/workspace/settlements-raw');sample=pd.read_csv(Z/'fixed_sample40.csv',keep_default_na=False);selection=json.loads((Z/'selection_receipt.json').read_text());sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
for p,h in selection['input_pins'].items():assert sha(p)==h,('sourceinputs changed',p)
C=duckdb.connect();obs=C.execute("select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,population_value_quality,oktmo,okato,source_file,latitude,longitude,is_additive_settlement_record from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf();by=obs.set_index('source_record_id');obs['row']=obs.source_record_id.map(lambda v:int(re.search(r'(\d+)$',v).group(1)));norm=lambda v:' '.join(str(v).lower().replace('ё','е').replace('_',' ').split()) if pd.notna(v) else '';books={};pins={};records=[];contexts=[]
def county(v):
 text=re.split(r'\s+-\s+(?:все\s+)?сельское население',norm(v))[0];text=text.replace('муниципальный','').replace('городской округ','').replace('район','');text=' '.join(text.replace('-',' ').replace('«','').replace('»','').replace('\"','').split())
 return {'чехов':'чеховский','киров':'кировский','павловский посад':'павлово посадский','гаврилов ям':'гаврилов ямский'}.get(text,text)

nprefix=re.compile(r'^\s*(?:село|деревня|хутор|пос[её]лок|станица|слобода|аул|кишлак|город|пгт|рабочий пос[её]лок|с\.|д\.|х\.|п\.)\s+',re.I)
def book(path):
 if str(path) not in books:books[str(path)]=xlrd.open_workbook(str(path));pins[str(path)]=sha(path)
 return books[str(path)]
def rawleaf(sid):
 r=by.loc[sid];p=RAW/r.source_file;sheet=book(p).sheet_by_name(sid.rsplit(':',2)[1]);n=int(sid.rsplit(':',1)[1]);vals=sheet.row_values(n-1);label=next((str(v).strip() for v in vals if isinstance(v,str) and norm(v).endswith(norm(r.settlement_name))),None);typed=bool(label and nprefix.search(label));matches=[v for v in vals if str(v).strip() in {str(int(r.population)),str(float(r.population))}];head=None
 for j in range(n-2,-1,-1):
  candidates=[str(v).strip() for v in sheet.row_values(j) if isinstance(v,str) and re.search(r'\bрайон(?:а)?\b',v.lower()) and not nprefix.match(v) and not re.match(r'^\s*(?:сельсовет|сельские округа|волости|поселения)',v,re.I)]
  if candidates:head=dict(row=j+1,label=candidates[0]);break
 return dict(source_record_id=sid,source_path=str(p),source_sha256=pins[str(p)],sheet=sheet.name,row=n,raw_label=label,raw_population_numeric_matches=matches,typed_own_NP=typed,selected_population=int(r.population),selected_quality=r.population_value_quality,nearest_printed_county=head,label_population_matches=bool(label and matches),is_additive=bool(r.is_additive_settlement_record))
obs['norm_name']=obs.settlement_name.map(norm)
raw21=RAW/'data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet';pins[str(raw21)]=sha(raw21)
for case in sample.to_dict('records'):
 sid02,sid10,sid21=[case[k] for k in ['native2002_source_record_id','native2010_source_record_id','native2021_source_record_id']];errors=[];holds=[];r02=by.loc[sid02];r10=by.loc[sid10];r21=by.loc[sid21];leaf02,leaf10=rawleaf(sid02),rawleaf(sid10)
 for leaf in [leaf02,leaf10]:
  if not leaf['label_population_matches'] or not leaf['typed_own_NP'] or not leaf['is_additive']:errors.append('rawownleaf count/type/grain mismatch')
  contexts.append(dict(target2010=sid10,kind='native_raw_leaf',witness_json=json.dumps(leaf,ensure_ascii=False)))
 head=leaf02['nearest_printed_county'];rawco=county(head['label']) if head else ''
 if rawco and rawco!=county(r02.district_raw):errors.append('native2002 truecounty heading differs importedcounty')
 n=int(sid21.rsplit(':',1)[1]);cur=C.execute('select object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement,population,fias_id_dadata,fias_level_dadata,settlement_fias_id_dadata,settlement_type_full_dadata,latitude_dadata,longitude_dadata from read_parquet(?) limit 1 offset ?',[str(raw21),n-1]).fetchdf().iloc[0].to_dict()
 if int(cur['population'])!=int(r21.population) or str(cur['oktmo'])!=str(r21.oktmo):errors.append('raw2021 ownvalue/nativecode differs')
 if norm(r21.settlement_name) not in norm(cur['object_name']) and norm(r21.settlement_name)!=norm(cur['settlement']):errors.append('raw2021ownname binding differs')
 if not nprefix.search(str(cur['object_name'])) and not cur['settlement_type_full_dadata']:holds.append('raw2021typed ownNPlabel unclear')
 if county(cur['mun_upper'])!=county(r02.district_raw):holds.append('actual02/21county captions require explicitcountychange review')
 # Independently resolve flat2010 county by publication-order neighbours whose literal name/type is regionunique in BOTH native02 and21, without accepted graph/context predicates.
 anchorproof=[];regional=obs[obs.region_norm.eq(r10.region_norm)]
 fileleaf=obs[obs.census_year.eq(2010)&obs.source_file.eq(r10.source_file)].copy();targetrow=int(sid10.rsplit(':',1)[1])
 for side in [-1,1]:
  nearby=fileleaf[(fileleaf.row-targetrow)*side>0].copy();nearby['delta']=(nearby.row-targetrow).abs();nearby=nearby[nearby.delta.le(20)].sort_values('delta')
  for nb in nearby.itertuples():
   candidates=regional[regional.norm_name.eq(norm(nb.settlement_name))&regional.settlement_type.eq(nb.settlement_type)];old=candidates[candidates.census_year.eq(2002)];now=candidates[candidates.census_year.eq(2021)]
   if len(old)==len(now)==1 and county(old.iloc[0].district_raw)==county(now.iloc[0].district_raw) and county(old.iloc[0].district_raw):
    oldw=rawleaf(old.iloc[0].source_record_id);midw=rawleaf(nb.source_record_id)
    if oldw['label_population_matches'] and oldw['typed_own_NP'] and midw['label_population_matches'] and midw['typed_own_NP']:
     anchorproof.append(dict(side=side,anchor2010=nb.source_record_id,anchor2002=old.iloc[0].source_record_id,anchor2021=now.iloc[0].source_record_id,raw2002county=oldw['nearest_printed_county'],native2021county=now.iloc[0].district_raw,county_key=county(old.iloc[0].district_raw),offset=nb.row-targetrow));break
 if len(anchorproof)!=2 or any(v['county_key']!=county(r02.district_raw) for v in anchorproof):holds.append('independent rawneighbour countybinding unresolved')
 contexts.append(dict(target2010=sid10,kind='independent_regionunique_rawneighbour_county_binding',witness_json=json.dumps(anchorproof,ensure_ascii=False)))
 point=json.loads(case['source_positive_point_origin_json']);origin=Path(point.get('point_origin_file',''));kind=point.get('point_origin_kind','');oplat=float(point['latitude']);oplon=float(point['longitude']);origin_status='unresolved'
 if origin.is_file():
  pins[str(origin)]=sha(origin)
  if pins[str(origin)]!=point.get('point_origin_sha256'):errors.append('pointorigin bytes differ')
 if origin==raw21:
  if cur['fias_level_dadata']=='6' and str(point.get('coordinate_source_record_id')) in {str(cur['fias_id_dadata']),sid21} and abs(float(cur['latitude_dadata'])-oplat)<1e-8 and abs(float(cur['longitude_dadata'])-oplon)<1e-8:origin_status='actual native ownFIASlevel6 row/code/point verified'
  else:holds.append('pointorigin nativeFIAS/code/coords require review')
 else:holds.append('external pointorigin requires literalownbinding inspection')
 # Independently enumerate every literalname regional rival across classes, all three years.
 rivals=obs[obs.region_norm.eq(r10.region_norm)&obs.settlement_name.map(norm).eq(norm(r10.settlement_name))];rivalrecords=[]
 for v in rivals.to_dict('records'):
  samecounty=county(v['district_raw'])==county(r02.district_raw);selected=v['source_record_id'] in {sid02,sid10,sid21};distance=None
  if pd.notna(v['latitude']) and pd.notna(v['longitude']):
   a,b,c,d=map(math.radians,[oplat,oplon,float(v['latitude']),float(v['longitude'])]);h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2;distance=6371.0088*2*math.asin(min(1,math.sqrt(h)))
  rivalrecords.append(dict(source_record_id=v['source_record_id'],year=int(v['census_year']),name=v['settlement_name'],type=v['settlement_type'],county=v['district_raw'],selected=selected,same_old_county=samecounty,native_point_distance_km=distance))
  if not selected and samecounty and int(v['census_year']) in [2002,2021]:holds.append('samecounty literalname rival needs grain/type exclusion')
 contexts.append(dict(target2010=sid10,kind='allregional_crossclass_literalname_rivals',witness_json=json.dumps(rivalrecords,ensure_ascii=False)))
 contexts.append(dict(target2010=sid10,kind='actual2021_rawownobject',witness_json=json.dumps(cur,ensure_ascii=False)))
 contexts.append(dict(target2010=sid10,kind='acceptedpointorigin',witness_json=json.dumps(point,ensure_ascii=False)))
 records.append(dict(native2010_source_record_id=sid10,native2002_source_record_id=sid02,native2021_source_record_id=sid21,name=case['name'],region=case['region'],type=case['type'],stratum=case['stratum'],population2010=int(r10.population),raw2002_county=rawco,raw2021_county=cur['mun_upper'],native2010_rawcounty_present=leaf10['nearest_printed_county'] is not None,regional_literalname_rivals=len(rivals),point_origin_check=origin_status,classification='error' if errors else 'hold' if holds else 'pass',errors_json=json.dumps(sorted(set(errors))),holds_json=json.dumps(sorted(set(holds))),retrospective_point_use='explicit continuityinference; historicalmeasurement notasserted'))
pd.DataFrame(records).to_csv(Z/'independent_sample_ledger.csv',index=False);pd.DataFrame(contexts).to_csv(Z/'literal_raw_and_rival_witnesses.csv.gz',index=False);(Z/'independent_raw_input_pins.json').write_text(json.dumps(pins,indent=2)+'\n');print(pd.DataFrame(records)[['name','region','stratum','classification','errors_json','holds_json']].to_string(index=False))

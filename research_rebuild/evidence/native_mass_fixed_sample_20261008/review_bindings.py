import json,re,gzip,hashlib,math
from pathlib import Path
import pandas as pd,duckdb,xlrd
Z=Path(__file__).resolve().parent;S=Z.parent/'native_singleton_rural_mass_20261008';samples=pd.read_csv(Z/'fixed_sample40.csv',keep_default_na=False);claims=pd.read_csv(S/'positive_literal_native_county_ownpoint_candidates.csv.gz',keep_default_na=False);ledger=pd.read_csv(Z/'independent_sample_ledger.csv',keep_default_na=False);literal=pd.read_csv(Z/'literal_raw_and_rival_witnesses.csv.gz',keep_default_na=False);C=duckdb.connect();obs=C.execute("select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,source_file,oktmo from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf();by=obs.set_index('source_record_id');raw=Path('/workspace/settlements-raw');curfile=raw/'data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet';books={};checks=[];pointchecks=[];georivals=[];pins=json.loads((Z/'independent_raw_input_pins.json').read_text());sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
nprefix=re.compile(r'^\s*(?:станция|железнодорожная станция|село|деревня|хутор|пос[её]лок|станица|слобода|аул|кишлак|город|пгт|рабочий пос[её]лок|с\.|д\.|х\.|п\.)\s+',re.I)
def norm(v):return ' '.join(str(v).lower().replace('ё','е').replace('_',' ').split())
def rawrow(sid):
 r=by.loc[sid];p=raw/r.source_file;pins[str(p)]=sha(p)
 if sid.startswith('2021:'):
  n=int(sid.rsplit(':',1)[1]);f=C.execute('select object_name,oktmo,mun_upper,population,fias_level_dadata,fias_id_dadata,latitude_dadata,longitude_dadata from read_parquet(?) limit 1 offset ?',[str(curfile),n-1]).fetchdf().iloc[0].to_dict();return dict(source_record_id=sid,row=n,label=f['object_name'],population=f['population'],county=f['mun_upper'],raw_native_oktmo=f['oktmo'],fias_level=f['fias_level_dadata'],latitude=f['latitude_dadata'],longitude=f['longitude_dadata'])
 if str(p) not in books:books[str(p)]=xlrd.open_workbook(str(p))
 sheet=books[str(p)].sheet_by_name(sid.rsplit(':',2)[1]);n=int(sid.rsplit(':',1)[1]);vs=sheet.row_values(n-1);label=next((str(v).strip() for v in vs if isinstance(v,str) and norm(v).endswith(norm(r.settlement_name))),None);assert label and nprefix.search(label),(sid,label,r.settlement_type);assert any(str(v).strip() in {str(int(r.population)),str(float(r.population))} for v in vs)
 return dict(source_record_id=sid,row=n,label=label,population=int(r.population),source_file=str(p),sheet=sheet.name)
def distance(a,b):
 x,y,z,w=map(math.radians,[*a,*b]);h=math.sin((z-x)/2)**2+math.cos(x)*math.cos(z)*math.sin((w-y)/2)**2;return 6371.0088*2*math.asin(min(1,math.sqrt(h)))
for case in samples.to_dict('records'):
 sid=case['native2010_source_record_id'];idx=ledger.index[ledger.native2010_source_record_id.eq(sid)][0];remaining=json.loads(ledger.loc[idx,'holds_json']);errors=json.loads(ledger.loc[idx,'errors_json']);claim=claims[claims.native2010_source_record_id.eq(sid)].iloc[0];rivals=json.loads(literal[(literal.target2010.eq(sid))&literal.kind.eq('allregional_crossclass_literalname_rivals')].iloc[0].witness_json);source_pairs=[]
 for year,col,target,colsid in [(2002,'old_native_two_sided_source_bracket_json',case['native2002_source_record_id'],'anchor_native2002_source_record_id'),(2021,'current_native_two_sided_source_bracket_json',case['native2021_source_record_id'],'native_current_source_record_id')]:
  pairs=json.loads(claim[col]);pairs=[p for p in pairs if p[0]==target]
  if not pairs:continue
  selected=min(pairs,key=lambda p:(int(p[4])-int(p[3]),json.dumps(p,sort_keys=True)));left,right=selected[1],selected[2];lo,hi=int(left[colsid].rsplit(':',1)[1]),int(right[colsid].rsplit(':',1)[1]);t=int(target.rsplit(':',1)[1]);valid=lo<t<hi
  witnesses=[]
  for anchor in [left,right]:
   for key in ['anchor_native2002_source_record_id','native_source_record_id','native_current_source_record_id']:
    leaf=rawrow(anchor[key]);assert norm(anchor['name']) in norm(leaf['label']);witnesses.append(leaf)
   a10=int(anchor['native_source_record_id'].rsplit(':',1)[1]);a02=by.loc[anchor['anchor_native2002_source_record_id']];a21=by.loc[anchor['native_current_source_record_id']]
   assert norm(a02.settlement_name)==norm(a21.settlement_name);assert norm(a02.district_raw)==norm(case['old_county_raw']) and norm(a21.district_raw)==norm(case['current_county_raw'])
  competing=[v for v in rivals if v['year']==year and not v['selected'] and v['same_old_county'] and lo<int(v['source_record_id'].rsplit(':',1)[1])<hi]
  valid=valid and not competing;source_pairs.append(dict(year=year,valid=valid));checks.append(dict(target2010=sid,year=year,own_native_target=target,left_native_source_id=left[colsid],right_native_source_id=right[colsid],ownrow_strictly_inside=lo<t<hi,compatible_crossclass_competitors_inside_json=json.dumps(competing,ensure_ascii=False),actual_reopened_anchor_leaves_json=json.dumps(witnesses,ensure_ascii=False),verified=valid))
 if len(source_pairs)==2 and all(p['valid'] for p in source_pairs):
  remaining=[v for v in remaining if v not in ['samecounty literalname rival needs grain/type exclusion','independent rawneighbour countybinding unresolved']]
 point=json.loads(case['source_positive_point_origin_json']);r21=rawrow(case['native2021_source_record_id']);origin=Path(point['point_origin_file']);point_status=ledger.loc[idx,'point_origin_check']
 if 'wikidata' in point['point_origin_kind']:
  q=point['coordinate_source_record_id'];ownclaims=[]
  with gzip.open(origin,'rt') as h:
   for n,line in enumerate(h,1):
    p=json.loads(line)
    if p.get('item','').endswith('/'+q):ownclaims.append(dict(raw_line=n,property=p['property'].rsplit('/',1)[-1],value=p['value']))
  codes=[p['value'] for p in ownclaims if p['property']=='P764'];types=[p['value'].rsplit('/',1)[-1] for p in ownclaims if p['property']=='P31'];coords=[p['value'] for p in ownclaims if p['property']=='P625'];coordinate_match=any(abs(float(re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',v).group(1))-float(point['longitude']))<1e-7 and abs(float(re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',v).group(2))-float(point['latitude']))<1e-7 for v in coords)
  code_match=str(r21['raw_native_oktmo']) in codes;physical=any(q in {'Q5084','Q532','Q192287'} for q in types);valid=coordinate_match and code_match and physical;pointchecks.append(dict(target2010=sid,qid=q,raw_source_path=str(origin),raw_source_sha256=sha(origin),native_current_ownoktmo=r21['raw_native_oktmo'],exact_ownP764_binding=code_match,P31_physical_types_json=json.dumps(types),literal_P625_coordinates_match=coordinate_match,all_own_claim_rows_json=json.dumps(ownclaims,ensure_ascii=False),verified=valid))
  if valid:remaining=[v for v in remaining if v!='external pointorigin requires literalownbinding inspection'];point_status='independent rawP764 exactownNPcode+physicalP31+rawP625 verified'
  else:errors.append('externalowncode/type/point rawbinding fails')
 # Reopen actual current raw coordinates for every same-name current rival; report geographic competitors instead of equating modern/historical measurements.
 for v in rivals:
  if v['year']!=2021 or v['selected']:continue
  rv=rawrow(v['source_record_id']);d=None
  if rv['latitude'] is not None and rv['longitude'] is not None:d=distance((float(point['latitude']),float(point['longitude'])),(float(rv['latitude']),float(rv['longitude'])))
  georivals.append(dict(target2010=sid,rival_source_record_id=v['source_record_id'],rival_name=rv['label'],rival_type=v['type'],raw_county=rv['county'],raw_native_owncode=rv['raw_native_oktmo'],raw_fias_level=rv['fias_level'],distance_km=d,same_county=v['same_old_county'],nearby_5km=d is not None and d<=5))
 ledger.loc[idx,'holds_json']=json.dumps(sorted(set(remaining)));ledger.loc[idx,'errors_json']=json.dumps(sorted(set(errors)));ledger.loc[idx,'classification']='error' if errors else 'hold' if remaining else 'pass';ledger.loc[idx,'point_origin_check']=point_status
ledger.to_csv(Z/'independent_sample_ledger.csv',index=False);pd.DataFrame(checks).to_csv(Z/'independently_reopened_bilateral_native_source_intervals.csv',index=False);pd.DataFrame(pointchecks).to_csv(Z/'independently_bound_raw_ownNP_Wikidata_points.csv',index=False);pd.DataFrame(georivals).to_csv(Z/'actual_current_geographic_namesake_rivals.csv',index=False);(Z/'independent_raw_input_pins.json').write_text(json.dumps(pins,indent=2)+'\n');print(ledger[['name','region','classification','errors_json','holds_json']].to_string(index=False))

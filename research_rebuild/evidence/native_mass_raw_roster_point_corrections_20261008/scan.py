import sys,json,re,hashlib,gzip,math
from pathlib import Path
import pandas as pd,duckdb
Z=Path(__file__).resolve().parent;E=Z.parent;sys.path.insert(0,str(E.parent/'mass_linkage'))
from working_state_20261007 import load
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
s=load(55);C=duckdb.connect();RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');raw=C.execute('select row_number() over() as raw_row_1based,object_level,object_name,oktmo,region,mun_upper,mun_lower,population,settlement_dadata,settlement_type_full_dadata,oktmo_dadata,fias_id_dadata,fias_level_dadata,latitude_dadata,longitude_dadata from read_parquet(?)',[str(RAW)]).fetchdf();exclude_path=E/'native_singleton_rural_mass_20261008/accepted_native_source_binding_witnesses.csv.gz';excluded=set(pd.read_csv(exclude_path,keep_default_na=False).native2021_source_record_id);current=s.obs[s.obs.census_year.eq(2021)];current=current[current.source_record_id.isin(s.point_rows)&current.source_record_id.isin(excluded)];pins={str(RAW):sha(RAW),str(exclude_path):sha(exclude_path)}
code=lambda v:str(int(float(v))) if pd.notna(v) and str(v).strip() not in ['','None','nan'] else ''
raw['code']=raw.oktmo.map(code);raw['pcode']=raw.oktmo_dadata.map(code);raw['typedNP']=raw.object_level.eq('Населенный пункт')&raw.object_name.str.match(r'^\s*(?:село|деревня|пос[её]лок|хутор|станица|аул|город|станция)\s+',case=False,na=False);raw['observedNP']=raw.typedNP&raw.population.notna()&~raw.object_name.str.contains(r'\(часть\s*\d+\)',case=False,regex=True,na=False);native_index={}
for row in raw[raw.observedNP].itertuples():
 if row.code:native_index.setdefault(row.code,[]).append(row)
byrow=raw.set_index('raw_row_1based');records=[];holds=[];eligible=[];wk_files={};point_ledgers={};counts={};pointall=dict(s.point_rows)
for r in current.itertuples():
 p=pointall[r.source_record_id];n=int(r.source_record_id.rsplit(':',1)[1]);own=byrow.loc[n];origin=Path(str(p.get('point_origin_file','')));kind=str(p.get('point_origin_kind',''));family='dadata_current_raw' if origin==RAW else 'wikidata' if 'wikidata' in kind.lower() else 'other';counts[family]=counts.get(family,0)+1
 if family=='wikidata':wk_files.setdefault(str(origin),[]).append((r,p,own));continue
 if family!='dadata_current_raw':continue
 if not own.observedNP or own.fias_level_dadata!='6' or not pd.notna(own.latitude_dadata) or not pd.notna(own.longitude_dadata):holds.append(dict(source_record_id=r.source_record_id,reason='origin actualcurrent raw ownNP/FIAS/point fields not narrow checked subset'));continue
 if abs(float(p['latitude'])-float(own.latitude_dadata))>1e-8 or abs(float(p['longitude'])-float(own.longitude_dadata))>1e-8:holds.append(dict(source_record_id=r.source_record_id,reason='acceptedpoint coordinates differ currentraw dadata fields'));continue
 provider=own.pcode;owncode=own.code
 eligible.append(dict(source_record_id=r.source_record_id,family=family,own_code=owncode,provider_code=provider,full3=s.years[s.uf.find(r.source_record_id)]=={2002,2010,2021}))
 if not provider or provider==owncode or provider not in native_index:continue
 for other in native_index[provider]:
  if other.raw_row_1based==n or other.code==owncode:continue
  sameFIAS=pd.notna(own.fias_id_dadata) and str(own.fias_id_dadata)==str(other.fias_id_dadata);samepoint=pd.notna(other.latitude_dadata) and abs(float(p['latitude'])-float(other.latitude_dadata))<1e-8 and abs(float(p['longitude'])-float(other.longitude_dadata))<1e-8
  # Exact other-code + observed sameyear NP. Point-sharing strengthens evidence; no blanket mismatch interpretation.
  if not sameFIAS and not samepoint:holds.append(dict(source_record_id=r.source_record_id,reason='provider code matches anotherpublishedNP but no actualsharedFIAS/point; date/bridge review required'));continue
  records.append(dict(source_record_id=r.source_record_id,name=r.settlement_name,region=r.region_norm,type=r.settlement_type,population=int(r.population),native_own_code=owncode,raw_own_row=n,raw_own_label=own.object_name,raw_own_population=int(own.population),raw_own_county=own.mun_upper,raw_own_subordinate_context=own.mun_lower,provider_own_code=provider,other_raw_source_record_id='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(other.raw_row_1based),other_raw_row=other.raw_row_1based,other_code=other.code,other_label=other.object_name,other_population=int(other.population),other_county=other.mun_upper,other_subordinate_context=other.mun_lower,same_FIAS=sameFIAS,same_coordinates=samepoint,latitude=p['latitude'],longitude=p['longitude'],point_origin_file=str(origin),point_origin_sha256=p.get('point_origin_sha256',''),point_origin_locator=p.get('point_origin_locator',''),point_origin_kind=kind,point_ledger_path=p.get('point_ledger_path',''),full3=s.years[s.uf.find(r.source_record_id)]=={2002,2010,2021},risk='explicit observed otherownNP provider code/sharedFIASpoint conflict; requires ownpoint rejection/recovery; populationidentity not rejected'))
# Cached raw Wikidata property index per cited originalfile, read once. Only exact actual point+physicaltype+otherownNP code, missing/deprecatedcode alone withheld.
for filename,uses in wk_files.items():
 path=Path(filename)
 if not path.is_file():counts['wikidata_missing_origin_file']=counts.get('wikidata_missing_origin_file',0)+len(uses);continue
 qids={str(p.get('coordinate_source_record_id','')) for _,p,_ in uses};properties={q:[] for q in qids};pins[str(path)]=sha(path)
 try:
  with gzip.open(path,'rt') as f:
   for n,line in enumerate(f,1):
    v=json.loads(line);q=v.get('item','').rsplit('/',1)[-1]
    if q in properties:properties[q].append(dict(raw_line=n,property=v.get('property','').rsplit('/',1)[-1],value=v.get('value','')))
 except (OSError,ValueError):counts['wikidata_origin_not_supported_by_truthy_gzip_parser']=counts.get('wikidata_origin_not_supported_by_truthy_gzip_parser',0)+len(uses);continue
 for r,p,own in uses:
  q=str(p.get('coordinate_source_record_id',''));props=properties.get(q,[]);codes={code(x['value']) for x in props if x['property']=='P764'};types={x['value'].rsplit('/',1)[-1] for x in props if x['property']=='P31'};coordinates=[]
  for x in props:
   if x['property']=='P625':
    m=re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',x['value'])
    if m:coordinates.append((float(m.group(2)),float(m.group(1))))
  coordmatch=any(abs(a-float(p['latitude']))<1e-7 and abs(b-float(p['longitude']))<1e-7 for a,b in coordinates);physical=bool(types&{'Q5084','Q532','Q192287','Q515','Q3957','Q486972'})
  if not codes or not coordmatch or not physical:continue
  eligible.append(dict(source_record_id=r.source_record_id,family='wikidata_raw_P764_P31_P625',own_code=own.code,provider_code=';'.join(sorted(codes)),full3=s.years[s.uf.find(r.source_record_id)]=={2002,2010,2021}))
  if own.code in codes:continue
  for candidate in codes:
   if not candidate or candidate not in native_index:continue
   for other in native_index[candidate]:
    if other.code==own.code:continue
    records.append(dict(source_record_id=r.source_record_id,name=r.settlement_name,region=r.region_norm,type=r.settlement_type,population=int(r.population),native_own_code=own.code,raw_own_row=int(r.source_record_id.rsplit(':',1)[1]),raw_own_label=own.object_name,raw_own_population=int(own.population),raw_own_county=own.mun_upper,raw_own_subordinate_context=own.mun_lower,provider_own_code=candidate,other_raw_source_record_id='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(other.raw_row_1based),other_raw_row=other.raw_row_1based,other_code=other.code,other_label=other.object_name,other_population=int(other.population),other_county=other.mun_upper,other_subordinate_context=other.mun_lower,same_FIAS=False,same_coordinates=False,latitude=p['latitude'],longitude=p['longitude'],point_origin_file=filename,point_origin_sha256=p.get('point_origin_sha256',''),point_origin_locator=p.get('point_origin_locator',''),point_origin_kind=p.get('point_origin_kind',''),point_ledger_path=p.get('point_ledger_path',''),full3=s.years[s.uf.find(r.source_record_id)]=={2002,2010,2021},wikidata_qid=q,physical_P31=';'.join(sorted(types)),rank_date_status='truthy currentcached P764; no datedcode reconstruction',risk='raw ownpointentity P764 names anotherpublishedNP; requires identifierdate/ownpoint resolution before harddownclassifying'))
frame=pd.DataFrame(records);frame.to_csv(Z/'explicit_other_published_NP_point_binding_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(holds).to_csv(Z/'withheld_nonexact_origin_or_date_bridge_cases.csv.gz',index=False,compression={'method':'gzip','mtime':0});eligible_frame=pd.DataFrame(eligible);eligible_frame['code_availability']=eligible_frame.provider_code.map(lambda v:'present' if v else 'empty');eligible_frame['native_code_in_actual_provider_codes']=eligible_frame.apply(lambda r:r.own_code in r.provider_code.split(';') if r.provider_code else False,axis=1);code_summary=eligible_frame.groupby(['family','code_availability','native_code_in_actual_provider_codes']).agg(current_carriers=('source_record_id','size')).reset_index();code_summary.to_csv(Z/'checked_origin_code_availability_summary.csv',index=False)
risks=[];s.obs['root']=s.obs.source_record_id.map(s.uf.find);groups={root:g for root,g in s.obs[s.obs.root.isin({s.uf.find(sid) for sid in frame.source_record_id})].groupby('root')}
for sid,g in frame.groupby('source_record_id') if len(frame) else []:
 own=s.by_id.loc[sid];component=groups[s.uf.find(sid)];risk=dict(source_record_id=sid,name=own.settlement_name,region=own.region_norm,point_origin_kind=g.iloc[0].point_origin_kind,whole_current_population=int(own.population),full3=s.years[s.uf.find(sid)]=={2002,2010,2021},competing_observed_NP_rows=len(g))
 for year in [2002,2010,2021]:
  year_rows=component[component.census_year.eq(year)];risk['component_population_'+str(year)]=int(year_rows.population.sum()) if len(year_rows) else None
 risks.append(risk)
riskframe=pd.DataFrame(risks);riskframe.to_csv(Z/'gross_unique_carrier_population_risk.csv',index=False)
receipt=dict(status='bounded_source53_State55_fullraw_explicit_other_NP_code_point_diagnostic',current_accepted_point_carriers_scanned=len(current),checked_source53_current_ids=len(excluded),origin_family_counts=counts,origin_ownNP_fields_checked_carriers=len(eligible),explicit_code_available_carriers=int(eligible_frame.provider_code.ne('').sum()),eligible_origin_code_summary=code_summary.to_dict('records'),candidate_raw_otherNP_pairs=len(records),unique_risk_carriers=len(risks),gross_current_population_risk=sum(r['whole_current_population'] for r in risks),gross_full3_component_population_by_year={str(y):sum(r['component_population_'+str(y)] for r in risks if r['full3']) for y in [2002,2010,2021]},top5=sorted(risks,key=lambda x:x['whole_current_population'],reverse=True)[:5],limitations=['Only exact explicit provider/entity codes belonging to another actualpublishedsameyear NP are signalled. Blank/old/deprecated/mismatching codes alone do not qualify.','Dadata othercode+sharedFIAS/point is material binding conflict. Wikidata truthy currentcodes require separate datedidentifier review before final rejection.','Gross population risk is not unique lostcoverage: other accepted points/alternate owncoded origins may preserve histories.','Unseen or unsupported origin families are not validated; no populationaccuracy estimate.'],input_pins=pins,source_state_inputs={str(p):sha(p) for p in s.inputs},original_points_or_graph_mutated=False)
(Z/'diagnostic_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['current_accepted_point_carriers_scanned','origin_family_counts','explicit_code_available_carriers','unique_risk_carriers','gross_current_population_risk','gross_full3_component_population_by_year','top5']},ensure_ascii=False,indent=2))

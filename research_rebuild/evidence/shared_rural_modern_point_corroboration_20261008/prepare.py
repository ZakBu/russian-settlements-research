import json,gzip,re,sys,collections,zipfile
from pathlib import Path
import pandas as pd,duckdb
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');E=O.parent;B=E/'inherited_moderate_Geo_ownpoint_correction_20261008';FOL=B/'broader_cached_modern_point_followup';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
q=pd.read_csv(FOL/'unresolved_shared_rural_Geo_point_quarantine.csv.gz',keep_default_na=False);f=pd.read_csv(B/'candidate_moderate_histories.csv.gz',keep_default_na=False);f=f[f.source_record_id_2021.isin(q['case'])];assert len(f)==62;obs=pd.read_parquet(B/'frozen_moderate_observations.parquet').set_index('source_record_id');active=json.load(gzip.open(B/'frozen_active_point_uses.json.gz','rt'));RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');G=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');pins={str(p):sha(p) for p in [RAW,G,C,B/'candidate_moderate_histories.csv.gz',B/'frozen_moderate_observations.parquet',B/'frozen_active_point_uses.json.gz',FOL/'application_receipt.json',FOL/'unresolved_shared_rural_Geo_point_quarantine.csv.gz',O/'prepare.py']}
def digits(v):
 text=str(v).strip('\"')
 if text.endswith('.0'):text=text[:-2]
 return text if text.isdigit() else ''
def bare(v):return ' '.join(re.sub('[^а-яa-z0-9]+',' ',re.sub(r'^(?:город|село|деревня|пос[её]лок(?: городского типа| сельского типа| при станции| железнодорожной станции)?|хутор|станица|аул|станция|разъезд|слобода|рабочий поселок|пгт|починок|местечко|железнодорожная станция|железнодорожный разъезд|населенный пункт|поселение)\s+','',normalize(re.sub(r'\s*\([^)]*\)\s*$','',str(v))))).split())
raw=pd.read_parquet(RAW,columns=['object_level','object_name','region','mun_upper','mun_lower','oktmo','population','oktmo_dadata','okato_dadata','fias_id_dadata','latitude_dadata','longitude_dadata']);raw['rn']=range(1,len(raw)+1);raw['n']=raw.object_name.map(bare);raw['county']=raw.mun_upper.map(county_key);raw['own_code_norm']=raw.oktmo.map(digits);raw['provider_code_norm']=raw.oktmo_dadata.map(digits);NP=raw[raw.object_level.eq('Населенный пункт')];rows=raw.set_index('rn');cl=pd.read_parquet(C);cl['n']=cl.name.map(bare);clnp=cl[cl.is_settlement_raw.eq('t')];counties={a.historical_okato[:5]:county_key(a['name']) for _,a in cl.iterrows() if a.is_settlement_raw=='f' and len(a.historical_okato)==8 and a.historical_okato.endswith('000') and 'район' in normalize(a['name'])};clnp=clnp.copy();clnp['county']=clnp.historical_okato.str[:5].map(counties).fillna('')
ex=set();exfiles=[E/'native_mass_raw_roster_point_corrections_20261008/explicit_other_published_NP_point_binding_candidates.csv.gz',E/'baseline_fullraw_point_code_conflict_scan_20261008/explicit_other_published_NP_point_binding_candidates.csv.gz',E/'baseline_fullraw_point_code_conflict_scan_20261008/seven_full3_current_carrier_binding_conflicts.csv']
for p in exfiles:pins[str(p)]=sha(p);ex.update(pd.read_csv(p,keep_default_na=False).source_record_id)
GN=[];ADM={}
with zipfile.ZipFile(G) as zf:
 with zf.open('RU.txt') as stream:
  for ln,b in enumerate(stream,1):
   v=b.decode('utf8').rstrip('\n').split('\t')
   if len(v)<19:continue
   if v[6:8]==['A','ADM1']:ADM[v[10]]=v
   if v[6]=='P' and v[8]=='RU':GN.append((ln,v))
idx=collections.defaultdict(dict)
for ln,v in GN:
 for alias in set([v[1],v[2],*v[3].split(',')]):
  if re.search('[а-яА-ЯёЁ]',alias):idx[bare(alias)][v[0]]=(ln,v)
W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');pins[str(W)]=sha(W);con=duckdb.connect(config={'threads':1});con.register('targets',f[['source_record_id_2021']].rename(columns={'source_record_id_2021':'source_record_id'}));ww=con.execute('select w.* from read_parquet(?) w join targets t using(source_record_id)',[str(W)]).fetchdf();con.close();ownWiki={}
for a in ww.to_dict('records'):
 sid=a['source_record_id'];pp=active[sid];own=rows.loc[int(sid.rsplit(':',1)[1])]
 if not a['wikidata_truthy_exact_p764_match'] or a['entity_competition_across_tsv_or_truthy'] or digits(a['source_oktmo_exact_digits'])!=own.own_code_norm:continue
 if not any(bare(label)==bare(obs.loc[sid].settlement_name) for label in json.loads(a['wikidata_tsv_ru_labels_json'])):continue
 typ=json.loads(a['wikidata_truthy_p31_claims_json']);codes=json.loads(a['wikidata_truthy_exact_p764_claims_json']);coords=json.loads(a['wikidata_truthy_p625_claims_json']);xy={(v['latitude'],v['longitude']) for v in coords if v.get('wgs84_valid')}
 if not any(v['value_qid'] in {'Q2514025','Q7930989','Q20019082','Q15078955','Q532','Q486972','Q192287','Q515','Q3957','Q5084','Q2023000'} for v in typ) or len(xy)!=1 or next(iter(xy))!=(pp['latitude'],pp['longitude']):continue
 if 'wikidata_truthy_claims' not in str(pp.get('point_origin_file','')):continue
 ownWiki[sid]={'qid':a['wikidata_qid'],'P764':codes,'P31':typ,'P625':coords,'source_native_current_code':own.own_code_norm}
points=[];witness=[];holds=[];rivals=[];accepted=[]
for z in f.to_dict('records'):
 sid=z['source_record_id_2021'];ids=[z['source_record_id_'+str(y)] for y in [2002,2010,2021]];p=active[sid];own=rows.loc[int(sid.rsplit(':',1)[1])];names={bare(obs.loc[i].settlement_name) for i in ids};xy=(float(p['latitude']),float(p['longitude']));reason=''
 if set(ids)&ex:reason='Excluded entire known provider-code conflict component'
 elif own.object_level!='Населенный пункт' or bare(own.object_name)!=bare(obs.loc[sid].settlement_name) or not str(own.oktmo) or len(NP[NP.oktmo.eq(own.oktmo)])!=1:reason='Native own typed NP/name/code binding not unique'
 elif sid not in ownWiki and NP[NP.fias_id_dadata.eq(own.fias_id_dadata)&~NP.oktmo.eq(own.oktmo)].shape[0] and pd.notna(own.fias_id_dadata) and str(own.fias_id_dadata):reason='Actual other native NP shares own FIAS identifier'
 elif sid not in ownWiki and own.provider_code_norm!=own.own_code_norm and len(NP[NP.own_code_norm.eq(own.provider_code_norm)]):reason='Provider code positively belongs to another actual native NP'
 elif sid not in ownWiki and pd.notna(own.latitude_dadata) and pd.notna(own.longitude_dadata) and xy==(float(own.latitude_dadata),float(own.longitude_dadata)) and len(NP[NP.latitude_dadata.eq(xy[0])&NP.longitude_dadata.eq(xy[1])&~NP.oktmo.eq(own.oktmo)]):reason='Active current raw coordinate shared by another native NP'
 candidates={}
 for name in names:candidates.update(idx[name])
 regional=[];near=[]
 for gid,(ln,v) in candidates.items():
  a=ADM.get(v[10]);regionnames={normalize(t) for t in [a[1],a[2],*a[3].split(',')]} if a else set()
  if normalize(own.region) not in regionnames:continue
  d=distance_km(xy,(float(v[4]),float(v[5])));regional.append({'geonameid':gid,'feature_code':v[7],'source_line_1based':ln,'current_distance_km':d,'literal_row':v,'literal_ADM1':a});
  if d<=5:near.append(regional[-1])
 rivals.append({'current_native_source_record_id':sid,'all_accepted_component_literal_names_json':json.dumps(sorted(names),ensure_ascii=False),'all_regional_GN_physical_namesakes_including_PPLQ_json':json.dumps(regional,ensure_ascii=False),'all_raw_current_region_name_NP_rivals_json':NP[NP.region.eq(own.region)&NP.n.isin(names)].to_json(orient='records',force_ascii=False)})
 if not reason and len(near)!=1:reason='Not exactly one regional literal-name physical GN candidate within5km'
 if not reason and near[0]['feature_code'] not in ['PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLC']:reason='Sole nearby GN record has retired/section/other grain, retained as real alternative'
 # Whole literal historical code/name/county roster; no arbitrary county flattening.
 for old in ids[:2]:
  pool=clnp[clnp.n.eq(bare(obs.loc[old].settlement_name))];printed=county_key(obs.loc[old].district_raw);proper=pool[pool.county.eq(own.county)|pool.county.eq(printed)]
  if not reason and printed and own.county and printed!=own.county and not len(proper):reason='Historic printed county/current own context contradiction'
 if reason:holds.append({'current_native_source_record_id':sid,'name':obs.loc[sid].settlement_name,'reason':reason,'population_2010':z['population_2010'],'population_2021':z['population_2021'],'regional_GN_rivals':len(regional),'GN_candidates_within5km':len(near)});continue
 g=near[0];targets=q[q['case'].eq(sid)].target_source_record_id.tolist();accepted.append(z)
 for target in targets:
  pp={k:v for k,v in p.items() if k!='point_ledger_path'};pp.update(target_source_record_id=target,latitude=xy[0],longitude=xy[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule='Existing independently own native2021 typed NP/name/code/current parish with all provider-code/FIAS/coordinate contradictions excluded; sole raw physical GN Cyrillic component-name candidate within5km among all same-region physical rivals including PPLQ; correct ADM1; already accepted whole native3 identity supports retrospective modern representative reuse; GN official code and ADM2 not required or invented',point_use_inference='own_current_representative_point_reused_retrospectively_with_independent_nearby_GN_ownNP_corroboration',historical_census_coordinate_asserted=False,historical_boundary_comparability='UNKNOWN',corroborating_source_file=str(G),corroborating_source_sha256=pins[str(G)],corroborating_source_locator=f"RU.txt line1based={g['source_line_1based']};geonameid={g['geonameid']}",modern_GN_official_code_asserted=False,GN_admin2=g['literal_row'][11] or 'UNKNOWN',case=sid);points.append(pp)
 witness.append({'current_native_source_record_id':sid,'native_name':obs.loc[sid].settlement_name,'native_type':obs.loc[sid].settlement_type,'native_current_code':own.oktmo,'actual_raw_current_county':own.mun_upper,'actual_raw_current_parish':own.mun_lower,'current_latitude':xy[0],'current_longitude':xy[1],'corroborating_raw_GN_record_json':json.dumps(g,ensure_ascii=False),'all_regional_GN_same_name_physical_rivals':len(regional),'sole_GN_candidate_within5km':True,'old_quarantined_targets_recovered_json':json.dumps(targets),'own_independent_current_Wiki_source_witness_json':json.dumps(ownWiki.get(sid,{}),ensure_ascii=False),'existing_point_origin_file':p.get('point_origin_file',''),'existing_point_origin_sha256':p.get('point_origin_sha256',''),'existing_point_origin_locator':p.get('point_origin_locator',''),'provider_ID_binding_status':'own native code exact after typography-only integer representation normalization' if own.own_code_norm==own.provider_code_norm else 'UNKNOWN; no actual other native NP code conflict','historical_boundary_comparability':'UNKNOWN','population_2002':z['population_2002'],'population_2010':z['population_2010'],'population_2021':z['population_2021']})
 for file in [Path(p['point_origin_file'])]:pins[str(file)]=sha(file)
for fn,data,cols in [('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('current_ownpoint_GN_corroboration_witnesses.csv.gz',witness,['current_native_source_record_id']),('all_actual_GN_and_native_region_rivals.csv.gz',rivals,['current_native_source_record_id']),('holds.csv.gz',holds,['current_native_source_record_id','reason'])]:pd.DataFrame(data,columns=cols if not data else None).to_csv(O/fn,index=False,compression={'method':'gzip','mtime':0})
r={'status':'Bounded62 source corroboration candidates checked; accepted old-point recovery uses ready for root61 replay on inactive60 quarantine targets','baseline_composition':'frozen58 native identity/current ownpoints plus frozen60 disjoint quarantine84; no mutable report output or State reload','target_quarantined_histories':62,'accepted_histories':len(accepted),'accepted_point_uses':len(points),'gross_restored_native_population_by_year':{str(y):int(sum(z['population_'+str(y)] for z in accepted)) for y in [2002,2010,2021]},'holds_by_reason':dict(collections.Counter(z['reason'] for z in holds)),'input_pins':pins,'output_pins':{n:sha(O/n) for n in ['accepted_point_use_delta.csv.gz','current_ownpoint_GN_corroboration_witnesses.csv.gz','all_actual_GN_and_native_region_rivals.csv.gz','holds.csv.gz']},'new_identity_edges':0,'historical_counts_or_zeros_invented':False};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print({k:v for k,v in r.items() if k not in ['input_pins','output_pins']})

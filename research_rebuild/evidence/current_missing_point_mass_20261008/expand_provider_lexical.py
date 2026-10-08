from pathlib import Path
import sys,json,re,collections
import pandas as pd,duckdb
O=Path(__file__).parent;E=O.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');S=Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet');P=E/'temporal_residual_mass_20261008/SHARED_points_compact_stage61.parquet';F=O/'prioritized_unresolved.csv.gz'
f=pd.read_csv(F,keep_default_na=False);c=duckdb.connect();c.register('targets',f[['source_record_id']]);s=c.execute('select s.* from read_parquet(?) s join targets using(source_record_id)',[str(S)]).fetchdf().set_index('source_record_id');raw=c.execute("select row_number() over() rn,* exclude(\"Указавшие национальную принадлежность\") from read_parquet(?)",[str(RAW)]).fetchdf();raw=raw[['rn','object_level','object_name','oktmo','region','mun_upper','mun_lower','settlement_fias_id_dadata','settlement_with_type_dadata','settlement_type_full_dadata','settlement_dadata','fias_id_dadata','fias_level_dadata','okato_dadata','oktmo_dadata','qc_geo_dadata','latitude_dadata','longitude_dadata']].set_index('rn');a=c.execute('select * from read_parquet(?)',[str(P)]).fetchdf().set_index('source_record_id');c.close()
def code(v):
 v=str(v);v=v[:-2] if v.endswith('.0') else v
 return v.zfill(11) if v.isdigit() and len(v) in [10,11] else v
codes=collections.Counter(code(z.oktmo) for z in raw.itertuples() if z.object_level=='Населенный пункт');occupied=collections.defaultdict(set)
for sid,z in a.iterrows():
 if str(sid).startswith('2021:'):occupied[(float(z.latitude),float(z.longitude))].add(sid)
def bare(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',normalize(v).replace('_x000d_','')).split())
def lexical(v,rail=False):
 v=normalize(v).replace('_x000d_','');v=re.sub(r'\bим\.?\s+', 'имени ',v);v=re.sub(r'\bсвх\b','совхоза',v);v=re.sub(r'\b(?:n|№)\s*(\d)',r'номер \1',v);v=re.sub(r'ж\.?\s*[д/]\.?\s*', 'железнодорожная ',v);v=v.replace('ж/д','железнодорожная');v=re.sub(r'\bжелезнодорожн(?:ая|ой|ого)\b','железнодорожная',v)
 if rail:
  v=re.sub(r'^\s*(?:при\s+)?(?:железнодорожная\s+)?(?:станци[яи]|разъезда?|ст\.)\s+','',v);v=re.sub(r',?\s*железнодорожная\s+станция\s*$','',v)
 return bare(v)
def typekey(v):
 v=normalize(v)
 if v in ['сельский поселок','поселок сельского типа']:v='поселок'
 return v
rawsha=sha(RAW);points=[];ev=[];holds=[]
for z in f.to_dict('records'):
 sid=z['source_record_id']
 if sid not in s.index:continue
 r=s.loc[sid].to_dict();rawrow=raw.loc[int(sid.rsplit(':',1)[1])].to_dict();reason=[]
 if not bool(r['provider_point_available']) or not bool(r['provider_point_valid_wgs84']) or not bool(r['provider_point_in_coarse_russia_envelope']):continue
 if str(r['provider_fias_level'])!='6' or not bool(r['provider_general_and_settlement_fias_ids_same']) or r['provider_general_fias_duplicate_count']!=1 or r['provider_coordinate_duplicate_count']!=1:continue
 if code(rawrow['oktmo_dadata'])!=code(rawrow['oktmo']) or codes[code(rawrow['oktmo'])]!=1:continue
 if rawrow['object_level']!='Населенный пункт':continue
 st=typekey(z['settlement_type']);pt=typekey(r['provider_settlement_type_full']);rail=any(t in normalize(z['settlement_name']) for t in ['станци','ж.д','ж/д','ж/д ст.','разъезд']) or st=='железнодорожный объект'
 subtypephysical=(st==pt or st=='поселок' and pt in ['поселок и(при) станция(и)','поселок при железнодорожной станции','станция'] or st=='железнодорожный объект' and pt in ['железнодорожная станция','железнодорожный разъезд','станция','разъезд'])
 if not subtypephysical:reason.append('source_provider_physical_type_incompatible')
 if lexical(z['settlement_name'],rail)!=lexical(r['provider_settlement_name'],rail):reason.append('name_not_equal_under_closed_lexical_rules')
 xy=(float(rawrow['latitude_dadata']),float(rawrow['longitude_dadata']));far=[]
 if occupied[xy]-{sid}:reason.append('other_accepted_current_NP_exact_point_occupation')
 for target in str(z['component_source_ids']).split('|'):
  if target in a.index:
   pp=a.loc[target];d=distance_km(xy,(float(pp.latitude),float(pp.longitude)))
   if d>5:far.append({'source_record_id':target,'distance_km':d})
 if far:reason.append('accepted_component_point_over5km')
 if reason:holds.append({**z,'provider_name':r['provider_settlement_name'],'provider_type':pt,'reason':';'.join(reason)});continue
 cid=str(rawrow['fias_id_dadata']);origin=str(RAW);loc='parquet_1basedrow='+str(int(sid.rsplit(':',1)[1]))+';latitude_dadata;longitude_dadata;fias_id_dadata;oktmo_dadata'
 points.append({'target_source_record_id':sid,'latitude':xy[0],'longitude':xy[1],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':cid,'point_origin_file':origin,'point_origin_sha256':rawsha,'point_origin_locator':loc,'point_origin_kind':'owncoded_unique_level6_FIAS_physicalNP_provider_representative_point','coordinate_binding_rule':'Reopened raw native own physicalNP/source OKTMO and provider full own OKTMO; .0 numeric text and one leading zero only; unique source owncode, unique FIAS and own point globally; primary=settlement FIAS level6; exact name under closed abbreviations/railway classifier wrappers/Excel control-text removal; compatible physical subtype; no accepted component over5km or other current point occupation','point_use_inference':'current_own_physicalNP_representative_provider_point;provider_measurement_date_unknown','historical_census_coordinate_asserted':False,'external_provider_ID_binding_asserted':True,'native2021_own_oktmo':str(rawrow['oktmo'])})
 ev.append({**z,'provider_source_name':r['provider_settlement_name'],'provider_source_type':r['provider_settlement_type_full'],'source_name_lexical_key':lexical(z['settlement_name'],rail),'provider_name_lexical_key':lexical(r['provider_settlement_name'],rail),'railway_classifier_wrapper_rule_applied':rail,'raw_provider_own_NP_witness_json':json.dumps(rawrow,ensure_ascii=False,default=str),'provider_ID_and_point_claim_separately_checked':True,'provider_qc_geo3_locality_representative_accuracy_not_address':str(rawrow['qc_geo_dadata']) in ['3','3.0'],'point_origin_locator':loc})
for n,d in [('accepted_provider_lexical_point_use_delta',points),('accepted_provider_lexical_source_bound_evidence',ev),('provider_lexical_holds',holds)]:pd.DataFrame(d).to_csv(O/(n+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
r={'baseline_stage':61,'accepted_current_ownpoints':len(points),'known_population2021':sum(float(z['population']) for z in ev if str(z['population'])),'full_native_source_code_binding':True,'lexical_positive_owncode_pool_held':len(holds),'raw_quality3_use_condition':'ownlocality representative point; no parcel/address or census-date accuracy asserted','input_pins':{str(x):sha(x) for x in [RAW,S,P,F,O/'expand_provider_lexical.py']}};(O/'provider_lexical_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False))

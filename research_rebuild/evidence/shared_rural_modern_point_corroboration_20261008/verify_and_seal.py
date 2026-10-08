import json,gzip,re,zipfile,collections
from pathlib import Path
import pandas as pd,duckdb
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');B=O.parent/'inherited_moderate_Geo_ownpoint_correction_20261008';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');G=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');import sys;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,distance_km,normalize
import ast
for node in ast.parse((O/'prepare.py').read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in ['digits','bare']:exec(compile(ast.Module(body=[node],type_ignores=[]),str(O/'prepare.py'),'exec'))
r=json.loads((O/'application_receipt.json').read_text());w=pd.read_csv(O/'current_ownpoint_GN_corroboration_witnesses.csv.gz',keep_default_na=False);points=pd.read_csv(O/'accepted_point_use_delta.csv.gz',keep_default_na=False);active=json.load(gzip.open(B/'frozen_active_point_uses.json.gz','rt'));raw=pd.read_parquet(RAW,columns=['object_level','object_name','region','mun_upper','mun_lower','oktmo','population','oktmo_dadata','fias_id_dadata','latitude_dadata','longitude_dadata']);raw['rn']=range(1,len(raw)+1);raw['own_code_norm']=raw.oktmo.map(digits);raw['provider_code_norm']=raw.oktmo_dadata.map(digits);NP=raw[raw.object_level.eq('Населенный пункт')];need=collections.defaultdict(dict);gn={};ownorigins=[]
for z in w.to_dict('records'):
 sid=z['current_native_source_record_id'];p=active[sid];own=raw.iloc[int(sid.rsplit(':',1)[1])-1];assert bare(own.object_name)==bare(z['native_name']) and own.own_code_norm==digits(z['native_current_code']);assert own.mun_upper==z['actual_raw_current_county'] and own.mun_lower==z['actual_raw_current_parish'];assert (z['current_latitude'],z['current_longitude'])==(p['latitude'],p['longitude']);g=json.loads(z['corroborating_raw_GN_record_json']);assert distance_km((float(g['literal_row'][4]),float(g['literal_row'][5])),(p['latitude'],p['longitude']))<=5;gn[g['geonameid']]=g
 q=json.loads(z['own_independent_current_Wiki_source_witness_json'])
 if q:
  for prop in ['P764','P31','P625']:
   for v in q[prop]:need[v['source_file']][int(v['line_number'])]=(q['qid'],prop,v['value_raw'])
 if Path(p['point_origin_file'])==RAW:assert (own.latitude_dadata,own.longitude_dadata)==(p['latitude'],p['longitude'])
 else:
  match=re.search(r'(?:line=|line1based=)(\d+)',str(p['point_origin_locator']));assert match,sid;fn=Path(p['point_origin_file']).name;need[fn][int(match[1])]=('', 'P625',(p['latitude'],p['longitude']))
 ownorigins.append({'current_native_source_record_id':sid,'raw_native_row1based':int(own.rn),'native_own_code':own.oktmo,'typed_raw_NP_label':own.object_name,'own_county':own.mun_upper,'own_parish':own.mun_lower,'active_point_origin_file':p['point_origin_file'],'active_latitude':p['latitude'],'active_longitude':p['longitude'],'raw_GN_ID':g['geonameid'],'GN_current_distance_km':g['current_distance_km'],'native_population_unchanged':own.population})
# Reopen all active own current point rows and coded Wiki property rows literally.
claims=0
for fn,rows in need.items():
 file=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;r['input_pins'][str(file)]=sha(file);seen=set()
 with gzip.open(file,'rt') as stream:
  for ln,line in enumerate(stream,1):
   if ln in rows:
    qid,prop,value=rows[ln];a=json.loads(line);assert a['property'].rsplit('/',1)[-1]==prop
    if qid:assert a['item'].rsplit('/',1)[-1]==qid
    if isinstance(value,tuple):m=re.fullmatch(r'POINT\(([-\d.]+) ([-\d.]+)\)',a['value']);assert m and (float(m[2]),float(m[1]))==value
    else:assert str(a['value'])==str(value)
    seen.add(ln);claims+=1
   if ln>=max(rows):break
 assert seen==set(rows)
seen=set();adm={}
with zipfile.ZipFile(G) as zf:
 with zf.open('RU.txt') as stream:
  for ln,b in enumerate(stream,1):
   a=b.decode('utf8').rstrip('\n').split('\t')
   if len(a)<19:continue
   if a[6:8]==['A','ADM1']:adm[a[10]]=a
   if a[0] in gn:assert a==gn[a[0]]['literal_row'] and ln==gn[a[0]]['source_line_1based'];seen.add(a[0])
assert seen==set(gn)
for g in gn.values():assert adm[g['literal_row'][10]]==g['literal_ADM1']
pd.DataFrame(ownorigins).to_csv(O/'literal_current_point_and_GN_checks.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# Four raw provider binding conflicts are documented separately from actual active Wiki point claims.
obs=pd.read_parquet(B/'frozen_moderate_observations.parquet').set_index('source_record_id');four={'Ильинка','Вогулка','Артемьево','Великий Двор'};cohort=pd.read_csv(B/'candidate_moderate_histories.csv.gz',keep_default_na=False);cohort=cohort[cohort.settlement_name_2021.isin(four)&cohort.source_record_id_2021.isin(set(pd.read_csv(B/'broader_cached_modern_point_followup/unresolved_shared_rural_Geo_point_quarantine.csv.gz')['case']))];conflicts=[];qneed=collections.defaultdict(dict);W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');con=duckdb.connect();con.register('t',cohort[['source_record_id_2021']].rename(columns={'source_record_id_2021':'source_record_id'}));wf=con.execute('select w.* from read_parquet(?) w join t using(source_record_id)',[str(W)]).fetchdf();con.close()
for a in wf.to_dict('records'):
 sid=a['source_record_id'];own=raw.iloc[int(sid.rsplit(':',1)[1])-1];p=active[sid];others=NP[NP.fias_id_dadata.eq(own.fias_id_dadata)&~NP.own_code_norm.eq(own.own_code_norm)];provider=NP[NP.own_code_norm.eq(own.provider_code_norm)];assert a['wikidata_truthy_exact_p764_match'] and not a['entity_competition_across_tsv_or_truthy'];coords=json.loads(a['wikidata_truthy_p625_claims_json']);assert {(g['latitude'],g['longitude']) for g in coords if g.get('wgs84_valid')}=={(p['latitude'],p['longitude'])}
 for prop,key in [('P625','wikidata_truthy_p625_claims_json'),('P764','wikidata_truthy_exact_p764_claims_json'),('P31','wikidata_truthy_p31_claims_json')]:
  for v in json.loads(a[key]):qneed[v['source_file']][int(v['line_number'])]=(a['wikidata_qid'],prop,v['value_raw'])
 conflicts.append({'current_native_source_record_id':sid,'own_native_label':own.object_name,'own_native_code':own.oktmo,'raw_provider_code':own.oktmo_dadata,'provider_code_normalized':own.provider_code_norm,'raw_shared_FIAS_id':own.fias_id_dadata,'actual_other_FIAS_NP_rows_json':others.to_json(orient='records',force_ascii=False),'actual_provider_code_NP_rows_json':provider.to_json(orient='records',force_ascii=False),'raw_Dadata_latitude':own.latitude_dadata,'raw_Dadata_longitude':own.longitude_dadata,'active_current_Wiki_latitude':p['latitude'],'active_current_Wiki_longitude':p['longitude'],'active_current_Wiki_own_entity':a['wikidata_qid'],'active_own_native_code_exact_P764':True,'raw_Dadata_ID_binding_ambiguous_or_wrong':True,'active_current_point_is_raw_Dadata_claim':False,'current_point_claim_rejected':False,'reason':'Active current coded Wiki physical NP point is independent of ambiguous/wrong raw Dadata identifier binding; no point rejection from provider ID ambiguity alone','old_point_recovery_admitted':sid in set(w.current_native_source_record_id),'coordinate_accuracy':'UNKNOWN; own locality representative point, not census-day measurement'})
for fn,rows in qneed.items():
 file=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;r['input_pins'][str(file)]=sha(file);seen=set()
 with gzip.open(file,'rt') as stream:
  for ln,line in enumerate(stream,1):
   if ln in rows:
    qid,prop,value=rows[ln];a=json.loads(line);assert a['item'].rsplit('/',1)[-1]==qid and a['property'].rsplit('/',1)[-1]==prop and str(a['value'])==str(value);seen.add(ln)
   if ln>=max(rows):break
 assert seen==set(rows)
pd.DataFrame(conflicts).to_csv(O/'four_raw_provider_FIAS_conflicts_vs_independent_active_Wiki_points.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(columns=['target_source_record_id','rejection_status','old_latitude','old_longitude','origin_ledger','origin_ledger_sha256']).to_csv(O/'current_point_use_rejections.csv.gz',index=False,compression={'method':'gzip','mtime':0})
q=pd.read_csv(B/'broader_cached_modern_point_followup/unresolved_shared_rural_Geo_point_quarantine.csv.gz',keep_default_na=False);assert set(points.target_source_record_id)<=set(q.target_source_record_id);assert points.target_source_record_id.is_unique and len(points)==59 and len(w)==45
r.update(status='FROZEN constructive own-current-point/GN corroboration batch literal source checks PASS; root61 prefix60 replay required',source_literal_verification_passed=True,existing_current_raw_point_rows_reopened=38,existing_current_Wiki_point_rows_reopened=7,raw_GN_physical_entities_reopened=len(gn),literal_Wiki_claim_rows_checked=claims,current_point_rejections=0,four_raw_provider_FIAS_ID_conflicts_separate_from_independent_active_Wiki_point_correctness=True,old_point_target_status='All59 accepted uses are a subset of known inactive State60 quarantine84; no unnecessary old-claim rejection',population_quality_names_types_codes_and_accepted_identity_unchanged=True,no_State_reload=True)
for p in [O/'literal_current_point_and_GN_checks.csv.gz',O/'four_raw_provider_FIAS_conflicts_vs_independent_active_Wiki_points.csv.gz',O/'current_point_use_rejections.csv.gz',O/'verify_and_seal.py']:r['output_pins'][p.name]=sha(p)
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print({k:v for k,v in r.items() if k not in ['input_pins','output_pins']})

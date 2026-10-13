import sys,json,importlib.util,re
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;s=load(37);r=json.loads((O/'application_receipt.json').read_text());assert s.metrics()==r['before'];f=pd.read_csv(O/'accepted_source_bindings.csv.gz',dtype=str,keep_default_na=False);out=[];bad=[]
for z in f.to_dict('records'):
 n=s.by_id.loc[z['current_source_record_id']];b=s.by_id.loc[z['native2010_source_record_id']];a=s.by_id.loc[z['old_source_record_id']];dp=s.point_rows[n.source_record_id];names={n.name_norm,b.name_norm,a.name_norm}
 for item in json.loads(z['raw_own_entity_bindings']):
  e=item['raw_own_entity'];names.update(normalize(v['value']) for v in e.get('aliases',{}).get('ru',[]));names.add(normalize(e.get('labels',{}).get('ru',{}).get('value','')))
 for _,p in s.obs[s.obs.census_year.eq(2021)&s.obs.region_norm.eq(n.region_norm)&s.obs.name_norm.isin(names)].iterrows():
  pp=s.point_rows.get(p.source_record_id);dist=distance_km((dp['latitude'],dp['longitude']),(pp['latitude'],pp['longitude'])) if pp else None;sharedcodes={str(v) for v in [n.okato,n.oktmo] if v}&{str(v) for v in [p.okato,p.oktmo] if v};sameq=bool(pp and str(dp.get('coordinate_source_record_id','')).startswith('Q') and pp.get('coordinate_source_record_id')==dp.get('coordinate_source_record_id'))
  out.append({'target_current_source_record_id':n.source_record_id,'competitor_current_source_record_id':p.source_record_id,'native_name':p.settlement_name,'native_type':p.settlement_type,'native_county':p.district_raw,'native_okato':p.okato,'native_oktmo':p.oktmo,'native_population':p.population,'component_years':str(sorted(s.years[s.uf.find(p.source_record_id)])),'admitted_own_point_json':json.dumps(pp,ensure_ascii=False) if pp else '', 'distance_to_target_current_km':dist,'within5km':dist is not None and dist<=5,'shares_own_native_code':bool(sharedcodes),'same_own_QID_point':sameq,'target_record':p.source_record_id==n.source_record_id})
  exclusive_oktmo=bool(n.oktmo and p.oktmo and str(n.oktmo)!=str(p.oktmo) and n.type_norm!=p.type_norm and sharedcodes=={str(n.okato)} and any(str(v.get('mainsnak',{}).get('datavalue',{}).get('value',''))==str(n.oktmo) for item in json.loads(z['raw_own_entity_bindings']) if item['independently_admitted_nativecode_or_point_QID'] for v in item['raw_own_entity'].get('claims',{}).get('P764',[]) if v.get('rank')!='deprecated'))
  out[-1]['shared_code_disambiguation']='Shared current publisher OKATO is ambiguous; distinct native OKTMO exactly matches independently bound ownQID P764 and distinct printed NP class' if exclusive_oktmo else ''
  if p.source_record_id!=n.source_record_id and (sameq or (sharedcodes and not exclusive_oktmo)):bad.append({'target':n.source_record_id,'competitor':p.source_record_id,'sharedcodes':list(sharedcodes),'sameq':sameq})
assert not bad, 'Unexplained current own-code/QID namesake collisions: '+json.dumps(bad,ensure_ascii=False)
pd.DataFrame(out).to_csv(O/'all_current_named_competitors.csv.gz',index=False,compression='gzip');r['output_pins']['all_current_named_competitors.csv.gz']=sha(O/'all_current_named_competitors.csv.gz');r['all_current_namesakes_checked_before_component_filter']=True;r['current_namesake_rows_checked']=len(out);(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));sp=importlib.util.spec_from_file_location('app',O/'apply.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);m.apply(s);print('Actual37 source/output pins, all current namesakes and exact weak/finite frozen CSV replay passed; current rows',len(out))

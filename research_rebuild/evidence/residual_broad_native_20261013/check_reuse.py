from pathlib import Path
import pandas as pd,json,hashlib
O=Path(__file__).parent;B=Path('/workspace/scratch/residual-20261013/base15');p=pd.read_parquet(B/'applied_point_snapshot.parquet',columns=['target_source_record_id','latitude','longitude']);p['lat']=pd.to_numeric(p.latitude,errors='coerce').round(7);p['lon']=pd.to_numeric(p.longitude,errors='coerce').round(7);f=pd.read_parquet(B/'applied_state_observations.parquet',columns=['source_record_id','root','census_year','settlement_name','settlement_type','district_raw','population']);d=f.set_index('source_record_id').to_dict('index');pg={k:g.target_source_record_id.tolist() for k,g in p.groupby(['lat','lon'])};pp=p.drop_duplicates('target_source_record_id').set_index('target_source_record_id').to_dict('index');r=pd.read_csv(O/'reviews.csv').fillna('');out=[]
for v in r.to_dict('records'):
 ids=json.loads(v['component_source_ids_json']);matches=[]
 for sid in ids:
  if sid not in pp:continue
  z=pp[sid];others=pg.get((z['lat'],z['lon']),[])
  for other in others:
   if other in ids:continue
   rec=d.get(other,{});matches.append({'target_source_record_id':sid,'other_source_record_id':other,**rec,'latitude':z['lat'],'longitude':z['lon'],'same_year':rec.get('census_year')==d[sid]['census_year']})
 out.append({'case':v['case'],'outside_component_exact_point_reuses_json':json.dumps(matches,ensure_ascii=False),'outside_component_exact_point_reuses_count':len(matches)})
pd.DataFrame(out).to_csv(O/'global_exact_point_reuses.csv',index=False)
m=json.loads((O/'manifest.json').read_text());m['output_hashes'].update({str(O/'global_exact_point_reuses.csv'):hashlib.sha256((O/'global_exact_point_reuses.csv').read_bytes()).hexdigest()});(O/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));print(pd.DataFrame(out)[['case','outside_component_exact_point_reuses_count']].to_string(index=False))

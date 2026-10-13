import sys,re,json
from pathlib import Path
import pandas as pd,xlrd,duckdb
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent;CACHE=Path('/dev/shm/settlements-stage71-20261009')
def nk(v):
 v=normalize(v);v=re.sub(r'["«»]','',v);v=re.sub(r'\bим\.','имени',v);v=v.replace('совхоза','совхоз').replace('отделения','отделение');v=re.sub(r'\bжелезнодорожной станции\b|\bстанция\b|\bстанции\b',' ',v);v=re.sub(r'(?<=\d)-(го|е|я|ой|й)\b','',v);v=re.sub(r'\b(первая|первое|первый)\b','1',v);v=re.sub(r'\b(вторая|второе|второй)\b','2',v);return ' '.join(v.split())
def main():
 obs=pd.read_parquet(CACHE/'applied_state_observations.parquet');pts=pd.read_parquet(CACHE/'applied_point_snapshot.parquet').set_index('target_source_record_id',drop=False);d=pd.read_csv(OUT/'dispositions.csv');reg=set(d.region);o=obs[obs.region_norm.isin(reg)].copy();o['n']=o.settlement_name.map(nk);o['county']=o.district_raw.map(county_key);by=obs.set_index('source_record_id');roots=obs.set_index('source_record_id').root.to_dict();mem=obs.groupby('root').source_record_id.agg(set).to_dict();edges=pd.read_csv(OUT/'accepted_identity_edge_delta.csv').to_dict('records');points=pd.read_csv(OUT/'accepted_point_use_delta.csv').to_dict('records');manifest=json.loads((OUT/'manifest.json').read_text());inputs=manifest['inputs_sha256'];witness=[];books={};targetids=set(d.source_record_id);held=[]
 def merge(a,b):
  aa,bb=roots[a],roots[b]
  if aa==bb:return True
  if set(by.loc[list(mem[aa]),'census_year'])&set(by.loc[list(mem[bb]),'census_year']):return False
  mem[aa]|=mem.pop(bb)
  for s in mem[aa]:roots[s]=aa
  return True
 for e in edges:
  if not merge(e['from_source_record_id'],e['to_source_record_id']):raise ValueError('previous edges conflict')
 own={sid:row for sid,row in pts.iterrows()}
 for p in points:own[p['target_source_record_id']]=p
 def rawcheck(sid):
  r=by.loc[sid];path=Path('/workspace/settlements-raw')/r.source_file
  if not path.exists():return False
  if str(path) not in inputs:inputs[str(path)]=sha(path)
  if path.suffix=='.parquet':
   no=int(sid.rsplit(':',1)[-1]);c=duckdb.connect(config={'threads':1});vals=c.execute('select object_name,oktmo,mun_upper,population from read_parquet(?) limit 1 offset '+str(no-1),[str(path)]).fetchdf().iloc[0].to_dict();c.close();valid=normalize(r.settlement_name) in normalize(vals['object_name']) and float(vals['population'])==float(r.population);loc='row_1based='+str(no)
  else:
   if path not in books:books[path]=xlrd.open_workbook(path,on_demand=True)
   sheet=sid.rsplit(':',2)[-2];no=int(sid.rsplit(':',1)[-1]);vals=books[path].sheet_by_name(sheet).row_values(no-1);valid=any(normalize(r.settlement_name) in normalize(v) for v in vals if isinstance(v,str)) and any(str(v).strip().replace(' ','').replace('\xa0','').replace('.','',1).isdigit() and float(str(v).strip().replace(' ','').replace('\xa0',''))==float(r.population) for v in vals);loc=sheet+':row_1based='+str(no)
  witness.append(dict(source_record_id=sid,source_file=str(path),source_sha256=inputs[str(path)],source_locator=loc,name_count_verified=valid,raw_values=json.dumps(vals,ensure_ascii=False)));return valid
 def addpoint(sid,donor):
  if sid in own:return
  dp=own[donor];ledger=Path(dp.get('point_ledger_path',''))
  if donor not in pts.index:return # new direct independently sourced points retained on target; no opaque chain provenance
  ledger=CACHE/'applied_point_snapshot.parquet'
  p=dict(target_source_record_id=sid,latitude=float(dp['latitude']),longitude=float(dp['longitude']),coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=donor,coordinate_origin_ledger=str(ledger),coordinate_origin_ledger_sha256=inputs[str(ledger)],coordinate_origin_ledger_locator='target_source_record_id='+donor,admission_rule='own_representative_continuity_unique_all_type_native_region_name_or_transparent_station_descriptor',direct_historical_coordinate_measurement=False,native_code_binding_asserted=False,boundary_comparability_asserted=False,point_temporal_interpretation='Retrospective representative continuity; no census date measurement')
  points.append(p);own[sid]=p
 for key,g in o.groupby(['region_norm','n']):
  if not targetids.intersection(g.source_record_id) or g.census_year.duplicated().any():continue
  if not all(g.is_additive_settlement_record.fillna(False)) or any(re.search(r'\(часть|сельсовет|сельское поселение|администраци',normalize(v)) for v in g.settlement_name):continue
  if not set(g.type_norm).issubset({'село','поселок','станция','деревня','хутор','станица','аул','поселок при станции','железнодорожная станция'}):continue
  # This rule is for unavailable county context; contradictory printed county keys stay held.
  counties=set(g.loc[g.county.ne(''),'county'])
  if len(counties)>1:continue
  donors=[s for s in g.source_record_id if s in pts.index]
  if not donors:continue
  donor=max(donors,key=lambda s:int(by.loc[s,'census_year']));dp=own[donor];xy=(float(dp['latitude']),float(dp['longitude']))
  if any(distance_km(xy,(float(own[s]['latitude']),float(own[s]['longitude'])))>5 for s in g.source_record_id if s in own):continue
  for sid in g.source_record_id:
   if not rawcheck(sid):continue
   if roots[sid]!=roots[donor]:
    if not merge(sid,donor):held.append(dict(source_record_id=sid,reason='same_year_component_conflict'));continue
    edges.append(dict(from_source_record_id=sid,to_source_record_id=donor,relation='same_place',decision_status='checked_rule_accepted',admission_rule='unique_all_type_literal_native_region_name_with_transparent_descriptors_and_accepted_own_point',name_norm=key[1],region_norm=key[0],all_type_native_per_year_name_alternatives=1,county_context_unavailable_allowed=True,source_context_witness_file=str(OUT/'regional_native_source_witnesses.csv.gz'),population_boundary_comparability_asserted=False,legal_type_change_date_asserted=False))
   addpoint(sid,donor)
 changed={p['target_source_record_id'] for p in points}|{e['from_source_record_id'] for e in edges}|{e['to_source_record_id'] for e in edges}
 for i,z in d.iterrows():
  sid=z.source_record_id;d.loc[i,'decision']='accepted_delta' if sid in changed else 'held';d.loc[i,'reason']='accepted_own_point_or_source_verified_native_identity' if sid in changed else ('typed_literal_part_no_whole_NP_ownpoint_projection' if '(часть' in normalize(z['name']) else 'unresolved_source_identity_or_ownpoint_requires_further_source');d.loc[i,'has_ownpoint_after']=sid in own;d.loc[i,'component_years_after']=','.join(map(str,sorted(set(by.loc[list(mem[roots[sid]]),'census_year']))))
 pd.DataFrame(edges).to_csv(OUT/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(OUT/'accepted_point_use_delta.csv',index=False);d.to_csv(OUT/'dispositions.csv',index=False);pd.DataFrame(witness).to_csv(OUT/'regional_native_source_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(held,columns=['source_record_id','reason']).to_csv(OUT/'regional_rule_holds.csv',index=False)
 manifest.update(accepted_identity_edges=len(edges),accepted_point_uses=len(points),changed_residual_rows=int(d.decision.eq('accepted_delta').sum()),inputs_sha256=inputs,outputs_sha256={f.name:sha(f) for f in OUT.iterdir() if f.suffix in ['.csv','.gz']});(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:manifest[k] for k in ['accepted_identity_edges','accepted_point_uses','changed_residual_rows']}))
if __name__=='__main__':main()

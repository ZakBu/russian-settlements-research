from pathlib import Path
import sys,json,hashlib
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize
s=load(20);p=pd.read_csv(O/'candidate_point_uses.csv').fillna('');a=pd.read_csv(O/'candidate_qualified_physical_observations.csv').fillna('');inv=pd.read_csv(O/'inventory.csv').fillna('');binding=pd.read_csv(O/'native_and_own_article_binding_checks.csv').fillna('');native=[];cache={};inputs=json.loads((O/'source_manifest.json').read_text())
for i,r in a.iterrows():
 if not r.source_record_id:continue
 b=s.by_id.loc[r.source_record_id];assert b.population==r.population_source_value and b.population_value_quality==r.population_quality
 path=Path(r.source_path)
 if not path.exists():path=R/b.source_file;a.at[i,'source_path']=str(path)
 if not path.exists():
  a.at[i,'original_native_source_path_unavailable']=str(path);path=Path(s.inputs[0]);a.at[i,'source_path']=str(path);a.at[i,'source_locator']='selected frozen source_record_id='+r.source_record_id;a.at[i,'source_reuse_provenance_status']='existing_accepted_native_observation_reused_from_pinned_selected; original_asset_not_present'
 h=sha(path);a.at[i,'source_sha256']=h;inputs[str(path)]=h
 if int(r.year)==2021:continue
 if path.suffix.lower() not in ('.xls','.xlsx'):continue
 sh,row=r.source_record_id.rsplit(':',2)[-2:];row=int(row);sh=0 if sh=='0' else sh;key=(str(path),sh)
 if key not in cache:cache[key]=pd.read_excel(path,sheet_name=sh,header=None)
 raw=cache[key].iloc[row-1];text=' | '.join(str(v) for v in raw if pd.notna(v));number=pd.to_numeric(raw.astype(str).str.replace(' ','',regex=False),errors='coerce');nameok=normalize(b.settlement_name) in normalize(text);assert nameok
 native.append({'sid':r.source_record_id,'qid':r.trajectory_id,'year':int(r.year),'population_selected':float(b.population),'population_quality':b.population_value_quality,'own_name_in_native_row':nameok,'count_in_native_row_matches':bool(number.eq(b.population).any()),'raw_row_excerpt':text[:600],'source_file':str(path),'source_sha256':h,'source_locator':str(sh)+'!row='+str(row)})
a.to_csv(O/'candidate_qualified_physical_observations.csv',index=False);pd.DataFrame(native).to_csv(O/'historic_native_row_checks.csv',index=False)
# Expose same-name/county alternatives. Unique own code disambiguates; otherwise native geographic/admin evidence remains review condition.
for i,r in binding.iterrows():
 b=s.by_id.loc[r.sid];same=s.obs[(s.obs.census_year==2021)&s.obs.region_norm.eq(b.region_norm)&s.obs.name_norm.eq(b.name_norm)&s.obs.district_raw.eq(b.district_raw)]
 binding.at[i,'same_name_current_county_candidates']=len(same);binding.at[i,'same_name_current_county_source_ids_json']=json.dumps(same.source_record_id.tolist());binding.at[i,'same_name_disambiguation_status']='own_code_exact' if r.own_code_exact else ('unique_exact_name_current_county' if len(same)==1 else 'requires_named_historical_subdivision_or_own_native_geographic_row_binding')
binding.to_csv(O/'native_and_own_article_binding_checks.csv',index=False)
largest=set(inv.nlargest(5,'population2021').sid);fixed=set(inv.assign(k=inv.qid.map(lambda q:hashlib.sha256(('fixed15-followup20261007'+q).encode()).hexdigest())).sort_values('k').head(15).sid);sample=binding[binding.sid.isin(largest|fixed)].copy();sample['sample']=sample.sid.map(lambda sid:'largest5' if sid in largest else 'fixed15');sample.to_csv(O/'fixed15_and_largest5_source_checks.csv',index=False)
credit={sid for sid in s.point_rows if s.years[s.uf.find(sid)]=={2002,2010,2021}}
for sub in ['working_full_chain_20261007/qualified_scope_source_id_credit_union.csv','complete_numbered_partition_batch_20261007/accepted_exclusive_member_projection.csv']+[sub+'/accepted_constituent_credit_union.csv' for sub in ['named_urban_merger_application_20261007','next_named_urban_merger_application_20261007','further_urban_merger_application_20261007']]+[sub+'/accepted_qualified_physical_observations.csv' for sub in ['recreated_named_locality_event_application_20261007','current_unpointed_own_wiki_mass_application_20261007','wikidata_actual_full3_mass_application_20261007']]:
 pp=R/'research_rebuild/evidence'/sub
 if not pp.exists():continue
 inputs[str(pp)]=sha(pp);f=pd.read_csv(pp,dtype=str).fillna('')
 for c in f:
  if 'source_record_id'in c:credit.update(f[c])
net=[]
for y in [2002,2010,2021]:
 d=a[a.year==y];ids=set(d.source_record_id)-{''}-credit;net.append({'year':y,'candidate_new_native_selected_ids':len(ids),'candidate_native_selected_population_net':float(s.by_id.loc[list(ids),'population'].sum()) if ids else 0,'secondary_nonadditive_population_no_selected_ID_credit':float(d[d.nonadditive_observation.astype(str).str.lower().eq('true')].population_source_value.sum()),'admitted_gain':0})
pd.DataFrame(net).to_csv(O/'unique_source_id_net_potential.csv',index=False);(O/'source_manifest.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2));rc=json.loads((O/'receipt.json').read_text());rc.update({'baseline_ordinary_stage20':s.metrics(),'historical_native_rows_directly_checked':len(native),'historical_native_count_mismatches_preserved':sum(not r['count_in_native_row_matches'] for r in native),'conditional_native_net':net,'same_name_current_county_ambiguous_candidates':int(binding.same_name_current_county_candidates.gt(1).sum()),'own_article_fixed15_largest5_checked_once':len(sample),'output_bytes':sum(p.stat().st_size for p in O.iterdir() if p.is_file())});(O/'receipt.json').write_text(json.dumps(rc,indent=2,ensure_ascii=False));print(json.dumps(rc,ensure_ascii=False))

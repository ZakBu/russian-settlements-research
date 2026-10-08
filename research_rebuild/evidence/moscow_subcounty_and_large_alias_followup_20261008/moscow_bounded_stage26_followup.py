import sys,json
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(26);d=pd.read_csv(O/'moscow_all_endpoint_current_component_membership_stage25.csv',dtype={'historical_own_okato':str,'current_okato':str});ctx=pd.read_csv('/workspace/settlements-work/secondary_2010_county_context_batch_20261007/all_selected_competitor_county_context.csv.gz',dtype=str).set_index('source_record_id');out=[];future=[]
for r in d.to_dict('records'):
 a=r['old_source_record_id'];b=r['current_source_record_id'];ar=s.uf.find(a);br=s.uf.find(b)
 if ar==br:status='Already source-backed joined in frozen26; no duplicate edges'
 elif s.by_id.loc[b].region_norm!='московская':status='Hard wrong region'
 elif s.years[ar]&s.years[br]:status='Hard actual same-year component collision'
 elif int(r['historical_distinct_owncodes_sharing_raw_point'])>1:status='Historical raw point shared across distinct own locality codes; physical historical binding unresolved'
 else:
  oldcounty=county_key(s.by_id.loc[a].district_raw);newcounty=county_key(s.by_id.loc[b].district_raw)
  neutral=(oldcounty==newcounty or newcounty==oldcounty+'ск' or newcounty==oldcounty+'ский' or oldcounty==newcounty+'ский' or (oldcounty,newcounty) in [('ступинский','ступино'),('коломенский','коломна'),('волоколамский','волоколамск'),('серпуховский','серпухов'),('солнечногорский','солнечногорск')])
  status='Eligible independently own-code-bound native point and neutral geographic county' if neutral else 'Different actual geographic county stem; no transfer or direct own-identity proof'
 r.update(stage26_status=status,old_component_years=json.dumps(sorted(s.years[ar])),current_component_years=json.dumps(sorted(s.years[br])));out.append(r)
 if (ar==br or status.startswith('Eligible')) and 2010 not in (s.years[ar]|s.years[br]):
  old=s.by_id.loc[a];pool=s.obs[s.obs.census_year.eq(2010)&s.obs.region_norm.eq('московская')&s.obs.settlement_name.map(normalize).eq(normalize(old.settlement_name))]
  for _,peer in pool.iterrows():
   sid=peer.source_record_id;c=ctx.loc[sid].to_dict() if sid in ctx.index else {};targetcounty=county_key(old.district_raw);actualcounty=county_key(peer.district_raw) or c.get('inferred_county_key','');actualcounty='' if pd.isna(actualcounty) else actualcounty
   future.append({'old2002_source_record_id':a,'current_source_record_id':b,'candidate_2010_source_record_id':sid,'name':peer.settlement_name,'population_2010':peer.population,'type_2002':old.settlement_type,'type_2010':peer.settlement_type,'historical_printed_county':old.district_raw,'known2010_county':actualcounty,'county_match':targetcounty==actualcounty,'candidate_2010_component_years':json.dumps(sorted(s.years[s.uf.find(sid)])),'context_proof_json':json.dumps(c,ensure_ascii=False),'candidate_status':'Future native source witness required; no identity or point mutation'})
pd.DataFrame(out).to_csv(O/'moscow_48_endpoint_resolution_frozen26.csv',index=False);pd.DataFrame(future).to_csv(O/'moscow_five_joined_future2010_native_options.csv',index=False);receipt={'baseline':26,'bounded_existing_endpoint_options':len(out),'distinct_native_old_ids':d.old_source_record_id.nunique(),'original47_distinct_old_population_no_credit':int(d.drop_duplicates('old_source_record_id').old_population.sum()),'endpoint_option_status_counts':pd.Series([r['stage26_status'] for r in out]).value_counts().to_dict(),'future2010_source_options':len(future),'new_edges':0,'new_points':0,'actual_full3_population_gain':0,'source_binding_rule':'462→464 classifier version mismatch is not veto; real shared coordinates/different historical geographic county/sameyear conflicts retained','input_sha256':sha(O/'moscow_all_endpoint_current_component_membership_stage25.csv')};(O/'moscow_bounded_followup_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False));print(pd.DataFrame(future)[['name','population_2010','known2010_county','county_match','candidate_2010_component_years']].to_string(index=False) if future else '')

"""Candidate representative-point transfers within only forty already accepted full-three-year components."""
import sys,json,re,itertools
from pathlib import Path
from collections import Counter
import pandas as pd,duckdb,pyarrow.parquet as pq
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,E
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
from measure_event_aware_path_union_20261005 import SELECTED
OUT=Path(__file__).resolve().parent
INVENTORY=E/'working_full_chain_20261007/own_point_full3_components_missing_other_year_points.csv'
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
EVENT=E/'event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
EVENT_CODES=Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')
def all3(s,pointids):
 obs=s.obs;pointed=obs.source_record_id.isin(pointids);full=obs.source_record_id.map(lambda x:s.years[s.uf.find(x)]=={2002,2010,2021});g=obs.assign(own=pointed).groupby('root').own.all();scope=obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~(obs.census_year.eq(2021)&obs.region_norm.eq('крым'));covered=full&obs.root.map(g)&scope
 return {str(int(y)):{'covered_population':int(d.loc[covered.loc[d.index],'population'].sum()),'covered_rows':int(covered.loc[d.index].sum())} for y,d in obs[scope].groupby('census_year')}
def main():
 s=load(stage=10);strictbefore=s.metrics();ids=set(s.point_rows);before=all3(s,ids);inv=pd.read_csv(INVENTORY);roots=set(inv.source_record_id.map(s.uf.find));assert len(roots)==40
 EAO=Path('/workspace/settlements-raw/data/raw/2002/086_3c3b73a0d2_EvrejskajaAO.xls')
 inputs={str(p):sha(p) for p in s.inputs+[INVENTORY,RAW,EVENT,EVENT_CODES,EAO]}
 import xlrd
 es=xlrd.open_workbook(str(EAO),on_demand=True).sheet_by_name('Sheet1');lit=' | '.join(str(v) for v in es.row_values(0) if v!='');assert 'Еврейская АО' in lit
 pd.DataFrame([{'source_physical_path':str(EAO),'source_sha256':inputs[str(EAO)],'source_sheet':'Sheet1','physical_row_1based':1,'raw_literal':lit,'parser_fallback_region_norm':'086_3c3b73a0d2_evrejskajaao','effective_region_for_screening':'еврейская','source_field_overwritten':False}]).to_csv(OUT/'physical_region_context_resolution.csv',index=False)
 meta=pq.read_table(SELECTED,columns=['source_record_id','entity_grain_status','source_sheet','source_row','source_name_raw']).to_pandas().set_index('source_record_id')
 eventids=set(pd.read_csv(EVENT,dtype=str,usecols=['source_record_id']).source_record_id);codes=set()
 for r in json.loads(EVENT_CODES.read_text()):
  for k in ['from_settlement_id_legacy_candidate','to_settlement_id_legacy_candidate']:
   v=str(r.get(k) or '')
   if v.startswith(('RU-OKATO-','RU-OKTMO-')):codes.add(normalize(v.rsplit('-',1)[-1]))
 collision=Counter((int(s.by_id.loc[x,'census_year']),p['latitude'],p['longitude']) for x,p in s.point_rows.items());obs=s.obs[s.obs.root.isin(roots)].join(meta,on='source_record_id');rows=[];holds=[];checks=[];providers=[];pointproof=[];pairproof=[];ledgerhash={};c=duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
 cols=set(c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(RAW)]).fetchdf().column_name);fields=[k for k in ['object_level','object_name','settlement','mun_upper','region','settlement_dadata','settlement_type_full_dadata','fias_level_dadata','qc_geo_dadata','latitude_dadata','longitude_dadata','oktmo'] if k in cols]
 for root,g in obs.groupby('root',sort=True):
  assert len(g)==3 and set(g.census_year)=={2002,2010,2021};missing=[x for x in g.source_record_id if x not in ids];assert len(missing)==1
  accepted=[x for x in g.source_record_id if x in ids]
  for sid in accepted:
   pp=s.point_rows[sid];lp=Path(pp['point_ledger_path']);ledgerhash.setdefault(str(lp),sha(lp));pointproof.append(dict(component_root=root,settlement_name=g.iloc[0].settlement_name,ledger_sha256=ledgerhash[str(lp)],**pp))
  donor=max(accepted,key=lambda x:int(s.by_id.loc[x,'census_year']));p=s.point_rows[donor];coord=(p['latitude'],p['longitude']);name=g.iloc[0].settlement_name;reasons=[]
  counties={county_key(v) for v in g.district_raw if county_key(v)}
  if len(counties)>1:reasons.append('source_county_context_difference_unresolved')
  effective_regions=g.region_norm.map(normalize).replace({'086_3c3b73a0d2_evrejskajaao':'еврейская'})
  if len(set(effective_regions))!=1:reasons.append('source_region_difference')
  if len(set(g.settlement_name.map(normalize)))!=1:reasons.append('source_name_difference')
  current=g[g.census_year.eq(2021)].iloc[0];rn=int(float(current.source_row));raw=c.execute('SELECT '+','.join(fields)+' FROM read_parquet(?) LIMIT 1 OFFSET ?',[str(RAW),rn-1]).fetchdf().to_dict('records')[0]
  providers.append(dict(component_root=root,target_source_record_id=current.source_record_id,physical_source_path=str(RAW),physical_source_sha256=inputs[str(RAW)],physical_row_1based=rn,**raw))
  for r in g.itertuples():
   sid=r.source_record_id;pt=s.point_rows.get(sid);nat=None
   if not bool(r.is_additive_settlement_record) or re.search(r'часть|\b(?:район|муниципальн\w*|итого|всего)\b',normalize(r.settlement_name)) or re.search('aggregate|municipal|parent|unresolved|control_total',str(r.entity_grain_status),re.I):reasons.append('parts_admin_or_nonwhole_grain')
   if sid in eventids or any(normalize(getattr(r,k)) in codes for k in ['oktmo','okato']):reasons.append('known_event_member')
   if sid in s.conflicting_point_targets:reasons.append('conflicting_accepted_point_alternatives')
   if pt and collision[(int(r.census_year),pt['latitude'],pt['longitude'])]>1:reasons.append('shared_same_year_accepted_point')
   if pd.notna(r.latitude) and pd.notna(r.longitude) and (r.latitude,r.longitude)!=(0,0):
    nat=distance_km(coord,(r.latitude,r.longitude))
    if nat>5:reasons.append('native_coordinate_conflict_requires_provider_context_resolution')
   checks.append({'component_root':root,'settlement_name':name,'source_record_id':sid,'census_year':r.census_year,'settlement_type_raw':r.settlement_type,'printed_type_variant':len(set(g.settlement_type.map(normalize)))>1,'source_county_raw':r.district_raw,'county_comparison_key':county_key(r.district_raw),'entity_grain_status':r.entity_grain_status,'own_point_already_accepted':sid in ids,'native_latitude':r.latitude,'native_longitude':r.longitude,'native_distance_from_representative_km':nat,'source_file':r.source_file,'source_sha256':r.source_sha256,'source_locator':r.source_locator,'source_sheet':r.source_sheet,'source_row':r.source_row,'population':r.population})
  for a,b in itertools.combinations(accepted,2):
   ap,bp=s.point_rows[a],s.point_rows[b]
   dist=distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']));pairproof.append({'component_root':root,'settlement_name':name,'accepted_source_record_id_a':a,'accepted_source_record_id_b':b,'distance_km':dist,'over_5km':dist>5})
   if dist>5:reasons.append('accepted_component_points_over_5km')
  target=missing[0];tr=s.by_id.loc[target]
  if collision[(int(tr.census_year),*coord)]>0:reasons.append('proposed_same_year_point_collision')
  if reasons:
   holds.append({'component_root':root,'settlement_name':name,'target_source_record_id':target,'target_year':int(tr.census_year),'hold_reasons':';'.join(sorted(set(reasons))),'printed_type_change_is_not_hold':True,'own_provider_settlement_label':raw.get('settlement_dadata'),'own_provider_type':raw.get('settlement_type_full_dadata'),'own_provider_fias_level':raw.get('fias_level_dadata'),'own_provider_qc_geo':raw.get('qc_geo_dadata'),'provider_context_resolution':'No native claim discarded: exact label alone does not choose between conflicting representative coordinates; source context/donor coordinates require further review.'});continue
  ledger=Path(p['point_ledger_path']);ledgerhash.setdefault(str(ledger),sha(ledger));row={'target_source_record_id':target,'target_year':int(tr.census_year),'latitude':coord[0],'longitude':coord[1],'coordinate_source_record_id':donor,'coordinate_admission_status':'candidate_pending_independent_review','coordinate_origin_ledger':str(ledger),'coordinate_origin_ledger_sha256':ledgerhash[str(ledger)],'coordinate_origin_ledger_locator':'target_source_record_id='+donor,'coordinate_origin_kind':'accepted_same_place_spatial_continuity_inference','admission_rule':'existing_accepted_full3_component_missing_own_point_representative_transfer_allow_printed_type_variant_v1','direct_historical_coordinate_measurement':False,'provider_binding_asserted':False,'boundary_comparability_asserted':False,'legal_type_change_asserted':False,'printed_type_variant':len(set(g.settlement_type.map(normalize)))>1,'target_settlement_name_raw':tr.settlement_name,'target_settlement_type_raw':tr.settlement_type,'target_district_raw':tr.district_raw,'target_source_file':tr.source_file,'target_source_sha256':tr.source_sha256,'target_source_locator':tr.source_locator,'target_population':tr.population}
  for field in ['source','source_sha256','source_locator','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_admission_status']:row['donor_'+field]=p.get(field,'')
  rows.append(row);collision[(int(tr.census_year),*coord)]+=1
 c.close();after=all3(s,ids|{r['target_source_record_id'] for r in rows});strictafter=s.metrics(extra_point_ids=[r['target_source_record_id'] for r in rows])
 pd.DataFrame(pointproof).to_csv(OUT/'accepted_point_origin_proof.csv',index=False);pd.DataFrame(pairproof).to_csv(OUT/'accepted_anchor_pair_distances.csv',index=False)
 pd.DataFrame(rows,columns=list(rows[0]) if rows else ['target_source_record_id','coordinate_admission_status']).to_csv(OUT/'candidate_point_use_delta.csv',index=False);pd.DataFrame(holds).to_csv(OUT/'held_components.csv',index=False);pd.DataFrame(checks).to_csv(OUT/'component_source_checks.csv',index=False);pd.DataFrame(providers).to_csv(OUT/'own_provider_physical_rows.csv',index=False)
 receipt={'status':'candidate_only_no_admission','accepted_input_stage':10,'bounded_components':40,'new_edges':0,'candidate_point_uses':len(rows),'held_components':len(holds),'baseline_strict_own_point':strictbefore,'simulated_after_strict_own_point':strictafter,'baseline_all_three_own_points':before,'simulated_after_all_three_own_points':after,'all_three_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'all_three_row_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'own_point_strict_population_gain':{y:strictafter[y]['covered_population']-strictbefore[y]['covered_population'] for y in before},'source_inputs_sha256':inputs,'donor_ledger_sha256':ledgerhash,'source_population_values_modified':False,'native_coordinate_claims_discarded':False,'legal_type_changes_asserted':False,'outputs_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
 (OUT/'simulation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['candidate_point_uses','held_components','all_three_population_gain','all_three_row_gain','own_point_strict_population_gain']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

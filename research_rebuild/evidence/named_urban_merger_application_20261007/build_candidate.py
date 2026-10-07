from pathlib import Path
import sys,json,hashlib,csv,math
import pandas as pd
import duckdb
ROOT=Path('/workspace/russian-settlements-research'); E=ROOT/'research_rebuild/evidence'; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from measure_event_aware_path_union_20261005 import SELECTED

def sha(p): return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def norm(v):return str(v).lower().replace('ё','е').replace('ѐ','е')
def write(name,rows):
 with (OUT/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def clean(r):
 return {k:(None if pd.isna(v) else (v.item() if hasattr(v,'item') else v)) for k,v in r.items()}
s=load(stage=15); obs=s.obs; meta=duckdb.connect().execute('select source_record_id,source_sheet,source_row from read_parquet(?)',[str(SELECTED)]).fetchdf(); obs=obs.merge(meta,on='source_record_id',how='left'); legal=E/'complete_urban_merger_series_20261007/legal_followup'
pins={str(SELECTED):sha(SELECTED),str(PARTITION_MEMBERS):sha(PARTITION_MEMBERS)}
for p in s.inputs: pins[str(p)]=sha(p)
manifest=json.loads((legal/'retrieval_manifest.json').read_text()); pins[str(legal/'retrieval_manifest.json')]=sha(legal/'retrieval_manifest.json')
for r in manifest:
 p=ROOT/r['compressed_path'];assert sha(p)==r['compressed_sha256'];pins[str(p)]=sha(p)
acts={r['key']:r for r in manifest}
rosters={
'Podolsk_Klimovsk_Lvovskiy':{2002:['Подольск','Климовск','Львовский'],2010:['Подольск','Климовск','Львовский'],2021:['Подольск']},
'Balashikha_Zheleznodorozhny':{2002:['Балашиха','Железнодорожный','Никольско-Архангельский','Салтыковка','Никольско-Архангельское','Горбово','Никольско-Трубецкое','Пехра-Покровское','Лукино','Безменково','Новая','совхоза им. 1 Мая','Щитниково','Абрамцево','Купавна'],2010:['Балашиха','Железнодорожный'],2021:['Балашиха']},
'Korolev_Yubileiny':{2002:['Королёв','Юбилейный','Первомайский','Болшево','Текстильщик','Торфопредприятие'],2010:['Королёв','Юбилейный'],2021:['Королёв']}}
laws={'Podolsk_Klimovsk_Lvovskiy':['pod_klim_103_2015','pod_lvov_282_2015','pod_rural_283_2015'],'Balashikha_Zheleznodorozhny':['bal_128_2003','bal_180_2004','zhel_149_2004','bal_zhel_209_2014'],'Korolev_Yubileiny':['kor_76_2003','kor_272_2004','kor_yub_54_2014']}
clauses={'pod_klim_103_2015':'article 1 merges named Podolsk/Klimovsk administrative cities; settlement union corroborated by 282-PG','pod_lvov_282_2015':'single-settlement union Lvovskiy and Podolsk; Klimovsk separately named in 103/2015-OZ','pod_rural_283_2015':'rural settlements retain separate settlement identities; excluded from named urban union','bal_128_2003':'clause 1 merges nine named settlements; clause 3 refuses three, subsequently merged by 180-PG','bal_180_2004':'clauses 1-2 merge sovkhoza im.1 Maya, Shchitnikovo, Abramtsevo into single Balashikha','zhel_149_2004':'clauses 1-2 merge Kupavna with Zheleznodorozhny as single settlement','bal_zhel_209_2014':'article 1 unites named cities as Balashikha','kor_76_2003':'clauses 1-2 merge Pervomaysky, Tekstilshchik, Bolshevo subordinate to Korolev','kor_272_2004':'clauses 1-2 merge Torfopredpriyatie subordinate to Korolev into single settlement','kor_yub_54_2014':'article 1 unites named Korolev/Yubileiny cities'}
# Exact printed hierarchy is essential for homonym controls; raw Excel row numbering is 1 based.
rural=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls'); urban=Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')
rd=pd.read_excel(rural,header=None);ud=pd.read_excel(urban,header=None)
assert 'Королёв' in str(rd.iloc[12,1]) and 'Торфопредприятие' in str(rd.iloc[13,1]) and int(rd.iloc[13,2])==234
assert 'Королёв' in str(ud.iloc[1028,0]) and 'Первомайский' in str(ud.iloc[1032,0]) and int(ud.iloc[1032,1])==10047
witnesses=[{'source_file':str(rural),'source_file_sha256':sha(rural),'sheet':'Sheet1','hierarchy_row':13,'hierarchy_text':str(rd.iloc[12,1]),'child_row':14,'child_raw_text':str(rd.iloc[13,1]),'child_population':234,'excluded_homonym_row':4055}, {'source_file':str(urban),'source_file_sha256':sha(urban),'sheet':'0','hierarchy_row':1029,'hierarchy_text':str(ud.iloc[1028,0]),'child_row':1033,'child_raw_text':str(ud.iloc[1032,0]),'child_population':10047,'excluded_homonym_row':'rural Istra1880/Kolomna2421'}]
write('exact_source_hierarchy_witnesses.csv',witnesses)
const=[];series=[];points=[];edges=[]
for group,years in rosters.items():
 members={}
 for y,names in years.items():
  members[y]=[]
  for name in names:
   d=obs[(obs.census_year==y)&obs.region_norm.eq('московская') & obs.settlement_name.map(norm).eq(norm(name))]
   if name=='Железнодорожный':d=d[d.settlement_type.eq('город')]
   if name=='Торфопредприятие':d=d[d.source_record_id.eq('2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:14')]
   if name=='Первомайский':d=d[d.source_record_id.eq('2002:1_TOM_01_04.xls:0:1033')]
   if name in ['Горбово','Лукино','Безменково','Новая','Щитниково','Абрамцево','Никольско-Архангельское','Никольско-Трубецкое','Пехра-Покровское','совхоза им. 1 Мая']:d=d[d.district_raw.eq('Балашихинский район')]
   assert len(d)==1,(group,y,name,d.source_record_id.tolist())
   r=clean(d.iloc[0].to_dict());assert math.isfinite(float(r['population']));members[y].append(r)
 parent=members[2021][0];sid=parent['source_record_id'];assert sid in s.point_rows
 point=clean(s.point_rows[sid]);assert math.isfinite(float(point['latitude'])) and math.isfinite(float(point['longitude']))
 provenance=json.dumps(point,ensure_ascii=False); points.append({'group':group,'scope_point_role':'representative_scope','parent_source_record_id':sid,'verified_active_state':15,'latitude':point['latitude'],'longitude':point['longitude'],'point_provenance_json':provenance,'historical_constituent_own_point_asserted':False})
 for y,rows in members.items():
  ids=[r['source_record_id'] for r in rows];assert len(ids)==len(set(ids))
  nested=[]
  for r in rows:
   p=Path('/workspace/settlements-raw')/r['source_file']; pins[str(p)]=sha(p)
   rr={'group':group,'census_year':y,'source_record_id':r['source_record_id'],'settlement_name':r['settlement_name'],'settlement_type':r['settlement_type'],'district_raw':r['district_raw'],'population':int(r['population']),'source_population_unmodified':True,'source_file':r['source_file'],'source_file_sha256':sha(p),'source_row_locator':f"{r['source_sheet']}!row={r['source_row']}",'additive_only_within_complete_named_year_group':True,'exclusive_source_ID_credit':True,'separate_population_credit_in_addition_to_group':False,'own_native_point_available':r['source_record_id'] in s.point_rows,'ordinary_same_place_edge_created':False}
   const.append(rr);nested.append(rr)
  series.append({'group':group,'census_year':y,'observation_id':f'named_merger:{group}:{y}','population':sum(int(r['population']) for r in rows),'population_derivation':'direct_published_successor_city' if y==2021 else 'explicit_sum_complete_named_event_roster','constituent_count':len(rows),'source_record_ids_json':json.dumps(ids,ensure_ascii=False),'members_json':json.dumps(nested,ensure_ascii=False),'roster_complete':True,'identity_axis':'named_merger_event_lineage','ordinary_same_place':False,'boundary_comparability':'UNKNOWN','population_series_scope':'named_event_lineage_not_constant_modern_boundary_estimate','legal_basis_json':json.dumps([dict(acts[k],clause=clauses[k]) for k in laws[group]],ensure_ascii=False),'official_act_verified':False,'point_role':'representative_scope','representative_parent_source_record_id':sid,'latitude':point['latitude'],'longitude':point['longitude'],'point_provenance_json':provenance,'no_fake_2021_child_population':True,'candidate_only':True})
 for a,b in [(2002,2010),(2010,2021)]:edges.append({'group':group,'from_observation_id':f'named_merger:{group}:{a}','to_observation_id':f'named_merger:{group}:{b}','relation':'complete_named_merger_lineage','ordinary_same_place':False,'boundary_comparability':'UNKNOWN','candidate_only':True})
write('candidate_group_observations.csv',series);write('candidate_constituent_credit_union.csv',const);write('candidate_representative_scope_points.csv',points);write('candidate_event_edges.csv',edges)
# Finite ordinary complete components, plus all existing selected-source qualified credits and partitions.
roots={root for root,ys in s.years.items() if ys=={2002,2010,2021}}
for sid in obs.source_record_id:
 root=s.uf.find(sid)
 if root in roots and (sid not in s.point_rows or not math.isfinite(float(s.by_id.loc[sid,'population']))):roots.discard(root)
ordinary=obs[obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((obs.census_year==2021)&obs.region_norm.eq('крым'))]
base=set(ordinary.loc[ordinary.source_record_id.map(lambda x:s.uf.find(x) in roots),'source_record_id'])
q=E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv';pins[str(q)]=sha(q)
base|=set(pd.read_csv(q).source_record_id)|set(pd.read_csv(PARTITION_MEMBERS).source_record_id)
fed=E/'federal_territory_spatial_overlay_20261005/federal_territory_observations.csv'; pins[str(fed)]=sha(fed)
new=set(r['source_record_id'] for r in const);gain=[]
for r in const:r['already_credited_in_stage15_partitions_physical_union']=r['source_record_id'] in base
write('candidate_constituent_credit_union.csv',const)
federal_rows=pd.read_csv(fed)
federal_rows=federal_rows[federal_rows.territory_key.isin(['RU-FED-MOW','RU-FED-SPB'])]
assert len(federal_rows)==6 and federal_rows.population_source_record_id.nunique()==6
federal_by_year=federal_rows.groupby('census_year').territory_population.sum().to_dict()
for y in [2002,2010,2021]:
 d=obs[obs.census_year==y]; before=d[d.source_record_id.isin(base)]; added=d[d.source_record_id.isin(new-base)]
 gain.append({'census_year':y,'baseline_stage':15,'baseline_selected_source_ID_union_population':int(before.population.sum()),'named_group_total_population':sum(r['population'] for r in series if r['census_year']==y),'new_unique_source_IDs':len(added),'net_national_population_added':int(added.population.sum()),'net_source_IDs_json':json.dumps(added.source_record_id.tolist()),'after_selected_source_ID_union_population':int(before.population.sum()+added.population.sum()),'federal_territory_population_change':0,'baseline_plus_federal_population':int(before.population.sum())+int(federal_by_year[y]),'after_plus_federal_population':int(before.population.sum()+added.population.sum())+int(federal_by_year[y]),'source_ID_union_required':True})
write('net_source_ID_union_gain.csv',gain)
(OUT/'receipt.json').write_text(json.dumps({'status':'complete_named_merger_candidate_ready_for_root_admission','active_state':15,'groups':3,'observations':9,'constituent_credits':len(const),'point_uses':3,'event_edges':6,'net_gain':gain,'inputs_sha256':pins,'output_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')},'sources_unchanged':True,'canonical_graph_unchanged':True,'legal_mirrors_not_officially_authenticated':True,'boundary_comparability':'UNKNOWN'},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'series':[(r['group'],r['census_year'],r['population']) for r in series],'gain':gain},ensure_ascii=False))

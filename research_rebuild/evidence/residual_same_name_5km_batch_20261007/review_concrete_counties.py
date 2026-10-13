"""Bounded physical county/context review of the eleven original candidates; original packet unchanged."""
import sys,json
from pathlib import Path
import pandas as pd,xlrd
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT/'mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
s=load();d=pd.read_csv(OUT/'candidate_identity_edge_delta.csv',keep_default_na=False)
# All claims below are physical context evidence, not inferred original census district values.
contexts={
'Юбилейный':('2002 Гремячинск block rows6668–6671; 2010 identical four-row sequence rows7829–7832','no_contradiction_in_physical_context',''),
'Курилово':('2002 explicit Подольский район; 2021 explicit Солнечногорск','hold_known_county_contradiction','Подольский vs Солнечногорск; near accepted historical point can itself be a wrong namesake'),
'шоссейное':('2010 physical row339 Новомосковский сельский округ, under Гурьевский район; 2021 Черняховск','hold_known_county_contradiction','Гурьевский vs Черняховск'),
'Софийск':('2002 heading row10132 Верхнебуреинский район; 2010 declared Верхнебуреинский район','no_contradiction_in_physical_context',''),
'Горный':('2002 heading row9984 Кировский район; 2010 declared Кировский район','no_contradiction_in_physical_context',''),
'Федино':('2010 physical source neighbors Старниково12576/Татаринцево12577/Торопово12578 and Гжелка12581/Дубовая Роща12582 all accepted Раменский components','hold_known_county_contradiction','Раменский source block vs 2021 Солнечногорск'),
'Карижа':('2002 Трубицынский сельсовет heading1936; same exact sequence Величково/Дубровка/Игнатьевское/Карижа in 2010 rows13250–13253','no_contradiction_in_physical_context',''),
'Мостовка':('2002 physical heading35 подчинение пгт Кольцово / Октябрьский район Екатеринбурга; 2021 Верхняя Пышма','hold_known_county_contradiction','Кольцово/Екатеринбург vs Верхняя Пышма'),
'Юшково':('2010 accepted Савинский anchors Тепляки10881 before and Воскресенское10883 after; 2021 target Пучежский район','hold_known_county_contradiction','Савинский source2010 vs Пучежский source2021'),
'Каверино':('2002 Волоколамский район/Шестаковский сельский округ305; 2010 Вельяминово13391 before and Константиновское13394 after both accepted Ступино components','hold_known_county_contradiction','Волоколамский source2002 vs Ступинский source2010; 2010 own identifier binding does not rescue wrong point'),
'Таежный':('2002 explicit Шелеховский район; 2021 explicit Нижнеудинский район','hold_known_county_contradiction','Шелеховский vs Нижнеудинский'),
}
physical=[];books={};hashes={};obs=s.obs.copy();obs['root']=obs.source_record_id.map(s.uf.find);component={k:g for k,g in obs.groupby('root',sort=False)}
for r in d.to_dict('records'):
 for side in ['from','to']:
  path=Path('/workspace/settlements-raw')/r[side+'_source_file'];sheet=str(r[side+'_source_sheet']);n=int(float(r[side+'_source_row']))
  if not path.exists() or path.suffix!='.xls':continue
  if path not in books:books[path]=xlrd.open_workbook(str(path),on_demand=True);hashes[str(path)]=sha(path)
  b=books[path];sh=b.sheet_by_index(int(sheet)) if sheet.isdigit() else b.sheet_by_name(sheet)
  for i in range(max(0,n-150),n):
   literal=' | '.join(str(v) for v in sh.row_values(i) if v!='')
   if i>=n-4 or any(w in literal.lower() for w in ['район','сельсовет','сельский округ']):physical.append({'candidate_name':r['from_settlement_name'],'side':side,'source_physical_path':str(path),'source_sha256':hashes[str(path)],'sheet':sheet,'physical_row_1based':i+1,'raw_literal':literal,'interpretation':'preceding printed context; does not overwrite source district'})
anchors=[]
for name in ['Федино','Каверино','Юшково','Карижа']:
 r=d[d.from_settlement_name.eq(name)].iloc[0];side='to' if name in ['Каверино','Карижа'] else 'from';sid=r[side+'_source_record_id'];prefix=sid.rsplit(':',1)[0]+':';n=int(float(r[side+'_source_row']));pool=obs[obs.source_record_id.str.startswith(prefix)].copy();pool['row']=pool.source_record_id.str.rsplit(':',n=1).str[-1].astype(int);pool=pool[pool.row.between(n-20,n+20)]
 for rr in pool.itertuples():
  if rr.source_record_id==sid:continue
  comp=component[s.uf.find(rr.source_record_id)];cur=comp[comp.census_year.eq(2021)]
  if len(cur)!=1 or rr.source_record_id not in s.point_rows:continue
  cr=cur.iloc[0];anchors.append({'candidate_name':name,'target_source_record_id':sid,'anchor_source_record_id':rr.source_record_id,'anchor_physical_row_1based':rr.row,'anchor_source_name':rr.settlement_name,'anchor_source_population':rr.population,'current_accepted_member_id':cr.source_record_id,'current_name':cr.settlement_name,'current_county_raw':cr.district_raw,'anchor_source_sha256':rr.source_sha256,'anchor_current_source_sha256':cr.source_sha256,'same_place_component_already_accepted':True})
import openpyxl
kal=Path('/workspace/settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx');kh=sha(kal);hashes[str(kal)]=kh;kb=openpyxl.load_workbook(kal,read_only=True,data_only=True);ks=kb['4']
for row in ks.iter_rows(min_row=239,max_row=340):
 if row[0].row in [239,243,339,340]:physical.append({'candidate_name':'шоссейное','side':'from','source_physical_path':str(kal),'source_sha256':kh,'sheet':'4','physical_row_1based':row[0].row,'raw_literal':' | '.join(str(c.value) for c in row if c.value is not None),'interpretation':'printed county/selsoviet context; does not overwrite original source district'})
pd.DataFrame(physical).to_csv(OUT/'root_review_physical_county_context.csv',index=False);pd.DataFrame(anchors).to_csv(OUT/'root_review_accepted_context_anchors.csv',index=False)
recs=[]
for r in d.to_dict('records'):
 name=r['from_settlement_name'];ev,status,reason=contexts[name];recs.append({'from_source_record_id':r['from_source_record_id'],'to_source_record_id':r['to_source_record_id'],'settlement_name':name,'recommendation':status,'hold_reason':reason,'physical_county_evidence':ev,'from_source_sha256':r['from_source_sha256'],'to_source_sha256':r['to_source_sha256'],'physical_context_verified':True,'population_comparability_asserted':False,'point_correctness_inferred_from_native_code':False})
pd.DataFrame(recs).to_csv(OUT/'root_admission_recommendations.csv',index=False)
eligible=d[d.from_settlement_name.isin([name for name,(_,status,_) in contexts.items() if status=='no_contradiction_in_physical_context'])]
eligible.to_csv(OUT/'root_eligible_candidate_identity_edges.csv',index=False)
receipt={'status':'bounded_concrete_review_no_admission','original_candidates':11,'eligible_candidates':len(eligible),'held_county_contradictions':11-len(eligible),'original_packet_modified':False,'cached_physical_source_hashes':hashes,'accepted_snapshot_input_hashes':{str(p):sha(p) for p in s.inputs},'caveat':'Accepted coordinates can be wrong namesakes despite native identifier binding. Literal name/hash checks alone did not establish county identity.'}
before=s.metrics()
for er in eligible.to_dict('records'):s.union(er['from_source_record_id'],er['to_source_record_id'])
after=s.metrics();receipt.update(baseline=before,simulated_after=after,simulated_full_three_year_population_gain={y:after[y]['covered_population']-before[y]['covered_population'] for y in before},simulated_full_three_year_row_gain={y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before})
(OUT/'root_review_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2)[:500])

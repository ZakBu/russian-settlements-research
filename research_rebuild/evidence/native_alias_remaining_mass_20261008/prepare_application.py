import sys,json,math,importlib.util
from pathlib import Path
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize,distance_km
O=Path(__file__).parent;s=load(27);before=s.metrics();assert before==json.loads((R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/application_receipt.json').read_text())['after'],'Integrated actual27 is required'
sp=importlib.util.spec_from_file_location('fm',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm);bf=fm.finite_metrics(s)
hist=pd.read_csv(O/'urban_type_historical_candidates.csv',dtype=str)
bind=pd.read_csv(O/'urban_type_bound_triplets.csv',dtype=str);edges=[];points=[];checks=[];competitors=[];pins={};books={}
classifier=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');pins[str(classifier)]=sha(classifier)
rawlines=classifier.read_text().splitlines();cl=[{'line_1based':i+1,'literal':v} for i,v in enumerate(rawlines) if v.split('\t')[0] in ['01405000005','01555000','04535555','01232894001']];assert len(cl)==4;(O/'own_classifier_raw_rows.json').write_text(json.dumps(cl,ensure_ascii=False,indent=2))
c=duckdb.connect();meta=c.execute("select source_record_id,source_sheet,source_row,entity_grain_status from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf().set_index('source_record_id')
contexts={'нагорный':{2002:[8433,8434,8435,8436,8437,8438,8439],2010:[1611,1612,1613,1614,1615,1616]},'сибирский':{2002:[8453,8454,8455,8456,8457,8458],2010:[1608,1609,1625,1626,1627]},'подгорный':{2002:[8671,8672,8673,8674,8675,8676]}}
for z in bind.to_dict('records'):
 case=z['case'];
 if case in ['нагорный','подгорный']:
  hh=hist[hist.historical_okato_2011_raw.eq(z['current_okato']) & hist.name_key.eq(case)];assert len(hh)==1;assert hh.iloc[0].historical_point_modern_region==z['region']
 ids=[z['source2002'],z['source2010'],z['source2021']];rows=[s.by_id.loc[x] for x in ids];roots={s.uf.find(x) for x in ids};years=[y for r in roots for y in s.years[r]];assert len(years)==len(set(years));assert set(years)=={2002,2010,2021}
 donor=s.point_rows[ids[-1]];dp=(donor['latitude'],donor['longitude'])
 for a in rows:
  sid=a.source_record_id;assert a.is_additive_settlement_record;assert math.isfinite(a.population);assert '(часть' not in normalize(a.settlement_name);assert sid not in s.conflicting_point_targets
  if sid in s.point_rows:assert distance_km(dp,(s.point_rows[sid]['latitude'],s.point_rows[sid]['longitude']))<=5
  mm=meta.loc[sid];path=Path('/workspace/settlements-raw')/a.source_file;pins[str(path)]=sha(path)
  check={'case':case,'source_record_id':sid,'census_year':int(a.census_year),'protected_population':a.population,'protected_quality':a.population_value_quality,'entity_grain_status':mm.entity_grain_status,'source_file':str(path),'source_sha256':pins[str(path)],'source_sheet':mm.source_sheet,'source_row_1based':mm.source_row,'population_comparability_asserted':False}
  if path.suffix=='.xls':
   bk=books.setdefault(str(path),xlrd.open_workbook(path));sh=bk.sheet_by_name(str(mm.source_sheet)) if str(mm.source_sheet) in bk.sheet_names() else bk.sheet_by_index(int(mm.source_sheet));rv=sh.row_values(int(mm.source_row)-1);ctx=[{'row':i,'values':sh.row_values(i-1)} for i in contexts[case].get(int(a.census_year),[int(mm.source_row)])];check.update(actual_raw_row_json=json.dumps(rv,ensure_ascii=False),printed_context_rows_json=json.dumps(ctx,ensure_ascii=False))
   assert any(normalize(a.settlement_name) in normalize(v) for v in rv)
   num=next(float(v) for v in rv if isinstance(v,(int,float)) and float(v)==a.population);check['actual_raw_population']=num
  elif int(a.census_year)==2010:
   proof=(O/'podgorny_primary2010_p178.txt').read_text();assert 'пгт Подгорный рп' in proof and '6760' in proof;check.update(actual_raw_population=6760,printed_context_rows_json='Primary2010 PDF p178 Железногорск parent, Городское население, пгт Подгорный рп6760, Сельское население2286',proof_file='podgorny_primary2010_p178.txt')
  else:check.update(actual_raw_population=a.population,printed_context_rows_json=json.dumps({'literal_name':a.settlement_name,'literal_type':a.settlement_type,'literal_county':a.district_raw,'own_okato':a.okato,'raw_selected_locator':a.source_locator},ensure_ascii=False))
  checks.append(check)
 # Enumerate all same-name homonyms and admitted points, including nearby candidates; positive binding relies on own code and printed admin, not region uniqueness.
 for _,a in s.obs[s.obs.name_norm.eq(case)&s.obs.region_norm.eq(z['region'])].iterrows():
  p=s.point_rows.get(a.source_record_id);dist=distance_km(dp,(p['latitude'],p['longitude'])) if p else None
  competitors.append({'case':case,'source_record_id':a.source_record_id,'year':a.census_year,'name':a.settlement_name,'type':a.settlement_type,'county':a.district_raw,'okato':a.okato,'population':a.population,'distance_to_bound_own_point_km':dist,'within_5km':dist is not None and dist<=5,'bound_triplet_member':a.source_record_id in ids})
  if p and dist<=5 and a.source_record_id not in ids:raise AssertionError('Nearby admitted different homonym '+a.source_record_id)
 for target in ids:
  if target not in s.point_rows:
   p=dict(donor);p.update(target_source_record_id=target,coordinate_admission_status='reviewed_extension_rule_accepted',case=case,coordinate_binding_rule='Independent current own name/code/type/admin point, native2002/2010 printed parent/type context; all admitted nearby homonyms enumerated',population_boundary_comparability_asserted=False,point_use_inference='modern_own_representative_point_on_source_bound_same_locality');points.append(p)
 for target in ids[:-1]:edges.append(dict(from_source_record_id=target,to_source_record_id=ids[-1],relation='same_place',decision_status='checked_rule_accepted',case=case,admission_rule='Native printed own settlement name and source parent context with exact historical/current own code; urban/rural type variants retain literal labels and protected population',source_binding_proof='actual_raw_source_bindings.csv;urban_type_bound_triplets.csv;urban_type_historical_candidates.csv;all_same_name_point_competitors.csv',population_boundary_comparability_asserted=False,municipal_event_date='UNKNOWN'))
pd.DataFrame(checks).to_csv(O/'actual_raw_source_bindings.csv',index=False);pd.DataFrame(competitors).to_csv(O/'all_same_name_point_competitors.csv',index=False);pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False)
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s)
outs=['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','actual_raw_source_bindings.csv','all_same_name_point_competitors.csv','urban_type_bound_triplets.csv','urban_type_historical_candidates.csv','podgorny_primary2010_p178.txt','own_classifier_raw_rows.json','sibirsky_raw_dbf_2011.json']
pins.update({x:sha(Path(x)) for x in ['/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf','/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet']})
r={'baseline_stage':27,'status':'Ready for parent review and loader integration; in-memory State API replay passed','cases':3,'edges':len(edges),'point_uses':len(points),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'input_pins':pins,'output_pins':{n:sha(O/n) for n in outs},'population_and_quality_unchanged':True,'Sibirsky_2010_secondary11306_vs_protected8786':'Explicit selected-source quality difference, not corrected or treated as identity requirement; native rawSib1626 is final standalone own subject-level settlement, separate from Barnaul block and rural Первомайский homonym.'}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r['net_finite_all3_all_points'],ensure_ascii=False))

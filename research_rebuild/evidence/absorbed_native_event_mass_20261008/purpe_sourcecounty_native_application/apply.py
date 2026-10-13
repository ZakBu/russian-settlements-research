from pathlib import Path
import sys,json,hashlib,xlrd,pandas as pd,re
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km
s=load(35);base=s.metrics();r02=Path('/workspace/settlements-raw/data/raw/2002/060_0d687479dd_02c_yamalo-nenets.xls');r10=Path('/workspace/settlements-raw/data/raw/2010/003_eb441570b1_11._20Урал_ФО_2010.xls');b02=xlrd.open_workbook(str(r02)).sheet_by_name('Sheet1');b10=xlrd.open_workbook(str(r10)).sheet_by_name('Урал');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); sh02=sha(r02);sh10=sha(r10)
cases=[('Tolka_Krasnoselkup',28,2726,155263,'Красноселькупский район',18),('Tolka_Purovsky',88,2758,155296,'Пуровский р-н',81),('Seyakha_printed_alias',173,2805,155317,'Ямальский район',165)]
def oldid(n):return f'2002:{r02.name}:Sheet1:{n}'
def tenid(n):return f'2010:{r10.name}:Урал:{n}'
def curid(n):return f'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:{n}'
edges=[];points=[];proof=[];competitors=[]
for case,n02,n10,n21,county,header in cases:
 a,b,c=oldid(n02),tenid(n10),curid(n21);z02,z10,z21=[s.by_id.loc[x]for x in [a,b,c]]
 assert float(b02.cell_value(n02-1,1))==z02.population
 assert float(b10.cell_value(n10-1,7))==z10.population
 assert county in str(b02.cell_value(header-1,0))
 name02=str(b02.cell_value(n02-1,0)).strip();name10=str(b10.cell_value(n10-1,6)).strip();assert z02.settlement_name.strip()in name02 and z10.settlement_name.strip()==name10
 base10=name10.split('(')[0].strip().lower().replace('ё','е');base21=str(z21.settlement_name).lower().replace('ё','е');assert base10==base21
 candidate_names=s.obs.settlement_name.str.split('(').str[0].str.strip().str.lower().str.replace('ё','е'); q=s.obs[s.obs.region_norm.eq(z21.region_norm)&candidate_names.eq(base21)];
 for _,v in q.iterrows():competitors.append({'case':case,'source_record_id':v.source_record_id,'year':v.census_year,'name':v.settlement_name,'county':v.district_raw,'population':v.population})
 if case=='Tolka_Krasnoselkup':assert 'Красносельская'in name10 and 'Красноселькупский'in str(z21.district_raw)
 if case=='Tolka_Purovsky':assert 'Пуровская'in name10 and 'Пуровский'in str(z21.district_raw)
 if case=='Seyakha_printed_alias':assert 'Ямальский'in str(z21.district_raw) and '(Сёяха, Сё-Яха)'in name10
 assert c in s.point_rows;cp=s.point_rows[c];assert cp.get('coordinate_source_record_id')==c
 # The current own code identifies a settlement NP, never a municipal receiver.
 assert len(str(z21.okato))==11 and len(str(z21.oktmo))==11
 for sid in [a,b]:
  if sid in s.point_rows:
   op=s.point_rows[sid];assert distance_km((op['latitude'],op['longitude']),(cp['latitude'],cp['longitude']))<5
  else:
   points.append({'target_source_record_id':sid,'latitude':cp['latitude'],'longitude':cp['longitude'],'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':c,'source_sha256':sh02 if sid==a else sh10,'source_locator':f'Sheet1!row={n02}'if sid==a else f'Урал!row={n10}','point_origin_file':cp['point_origin_file'],'point_origin_sha256':cp['point_origin_sha256'],'point_origin_locator':cp['point_origin_locator'],'point_origin_kind':cp['point_origin_kind'],'coordinate_origin_ledger':cp['point_ledger_path'],'coordinate_origin_ledger_sha256':sha(Path(cp['point_ledger_path'])),'coordinate_origin_ledger_locator':f'target_source_record_id={c}','admission_rule':'own_NP_point_continuity_over_literal_printed_alias_and_actual_county_context','direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'boundary_comparability_asserted':False})
 for x,y in [(a,b),(b,c)]:
  if s.uf.find(x)!=s.uf.find(y):edges.append({'from_source_record_id':x,'to_source_record_id':y,'relation':'same_place','decision_status':'checked_rule_accepted','case':case,'admission_rule':'Literal ownNP base-name and explicit source-printed parenthetical county/name qualifier; actual native02 raw county header; unique county-qualified current own coded NP and own point','source_binding_proof':'actual_raw_source_bindings.csv;all_name_competitors.csv','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
 proof.append({'case':case,'source2002_record_id':a,'source2010_record_id':b,'source2021_record_id':c,'raw2002_path':str(r02),'raw2002_sha256':sh02,'raw2002_locator':f'Sheet1!row={n02};county_header_row={header}','raw2002_cells_json':json.dumps(b02.row_values(n02-1),ensure_ascii=False),'raw2002_county_cells_json':json.dumps(b02.row_values(header-1),ensure_ascii=False),'imported2002_county':z02.district_raw,'derived_actual2002_county':county,'raw2010_path':str(r10),'raw2010_sha256':sh10,'raw2010_locator':f'Урал!row={n10};printed_name_column=G;population_column=H','raw2010_identity_cells_json':json.dumps(b10.row_values(n10-1)[:8],ensure_ascii=False),'current_np_name':z21.settlement_name,'current_county':z21.district_raw,'current_okato':z21.okato,'current_oktmo':z21.oktmo,'current_point_provenance_json':json.dumps(cp,ensure_ascii=False),'population2002':z02.population,'population2010':z10.population,'population2021':z21.population,'boundary_comparability':'UNKNOWN','event_asserted':False})
# Freeze the last actual printed county heading, ignoring secondary «сс» captions.
for z in proof:
 n=int(z['source2010_record_id'].split(':')[-1]);j=[j for j in range(n)if 'район' in str(b10.cell_value(j,3))][-1]
 z.update(derived_actual2010_county=b10.cell_value(j,3),raw2010_county_header_locator=f'Урал!row={j+1};column=D',raw2010_county_header_identity_cells_json=json.dumps(b10.row_values(j)[:8],ensure_ascii=False))
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(proof).to_csv(O/'actual_raw_source_bindings.csv',index=False);pd.DataFrame(competitors).to_csv(O/'all_name_competitors.csv',index=False)
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();gain={y:after[y]['covered_population']-base[y]['covered_population']for y in base}
r={'status':'verified_actual35_replay_native_ordinary_three_census_alias_application','baseline_stage':35,'cases':len(cases),'identity_edges':len(edges),'new_point_uses':len(points),'ordinary_population_gain_by_year':gain,'before':base,'after':after,'source_integrity':'Own native02 and native10 rows/counts exactly verified against raw workbooks; imported county and source counts unchanged; rawprinted derivedcounty annotation separate','source_grain':'native_own_NP','boundary_comparability':'UNKNOWN','historical_direct_coordinate_measurement_asserted':False,'purpe_hold':'Native02/10 alreadylinked ownpoints. No selected2021ownPurpe row; cached explicit absorption event not available. No false same_place to Gubkinsky and no fake child2021 count.'}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))

import sys,json,re
from pathlib import Path
from collections import defaultdict
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
O=Path(__file__).parent;s=load(26);before=s.metrics();c=duckdb.connect();h=c.execute('select historical_okato_2009_raw,historical_okato_2011_raw,name_key,type_key_2009,historical_point_modern_region,name_raw_2011,record_number_1based,latitude_from_lat,longitude_from_long from read_parquet(?)',['/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet']).fetchdf();meta=c.execute('select source_record_id,source_sheet,source_row from read_parquet(?)',['/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet']).fetchdf().set_index('source_record_id');pool=s.obs[s.obs.census_year.eq(2010)&s.obs.region_norm.eq('ивановская')&s.obs.settlement_name.str.contains(r' п\.$',regex=True)].copy();books={};rows=[];holds=[];proof=[];sourcechecks=pd.read_csv(O/'large_actual_native_row_and_alias_proofs.csv').set_index('source_record_id')
for _,a in pool.iterrows():
 sid=a.source_record_id;n=normalize(re.sub(r'\s+п\.$','',a.settlement_name));old=s.obs[s.obs.census_year.eq(2002)&s.obs.region_norm.eq(a.region_norm)&s.obs.settlement_name.map(normalize).map(lambda z:z.replace('-', '') if n=='ново-писцово' else z).eq(n.replace('-', '') if n=='ново-писцово' else n)&s.obs.type_norm.eq('пгт')];cur=s.obs[s.obs.census_year.eq(2021)&s.obs.region_norm.eq(a.region_norm)&s.obs.settlement_name.map(normalize).map(lambda z:z.replace('-', '') if n=='ново-писцово' else z).eq(n.replace('-', '') if n=='ново-писцово' else n)&s.obs.type_norm.isin(['пгт','поселок'])];gh=h[h.name_key.map(normalize).map(lambda z:z.replace('-', '') if n=='ново-писцово' else z).eq(n.replace('-', '') if n=='ново-писцово' else n)&h.type_key_2009.eq('пгт')&h.historical_point_modern_region.eq(a.region_norm)];
 if len(old)!=1 or len(gh)!=1:holds.append({'source_record_id':sid,'name':a.settlement_name,'reason':'Historical own urban NP or classifier code not unique'});continue
 g=gh.iloc[0];matched=[]
 for _,b in cur.iterrows():
  bc=str(b.okato or '')
  if bc.endswith('.0'):bc=bc[:-2]
  if bc in [g.historical_okato_2009_raw,g.historical_okato_2011_raw]:matched.append(b)
 if len(matched)!=1:holds.append({'source_record_id':sid,'name':a.settlement_name,'reason':'No unique current urban own code/name/context'});continue
 b=matched[0];bid=b.source_record_id;oid=old.iloc[0].source_record_id;reason=[]
 if bid not in s.point_rows:reason.append('No admitted current own point')
 roots={s.uf.find(x) for x in [sid,oid,bid]};years=[]
 for root in roots:years.extend(s.years[root])
 if len(years)!=len(set(years)):reason.append('Real repeated-year component')
 p=s.point_rows.get(bid)
 if p:
  for x in [sid,oid,bid]:
   pp=s.point_rows.get(x)
   if pp and distance_km((pp['latitude'],pp['longitude']),(p['latitude'],p['longitude']))>5:reason.append('Actual admitted point conflict')
 if reason:holds.append({'source_record_id':sid,'name':a.settlement_name,'reason':'; '.join(reason)});continue
 m=meta.loc[sid];path=Path('/workspace/settlements-raw')/a.source_file;bk=books.setdefault(str(path),xlrd.open_workbook(path));sh=bk.sheet_by_name(str(m.source_sheet));vals=sh.row_values(int(m.source_row)-1);li=next(i for i,v in enumerate(vals) if normalize(a.settlement_name) in normalize(v));literal=str(vals[li]);num=next(float(v) for v in vals[li+1:] if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',str(v).replace(' ','')));proof.append({'source_record_id':sid,'actual_raw_label':literal,'actual_first_reported_population':num,'selected_protected_population':a.population,'protected_vs_actual_population_difference':a.population-num,'source_file':str(path),'source_sha256':sha(path),'source_sheet':str(m.source_sheet),'source_row_1based':int(m.source_row),'raw_row_json':json.dumps(vals,ensure_ascii=False),'name_rule':'Remove standalone compatible type suffix п.; preserve the literal source spelling','source_quality_preserved':a.population_value_quality,'already_checked_row_reused':sid in sourcechecks.index});
 rows.append({'case':n,'from_source_record_id':sid,'old2002_source_record_id':oid,'current_source_record_id':bid,'canonical_name':n,'printed_2010_name':a.settlement_name,'from_population':a.population,'old_population':old.iloc[0].population,'current_population':b.population,'historical_own_code_2009':g.historical_okato_2009_raw,'historical_own_code_2011':g.historical_okato_2011_raw,'raw_own_geo_label':g.name_raw_2011,'raw_geo_record_1based':g.record_number_1based,'historical_classifier_own_type':'пгт','current_printed_type':b.settlement_type,'current_printed_county':b.district_raw,'all_region_current_compatible_type_candidates':len(cur),'matched_current_own_code_candidates':len(matched),'old_component_years':json.dumps(sorted(s.years[s.uf.find(oid)])),'source2010_component_years':json.dumps(sorted(s.years[s.uf.find(sid)])),'current_component_years':json.dumps(sorted(s.years[s.uf.find(bid)])),'current_own_point_json':json.dumps(p,ensure_ascii=False),'candidate_status':'Source-bound whole urban NP alias candidate; no mutations'})
pd.DataFrame(rows).to_csv(O/'standalone_type_suffix_candidates.csv',index=False);pd.DataFrame(proof).to_csv(O/'standalone_type_suffix_actual_source_checks.csv',index=False);pd.DataFrame(holds).to_csv(O/'standalone_type_suffix_holds.csv',index=False);print('Candidates',len(rows),'protected2010 population',int(sum(z['from_population'] for z in rows)),'holds',len(holds));print(pd.DataFrame(rows)[['canonical_name','from_population','old_population','current_population']].to_string(index=False) if rows else '')

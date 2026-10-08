import sys,json,re,gzip
from pathlib import Path
import pandas as pd,xlrd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(25);c=duckdb.connect();selected='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet';meta=c.execute('select source_record_id,source_sheet,source_row from read_parquet(?)',[selected]).fetchdf().set_index('source_record_id');cases=[('Lezhnevo','2010:013_f60b2d2bcf_5._20Belg_Bryan_Vlad_Voron_Ivanov_Kalug_20L1_ethn_2010.xls:Data Sheet:9834','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:21264'),('Centoroy','2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1610','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:161732'),('Berdykel scope hold','2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1519','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:162088')];rows=[];anchor_rows=[];books={}
for case,sid,bid in cases:
 a=s.by_id.loc[sid];m=meta.loc[sid];file=Path('/workspace/settlements-raw')/a.source_file;b=books.setdefault(str(file),xlrd.open_workbook(file));sh=b.sheet_by_name(str(m.source_sheet));rn=int(m.source_row);vals=sh.row_values(rn-1);li=next(i for i,x in enumerate(vals) if normalize(a.settlement_name) in normalize(x));literal=str(vals[li]);num=next(float(v) for v in vals[li+1:] if re.fullmatch('[0-9]+(?:\\.[0-9]+)?',str(v).replace(' ','')));assert num==float(a.population);anchors=[]
 # Existing accepted native2002 counterparts supply historical county, not proposed renamed-current identity.
 sheetobs=s.obs[s.obs.census_year.eq(2010)&s.obs.source_file.eq(a.source_file)]
 for _,peer in sheetobs.iterrows():
  pid=peer.source_record_id;pm=meta.loc[pid]
  if str(pm.source_sheet)!=str(m.source_sheet) or pd.isna(pm.source_row) or not(0<abs(int(pm.source_row)-rn)<=20):continue
  root=s.uf.find(pid);old=s.obs[s.obs.source_record_id.map(s.uf.find).eq(root)&s.obs.census_year.eq(2002)]
  if len(old)!=1 or not county_key(old.iloc[0].district_raw):continue
  pr=int(pm.source_row);pv=sh.row_values(pr-1);pl=[str(v) for v in pv if isinstance(v,str) and normalize(peer.settlement_name) in normalize(v)];
  if not pl:continue
  anchor={'target_source_record_id':sid,'anchor_2010_source_record_id':pid,'anchor_source_row_1based':pr,'anchor_raw_label':pl[0],'anchor_2002_source_record_id':old.iloc[0].source_record_id,'historical_printed_county':old.iloc[0].district_raw,'historical_county_key':county_key(old.iloc[0].district_raw),'anchor_component_years':json.dumps(sorted(s.years[root]))};anchors.append(anchor)
 lower=sorted([x for x in anchors if x['anchor_source_row_1based']<rn],key=lambda x:x['anchor_source_row_1based'],reverse=True);upper=sorted([x for x in anchors if x['anchor_source_row_1based']>rn],key=lambda x:x['anchor_source_row_1based']);pair=None
 for l in lower:
  for u in upper:
   if l['historical_county_key']==u['historical_county_key'] and normalize(l['anchor_raw_label'])!=normalize(u['anchor_raw_label']):pair=(l,u);break
  if pair:break
 proof={'case':case,'source_record_id':sid,'current_source_record_id':bid,'actual_native_label':literal,'actual_first_population':num,'original_native_source_file':str(file),'original_native_source_sha256':sha(file),'source_sheet':str(m.source_sheet),'source_row_1based':rn,'native_raw_row_json':json.dumps(vals,ensure_ascii=False),'old_component_years':json.dumps(sorted(s.years[s.uf.find(sid)])),'current_component_years':json.dumps(sorted(s.years[s.uf.find(bid)])),'inferred_historical_county_from_two_sided_existing_native_anchors':pair[0]['historical_printed_county'] if pair else '', 'two_sided_native_anchor_proof':json.dumps(pair,ensure_ascii=False),'current_own_point_json':json.dumps(s.point_rows.get(bid,{}),ensure_ascii=False),'source_population_quality_preserved':a.population_value_quality}
 if case=='Lezhnevo':proof['name_rule']='Strip explicit standalone trailing type abbreviation п. compatible with printed пгт; preserve original label';proof['same_type_region_unique_urban_name']=True
 elif case=='Centoroy':
  p=Path('/workspace/settlements-raw/data/raw/wikipedia_articles/batch_00114.json.gz');j=json.load(gzip.open(p,'rt'));pg=next(x for x in j['payload']['query']['pages'] if x.get('pageid')==1952452);text=pg['revisions'][0]['slots']['main']['content'];hits=[text[max(0,k.start()-100):k.end()+220] for k in re.finditer('Центорой|прежние имена|Ахмат-Юрт',text)];proof.update(name_rule='Existing admitted own former name; source2010 historic county independently bracketed',own_article_source_file=str(p),own_article_sha256=sha(p),own_article_pageid=1952452,own_article_revision=pg['revisions'][0]['revid'],own_article_alias_excerpts=json.dumps(hits[:6],ensure_ascii=False))
 else:proof['hold_reason']='Known own article census2010 explicitly includes Primykanie; atomic settlement population grain unresolved';proof['population_grain_credit_allowed']=False
 rows.append(proof);anchor_rows.extend(pair or [])
pd.DataFrame(rows).to_csv(O/'large_actual_native_row_and_alias_proofs.csv',index=False);pd.DataFrame(anchor_rows).to_csv(O/'large_2010_two_sided_historical_native_county_anchors.csv',index=False);print(pd.DataFrame(rows)[['case','actual_native_label','actual_first_population','inferred_historical_county_from_two_sided_existing_native_anchors']].to_string(index=False))

from pathlib import Path
import sys,json,re,pandas as pd,pyarrow.parquet as pq,xlrd
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=E/'large_absorbed_city_closed_scope_mass_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load();print('loaded');meta=pq.read_table(s.inputs[0],columns=['source_record_id','source_sheet','source_row','source_name_raw']).to_pandas();o=s.obs.merge(meta,on='source_record_id');rawpath=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');raw=pq.read_table(rawpath,columns=['object_level','object_name','region','mun_upper','mun_lower','settlement','population','oktmo']).to_pandas();sh=xlrd.open_workbook('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls').sheet_by_index(0)
configs=[('Каменск-Шахтинский','ростовская',4961,4964),('Владимир','владимирская',241,250),('Барнаул','алтайский',8414,8430),('Находка','приморский',9955,9960),('Волгоград','волгоградская',4776,4792),('Артем','приморский',9930,9938),('Екатеринбург','свердловская',7391,7411),('Челябинск','челябинская',7952,7965),('Копейск','челябинская',7994,8004),('Шахты','ростовская',4981,4987),('Киров','кировская',5928,5940),('Якутск','саха якутия',9747,9757)]
results=[];scopes=[]
for name,region,a,b in configs:
 city=o[o.census_year.eq(2021)&o.name_norm.str.replace('-', ' ',regex=False).eq(name.lower().replace('ё','е').replace('-', ' '))&o.region_norm.eq(region)&o.type_norm.eq('город')]
 if len(city)!=1:results.append({'city':name,'hold':'nativecurrentcitynotunique','hits':len(city)});continue
 c=city.iloc[0];rs=raw.iloc[int(c.source_row)-1];scope=raw[raw.region.eq(rs.region)&raw.mun_upper.eq(rs.mun_upper)].copy();scope['raw_row_1based']=scope.index+1;np=scope[scope.object_level.eq('Населенный пункт')];parent=scope[scope.object_level.eq('Муниципалитет верхнего уровня')]
 scopes.append(scope.assign(city_scope=name));federal=[]
 for n in range(a,b+1):
  label=str(sh.cell_value(n-1,0));value=sh.cell_value(n-1,1)
  if re.match(r'^\s+(?:г\.|пгт|с\.|п\.)\s+',label) and 'с подчиненными' not in label and 'Сельское население' not in label:
   matches=o[o.census_year.eq(2002)&o.source_file.eq('data/raw/2002_official_tom1/1_TOM_01_04.xls')&o.source_row.eq(n)];federal.extend(matches.to_dict('records'))
  elif 'Сельское население - п.' in label:
   matches=o[o.census_year.eq(2002)&o.source_file.eq('data/raw/2002_official_tom1/1_TOM_01_04.xls')&o.source_row.eq(n)];federal.extend(matches.to_dict('records'))
 results.append({'city':name,'region':region,'current_city_id':c.source_record_id,'current_parent':rs.mun_upper,'current_rawNP_count':len(np),'current_rawNP_sum':int(np.population.sum()),'current_parent_count':int(parent.iloc[0].population) if len(parent)==1 else None,'current_parent_NP_closure':len(parent)==1 and int(parent.iloc[0].population)==int(np.population.sum()),'native_current_count':int(c.population),'current_accepted_point':c.source_record_id in s.point_rows,'federal2002_start':a,'federal2002_end':b,'federal2002_parent_control':int(sh.cell_value(a-1,1)),'federal2002_atomic_count':len(federal),'federal2002_atomic_sum':sum(int(z['population']) for z in federal),'rural2002_residual_to_close':int(sh.cell_value(a-1,1))-sum(int(z['population']) for z in federal),'federal2002_members_json':json.dumps([{k:z[k] for k in ['source_record_id','settlement_name','settlement_type','population']} for z in federal],ensure_ascii=False)})
pd.DataFrame(results).to_csv(O/'city_scope_first_pass.csv',index=False);pd.concat(scopes).to_csv(O/'published2021_city_parent_all_child_rows.csv',index=False);print(pd.DataFrame(results).drop(columns=['federal2002_members_json'],errors='ignore').to_string(index=False))

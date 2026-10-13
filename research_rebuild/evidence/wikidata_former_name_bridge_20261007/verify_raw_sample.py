import sys,json,gzip,re
from pathlib import Path
import pandas as pd
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];sys.path.insert(0,str(ROOT/'mass_linkage'))
from current_chain_state_20261007 import sha,normalize
from apply_unique_county_name_bridge_20261007 import county_key
obs=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet').set_index('source_record_id');cache={};checks=[]
for role,file in [('fixed_sample20','fixed_sample20.csv'),('top5','top5_raw_checks.csv')]:
 for r in pd.read_csv(OUT/file).to_dict('records'):
  z={'sample_role':role,'qid':r['qid'],'from_source_record_id':r['from_source_record_id'],'to_source_record_id':r['to_source_record_id'],'former_name_witness_file':r['witness_file'],'former_name_witness_locator':r['witness_locator'],'former_name_witness_sha256':sha(Path(r['witness_file']))}
  for side in ['from','to']:
   o=obs.loc[r[side+'_source_record_id']];p=Path('/workspace/settlements-raw')/o.source_file
   key=(str(p),o.source_sheet)
   try:
    if key not in cache:cache[key]=pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_excel(p,sheet_name=o.source_sheet,header=None)
    row=cache[key].iloc[int(o.source_row)-1];raw=[str(x) for x in row.values if pd.notna(x)]
    nameok=any(normalize(o.settlement_name) in normalize(x) for x in raw);popok=any(x==str(int(o.population)) or x==str(float(o.population)) for x in raw)
    county=county_key(o.district_raw);countyproof=[]
    if county:
     for ix in range(int(o.source_row)-1,max(-1,int(o.source_row)-350),-1):
      rr=cache[key].iloc[ix];values=[str(x) for x in rr.values if pd.notna(x)]
      matches=[x for x in values if (county_key(x)==county or normalize(o.district_raw) in normalize(x)) and ('район' in normalize(x) or 'округ' in normalize(x))]
      if matches:countyproof=[f'row={ix+1}',matches];break
    z[side+'_raw_county_context_found']=bool(countyproof);z[side+'_raw_county_context']=json.dumps(countyproof,ensure_ascii=False)
    z.update({side+'_source_file':str(p),side+'_source_sha256':sha(p),side+'_source_locator':f'{o.source_sheet}!row={int(o.source_row)}',side+'_raw_name_population_match':nameok and popok,side+'_raw_row_excerpt':json.dumps(raw[:12],ensure_ascii=False)})
   except Exception as e:z[side+'_raw_check_error']=str(e)
  z['former_name_exact_own_source_checked']=Path(r['witness_file']).exists() and bool(r['witness_locator']);checks.append(z)
pd.DataFrame(checks).to_csv(OUT/'raw_source_check_results.csv',index=False);print(pd.DataFrame(checks)[['sample_role','from_raw_name_population_match','to_raw_name_population_match']].value_counts().to_string())

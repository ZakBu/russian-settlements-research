import sys,json,re
from pathlib import Path
import pandas as pd,xlrd,duckdb
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mass_linkage'))
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent;CACHE=Path('/dev/shm/settlements-stage71-20261009');r=pd.read_csv('/dev/shm/over500-20261009/south_remaining.csv');obs=pd.read_parquet(CACHE/'applied_state_observations.parquet');by=obs.set_index('source_record_id');raw21=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');c=duckdb.connect(config={'threads':1});raw=c.execute('select object_name,oktmo,mun_upper,mun_lower,population from read_parquet(?)',[str(raw21)]).fetchdf();raw['source_record_id']=['2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(n) for n in range(1,len(raw)+1)];raw=raw.set_index('source_record_id');c.close();raw.to_parquet('/dev/shm/over500-20261009/south_native_current.parquet');books={};hashes={str(raw21):sha(raw21)};w=[];bindings=[]
obs['county']=obs.district_raw.map(county_key);owncounty=obs[obs.census_year.ne(2010)&obs.county.ne('')].groupby('root').county.agg(lambda x:set(x)).to_dict();currentids=obs[obs.census_year.eq(2021)].groupby('root').source_record_id.agg(list).to_dict()
for q in r.to_dict('records'):
 sid=q['source_record_id'];path=Path('/workspace/settlements-raw')/q['source_file'];sheet=sid.rsplit(':',2)[-2];no=int(sid.rsplit(':',1)[-1]);
 if path not in books:books[path]=xlrd.open_workbook(path,on_demand=True);hashes[str(path)]=sha(path)
 sh=books[path].sheet_by_name(sheet);vals=sh.row_values(no-1);nameok=any(normalize(q['settlement_name']) in normalize(v) for v in vals if isinstance(v,str));popok=any(str(v).strip().replace('.','',1).isdigit() and float(str(v).strip())==float(q['population']) for v in vals);parent=[]
 if q['census_year']==2002:
  for n in range(no-2,-1,-1):
   texts=[str(v) for v in sh.row_values(n) if isinstance(v,str)];line=' | '.join(texts)
   if re.search(r'сельсовет|\bсс\b|сельская администрация|администрация сельск|администрации г\.|администрации.*города',normalize(line)):
    parent.append({'row_1based':n+1,'literal':line});break
 w.append(dict(source_record_id=sid,source_file=str(path),source_sha256=hashes[str(path)],source_sheet=sheet,source_row_1based=no,native_literal=json.dumps(vals,ensure_ascii=False),native_name_verified=nameok,native_population_verified=popok,explicit_parent_context=json.dumps(parent,ensure_ascii=False)))
 if q['census_year']!=2010 or pd.notna(q['district_raw']):continue
 same=obs[obs.census_year.eq(2010)&obs.source_file.eq(q['source_file'])&obs.region_norm.eq(q['region_norm'])].copy();same=same[same.source_record_id.str.rsplit(':',n=2).str[-2].eq(sheet)];same['row']=same.source_record_id.str.rsplit(':',n=1).str[-1].astype(int);anchors=[]
 for a in same[same.row.ne(no)&(same.row-no).abs().le(35)].itertuples():
  ids=currentids.get(a.root,[])
  if len(ids)!=1 or ids[0] not in raw.index:continue
  cur=raw.loc[ids[0]];county=county_key(cur.mun_upper);lower=normalize(cur.mun_lower)
  if not lower or not county:continue
  anchorcells=sh.row_values(a.row-1);valid=any(normalize(a.settlement_name) in normalize(v) for v in anchorcells if isinstance(v,str))
  if valid:anchors.append((a.row,a.source_record_id,ids[0],county,lower,json.dumps(anchorcells,ensure_ascii=False)))
 lo=sorted((a for a in anchors if a[0]<no),reverse=True);hi=sorted(a for a in anchors if a[0]>no)
 if not lo or not hi:continue
 if lo[0][1]!=hi[0][1]:
  lowerSame=lo[0][4]==hi[0][4];bindings.append(dict(source_record_id=sid,inferred_county=lo[0][3] if lo[0][3]==hi[0][3] else '',bounded_county_alternatives=json.dumps(sorted({lo[0][3],hi[0][3]}),ensure_ascii=False),inferred_native_current_municipal_lower=lo[0][4] if lowerSame and lo[0][3]==hi[0][3] else '',lower_source_record_id=lo[0][1],upper_source_record_id=hi[0][1],lower_current_native_source_record_id=lo[0][2],upper_current_native_source_record_id=hi[0][2],lower_literal=lo[0][5],upper_literal=hi[0][5],source_file=str(path),source_sha256=hashes[str(path)],inference_rule='two_distinct_accepted_native_source_anchors_same_current_county_and_optional_same_primary_municipal_lower',source_field_modified=False))
pd.DataFrame(w).to_csv(OUT/'native_source_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(bindings).to_csv(OUT/'source_order_current_context.csv',index=False);(OUT/'source_inputs.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n');print('rows',len(w),'inferredcontexts',len(bindings));print(pd.DataFrame(bindings)[['source_record_id','inferred_county','inferred_native_current_municipal_lower']].to_string(index=False))

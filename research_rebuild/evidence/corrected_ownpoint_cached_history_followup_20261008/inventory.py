from pathlib import Path
import sys,json,collections,re
import pandas as pd,duckdb
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');E=O.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize
s=load(57);P=E/'native_mass_raw_roster_point_corrections_20261008/accepted_point_use_delta.csv.gz';p=pd.read_csv(P,keep_default_na=False);current=set(p.loc[p.target_source_record_id.str.startswith('2021:'),'target_source_record_id']);members=collections.defaultdict(list)
for sid in s.by_id.index:members[s.uf.find(sid)].append(sid)
credit=set();pins={str(f):sha(f) for f in [P,*s.inputs]}
for folder,pattern in [('native2010_remaining_county_rule_mass_20261008','baseline49_union_*.gz'),('cached_current_bound_secondary2002_mass_20261008','accepted_selected_source_id_credit_union.csv.gz'),('working_full_chain_20261007','*credit_union.csv')]:
 for f in sorted((E/folder).glob(pattern)):
  data=pd.read_csv(f,keep_default_na=False);pins[str(f)]=sha(f)
  for col in data:
   if 'source_record_id' in col and not col.endswith('json'):credit.update(data[col].astype(str))
T=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');pins[str(T)]=sha(T);bycode=collections.defaultdict(set)
for line in T.open():
 vals=line.rstrip().split('\t');q=re.findall(r'Q\d+',vals[0]) if vals else []
 if q and len(vals)>=2:
  for code in re.findall(r'\d{8,11}',vals[1]):bycode[str(int(code))].add(q[0])
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');c=duckdb.connect(config={'threads':1});rawcodes=c.execute('select row_number() over() rn,oktmo from read_parquet(?)',[str(RAW)]).fetchdf().set_index('rn').oktmo.to_dict();c.close();pins[str(RAW)]=sha(RAW)
rows=[]
for sid in sorted(current):
 root=s.uf.find(sid);ys=s.years[root];member=members[root];row=s.by_id.loc[sid];point=s.point_rows.get(sid)
 if not point:continue
 own=str(rawcodes[int(sid.rsplit(':',1)[1])]);qs=set(bycode.get(str(int(own)),set()));direct=str(point.get('coordinate_source_record_id',''))
 if re.fullmatch(r'Q\d+',direct):qs.add(direct)
 pops={int(s.by_id.loc[i,'census_year']):s.by_id.loc[i,'population'] for i in member};ids={int(s.by_id.loc[i,'census_year']):i for i in member};rows.append({'current_source_record_id':sid,'name':row.settlement_name,'region':row.region_norm,'county':row.district_raw,'type':row.settlement_type,'native2021_own_code':own,'years_json':json.dumps(sorted(ys)),'missing_year':next(iter({2002,2010,2021}-ys)) if len(ys)==2 else '','native2010_source_record_id':ids.get(2010,''),'native2002_source_record_id':ids.get(2002,''),'population2010':pops.get(2010,''),'population2002':pops.get(2002,''),'population2021':pops.get(2021,''),'point_source_record_id':direct,'point_json':json.dumps(point,ensure_ascii=False,default=str),'correct_own_Q_candidates_json':json.dumps(sorted(qs)),'ordinary':bool(row.is_additive_settlement_record),'already_native2010_qualified':ids.get(2010,'') in credit if 2010 in ids else False,'all_member_points_available':all(i in s.point_rows and i not in s.conflicting_point_targets for i in member)})
f=pd.DataFrame(rows);f.to_csv(O/'corrected_carrier_component_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});a=f[f.missing_year.ne('')&f.ordinary&f.all_member_points_available&~f.already_native2010_qualified].copy();a.to_csv(O/'uncredited_two_year_ownpoint_components.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'baseline_stage':57,'recovered_current_carriers':len(f),'component_years':f.years_json.value_counts().to_dict(),'uncredited_two_year_components':len(a),'uncredited_existing_native2010_population':int(pd.to_numeric(a.population2010,errors='coerce').sum()),'uncredited_existing_native2002_population':int(pd.to_numeric(a.population2002,errors='coerce').sum()),'uncredited_existing_native2021_population':int(pd.to_numeric(a.population2021,errors='coerce').sum()),'own_Q_candidates':len({q for v in a.correct_own_Q_candidates_json for q in json.loads(v)}),'input_pins':pins};(O/'inventory_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False));print(a.drop(columns=['point_json']).to_string(index=False))

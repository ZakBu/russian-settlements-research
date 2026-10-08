import json,difflib,re
from pathlib import Path
import pandas as pd,duckdb
O=Path(__file__).parent;a=pd.read_csv(O/'regional_inventory.csv');D={};origin={}
for p in Path('/workspace/settlements-work/continuation_20261004/R4/residual_alias_fetch/raw_entity_batches').glob('*.json'):
 for q,z in json.load(open(p)).get('entities',{}).items():D[q]=z;origin[q]=str(p)
w=duckdb.connect().execute('select source_record_id,wikidata_qid from read_parquet(?)',['/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet']).fetchdf();qids={sid:list(g.wikidata_qid) for sid,g in w.groupby('source_record_id')}
def n(s):return re.sub('[^а-яa-z0-9]','',str(s).lower().replace('ё','е'))
rows=[]
for b in a[a.census_year.eq(2021)&a.point].to_dict('records'):
 for q in qids.get(b['source_record_id'],[]):
  z=D.get(q,{});pops=[]
  for x in z.get('claims',{}).get('P1082',[]):
   try:
    yy=[int(t['datavalue']['value']['time'][1:5]) for t in x.get('qualifiers',{}).get('P585',[])];pop=float(x['mainsnak']['datavalue']['value']['amount'])
    if 2002 in yy:pops.append(pop)
   except:pass
  for old in a[a.census_year.eq(2002)&a.population.gt(0)&a.population.isin(pops)&a.years.ne('[2002, 2010, 2021]')].to_dict('records'):
   ratio=difflib.SequenceMatcher(None,n(old['settlement_name']),n(b['settlement_name'])).ratio()
   rows.append({'old':old['settlement_name'],'cur':b['settlement_name'],'old_id':old['source_record_id'],'cur_id':b['source_record_id'],'qid':q,'pop':old['population'],'ratio':ratio,'old_county':old['district_raw'],'cur_county':b['district_raw'],'entity_path':origin[q]})
pd.DataFrame(rows).to_csv(O/'population_context_candidates.csv',index=False);print(pd.DataFrame(rows)[['old','cur','pop','ratio','old_county','cur_county']].to_string(index=False))

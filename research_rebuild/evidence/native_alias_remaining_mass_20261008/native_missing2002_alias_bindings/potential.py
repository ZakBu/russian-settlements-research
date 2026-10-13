import gzip,json,re
from pathlib import Path
import pandas as pd,duckdb
O=Path(__file__).parent
P=O.parents[1]/'legacy_coordinate_current_ownpoint_mass_20261008/missing_third_year_priority/temporal_gap_trajectories.csv.gz'
f=pd.read_csv(P,dtype=str,keep_default_na=False);f=f[f.missing_year.eq('2002')]
ents={};archives={}
for p in Path('/workspace/settlements-work/own_dated2002_secondary_scope_20261008').glob('batch_*.json.gz'):
 z=json.load(gzip.open(p,'rt'));ee=z.get('entities',z.get('payload',{}).get('entities',{}));ents.update(ee);archives.update({q:str(p) for q in ee})
def norm(s):return re.sub(r'\s+',' ',str(s).lower().replace('ё','е')).strip()
def names(s):
 s=norm(s);s=re.sub(r'^(пос[её]лок|село|деревня|хутор)\s+','',s);s=re.sub(r'\s*\([^)]*\)$','',s);s=re.sub(r'^им\.\s*','имени ',s);return s
old=duckdb.connect().execute("select source_record_id,settlement_name,settlement_type,region_raw,district_raw,population,source_file,source_sheet,source_row,entity_grain_status from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet') where census_year=2002").fetchdf();old['key']=old.settlement_name.map(names)
rows=[]
for x in f.to_dict('records'):
 for q in json.loads(x['current_ownpoint_qids_json']):
  e=ents.get(q)
  if not e:continue
  labels=[e.get('labels',{}).get('ru',{}).get('value','')]+[a['value'] for a in e.get('aliases',{}).get('ru',[])];keys={names(v) for v in labels if v};codes=[c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in e.get('claims',{}).get('P764',[])];owncodes={x['current_native_okato'],x['current_native_oktmo']};cp=any(str(v) in owncodes or str(v).lstrip('0') in {k.lstrip('0') for k in owncodes if k} for v in codes)
  if not cp or names(x['name']) not in keys:continue
  dated=[]
  for c in e.get('claims',{}).get('P1082',[]):
   if any(v.get('datavalue',{}).get('value',{}).get('time','').startswith('+2002-') for v in c.get('qualifiers',{}).get('P585',[])):
    dated.append(float(c['mainsnak']['datavalue']['value']['amount']))
  opts=old[old.region_raw.eq(x['region'])&old.key.isin(keys)]
  for z in opts.to_dict('records'):
   rows.append(dict(x,old_source_record_id=z['source_record_id'],old_name=z['settlement_name'],old_county=z['district_raw'],old_type=z['settlement_type'],old_population=z['population'],qid=q,entity_file=archives[q],entity_own_names=json.dumps(labels,ensure_ascii=False),native_old_name_binding_rule='Explicit own entity name/alias or printed im. abbreviation',dated2002_exact=float(z['population']) in dated,source_file=z['source_file'],source_sheet=z['source_sheet'],source_row=z['source_row'],same_own_alias_region_options=len(opts)))
rr=pd.DataFrame(rows);rr.to_csv(O/'native_alias_potential.csv',index=False);print(rr[['name','old_name','region','old_population','qid','dated2002_exact','same_own_alias_region_options']].to_string(index=False));print('cases',len(rr),'oldpop',rr.old_population.sum() if len(rr) else 0)

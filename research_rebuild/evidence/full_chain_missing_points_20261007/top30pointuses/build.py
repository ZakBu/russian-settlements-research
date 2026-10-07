#!/usr/bin/env python3
"""Build a bounded batch of point uses for the next ranked unpointed full chains."""
from __future__ import annotations
import hashlib, json, re, sys
from collections import Counter
from pathlib import Path
import duckdb, pandas as pd
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import State,normalize,distance_km
from measure_event_aware_path_union_20261005 import SELECTED
OUT=Path(__file__).resolve().parent
TOCHNO=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
ENTITY=OUT/'wikidata_entities.json'
CSV=OUT/'top30_point_use_delta.csv'; CONTEXT=OUT/'source_context.csv'; RECEIPT=OUT/'receipt.json'
ALIASES=[r'^при станции\s+',r'^станции\s+',r'^станция\s+',r'^железнодорожной станции\s+',r'^железнодорожного разъезда\s+',r'^разъезда\s+']
QIDS={('зеленоградский','московская область'): 'Q4024098', ('станции таловка','республика бурятия'): 'Q19691747', ('железнодорожной станции тулюшка','иркутская область'): 'Q16017657', ('плодопитомник','амурская область'): 'Q19691774'}

def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def aliases(name):
 n=normalize(name); out={n}
 for pat in ALIASES: out.add(re.sub(pat,'',n))
 return {x for x in out if x}
def provider_type_ok(target_type,source_type):
 t,s=normalize(target_type),normalize(source_type)
 if t=='поселок': return s=='поселок' or s.startswith('поселок ') or s=='сельский поселок'
 if t=='пгт': return s=='поселок городского типа'
 if t=='село': return s=='село'
 return t==s

def component_inventory(state):
 obs=state.obs.copy();obs['root']=obs.source_record_id.map(state.uf.find);out=[]
 for root,g in obs.groupby('root',sort=False):
  if state.years[state.uf.find(root)]!={2002,2010,2021} or len(g)!=3 or set(g.census_year.astype(int))!={2002,2010,2021}:continue
  if any(sid in state.point_rows for sid in g.source_record_id):continue
  if any(len({normalize(v) for v in g[c]})!=1 for c in ('settlement_name','settlement_type','region_norm')):continue
  if any(normalize(v) in {'троицкое'} and normalize(r)=='московская' for v,r in zip(g.settlement_name,g.region_norm)):continue
  out.append((sum(int(x) for x in g.population if pd.notna(x)),root,g))
 return sorted(out,key=lambda x:(-x[0],str(x[1])))

def main():
 state=State(); baseline=state.metrics();strict=component_inventory(state)
 ids2021=[str(g.loc[g.census_year.eq(2021),'source_record_id'].iloc[0]) for _,_,g in strict]
 con=duckdb.connect(config={'threads':1,'memory_limit':'1GB'})
 sel=con.execute('SELECT source_record_id,settlement_name,settlement_type,region_raw,district_raw,population,oktmo,okato,latitude,longitude,source_file,source_sha256,source_locator FROM read_parquet(?) WHERE census_year=2021',[str(SELECTED)]).fetchdf()
 sel=sel[sel.source_record_id.astype(str).isin(set(ids2021))].copy();sel.source_record_id=sel.source_record_id.astype(str);sidx=sel.set_index('source_record_id')
 prov=con.execute("SELECT file_row_number,object_level,settlement_dadata,settlement_type_full_dadata,region,fias_level_dadata,qc_geo_dadata,oktmo,latitude_dadata,longitude_dadata FROM read_parquet(?,file_row_number=true) WHERE object_level='Населенный пункт' AND fias_level_dadata=6 AND qc_geo_dadata=3 AND latitude_dadata IS NOT NULL AND longitude_dadata IS NOT NULL",[str(TOCHNO)]).fetchdf()
 entity=json.loads(ENTITY.read_text(encoding='utf-8'))['entities']; pindex={}
 for _,r in prov.iterrows():
  key=(normalize(r.settlement_dadata),normalize(r.region),str(r.oktmo));pindex.setdefault(key,[]).append(r)
 candidates=[]; held=Counter();
 for rank,(mass,root,g) in enumerate(strict,1):
  cur=g[g.census_year.eq(2021)].iloc[0];sid=str(cur.source_record_id)
  if sid not in sidx.index:continue
  t=sidx.loc[sid]; name=str(t.settlement_name);kind=str(t.settlement_type);region=str(t.region_raw);aliases0=aliases(name);provider=None
  if normalize(kind) in {'поселок','пгт','село'} and pd.notna(t.oktmo):
   matches=[]
   for a in aliases0: matches+=pindex.get((a,normalize(region),str(t.oktmo)),[])
   # accept a single provider record, or duplicate rows only if source tuple and point are identical
   if len(matches)==1 and provider_type_ok(kind,matches[0].settlement_type_full_dadata):provider=matches[0]
   elif len(matches)>1:
    sig={(str(x.settlement_dadata),str(x.settlement_type_full_dadata),float(x.latitude_dadata),float(x.longitude_dadata)) for x in matches}
    if len(sig)==1 and provider_type_ok(kind,matches[0].settlement_type_full_dadata):provider=matches[0]
  item=None
  if provider is not None:
   lat,lon=float(provider.latitude_dadata),float(provider.longitude_dadata)
   if pd.notna(t.latitude) and pd.notna(t.longitude) and distance_km((lat,lon),(float(t.latitude),float(t.longitude)))<=0.05:
    item={'source_kind':'tochno_exact_locality_alias','latitude':lat,'longitude':lon,'source_path':str(TOCHNO),'source_sha256':sha(TOCHNO),'source_url':'','source_qid':'','source_locator':f"file_row_number={int(provider.file_row_number)} (0-based); settlement_dadata={provider.settlement_dadata}; settlement_type_full_dadata={provider.settlement_type_full_dadata}; region={provider.region}; object_level={provider.object_level}; fias_level_dadata={provider.fias_level_dadata}; qc_geo_dadata={provider.qc_geo_dadata}; oktmo={provider.oktmo}"}
   else: held['provider_coordinate_not_within_50m_selected_2021']+=1
  qid=QIDS.get((normalize(name),normalize(region)))
  if item is None and qid:
   e=entity.get(qid); desc=e.get('descriptions',{}).get('ru',{}).get('value','') if e else ''
   region_words=normalize(region).split();region_stem=(region_words[1] if region_words[0] in {'республика','край'} and len(region_words)>1 else region_words[0])[:5]
   district_stem=normalize(district if (district:=str(t.district_raw)) else '').split()[0][:6]
   # Russian case endings differ between the selected census row and Wikidata
   # descriptions; compare stable stems while requiring both region and county.
   if e and normalize(e.get('labels',{}).get('ru',{}).get('value','')) in aliases0 and region_stem in normalize(desc) and district_stem in normalize(desc):
    claims=e.get('claims',{}).get('P625',[]);pts=[]
    for c in claims:
     v=c.get('mainsnak',{}).get('datavalue',{}).get('value',{})
     if v.get('globe')=='http://www.wikidata.org/entity/Q2':
      d=distance_km((float(v['latitude']),float(v['longitude'])),(float(t.latitude),float(t.longitude))) if pd.notna(t.latitude) and pd.notna(t.longitude) else 0
      if d<=5:pts.append((d,c,v))
    if pts:
     _,c,v=min(pts,key=lambda x:x[0]);item={'source_kind':'wikidata_named_locality_P625','latitude':float(v['latitude']),'longitude':float(v['longitude']),'source_path':str(ENTITY),'source_sha256':sha(ENTITY),'source_url':f'https://www.wikidata.org/wiki/{qid}','source_qid':qid,'source_locator':f"entity={qid}; label={e['labels']['ru']['value']}; description={desc}; claims.P625 statement_id={c['id']}; nearest P625 to selected 2021 coordinate <=5 km"}
  if item is None:
   held['no_simple_exact_source_point']+=1;continue
  item.update(rank=rank,mass=mass,root=root,group=g,current=cur,selected=t)
  candidates.append(item)
  if len(candidates)>=30:break
 if len(candidates)<30: raise RuntimeError(f'Only {len(candidates)} simple source points found for ranked full chains; held={dict(held)}')
 output=[];context=[]
 for item in candidates:
  g=item['group'];cur=item['current'];t=item['selected'];name=str(t.settlement_name);region=str(t.region_raw);district=str(t.district_raw)
  for _,r in g.sort_values('census_year').iterrows():
   y=int(r.census_year);direct=y==2021
   origin=(f"Direct named locality point from {item['source_kind']}; selected 2021 record context: {name}, {region}, {district}; no external provider identifier binding asserted." if direct else f"Retrospective spatial continuity inference from the reviewed 2021 named-locality point across the already accepted full same_place chain ({name}, {region}); old census source record receives a modern point and no historical point measurement is claimed.")
   output.append({'target_source_record_id':str(r.source_record_id),'target_year':y,'latitude':item['latitude'],'longitude':item['longitude'],'source':item['source_path'],'source_sha256':item['source_sha256'],'source_url':item['source_url'],'source_qid':item['source_qid'],'source_locator':item['source_locator'],'coordinate_source_record_id':str(cur.source_record_id),'coordinate_admission_status':'reviewed_case_accepted','coordinate_quality':'named_locality_point_current_2021' if direct else 'retrospective_full_chain_spatial_continuity','provider_binding_asserted':False,'provider_binding_separate':True,'coordinate_origin_kind':'direct_named_locality_point' if direct else 'accepted_same_place_spatial_continuity_inference','retrospective_old_record_id':not direct,'origin':origin})
  context.append({'rank_by_three_year_population':item['rank'],'population_sum_2002_2010_2021':item['mass'],'target_name_2021':name,'target_type_2021':str(t.settlement_type),'region_2021':region,'district_2021':district,'oktmo_2021':str(t.oktmo),'okato_2021':str(t.okato),'selected_2021_latitude':t.latitude,'selected_2021_longitude':t.longitude,'selected_2021_source_record_id':str(cur.source_record_id),'source_record_ids_2002_2010_2021':' | '.join(g.sort_values('census_year').source_record_id.astype(str)),'point_source_kind':item['source_kind'],'point_latitude':item['latitude'],'point_longitude':item['longitude'],'source_path':item['source_path'],'source_sha256':item['source_sha256'],'source_url':item['source_url'],'source_qid':item['source_qid'],'source_locator':item['source_locator'],'provider_binding_asserted':False,'provider_binding_separate':True})
 frame=pd.DataFrame(output);ctx=pd.DataFrame(context)
 if len(frame)!=90 or frame.target_source_record_id.duplicated().any():raise RuntimeError('Expected 30 components / 90 distinct target rows')
 if not frame.provider_binding_asserted.eq(False).all() or not frame.latitude.between(-90,90).all() or not frame.longitude.between(-180,180).all():raise RuntimeError('Invalid point provenance or coordinates')
 frame.to_csv(CSV,index=False);ctx.to_csv(CONTEXT,index=False)
 after=state.metrics(extra_point_ids=frame.target_source_record_id.astype(str).tolist())
 graph_inputs={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in state.inputs}
 receipt={'status':'staged_top30_point_use_batch_for_existing_accepted_full_chains','components':30,'point_use_rows':len(frame),'point_rows_by_source_kind':dict(Counter(x['source_kind'] for x in candidates)),'ranked_components':[{k:c[k] for k in ['rank','mass','source_kind','source_qid','source_locator']} for c in candidates],'accepted_graph_inputs':graph_inputs,'source_inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SELECTED,TOCHNO,ENTITY]},'source_context_csv_sha256':sha(CONTEXT),'point_use_csv_sha256':sha(CSV),'build_script_sha256':sha(Path(__file__)),'provider_binding_asserted':False,'provider_binding_separate':True,'coverage_before':baseline,'coverage_after_staged_batch':after,'coverage_population_delta':{y:after[y]['covered_population']-baseline[y]['covered_population'] for y in baseline},'rules':{'rank':'sum selected population from 2002, 2010, 2021, ranked descending among full three-year components with exactly one row per year, stable name/type/region, and no accepted point in current State','provider':'exact locality alias (only stripped station-introduction phrases), exact normalized region, exact selected OKTMO, object_level=Населенный пункт, FIAS level 6, QC geo 3, source type compatible with selected locality type, unique record, and within 50 m of selected 2021 raw coordinate; provider binding remains separate and unasserted','wikidata':'explicit QID-to-target mapping; exact Russian label/recognized station alias; description names matching region and county; P625 globe Earth; nearest P625 selected within 5 km of selected 2021 row; provider binding remains separate and unasserted','old_years':'2021 current point reused over already accepted same_place identity as retrospective spatial continuity inference; no historical point measurement claimed'}}
 RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'components':len(candidates),'rows':len(frame),'sources':dict(Counter(x['source_kind'] for x in candidates)),'gains':receipt['coverage_population_delta'],'csv':sha(CSV),'context':sha(CONTEXT)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

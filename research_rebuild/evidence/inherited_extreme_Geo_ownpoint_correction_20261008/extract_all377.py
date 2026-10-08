from pathlib import Path
import sys,json,hashlib,time
import numpy as np,pandas as pd
ROOT=Path('/workspace/russian-settlements-research');E=ROOT/'research_rebuild/evidence';O=E/'working_full_chain_20261007';sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'));sys.path.insert(0,str(O))
start=time.monotonic();loader=ROOT/'research_rebuild/mass_linkage/working_state_20261007.py';code_sha=hashlib.sha256(loader.read_bytes()).hexdigest()
from working_state_20261007 import load
from replay_additional_native_20261008 import finite
s=load(58);expected={'histories':141106,'populations_by_year':{'2002':126915601,'2010':124056022,'2021':124679751}};assert finite(s)==expected
obs=s.obs;bad=~obs.source_record_id.isin(s.point_rows)|~np.isfinite(obs.population);badroots=set(obs.loc[bad,'root'])|{s.uf.find(x) for x in s.conflicting_point_targets};ordinary=obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~(obs.census_year.eq(2021)&obs.region_norm.eq('крым'));roots={r for r in set(obs.loc[ordinary,'root']) if s.years[r]=={2002,2010,2021} and r not in badroots};d=obs[ordinary&obs.root.isin(roots)].copy();assert len(roots)==141106;assert not d[['root','census_year']].duplicated().any();assert len(d)==3*len(roots)
base=pd.DataFrame(index=sorted(roots));base.index.name='component_root';pairs=[(2002,2010),(2002,2021),(2010,2021)]
for y in [2002,2010,2021]:
 f=d[d.census_year.eq(y)].set_index('root').reindex(base.index)
 for field in ['source_record_id','settlement_name','settlement_type','region_norm','population']:base[field+'_'+str(y)]=f[field].values
 points=[s.point_rows[x] for x in f.source_record_id]
 for field in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_admission_status','coordinate_source_record_id']:
  base[field+'_'+str(y)]=[p.get(field,'') for p in points]
for a,b in pairs:
 lat1=np.radians(base['latitude_'+str(a)].astype(float));lat2=np.radians(base['latitude_'+str(b)].astype(float));lon1=np.radians(base['longitude_'+str(a)].astype(float));lon2=np.radians(base['longitude_'+str(b)].astype(float));h=np.sin((lat2-lat1)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2; base[f'distance_km_{a}_{b}']=6371.0088*2*np.arcsin(np.sqrt(np.clip(h,0,1)))
cols=[f'distance_km_{a}_{b}' for a,b in pairs];base['max_interyear_distance_km']=base[cols].max(axis=1);base['max_pair']=base[cols].idxmax(axis=1);base=base.sort_values(['max_interyear_distance_km','source_record_id_2021'],ascending=[False,True]);base['rank_max_interyear_distance']=np.arange(1,len(base)+1)
selected=base[base.max_interyear_distance_km.gt(100)].reset_index(); assert len(selected)==377
Z=E/'inherited_extreme_Geo_ownpoint_correction_20261008';selected.to_csv(Z/'all377_extreme_histories.csv',index=False)
ids=set(selected['source_record_id_2002'])|set(selected['source_record_id_2010'])|set(selected['source_record_id_2021'])
(Z/'active_extreme_point_claims.json').write_text(json.dumps({sid:s.point_rows[sid] for sid in ids},ensure_ascii=False,default=str))
s.obs[s.obs.source_record_id.isin(ids)].to_csv(Z/'native_extreme_observations.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(Z/'source_state58_input_pins.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in s.inputs},indent=2))
print(json.dumps({'histories':len(selected),'populations':{str(y):int(selected['population_'+str(y)].sum()) for y in [2002,2010,2021]},'point_origin2021_counts':selected.point_origin_kind_2021.value_counts().to_dict(),'old_Geo_points':sum('geokladr' in str(p).lower() for y in [2002,2010] for p in selected['point_origin_file_'+str(y)])},ensure_ascii=False),flush=True)

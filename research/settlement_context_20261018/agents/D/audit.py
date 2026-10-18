#!/usr/bin/env python3
"""Independent CSV audit; no import of production builders or pickle; no source mutations."""
from pathlib import Path
import sys, hashlib, json, platform, subprocess
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
P=ROOT/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
x=pd.read_csv(P,dtype=str,keep_default_na=False)
assert sha(P)=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
assert x.shape==(142570,135)
n=len(x);years=[2002,2010,2021];p={y:pd.to_numeric(x[f'population_{y}'],errors='coerce') for y in years}
coord={y:(pd.to_numeric(x[f'latitude_{y}'],errors='coerce'),pd.to_numeric(x[f'longitude_{y}'],errors='coerce')) for y in years}
valid={y:a.between(-90,90)&b.between(-180,180) for y,(a,b) in coord.items()}
contract={'status':'computed','audit_script_sha256':sha(__file__),'input':str(P.relative_to(ROOT)),'input_sha256':sha(P),'shape':list(x.shape),'entity_uid_unique':bool(x.entity_uid.is_unique),'entity_uid_missing':int(x.entity_uid.eq('').sum()),'code_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'seed':None,'population':{},'coordinates':{},'scope':'balanced accepted ordinary same-place panel; not national census universe','boundary_comparability':'not established by identity; no universal verified-comparable flag available'}
schema=[]
for c in x:
 v=x[c];num=pd.to_numeric(v,errors='coerce')
 schema.append({'column':c,'missing':int(v.eq('').sum()),'distinct':int(v.nunique()),'numeric_nonmissing':int(num.notna().sum())})
pd.DataFrame(schema).to_csv(OUT/'evidence/schema.csv',index=False)
for y in years:
 q=p[y];a,b=coord[y]
 contract['population'][str(y)]={'numeric':int(q.notna().sum()),'sum':float(q.sum()),'zeros':int(q.eq(0).sum()),'positive':int(q.gt(0).sum()),'negative':int(q.lt(0).sum()),'noninteger':int((q.notna()&(q%1!=0)).sum())}
 contract['coordinates'][str(y)]={'valid_geographic_range':int(valid[y].sum()),'missing':int((a.isna()|b.isna()).sum()),'zero_zero':int((a.eq(0)&b.eq(0)).sum()),'duplicate_coordinate_rows':int(pd.DataFrame({'a':a,'b':b}).duplicated(keep=False).sum()),'historical_measurement_asserted_true':int(x[f'historical_measurement_asserted_{y}'].str.lower().eq('true').sum())}
 for stem in ['population_value_quality','coordinate_admission_status','point_origin_kind','point_origin_resolution_status','source_actual_resolution_status','region_interpretation_status']:
  x[f'{stem}_{y}'].replace('','<MISSING>').value_counts().rename_axis('value').reset_index(name='n').to_csv(OUT/f'evidence/{stem}_{y}.csv',index=False)
# Original population only populated on overlaid records; reconstruct sensitivity without replacing selected main data.
o=pd.to_numeric(x.original_population_2010,errors='coerce');overlay=x.population_source_application_status_2010.ne('')
restored=p[2010].copy();restored.loc[overlay]=o.loc[overlay]
contract['original_2010']={'populated_original':int(o.notna().sum()),'overlay_records':int(overlay.sum()),'overlay_original_missing':int((overlay&o.isna()).sum()),'selected_sum_overlay':float(p[2010][overlay].sum()),'original_sum_overlay':float(o[overlay].sum()),'selected_diff_original':float((p[2010][overlay]-o[overlay]).sum()),'restored_sum_with_missing_preserved':float(restored.sum()),'restored_numeric':int(restored.notna().sum())}
# Risk manifests retain IDs, all outcomes and flags; no quality exclusion.
c=x[['entity_uid','effective_region_norm_2010','settlement_type_2010','population_value_quality_2010']].copy()
for y in years:c[f'population_{y}']=p[y];c[f'coord_valid_{y}']=valid[y]
for a,b in [(2002,2010),(2010,2021)]:
 c[f'risk_zero_{b}']=p[a].gt(0)&p[b].notna();c[f'zero_event_{b}']=c[f'risk_zero_{b}']&p[b].eq(0)
 c[f'risk_repopulation_{b}']=p[a].eq(0)&p[b].notna();c[f'repopulation_event_{b}']=c[f'risk_repopulation_{b}']&p[b].gt(0)
# Haversine coordinate drift. Coincident coordinates across identities need sensitivity, not arbitrary dedup.
maxdrift=np.zeros(n)
for a,b in [(2002,2010),(2010,2021),(2002,2021)]:
 la,lo=coord[a];lb,lob=coord[b];r=np.pi/180
 h=np.sin((lb-la)*r/2)**2+np.cos(la*r)*np.cos(lb*r)*np.sin((lob-lo)*r/2)**2
 dist=6371.0088*2*np.arcsin(np.sqrt(np.clip(h,0,1)))
 c[f'point_drift_{a}_{b}_km']=dist
 maxdrift=np.maximum(maxdrift,dist.fillna(np.inf))
c['max_point_drift_km']=maxdrift
c['cross_year_region_change']=(x.effective_region_norm_2002!=x.effective_region_norm_2010)|(x.effective_region_norm_2010!=x.effective_region_norm_2021)
c['cross_year_type_change']=(x.settlement_type_2002!=x.settlement_type_2010)|(x.settlement_type_2010!=x.settlement_type_2021)
c['boundary_verification_status']='unknown_not_inferred_from_identity'
c.to_csv(OUT/'cohorts/panel_audit.csv.gz',index=False)
contract['coordinate_drift']={'max_km':float(maxdrift.max()),'gt_1km':int((maxdrift>1).sum()),'gt_5km':int((maxdrift>5).sum()),'gt_100km':int((maxdrift>100).sum())}
contract['region_change_n']=int(c.cross_year_region_change.sum());contract['type_change_n']=int(c.cross_year_type_change.sum())
contract['risk_sets']={col:int(c[col].sum()) for col in c if col.startswith(('risk_','zero_event','repopulation_event'))}
c.loc[c.max_point_drift_km>5].to_csv(OUT/'evidence/point_drift_over5km.csv',index=False)
ex=pd.DataFrame({'entity_uid':x.entity_uid,'excluded_from_master':False,'excluded_from_numeric2010':p[2010].isna(),'reason':np.where(p[2010].isna(),'population_2010_not_numeric','retained')})
ex.to_csv(OUT/'evidence/exclusion_log.csv.gz',index=False)
# Strata and cross-tabulations, including missing categories.
c['baseline_size']=pd.cut(p[2010],[-np.inf,0,10,100,1000,10000,100000,np.inf],labels=['zero','1-10','11-100','101-1000','1001-10000','10001-100000','>100000']).astype(str)
for key in ['effective_region_norm_2010','settlement_type_2010','population_value_quality_2010','baseline_size']:
 g=c.groupby(key,dropna=False).agg(n=('entity_uid','size'),pop2002=('population_2002','sum'),pop2010=('population_2010','sum'),pop2021=('population_2021','sum'),risk_zero2010=('risk_zero_2010','sum'),zero2010=('zero_event_2010','sum'),risk_zero2021=('risk_zero_2021','sum'),zero2021=('zero_event_2021','sum'),risk_return2021=('risk_repopulation_2021','sum'),return2021=('repopulation_event_2021','sum'))
 g.to_csv(OUT/f'cohorts/by_{key}.csv')
fpath=ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv';f=pd.read_csv(fpath)
contract['federal']={'input_sha256':sha(fpath),'rows':len(f),'sum_by_year':{str(k):int(v) for k,v in f.groupby('census_year').territory_population.sum().items()},'ordinary_federal_region_rows':int(x.effective_region_norm_2010.isin(['москва','санкт петербург']).sum()),'policy':'Do not add territory masses to ordinary children. External center anchor allowed only as explicitly approximate territorial sensitivity, never exact circular allocation. Main ordinary analysis must state federal external-center limitation.'}
# Raw flags are assertions, including explicit False; count exact key/value, not keyword positivity.
flags=[]
for y in years:
 for s,count in x[f'point_use_raw_flags_json_{y}'].value_counts().items():
  try:d=json.loads(s)
  except Exception:d={'parse_error':s}
  for k,v in d.items():flags.append({'year':y,'key':k,'value':str(v),'n':int(count)})
if flags:pd.DataFrame(flags).groupby(['year','key','value'],as_index=False).n.sum().to_csv(OUT/'evidence/point_raw_flags.csv',index=False)
(OUT/'evidence/data_contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2))
print(json.dumps(contract,ensure_ascii=False,indent=2))

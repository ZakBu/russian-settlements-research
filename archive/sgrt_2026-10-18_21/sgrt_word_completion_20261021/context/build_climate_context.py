#!/usr/bin/env python3
"""Extract actual published climate rasters; distinguish climatic normal and daily SAT proxy."""
from pathlib import Path
import calendar,hashlib,json
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2];RAW=Path('/workspace/scratch/sgrt_context_completion')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def extract(path,lon,lat):
 with rasterio.open(path) as src:
  finite=np.isfinite(lon)&np.isfinite(lat);rr=np.full(len(lon),-1,int);cc=rr.copy();r,c=rasterio.transform.rowcol(src.transform,lon[finite],lat[finite]);rr[finite]=r;cc[finite]=c
  value=np.full(len(lon),np.nan);valid=(rr>=0)&(cc>=0)&(rr<src.height)&(cc<src.width)
  # Read each physical block once, not once per settlement.
  bh,bw=src.block_shapes[0];keys=(rr//bh)*(int(np.ceil(src.width/bw)))+cc//bw
  for key in np.unique(keys[valid]):
   ix=np.flatnonzero(valid&(keys==key));br=int(rr[ix[0]]//bh)*bh;bc=int(cc[ix[0]]//bw)*bw
   block=src.read(1,window=Window(bc,br,min(bw,src.width-bc),min(bh,src.height-br)),masked=True)
   v=block[rr[ix]-br,cc[ix]-bc];value[ix]=v.filled(np.nan) if np.ma.isMaskedArray(v) and np.issubdtype(v.dtype,np.floating) else np.where(np.ma.getmaskarray(v),np.nan,v.data)
  meta={'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path),'shape':[src.height,src.width],'resolution_degrees':list(src.res),'crs':str(src.crs),'nodata':src.nodata}
  return value,meta

def run():
 d=pd.read_parquet(REPO/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',columns=['id','lat','lon']);assert len(d)>=142570 and d.id.is_unique
 features=d[['id']].copy();months=[];meta=[]
 for month in range(1,13):
  tv,tm=extract(RAW/f'wc2.1_10m_tavg_{month:02d}.tif',d.lon.values,d.lat.values);pv,pm=extract(RAW/f'wc2.1_10m_prec_{month:02d}.tif',d.lon.values,d.lat.values)
  features[f'climate_tavg_normal_month{month:02d}_c']=tv;features[f'climate_prec_normal_month{month:02d}_mm']=pv;months.append(tv);meta.extend([tm,pm])
 temperatures=np.column_stack(months);days=np.array([calendar.monthrange(2001,m)[1] for m in range(1,13)])
 features['climate_annual_mean_temperature_c']=np.sum(temperatures*days,axis=1)/365
 features['climate_annual_precipitation_mm']=features.filter(regex='climate_prec_normal_month').sum(axis=1,min_count=12)
 features['climate_monthly_approx_active_temperature_sum_above10_cday']=np.sum(np.where(temperatures>10,temperatures,0)*days,axis=1)
 features['climate_monthly_approx_growing_degree_days_base10_cday']=np.sum(np.maximum(temperatures-10,0)*days,axis=1)
 features.loc[np.isnan(temperatures).any(axis=1),['climate_monthly_approx_active_temperature_sum_above10_cday','climate_monthly_approx_growing_degree_days_base10_cday']]=np.nan
 ai,am=extract(RAW/'Global-AI_ET0__annual_v3_1/ai_v31_yr.tif',d.lon.values,d.lat.values);et,em=extract(RAW/'Global-AI_ET0__annual_v3_1/et0_v31_yr.tif',d.lon.values,d.lat.values);meta.extend([am,em])
 features['climate_global_ai_v31_precipitation_over_et0']=np.where(np.isfinite(et)&(ai>0),ai*.0001,np.nan)
 features['climate_global_ai_integer_saturation']=pd.Series(ai==65535,dtype='boolean').mask(~np.isfinite(ai))
 features['climate_global_et0_v31_annual_mm']=et
 features['climate_normal_period']='1970-2000';features['climate_word_daily_sat_observed']=False;features['climate_bonitet_observed']=False
 features.to_parquet(ROOT/'climate_settlement_features.parquet',index=False)
 coverage=[dict(feature=c,nonnull=int(features[c].notna().sum()),unknown=int(features[c].isna().sum())) for c in features if c!='id'];pd.DataFrame(coverage).to_csv(ROOT/'climate_coverage.csv',index=False)
 receipt={'status':'ACTUALLY_EXTRACTED','rows':len(features),'unique_id':features.id.nunique(),'raster_sources':meta,'normal_period':'1970-2000','worldclim_resolution':'10arcmin','aridity_resolution':'30arcsec','ai_scale_factor':.0001,'climate_meaning':'spatial_climatic_context_not_2010or2021weather','active_temperature_sum':'monthly_mean_approximation_not_daily_observed_SAT','soil_bonitet':'not_obtained','coverage':coverage}
 (ROOT/'climate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False));print('CLIMATE',len(features),features.climate_global_ai_v31_precipitation_over_et0.notna().sum(),features.climate_annual_mean_temperature_c.notna().sum())
if __name__=='__main__':run()

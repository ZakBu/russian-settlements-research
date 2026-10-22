#!/usr/bin/env python3
"""Add FAO GAEZ published daily-derived SAT normal; no monthly approximation."""
from build_climate_context import ROOT,REPO,RAW,extract
import pandas as pd,json,numpy as np

def run():
 axis=pd.read_parquet(REPO/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',columns=['id','lat','lon'])
 d=pd.read_parquet(ROOT/'climate_settlement_features.parquet');assert d.id.equals(axis.id)
 meta=[]
 for file,col,scale in [('ts3_CRUTS32_Hist_8110.tif','climate_gaez_sat_above10_cday_1981_2010',1),('riS_CRUTS32_Hist_8110.tif','climate_gaez_summer_precipitation_over_pet_1981_2010',.01)]:
  v,m=extract(RAW/file,axis.lon.values,axis.lat.values);d[col]=v*scale;m['output_feature']=col;m['scale_factor']=scale;meta.append(m)
 d['climate_daily_derived_sat_source_available']=d.climate_gaez_sat_above10_cday_1981_2010.notna().astype('boolean').mask(axis.lat.isna()|axis.lon.isna())
 d.to_parquet(ROOT/'climate_settlement_features.parquet',index=False)
 coverage=[dict(feature=c,nonnull=int(d[c].notna().sum()),unknown=int(d[c].isna().sum())) for c in d if c!='id'];pd.DataFrame(coverage).to_csv(ROOT/'climate_coverage.csv',index=False)
 receipt=json.loads((ROOT/'climate_receipt.json').read_text());receipt['raster_sources']=[m for m in receipt['raster_sources'] if not m['file'].endswith('_Hist_8110.tif')]+meta;receipt['coverage']=coverage
 receipt['active_temperature_sum']='Primary FAO GAEZv4 CRUTS32 historical1981-2010 published annual temperature sum for days with Ta>10C, degree-days,5arcmin; exact requested variable, climatic normal derived from climate model data, not station daily observations. Legacy monthly approximation retained with explicit name.'
 receipt['gaez_summer_moisture']='GAEZ riS seasonal P/PET*100, April-September in Northern Hemisphere; output divided100;1981-2010 normal. Annual GlobalAI uses different1970-2000 normal and must not be treated as same-date weather.'
 (ROOT/'climate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(d[['climate_gaez_sat_above10_cday_1981_2010','climate_gaez_summer_precipitation_over_pet_1981_2010']].describe().to_string())
if __name__=='__main__':run()

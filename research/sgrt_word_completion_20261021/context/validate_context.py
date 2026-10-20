#!/usr/bin/env python3
"""Independent semantic and join checks against source rows and raster cells."""
from pathlib import Path
import pandas as pd,numpy as np,json,rasterio
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2];RAW=Path('/workspace/scratch/sgrt_context_completion')
def run():
 axis=pd.read_parquet(REPO/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',columns=['id','lat','lon']);checks={}
 for name in ['climate','municipal','soil']:
  x=pd.read_parquet(ROOT/f'{name}_settlement_features.parquet');assert x.id.equals(axis.id) and x.id.is_unique;checks[name+'_axis_rows']=len(x)
 c=pd.read_parquet(ROOT/'climate_settlement_features.parquet');s=pd.read_parquet(ROOT/'soil_settlement_features.parquet');m=pd.read_parquet(ROOT/'municipal_settlement_features.parquet');w=pd.read_parquet(ROOT/'municipal_annual_wide.parquet');source=pd.read_parquet(ROOT/'municipal_annual_context.parquet')
 missing=axis.lat.isna()|axis.lon.isna()
 assert c.loc[missing,'climate_gaez_sat_above10_cday_1981_2010'].isna().all()
 assert s.loc[missing,s.columns.str.endswith('_rating_lower')].isna().all().all()
 assert s.soil_russian_bonitet_score.isna().all()
 assert source.loc[source.conflicting_values|source.ambiguous_multiple_raw_codes,'value'].isna().all()
 assert m.context_migration_increase_2010.isna().all()
 assert m.context_sown_share_of_farmland_usable_2021.isna().all()
 assert not m.agro_high_productivity_evidence.dtype==bool
 d=w[w.natural_increase_derived_from_births_minus_deaths]
 assert np.allclose(d.natural_increase,d.births-d.deaths)
 d=w[w.municipal_population_annual_mean_endpoints.notna()]
 assert d.municipal_population_jan1_raw_code.eq(d.municipal_population_jan1_nextyear_raw_code).all()
 assert np.allclose(d.municipal_population_annual_mean_endpoints,(d.municipal_population_jan1+d.municipal_population_jan1_nextyear)/2)
 d=w[w.sown_share_of_farmland_usable.notna()]
 assert d.sown_share_of_farmland_usable.between(0,1).all()
 for file,col,scale in [('ts3_CRUTS32_Hist_8110.tif','climate_gaez_sat_above10_cday_1981_2010',1),('riS_CRUTS32_Hist_8110.tif','climate_gaez_summer_precipitation_over_pet_1981_2010',.01)]:
  ix=c[c[col].notna()].sample(100,random_state=177).index
  with rasterio.open(RAW/file) as src:
   values=np.array([v[0] for v in src.sample(list(zip(axis.loc[ix,'lon'],axis.loc[ix,'lat'])))])*scale
   assert np.allclose(values,c.loc[ix,col])
 checks.update(status='PASS',unknown_coordinate_rows=int(missing.sum()),migration2010_nonnull=0,gaez_sat_nonnull=int(c.climate_gaez_sat_above10_cday_1981_2010.notna().sum()),municipal2021_natural_rate_nonnull=int(m.context_natural_increase_per1000_2021.notna().sum()),municipal2010_natural_rate_nonnull=int(m.context_natural_increase_per1000_2010.notna().sum()),farmland_sown2008_strict_nonnull=int(m.context_sown_share_of_farmland_usable_2008.notna().sum()),farmland_sown2008_source_harmonized_nonnull=int(m.context_sown_share_of_farmland_source_harmonized_usable_2008.notna().sum()),soil_nutrient_rating_nonnull=int(s.soil_gaez_low_input_nutrient_availability_class_rating_lower.notna().sum()),raster_direct_samples_verified=200)
 (ROOT/'validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));print(json.dumps(checks,ensure_ascii=False,indent=2))
if __name__=='__main__':run()

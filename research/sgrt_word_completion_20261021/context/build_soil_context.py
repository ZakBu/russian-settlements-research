#!/usr/bin/env python3
"""Actual FAO soil quality classes, explicitly distinct from Russian soil bonitet."""
from build_climate_context import ROOT,REPO,RAW,extract,sha
import requests,json,pandas as pd,numpy as np,rasterio,base64,io
from PIL import Image

def run():
 catalog=json.loads((ROOT/'gaez_soil_catalog.json').read_text());axis=pd.read_parquet(REPO/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',columns=['id','lat','lon']);d=axis[['id']].copy();meta=[]
 legend=json.loads((ROOT/'gaez_soil_legend.json').read_text());colors={}
 for layer in legend['layers']:
  for x in layer['legend']:
   im=Image.open(io.BytesIO(base64.b64decode(x['imageData']))).convert('RGB');colors[im.getpixel((im.width//2,im.height//2))]=x['label']
 names={'SQ0_mze_v9aL':'most_limiting_rating','SQ1_mze_v9aL':'nutrient_availability','SQ3_mze_v9aL':'rooting_conditions','SQ4_mze_v9aL':'oxygen_availability_to_roots','SQ5_mze_v9aL':'salinity_sodicity','SQ6_mze_v9aL':'lime_gypsum','SQ7_mze_v9aL':'workability'}
 for item in catalog['features']:
  a=item['attributes'];name=a['Name']
  if name not in names:continue
  p=RAW/(name+'.tif')
  if not p.exists():
   with requests.get(a['download_url'],timeout=90) as r:r.raise_for_status();p.write_bytes(r.content)
  values,m=extract(p,axis.lon.values,axis.lat.values);col='soil_gaez_low_input_'+names[name]+'_class';d[col]=values
  with rasterio.open(p) as src:palette=src.colormap(1)
  labels={code:colors[rgb[:3]] for code,rgb in palette.items() if rgb[:3] in colors and code<14};assert set(range(14)).issubset(labels),labels
  d[col+'_label']=d[col].map(labels).astype('string')
  for side in ['lower','upper']:
   bound={code:float(label.split(' - ')[0 if side=='lower' else 1]) for code,label in labels.items() if ' - ' in label}
   d[col+'_rating_'+side]=d[col].map(bound)
  m.update(source_metadata=a,feature=col,observed_values=sorted(np.unique(values[np.isfinite(values)]).tolist()),class_label_from_matching_TIFF_palette_to_FAO_legend=labels);meta.append(m);print(name,p.stat().st_size,d[col+'_rating_lower'].notna().sum(),flush=True)
 d['soil_russian_bonitet_score']=np.nan
 d.to_parquet(ROOT/'soil_settlement_features.parquet',index=False)
 receipt={'status':'ACTUALLY_EXTRACTED','axis_rows':len(d),'sources':meta,'interpretation':'FAO GAEZv4 published soil-quality rating classes for low-input maize parameterization, HWSD-based; neither Russian bonitet nor measured soil productivity. Class labels/bounds decoded by exact TIFF palette RGB to primary FAO legend PNG matching, not assumed class ranking. Codes0NA,11permafrost,12not evaluated,13water retained raw but haveNULLrating. No time series/date claim: source year=n.a.','russian_bonitet':'NationalSoilAtlas class map exists as unreferenced JPG1:30M; quantitative spatial assignment not validated; all scoresNULL','coverage':{c:int(d[c].notna().sum()) for c in d if c!='id'}}
 (ROOT/'soil_context_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()

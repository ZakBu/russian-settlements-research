#!/usr/bin/env python3
"""Structural/source checks, not a scientific acceptance test for the digitization."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd,rasterio
from PIL import Image
ROOT=Path(__file__).resolve().parent
axis=ROOT.parent/'axis/full_settlement_axis.parquet'
f=pd.read_parquet(ROOT/'experimental_bonitet_settlement_intervals.parquet')
a=pd.read_parquet(axis,columns=['id','lat','lon']);r=json.loads((ROOT/'recovery_receipt.json').read_text())
assert f.id.is_unique and f.id.tolist()==a.id.tolist()
assert hashlib.sha256(axis.read_bytes()).hexdigest()==r['axis_sha256']
lo='soil_bonitet_atlas_experimental_interval_lower';hi='soil_bonitet_atlas_experimental_interval_upper'
assert f[lo].notna().equals(f[hi].notna())
accepted=f[lo].notna();assert int(accepted.sum())==20559
assert not f.soil_bonitet_atlas_scientifically_adopted.any()
assert not f.soil_bonitet_atlas_is_direct_settlement_soil_measurement.any()
assert f.loc[a.lat.isna()|a.lon.isna(),lo].isna().all()
assert f.loc[f.soil_bonitet_atlas_status.eq('outside_control_hull_no_extrapolation'),lo].isna().all()
valid_intervals={(i,i+10) for i in range(0,120,10)}|{(120,125)}
assert set(zip(f.loc[accepted,lo],f.loc[accepted,hi]))<=valid_intervals
controls=pd.read_csv(ROOT/'control_points_linked.csv');h=pd.read_csv(ROOT/'heldout_georeference_errors.csv')
assert len(controls)==45 and controls.name.is_unique and len(h)==12
assert set(h.name)==set(controls.loc[controls.role.eq('holdout'),'name'])
assert np.allclose(h.error_pixels,np.hypot(h.pixel_x-h.predicted_pixel_x,h.pixel_y-h.predicted_pixel_y))
source=ROOT/'sources/atlas_240_241_3600x2400.jpg';im=np.asarray(Image.open(source).convert('RGB'));assert im.shape==(2400,3600,3)
assert hashlib.sha256(source.read_bytes()).hexdigest()==r['source_sha256']
legend=pd.read_csv(ROOT/'legend_intervals.csv');assert len(legend)==13
for row in legend.itertuples():
    v=np.median(im[row.legend_sample_y-3:row.legend_sample_y+4,2588:2600].reshape(-1,3),axis=0)
    assert np.allclose(v,[row.red,row.green,row.blue])
with rasterio.open(ROOT/'experimental_bonitet_intervals_25km.tif') as src:
    assert src.crs.to_epsg()==3576 and src.count==2 and src.res==(25000,25000)
    x=src.read();known=x[0]!=src.nodata
    assert np.array_equal(known,x[1]!=src.nodata)
    assert set(zip(x[0][known],x[1][known]))<=valid_intervals
receipt={'status':'PASS_STRUCTURAL_AND_SOURCE_CONTROLS_ONLY','scientific_adoption':False,'rows':len(f),'experimental_interval_rows':int(accepted.sum()),'source_and_axis_sha256_verified':True,'unlocated_and_extrapolation_withheld':True,'legend_samples_verified':13,'heldout_controls_preserved':12,'tiff_crs_and_interval_nodata_verified':True}
(ROOT/'validation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
manifest=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and '__pycache__' not in str(p) and p.name!='file_manifest.json':manifest.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(ROOT/'file_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))

#!/usr/bin/env python3
"""Read back every new observation through Rasterio's point-sampling API."""
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
import rasterio

H=Path(__file__).resolve().parent
B=H.parent
R=B.parent
RAW=Path('/workspace/scratch/sgrt_context_completion')
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4194304),b''):h.update(block)
    return h.hexdigest()

def run():
    receipt=json.loads((H/'context_extension_receipt.json').read_text())
    axis=pd.read_parquet(R/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet')
    add=pd.read_parquet(R/'data/source_controls_cycle05/federal_np2021_axis_addendum.parquet')
    obs=pd.read_parquet(H/'source_pixel_observations.parquet')
    assert len(obs)==11725 and not obs.duplicated(['id','feature']).any()
    outputs={}
    for family in ['climate','soil']:
        full=pd.read_parquet(H/(family+'_settlement_features.parquet'))
        old=pd.read_parquet(B/(family+'_settlement_features.parquet'))
        assert full.id.equals(axis.id)
        pd.testing.assert_frame_equal(full.set_index('id').loc[old.id].reset_index(),old,check_exact=True)
        outputs[family]=full.set_index('id').loc[add.id]
    checks=[]
    for metadata in receipt['raster_sources']:
        path=RAW/metadata['raw_relative_path']
        assert sha(path)==metadata['sha256']==metadata['accepted_old_receipt_sha256']
        rows=obs[obs.feature.eq(metadata['feature'])].set_index('id').loc[add.id]
        assert len(rows)==335
        with rasterio.open(path) as src:
            point=list(src.sample(list(zip(add.lon,add.lat)),indexes=1,masked=True))
            values=np.array([np.nan if np.ma.is_masked(v[0]) else float(v[0]) for v in point])
            np.testing.assert_array_equal(values,rows.source_raw_value.to_numpy())
            assert np.array_equal(np.isfinite(values),rows.source_valid.to_numpy())
            inv=~src.transform
            for i,(lon,lat) in enumerate(zip(add.lon,add.lat)):
                col,row=inv*(lon,lat)
                assert int(np.floor(row))==int(rows.source_row.iloc[i])
                assert int(np.floor(col))==int(rows.source_col.iloc[i])
                assert rows.source_pixel_id.iloc[i]==f'{metadata["sha256"]}:{int(np.floor(row))}:{int(np.floor(col))}'
            scaled=values*metadata['scale_factor']
            feature=metadata['feature']
            if feature=='climate_global_ai_v31_precipitation_over_et0':
                scaled=np.where(np.isfinite(outputs['climate'].climate_global_et0_v31_annual_mm)&(values>0),scaled,np.nan)
            family='soil' if feature.startswith('soil_') else 'climate'
            np.testing.assert_array_equal(scaled,outputs[family][feature].to_numpy())
        checks.append(dict(feature=metadata['feature'],point_sample_readbacks=335,valid=int(np.isfinite(values).sum()),pass_=True))
    assert outputs['soil'].soil_russian_bonitet_score.isna().all()
    before=receipt['source_sha256']
    assert all(sha(Path(p))==digest for p,digest in before.items())
    result=dict(status='PASS',all_source_point_samples_verified=11725,all_new_rows=335,
        preserved_old_rows_exactly=173527,full_axis_rows=173862,rasters=len(checks),checks=checks,
        original_sources_unchanged=True,context_receipt_sha256=sha(H/'context_extension_receipt.json'))
    (H/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({key:value for key,value in result.items() if key!='checks'},indent=2))

if __name__=='__main__':run()

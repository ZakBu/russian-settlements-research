#!/usr/bin/env python3
"""Sample accepted rasters at477 source-admitted coordinates; preserve all unaffected values."""
from pathlib import Path
import base64, calendar, hashlib, io, json
import zipfile
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from PIL import Image

H = Path(__file__).resolve().parent
BASE = H.parent
ROOT = BASE.parent
RAW = Path('/workspace/scratch/sgrt_context_completion')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()

def run():
    axis_path = ROOT/'source_geography_recovery_cycle07/nodes_coordinate_overlay.parquet'
    add_path = ROOT/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet'
    axis = pd.read_parquet(axis_path,columns=['id','lat','lon'])
    add = pd.read_parquet(add_path).rename(columns={'new_lat':'lat','new_lon':'lon'})
    oldc = pd.read_parquet(BASE/'cycle05_federal335/climate_settlement_features.parquet')
    olds = pd.read_parquet(BASE/'cycle05_federal335/soil_settlement_features.parquet')
    assert len(add) == 477 and axis.id.is_unique and add.id.is_unique
    assert oldc.id.equals(olds.id)
    assert set(oldc.id)<=set(axis.id) and set(add.id)<=set(oldc.id)
    axis=axis.set_index('id').loc[oldc.id].reset_index()
    assert set(add.id)<=set(oldc.id)
    assert np.isfinite(add[['lat','lon']].to_numpy()).all()
    source_paths = [axis_path, add_path, BASE/'cycle05_federal335/climate_settlement_features.parquet',
                    BASE/'cycle05_federal335/soil_settlement_features.parquet', BASE/'climate_receipt.json',
                    BASE/'soil_context_receipt.json', BASE/'gaez_soil_legend.json', RAW/'Global-AI_ET0__annual_v3_1.zip']
    before = {str(p):sha(p) for p in source_paths}
    cr = json.loads((BASE/'climate_receipt.json').read_text())
    sr = json.loads((BASE/'soil_context_receipt.json').read_text())
    accepted = {v['file']:v for v in cr['raster_sources'] + sr['sources']}
    samples = []
    raster_meta = []

    def sample(file, feature, scale=1., raw=False):
        path = RAW/file
        dataset_path=str(path)
        if path.exists():digest=sha(path);raster_file_bytes=path.stat().st_size
        else:
            archive=RAW/'Global-AI_ET0__annual_v3_1.zip';member=file;hh=hashlib.sha256()
            with zipfile.ZipFile(archive) as z, z.open(member) as stream:
                for block in iter(lambda:stream.read(4194304),b''):hh.update(block)
                raster_file_bytes=z.getinfo(member).file_size
            digest=hh.hexdigest();dataset_path='/vsizip/'+str(archive)+'/'+member
        assert digest == accepted[path.name]['sha256'], path
        values = np.full(len(add), np.nan)
        with rasterio.open(dataset_path) as src:
            assert src.crs.to_epsg() == 4326
            rr, cc = rasterio.transform.rowcol(src.transform, add.lon.to_numpy(), add.lat.to_numpy())
            rr, cc = np.asarray(rr), np.asarray(cc)
            valid = (rr>=0)&(cc>=0)&(rr<src.height)&(cc<src.width)
            bh,bw = src.block_shapes[0]
            for br,bc in sorted(set(zip((rr[valid]//bh)*bh,(cc[valid]//bw)*bw))):
                ix = np.flatnonzero(valid & (rr//bh == br//bh) & (cc//bw == bc//bw))
                block = src.read(1,window=Window(int(bc),int(br),min(bw,src.width-int(bc)),min(bh,src.height-int(br))),masked=True)
                pixel = block[rr[ix]-br, cc[ix]-bc]
                values[ix] = np.where(np.ma.getmaskarray(pixel),np.nan,pixel.data)
            # Independent physical one-pixel reads, all 477 per raster, bypass block selection.
            for i,row in enumerate(add.itertuples()):
                if valid[i]:
                    direct = src.read(1,window=Window(int(cc[i]),int(rr[i]),1,1),masked=True)
                    masked = bool(np.ma.getmaskarray(direct)[0,0])
                    observed = np.nan if masked else float(direct.data[0,0])
                    assert (np.isnan(observed) and np.isnan(values[i])) or observed == values[i]
                    x,y = rasterio.transform.xy(src.transform,int(rr[i]),int(cc[i]),offset='center')
                    reason = 'source_nodata_mask' if masked else 'valid_source_pixel'
                else:
                    masked=True;observed=np.nan;x=y=np.nan;reason='outside_source_grid'
                samples.append(dict(id=row.id,feature=feature,file=path.name,source_sha256=digest,
                    source_pixel_id=f'{digest}:{int(rr[i])}:{int(cc[i])}',source_row=int(rr[i]),source_col=int(cc[i]),
                    source_pixel_center_lon=x,source_pixel_center_lat=y,source_raw_value=observed,
                    source_valid=not masked,validity_reason=reason,scale_factor=scale,
                    scaled_source_value=values[i]*scale,input_lon=row.lon,input_lat=row.lat))
            raster_meta.append(dict(file=path.name,raw_relative_path=file,sha256=digest,bytes=raster_file_bytes,dataset_access=dataset_path,
                accepted_old_receipt_sha256=accepted[path.name]['sha256'],feature=feature,scale_factor=scale,
                shape=[src.height,src.width],crs=str(src.crs),transform=list(src.transform),nodata=src.nodata,
                valid_samples=int(np.isfinite(values).sum()),nodata_samples=int(np.isnan(values).sum())))
        return values if raw else values*scale

    c = add[['id']].copy()
    temperatures=[]
    for month in range(1,13):
        tcol=f'climate_tavg_normal_month{month:02d}_c'
        c[tcol]=sample(f'wc2.1_10m_tavg_{month:02d}.tif',tcol)
        pcol=f'climate_prec_normal_month{month:02d}_mm'
        c[pcol]=sample(f'wc2.1_10m_prec_{month:02d}.tif',pcol)
        temperatures.append(c[tcol].to_numpy())
    temp=np.column_stack(temperatures)
    days=np.array([calendar.monthrange(2001,m)[1] for m in range(1,13)])
    c['climate_annual_mean_temperature_c']=np.sum(temp*days,axis=1)/365
    c['climate_annual_precipitation_mm']=c.filter(regex='climate_prec_normal_month').sum(axis=1,min_count=12)
    c['climate_monthly_approx_active_temperature_sum_above10_cday']=np.sum(np.where(temp>10,temp,0)*days,axis=1)
    c['climate_monthly_approx_growing_degree_days_base10_cday']=np.sum(np.maximum(temp-10,0)*days,axis=1)
    c.loc[np.isnan(temp).any(axis=1),['climate_monthly_approx_active_temperature_sum_above10_cday','climate_monthly_approx_growing_degree_days_base10_cday']]=np.nan
    ai=sample('Global-AI_ET0__annual_v3_1/ai_v31_yr.tif','climate_global_ai_v31_precipitation_over_et0',.0001,raw=True)
    et=sample('Global-AI_ET0__annual_v3_1/et0_v31_yr.tif','climate_global_et0_v31_annual_mm')
    c['climate_global_ai_v31_precipitation_over_et0']=np.where(np.isfinite(et)&(ai>0),ai*.0001,np.nan)
    c['climate_global_ai_integer_saturation']=pd.Series(ai==65535,dtype='boolean').mask(~np.isfinite(ai))
    c['climate_global_et0_v31_annual_mm']=et
    c['climate_normal_period']='1970-2000'
    c['climate_word_daily_sat_observed']=False
    c['climate_bonitet_observed']=False
    for file,col,scale in [('ts3_CRUTS32_Hist_8110.tif','climate_gaez_sat_above10_cday_1981_2010',1.),
                           ('riS_CRUTS32_Hist_8110.tif','climate_gaez_summer_precipitation_over_pet_1981_2010',.01)]:
        c[col]=sample(file,col,scale)
    c['climate_daily_derived_sat_source_available']=c.climate_gaez_sat_above10_cday_1981_2010.notna().astype('boolean')

    legend=json.loads((BASE/'gaez_soil_legend.json').read_text())
    colors={}
    for layer in legend['layers']:
        for entry in layer['legend']:
            im=Image.open(io.BytesIO(base64.b64decode(entry['imageData']))).convert('RGB')
            colors[im.getpixel((im.width//2,im.height//2))]=entry['label']
    s=add[['id']].copy()
    names={'SQ0_mze_v9aL':'most_limiting_rating','SQ1_mze_v9aL':'nutrient_availability',
           'SQ3_mze_v9aL':'rooting_conditions','SQ4_mze_v9aL':'oxygen_availability_to_roots',
           'SQ5_mze_v9aL':'salinity_sodicity','SQ6_mze_v9aL':'lime_gypsum','SQ7_mze_v9aL':'workability'}
    palette_proofs=[]
    for name,label in names.items():
        col='soil_gaez_low_input_'+label+'_class'
        s[col]=sample(name+'.tif',col)
        with rasterio.open(RAW/(name+'.tif')) as src: palette=src.colormap(1)
        labels={code:colors[rgb[:3]] for code,rgb in palette.items() if rgb[:3] in colors and code<14}
        assert set(range(14)).issubset(labels)
        s[col+'_label']=s[col].map(labels).astype('string')
        for side in ['lower','upper']:
            bounds={code:float(value.split(' - ')[0 if side=='lower' else 1]) for code,value in labels.items() if ' - ' in value}
            s[col+'_rating_'+side]=s[col].map(bounds)
        palette_proofs.append(dict(feature=col,class_label_map=labels))
    s['soil_russian_bonitet_score']=np.nan
    outputs={}
    for family,old,new in [('climate',oldc,c),('soil',olds,s)]:
        assert set(old.columns)==set(new.columns)
        new=new[old.columns].astype(old.dtypes.to_dict())
        full=old.copy().set_index('id')
        for col in new.columns:
            if col!='id':full.loc[new.id,col]=new[col].to_numpy()
        full=full.reset_index()[old.columns].astype(old.dtypes.to_dict())
        unaffected=~old.id.isin(new.id)
        pd.testing.assert_frame_equal(full.loc[unaffected].reset_index(drop=True),old.loc[unaffected].reset_index(drop=True),check_exact=True,check_dtype=True)
        pd.testing.assert_frame_equal(full.set_index('id').loc[new.id].reset_index(),new,check_exact=True,check_dtype=True)
        assert full.id.equals(axis.id) and len(full)==173862
        path=H/(family+'_settlement_features.parquet');full.to_parquet(path,index=False)
        check=pd.read_parquet(path)
        pd.testing.assert_frame_equal(check,full,check_exact=True,check_dtype=True)
        new.to_parquet(H/(family+'_new477.parquet'),index=False)
        outputs[family]=dict(path=path.name,sha256=sha(path),rows=len(full),unaffected_rows_exactly_preserved=int((~old.id.isin(new.id)).sum()),updated_rows=len(new),
            new_coverage={col:int(new[col].notna().sum()) for col in new if col!='id'})
    obs=pd.DataFrame(samples);obs.to_parquet(H/'source_pixel_observations.parquet',index=False)
    assert len(obs)==477*35
    assert before=={str(p):sha(p) for p in source_paths}
    assert all(m['sha256']==accepted[m['file']]['sha256'] for m in raster_meta)
    out=dict(status='ACTUALLY_SAMPLED_AND_ALL_PIXELS_READ_BACK',axis_rows=len(axis),new_rows=len(add),
        unaffected_values_exactly_preserved=True,updated_old477previous_missing_values=True,source_sha256=before,raster_sources=raster_meta,
        outputs=outputs,source_pixel_observations=len(obs),single_pixel_independent_readbacks=len(obs),
        source_pixel_observations_sha256=sha(H/'source_pixel_observations.parquet'),palette_proofs=palette_proofs,
        interpolation='none; containing source grid cell',climate_normal_periods={'WorldClim_and_GlobalAI':'1970-2000','GAEZ_SAT_and_summer_P_over_PET':'1981-2010'},
        source_coordinate_dates='Retained from source axis; raster sampling does not prove coordinate survey dates',
        soil_meaning=sr['interpretation'],russian_bonitet_new477='all NA; no extrapolation',source_coordinate_overlay_sha256=sha(axis_path),source_admission_scoped477=True,
        scientific_word_acceptance=False)
    (H/'context_extension_receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({key:value for key,value in out.items() if key not in ['raster_sources','palette_proofs','source_sha256']},ensure_ascii=False,indent=2))

if __name__=='__main__':run()

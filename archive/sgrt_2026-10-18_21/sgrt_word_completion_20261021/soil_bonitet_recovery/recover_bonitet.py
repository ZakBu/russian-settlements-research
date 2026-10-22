#!/usr/bin/env python3
"""Experimental interval-only recovery from an unreferenced national soil atlas.

Digitized city dots are cartographic controls, not observations of soil at cities.
No numerical value is donated across class boundaries or outside control coverage.
"""
from pathlib import Path
import hashlib,json,warnings
import numpy as np,pandas as pd
from PIL import Image
from scipy.optimize import differential_evolution
from scipy.spatial import Delaunay
from scipy.ndimage import uniform_filter
from pyproj import Geod
from sklearn.model_selection import KFold
from pyproj import Transformer
import rasterio
from rasterio.transform import from_origin
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
SOURCE=ROOT/'sources/atlas_240_241_3600x2400.jpg'
SOURCE_URL='https://files.soil-db.ru/soilatlas/3600x2400/240-241-min.jpg'
GEOD=Geod(ellps='WGS84')

def design(lon,lat,kind,params):
    n=params[0];theta=n*np.radians((np.asarray(lon)-100+180)%360-180);phi=np.radians(lat)
    if kind=='eqdc':rho=params[1]-phi
    elif kind=='lcc':rho=np.tan(np.pi/4+phi/2)**(-n)
    elif kind=='aea':
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');rho=np.sqrt(params[1]-2*n*np.sin(phi))
    return np.column_stack([rho*np.sin(theta),rho*np.cos(theta),np.ones(len(phi))])

def fit(g,kind):
    Y=g[['pixel_x','pixel_y']].to_numpy(float)
    def objective(params):
        X=design(g.lon.to_numpy(),g.lat.to_numpy(),kind,params)
        if not np.isfinite(X).all():return 1e20
        B=np.linalg.lstsq(X,Y,rcond=None)[0]
        return np.mean(np.sum((X@B-Y)**2,axis=1))
    bounds={'eqdc':[(.65,.98),(1.6,2.5)],'lcc':[(.65,.98)],'aea':[(.65,.98),(1.2,2.5)]}[kind]
    f=differential_evolution(objective,bounds,seed=415,popsize=10,maxiter=120,tol=1e-8)
    X=design(g.lon.to_numpy(),g.lat.to_numpy(),kind,f.x);B=np.linalg.lstsq(X,Y,rcond=None)[0]
    return f.x,B

def predict(g,kind,params,B):return design(g.lon.to_numpy(),g.lat.to_numpy(),kind,params)@B

def main():
    if not SOURCE.exists():
        import urllib.request
        SOURCE.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(SOURCE_URL,SOURCE)
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!='b70292ee3c8843c1c2872b970cd405be9b182f91c3be63d3d18cffccafcf9324':
        raise ValueError('Atlas source bytes changed; controls and legend must be revalidated')
    g=pd.read_csv(ROOT/'control_points_digitized.csv');axis=pd.read_parquet(BASE/'axis/full_settlement_axis.parquet');a=pd.concat([axis,pd.read_parquet(BASE/'axis/external_context_centers.parquet')],ignore_index=True)
    linked=[]
    for row in g.itertuples():
        match=a[a.name.str.lower().str.replace('ё','е').eq(row.name.lower().replace('ё','е'))&a.lat.notna()&a.lon.notna()].sort_values('population_2021',ascending=False,na_position='last')
        if not len(match):raise ValueError('Unresolved named control '+row.name)
        v=match.iloc[0];linked.append({'name':row.name,'id':v.id,'lat':v.lat,'lon':v.lon,'pixel_x':row.pixel_x,'pixel_y':row.pixel_y})
    g=pd.DataFrame(linked);g['role']=np.where(np.arange(len(g))%4==0,'holdout','train')
    train=g[g.role.eq('train')].copy();hold=g[g.role.eq('holdout')].copy();cv={}
    for kind in ['eqdc','lcc','aea']:
        errors=[]
        for tr,te in KFold(5,shuffle=True,random_state=107).split(train):
            p,b=fit(train.iloc[tr],kind);pred=predict(train.iloc[te],kind,p,b);errors.extend(np.linalg.norm(pred-train.iloc[te][['pixel_x','pixel_y']].to_numpy(),axis=1))
        cv[kind]={'rmse_pixels':float(np.sqrt(np.mean(np.square(errors)))),'p95_pixels':float(np.quantile(errors,.95))}
    kind=min(cv,key=lambda k:cv[k]['rmse_pixels']);p,b=fit(train,kind);hp=predict(hold,kind,p,b)
    hold['error_pixels']=np.linalg.norm(hp-hold[['pixel_x','pixel_y']].to_numpy(),axis=1)
    hold[['predicted_pixel_x','predicted_pixel_y']]=hp
    # Local finite-difference map scale converts residual to approximate ground km.
    km_per_pixel=[]
    for row in hold.itertuples():
        lon2,lat2,_=GEOD.fwd(row.lon,row.lat,90,10000)
        pp=design([row.lon,lon2],[row.lat,lat2],kind,p)@b
        km_per_pixel.append(10/np.linalg.norm(pp[1]-pp[0]))
    hold['approx_error_km']=hold.error_pixels.to_numpy()*km_per_pixel
    hold.to_csv(ROOT/'heldout_georeference_errors.csv',index=False)
    # Model choice uses training CV only; final coefficients then use all controls.
    params,B=fit(g,kind);g['role_before_final_refit']=g.role;g.to_csv(ROOT/'control_points_linked.csv',index=False)
    radius=int(np.ceil(max(cv[kind]['p95_pixels'],float(hold.error_pixels.max()))+2))
    im=np.asarray(Image.open(SOURCE).convert('RGB'));palette_y=[560,590,621,652,682,713,743,773,804,834,865,895,926]
    palette=np.array([np.median(im[y-3:y+4,2588:2600].reshape(-1,3),axis=0) for y in palette_y])
    ranges=[(120,125),(110,120),(100,110),(90,100),(80,90),(70,80),(60,70),(50,60),(40,50),(30,40),(20,30),(10,20),(0,10)]
    color_dist=np.sum((im[:,:,None,:].astype('float32')-palette[None,None,:,:])**2,axis=3)
    classes=np.argmin(color_dist,axis=2).astype('int16');valid=np.min(color_dist,axis=2)<=22**2
    valid[:240]=False;valid[1200:]=False;valid[:,:750]=False;valid[:,2500:]=False
    classes[~valid]=-1
    # Neighbourhood certification requires a single legend interval across the
    # georeference error radius, allowing text/hatch pixels to remain unclassified.
    size=2*radius+1;support=np.stack([uniform_filter((classes==k).astype('float32'),size=size,mode='constant') for k in range(13)],axis=2)
    total=support.sum(axis=2);winner=np.argmax(support,axis=2);best=np.max(support,axis=2);second=np.partition(support,-2,axis=2)[:,:,-2]
    stable=(total>=.35)&(best>=.35)&(best/np.maximum(total,1e-8)>=.95)&(second<.02)
    loc=axis.lat.notna()&axis.lon.notna();xy=np.full((len(axis),2),np.nan);xy[loc]=predict(axis.loc[loc],kind,params,B)
    ix=np.rint(np.nan_to_num(xy[:,0],nan=-1)).astype(int);iy=np.rint(np.nan_to_num(xy[:,1],nan=-1)).astype(int)
    hull=Delaunay(g[['pixel_x','pixel_y']].to_numpy());inside=np.zeros(len(axis),bool);inside[loc]=hull.find_simplex(xy[loc])>=0
    pixel_inside=(ix>=0)&(ix<im.shape[1])&(iy>=0)&(iy<im.shape[0]);cert=np.zeros(len(axis),bool);z=inside&pixel_inside
    cert[z]=stable[iy[z],ix[z]]
    low=np.full(len(axis),np.nan);high=low.copy();cls=np.full(len(axis),-1);cls[cert]=winner[iy[cert],ix[cert]]
    for k,(lo,hi) in enumerate(ranges):low[cls==k]=lo;high[cls==k]=hi
    out=axis[['id']].copy();out['soil_bonitet_atlas_experimental_interval_lower']=low;out['soil_bonitet_atlas_experimental_interval_upper']=high;out['soil_bonitet_atlas_interpolated_map_x']=xy[:,0];out['soil_bonitet_atlas_interpolated_map_y']=xy[:,1]
    out['soil_bonitet_atlas_status']=np.select([~loc,~inside,~pixel_inside,cert],['unlocated','outside_control_hull_no_extrapolation','outside_source_image','experimental_single_interval_stable_under_error_radius'],default='mixed_interval_or_hatch_text_water_uncertainty')
    out['soil_bonitet_atlas_georeference_error_radius_pixels']=radius
    out['soil_bonitet_atlas_is_direct_settlement_soil_measurement']=False
    out['soil_bonitet_atlas_scientifically_adopted']=False
    out.to_parquet(ROOT/'experimental_bonitet_settlement_intervals.parquet',index=False)
    coverage=axis[['id','region']].merge(out[['id','soil_bonitet_atlas_experimental_interval_lower']],on='id',validate='one_to_one')
    coverage['experimental_interval_available']=coverage.soil_bonitet_atlas_experimental_interval_lower.notna()
    coverage.groupby('region',dropna=False).agg(axis_entities=('id','size'),experimental_intervals=('experimental_interval_available','sum')).reset_index().to_csv(ROOT/'coverage_by_region.csv',index=False)
    out.groupby(['soil_bonitet_atlas_experimental_interval_lower','soil_bonitet_atlas_experimental_interval_upper']).size().reset_index(name='axis_entity_count').to_csv(ROOT/'interval_counts.csv',index=False)
    pd.DataFrame([{'class_id':i,'lower':lo,'upper':hi,'red':float(palette[i,0]),'green':float(palette[i,1]),'blue':float(palette[i,2]),'legend_sample_y':palette_y[i]} for i,(lo,hi) in enumerate(ranges)]).to_csv(ROOT/'legend_intervals.csv',index=False)
    receipt={'status':'EXPERIMENTAL_COARSE_ATLAS_INTERVAL_RECOVERY_NOT_ADOPTED','source_page':'https://soil-db.ru/soilatlas/razdel-6-funkcii-pochv/bonitet-pochvennogo-pokrova','source_image_url':SOURCE_URL,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_size_pixels':list(im.shape[:2][::-1]),'source_scale':'1:30,000,000','source_spatial_grain':'soil-geographical districts and mountain provinces; not plots or village boundaries','legend_classes':13,'controls':len(g),'training_controls':len(train),'heldout_controls':len(hold),'selection_training_cv':cv,'selected_projection_family':kind,'final_spherical_conic_params':params.tolist(),'final_affine_matrix':B.tolist(),'heldout_rmse_pixels':float(np.sqrt(np.mean(hold.error_pixels**2))),'heldout_rmse_approx_km':float(np.sqrt(np.mean(hold.approx_error_km**2))),'heldout_max_approx_km':float(hold.approx_error_km.max()),'conservative_error_radius_pixels':radius,'class_support_rule':'within radius:>=35% exact palette support, modal>=95%, any second class<2%; outside convex hull withheld','axis_rows':len(out),'nonnull_experimental_intervals':int(cert.sum()),'status_counts':out.soil_bonitet_atlas_status.value_counts().to_dict(),'not_point_bonitet_scores':True,'not_a_substitute_for_verified_georeferenced_soil_data':True,'scientific_adoption':False,'axis_sha256':hashlib.sha256((BASE/'axis/full_settlement_axis.parquet').read_bytes()).hexdigest()}
    receipt['holdout_is_blind_preregistered_external_test']=False
    receipt['holdout_scope']='Deterministic technical check after manual digitization quality control; exploratory all-control fits helped detect misread dots before the final train/holdout split. Final family selection uses training CV only.'
    (ROOT/'recovery_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
    np.savez_compressed(ROOT/'atlas_classification.npz',classes=classes.astype('int8'),stable=stable,palette=palette)
    # A separate coarse grid is an experimental digitization, never a field-scale map.
    proj=Transformer.from_crs('EPSG:4326','EPSG:3576',always_xy=True)
    inverse=Transformer.from_crs('EPSG:3576','EPSG:4326',always_xy=True)
    gx,gy=proj.transform(g.lon.to_numpy(),g.lat.to_numpy());resolution=25000
    xmin=np.floor(np.min(gx)/resolution)*resolution;ymax=np.ceil(np.max(gy)/resolution)*resolution
    width=int(np.ceil((np.max(gx)-xmin)/resolution));height=int(np.ceil((ymax-np.min(gy))/resolution))
    xx,yy=np.meshgrid(xmin+(np.arange(width)+.5)*resolution,ymax-(np.arange(height)+.5)*resolution)
    glon,glat=inverse.transform(xx.ravel(),yy.ravel());mapxy=design(glon,glat,kind,params)@B
    u=np.rint(mapxy[:,0]).astype(int);v=np.rint(mapxy[:,1]).astype(int)
    ok=(hull.find_simplex(mapxy)>=0)&(u>=0)&(u<im.shape[1])&(v>=0)&(v<im.shape[0]);which=np.where(ok)[0];ok[which]=stable[v[which],u[which]]
    raster=np.full((2,len(u)),-9999,dtype='float32');chosen=winner[v[ok],u[ok]]
    for k,(lo,hi) in enumerate(ranges):
        indices=np.where(ok)[0][chosen==k];raster[0,indices]=lo;raster[1,indices]=hi
    with rasterio.open(ROOT/'experimental_bonitet_intervals_25km.tif','w',driver='GTiff',height=height,width=width,count=2,dtype='float32',crs='EPSG:3576',transform=from_origin(xmin,ymax,resolution,resolution),nodata=-9999,compress='deflate') as dst:
        dst.write(raster.reshape(2,height,width));dst.set_band_description(1,'Experimental atlas class lower endpoint');dst.set_band_description(2,'Experimental atlas class upper endpoint')
        dst.update_tags(source_scale='1:30000000',scientific_adoption='false',point_measurement='false',georeference_holdout_rmse_km=str(receipt['heldout_rmse_approx_km']),georeference_error_radius_pixels=str(radius),source_sha256=receipt['source_sha256'])

if __name__=='__main__':main()

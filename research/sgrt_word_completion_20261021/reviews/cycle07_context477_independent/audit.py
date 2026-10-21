from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,zipfile,rasterio,calendar
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'context/cycle07_coordinate_recovery';O=B/'reviews/cycle07_context477_independent';checks=[]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for s in iter(lambda:f.read(4<<20),b''):h.update(s)
 return h.hexdigest()
def ck(k,v):checks.append(dict(check=k,pass_=bool(v)))
def eq(a,b):return np.array_equal(np.asarray(a,float),np.asarray(b,float),equal_nan=True)
r=json.loads((P/'context_extension_receipt.json').read_text());obs=pd.read_parquet(P/'source_pixel_observations.parquet');patch=pd.read_parquet(B/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet').set_index('id');ck('all16695samples_unique_sourcefeatureIDs',len(obs)==16695 and not obs.duplicated(['id','feature']).any());ck('rawsamples_exact_source477coords',eq(obs.input_lon,obs.id.map(patch.new_lon)) and eq(obs.input_lat,obs.id.map(patch.new_lat)))
for p,h in r['source_sha256'].items():ck('actual_sourcehash_'+p,sha(p)==h)
cl=pd.read_parquet(P/'climate_settlement_features.parquet').set_index('id');so=pd.read_parquet(P/'soil_settlement_features.parquet').set_index('id');samples={}
for item in r['raster_sources']:
 access=item['dataset_access'];file=Path(access)
 if access.startswith('/vsizip/'):
  zipath=next(p for p in r['source_sha256']if p.endswith('.zip'));member=item['raw_relative_path'];hh=hashlib.sha256()
  with zipfile.ZipFile(zipath)as zz,zz.open(member)as stream:
   for chunk in iter(lambda:stream.read(4<<20),b''):hh.update(chunk)
  actualsha=hh.hexdigest()
 else:actualsha=sha(file)
 ck('actual_rasterSHA_'+item['feature'],actualsha==item['sha256']==item['accepted_old_receipt_sha256']);g=obs[obs.feature.eq(item['feature'])].set_index('id').loc[patch.index];coords=list(zip(patch.new_lon,patch.new_lat))
 with rasterio.open(access)as src:
  v=np.ma.concatenate(list(src.sample(coords,indexes=1,masked=True))).reshape(-1);raw=v.filled(np.nan) if np.issubdtype(v.dtype,np.floating)else v.astype(float).filled(np.nan);rr,cc=np.asarray([src.index(x,y)for x,y in coords]).T;ck('all477sourcecontainingpixelindices_'+item['feature'],np.array_equal(g.source_row,rr)and np.array_equal(g.source_col,cc));ck('all477rawmaskpixels_'+item['feature'],eq(raw,g.source_raw_value)and np.array_equal(~np.ma.getmaskarray(v),g.source_valid));ck('sourcegridmetadata_'+item['feature'],src.crs.to_epsg()==4326 and [src.height,src.width]==item['shape']and list(src.transform)==item['transform'])
 samples[item['feature']]=raw*item['scale_factor'];ck('all477scaledledger_'+item['feature'],eq(samples[item['feature']],g.scaled_source_value));table=so if item['feature'].startswith('soil_')else cl;ck('all477outputsourcevalues_'+item['feature'],eq(table.loc[patch.index,item['feature']],samples[item['feature']]))
temps=np.column_stack([samples[f'climate_tavg_normal_month{m:02}_c']for m in range(1,13)]);days=np.array([calendar.monthrange(2001,m)[1]for m in range(1,13)]);derived={'climate_annual_mean_temperature_c':np.sum(temps*days,axis=1)/365,'climate_annual_precipitation_mm':np.column_stack([samples[f'climate_prec_normal_month{m:02}_mm']for m in range(1,13)]).sum(axis=1),'climate_monthly_approx_active_temperature_sum_above10_cday':np.sum(np.where(temps>10,temps,0)*days,axis=1),'climate_monthly_approx_growing_degree_days_base10_cday':np.sum(np.maximum(temps-10,0)*days,axis=1)}
for col,val in derived.items():ck('derivedclimate477_'+col,eq(cl.loc[patch.index,col],val))
for family,table in [('climate',cl),('soil',so)]:
 original=pd.read_parquet(B/'context/cycle05_federal335'/f'{family}_settlement_features.parquet').set_index('id');ck(family+':all173862IDs_same',table.index.equals(original.index));ck(family+':all_unaffected173385cells_dtypes_exact',table.loc[~table.index.isin(patch.index)].equals(original.loc[~original.index.isin(patch.index)]));ck(family+':all_updated477_were_sourceNA_numeric',original.loc[patch.index].select_dtypes('number').isna().all().all());ck(family+':outputactualhash',sha(P/f'{family}_settlement_features.parquet')==r['outputs'][family]['sha256'])
for item in r['palette_proofs']:
 col=item['feature'];classes=samples[col]
 for side,j in [('lower',0),('upper',1)]:
  lookup={int(k):float(v.split(' - ')[j]) for k,v in item['class_label_map'].items()if ' - 'in v};want=pd.Series(classes,index=patch.index).map(lookup);ck('soil477rating_'+col+'_'+side,eq(so.loc[patch.index,col+'_rating_'+side],want))
ck('Russianbonitet477_unknown_notsoilrating',so.loc[patch.index,'soil_russian_bonitet_score'].isna().all());ck('source_pixel_ledger_actualSHA',sha(P/'source_pixel_observations.parquet')==r['source_pixel_observations_sha256']);result=dict(status='ACCEPTED'if all(x['pass_']for x in checks)else'REJECTED',all_checks_passed=all(x['pass_']for x in checks),n_checks=len(checks),n_failed=sum(not x['pass_']for x in checks),checks=checks,accepted_climate_sha256=sha(P/'climate_settlement_features.parquet'),accepted_soil_sha256=sha(P/'soil_settlement_features.parquet'),accepted_context_receipt_sha256=sha(P/'context_extension_receipt.json'),scope='All16695 containingpixels independently read usingRasterio.sample, sourcehashes/masks/rowcols/scales/derivedmonthlyclimate/soilratingbounds andall173385unaffectedrows/dtypes independentlychecked. Sourcepoint2021 assertion, climatenormal1970-2000/1981-2010, FAOlowinputmaizerating NOTRussianbonitet ormeasured2021fertility.');(O/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['n_checks'],result['n_failed']);print([x for x in checks if not x['pass_']])

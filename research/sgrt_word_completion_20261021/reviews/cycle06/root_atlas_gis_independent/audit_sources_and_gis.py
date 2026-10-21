"""Independent full source-field and geometry review; no author renderer/exporter import."""
from pathlib import Path
import sqlite3,json,hashlib,struct,zipfile,datetime
import numpy as np,pandas as pd
import pyogrio,pyogrio.raw,shapely,fitz
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=ROOT.parents[1];MODEL=ROOT/'model/output_cycle06_access_v2_baseline';CAN=ROOT/'typology/canonical_cycle06/output_cycle06_access_v2_baseline';MAP=ROOT/'maps/cycle06_access_v2_baseline';GIS=ROOT/'delivery/gis_cycle06_access_v2_baseline';TEMP=Path('/tmp/sgrt_cycle06_independent_gis/SGRT_output_cycle06_access_v2_baseline.gpkg')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def dump(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
def normalized(series):
 v=series.copy();nonnull=v.dropna()
 if pd.api.types.is_numeric_dtype(v.dtype) or pd.api.types.is_bool_dtype(v.dtype) or len(nonnull) and nonnull.map(lambda x:isinstance(x,(bool,np.bool_))).all():return pd.to_numeric(v,errors='raise').astype('float64').to_numpy(),True
 return v.astype('string').fillna('__NULL__').to_numpy(),False

def main():
 if (H/'source_and_gis_audit.json').exists():raise FileExistsError('Use a new review directory')
 checks=[];counts=[];mapmeta=json.loads((MAP/'map_manifest.json').read_text());gisreceipt=GIS/'SGRT_output_cycle06_access_v2_baseline.receipt.json';g=json.loads(gisreceipt.read_text());archive=GIS/g['archive'];pins={**mapmeta['input_sha256'],**g['input_sha256']};pins={str(Path(k) if Path(k).is_absolute() else REPO/k):v for k,v in pins.items()};assert all(sha(Path(k))==v for k,v in pins.items());assert sha(archive)==g['archive_sha256'] and sha(TEMP)==g['sha256'];checks+=['Every map and GIS source hash exact','ZIP bytes/extracted GeoPackage bytes match published SHA']
 for f in mapmeta['figures']:
  for o in f['outputs']:assert sha(MAP/o['path'])==o['sha256']
 assert sha(MAP/'SGRT_CYCLE06_MODEL_ATLAS.pdf')==mapmeta['atlas']['sha256'];checks.append('All54 individual map PNG/PDF/SVG file SHA and18-page atlas SHA exact')
 n=pd.read_parquet(MODEL/'nodes.parquet',columns=['id','name','region','type','lat','lon','axis_kind','_population_axis_row','population_2002','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021','accepted_statistical_rural_role2021','accepted_formal_settlement_subtype2021']);mem=pd.read_parquet(MODEL/'memberships.parquet');s=pd.read_parquet(MODEL/'systems.parquet');c=pd.read_parquet(MODEL/'candidate_centers.parquet');t=pd.read_parquet(CAN/'word_type_hypotheses.parquet');cfg=pd.read_parquet(MODEL/'system_configurations.parquet');acc=pd.read_parquet(MODEL/'network_accessibility.parquet');assert n.id.is_unique and mem.id.equals(n.id)
 # Independently compute compound annual change using log/expm1.
 def rate(x,y):
  a=np.asarray(x,dtype=float);b=np.asarray(y,dtype=float);out=np.full(len(a),np.nan);positive=np.isfinite(a)&np.isfinite(b)&(a>0)&(b>0);out[positive]=np.expm1(np.log(b[positive]/a[positive])/11);out[np.isfinite(a)&(a>0)&(b==0)]=-1.;return out
 expected={};expected['01_centers']={'centers':len(c),'ranks':{str(k):int(v) for k,v in c.intrinsic_empirical_rank.value_counts().sort_index().items()}}
 for level in sorted(s.level.unique()):
  ss=s[s.level.eq(level)];tt=t[t.level.eq(level)];picked=tt[tt.operational_hypothesis];assigned=mem[f'center_id_l{level}'].notna()&mem._population_axis_row.fillna(False);assert n.loc[assigned,['lat','lon']].notna().all().all();expected[f'02_membership_level{level}']={'level':int(level),'systems':len(ss),'assigned_population_units':int(assigned.sum())};expected[f'03_word_types_level{level}']={'level':int(level),'candidate_center_type_pairs':len(picked),'by_type':{str(k):int(v) for k,v in picked.word_type.value_counts().sort_index().items()}}
  unique=tt.drop_duplicates(['level','center_id']).set_index('center_id').loc[ss.center_id];cr=rate(ss.center_population_2010,ss.center_population_2021);rr=rate(ss.rural_external_population_known_sum_2010,ss.rural_external_population_known_sum_2021);np.testing.assert_allclose(cr,unique.center_annual_rate,equal_nan=True,atol=2e-15);np.testing.assert_allclose(rr,unique.rural_annual_rate,equal_nan=True,atol=2e-15);complete=np.ones(len(ss),bool)
  for kind in ['system','rural_external']:
   for year in [2010,2021]:complete&=ss[f'{kind}_population_complete_{year}'].to_numpy(bool)
  assert np.array_equal(complete,unique.population_pair_complete);valid=complete&np.isfinite(cr)&np.isfinite(rr);expected[f'04_dynamics_level{level}']={'level':int(level),'numeric_complete_pairs':int(valid.sum()),'all_systems':len(ss)};q=cfg[cfg.level.eq(level)];expected[f'06_configuration_level{level}']={'level':int(level),'same_order_configuration':q.same_order_configuration.value_counts().to_dict(),'nested_child_configuration':q.nested_child_configuration.value_counts().to_dict()};counts.append({'level':int(level),'systems':len(ss),'assigned_axis_rows':int(assigned.sum()),'type_hypotheses':len(picked),'dynamics_pairs':int(valid.sum()),'dynamics_rural_endpoint_zero_rows':int((valid&(ss.rural_external_population_known_sum_2021.to_numpy()==0)).sum())})
 expected['05_large_city_access']={'population_units_with_path':int((n._population_axis_row.fillna(False)&acc.nearest_large_city_network_minutes.notna()).sum()),'population_threshold':100000}
 assert sum(d['type_hypotheses'] for d in counts)==47
 for f in mapmeta['figures']:assert f['statistics']==expected[f['figure']],(f['figure'],f['statistics'],expected[f['figure']]);checks.append(f['figure']+': every displayed/statistical source count exact')
 atlas=fitz.open(MAP/'SGRT_CYCLE06_MODEL_ATLAS.pdf');assert len(atlas)==18;pixel=[]
 for i,f in enumerate(mapmeta['figures']):
  standalone=fitz.open(MAP/(f['figure']+'.pdf'));one=atlas[i].get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False);two=standalone[0].get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False);assert (one.width,one.height)==(two.width,two.height);a=np.frombuffer(one.samples,dtype='uint8').astype(int);b=np.frombuffer(two.samples,dtype='uint8').astype(int);delta=np.abs(a-b);pixel.append({'page':i+1,'figure':f['figure'],'identical_rendered_pixels':bool((delta==0).all()),'maximum_channel_delta':int(delta.max()),'mean_absolute_channel_delta':float(delta.mean()),'identical_vector_text':atlas[i].get_text()==standalone[0].get_text(),'atlas_used_image_dimensions':[(v['width'],v['height']) for v in atlas[i].get_image_info()],'standalone_used_image_dimensions':[(v['width'],v['height']) for v in standalone[0].get_image_info()]});assert atlas[i].get_text()==standalone[0].get_text();standalone.close()
 checks.append('All18 combined PDF page dimensions and vector text equal standalone panels; raster differences documented (atlas100dpi vs individual180dpi)');atlas.close();dump(H/'atlas_page_raster_comparison.json',pixel)
 con=sqlite3.connect(f'file:{TEMP}?mode=ro',uri=True);assert con.execute('pragma integrity_check').fetchone()[0]=='ok';assert con.execute('pragma foreign_key_check').fetchall()==[];checks+=['SQLite full integrity_check and foreign_key_check pass'];layer_counts={x:con.execute(f'select count(*) from "{x}"').fetchone()[0] for x, in con.execute('select table_name from gpkg_contents')};assert layer_counts=={v['layer']:v['rows'] for v in g['layers']};checks.append('Every10 GIS spatial/attribute layer row count exact')
 field_controls=[]
 def compare(layer,expected,key=None):
  columns=[str(v) for v in expected.columns];select=','.join('"'+v.replace('"','""')+'"' for v in columns);actual=pd.read_sql_query(f'select {select} from "{layer}" order by fid',con)
  if key:
   assert actual[key].is_unique and set(actual[key])==set(expected[key]);actual=actual.set_index(key).loc[expected[key]].reset_index();expected=expected.reset_index(drop=True)
  assert len(actual)==len(expected)
  for col in columns:
   aa,numeric=normalized(expected[col]);bb,_=normalized(actual[col])
   if numeric:
    bb=pd.to_numeric(actual[col],errors='raise').astype(float).to_numpy();assert np.array_equal(np.isnan(aa),np.isnan(bb)),(layer,col,'NULL');assert np.array_equal(aa[~np.isnan(aa)],bb[~np.isnan(bb)]),(layer,col,'value')
   else:assert np.array_equal(aa,bb),(layer,col,'string')
  field_controls.append({'layer':layer,'source_columns':len(columns),'rows':len(actual),'source_cells_exact':len(columns)*len(actual)})
 # All original membership attributes plus effective population/type fields and accessibility.
 base=mem.merge(n[['id','population_2002','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021','accepted_statistical_rural_role2021','accepted_formal_settlement_subtype2021']],on='id',validate='one_to_one');base=base.merge(acc,on='id',validate='one_to_one');geo=base.lat.notna()&base.lon.notna();compare('settlements',base.loc[geo].reset_index(drop=True),'id');compare('unlocated_source_entities',base.loc[~geo].reset_index(drop=True),'id');compare('candidate_centers',c,'id');assert sum(layer_counts[k] for k in ['settlements','unlocated_source_entities'])==len(n)
 for level in sorted(s.level.unique()):
  expected_systems=s[s.level.eq(level)].merge(cfg[cfg.level.eq(level)],on=['level','center_id'],validate='one_to_one').reset_index(drop=True);compare(f'systems_level{level}',expected_systems,'center_id');tt=t[t.level.eq(level)].set_index(['center_id','word_type']);raw=pd.read_sql_query(f'select * from systems_level{level} order by fid',con).set_index('center_id')
  for typ in range(1,10):
   selected=tt.xs(typ,level='word_type');assert np.array_equal(raw.loc[selected.index,f'word_type{typ}_operational_hypothesis'].to_numpy().astype(int),selected.operational_hypothesis.to_numpy().astype(int));assert raw.loc[selected.index,f'word_type{typ}_evidence_status'].tolist()==selected.rule_status.tolist();assert np.array_equal(raw.loc[selected.index,f'word_type{typ}_exact_contemporary_geography_candidate'].to_numpy().astype(int),selected.operational_hypothesis_exact_contemporary_geography.to_numpy().astype(int))
  for uid,group in t[t.level.eq(level)].groupby('center_id',sort=False):
   stored=json.loads(raw.loc[uid,'word_type_status_json']);assert stored['operational_hypotheses']==group.loc[group.operational_hypothesis,'word_type'].astype(int).tolist();assert stored['indicator_complete_without_causal_validation']==group.loc[group.rule_status.eq('satisfied_observed_indicators'),'word_type'].astype(int).tolist()
 checks+=['All model membership, effective population/role/subtype and accessibility cells exact','All candidate source fields exact','All four levels system+own/nested configuration fields exact','All nine literal/strict contemporary type flags and source-status JSON exact']
 compare('hierarchy_links',pd.read_parquet(MODEL/'hierarchy.parquet'));compare('broad_prototypes_not_literal_word_types',pd.read_parquet(CAN/'broad_prototypes.parquet'));checks+=['All hierarchy and explicitly broad-not-literal prototype cells exact']
 geometry_controls=[]
 for table,column,kind,srs,z,m in con.execute('select * from gpkg_geometry_columns').fetchall():
  assert kind=='POINT' and srs==4326 and z==m==0;rows=con.execute(f'select geom,lon,lat from "{table}"');count=0
  for blob,lon,lat in rows:
   assert len(blob)==29 and blob[:2]==b'GP' and blob[2:4]==bytes([0,1]);assert struct.unpack('<i',blob[4:8])[0]==4326;byteorder,typ,x,y=struct.unpack('<BIdd',blob[8:]);assert byteorder==typ==1 and x==lon and y==lat and -180<=x<=180 and -90<=y<=90;count+=1
  info=pyogrio.read_info(TEMP,layer=table);assert info['crs']=='EPSG:4326' and info['features']==count;metadata,_,wkb,values=pyogrio.raw.read(TEMP,layer=table,columns=['lon','lat']);decoded=shapely.from_wkb(wkb);field=dict(zip(metadata['fields'],values));assert shapely.is_valid(decoded).all() and (shapely.get_type_id(decoded)==0).all();assert np.array_equal(shapely.get_x(decoded),field['lon']) and np.array_equal(shapely.get_y(decoded),field['lat']);geometry_controls.append({'layer':table,'every_geometry_decoded':count,'independent_GDAL_Shapely_valid_points':True})
 checks+=['Every GIS geometry decoded independently: little-endian WKB Point, EPSG4326, exact source lon/lat','GDAL/pyogrio and Shapely independently validate all6 point layers']
 for table in ['settlements','unlocated_source_entities']:
  schema={v[1]:v[2] for v in con.execute(f'pragma table_info("{table}")')}
  for col in ['population_2002','population_2010','population_2021']:
   assert schema[col]=='REAL';assert con.execute(f"select count(*) from {table} where typeof({col}) not in ('real','integer','null')").fetchone()[0]==0
  assert schema['accepted_statistical_rural_role2021']=='INTEGER';assert con.execute(f'select count(*) from {table} where accepted_statistical_rural_role2021 not in (0,1)').fetchone()[0]==0
 ctx=pd.read_sql_query("select id,axis_kind,_population_axis_row,population_2010,population_2021 from settlements where id like 'ctx:%'",con);assert len(ctx)==2 and ctx.population_2010.isna().all() and ctx.population_2021.isna().all() and ctx._population_axis_row.eq(0).all();context_systems=[]
 for level in [1,2,3,4]:
  q=pd.read_sql_query(f"select level,center_id,center_population_2010,center_population_2021,system_population_known_sum_2021,system_population_complete_2021 from systems_level{level} where center_id like 'ctx:%'",con);context_systems+=q.astype(object).where(q.notna(),None).to_dict('records')
 checks+=['Population fields numeric REAL; missing NULL and observed zero preserved','Nullable statistical rural roles retain INTEGER0/1/NULL','Both external contexts retain NULL own2010/2021 and nonadditive flag; no citysubject population injection']
 rawprov=con.execute('select receipt_json,membership_sha256 from model_run_provenance').fetchone();assert json.loads(rawprov[0])==json.loads((MODEL/'run_receipt.json').read_text()) and rawprov[1]==sha(MODEL/'memberships.parquet');checks+=['Embedded run provenance and membership SHA exact'];con.close();assert all(sha(Path(k))==v for k,v in pins.items());assert sha(TEMP)==g['sha256'] and sha(archive)==g['archive_sha256'];dump(H/'source_and_gis_audit.json',{'status':'SOURCE_COUNTS_AND_GIS_BYTES_ACCEPTED_PRESENTATION_REVIEW_SEPARATE','all_checks_passed':True,'n_checks':len(checks),'n_failed':0,'checks':checks,'source_sha256':pins,'map_manifest_sha256':sha(MAP/'map_manifest.json'),'GIS_receipt_sha256':sha(gisreceipt),'archive_sha256':sha(archive),'extracted_gpkg_sha256':sha(TEMP),'all_level_source_counts':counts,'field_controls':field_controls,'geometry_controls':geometry_controls,'external_context_systems':context_systems,'external_context_limitation':'system_population_known_sum is the same raw known additive-member sum as primary model; complete member sums are NOT complete own-city/federal-city-context populations when center population is NULL. This must be disclosed in GIS/atlas companion documentation.','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()});print('PASS',len(checks),'source/GIS checks')
if __name__=='__main__':main()

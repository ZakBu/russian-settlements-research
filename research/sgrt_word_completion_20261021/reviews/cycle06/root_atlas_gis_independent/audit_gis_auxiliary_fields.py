"""Independent readback of every auxiliary source/function field in actual GIS."""
from pathlib import Path
import json,sqlite3,hashlib
import pandas as pd,numpy as np
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=ROOT.parents[1];MODEL=ROOT/'model/output_cycle06_access_v2_baseline';GIS=ROOT/'delivery/gis_cycle06_access_v2_baseline';TEMP=Path('/tmp/sgrt_cycle06_independent_gis/SGRT_output_cycle06_access_v2_baseline.gpkg')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if (H/'gis_auxiliary_source_field_audit.json').exists():raise FileExistsError('Never overwrite')
 con=sqlite3.connect(f'file:{TEMP}?mode=ro',uri=True);receipt=json.loads((GIS/'SGRT_output_cycle06_access_v2_baseline.receipt.json').read_text());assert sha(TEMP)==receipt['sha256'];config=json.loads((ROOT/'model_inputs_cycle06/final_access_v2/config_baseline_final.json').read_text());axis=pd.read_parquet(REPO/config['axis'],columns=['id','population_2010','population_value_quality_2010']);sources=[(axis.rename(columns={'population_2010':'original_axis_population2010','population_value_quality_2010':'original_axis_population_quality2010'}),'original axis2010')];counts=[];schema_failures=[];rounding=[]
 layers={'context/cycle05_federal335/climate_settlement_features.parquet':['climate_gaez_sat_above10_cday_1981_2010','climate_gaez_summer_precipitation_over_pet_1981_2010'],'context/cycle05_federal335/soil_settlement_features.parquet':['soil_gaez_low_input_most_limiting_rating_class','soil_gaez_low_input_most_limiting_rating_class_label'],'soil_bonitet_recovery/experimental_bonitet_settlement_intervals.parquet':['soil_bonitet_atlas_experimental_interval_lower','soil_bonitet_atlas_experimental_interval_upper','soil_bonitet_atlas_status','soil_bonitet_atlas_scientifically_adopted'],'land2021_recovery/settlement_regional_farmland2021_context.parquet':['region_farmland2021_sown_share','region_farmland2021_native_grain','region_farmland2021_pair_status','region_farmland2021_do_not_sum_over_settlements']}
 for path,cols in layers.items():sources.append((pd.read_parquet(ROOT/path,columns=['id']+cols),path))
 functions=pd.read_parquet(MODEL/'function_specific_memberships.parquet',columns=['id','function_group','assigned_center_id','assigned_travel_minutes','assignment_status'])
 for group,f in functions.groupby('function_group',observed=True):sources.append((f.drop(columns='function_group').rename(columns={c:f'function_{group}_{c}' for c in ['assigned_center_id','assigned_travel_minutes','assignment_status']}),'function '+str(group)))
 for layer in ['settlements','unlocated_source_entities']:
  ids=pd.read_sql_query(f'select id from {layer} order by fid',con);sqltypes={v[1]:v[2] for v in con.execute(f'pragma table_info({layer})')}
  for frame,name in sources:
   assert frame.id.is_unique;expected=ids.merge(frame,on='id',how='left',validate='one_to_one');cols=list(frame.columns);select=','.join('"'+c.replace('"','""')+'"' for c in cols);actual=pd.read_sql_query(f'select {select} from {layer} order by fid',con);assert actual.id.tolist()==expected.id.tolist()
   for c in cols[1:]:
    v=expected[c];nonmissing=v.dropna();boollike=pd.api.types.is_bool_dtype(v.dtype) or len(nonmissing)>0 and nonmissing.map(lambda q:isinstance(q,(bool,np.bool_))).all()
    if pd.api.types.is_numeric_dtype(v.dtype) or boollike:
     a=pd.to_numeric(v,errors='raise').astype('float64').to_numpy();b=pd.to_numeric(actual[c],errors='raise').astype('float64').to_numpy();assert np.array_equal(np.isnan(a),np.isnan(b)),(layer,name,c,'null');difference=np.abs(a-b);maximum=float(np.nanmax(difference)) if np.isfinite(difference).any() else 0.;assert maximum<1e-10,(layer,name,c,'values');rounding.append({'layer':layer,'field':c,'max_absolute_float_difference':maximum,'different_float_cells':int((difference>0).sum())});
     if sqltypes[c] not in ['REAL','INTEGER']:schema_failures.append({'layer':layer,'field':c,'source_dtype':str(v.dtype),'SQL_declared_type':sqltypes[c],'finite_source_values':int(np.isfinite(a).sum())})
    else:assert v.astype('string').fillna('__NULL__').tolist()==actual[c].astype('string').fillna('__NULL__').tolist(),(layer,name,c,'text')
   counts.append({'layer':layer,'source':name,'rows':len(ids),'columns':len(cols)-1,'cells_exact':len(ids)*(len(cols)-1)})
 con.close();assert sha(TEMP)==receipt['sha256'];out={'status':'REJECT_NUMERIC_FUNCTION_TIME_TEXT_SCHEMA' if schema_failures else 'ACCEPTED_EVERY_AUXILIARY_GIS_SOURCE_FIELD','all_checks_passed':not bool(schema_failures),'n_checks':len(counts)+len(schema_failures),'n_failed':len(schema_failures),'numeric_schema_failures':schema_failures,'numeric_rounding_controls':rounding,'controls':counts,'total_auxiliary_cells_exact':sum(d['cells_exact'] for d in counts),'gpkg_sha256':receipt['sha256']};(H/'gis_auxiliary_source_field_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(out['status'],len(counts),'source comparisons;',len(schema_failures),'schema failures')
if __name__=='__main__':main()

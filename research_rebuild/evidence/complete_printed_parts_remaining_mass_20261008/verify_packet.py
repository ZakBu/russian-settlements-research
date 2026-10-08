import json,hashlib
from pathlib import Path
import pandas as pd,duckdb,xlrd
Z=Path(__file__).resolve().parent
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
r=json.loads((Z/'candidate_receipt.json').read_text());series=pd.read_csv(Z/'candidate_whole_place_three_census_series.csv',dtype={'oktmo_native_current':str});pts=pd.read_csv(Z/'candidate_own_whole_points.csv',keep_default_na=False);m=pd.read_csv(Z/'candidate_native_constituents.csv');w=pd.read_csv(Z/'actual_raw_source_witnesses.csv');a=pd.read_csv(Z/'two_sided_historical_county_anchors.csv');origin=[];boundary=[]
raw=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');r['source_hash_manifest'][str(raw)]=sha(raw);c=duckdb.connect()
for p in pts.to_dict('records'):
 n=int(p['whole_native2021_source_record_id'].rsplit(':',1)[1]); f=c.execute('select object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement,population,fias_id_dadata,fias_level_dadata,settlement_fias_id_dadata,latitude_dadata,longitude_dadata from read_parquet(?) limit 1 offset ?',[str(raw),n-1]).fetchdf().iloc[0].to_dict();g=series[series.place_id.eq(p['place_id'])&series.year.eq(2021)].iloc[0]
 assert int(f['population'])==g.population and str(f['oktmo'])==str(p['whole_native_oktmo']);assert f['fias_level_dadata']=='6'
 assert abs(f['latitude_dadata']-float(p['latitude']))<1e-9 and abs(f['longitude_dadata']-float(p['longitude']))<1e-9
 origin.append(dict(place_id=p['place_id'],source_record_id=p['whole_native2021_source_record_id'],raw_path=str(raw),raw_sha256=sha(raw),raw_row_1based=n,**f));lp=Path(p['point_ledger_path']);r['source_hash_manifest'][str(lp)]=sha(lp)
for x in a.to_dict('records'):
 p=Path('/workspace/settlements-raw')/'data/raw/2010/013_f60b2d2bcf_5._20Belg_Bryan_Vlad_Voron_Ivanov_Kalug_20L1_ethn_2010.xls';s=xlrd.open_workbook(str(p)).sheet_by_name('Data Sheet');aidx=int(x['anchor2010_source_record_id'].rsplit(':',1)[1]);tidx=int(x['target_source_record_id'].rsplit(':',1)[1]);labels=[]
 for n in range(min(aidx,tidx),max(aidx,tidx)+1):
  vals=s.row_values(n-1);label=str(vals[3]);assert not ('район' in label.lower() or 'городской округ' in label.lower());labels.append(dict(raw_row_1based=n,raw_label=label,raw_region=vals[2],raw_population=vals[4]))
 boundary.append(dict(**x,actual_source_interval_json=json.dumps(labels,ensure_ascii=False),actual_printed_admin_boundary_inside=False))
for p in w[w.source_record_id.str.startswith('2002:')].to_dict('records'):
 b=xlrd.open_workbook(p['raw_source_path']);s=b.sheet_by_name('Sheet1');n=int(p['source_record_id'].rsplit(':',1)[1]);head=next((dict(row=j+1,label=str(s.cell_value(j,1))) for j in range(n-1,-1,-1) if 'район' in str(s.cell_value(j,1)).lower()),None);p['actual_nearest_printed_county_json']=json.dumps(head,ensure_ascii=False);origin.append(p)
pd.DataFrame(origin).to_csv(Z/'actual_native_whole_points_and_old_county_headers.csv',index=False);pd.DataFrame(boundary).to_csv(Z/'actual_raw_county_anchor_interval_checks.csv',index=False)
for i,x in series.iterrows():
 g=m[m.place_id.eq(x.place_id)&m.year.eq(x.year)];p=pts[pts.place_id.eq(x.place_id)].iloc[0]
 series.loc[i,'member_populations_json']=json.dumps(g.population.astype(int).tolist());series.loc[i,'member_source_provenance_json']=json.dumps(w.set_index('source_record_id').loc[g.source_record_id].reset_index().to_dict('records'),ensure_ascii=False)
 series.loc[i,'point_ledger_path']=p.point_ledger_path;series.loc[i,'point_ledger_sha256']=r['source_hash_manifest'][p.point_ledger_path];series.loc[i,'point_ledger_locator']='target_source_record_id='+p.whole_native2021_source_record_id;series.loc[i,'oktmo_native_current']=str(p.whole_native_oktmo);series.loc[i,'point_scope']='whole locality; no individual part coordinate'
 series.loc[i,'direct_historical_coordinate_measurement']=False;series.loc[i,'retrospective_point_use_is_continuity_inference']=int(x.year)!=2021;series.loc[i,'boundary_comparability_asserted']=False;series.loc[i,'modern_boundary_harmonized']=False
series.to_csv(Z/'candidate_whole_place_three_census_series.csv',index=False)
root=Z.parent/'working_full_chain_20261007/coverage_receipt.json';baseline=json.loads(root.read_text());assert baseline['working_stage']==51
for year,metrics in r['baseline_ordinary_metrics'].items():
 axis=baseline['ordinary_axes_by_year'][year]['axes']['point_and_full_three_census_identity'];assert metrics['covered_population']==axis['population'];assert metrics['covered_rows']==axis['rows']
r['baseline51_ordinary_rows_and_population_reproduced']=True;r['baseline51_root_coverage_receipt_sha256']=sha(root);r['actual_raw2021_code_FIAS_ownpoint_bindings_verified']=True;r['actual_source_county_anchor_intervals_verified']=True;r['output_sha256']={p.name:sha(p) for p in Z.glob('*.csv')};(Z/'candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r['conditional_source_ID_union_exclusive_gain']))

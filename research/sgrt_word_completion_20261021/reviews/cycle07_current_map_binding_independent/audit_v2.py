"""Independent exact compact atlas source readback; no producer import or model refit."""
from pathlib import Path
import hashlib,json
import pandas as pd,pyarrow.parquet as pq
R=next(p for p in Path(__file__).resolve().parents if(p/'model').is_dir()and(p/'transport').is_dir());D=R/'maps/cycle07_current_primary_binding_v1';O=Path(__file__).parent

def exact_frame(left,right,**ignored):
 assert left.shape==right.shape and list(left.columns)==list(right.columns)
 assert left.isna().equals(right.isna())
 for column in left:
  mask=left[column].notna()
  assert (left.loc[mask,column].to_numpy()==right.loc[mask,column].to_numpy()).all(),column

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();cfg=json.loads((D/'map_config.json').read_text());receipt=json.loads((D/'binding_receipt.json').read_text());contract=json.loads((R/'maps/cycle07_current_primary_contract_v1.json').read_text());checks=0;cells=0
for name,h in receipt['files'].items():assert sha(D/name)==h;checks+=1
for p,h in receipt['watched_sources'].items():assert sha(p)==h;checks+=1
assert sha(R/'maps/cycle07_current_primary_contract_v1.json')==receipt['source_contract_sha256'];assert cfg['family']=='cycle07_bottomup';assert len(cfg['retained_resolutions'])==9;assert len(cfg['national_map_resolutions'])==4;assert all(cfg['view_metadata'][v]['resolution_kind']=='empirical_resolution'for v in cfg['national_map_resolutions']);checks+=4
bu=pd.read_parquet(D/'units.parquet');bt=pd.read_parquet(D/'types.parquet');bm=pd.read_parquet(D/'memberships.parquet');be=pd.read_parquet(D/'all_trajectory.parquet');assert bu.unit_id.is_unique and bt.unit_id.is_unique;assert len(bu)==258417;assert len(bm)==9*173858
for key in ['units','types']:
 exact_frame(pd.read_parquet(D/(key+'.parquet')),pd.read_parquet(D/('all_'+key+'.parquet')));checks+=1
for v in contract['views']:
 vid=v['view_id'];part=bu[bu.level.eq(vid)].reset_index(drop=True);schema=set(pq.ParquetFile(v['units']['path']).schema_arrow.names);cols=[c for c in part.columns if c in schema and c!='level'];s=pd.read_parquet(v['units']['path'],columns=cols);assert part.unit_id.tolist()==s.unit_id.tolist();exact_frame(part[cols],s,check_dtype=False);checks+=2;cells+=s.size
 if 'unit_name'not in schema and'name'in schema:pd.testing.assert_series_equal(part.unit_name,s['name'],check_names=False);checks+=1
 ids=set(part.unit_id);source_t=pd.read_parquet(v['types']['path']);bound_t=bt[bt.unit_id.isin(ids)].reset_index(drop=True);exact_frame(bound_t,source_t,check_dtype=False);checks+=1;cells+=source_t.size
 source_m=pd.read_parquet(v['memberships']['path'],columns=['unit_id','id','is_overlay_membership']);bound_m=bm[bm.unit_id.isin(ids)].reset_index(drop=True);exact_frame(bound_m,source_m,check_dtype=False);assert len(bound_m)==173858 and bound_m.id.is_unique and not bound_m.is_overlay_membership.any();checks+=3;cells+=source_m.size
 source_e=pd.read_parquet(v['trajectory']['path']);bound_e=be[be.unit_id.isin(ids)].reset_index(drop=True);exact_frame(bound_e,source_e,check_dtype=False);checks+=1;cells+=source_e.size
 for key in ['normalization_admission','typology_admission']:
  a=json.loads(Path(v[key]['path']).read_text());assert a['all_checks_passed'] and str(a['status']).startswith('ACCEPTED');checks+=1
 assert cfg['view_metadata'][vid]==v['semantics'];assert cfg['view_metadata'][vid]['source_sha256']==sha(v['units']['path']);assert receipt['all_view_unit_counts'][vid]==len(part);checks+=3
raw=R/'model/cycle07_scale_hierarchy/source477_adminall_v2/output_primary_v1';expected=pd.concat([pd.read_parquet(raw/f'cap_{cap:03d}_objective_curve.parquet')for cap in [30,45,60,90,120]],ignore_index=True);exact_frame(pd.read_parquet(D/'merge_diagnostics.parquet'),expected);checks+=1;cells+=expected.size
expected=pd.read_csv(raw/'candidate_knee_summary.csv').rename(columns={'status':'knee_status'}).merge(pd.read_csv(raw/'retained_resolution_stability.csv').rename(columns={'accepted':'retained'}),on='candidate_cap',validate='one_to_one');exact_frame(pd.read_parquet(D/'knee_diagnostics.parquet'),expected,check_dtype=False);checks+=1;cells+=expected.size
exact_frame(pd.read_parquet(D/'bootstrap_diagnostics.parquet'),pd.read_parquet(raw/'all_50_bootstrap_ledger.parquet'));checks+=1;cells+=250*12
cols=['id','name','lat','lon','population_2021','source_record_id_2021','source2021_effective_settlement_type','source2021_role_has_dated_source','is_additive_source_unit'];source=pd.read_parquet(contract['nodes']['path'],columns=cols);nodes=pd.read_parquet(D/'nodes.parquet');exact_frame(nodes[cols[:6]],source[cols[:6]]);expected=source.source2021_effective_settlement_type.eq('город')&source.source2021_role_has_dated_source.eq(True)&source.source_record_id_2021.notna()&source.is_additive_source_unit.eq(True);pd.testing.assert_series_equal(nodes.formal_city2021,expected,check_names=False);checks+=2;cells+=nodes.size
for name,s in cfg['sources'].items():assert sha(s['path'])==s['sha256'];checks+=1
result={'status':'ACCEPTED_EXACT_CURRENT_NINE_VIEW_CARTOGRAPHIC_SOURCE_BINDING','all_checks_passed':True,'independent_checks':checks,'independently_compared_source_cells':cells,'config_sha256':sha(D/'map_config.json'),'binding_receipt_sha256':sha(D/'binding_receipt.json'),'source_contract_sha256':sha(R/'maps/cycle07_current_primary_contract_v1.json'),'review_code_sha256':sha(Path(__file__)),'exact_nonnull_scalar_equality_and_identical_null_masks':True,'n_view_units':len(bu),'n_view_memberships':len(bm),'scope':'Exact source coordinates/formal-city flag, every retained unit field/type/member/trajectory cell, all9source admissions/semantics, true curve/knee/all250bootstrap diagnostics and every source SHA. No producer imported, no new model validation claim. Renderer and actual page visual acceptance separate.'};(O/'source_admission_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result))

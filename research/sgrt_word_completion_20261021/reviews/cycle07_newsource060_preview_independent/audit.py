from pathlib import Path
import json,hashlib,importlib.util
import pandas as pd,numpy as np
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'maps/cycle07_newsource060_preview_binding_v1';O=B/'reviews/cycle07_newsource060_preview_independent';r=json.loads((P/'binding_receipt.json').read_text());c=json.loads((P/'map_config.json').read_text());checks=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ck(k,v,d=None):checks.append({'check':k,'passed':bool(v),'detail':d})
for p,h in r['source_pins'].items():ck('source_pin_'+p,sha(Path(p))==h)
for p,h in r['files'].items():ck('projection_pin_'+p,sha(P/p)==h)
base=Path(next(p for p in r['source_pins']if p.endswith('effective_full_nodes.parquet')));norm=Path(next(p for p in r['source_pins']if p.endswith('normalized_units.parquet')));typ=Path(next(p for p in r['source_pins']if p.endswith('complete_typology.parquet')));mem=Path(next(p for p in r['source_pins']if p.endswith('memberships_scoped.parquet')))
for name,source in [('units',norm),('types',typ),('memberships',mem)]:
 target=pd.read_parquet(P/(name+'.parquet'));src=pd.read_parquet(source);bad=[]
 for col in target:
  if col=='level':continue
  try:pd.testing.assert_series_equal(target[col].reset_index(drop=True),src[col].reset_index(drop=True),check_names=False,check_dtype=False,check_exact=True)
  except (AssertionError,KeyError):bad.append(col)
 ck('ALL_source_cells_'+name,not bad,bad)
n=pd.read_parquet(P/'nodes.parquet');cols=['id','name','lat','lon','population_2021','source_record_id_2021','source2021_effective_settlement_type','source2021_role_has_dated_source','is_additive_source_unit'];src=pd.read_parquet(base,columns=cols)
for col in ['id','name','lat','lon','population_2021','source_record_id_2021']:
 try:pd.testing.assert_series_equal(n[col],src[col],check_dtype=False,check_names=False,check_exact=True);ok=True
 except AssertionError:ok=False
 ck('ALL173864_source_nodes_'+col,ok)
formal=src.source2021_effective_settlement_type.eq('город')&src.source2021_role_has_dated_source.eq(True)&src.source_record_id_2021.notna()&src.is_additive_source_unit.eq(True);ck('datedformal_city_source_rule',np.array_equal(n.formal_city2021,formal))
for spec in c['independent_admissions']:
 p=Path(spec['path']);a=json.loads(p.read_text());ck('actual_accepted_admission_'+p.parent.name,sha(p)==spec['sha256']and a.get('all_checks_passed')is True and a.get('n_failed',0)==0 and a['status']==spec['expected_status'])
view=c['retained_resolutions'][0];meta=c['view_metadata'][view];ck('operational60_NOT_empirical_level',c['status']=='ACTUAL_NEWSOURCE060_PREVIEW_ONLY_NOT_FULL_ATLAS'and meta['resolution_kind']=='operational_forest'and meta['registry_level']is None and meta['candidate_cap']==60 and meta['partition_role']=='supported_end_forest')
sp=importlib.util.spec_from_file_location('admitted_v6',B/'maps/cycle07_tools/render_atlas_v6.py');mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod);nn,u,z,watch=mod.load(c,require_admission=True);co=n.set_index('id').loc[z.id];ck('every_member_coordinate_exact_SOURCE_NOTcore',np.array_equal(z.lat.to_numpy(),co.lat.to_numpy(),equal_nan=True)and np.array_equal(z.lon.to_numpy(),co.lon.to_numpy(),equal_nan=True));valid=np.isfinite(co.lat)&np.isfinite(co.lon)&co.lat.between(-90,90)&co.lon.between(-180,180);x,y=mod.T.transform(co.loc[valid,'lon'].to_numpy(),co.loc[valid,'lat'].to_numpy());ck('every_actual_projected_point_exact',np.array_equal(z.loc[valid.to_numpy(),'_x'],x)and np.array_equal(z.loc[valid.to_numpy(),'_y'],y));ck('full26705units46types173858members',len(u)==26705 and u.primary_type_id.nunique()==46 and len(z)==173858 and z.id.is_unique and u.unit_id.is_unique);ck('all477_source_coordinates_integrated',int(valid.sum())==155782 and int((~valid).sum())==18076)
wrapper=B/'maps/cycle07_tools/render_newsource060_preview_v1.py';ck('wrapper_scientific_scope_explicit',all(t in wrapper.read_text()for t in ['Операционный дорожный охват 60 минут; не эмпирическая ступень','477 координат','353 новых первичных','сам должен удовлетворять','len(z)','u.primary_type_id.nunique()']))
out={'status':'ACCEPTED_CURRENT_PRIMARY_OPERATIONAL060_PREVIEW_BINDING','all_checks_passed':all(q['passed']for q in checks),'n_checks':len(checks),'n_failed':sum(not q['passed']for q in checks),'checks':checks,'accepted_config_sha256':sha(P/'map_config.json'),'accepted_binding_receipt_sha256':sha(P/'binding_receipt.json'),'accepted_renderer_sha256':sha(B/'maps/cycle07_tools/render_atlas_v6.py'),'accepted_wrapper_sha256':sha(wrapper),'coordinate_coverage':{'all_members':len(z),'with_coordinates':int(valid.sum()),'without_coordinates':int((~valid).sum())},'scope':'Actual NEW477 dominant-core source frame/normalized26705 units/46types/member173858 projections/sourcepoint coordinates and current source admissions checked independently. Wrapper source captions and operational60 scope correct. Rendering allowed for concrete review artifact; actual PNG/PDF visual/numeric review required and no substitution for four empirical levels or full operational supplement.'};(O/'admission.json').write_text(json.dumps(out,indent=2)+'\n');print(out['all_checks_passed'],out['n_checks'],out['n_failed']);print([q for q in checks if not q['passed']])

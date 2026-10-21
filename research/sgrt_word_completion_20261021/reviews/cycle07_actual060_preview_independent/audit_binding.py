from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,importlib.util
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'maps/cycle07_actual060_preview_binding_v3';O=B/'reviews/cycle07_actual060_preview_independent';checks=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ck(k,v,d=None):checks.append(dict(check=k,pass_=bool(v),detail=d))
r=json.loads((P/'binding_receipt.json').read_text());c=json.loads((P/'map_config.json').read_text());u=pd.read_parquet(P/'units.parquet');t=pd.read_parquet(P/'types.parquet');m=pd.read_parquet(P/'memberships.parquet');n=pd.read_parquet(P/'nodes.parquet')
for name,target in [('source_normalized_units',u),('source_types',t),('source_memberships',m)]:
 s=r[name];ck(name+':actualsourceSHA',sha(s['path'])==s['sha256']);source=pd.read_parquet(s['path']).reset_index(drop=True);bad=[]
 for col in target:
  if col=='level':continue
  if col not in source:bad.append(col);continue
  try:pd.testing.assert_series_equal(target[col].reset_index(drop=True),source[col],check_names=False,check_dtype=False,check_exact=True)
  except AssertionError:bad.append(col)
 ck(name+':allprojectedcells_exact',not bad,bad)
ck('all28501units_types46exactkeys',len(u)==len(t)==28501 and u.unit_id.equals(t.unit_id)and u.unit_id.is_unique and t.primary_type_id.nunique()==46);ck('173858members_exactonce_173856ordinary2ctx',len(m)==173858 and m.id.is_unique and m.id.str.startswith('ctx:').sum()==2);view='primary_cap060_supported_end_forest';ck('derivedlevel_ONLYoperational_view',u.level.eq(view).all()and c['retained_resolutions']==[view]and c['view_metadata'][view]['kind']=='operational_forest');source=pd.read_parquet(r['source_base_nodes']['path'],columns=['id','name','lat','lon','population_2021','source_record_id_2021','source2021_effective_settlement_type','source2021_role_has_dated_source','is_additive_source_unit']);ck('fulloldsourcecoordinateframe173864_sourceSHA',sha(r['source_base_nodes']['path'])==r['source_base_nodes']['sha256']and len(n)==173864)
for col in ['id','name','lat','lon','population_2021','source_record_id_2021']:
 try:pd.testing.assert_series_equal(n[col],source[col],check_dtype=False,check_names=False,check_exact=True);ok=True
 except AssertionError:ok=False
 ck('all_source_nodes_'+col,ok)
formal=source.source2021_effective_settlement_type.eq('город')&source.source2021_role_has_dated_source.eq(True)&source.source_record_id_2021.notna()&source.is_additive_source_unit.eq(True);ck('datedformalcityrule_exact',np.array_equal(n.formal_city2021,formal));ck('fulltype_oldgeometry_NEWprimarynotclaimed',c['status']=='ACTUAL060_PREVIEW_ONLY_NOT_ALL5_ALL50_ATLAS'and '477' in str(c['component_integration_status'])and 'доминант' in str(c['component_integration_status']))
for name,spec in c['sources'].items():ck('all_boundsourceSHA_'+name,sha(spec['path'])==spec['sha256'])
for spec in c['independent_admissions']:
 f=Path(spec['path']);d=json.loads(f.read_text());status=d
 for key in spec['status_pointer']:status=status[key]
 ck('accepted_source_admission_'+f.parent.name,sha(f)==spec['sha256']and status==spec['expected_status']and 'ACCEPT' in status and d.get('all_checks_passed')is True and d.get('n_failed',0)==0)
sp=importlib.util.spec_from_file_location('atlasV5',B/'maps/cycle07_tools/render_atlas_v5.py');mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod);nn,uu,z,watch=mod.load(c,require_admission=True);coords=n.set_index('id').loc[z.id];ck('all173858_memberpoints_NOTcore_shadow',np.array_equal(z.lat.to_numpy(),coords.lat.to_numpy(),equal_nan=True)and np.array_equal(z.lon.to_numpy(),coords.lon.to_numpy(),equal_nan=True));valid=np.isfinite(coords.lat)&np.isfinite(coords.lon)&coords.lat.between(-90,90)&coords.lon.between(-180,180);x,y=mod.T.transform(coords.loc[valid,'lon'].to_numpy(),coords.loc[valid,'lat'].to_numpy());ck('all_actual_projectedmembercoordinates_exact',np.array_equal(z.loc[valid.to_numpy(),'_x'],x)and np.array_equal(z.loc[valid.to_numpy(),'_y'],y));counts={'all_members':len(z),'with_coordinates':int(valid.sum()),'without_coordinates':int((~valid).sum())};ck('knownandunknown_sourcepoints_both_retained',len(z)==173858 and 0<counts['without_coordinates']<len(z));sourcecols=['structural_class','unit_role','primary_type_id','trajectory_class','classification_confidence']
for col in sourcecols:ck('all_loaded_typefield_'+col,uu[col].equals(t[col]))
for name,h in r['files'].items():ck('all_projectionoutputSHA_'+name,sha(P/name)==h)
res=dict(status='ACCEPTED_ACTUAL060_PREVIEW_BINDING_ONLY'if all(x['pass_']for x in checks)else'REJECTED',all_checks_passed=all(x['pass_']for x in checks),n_checks=len(checks),n_failed=sum(not x['pass_']for x in checks),checks=checks,accepted_config_sha256=sha(P/'map_config.json'),accepted_binding_receipt_sha256=sha(P/'binding_receipt.json'),accepted_renderer_sha256=sha(B/'maps/cycle07_tools/render_atlas_v5.py'),accepted_preview_code_sha256=sha(B/'maps/cycle07_tools/render_actual060_preview_v2.py'),coordinate_coverage=counts,scope='Fullactual28501unit/type and173858membership projections/source535→compactpoint fields comparedallcells; allmembersprojectedusingSOURCEpoints notcorecoordinates, typefieldsretained. CorrectedV3unknownnonfocalcontextwholepolicy. Oldgeometry-feasible-core checkpoint+353new2010 source; NOTnewdominantcore477integratedfinalprimary, notall5/all50finalatlas. Renderpreviewallowed; actualPNG/PDFnumericlayoutvisualreview remainsseparate.');(O/'binding_admission.json').write_text(json.dumps(res,indent=2)+'\n');print(res['status'],res['n_checks'],res['n_failed'],counts);print([x for x in checks if not x['pass_']])

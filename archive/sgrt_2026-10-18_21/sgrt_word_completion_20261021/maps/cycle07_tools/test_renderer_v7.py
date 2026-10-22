"""Synthetic schema, accounting and actual raster/PDF smoke checks; no research outcomes."""
import importlib.util,json,tempfile,shutil
from pathlib import Path
import pandas as pd,numpy as np,fitz
P=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('atlas_renderer',P/'render_atlas_v7.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
def fixture(h):
 n=pd.DataFrame({'id':['np3:a','np3:b','np3:c','np3:d'],'name':['Синтетический А','Синтетический Б','Синтетический В','Без координат'],'lat':[55,55.1,56,np.nan],'lon':[37,37.2,39,np.nan],'population_2021':[2000000,1000001,200,0],'formal_city2021':[True,True,False,False],'source_record_id_2021':['2021:a','2021:b','2021:c','2021:d']})
 u=pd.DataFrame({'unit_id':['u1','u2','u3'],'level':['0','0','1'],'core_id':['np3:a','np3:c','np3:a'],'kind':['functional_union','atomic_settlement','functional_union'],'lat':[10.,11.,12.],'lon':[20.,21.,22.],'n_children':[0,0,2],'parent_unit_id':['u3','u3',None],'max_member_direct_minutes':[4,0,55],'max_member_geodesic_km':[20,0,150],'extent_complete':[True,False,False]})
 m=pd.DataFrame({'unit_id':['u1','u1','u2','u2','u3','u3','u3','u3'],'id':['np3:a','np3:b','np3:c','np3:d']*2,'is_overlay_membership':[False]*8})
 ty=pd.DataFrame({'unit_id':u.unit_id,'primary_type_id':['T1','T2','T3'],'primary_type_name':['Рост ядра','Структурный тип без траектории','Смешанный'],'structural_class':['Моно','Атом','Поли'],'trajectory_class':['{"center":"growth","rural":"decline","system":"stable"}','{"own":"unavailable"}','{"center":"stable","rural":"growth","system":"growth"}'],'unit_role':['territorial_unit','protected_carry','territorial_unit'],'primary2010_population_share':[1,.2,.8],'protected_secondary2010_population_share':[0,.8,.2],'population2010_known_denominator':[100,100,200],'2010_missing_population_count':[0,1,1],'population_quality_share_denominator_scope':['known_additive_member_population']*3})
 merge=pd.DataFrame({'candidate_cap':[30]*3,'merge_index':[0,1,2],'Q':[-.3,.1,.2]});knee=pd.DataFrame({'candidate_cap':[30],'knee_status':['no-knee'],'retained':[False],'median_ari':[np.nan]});boot=pd.DataFrame({'candidate_cap':[30]*50,'replicate_id':range(50),'status':['meaningful']*40+['no-knee']*10,'assessable':[True]*40+[False]*10,'ari':[.9]*40+[np.nan]*10})
 cfg={'family':'cycle07_bottomup','retained_resolutions':['0','1'],'zoom_resolution':'1','sources':{},'view_metadata':{'0':{'label':'Проверка переноса длинного заголовка: географическое размещение поселений и демографические сочетания центра и сельского окружения при охвате60 минут'},'1':{'label':'Другой фактический вариант'}},'dpi':50,'component_integration_status':{'source':'SYNTHETIC_ONLY'},'population_frame_scope':{'source_rows':4,'partition_rows':4}}
 for k,d in [('nodes',n),('units',u),('memberships',m),('types',ty),('merge_diagnostics',merge),('knee_diagnostics',knee),('bootstrap_diagnostics',boot)]:
  p=h/f'{k}.parquet';d.to_parquet(p,index=False);cfg['sources'][k]={'path':str(p),'sha256':r.sha(p)}
 links=pd.DataFrame({'unit_id_lower':['u1','u2'],'unit_id_upper':['u3','u3'],'lower_empirical_level':[0,0],'upper_empirical_level':[1,1]});p=h/'geo_links.parquet';links.to_parquet(p,index=False);cfg['sources']['geographic_parent_links']={'path':str(p),'sha256':r.sha(p)}
 return cfg
with tempfile.TemporaryDirectory(prefix='sgrt_atlas_synthetic_') as tmp:
 h=Path(tmp);cfg=fixture(h);n,u,z,w=r.load(cfg);checks={'all_types_exact':len(u)==3,'missing_coordinate_retained':int((~z._coordinate_valid).sum())==2,'roles_preserved':set(u.unit_role)=={'territorial_unit','protected_carry'}}
 source_coords=n.set_index('id').loc[z.id];checks['member_coords_never_shadowed_by_core']=np.allclose(z.lat,source_coords.lat,equal_nan=True) and np.allclose(z.lon,source_coords.lon,equal_nan=True) and np.allclose(z.member_lat,z.lat,equal_nan=True) and np.allclose(z.member_lon,z.lon,equal_nan=True)
 valid=z._coordinate_valid;xx,yy=r.T.transform(source_coords.loc[valid.to_numpy(),'lon'].to_numpy(),source_coords.loc[valid.to_numpy(),'lat'].to_numpy());checks['every_member_projected_source_point']=np.allclose(z.loc[valid,'_x'],xx) and np.allclose(z.loc[valid,'_y'],yy)
 for label,mut in [('old_family',lambda c:c.update(family='cycle06')),('wrong_levels',lambda c:c.update(retained_resolutions=['1']))]:
  c=json.loads(json.dumps(cfg));mut(c)
  try:r.load(c);checks[label+'_rejected']=False
  except ValueError:checks[label+'_rejected']=True
 try:r.load(cfg,require_admission=True);checks['unaccepted_actual_render_rejected']=False
 except ValueError:checks['unaccepted_actual_render_rejected']=True
 # Source-contract negative cases bind changed synthetic tables withtheirnewSHA.
 for label,key,mut in [('missing_type','types',lambda d:d.iloc[:-1]),('double_primary','memberships',lambda d:pd.concat([d,d.iloc[[0]]],ignore_index=True)),('zero_denominator_share','types',lambda d:d.assign(population2010_known_denominator=0)),('string_overlay','memberships',lambda d:d.assign(is_overlay_membership='False'))]:
  c=json.loads(json.dumps(cfg));d=r.read_table(c['sources'][key]);p=h/f'{label}.parquet';mut(d).to_parquet(p,index=False);c['sources'][key]={'path':str(p),'sha256':r.sha(p)}
  try:r.load(c);checks[label+'_rejected']=False
  except ValueError:checks[label+'_rejected']=True
 # Render real matplotlib/PDF paths using ONLY the labeled in-memory synthetic input.
 out=h/'out';out.mkdir();a=r.Atlas(out,n,u,z,cfg,w)
 try:a.diagnostics();a.national('0');a.national('1');a.national_trajectories('0');a.national_trajectories('1');a.zooms()
 finally:a.close()
 preview=P/'synthetic_preview_v7';preview.mkdir(exist_ok=True)
 for page in a.pages:
  if page['kind'] in ['source_quality','native_source_frame','national_12','city_zoom_1'] or page['kind'].startswith('national_trajectory_'):shutil.copyfile(out/page['png'],preview/page['png'])
 doc=fitz.open(out/'atlas_cycle07.pdf');checks['real_pdf_png_count']=len(doc)==len(a.pages)==len(list(out.glob('*.png')));checks['cyrillic_text_in_pdf']='потенциальные' in ''.join(p.get_text() for p in doc).lower();checks['all50_bootstraps_saved']=len(pd.read_csv(out/'all_bootstrap_outcomes.csv'))==50;checks['all_type_codes_saved']=set(pd.read_csv(out/'type_counts.csv').primary_type_id)=={'T1','T2','T3'}
 checks['zoom_full_members_missing_coords_retained']=a.pages[-1]['selections'][0]['n_members']==4
 checks['all7_atomic_states_preserved']=all(r.trajectory_summary(json.dumps({'own':st}),True)=='own:'+st for st in r.OWN_COLORS)
 checks['bivariate_zero_unknown_norural_distinct']=len({r.trajectory_summary(json.dumps({'center':'stable','rural':st})) for st in ['observed_zero_both','unavailable','not_applicable']})==3
 checks['unknown_not_stable']=r.trajectory_summary('{"center":"growth","rural":"unavailable"}')=='unavailable_pair'
 checks['all9_bivariate_combinations']={r.trajectory_summary(json.dumps({'center':a,'rural':b})) for a in ['growth','stable','decline'] for b in ['growth','stable','decline']}=={a+'|'+b for a,b in r.BIVARIATE}
 checks['every_title_within_page_fixed16pt']=all(x['title_bbox_within_page'] and x['title_font_points']==16 for x in a.pages)
 checks['meaningful_long_title_wrapped']=any('\n' in x['wrapped_title'] for x in a.pages)
 index=pd.read_csv(out/'machine_map_index.csv');checks['machine_index_every_page']=len(index)==len(a.pages) and set(['resolution_kind','registry_level','candidate_cap','partition_role','source_sha256'])<=set(index);checks['geographic_children_from_actuallinks']=pd.read_csv(out/'actual_geographic_parent_links.csv.gz').unit_id_upper.value_counts().to_dict()=={'u3':2};refs=[q['cartographic_reference']for page in a.pages if page['kind'].startswith('city_zoom')for q in page['selections']];checks['scale_bar_true_geodesic_not_projection_distance']=len(refs)>0 and all(abs(v['distance_km']-v['measured_geodesic_km'])<1e-8 for v in refs)
 assert all(checks.values()),checks
 (P/'synthetic_test_receipt_v7.json').write_text(json.dumps({'status':'SYNTHETIC_ONLY_PASS_NOT_ACTUAL_ATLAS','checks':checks,'actual_research_inputs_read':False,'rendered_pages':len(doc),'renderer_sha256':r.sha(P/'render_atlas_v7.py')},ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,ensure_ascii=False))

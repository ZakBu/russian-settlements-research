from pathlib import Path
import json,hashlib
import pandas as pd
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');O=B/'reviews/cycle07_actual_report_binding_independent';I=B/'delivery/cycle07_current_primary_v1/report_source_inventory_v1.json';C=B/'delivery/cycle07_current_primary_v1/report_inputs_PENDING_v1.json';i=json.loads(I.read_text());c=json.loads(C.read_text());checks=[]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for x in iter(lambda:f.read(8388608),b''):h.update(x)
 return h.hexdigest()
def path(x):return Path(x)if Path(x).is_absolute()else B/x
def ck(k,v,d=None):checks.append({'check':k,'passed':bool(v),'detail':d});assert v,(k,d)
startsha=sha(I)
for role,s in i['files'].items():ck('actual_inventory_SHA_'+role,sha(path(s['path']))==s['sha256'])
ck('held_report_V6_source',sha(B/'delivery/cycle07_tools/build_report_v6.py')=='4be8b658a7a8ffa487cd946241a21434b154f12fd80671969cbbf435adb61321')
for role,rel in i['evidence'].items():
 p=path(rel);d=json.loads(p.read_text());ck('prior_source_admission_'+role,d.get('all_checks_passed')is True or(d.get('n_failed')==0 and str(d.get('status','')).startswith('ACCEPTED')))
 ck('evidence_exists_'+role,p.is_file())
idxp=B/'reviews/cycle07_typology_independent/all9_current477_review_index.json';idx=json.loads(idxp.read_text());ck('all9source_type_index_actual',idx['all_checks_passed']and idx['n_views']==9)
sourcehashes=[]
for v in idx['views']:
 sourcehashes.append(v['source_units_sha256'])
 for role in ['source_audit','type_audit']:
  p=path(v[role]['path']);d=json.loads(p.read_text());ck('current_'+v['view_id']+'_'+role,sha(p)==v[role]['sha256']and d['all_checks_passed']is True and d.get('n_failed',0)==0)
ck('all9_normalized_source_hashset',len(i['all_normalized_source_unit_sha256s'])==9 and set(i['all_normalized_source_unit_sha256s'])==set(sourcehashes))
u=pd.read_parquet(path(i['files']['units']['path']));t=pd.read_parquet(path(i['files']['types']['path']));e=pd.read_parquet(path(i['files']['trajectory']['path']));view=c['view_column'];ck('actual_viewcolumn',view=='operational_view_id'and view in u);ck('all_actualview_semantics',set(u[view])==set(c['view_semantics'])=={v['view_id']for v in idx['views']});ck('all_unit_type_exactIDs_once',u.unit_id.is_unique and t.unit_id.is_unique and set(u.unit_id)==set(t.unit_id));ck('all_units_typed',t.primary_type_id.notna().all());ck('all_trajectory_IDs_in_unitframe',e.unit_id.isin(u.unit_id).all());ck('actual258417viewrows',len(u)==258417)
for v in idx['views']:
 z=u[u[view].eq(v['view_id'])];ck('actual_scope_count_'+v['view_id'],len(z)==v['n_units']);sem=c['view_semantics'][v['view_id']];ck('actual_semantics_'+v['view_id'],sem==v['semantics']);ck('actual_sourcehash_'+v['view_id'],sem['source_sha256']==v['source_units_sha256'])
# Root's exact36million-cell projection proof is independently source-bound by the actual map config/receipt.
mr=json.loads(path(i['evidence']['map_source_admission']).read_text());binding=path(i['files']['typology_receipt']['path']);ck('exact_map_combined_projection_subject',mr['binding_receipt_sha256']==sha(binding)and mr['n_view_units']==len(u));bt=json.loads(binding.read_text());bindingtext=binding.read_text()
for role in ['units','types','trajectory','knees','bootstrap']:ck('map_binding_pins_actual_'+role,i['files'][role]['sha256']in bindingtext)
boot=pd.read_parquet(path(i['files']['bootstrap']['path']));knees=pd.read_parquet(path(i['files']['knees']['path']));ck('all250diagnosticrows',len(boot)==250 and boot.groupby('candidate_cap').size().eq(50).all());ck('all5candidatecaps',set(boot.candidate_cap)==set(knees.candidate_cap)=={30,45,60,90,120});ck('primary60_is_operational',c['primary_view_id'].endswith('cap060_supported_end_forest')and c['view_semantics'][c['primary_view_id']]['kind']=='operational_forest')
ck('current_source_frame_denoms',c['population_frame_scope']['full_source_view_rows']==173864 and c['population_frame_scope']['geographic_partition_rows']==173858 and c['population_frame_scope']['context_partition_rows']==2 and c['population_frame_scope']['excluded_nonadditive_source_rows']==6)
# Recheck all4 completed estimate-source-review chains; every normalized source subject is bound.
metrics=[];covered=[]
for run in c['analysis_runs']:
 a={k:i['files'][run[k]]for k in ['metrics_role','receipt_role','source_role','numeric_review_role']};r=json.loads(path(a['receipt_role']['path']).read_text());n=json.loads(path(a['numeric_review_role']['path']).read_text());src=path(a['source_role']['path']);ck('exact_actualrun_numericalreview_'+run['receipt_role'],n['all_checks_passed']and n['accepted_analysis_receipt_sha256']==sha(path(a['receipt_role']['path'])));ck('exact_actualrun_source_'+run['receipt_role'],r['source_receipt_sha256']==sha(src)and r['source_inputs_unchanged']is True)
 for h in run['source_unit_sha256s']:ck('actualrun_unit_subject_'+h,h in src.read_text()and h in sourcehashes);covered.append(h)
 m=pd.read_csv(path(a['metrics_role']['path']));m['analysis_scope_label']=run['label'];metrics.append(m)
ck('all9analysis_source_subjects_once',len(covered)==9 and set(covered)==set(sourcehashes));m=pd.concat(metrics,ignore_index=True);ck('all177fitrows',len(m)==177);ck('no_pooled_view_scenario_modelkeys',not m.duplicated(['analysis_scope_label','candidate_cap','comparison_family','scenario','model']).any());ck('operational_and_empirical_labels_distinct',set(m.analysis_scope_label)=={'Операционные районы','Вложенные разрешения'})
sp=pd.read_csv(path(i['files']['spatial_summary']['path']));ck('sourceexisting90primary_rural_diagnostics',len(sp)==90 and sp.groupby(['partition_family','candidate_cap','scenario','comparison_family','model']).size().eq(1).all());ck('actual_positive_spatialresiduals',sp.group_oof_moran_i.gt(0).all()and sp.group_oof_two_sided_permutation_p.le(.05).all())
wc=path(i['files']['word_crosswalk']['path']);wa=json.loads(path(i['evidence']['word_crosswalk_admission']).read_text());ck('parent_accepted_crosswalk_subject',wa['all_checks_passed']and wa['accepted_reader_csv_sha256']==sha(wc));ck('all9crosswalkrows',len(pd.read_csv(wc))==9)
sc=pd.read_csv(path(i['files']['sensitivity_comparison']['path']));ck('all6methodpaths_62comparisons',len(sc)==62 and sc.scenario.nunique()==6);ck('no_sensitivity50_claim',not sc.bootstrap50_computed_for_sensitivity.any())
ck('source2010exact353changes',len(pd.read_parquet(path(i['files']['source2010_changes']['path'])))==353);ck('approved_coordinate477only',len(pd.read_parquet(path(i['files']['coordinate_changes']['path'])))==477)
atlas=path(i['files']['atlas_receipt']['path']);a=json.loads(atlas.read_text());ck('actualatlas_binds_exactcombinedsource',i['files']['units']['sha256']in atlas.read_text()and i['files']['types']['sha256']in atlas.read_text())
for role in ['map_hierarchy','map_types','map_coverage']:ck('actual_selectedmap_in_closedatlas_'+role,i['files'][role]['sha256']in atlas.read_text())
ck('computed_source_status',json.loads(path(i['files']['analysis_status']['path']).read_text())['status']=='COMPUTED_CYCLE07_SOURCE_BOUND');ck('integration_current477_dominantcore',bool(c['component_integration_status'])and '477' in str(c['component_integration_status'])and 'Челябинск' in str(c['component_integration_status']))
ck('source_manifest_unchanged',sha(I)==startsha)
rec={'status':'ACCEPTED_ACTUAL_REPORT_SOURCE_BINDING_FOR_PRELIMINARY_REVIEWDRAFT','all_checks_passed':True,'n_failed':0,'n_checks':len(checks),'accepted_source_manifest_sha256':sha(I),'accepted_report_code_sha256':sha(B/'delivery/cycle07_tools/build_report_v6.py'),'accepted_source_files':i['files'],'all_normalized_source_unit_sha256s':sourcehashes,'checks':checks,'scope':'Actual current report inventory: all source bytes/admission subjects, exact nine-view combined source/type projection, all258417typedunit rows, all250stability witnesses, all177accepted fits in four separate source families, all9normalized subjects, sixbaseline-only sensitivities,353primary2010changes,477coordinates and parent-admitted Word interpretation crosswalk checked. Actual closed atlas and selected source-derived PNG bytes bound; this is source/execution approval, not final map/report visual approval or proof of functional orders/commuting/causal mechanisms. Report contract may add only these exact inventory manifest/admission pointers; final input config, generated PDF/DOCX/brief and everypage visual review remain separately inspectable.'};f=O/'admission.json';assert not f.exists();f.write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');print('ACCEPTED',len(checks),sha(f),sha(I))

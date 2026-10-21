from pathlib import Path
import json,hashlib,pandas as pd,numpy as np,fitz
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');M=B/'model/output_cycle06_access_v2_baseline';P=B/'maps/cycle06_access_v2_baseline_v4';C=B/'typology/canonical_cycle06/output_cycle06_access_v2_baseline';j=json.loads((P/'map_manifest.json').read_text());checks=[]
def ck(k,v):checks.append({'check':k,'pass':bool(v)})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for fn,h in j['input_sha256'].items():ck('map_actual_source_'+Path(fn).name,sha(Path(fn))==h)
n=pd.read_parquet(M/'nodes.parquet',columns=['id','_population_axis_row']);m=pd.read_parquet(M/'memberships.parquet');s=pd.read_parquet(M/'systems.parquet');c=pd.read_parquet(M/'candidate_centers.parquet');t=pd.read_parquet(C/'word_type_hypotheses.parquet');conf=pd.read_parquet(M/'system_configurations.parquet');access=pd.read_parquet(M/'network_accessibility.parquet');ck('18_figures_and_atlas_pages',len(j['figures'])==18 and j['atlas']['pages']==18 and len(fitz.open(P/'SGRT_CYCLE06_MODEL_ATLAS.pdf'))==18);ck('actual_atlas_pdf_hash',sha(P/'SGRT_CYCLE06_MODEL_ATLAS.pdf')==j['atlas']['sha256'])
for fig in j['figures']:
 f=fig['figure'];v=fig['statistics'];lev=v.get('level');expected=None
 if f=='01_centers':expected={'centers':len(c),'ranks':{str(k):int(v) for k,v in c.intrinsic_empirical_rank.value_counts().sort_index().items()}}
 elif f.startswith('02_membership'):expected={'level':lev,'systems':int(s.level.eq(lev).sum()),'assigned_population_units':int((m[f'center_id_l{lev}'].notna()&m._population_axis_row).sum())}
 elif f.startswith('03_word_types'):
  z=t[t.level.eq(lev)&t.operational_hypothesis];expected={'level':lev,'candidate_center_type_pairs':len(z),'by_type':{str(k):int(v) for k,v in z.word_type.value_counts().sort_index().items()}}
 elif f.startswith('04_dynamics'):
  z=t[t.level.eq(lev)].drop_duplicates(['level','center_id']);expected={'level':lev,'numeric_complete_pairs':int((z.population_pair_complete&np.isfinite(z.center_annual_rate)&np.isfinite(z.rural_annual_rate)).sum()),'all_systems':int(s.level.eq(lev).sum())}
 elif f.startswith('06_configuration'):
  z=conf[conf.level.eq(lev)];expected={'level':lev,**{col:z[col].value_counts().to_dict() for col in ['same_order_configuration','nested_child_configuration']}}
 elif f=='05_large_city_access':expected={'population_units_with_path':int((access.nearest_large_city_network_minutes.notna()&n._population_axis_row).sum()),'population_threshold':100000}
 ck('actual_model_figure_counts_'+f,v==expected)
 for obj in fig['outputs']:ck('actual_image_hash_'+obj['path'],sha(P/obj['path'])==obj['sha256'])
ck('2021_source_epoch_and_no_polygon_claim',j['transport_reference_year']==2021 and j['geometry']=='actual NP point memberships; no invented polygon borders' and j['all_inputs_unchanged'])
r={'status':'ACCEPTED_SOURCE_BINDING_AND_FIGURE_STATISTICS_VISUAL_SCOPE_SEPARATE' if all(c['pass'] for c in checks) else 'REJECTED','all_checks_passed':all(c['pass'] for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'checks':checks,'map_manifest_sha256':sha(P/'map_manifest.json'),'scope':'All18 realfigure counts/categories and54PNG/PDF/SVGbytehashes tied to actualacceptedbaseline/canonical sources and18-pagePDF; visual text/overlap acceptance separately attributed.'};(B/'reviews/cycle06/atlas_v4_source_independent_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r['status'],r['n_checks'],r['n_failed']);print([c for c in checks if not c['pass']])

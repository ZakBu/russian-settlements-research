"""Rebuild full stage71 panel and exact historical/municipal links, inputs read-only.
No2010 quality labels filter source counts; zeros remain observed values.
"""
from pathlib import Path
import argparse,json,hashlib
import pandas as pd,numpy as np

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3]);ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent);args=ap.parse_args();r=args.repo.resolve();o=args.output.resolve();o.mkdir(parents=True,exist_ok=True);checks=[];inputs={}
 def ck(name,condition,details=None):
  checks.append({'test':name,'passed':bool(condition),'details':details});assert condition,(name,details)
 def pin(p):inputs[str(p.relative_to(r))]={'sha256':sha(p),'bytes':p.stat().st_size}
 sp=r/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz';pin(sp);ck('source_SHA256',sha(sp)=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c')
 source=pd.read_csv(sp,low_memory=False,dtype={f'{c}_{y}':'string' for y in [2002,2010,2021] for c in ['oktmo','okato']});ck('source_shape',source.shape==(142570,135));ck('source_unique_entity_uid',source.entity_uid.is_unique)
 p=pd.DataFrame({'id':source.entity_uid,'name':source.settlement_name_2021,'type':source.settlement_type_2021,'region':source.effective_region_norm_2021,'lat':source.latitude_2021,'lon':source.longitude_2021})
 for y in [2002,2010,2021]:
  for c in ['population','source_record_id','settlement_name','settlement_type','region_norm','district_raw','oktmo','okato','population_value_quality','source_actual_sha256','source_actual_resolution_status','point_origin_kind']:
   p[f'{c}_{y}']=source[f'{c}_{y}']
  p[f'population_{y}_observed']=p[f'population_{y}'].notna();p[f'population_{y}_zero']=p[f'population_{y}'].eq(0)
  ck(f'exact_population_{y}_preserved',np.array_equal(p[f'population_{y}'],source[f'population_{y}'],equal_nan=True));ck(f'nonnegative_population_{y}',p[f'population_{y}'].dropna().ge(0).all())
 p['ordinary_same_place_identity']=source.ordinary_same_place_identity;p['all_three_own_point_uses']=source.all_three_own_point_uses;p['coordinate_reference_year']=2021;p['historical_coordinate_measurement_asserted']=False;p['historical_boundary_comparability']='not_established'
 ck('coordinate_domain',p.lat.between(-90,90).all() and p.lon.between(-180,180).all());ck('all2010_source_values_and_zeros_retained',len(p)==142570 and p.population_2010.eq(0).sum()==source.population_2010.eq(0).sum(),{'zeros':int(p.population_2010.eq(0).sum())})
 # Prefer enriched native bridge; source row ambiguity is preserved, not silently resolved by proximity.
 bp=r/'research_rebuild/evidence/tochno_enrichment_application_20261013/native_np_municipality_bridge.csv.gz'
 if not bp.exists():bp=r/'research_rebuild/evidence/tochno_np_attach_20261013/bridges/native_np_municipality_bridge.csv.gz'
 if bp.exists():
  pin(bp);b=pd.read_csv(bp,dtype='string');u=b[b.municipality_role.eq('upper')].copy();n=u.groupby('source_record_id').size();u['unique_upper_context']=u.source_record_id.map(n).eq(1);u=u[u.unique_upper_context].set_index('source_record_id')
  for col,new in [('municipality_label_raw','municipality_upper_2021'),('municipality_oktmo_code8','municipality_oktmo8_2021'),('context_status','municipality_context_status'),('municipality_source_row_ambiguous','municipality_source_row_ambiguous'),('code_namespace','municipality_code_namespace')]:
   p[new]=p.source_record_id_2021.map(u[col]) if col in u else pd.NA
  # Only normalize an explicit native municipal code; never truncate settlement codes into a crosswalk.
  raw=p.municipality_oktmo8_2021.astype('string');norm=raw.str.replace(r'\.0$','',regex=True);valid=norm.str.fullmatch(r'\d{1,8}',na=False);p['municipality_oktmo8_2021']=norm.where(valid).str.zfill(8);p['municipality_code_raw']=raw
  b=b[b.source_record_id.isin(set(p.source_record_id_2021))].copy();b['id']=b.source_record_id.map(p.set_index('source_record_id_2021').id);b.to_parquet(o/'municipality_bridge.parquet',index=False,compression='zstd');b.to_csv(o/'municipality_bridge.csv.gz',index=False,compression={'method':'gzip','mtime':0});p[['id','source_record_id_2021','municipality_upper_2021','municipality_oktmo8_2021','municipality_context_status','municipality_source_row_ambiguous','municipality_code_namespace']].to_csv(o/'municipality_upper_crosswalk.csv.gz',index=False,compression={'method':'gzip','mtime':0})
  mun_audit={'input_rows':len(pd.read_csv(bp,usecols=['source_record_id'])),'master_context_rows':len(b),'upper_attached':int(p.municipality_upper_2021.notna().sum()),'code_attached':int(p.municipality_oktmo8_2021.notna().sum()),'input_upper_duplicate_source_ids':int(n.gt(1).sum()),'statuses':p.municipality_context_status.fillna('MISSING').value_counts().to_dict(),'ambiguous_source_row_attached':int(p.municipality_source_row_ambiguous.eq('True').sum()),'historical_administrative_membership_asserted':False,'territorial_effective_dates_unknown':True}
 else:mun_audit={'status':'bridge_unavailable'}
 # Historical1989 candidates matched ONLY by exact root/anchor IDs. All ambiguities held.
 hp=r/'research_rebuild/evidence/historical_sources_integration_20261014/population_1989_selected_long.parquet';hist_audit={'status':'unavailable'}
 if hp.exists():
  pin(hp);h=pd.read_parquet(hp);ck('historical_root_unique',h.root.is_unique);lookup={}
  for y in [2002,2010,2021]:
   for idx,key in source[f'source_record_id_{y}'].items():
    if isinstance(key,str):lookup.setdefault(key,set()).add(idx)
  links=[];unmatched=[]
  for j,row in h.iterrows():
   candidates=set()
   for key in [row.get('root'),row.get('anchor_source_record_id')]:
    if isinstance(key,str):candidates |= lookup.get(key,set())
   if not candidates:unmatched.append(j)
   for i in candidates:links.append({'historical_index':j,'panel_index':i,'historical_candidate_modern_count':len(candidates)})
  l=pd.DataFrame(links);l['modern_candidate_historical_count']=l.groupby('panel_index').historical_index.transform('nunique');l['accepted']=l.historical_candidate_modern_count.eq(1)&l.modern_candidate_historical_count.eq(1)
  l=l.merge(h[['root','historical_name','population','source_kind','population_basis','historical_boundary_comparability']],left_on='historical_index',right_index=True,validate='many_to_one');l['id']=l.panel_index.map(p.id);l.to_csv(o/'historical1989_link_audit.csv.gz',index=False,compression={'method':'gzip','mtime':0});h.loc[unmatched].to_parquet(o/'historical1989_unmatched.parquet',index=False)
  accepted=l[l.accepted];cohort=h.loc[accepted.historical_index].copy().reset_index(drop=True);cohort['id']=accepted.id.to_numpy();cohort['binding_to_master']='exact_unique_root_or_anchor_source_record_id';cohort=cohort.merge(p[['id','name','type','region','lat','lon','population_2002','population_2010','population_2021']],on='id',validate='one_to_one',suffixes=('_historical','_reference2021'));cohort['is_primary_source_kind']=cohort.source_kind.isin(['official_census_transcription','primary_regional_census']);cohort.to_parquet(o/'cohort1989.parquet',index=False,compression='zstd');cohort.to_csv(o/'cohort1989.csv.gz',index=False,compression={'method':'gzip','mtime':0})
  hist_index=cohort.set_index('id');p['population_1989']=p.id.map(hist_index.population);p['population_1989_source_kind']=p.id.map(hist_index.source_kind);p['population_1989_basis']=p.id.map(hist_index.population_basis);p['population_1989_boundary_comparability']=p.id.map(hist_index.historical_boundary_comparability);p['population_1989_primary']=p.id.map(hist_index.is_primary_source_kind).fillna(False).astype(bool)
  ck('historical_join_unique',cohort.id.is_unique);ck('held1989_not_assigned',p.loc[l.loc[~l.accepted,'panel_index'].unique(),'population_1989'].isna().all());ck('historical_link_count',p.population_1989.notna().sum()==len(cohort))
  hist_audit={'input_rows':len(h),'exact_unique_linked_rows':len(cohort),'primary_source_kind_rows':int(cohort.is_primary_source_kind.sum()),'unmatched_historical_rows':len(unmatched),'held_candidate_links':int((~l.accepted).sum()),'input_anchors_duplicate_nonmissing':int(h.anchor_source_record_id.dropna().duplicated().sum()),'source_kind_counts':cohort.source_kind.fillna('MISSING').value_counts().to_dict(),'population_basis_counts':cohort.population_basis.fillna('MISSING').value_counts().to_dict(),'boundary_comparability_counts':cohort.historical_boundary_comparability.fillna('MISSING').value_counts().to_dict(),'nationally_complete':False,'no_spatial_or_fuzzy_binding':True}
  versions=[]
  for q in sorted((r/'research_rebuild/evidence').glob('*/population_1989_selected_long.parquet')):
   z=pd.read_parquet(q,columns=['root','population']);versions.append({'path':str(q.relative_to(r)),'rows':len(z),'sum_mixed_population_bases':float(z.population.sum()),'sha256':sha(q),'selected':q==hp})
  (o/'historical1989_version_inventory.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2))
 # External federal territory centers are masses for geometry only, not additional panel observations.
 fp=r/'publication/stage71/accepted_common_federal_territory_axis.csv'
 if fp.exists():pin(fp);f=pd.read_csv(fp);f.to_csv(o/'external_federal_centers.csv',index=False)
 p.to_parquet(o/'panel.parquet',index=False,compression='zstd');ck('panel_rows_preserved',len(p)==len(source));ck('input_SHA256_unchanged',sha(sp)==inputs[str(sp.relative_to(r))]['sha256'])
 region=[]
 for reg,g in p.groupby('region',dropna=False):
  z={'region':reg,'n':len(g)}
  for y in [1989,2002,2010,2021]:
   if f'population_{y}' in g:z[f'observed_{y}']=int(g[f'population_{y}'].notna().sum());z[f'zero_{y}']=int(g[f'population_{y}'].eq(0).sum());z[f'population_sum_{y}']=float(g[f'population_{y}'].sum())
  region.append(z)
 pd.DataFrame(region).to_csv(o/'regional_coverage.csv',index=False)
 modern={str(y):{'observed':int(p[f'population_{y}'].notna().sum()),'missing':int(p[f'population_{y}'].isna().sum()),'zero':int(p[f'population_{y}'].eq(0).sum()),'sum':float(p[f'population_{y}'].sum()),'population_quality_metadata_only':source[f'population_value_quality_{y}'].fillna('MISSING').value_counts().to_dict(),'source_id_duplicate':int(p[f'source_record_id_{y}'].duplicated().sum())} for y in [2002,2010,2021]}
 report={'rows':len(p),'columns':len(p.columns),'source_shape':list(source.shape),'source_sha256':sha(sp),'all2010_included':True,'metadata_not_evidence_of_value_error':True,'2010_zero_is_observed_not_missing':True,'modern':modern,'municipality':mun_audit,'historical1989':hist_audit,'checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'inputs':inputs,'panel_sha256':sha(o/'panel.parquet')}
 (o/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));outputs={q.name:{'sha256':sha(q),'bytes':q.stat().st_size} for q in sorted(o.iterdir()) if q.is_file() and q.name!='checksums.json' and not q.name.endswith('.log')};(o/'checksums.json').write_text(json.dumps({'inputs':inputs,'outputs':outputs},ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

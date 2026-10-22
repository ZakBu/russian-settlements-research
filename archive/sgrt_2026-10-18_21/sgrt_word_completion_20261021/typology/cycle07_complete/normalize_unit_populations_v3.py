"""Population-only projection/aggregation for arbitrary accepted empirical units.
No modifications of hierarchy, Mi, functions, coordinates or historical sources.
"""
import argparse,hashlib,json,os,sys,gc
from pathlib import Path
import numpy as np
import pandas as pd
from classify_complete import truth,number,admitted
from atomic_normalization import atom

YEARS=(2002,2010,2021)
PRIMARY={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
SECONDARY='secondary_confidentiality_protected_value_exact_scope_unverified'
def source_admitted(review):
 if review.get('status')=='INDEPENDENT_RELINK_V4_ACCEPTED':
  assert review.get('all_checks_passed') is True and review.get('n_failed')==0
 else:admitted(review)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def same(a,b):return (pd.isna(a) and pd.isna(b)) or (not pd.isna(a) and not pd.isna(b) and a==b)
def stats(data,year):
 p=pd.to_numeric(data[f'population_{year}'],errors='coerce');valid=p.map(lambda x:number(x) is not None);q=data[f'population_value_quality_{year}'].fillna('quality_unavailable')
 total=float(p[valid].sum()) if valid.any() else np.nan
 return {'known_sum':total,'complete':bool(len(data)>0 and valid.all()),'n_missing':int((~valid).sum()),'n_zero':int((p[valid]==0).sum()),'primary_complete':bool(len(data)>0 and valid.all() and q.isin(PRIMARY).all()),'primary_share':float(p[valid&q.isin(PRIMARY)].sum()/total) if total>0 else np.nan,'secondary_share':float(p[valid&q.eq(SECONDARY)].sum()/total) if total>0 else np.nan,'qualities':json.dumps(q.value_counts().to_dict(),ensure_ascii=False)}

def aggregate(u,m,n,c):
 nid=c.get('node_id_column','id');uid=c.get('unit_id_column','unit_id');mid=c.get('membership_node_column','id');muid=c.get('membership_unit_column','unit_id')
 assert u[uid].notna().all() and u[uid].is_unique and n[nid].is_unique
 assert not m.duplicated([muid,mid]).any()
 assert set(m[muid])==set(u[uid]) and set(m[mid])<=set(n[nid])
 n=n.set_index(nid,drop=False);groups=m.groupby(muid,sort=False)[mid].agg(list).to_dict();records=[]
 for _,r in u.iterrows():
  row=r.to_dict();row['raw_kind']=r['kind'];row['raw_central_object_definition']=r.get('central_object_definition',pd.NA)
  normalized_kind={'provider_core_seed':'atomic_settlement','atomic_residual':'atomic_settlement'}.get(r['kind'],r['kind'])
  assert normalized_kind in ('atomic_settlement','functional_union','external_context_anchor','superregional_overlay')
  row['kind']=normalized_kind;unit=r[uid];raw=n.loc[groups[unit]]
  core=json.loads(r['central_object_ids_json']) if 'central_object_ids_json' in u else json.loads(r['central_object_ids']) if 'central_object_ids' in u else [str(r['core_id'])]
  assert core and len(core)==len(set(core)) and set(core)<=set(n.index)
  atomic=normalized_kind=='atomic_settlement'
  definition='own_atomic' if atomic else r.get('central_object_definition','one_focal_core')
  policy=c.get('central_definition_policy','one_focal_core_primary')
  if policy=='one_focal_core_primary':
   assert len(core)==1 and definition in ('own_atomic','one_focal_core'),'Primary central object must be one actual focal core, not provider-seed pool'
   if 'core_id' in u: assert core==[str(r['core_id'])],'Central object differs from declared actual focal core'
  elif policy!='separately_admitted_supported_peer_nuclei': raise ValueError('Unknown central object policy')
  row['central_object_ids_json']=json.dumps(core);row['central_object_definition']=definition
  row['level']=r.get('resolution_index',pd.NA)
  row['center_id']=core[0] if len(core)==1 else pd.NA
  row['center_scope']='external_metropolitan_context_anchor' if len(core)==1 and core[0] in ('ctx:RU-FED-MOW','ctx:RU-FED-SPB') else 'ordinary_source_settlement_focal' if all(truth(n.loc[x,'_population_axis_row']) is True for x in core) else 'nonadditive_source_object_focal'
  row['operational_view_id']=c.get('operational_view_id',pd.NA)
  row['display_retained']=c.get('display_retained',pd.NA)
  row['empirical_resolution_supported']=c.get('empirical_resolution_supported',pd.NA)
  for yy in YEARS:
   unknown_ctx=raw.loc[raw.index.isin(('ctx:RU-FED-MOW','ctx:RU-FED-SPB')) & pd.to_numeric(raw[f'population_{yy}'],errors='coerce').isna()]
   row[f'unknown_nonadditive_metropolitan_all_population_slots_{yy}']=len(unknown_ctx)
   row[f'unknown_nonadditive_metropolitan_focal_population_slots_{yy}']=int(unknown_ctx.index.isin(core).sum())
   row[f'unknown_nonadditive_metropolitan_nonfocal_population_slots_{yy}']=int((~unknown_ctx.index.isin(core)).sum())
  if atomic and not c.get('disable_atomic_fast_path',False):
   assert len(groups[unit])==1 and core==groups[unit],'Atomic core/member singleton mismatch'
   row.update(atom(n.loc[core[0]],c));records.append({sys.intern(k):v for k,v in row.items()});continue
  pop=raw.loc[raw['_population_axis_row'].map(lambda v:truth(v) is True)]
  ext=pop.loc[~pop.index.isin(core)];roles=ext['accepted_statistical_rural_role2021'].map(truth)
  rural=ext.loc[roles.map(lambda v:v is True)];unknown=int(roles.isna().sum());center=n.loc[core]
  for set_name,source_ids in [('central_object',core),('rural_external_members',rural.index.tolist()),('additive_whole_members',pop.index.tolist())]:
   row[set_name+'_set_sha256']=hashlib.sha256(json.dumps(sorted(map(str,source_ids)),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  rural_p2021=pd.to_numeric(rural.population_2021,errors='coerce')
  row['rural_known_population2021_denominator']=float(rural_p2021.sum(min_count=1)) if len(rural) else np.nan
  row['rural_known_population2021_n_missing']=int(rural_p2021.isna().sum())
  row['rural_weight_denominator_is_known_lowerbound']=bool(unknown>0 or rural_p2021.isna().any())
  missing_context_core=any(truth(n.loc[x,'_population_axis_row']) is not True for x in core)
  row.update(n_population_axis_settlements=len(pop),n_external_settlements=len(ext),n_rural_external_settlements=len(rural),n_unknown_role_external_settlements=unknown,rural_role_complete=unknown==0,historical_boundary_equivalence_proven=False,nonadditive_external_central_exception=bool(missing_context_core and r['unit_role']=='context_overlay'))
  for y in YEARS:
   ps=stats(pop,y);rs=stats(rural,y);cs=stats(center,y)
   row[f'system_population_known_sum_{y}']=ps['known_sum']
   row[f'system_population_complete_{y}']=ps['complete'] and not missing_context_core and row[f'unknown_nonadditive_metropolitan_all_population_slots_{y}']==0
   row[f'system_known_additive_member_population_sum_{y}']=ps['known_sum']
   row[f'n_missing_population_{y}']=ps['n_missing'];row[f'n_observed_zero_{y}']=ps['n_zero']
   row[f'center_population_{y}']=cs['known_sum'] if cs['complete'] else np.nan
   row[f'center_population_complete_{y}']=cs['complete']
   row[f'own_population_{y}']=cs['known_sum'] if atomic and cs['complete'] else np.nan
   row[f'own_population_complete_{y}']=bool(atomic and cs['complete'])
   # No rural members is a structurally empty object, not an invented population observation.
   row[f'rural_external_population_known_sum_{y}']=rs['known_sum'] if len(rural) else 0.
   row[f'rural_population_complete_{y}']=bool((rs['complete'] if len(rural) else True) and unknown==0)
   row[f'population_quality_counts_json_{y}']=ps['qualities']
   row[f'center_population_quality_counts_json_{y}']=cs['qualities']
   row[f'population_secondary_protected_scope_unverified_known_population_share_{y}']=ps['secondary_share']
   row[f'system_population_exact_primary_supported_{y}']=ps['primary_complete'] and not missing_context_core and row[f'unknown_nonadditive_metropolitan_all_population_slots_{y}']==0
   row[f'classification_population_exact_primary_supported_{y}']=cs['primary_complete'] if atomic else row[f'system_population_exact_primary_supported_{y}']
   row[f'classification_secondary_population_share_{y}']=cs['secondary_share'] if atomic else ps['secondary_share']
  basis=center if atomic else pop
  recovered=basis['primary2010_overlay_applied'].map(lambda x:truth(x) is True)
  vals=pd.to_numeric(basis.population_2010,errors='coerce');den=vals.sum(min_count=1)
  prior=basis.copy();prior['population_2010']=basis.population_2010_prior;prior['population_value_quality_2010']=basis.population_value_quality_2010_prior
  row['n_members_primary2010_newly_recovered']=int(recovered.sum())
  row['primary2010_newly_recovered_population_share']=float(vals[recovered].sum()/den) if den>0 else np.nan
  row['n_members_primary2010_numeric_changed']=int(basis.primary2010_numeric_changed.sum())
  row['n_members_primary2010_quality_changed']=int(basis.primary2010_quality_changed.sum())
  row['prior_secondary2010_population_share']=stats(prior,2010)['secondary_share']
  basis_stats=stats(basis,2010)
  row['current_secondary2010_population_share']=basis_stats['secondary_share']
  row['primary2010_population_share']=basis_stats['primary_share']
  row['protected_secondary2010_population_share']=basis_stats['secondary_share']
  row['population2010_known_denominator']=basis_stats['known_sum']
  row['2010_missing_population_count']=basis_stats['n_missing']
  row['population_quality_share_denominator_scope']='own_source_series' if atomic else 'known_nonnegative_additive_member_population2010'
  row['unknown_nonadditive_central_population_slots2010']=int(sum(number(n.loc[x,'population_2010']) is None for x in core if truth(n.loc[x,'_population_axis_row']) is not True))
  for witness in c.get('context_projection',[]):
   scope=witness['scope']
   selected=center if scope=='focal' else rural if scope=='rural_members' else raw if scope=='all_members' else None
   if selected is None: raise ValueError('Unknown context witness scope')
   assert witness['kind'] in ('boolean','positive_count') and all(witness.get(k) for k in ('source','year','grain','absence_is_unknown'))
   known=pd.Series(False,index=selected.index);positive=pd.Series(False,index=selected.index);raw_summary={}
   for column in witness['columns']:
    vals=selected[column]
    flag=vals.map(lambda x:truth(x) is True) if witness['kind']=='boolean' else vals.map(lambda x:number(x) is not None and number(x)>0)
    # Zero catalogue counts do not establish actual absence or observation coverage.
    observed=vals.notna() if witness['kind']=='boolean' else flag
    known=known|observed;positive=positive|flag
    raw_summary[column]={'n_field_nonmissing':int(vals.notna().sum()),'n_positive':int(flag.sum()),'n_missing':int(vals.isna().sum())}
   if witness.get('observed_column'):
    known=selected[witness['observed_column']].map(lambda x:truth(x) is True)
    positive=positive & known
   prefix=witness['output_column']
   row[prefix]=True if positive.any() else pd.NA
   row[prefix+'_actual_source_observed_flag']=True if known.any() else pd.NA
   row[prefix+'_n_positive_members']=int(positive.sum())
   row[prefix+'_n_source_observed_members']=int(known.sum())
   row[prefix+'_n_source_scope_members']=len(selected)
   row[prefix+'_raw_source_field_controls_json']=json.dumps(raw_summary,ensure_ascii=False)
   weights=pd.to_numeric(selected.population_2021,errors='coerce');den=weights.sum(min_count=1)
   row[prefix+'_scope_known_population2021_denominator']=float(den) if pd.notna(den) else np.nan
   row[prefix+'_source_observed_population_coverage2021']=float(weights[known].sum()/den) if den>0 else np.nan
   row[prefix+'_positive_witness_population_share2021']=float(weights[positive].sum()/den) if den>0 else np.nan
   source_columns=witness.get('independent_source_unit_columns',[])
   if not source_columns: raise ValueError('Explicit independent source grain columns required')
   row[prefix+'_n_distinct_observed_source_units']=int(selected.loc[known,source_columns].dropna().drop_duplicates().shape[0])
   row[prefix+'_source_year']=witness['year'];row[prefix+'_source_grain']=witness['grain'];row[prefix+'_statistical_source_unit_independence_claimed']=False
  for numeric in c.get('context_numeric_projection',[]):
   scope=numeric['scope'];selected=center if scope=='focal' else rural if scope=='rural_members' else raw if scope=='all_members' else None
   if selected is None:raise ValueError('Unknown numeric context scope')
   assert all(numeric.get(k) for k in ('source','year','grain','unit','independent_source_unit_columns'))
   values=pd.to_numeric(selected[numeric['value_column']],errors='coerce');usable=values.notna() & np.isfinite(values)
   if numeric.get('observed_column'):usable=usable & selected[numeric['observed_column']].map(lambda x:truth(x) is True)
   weights=pd.to_numeric(selected.population_2021,errors='coerce');finite_weight=weights.notna() & np.isfinite(weights) & weights.ge(0)
   denominator=weights.loc[finite_weight].sum(min_count=1);covered=weights.loc[finite_weight & usable].sum(min_count=1)
   prefix=numeric['output_prefix']
   row[prefix+'_weighted_mean']=float((values[finite_weight & usable]*weights[finite_weight & usable]).sum()/covered) if covered>0 else np.nan
   row[prefix+'_known_population2021_denominator']=float(denominator) if pd.notna(denominator) else np.nan
   row[prefix+'_source_observed_population_coverage2021']=float(covered/denominator) if denominator>0 and pd.notna(covered) else 0. if denominator>0 else np.nan
   row[prefix+'_n_distinct_observed_source_units']=int(selected.loc[usable,numeric['independent_source_unit_columns']].dropna().drop_duplicates().shape[0])
   row[prefix+'_n_usable_NP_context_records']=int(usable.sum())
   row[prefix+'_source_year']=numeric['year'];row[prefix+'_source_grain']=numeric['grain'];row[prefix+'_source_unit']=numeric['unit'];row[prefix+'_statistical_source_unit_independence_claimed']=False
   row[prefix+'_is_population_exposure_context_not_ownNP_productivity']=True
  records.append({sys.intern(k):v for k,v in row.items()})
 result=pd.DataFrame(records);assert len(result)==len(u) and set(result[uid])==set(u[uid]);return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();cp=Path(a.contract);c=json.loads(cp.read_text());out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh output required')
 watched={str(cp.resolve()):sha(cp),str(Path(__file__).resolve()):sha(__file__),str(Path(__file__).with_name('atomic_normalization.py').resolve()):sha(Path(__file__).with_name('atomic_normalization.py'))}
 for key in ('raw_units','memberships','base_nodes'):
  p=Path(c[key+'_path']);assert sha(p)==c[key+'_sha256'];watched[str(p.resolve())]=sha(p)
 assert c['source_admissions'],'At least one accepted source admission required'
 for review in c['source_admissions']:
  p=Path(review['path']);assert sha(p)==review['sha256'];source_admitted(json.loads(p.read_text()));watched[str(p.resolve())]=sha(p)
 u=pd.read_parquet(c['raw_units_path']);m=pd.read_parquet(c['memberships_path']);raw_input_unit_count=len(u)
 scope_filter=c.get('scope_filter',{})
 for column in c.get('required_separate_partition_columns',['partition_role']):
  if column in u and u[column].nunique(dropna=False)>1: assert column in scope_filter,'Partition alternatives must be normalized/count separately'
 for column,value in scope_filter.items():
  assert column in u;u=u.loc[u[column].eq(value)].copy()
 assert len(u)>0,'Empty declared source partition'
 unit_column=c.get('unit_id_column','unit_id');member_unit_column=c.get('membership_unit_column','unit_id');m=m.loc[m[member_unit_column].isin(u[unit_column])].copy()
 base=pd.read_parquet(c['base_nodes_path'])
 for layer in c.get('context_layers',[]):
  lp=Path(layer['path']);lr=Path(layer['admission_path']);assert sha(lp)==layer['sha256'] and sha(lr)==layer['admission_sha256']
  la=json.loads(lr.read_text());admitted(la);assert layer['sha256'] in json.dumps(la),'Context artifact SHA not pinned by source admission'
  watched[str(lp.resolve())]=sha(lp);watched[str(lr.resolve())]=sha(lr)
  values=pd.read_parquet(lp);key=layer.get('id_column','id');assert values[key].is_unique and set(values[key])<=set(base.id)
  values=values.set_index(key)
  for source,target in layer['column_mapping'].items():
   assert target not in base,'Context layer must use separate explicit names, not shadow existing source fields'
   base[target]=base.id.map(values[source])
 columns=['id','_population_axis_row','accepted_statistical_rural_role2021']+[f'{prefix}_{y}' for y in YEARS for prefix in ('population','population_value_quality')]
 columns += list(dict.fromkeys(x for w in c.get('context_projection',[]) for x in w['columns']+w.get('independent_source_unit_columns',[])+([w['observed_column']] if w.get('observed_column') else []) if x not in columns))
 columns += list(dict.fromkeys(x for w in c.get('context_numeric_projection',[]) for x in [w['value_column']]+w['independent_source_unit_columns']+([w['observed_column']] if w.get('observed_column') else []) if x not in columns))
 columns += [x for x in ('source_record_id_2021','name','region') if x in base and x not in columns]
 n=base[columns].copy();n['population2010_effective_source_uid']=base[c.get('base2010_source_uid_column','source_record_id_2010')] if c.get('base2010_source_uid_column','source_record_id_2010') in base else pd.NA
 n['population2010_prior_source_uid']=n.population2010_effective_source_uid
 n['population2010_effective_source_admission_sha256']=pd.NA
 n['population_2010_prior']=n.population_2010;n['population_value_quality_2010_prior']=n.population_value_quality_2010
 for k in ('primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed'):n[k]=False
 overlay=c.get('population_overlay');view=c.get('accepted_population_source_view');applied=[]
 if overlay and view:raise ValueError('Use either accepted effective population view or direct primary overlay, not both')
 if view:
  vp=Path(view['path']);vrp=Path(view['admission_path']);assert sha(vp)==view['sha256'] and sha(vrp)==view['admission_sha256']
  va=json.loads(vrp.read_text());admitted(va);assert va['accepted_effective_nodes_sha256']==sha(vp)
  watched[str(vp.resolve())]=sha(vp);watched[str(vrp.resolve())]=sha(vrp)
  v=pd.read_parquet(vp).set_index('id',drop=False);n=n.set_index('id',drop=False);assert v.index.is_unique and set(v.index)==set(n.index)
  for col in ['_population_axis_row','accepted_statistical_rural_role2021']+[f'{prefix}_{year}' for year in (2002,2021) for prefix in ('population','population_value_quality')]:
   assert (n[col].eq(v.loc[n.index,col])|(n[col].isna()&v.loc[n.index,col].isna())).fillna(False).all(),'Population view conflicts with non2010/role source'
  for col in ['population_2010','population_value_quality_2010','population_2010_prior','population_value_quality_2010_prior','population2010_prior_source_uid','population2010_effective_source_uid','population2010_effective_source_admission_sha256','primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed']:n[col]=v.loc[n.index,col]
  applied=n.index[n.primary2010_overlay_applied.fillna(False).astype(bool)].tolist();n=n.reset_index(drop=True)
 if overlay:
  p=Path(overlay['path']);rp=Path(overlay['admission_path']);assert sha(p)==overlay['sha256'] and sha(rp)==overlay['admission_sha256'];review=json.loads(rp.read_text());admitted(review);assert review['accepted_overlay_sha256']==sha(p)
  watched[str(p.resolve())]=sha(p);watched[str(rp.resolve())]=sha(rp)
  o=pd.read_parquet(p);assert o[overlay['id_column']].is_unique;n=n.set_index('id',drop=False)
  prior_o=o.set_index(overlay['id_column']);assert set(prior_o.index)<=set(n.index)
  for target,col in [('population_2010',overlay['prior_population_column']),('population_value_quality_2010',overlay['prior_quality_column'])]:
   left=n.loc[prior_o.index,target];right=prior_o[col]
   assert (left.eq(right)|(left.isna()&right.isna())).fillna(False).all(),'Cumulative overlay prior full-axis populations/quality differ from base'
  if overlay.get('prior_source_uid_column'):
   n.loc[prior_o.index,'population2010_effective_source_uid']=prior_o[overlay['prior_source_uid_column']]
   n.loc[prior_o.index,'population2010_prior_source_uid']=prior_o[overlay['prior_source_uid_column']]
  for _,r in o.iterrows():
   if truth(r[overlay['apply_column']]) is not True:continue
   ident=r[overlay['id_column']];assert ident in n.index
   assert same(n.loc[ident,'population_2010'],r[overlay['prior_population_column']]) and same(n.loc[ident,'population_value_quality_2010'],r[overlay['prior_quality_column']]),'Overlay prior source differs'
   source_uid=r[overlay['source_uid_column']];assert pd.notna(source_uid) and str(source_uid),'Primary source UID required'
   n.loc[ident,'population2010_effective_source_uid']=str(source_uid);n.loc[ident,'population2010_effective_source_admission_sha256']=overlay['admission_sha256']
   new=number(r[overlay['population_column']]);q=r[overlay['quality_column']];assert new is not None and q in PRIMARY
   n.loc[ident,'primary2010_overlay_applied']=True;n.loc[ident,'primary2010_numeric_changed']=not same(n.loc[ident,'population_2010'],new);n.loc[ident,'primary2010_quality_changed']=not same(n.loc[ident,'population_value_quality_2010'],q)
   n.loc[ident,'population_2010']=new;n.loc[ident,'population_value_quality_2010']=q;applied.append(ident)
  n=n.reset_index(drop=True)
 del base
 if view:del v
 if overlay:del o,prior_o
 gc.collect()
 normalized=aggregate(u,m,n,c)
 for p,s in watched.items():assert sha(p)==s,'Source changed during aggregation'
 out.mkdir(parents=True);u.to_parquet(out/'raw_units_scoped.parquet',index=False);m.to_parquet(out/'memberships_scoped.parquet',index=False)
 shared=c.get('shared_effective_source_view')
 if shared:
  sp=Path(shared['path']);assert sha(sp)==shared['sha256']
  payload=n.to_parquet(index=False);assert hashlib.sha256(payload).hexdigest()==shared['sha256'],'Shared source view is not byte-identical to current admitted source projection'
  os.link(sp,out/'effective_population_source_view.parquet')
 else:n.to_parquet(out/'effective_population_source_view.parquet',index=False)
 normalized.to_parquet(out/'normalized_units.parquet',index=False)
 pd.DataFrame({'id':applied}).to_csv(out/'applied_primary2010_ids.csv',index=False)
 receipt={'status':'COMPUTED_POPULATION_NORMALIZATION_PENDING_INDEPENDENT_ADMISSION','raw_units_sha256':c['raw_units_sha256'],'raw_input_unit_count':raw_input_unit_count,'scope_filter':scope_filter,'raw_scoped_units_sha256':sha(out/'raw_units_scoped.parquet'),'scoped_memberships_sha256':sha(out/'memberships_scoped.parquet'),'normalized_units_sha256':sha(out/'normalized_units.parquet'),'effective_nodes_sha256':sha(out/'effective_population_source_view.parquet'),'base_nodes_sha256':c['base_nodes_sha256'],'central_definition_policy':c.get('central_definition_policy','one_focal_core_primary'),'n_units':len(normalized),'unit_role_counts':normalized.unit_role.value_counts().to_dict(),'n_primary2010_overrides':len(applied),'context_layers':c.get('context_layers',[]),'context_projection':c.get('context_projection',[]),'context_numeric_projection':c.get('context_numeric_projection',[]),'source_admissions':c['source_admissions'],'watched_inputs':watched,'overlay':overlay,'accepted_population_source_view':view,'shared_effective_source_view':shared,'hierarchy_or_mi_or_coordinates_changed':False,'historical_boundary_equivalence_claimed':False,'code_sha256':sha(__file__),'files':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()

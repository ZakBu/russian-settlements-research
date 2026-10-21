"""Independent all-unit groupby population/context audit; no producer imports."""
from pathlib import Path
import argparse,json,hashlib,time
import numpy as np,pandas as pd,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[2]
PQUAL={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
SQUAL='secondary_confidentiality_protected_value_exact_scope_unverified'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',required=True);ap.add_argument('--normalized',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();start=time.monotonic();out=Path(a.output);assert not out.exists();out.mkdir(parents=True);cp=Path(a.contract);c=json.loads(cp.read_text());folder=Path(a.normalized);checks=[];watched={str(cp):sha(cp)};witness=[]
 def ck(name,ok,detail=None):checks.append({'check':name,'passed':bool(ok),'detail':detail})
 def load(p,s=None,columns=None):
  p=Path(p);actual=sha(p);ck('source_sha_'+str(p),s is None or actual==s);watched[str(p)]=actual;return pd.read_parquet(p,columns=columns)
 raw=load(c['raw_units_path'],c['raw_units_sha256']);mraw=load(c['memberships_path'],c['memberships_sha256']);base_columns=list(set(pq.read_schema(folder/'effective_population_source_view.parquet').names)&set(pq.read_schema(c['base_nodes_path']).names));base=load(c['base_nodes_path'],c['base_nodes_sha256'],base_columns);u=load(folder/'normalized_units.parquet');n_saved=load(folder/'effective_population_source_view.parquet');m_saved=load(folder/'memberships_scoped.parquet');raw_saved=load(folder/'raw_units_scoped.parquet');receipt=json.loads((folder/'receipt.json').read_text());watched[str(folder/'receipt.json')]=sha(folder/'receipt.json')
 for col,val in c.get('scope_filter',{}).items():raw=raw[raw[col].eq(val)]
 m=mraw[mraw.unit_id.isin(raw.unit_id)].copy();ck('actual_scoped_units_exact',raw.reset_index(drop=True).equals(raw_saved.reset_index(drop=True)));ck('actual_scoped_members_exact',m.reset_index(drop=True).equals(m_saved.reset_index(drop=True)));ck('all_keys_and_partition',raw.unit_id.is_unique and u.unit_id.is_unique and set(raw.unit_id)==set(u.unit_id) and not m.duplicated(['unit_id','id']).any() and not m.id.duplicated().any() and set(m.unit_id)==set(u.unit_id));ck('173858_source_partition',len(m)==173858 and len(u)>0)
 # Rebuild source columns directly from original accepted full node fields and pinned context layers.
 n=base.copy();basecol=set(base)
 for layer in c.get('context_layers',[]):
  d=load(layer['path'],layer['sha256']);idx=d.set_index(layer.get('id_column','id'));ck('layer_unique_'+layer['path'],idx.index.is_unique and set(idx.index)<=set(n.id))
  for src,dst in layer['column_mapping'].items():ck('no_shadow_'+dst,dst not in basecol);n[dst]=n.id.map(idx[src])
 view=load(c['accepted_population_source_view']['path'],c['accepted_population_source_view']['sha256']).set_index('id');n=n.set_index('id',drop=False);ck('same_full_source_ids',n.index.is_unique and set(n.index)==set(view.index)==set(n_saved.id))
 for col in ['_population_axis_row','accepted_statistical_rural_role2021']+[f'{p}_{y}' for y in [2002,2021] for p in ['population','population_value_quality']]:
  x=n[col];y=view.loc[n.index,col];ck('353_preserves_'+col,(x.eq(y)|(x.isna()&y.isna())).fillna(False).all())
 effective_cols=['population_2010','population_value_quality_2010','population_2010_prior','population_value_quality_2010_prior','population2010_prior_source_uid','population2010_effective_source_uid','population2010_effective_source_admission_sha256','primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed']
 for col in effective_cols:n[col]=view.loc[n.index,col]
 saved=n_saved.set_index('id',drop=False).loc[n.index]
 for col in saved:
  x=n[col];y=saved[col];ck('every_effective_source_field_'+col,(x.eq(y)|(x.isna()&y.isna())).fillna(False).all())
 ck('353_new_primary_flags_not_cumulative',int(n.primary2010_overlay_applied.fillna(False).sum())==353 and int(n.primary2010_numeric_changed.fillna(False).sum())==292)
 cumulative=load(R/'demography2010_recovery_cycle06/admitted_overlay_v2_table5_adygea/full_axis_primary2010_overlay.parquet');cumulative=cumulative[cumulative.prior_accepted_four_region_overlay_applied.eq(True)|cumulative.primary2010_new_primary_recovery_applied.eq(True)].set_index('id');actual=n.loc[cumulative.index];ck('all19262_old_plus_new_population_and_quality_preserved',len(cumulative)==19262 and actual.population_2010.eq(cumulative.reviewed_primary2010_population).all() and actual.population_value_quality_2010.eq(cumulative.reviewed_primary2010_quality).all())
 # Keyed comparisons all actual units, never sample only population-supported units.
 u=u.set_index('unit_id',drop=False).sort_index();u.index.name='_unitkey';index=u.index;atomic=u.kind.eq('atomic_settlement');nf=len(index)
 def cmp(col,expected,json_values=False):
  exp=pd.Series(expected,index=index) if np.isscalar(expected) or expected is pd.NA else pd.Series(expected).reindex(index)
  act=u[col]
  if json_values:
   av=act.map(json.loads);ev=exp.map(json.loads);ok=av.eq(ev)
  elif pd.api.types.is_numeric_dtype(act) and not pd.api.types.is_bool_dtype(act):
   av=pd.to_numeric(act,errors='coerce').to_numpy(dtype=float,na_value=np.nan);ev=pd.to_numeric(exp,errors='coerce').to_numpy(dtype=float,na_value=np.nan);ok=pd.Series(np.isclose(av,ev,rtol=1e-11,atol=1e-7,equal_nan=True),index=index)
  else:ok=(act.eq(exp)|(act.isna()&exp.isna())).fillna(False)
  bad=~ok;ck('all_units_'+col,not bad.any(),{'rows':nf,'mismatches':int(bad.sum())})
  if bad.any():
   for k in index[bad][:5]:witness.append({'unit_id':k,'field':col,'actual':str(act.loc[k]),'expected':str(exp.loc[k])})
 def cnt(frame):return frame.groupby('unit_id',sort=False).size().reindex(index,fill_value=0)
 def sums(frame,col,empty=np.nan):return frame.groupby('unit_id',sort=False)[col].sum(min_count=1).reindex(index,fill_value=empty)
 def valid(s):return pd.to_numeric(s,errors='coerce').where(lambda v:np.isfinite(v)&v.ge(0))
 rawidx=raw.set_index('unit_id',drop=False).loc[index]
 for col in raw:
  if col not in ['kind','central_object_definition','resolution_index']:
   if col in u:
    cmp(col,rawidx[col])
 cmp('raw_central_object_definition',rawidx.central_object_definition);cmp('central_object_definition',pd.Series(np.where(atomic,'own_atomic','one_focal_core'),index=index));cmp('central_object_ids_json',u.core_id.map(lambda k:json.dumps([str(k)])),True);cmp('level',rawidx.resolution_index);cmp('raw_kind',rawidx.kind);cmp('kind',rawidx.kind.replace({'provider_core_seed':'atomic_settlement','atomic_residual':'atomic_settlement'}));cmp('center_id',rawidx.core_id);cmp('operational_view_id',c['operational_view_id']);cmp('display_retained',c['display_retained']);cmp('empirical_resolution_supported',c['empirical_resolution_supported']);cmp('historical_boundary_equivalence_proven',False)
 # Independent member/focal joins. Rural excludes exactly one declared focal, including other provider seeds.
 joined=m.merge(n.reset_index(drop=True),on='id',validate='many_to_one').merge(u[['unit_id','core_id']],on='unit_id',validate='many_to_one');pop=joined[joined._population_axis_row.eq(True)].copy();ext=pop[pop.id.ne(pop.core_id)].copy();rural=ext[ext.accepted_statistical_rural_role2021.eq(True)].copy();unknown=ext[ext.accepted_statistical_rural_role2021.isna()].copy();center=u[['unit_id','core_id']].rename(columns={'core_id':'id'}).merge(n.reset_index(drop=True),on='id',validate='many_to_one');member_pairs=set(zip(m.unit_id,m.id));ck('every_focal_member',all((uid,core) in member_pairs for uid,core in zip(u.unit_id,u.core_id)))
 # Avoid O(N*M) replay; every source membership belongs to exactly one unit by checked keys.
 center=center.set_index('unit_id',drop=False).loc[index];center.index.name='_unitkey';missing_core=~center._population_axis_row.eq(True);cmp('center_scope',pd.Series(np.where(center.id.isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB']),'external_metropolitan_context_anchor',np.where(~missing_core,'ordinary_source_settlement_focal','nonadditive_source_object_focal')),index=index))
 cmp('n_population_axis_settlements',cnt(pop));cmp('n_external_settlements',cnt(ext));cmp('n_rural_external_settlements',cnt(rural));cmp('n_unknown_role_external_settlements',cnt(unknown));cmp('rural_role_complete',cnt(unknown).eq(0));cmp('nonadditive_external_central_exception',missing_core&u.unit_role.eq('context_overlay'))
 for name,frame in [('central_object',center.reset_index(drop=True)),('rural_external_members',rural),('additive_whole_members',pop)]:
  groups=frame.groupby('unit_id',sort=False).id.agg(list).to_dict();cmp(name+'_set_sha256',pd.Series({k:hashlib.sha256(json.dumps(sorted(groups.get(k,[])),ensure_ascii=False,separators=(',',':')).encode()).hexdigest() for k in index}))
 for y in [2002,2010,2021]:
  pc='population_'+str(y);qc='population_value_quality_'+str(y)
  for f in [pop,rural,center]:f['_p']=valid(f[pc]);f['_q']=f[qc].fillna('quality_unavailable')
  total=sums(pop,'_p');ruralsum=sums(rural,'_p');nmiss=cnt(pop[pop._p.isna()]);full=cnt(pop).gt(0)&nmiss.eq(0)&~missing_core;cf=center._p.notna();rfull=cnt(rural[rural._p.isna()]).eq(0)&cnt(unknown).eq(0);primaryfull=full&cnt(pop[~pop._q.isin(PQUAL)]).eq(0)
  cmp(f'system_population_known_sum_{y}',total);cmp(f'system_known_additive_member_population_sum_{y}',total);cmp(f'system_population_complete_{y}',full);cmp(f'n_missing_population_{y}',nmiss);cmp(f'n_observed_zero_{y}',cnt(pop[pop._p.eq(0)]));cmp(f'center_population_{y}',center._p);cmp(f'center_population_complete_{y}',cf);cmp(f'own_population_{y}',center._p.where(atomic));cmp(f'own_population_complete_{y}',atomic&cf);cmp(f'rural_external_population_known_sum_{y}',ruralsum.where(cnt(rural).gt(0),0));cmp(f'rural_population_complete_{y}',rfull)
  sec=sums(pop[pop._q.eq(SQUAL)],'_p',empty=0).fillna(0).div(total).where(total.gt(0));cmp(f'population_secondary_protected_scope_unverified_known_population_share_{y}',sec);cmp(f'system_population_exact_primary_supported_{y}',primaryfull);cmp(f'classification_population_exact_primary_supported_{y}',primaryfull.where(~atomic,cf&center._q.isin(PQUAL)));cmp(f'classification_secondary_population_share_{y}',sec.where(~atomic,center._q.eq(SQUAL).astype(float).where(center._p.gt(0))))
  quality=pop.groupby(['unit_id','_q']).size();qualgroups={k:g.droplevel(0).to_dict() for k,g in quality.groupby(level=0,sort=False)};qdict={k:json.dumps(qualgroups.get(k,{}),ensure_ascii=False) for k in index};cmp(f'population_quality_counts_json_{y}',pd.Series(qdict),True);cmp(f'center_population_quality_counts_json_{y}',center._q.map(lambda s:json.dumps({s:1},ensure_ascii=False)),True)
 basis=pd.concat([pop[~pop.unit_id.isin(index[atomic])],center.loc[atomic].reset_index(drop=True)],ignore_index=True)
 for col in ['primary2010_overlay_applied','primary2010_numeric_changed','primary2010_quality_changed']:cmp({'primary2010_overlay_applied':'n_members_primary2010_newly_recovered','primary2010_numeric_changed':'n_members_primary2010_numeric_changed','primary2010_quality_changed':'n_members_primary2010_quality_changed'}[col],cnt(basis[basis[col].eq(True)]))
 for old in [False,True]:
  suffix='_prior' if old else '';p=valid(basis['population_2010'+suffix]);q=basis['population_value_quality_2010'+suffix].fillna('quality_unavailable');b=basis[['unit_id']].copy();b['p']=p;b['secondary']=p.where(q.eq(SQUAL),0);b['primary']=p.where(q.isin(PQUAL),0);den=sums(b,'p');sec=sums(b,'secondary').div(den).where(den.gt(0));cmp('prior_secondary2010_population_share' if old else 'current_secondary2010_population_share',sec)
  if not old:
   cmp('primary2010_population_share',sums(b,'primary').div(den).where(den.gt(0)));cmp('protected_secondary2010_population_share',sec);cmp('population2010_known_denominator',den);cmp('2010_missing_population_count',cnt(b[p.isna()]));b['recovered']=p.where(basis.primary2010_overlay_applied.eq(True),0);cmp('primary2010_newly_recovered_population_share',sums(b,'recovered').div(den).where(den.gt(0)))
 cmp('population_quality_share_denominator_scope',pd.Series(np.where(atomic,'own_source_series','known_nonnegative_additive_member_population2010'),index=index));cmp('unknown_nonadditive_central_population_slots2010',(missing_core&valid(center.population_2010).isna()).astype(int))
 ruralp=valid(rural.population_2021);rural=rural.copy();rural['_p21']=ruralp;cmp('rural_known_population2021_denominator',sums(rural,'_p21'));cmp('rural_known_population2021_n_missing',cnt(rural[rural._p21.isna()]));cmp('rural_weight_denominator_is_known_lowerbound',cnt(unknown).gt(0)|cnt(rural[rural._p21.isna()]).gt(0))
 scopes={'focal':center.reset_index(drop=True),'rural_members':rural,'all_members':joined}
 for w in c.get('context_projection',[]):
  s=scopes[w['scope']].copy();positive=pd.Series(False,index=s.index);known=positive.copy();rawcontrols={}
  for col in w['columns']:
   val=s[col];flag=val.eq(True).fillna(False) if w['kind']=='boolean' else valid(val).gt(0);obs=val.notna() if w['kind']=='boolean' else flag;positive|=flag;known|=obs;rawcontrols[col]=(val,flag)
  if w.get('observed_column'):known=s[w['observed_column']].eq(True).fillna(False);positive&=known
  prefix=w['output_column'];s['_weight']=valid(s.population_2021);den=sums(s,'_weight');kc=cnt(s[known]);pos=cnt(s[positive]);cmp(prefix,pos.gt(0).where(pos.gt(0),pd.NA));cmp(prefix+'_actual_source_observed_flag',kc.gt(0).where(kc.gt(0),pd.NA));cmp(prefix+'_n_positive_members',pos);cmp(prefix+'_n_source_observed_members',kc);cmp(prefix+'_n_source_scope_members',cnt(s));cmp(prefix+'_scope_known_population2021_denominator',den)
  for suffix,mask in [('source_observed_population_coverage2021',known),('positive_witness_population_share2021',positive)]:cmp(prefix+'_'+suffix,sums(s[mask],'_weight',empty=0).fillna(0).div(den).where(den.gt(0)))
  distinct=s.loc[known,['unit_id']+w['independent_source_unit_columns']].dropna().drop_duplicates();cmp(prefix+'_n_distinct_observed_source_units',cnt(distinct));cmp(prefix+'_source_year',w['year']);cmp(prefix+'_source_grain',w['grain']);cmp(prefix+'_statistical_source_unit_independence_claimed',False)
  controls={k:{} for k in index}
  for col,(val,flag) in rawcontrols.items():
   non=cnt(s[val.notna()]);yes=cnt(s[flag]);mis=cnt(s[val.isna()])
   for k in index:controls[k][col]={'n_field_nonmissing':int(non.loc[k]),'n_positive':int(yes.loc[k]),'n_missing':int(mis.loc[k])}
  cmp(prefix+'_raw_source_field_controls_json',pd.Series({k:json.dumps(v) for k,v in controls.items()}),True)
 for w in c.get('context_numeric_projection',[]):
  s=scopes[w['scope']].copy();v=pd.to_numeric(s[w['value_column']],errors='coerce');usable=v.notna()&np.isfinite(v)
  if w.get('observed_column'):usable&=s[w['observed_column']].eq(True).fillna(False)
  s['_weight']=valid(s.population_2021);s['_num']=v*s['_weight'];den=sums(s,'_weight');covered=sums(s[usable],'_weight');mean=sums(s[usable],'_num').div(covered).where(covered.gt(0));prefix=w['output_prefix'];cmp(prefix+'_weighted_mean',mean);cmp(prefix+'_known_population2021_denominator',den);cmp(prefix+'_source_observed_population_coverage2021',covered.fillna(0).div(den).where(den.gt(0)));cmp(prefix+'_n_distinct_observed_source_units',cnt(s.loc[usable,['unit_id']+w['independent_source_unit_columns']].dropna().drop_duplicates()));cmp(prefix+'_n_usable_NP_context_records',cnt(s[usable]));cmp(prefix+'_source_year',w['year']);cmp(prefix+'_source_grain',w['grain']);cmp(prefix+'_source_unit',w['unit']);cmp(prefix+'_statistical_source_unit_independence_claimed',False);cmp(prefix+'_is_population_exposure_context_not_ownNP_productivity',True)
 ck('all_watched_source_bytes_unchanged',all(sha(p)==s for p,s in watched.items()));ok=all(x['passed'] for x in checks);rec={'status':'ACCEPTED_INDEPENDENT_ALL_UNIT_POPULATION_CONTEXT_NORMALIZATION' if ok else 'REJECTED','all_checks_passed':ok,'n_checks':len(checks),'n_failed':sum(not x['passed'] for x in checks),'checks':checks,'n_units':nf,'accepted_units_sha256':sha(folder/'normalized_units.parquet') if ok else None,'units_sha256':sha(folder/'normalized_units.parquet'),'nodes_sha256':sha(folder/'effective_population_source_view.parquet'),'rural_excludes_exact_central_set':True,'whole_members_counted_once':True,'source_inputs_sha256':watched,'code_sha256':sha(__file__),'checked_unit_fields':sorted(x['check'][10:] for x in checks if x['check'].startswith('all_units_')),'unchecked_unit_fields':sorted(set(u.columns)-{x['check'][10:] for x in checks if x['check'].startswith('all_units_')}),'seconds':time.monotonic()-start,'limitations':'Projection/aggregation audit of admitted source cells. It does not make unknown context absence, prove historical boundary equality, or adopt477coordinate/relink frame. No producer import.'};(out/'audit.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');pd.DataFrame(witness).to_csv(out/'mismatch_witnesses.csv',index=False);print(json.dumps({k:rec[k] for k in ['status','n_units','n_checks','n_failed','seconds']}),flush=True);print(json.dumps([x for x in checks if not x['passed']],ensure_ascii=False),flush=True)
if __name__=='__main__':main()

"""Scalar implementation of the same source aggregation for singleton units."""
import json,math,hashlib
import pandas as pd
from classify_complete import truth,number
PRIMARY={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
SECONDARY='secondary_confidentiality_protected_value_exact_scope_unverified'
def valid(v):return number(v) is not None
def missing(v):return pd.isna(v)
def shares(p,q):return (float(q in PRIMARY),float(q==SECONDARY)) if valid(p) and float(p)>0 else (float('nan'),float('nan'))
def atom(d,c):
 row={};add=truth(d['_population_axis_row']) is True;ident=str(d['id']);emptyhash=hashlib.sha256(b'[]').hexdigest();selfhash=hashlib.sha256(json.dumps([ident],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 row.update(n_population_axis_settlements=int(add),n_external_settlements=0,n_rural_external_settlements=0,n_unknown_role_external_settlements=0,rural_role_complete=True,historical_boundary_equivalence_proven=False,nonadditive_external_central_exception=False,rural_known_population2021_denominator=float('nan'),rural_known_population2021_n_missing=0,rural_weight_denominator_is_known_lowerbound=False,central_object_set_sha256=selfhash,rural_external_members_set_sha256=emptyhash,additive_whole_members_set_sha256=selfhash if add else emptyhash)
 for y in (2002,2010,2021):
  p=d[f'population_{y}'];v=valid(p);q=d[f'population_value_quality_{y}'];q='quality_unavailable' if missing(q) else q;primary,secondary=shares(p,q)
  for obj in ('center','own'):row[f'{obj}_population_{y}']=float(p) if v else float('nan');row[f'{obj}_population_complete_{y}']=v
  row[f'system_population_known_sum_{y}']=float(p) if add and v else float('nan');row[f'system_known_additive_member_population_sum_{y}']=row[f'system_population_known_sum_{y}'];row[f'system_population_complete_{y}']=bool(add and v)
  row[f'n_missing_population_{y}']=int(add and not v);row[f'n_observed_zero_{y}']=int(add and v and float(p)==0)
  row[f'rural_external_population_known_sum_{y}']=0.;row[f'rural_population_complete_{y}']=True
  row[f'population_quality_counts_json_{y}']=json.dumps({q:1} if add else {},ensure_ascii=False);row[f'center_population_quality_counts_json_{y}']=json.dumps({q:1},ensure_ascii=False)
  row[f'population_secondary_protected_scope_unverified_known_population_share_{y}']=secondary if add else float('nan');row[f'system_population_exact_primary_supported_{y}']=bool(add and v and q in PRIMARY)
  row[f'classification_population_exact_primary_supported_{y}']=bool(v and q in PRIMARY);row[f'classification_secondary_population_share_{y}']=secondary
 p=d['population_2010'];q=d['population_value_quality_2010'];primary,secondary=shares(p,q)
 row['n_members_primary2010_newly_recovered']=int(truth(d['primary2010_overlay_applied']) is True)
 row['primary2010_newly_recovered_population_share']=float(row['n_members_primary2010_newly_recovered']) if valid(p) and float(p)>0 else float('nan')
 row['n_members_primary2010_numeric_changed']=int(truth(d['primary2010_numeric_changed']) is True);row['n_members_primary2010_quality_changed']=int(truth(d['primary2010_quality_changed']) is True)
 row['prior_secondary2010_population_share']=shares(d['population_2010_prior'],d['population_value_quality_2010_prior'])[1]
 row['current_secondary2010_population_share']=secondary;row['primary2010_population_share']=primary;row['protected_secondary2010_population_share']=secondary;row['population2010_known_denominator']=float(p) if valid(p) else float('nan');row['2010_missing_population_count']=int(not valid(p));row['population_quality_share_denominator_scope']='own_source_series';row['unknown_nonadditive_central_population_slots2010']=int(not add and not valid(p))
 for w in c.get('context_projection',[]):
  include=w['scope'] in ('focal','all_members');positive=False;known=False;raw={}
  for col in w['columns']:
   value=d[col];pos=truth(value) is True if w['kind']=='boolean' else valid(value) and float(value)>0
   obs=not missing(value) if w['kind']=='boolean' else pos
   if include:positive|=pos;known|=obs
   raw[col]={'n_field_nonmissing':int(include and not missing(value)),'n_positive':int(include and pos),'n_missing':int(include and missing(value))}
  if include and w.get('observed_column'):known=truth(d[w['observed_column']]) is True;positive=positive and known
  prefix=w['output_column'];weight=d['population_2021'];den=float(weight) if include and valid(weight) else float('nan')
  row[prefix]=True if positive else pd.NA;row[prefix+'_actual_source_observed_flag']=True if known else pd.NA;row[prefix+'_n_positive_members']=int(positive);row[prefix+'_n_source_observed_members']=int(known);row[prefix+'_n_source_scope_members']=int(include);row[prefix+'_raw_source_field_controls_json']=json.dumps(raw,ensure_ascii=False)
  row[prefix+'_scope_known_population2021_denominator']=den;row[prefix+'_source_observed_population_coverage2021']=float(known) if den>0 else float('nan');row[prefix+'_positive_witness_population_share2021']=float(positive) if den>0 else float('nan')
  row[prefix+'_n_distinct_observed_source_units']=int(known and all(not missing(d[x]) for x in w['independent_source_unit_columns']));row[prefix+'_source_year']=w['year'];row[prefix+'_source_grain']=w['grain'];row[prefix+'_statistical_source_unit_independence_claimed']=False
 for w in c.get('context_numeric_projection',[]):
  include=w['scope'] in ('focal','all_members');value=pd.to_numeric(d[w['value_column']],errors='coerce');usable=bool(include and not missing(value) and math.isfinite(float(value)))
  if w.get('observed_column'):usable=usable and truth(d[w['observed_column']]) is True
  weight=d['population_2021'];den=float(weight) if include and valid(weight) else float('nan');prefix=w['output_prefix']
  row[prefix+'_weighted_mean']=float(value) if usable and den>0 else float('nan');row[prefix+'_known_population2021_denominator']=den;row[prefix+'_source_observed_population_coverage2021']=float(usable) if den>0 else float('nan')
  row[prefix+'_n_distinct_observed_source_units']=int(usable and all(not missing(d[x]) for x in w['independent_source_unit_columns']));row[prefix+'_n_usable_NP_context_records']=int(usable);row[prefix+'_source_year']=w['year'];row[prefix+'_source_grain']=w['grain'];row[prefix+'_source_unit']=w['unit'];row[prefix+'_statistical_source_unit_independence_claimed']=False;row[prefix+'_is_population_exposure_context_not_ownNP_productivity']=True
 return row

"""Actual missingness/source attribution, no reclassification or imputation."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--normalized',required=True);ap.add_argument('--classified',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();d=Path(a.normalized);t=Path(a.classified);out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh diagnostic output required')
 nr=json.loads((d/'receipt.json').read_text());tr=json.loads((t/'receipt.json').read_text());assert tr['input_units_sha256']==nr['normalized_units_sha256'];assert tr['all_units_classified']
 ucols=[f'unknown_nonadditive_metropolitan_{role}_population_slots_{year}' for role in ('all','focal','nonfocal') for year in (2010,2021)]+['unit_id','kind','unit_role','center_id','name','region','center_scope','n_unknown_role_external_settlements']
 specs={'own':('own_population','own_population_complete'),'center':('center_population','center_population_complete'),'rural':('rural_external_population_known_sum','rural_population_complete'),'system':('system_population_known_sum','system_population_complete')}
 for pop,complete in specs.values():ucols.extend([f'{x}_{year}' for year in (2010,2021) for x in (pop,complete)])
 u=pd.read_parquet(d/'normalized_units.parquet',columns=ucols);types=pd.read_parquet(t/'complete_typology.parquet',columns=['unit_id','primary_type_id','primary_type_name','trajectory_class','classification_confidence']);u=u.merge(types,on='unit_id',validate='one_to_one');states=u.trajectory_class.map(json.loads);u=u.set_index('unit_id',drop=False);u.index.name=None
 ncols=['id','_population_axis_row','accepted_statistical_rural_role2021','population_2010','population_2021','population_value_quality_2010','source_record_id_2021']
 nodes=pd.read_parquet(d/'effective_population_source_view.parquet',columns=ncols);n=nodes.set_index('id',drop=False)
 m=pd.read_parquet(d/'memberships_scoped.parquet',columns=['unit_id','id']).merge(nodes,on='id',validate='many_to_one').merge(u[['unit_id','center_id','kind']],on='unit_id',validate='many_to_one')
 whole=m[m._population_axis_row.fillna(False)];external=whole[whole.id.ne(whole.center_id)];rural=external[external.accepted_statistical_rural_role2021.eq(True).fillna(False)];nonrural=external[external.accepted_statistical_rural_role2021.eq(False).fillna(False)]
 centers=u[['unit_id','center_id']].merge(nodes,left_on='center_id',right_on='id',validate='many_to_one')
 rows=[];full_descriptions={}
 for obj,data in [('own',centers),('center',centers),('rural',rural),('system',whole)]:
  z=data.copy();z['missing2010']=z.population_2010.isna();z['missing2021']=z.population_2021.isna();z['paired']=~z.missing2010&~z.missing2021;z['secondary2010']=z.population_value_quality_2010.eq('secondary_confidentiality_protected_value_exact_scope_unverified')&z.population_2010.notna();z['missing2010_known2021_P']=z.population_2021.where(z.missing2010);z['pairP2010']=z.population_2010.where(z.paired);z['pairP2021']=z.population_2021.where(z.paired)
  g=z.groupby('unit_id',sort=False);s=g[['population_2010','population_2021','missing2010_known2021_P','pairP2010','pairP2021']].sum(min_count=1);counts=g[['missing2010','missing2021','paired','secondary2010']].sum();counts['n_source_rows']=g.size();summary=s.join(counts)
  full_descriptions[obj]=summary
  for uid,r in u.iterrows():
   state=json.loads(r.trajectory_class).get(obj)
   if state is None:continue
   ss=summary.loc[uid] if uid in summary.index else pd.Series(dtype=object)
   pop,complete=specs[obj];reasons=[]
   for year in (2010,2021):
    if pd.isna(r[f'{pop}_{year}']):reasons.append(f'endpoint_population_{year}_missing')
    if not bool(r[f'{complete}_{year}']):reasons.append(f'incomplete_source_members_{year}')
   if obj=='rural' and r.n_unknown_role_external_settlements>0:reasons.append('unknown_statistical_rural_membership')
   if obj=='system':
    for year in (2010,2021):
     if r[f'unknown_nonadditive_metropolitan_all_population_slots_{year}']>0:reasons.append(f'nonadditive_metropolitan_member_own_population_{year}_unknown')
   if state=='not_applicable':reasons=['structurally_not_applicable']
   elif state!='unavailable':reasons=['observed_complete_series']
   numer=ss.get('missing2010_known2021_P',np.nan);denom=ss.get('population_2021',np.nan)
   fraction=float(numer/denom) if pd.notna(numer) and denom>0 else 0. if denom>0 and int(ss.get('missing2010',0))==0 else np.nan
   atomic=r.kind=='atomic_settlement';core=n.loc[r.center_id]
   valid=all(bool(r[f'{complete}_{y}']) and pd.notna(r[f'{pop}_{y}']) for y in (2010,2021))
   assert not(valid and state=='unavailable'),'Complete known pair rejected for reason other than declared data completeness'
   rows.append({'unit_id':uid,'unit_role':r.unit_role,'kind':r.kind,'object':obj,'state':state,'reason':'|'.join(reasons),'center_scope':r.center_scope,'n_source_rows':int(ss.get('n_source_rows',0)),'n_missing2010':int(ss.get('missing2010',0)),'n_missing2021':int(ss.get('missing2021',0)),'n_paired_observed_source_records':int(ss.get('paired',0)),'n_secondary2010_known_source_values':int(ss.get('secondary2010',0)),'known2021_population_denominator':denom,'missing2010_fraction_of_known2021_population':fraction,'observed_pair_cohort_P2010':ss.get('pairP2010',np.nan),'observed_pair_cohort_P2021':ss.get('pairP2021',np.nan),'primary_is_complete_whole_unit_not_partial_cohort':True,'core_has_native2021_record':pd.notna(core.source_record_id_2021),'core_population2010_missing':pd.isna(core.population_2010),'core_population2021_missing':pd.isna(core.population_2021),'classification_confidence':r.classification_confidence})
 result=pd.DataFrame(rows);out.mkdir(parents=True);result.to_parquet(out/'all_object_missingness_reasons.parquet',index=False)
 result.groupby(['unit_role','object','state','reason'],dropna=False).agg(n_units=('unit_id','size'),median_missing2010_share_of_known2021_P=('missing2010_fraction_of_known2021_population','median'),n_with_known_secondary2010=('n_secondary2010_known_source_values',lambda x:int(x.gt(0).sum()))).reset_index().to_csv(out/'reason_counts.csv',index=False)
 carry=result[result.object.eq('own')&result.state.eq('unavailable')];carry.groupby(['core_has_native2021_record','core_population2010_missing','core_population2021_missing'],dropna=False).size().rename('n_units').reset_index().to_csv(out/'carry_unavailable_attribution.csv',index=False)
 target=u[u.trajectory_class.map(lambda x:json.loads(x)=={'center':'decline','rural':'unavailable','system':'unavailable'})];targetids=set(target.unit_id);targetrows=result[result.unit_id.isin(targetids)];targetrows.to_csv(out/'center_decline_surroundings_unavailable.csv',index=False)
 cases=[]
 for uid,r in u.iterrows():
  st=json.loads(r.trajectory_class)
  if st!={'center':'growth','rural':'growth','system':'decline'}:continue
  z=nonrural[nonrural.unit_id.eq(uid)];row={'unit_id':uid,'name':r['name'],'region':r.region,'n_other_nonrural_members':len(z)}
  for y in (2010,2021):
   vals=z[f'population_{y}'];assert vals.notna().all();other=float(vals.sum())
   center=float(r[f'center_population_{y}']);rur=float(r[f'rural_external_population_known_sum_{y}']);wholep=float(r[f'system_population_known_sum_{y}']);assert center+rur+other==wholep
   row.update({f'center_P{y}':center,f'rural_P{y}':rur,f'other_nonrural_P{y}':other,f'whole_P{y}':wholep})
  for obj in ('center','rural','other_nonrural','whole'):row[obj+'_absolute_change']=row[obj+'_P2021']-row[obj+'_P2010']
  assert row['center_absolute_change']+row['rural_absolute_change']+row['other_nonrural_absolute_change']==row['whole_absolute_change'];cases.append(row)
 pd.DataFrame(cases).to_csv(out/'growth_center_rural_decline_whole_decomposition.csv',index=False)
 available_secondary=result[~result.state.isin(['unavailable','not_applicable'])&result.n_secondary2010_known_source_values.gt(0)]
 rural_target=targetrows[targetrows.object.eq('rural')];dist=rural_target.missing2010_fraction_of_known2021_population.dropna()
 receipt={'status':'COMPUTED_ACTUAL_MISSINGNESS_AND_ADDITIVE_COMPONENT_DIAGNOSIS','n_units':len(u),'n_all_object_rows':len(result),'known_complete_secondary_series_assigned_state':len(available_secondary),'n_available_pairs_rejected_due_to_quality':0,'carry_recent_unavailable':len(carry),'center_decline_rural_system_unavailable_units':len(target),'target_rural_missing2010_known2021_P_share_quantiles':{str(q):float(dist.quantile(q)) for q in (0,.25,.5,.75,1)} if len(dist) else {},'growth_center_rural_decline_whole_cases':len(cases),'component_identities_exact':True,'no_values_or_types_changed':True,'source_353_applied':True,'source_phase':'NEW477coordinate/institution/adminall/dominant-core source family plus admitted353 population2010; operationalcap endforest, not automatically empirical level','population_cohort_sums_are_diagnostics_not_whole_unit_imputations':True,'normalized_receipt_sha256':sha(d/'receipt.json'),'classification_receipt_sha256':sha(t/'receipt.json'),'code_sha256':sha(__file__),'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()

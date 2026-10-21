from pathlib import Path
import json,hashlib,numpy as np,pandas as pd,pyarrow.parquet as pq
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'model_inputs_cycle07/institutional_mass477_v1/computed';O=B/'reviews/cycle07_mass_pool477_independent';checks=[]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for x in iter(lambda:f.read(4<<20),b''):h.update(x)
 return h.hexdigest()
def ck(k,v,d=None):checks.append(dict(check=k,pass_=bool(v),detail=d))
def eq(a,b):return np.allclose(np.asarray(a,float),np.asarray(b,float),equal_nan=True,atol=1e-12,rtol=1e-11)
receipt=json.loads((P/'receipt.json').read_text());config=json.loads((B/'model_inputs_cycle06/final_access_v2/config_source_geography_inclusive_final.json').read_text());mass=pd.read_parquet(P/'fixed_own_mass_components.parquet');oldmass=pd.read_parquet(B/'model_inputs_cycle06/provisional_access_v2_source_geography_inclusive/fixed_own_mass_components.parquet');basep=B/'source_geography_recovery_cycle07/nodes_coordinate_overlay.parquet';newp=P/'effective_full_nodes.parquet';newcols=pq.ParquetFile(newp).schema_arrow.names;override={}
for fam,prefix in [('education','school_'),('commerce','services_'),('medical','medical_')]:
 f=pd.read_parquet(B/'model_inputs_cycle07/institutional_relink477_v1'/fam/'settlement_features_full_axis.parquet').set_index('id')
 for c in f:
  target=prefix+c
  if target in newcols:override[target]=f[c]
pop=pd.read_parquet(B/'typology/cycle07_complete/population_source353_v1/effective_population_source_view.parquet').set_index('id')
for c in ['population_2010','population_value_quality_2010']+[c for c in pop if c.startswith(('population2010_','primary2010_'))or c in ['population_2010_prior','population_value_quality_2010_prior']]:override[c]=pop[c]
required=set(['id','lat','lon','routable_coordinate','axis_kind','accepted_formal_settlement_subtype2021','accepted_subtype_has_dated2021_source','accepted_statistical_rural_role2021','source_record_id_2021','population_2021','_population_axis_row'])
for co in config['components']:required.update(co.get('columns',[]))
for opts in config['physical_features'].values():required.update(opts)
for opts in config['center_eligibility_2021_features'].values():required.update(opts)
required.update(config.get('rank_feature_columns',[]));required.update(config['center_eligibility_2021_admin_columns'])
for d in config['derived_features']:required.update(d['columns']);required.add(d['name'])
n=pd.read_parquet(newp,columns=sorted(required));ids=n.id;ck('all173864nodes_mass_source_IDorder',len(n)==173864 and n.id.is_unique and ids.equals(mass.id)and ids.equals(oldmass.id))
for d in config['derived_features']:
 ck('derived_disjoint_SUM_notMAX_'+d['name'],d['operation']=='sum_disjoint');expected=n[d['columns']].apply(pd.to_numeric,errors='coerce').sum(axis=1,min_count=1);override[d['name']]=pd.Series(expected.to_numpy(),index=ids);ck('all_derived_numeric_source_'+d['name'],eq(expected,n[d['name']]))
override['routable_coordinate']=pd.Series((np.isfinite(n[['lat','lon']]).all(axis=1)&n.lat.between(-90,90)&n.lon.between(-180,180)).to_numpy(),index=ids.to_numpy());bad=set();batches=0
for oldbatch,newbatch in zip(pq.ParquetFile(basep).iter_batches(batch_size=2048),pq.ParquetFile(newp).iter_batches(batch_size=2048)):
 a=oldbatch.to_pandas();z=newbatch.to_pandas();index=z.id
 for c in z:
  if c in override:
   source=override[c].reindex(index)
   if c in a:
    expected=a[c].copy();known=index.isin(override[c].index);expected.loc[known]=source.to_numpy()[known]
   else:expected=pd.Series(source.to_numpy(),index=z.index)
  elif c in a:expected=a[c]
  else:bad.add(c);continue
  try:pd.testing.assert_series_equal(z[c].reset_index(drop=True),expected.reset_index(drop=True),check_names=False,check_dtype=False,check_exact=True)
  except AssertionError:bad.add(c)
 batches+=1
ck('full173864x543_allcells_accepted_source_overlay_transform',not bad,sorted(bad));ck('full_batches_allrows',batches==int(np.ceil(173864/2048)))
physical={}
def physical_max(cols):
 v=n[cols].apply(pd.to_numeric,errors='coerce');return v.where(v>0).max(axis=1,skipna=True)
for name,cols in config['physical_features'].items():
 val=physical_max(cols);physical[name]=val;ck('actualphysical_proxy_'+name,eq(val,mass['physical_'+name+'_count_proxy']));ck('actualphysical_positive_'+name,np.array_equal(val.gt(0),mass['physical_'+name+'_positive_witness']))
components=json.loads((P/'mass_components.json').read_text());zs={}
for item,bind in zip(config['components'],components):
 val=physical[item['physical']]if item.get('physical')else n[item['columns']].apply(pd.to_numeric,errors='coerce').bfill(axis=1).iloc[:,0];x=np.log1p(val.where(val>=0))if item['transform']=='log1p'else val;mu=np.nanmean(x);sd=np.nanstd(x,ddof=0);z=(x-mu)/sd if sd>1e-12 else x*float('nan');zs[item['name']]=z;ck('source_raw_'+item['name'],eq(val,mass[item['name']+'_raw']));ck('source_global_z_'+item['name'],eq(z,mass[item['name']+'_z']));ck('source_global_parameters_'+item['name'],np.isclose(mu,bind['mean_transformed'],atol=1e-12)and np.isclose(sd,bind['sd_transformed'],atol=1e-12));ck('dated2021_noncatchment_'+item['name'],item['year']==2021 and 'catchment'not in str(item.get('columns',[])).lower())
blocks={}
for block in sorted({x['block']for x in components}):
 value=pd.DataFrame({x['name']:zs[x['name']]for x in components if x['block']==block}).mean(axis=1);blocks[block]=value;ck('independent_equal_component_block_'+block,eq(value,mass['block_'+block+'_z']))
z=pd.DataFrame(blocks);index=z.mean(axis=1);positive=np.exp(index.clip(-20,20)).where(z.notna().any(axis=1));ck('all173864_newownMi_fixed_formula',eq(positive,mass.own_positive_mass)and eq(index,mass.own_mean_standardized_index));ck('all_knownblockcounts',eq(z.notna().sum(axis=1),mass.n_observed_mass_blocks));ck('no_mass_catchment_or_future_fit',~mass.mass_uses_modeled_catchment.any()and~mass.mass_mixes_observation_dates.any());changed=~((oldmass.own_positive_mass==mass.own_positive_mass)|(oldmass.own_positive_mass.isna()&mass.own_positive_mass.isna()));ck('all6715globalnormalizationMi_changes_exact',changed.sum()==6715)
for co in config['components']:
 if co['block']!='service':ck('all_nonservice_raw_z_unchanged_'+co['name'],all(eq(oldmass[co['name']+s],mass[co['name']+s])for s in ['_raw','_z']))
observed={key:physical_max(config['center_eligibility_2021_features'][key]).gt(0)for key in ['education','healthcare','hospital','finance','administration','trade']};sub=n.accepted_formal_settlement_subtype2021.fillna('').str.casefold().str.replace('ё','е',regex=False);urban=(sub.isin(['город','пгт','поселок городского типа','рабочий поселок','курортный поселок','дачный поселок','городской поселок','рп','кп','дп','гп'])|n.accepted_statistical_rural_role2021.eq(False).fillna(False))&n.accepted_subtype_has_dated2021_source&n.source_record_id_2021.notna()&n.population_2021.notna();admin=n[config['center_eligibility_2021_admin_columns']].fillna(False).any(axis=1);functions=pd.DataFrame({f:observed[f]for f in ['education','healthcare','administration','finance']});diverse=functions.sum(axis=1).ge(2)&pd.DataFrame({f:observed[f]for f in ['education','healthcare','administration']}).any(axis=1);eligible=urban|admin|diverse|observed['hospital']|n.axis_kind.eq('external_service_provider');candidate=n.routable_coordinate&positive.notna()&eligible&~n.axis_kind.eq('federal_territory_source_unit');ck('all_candidate_source_flags',np.array_equal(candidate,mass.candidate_center)and np.array_equal(urban,mass.candidate_native2021_formal_urban_witness)and np.array_equal(admin,mass.candidate_official2021_administrative_role_witness));ck('restricted_candidates9329_secondary_to_newpool',candidate.sum()==9329)
for p,h in receipt['inputs_sha256'].items():ck('actual_inputSHA_'+p,sha(p)==h)
for p,h in receipt['outputs_sha256'].items():ck('actual_outputSHA_'+p,sha(P/p)==h)
res=dict(status='ACCEPTED'if all(x['pass_']for x in checks)else'REJECTED',all_checks_passed=all(x['pass_']for x in checks),n_checks=len(checks),n_failed=sum(not x['pass_']for x in checks),checks=checks,accepted_mass_sha256=sha(P/'fixed_own_mass_components.parquet'),accepted_nodes_sha256=sha(newp),accepted_mass_receipt_sha256=sha(P/'receipt.json'),scope='Full173864x543 acceptedsource transformation incl477coords/threeinstitutionalfeaturefamilies/353effectiveprimary2010; allglobalraw/z/physical/proxy/equalblocks/ownMi andrestrictedcandidate flags independentlyrebuilt. Newdatedseatprovidereligibility separate; localrolesnotmasscapacity. All2010proofs orthogonaltoMi2021. Noq/Huff/hierarchyoutcomes accepted.');(O/'mass_admission.json').write_text(json.dumps(res,indent=2)+'\n');print(res['status'],res['n_checks'],res['n_failed']);print([x for x in checks if not x['pass_']])

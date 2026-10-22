"""End-to-end implementation check on four fabricated nodes; never a research result."""
from pathlib import Path
import json,hashlib,subprocess,sys
import pandas as pd
import test_word_model as t
BASE=Path(__file__).resolve().parent/'_synthetic_integration'
BASE.mkdir(exist_ok=True)
n,c,r,g=t.fixture();g['model'].update({'random_seed':1,'maximum_rank_components':2,'minimum_rank_cluster_size':1});n['school_count']=[0.,1.,2.,0.];n['is_additive_source_unit']=True
for year in [2002,2010,2021]:n[f'population_value_quality_{year}']='direct_published_census_value'
n.to_parquet(BASE/'axis.parquet',index=False);r.to_parquet(BASE/'candidate_travel_times.parquet',index=False)
pd.DataFrame({'id':['v','c','h'],'routing_budget_minutes':[360]*3}).to_parquet(BASE/'route_destination_index.parquet',index=False)
pd.DataFrame({'id':['v','c','h']}).to_parquet(BASE/'route_origin_index.parquet',index=False)
pd.DataFrame({'id':pd.Series([],dtype='str')}).to_parquet(BASE/'route_destination_rejections.parquet',index=False)
(BASE/'routing_receipt.json').write_text(json.dumps({'status':'COMPUTED','output_sha256':hashlib.sha256((BASE/'candidate_travel_times.parquet').read_bytes()).hexdigest(),'synthetic':True}))
g.update({'axis':str(BASE/'axis.parquet'),'travel_edges':str(BASE/'candidate_travel_times.parquet'),'mass_reference_year':2010,'physical_features':{'education':['school_count'],'healthcare':[],'hospital':[],'trade':[],'finance':[],'administration':[]},'components':[{'name':'own_population','block':'demography','columns':['population_2010'],'transform':'log1p','year':2010},{'name':'school','block':'service','physical':'education','transform':'log1p','year':2010}],'initial_assignment_center_scope':'lowest_empirical_order_only','target_run_id':'SYNTHETIC_NOT_RESEARCH'})
(BASE/'config.json').write_text(json.dumps(g))
subprocess.run([sys.executable,str(Path(t.m.__file__)),'--inputs',str(BASE/'config.json'),'--output',str(BASE/'output'),'--stage','full'],check=True,stdout=subprocess.DEVNULL)
receipt=json.loads((BASE/'output/run_receipt.json').read_text());assert receipt['status']=='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW';assert receipt['scientific_acceptance'] is False
assert pd.read_csv(BASE/'output/population_balances.csv').known_population_conserved.all()
assert pd.read_parquet(BASE/'output/systems.parquet').n_population_axis_settlements.gt(0).all()
print('Synthetic full CLI PASS: scopeverification/Arrow/Huff/hierarchy/quality/types/functionleaders/outputreceipts; NOT scientific validation')
# Exact compact adapter equivalence, including float32 connector and self override.
import numpy as np
mapping=pd.DataFrame({'id':n.id,'snap_km':[.0123456789,.02,.03,.04]})
om=mapping.copy();om['origin_index']=np.arange(len(om),dtype='uint32');om.to_parquet(BASE/'route_origin_index.parquet',index=False)
dm=mapping.copy();dm['destination_index']=np.arange(len(dm),dtype='uint32');dm['routing_budget_minutes']=360;dm.to_parquet(BASE/'route_destination_index.parquet',index=False)
index=pd.Series(np.arange(len(n)),index=n.id);oi=r.origin_id.map(index).to_numpy('uint32');di=r.destination_id.map(index).to_numpy('uint32');network=r.travel_minutes.to_numpy('float32');snap=mapping.snap_km.to_numpy(float)*4.;connector=(snap[oi]+snap[di]).astype('float32');total=(network+connector).astype('float32');total[oi==di]=0.
compact=pd.DataFrame({'origin_index':oi,'destination_index':di,'network_minutes':network});compact.to_parquet(BASE/'compact_part.parquet',index=False)
plain=r.copy();plain['travel_minutes']=total;plain.to_parquet(BASE/'candidate_travel_times.parquet',index=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'format':'compact_parquet_parts_v1','rows':len(compact),'origin_mapping':{'path':'route_origin_index.parquet','sha256':sha(BASE/'route_origin_index.parquet'),'index_column':'origin_index'},'destination_mapping':{'path':'route_destination_index.parquet','sha256':sha(BASE/'route_destination_index.parquet'),'index_column':'destination_index'},'parts':[{'path':'compact_part.parquet','rows':len(compact),'sha256':sha(BASE/'compact_part.parquet')}]}
(BASE/'candidate_travel_times_manifest.json').write_text(json.dumps(manifest))
mass=pd.DataFrame({'id':n.id,'physical_education_count_proxy':[np.nan,1.,2.,np.nan]})
standard,_=t.m.load_travel(g,n,c,mass)
g['travel_manifest']=str(BASE/'candidate_travel_times_manifest.json');encoded,_=t.m.load_travel(g,n,c,mass)
for data in [standard,encoded]:data.sort_values(['origin_id','destination_id'],inplace=True);data.reset_index(drop=True,inplace=True)
pd.testing.assert_frame_equal(standard,encoded,check_flags=False,check_dtype=True)
(BASE/'config.json').write_text(json.dumps(g));(BASE/'routing_receipt.json').write_text(json.dumps({'status':'COMPUTED','output_manifest_sha256':sha(BASE/'candidate_travel_times_manifest.json'),'synthetic':True}))
subprocess.run([sys.executable,str(Path(t.m.__file__)),'--inputs',str(BASE/'config.json'),'--output',str(BASE/'output_compact'),'--stage','full'],check=True,stdout=subprocess.DEVNULL)
assert pd.read_csv(BASE/'output_compact/population_balances.csv').known_population_conserved.all()
print('Exact compact-vs-string float32 equivalence and full compact CLI PASS; NOT scientific validation')

om.loc[om.id.eq('h'),'id']='raw:H';om['canonical_id']=om.id.replace({'raw:H':'h'});om.to_parquet(BASE/'route_origin_index.parquet',index=False)
manifest['origin_mapping']['sha256']=sha(BASE/'route_origin_index.parquet');(BASE/'candidate_travel_times_manifest.json').write_text(json.dumps(manifest));g['route_id_aliases']={'raw:H':'h'}
aliased,_=t.m.load_travel(g,n,c,mass);aliased.sort_values(['origin_id','destination_id'],inplace=True);aliased.reset_index(drop=True,inplace=True)
pd.testing.assert_frame_equal(standard,aliased,check_flags=False,check_dtype=True)
assert aliased[aliased.origin_id.eq('h')&aliased.destination_id.eq('h')].travel_minutes.eq(0).all()
print('Canonical origin alias preserves exact rows/selfzero PASS')

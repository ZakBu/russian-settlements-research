"""Every actual core/rural/whole/prior population stats tuple vs admitted scalar helper."""
import argparse,hashlib,json,math,time
from pathlib import Path
import pandas as pd
import numpy as np
from normalize_unit_populations_source477_v4 import stats
from population_statistics_array import stats_array

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def same(a,b):
 if isinstance(a,str):return json.loads(a)==json.loads(b) if a.startswith('{') else a==b
 if pd.isna(a) or pd.isna(b):return bool(pd.isna(a) and pd.isna(b))
 return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-12)
def main():
 p=argparse.ArgumentParser();p.add_argument('--normalized',required=True);p.add_argument('--output',required=True);a=p.parse_args();d=Path(a.normalized);out=Path(a.output);assert not out.exists();t=time.monotonic();cols=['id','_population_axis_row','accepted_statistical_rural_role2021']+[f'{v}_{y}' for y in (2002,2010,2021) for v in ('population','population_value_quality')]+['population_2010_prior','population_value_quality_2010_prior'];n=pd.read_parquet(d/'effective_population_source_view.parquet',columns=cols).set_index('id',drop=False);m=pd.read_parquet(d/'memberships_scoped.parquet',columns=['unit_id','id']);groups=m.groupby('unit_id').id.agg(list).to_dict();u=pd.read_parquet(d/'normalized_units.parquet',columns=['unit_id','core_id','kind']);n_atomic_unchanged=int(u.kind.eq('atomic_settlement').sum());u=u[~u.kind.eq('atomic_settlement')];bad=[];checks=0
 for _,r in u.iterrows():
  raw=n.loc[groups[r.unit_id]];whole=raw[raw._population_axis_row.fillna(False)];rural=whole[whole.id.ne(r.core_id)&whole.accepted_statistical_rural_role2021.eq(True).fillna(False)];core=n.loc[[r.core_id]];prior=whole.copy();prior['population_2010']=prior.population_2010_prior;prior['population_value_quality_2010']=prior.population_value_quality_2010_prior
  for name,z,years in [('core',core,(2002,2010,2021)),('whole',whole,(2002,2010,2021)),('rural',rural,(2002,2010,2021)),('prior',prior,(2010,))]:
   for y in years:
    old=stats(z,y);new=stats_array(z,y)
    for k in old:
     checks+=1
     if not same(old[k],new[k]):bad.append({'unit_id':r.unit_id,'object':name,'year':y,'field':k,'scalar':repr(old[k]),'array':repr(new[k])})
 out.mkdir(parents=True);pd.DataFrame(bad).to_csv(out/'differences.csv',index=False);r={'status':'COMPUTED_SOURCE_EQUIVALENCE_ARRAY_POPULATION_STATS','n_actual_functional_units':len(u),'n_atomic_fastpath_units_unchanged':n_atomic_unchanged,'n_compared_stats_fields':checks,'n_differences':len(bad),'all_equal':not bad,'source_units_sha256':sha(d/'normalized_units.parquet'),'source_nodes_sha256':sha(d/'effective_population_source_view.parquet'),'array_helper_sha256':sha(Path(__file__).with_name('population_statistics_array.py')),'scalar_reference_sha256':sha(Path(__file__).with_name('normalize_unit_populations_source477_v4.py')),'seconds':time.monotonic()-t,'author_equivalence_not_independent_admission':True};(out/'receipt.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
 if bad:raise ValueError('Population stats differ')
if __name__=='__main__':main()

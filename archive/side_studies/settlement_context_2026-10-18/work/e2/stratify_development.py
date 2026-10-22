"""Descriptive subgroup error check; no new fit/no holdout outcomes."""
import pandas as pd,numpy as np
from pathlib import Path
p=Path('research_staging/e2/development')
d=pd.read_parquet(p/'predictions.parquet');f=pd.read_csv('research_staging/geo/features.csv.gz',usecols=['entity_uid','population_2010','r30_mass2010','r30_maxshare'])
d=d.merge(f,on='entity_uid',validate='one_to_one');rows=[]
for axis,group in [('P2010',pd.cut(d.population_2010,[0,10,100,1000,10000,np.inf],right=False)),('terminal_zero',d.observed.eq(-2))]:
 for key,g in d.groupby(group,observed=True):
  b=g.baseline_loss.mean();a=g.augmented_loss.mean();rows.append({'axis':axis,'group':str(key),'n':len(g),'baseline_mae':b,'augmented_mae':a,'delta_mae':b-a,'relative_improvement':(b-a)/b})
pd.DataFrame(rows).to_csv('research_staging/e2/development_subgroups.csv',index=False)

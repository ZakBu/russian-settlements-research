"""X2010-only development support diagnostic and prespecified illustrative pairs. Never reads2021."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'statistics'))
from statistical_utils import split_blocks
p=Path('research_staging/geo/features.csv.gz');d=pd.read_csv(p)
_,hold,_=split_blocks(d.longitude_2010,d.latitude_2010)
d=d.loc[(~hold)&(d.population_2010>0)].copy()
cs=['population_2010','r30_mass2010','r30_count_all','r30_maxshare','r30_effective_n','nearest_larger_km','nearest_larger_size_ratio']
corr=d[cs].corr(method='spearman');corr.to_csv('research_staging/e2/development_X_spearman.csv')
positive=d.r30_mass2010>0
err=((d.loc[positive,'r30_effective_n']>d.loc[positive,'r30_count_positive']+1e-6)|(d.loc[positive,'r30_effective_n']<1-1e-6)).sum();assert not err
shares=d.loc[positive,'r30_maxshare'].to_numpy();hhi=1/d.loc[positive,'r30_effective_n'].to_numpy();assert np.all(hhi>=shares**2-1e-10) and np.all(hhi<=shares+1e-10)
# All candidate selection uses baseline2010 only. Radius query checks multiplicative tolerances.
candidates=[]
for region,g in d.loc[positive&(d.r30_count_all>0)].groupby('effective_region_norm_2010',dropna=False):
 g=g.sort_values('entity_uid').reset_index(drop=True)
 z=np.column_stack([np.log(g.population_2010)/np.log(1.1),np.log(g.r30_mass2010)/np.log(1.1),np.log(g.r30_count_all)/np.log(1.2),g.nearest_ge100000_km/20])
 tree=cKDTree(z)
 for i in range(len(g)):
  js=tree.query_ball_point(z[i],r=1,p=np.inf)
  for j in js:
   if j<=i or abs(g.r30_maxshare.iloc[i]-g.r30_maxshare.iloc[j])<.25:continue
   a,b=g.iloc[i],g.iloc[j]
   candidates.append({'uid_a':a.entity_uid,'uid_b':b.entity_uid,'region':str(region),'p2010_a':a.population_2010,'p2010_b':b.population_2010,'mass30_a':a.r30_mass2010,'mass30_b':b.r30_mass2010,'count30_a':a.r30_count_all,'count30_b':b.r30_count_all,'maxshare30_a':a.r30_maxshare,'maxshare30_b':b.r30_maxshare,'effective_n30_a':a.r30_effective_n,'effective_n30_b':b.r30_effective_n,'distance100k_a':a.nearest_ge100000_km,'distance100k_b':b.nearest_ge100000_km})
candidates.sort(key=lambda r:(r['uid_a'],r['uid_b']))
# No re-use of UID, deterministic first five for final report.
selected=[];used=set()
for r in candidates:
 if r['uid_a'] not in used and r['uid_b'] not in used:
  selected.append(r);used.update([r['uid_a'],r['uid_b']])
 if len(selected)==5:break
pd.DataFrame(selected).to_csv('research_staging/e2/illustrative_pairs_preoutcome.csv',index=False)
summary={'feature_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'holdout_y_read':False,'development_positive_p2010_n':len(d),'mass_positive_n':int(positive.sum()),'degenerate_npositive_le1':int((d.r30_count_positive<=1).sum()),'mass_zero_n':int((~positive).sum()),'larger_missing_n':int(d.nearest_larger_km.isna().sum()),'hierarchy_effectiveN_bounds_violations':int(err),'matching_pairs_available':len(candidates),'selected_pairs':len(selected),'selection':'lexicographicUID,one region,Pself andM within10percent,n within20percent,distance100k within20km,maxshare contrast>=0.25,no outcomes read','interpretation':'Overlap demonstrated for illustrative subset only; not causal matching or national positivity proof.'}
Path('research_staging/e2/development_X_support.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False))

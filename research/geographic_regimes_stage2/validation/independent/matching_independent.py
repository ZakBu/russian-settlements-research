"""Reconstruct matching independently; primary compare.py never read."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
out=Path('stage2_work/replication');t=pd.read_csv('stage2_work/geo/outputs/territory_metrics.csv')
features=['logpop2002','logn2002','top10_share2002','size_fraction_lt10','size_fraction_10_99','size_fraction_100_999','log_size_median2002','log_size_p90_2002','log_nn2002','log_centre100k2002']
for dest,src in [('log_size_median2002','size_median2002'),('log_size_p90_2002','size_p90_2002'),('log_nn2002','nn2002_km_median'),('log_centre100k2002','centre100k2002_km_median')]:t[dest]=np.log1p(t[src])
expect=[];scales=[]
for kind in ['region','grid50','grid25','grid100','grid50shift25']:
 d=t[(t.kind==kind)&(t.n_positive2002>=20)].copy();d=d[np.isfinite(d[features]).all(axis=1)].sort_values('unit').reset_index(drop=True)
 x=d[features].to_numpy();m=np.median(x,axis=0);scale=np.quantile(x,.75,axis=0)-np.quantile(x,.25,axis=0);sd=np.std(x,axis=0);scale=np.where(scale==0,sd,scale);keep=scale>0;z=(x[:,keep]-m[keep])/scale[keep]
 for i,f in enumerate(features):scales.append(dict(kind=kind,feature=f,median=m[i],scale=scale[i],retained=bool(keep[i]),n=len(d)))
 for i in range(len(d)):
  dif=np.abs(z[i+1:]-z[i]);maxd=np.max(dif,axis=1);rms=np.sqrt(np.mean(dif**2,axis=1));js=np.where((maxd<=1)&(rms<=.5))[0]
  for a in js:
   j=i+1+a;rec=dict(kind=kind,unit_a=d.loc[i,'unit'],unit_b=d.loc[j,'unit'],max_abs_std_diff=maxd[a],rms_std_diff=rms[a]);rec.update({'std_diff_'+f:float(dif[a,k]) for k,f in enumerate(np.array(features)[keep])});expect.append(rec)
pd.DataFrame(scales).to_csv(out/'independent_matching_scales.csv',index=False)
e=pd.DataFrame(expect);e.to_csv(out/'independent_all_matching.csv.gz',index=False)
json.dump({'status':'expectation_created','n':len(e),'counts':e.groupby('kind').size().to_dict(),'main_compare_not_read':True},open(out/'matching_receipt.json','w'),indent=2)
print(e.groupby('kind').size())

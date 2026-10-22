"""Premetric finite knee/stability rule; no population-scale constraints."""
import numpy as np

def objective_knee(objectives,min_fraction=.05,min_points=10,min_relative_gain=.25):
 y=np.asarray(objectives,dtype=float);n=len(y)
 if n<2 or not np.isfinite(y).all():return dict(status='invalid_objective_path',selected_merge=None)
 x=np.arange(n,dtype=float);side=max(min_points,int(np.ceil(min_fraction*(n-1))))
 if n<2*side+1:return dict(status='no_knee_insufficient_merge_path',selected_merge=None,n_points=n,min_side=side)
 sx=np.r_[0.,np.cumsum(x)];sy=np.r_[0.,np.cumsum(y)];sxx=np.r_[0.,np.cumsum(x*x)];syy=np.r_[0.,np.cumsum(y*y)];sxy=np.r_[0.,np.cumsum(x*y)]
 def sse(lo,hi):
  count=hi-lo;a=sx[hi]-sx[lo];b=sy[hi]-sy[lo];xx=sxx[hi]-sxx[lo]-a*a/count;yy=syy[hi]-syy[lo]-b*b/count;xy=sxy[hi]-sxy[lo]-a*b/count
  return max(0.,yy-(xy*xy/xx if xx>1e-15 else 0.))
 single=sse(0,n);candidates=[(sse(0,k+1)+sse(k,n),k) for k in range(side,n-side)]
 loss,k=min(candidates);gain=(single-loss)/single if single>1e-12 else 0.
 return dict(status='candidate_knee' if gain>=min_relative_gain else 'no_knee',selected_merge=int(k) if gain>=min_relative_gain else None,relative_sse_gain=float(gain),single_line_sse=float(single),two_line_sse=float(loss),n_points=n,min_side=side)

def accept_stable_cut(aris,knee_fractions,expected_replicates=50):
 a=np.asarray(aris,float);k=np.asarray(knee_fractions,float)
 if len(a)!=expected_replicates or len(k)!=expected_replicates:return dict(accepted=False,reason='missing_requested_replicates',n_valid=0)
 good=np.isfinite(a)&np.isfinite(k)
 # Do not silently ignore failed/no-knee/low-comparison-coverage repetitions.
 if len(a)!=expected_replicates or len(k)!=expected_replicates or good.sum()<40:return dict(accepted=False,reason='fewer_than_40_of_50_assessable',n_valid=int(good.sum()))
 a=a[good];k=k[good]
 med=float(np.median(a));p10=float(np.quantile(a,.1));iqr=float(np.quantile(k,.75)-np.quantile(k,.25))
 return dict(accepted=med>=.8 and p10>=.6 and iqr<=.15,median_ari=med,p10_ari=p10,knee_fraction_iqr=iqr,n_valid=int(good.sum()),n_total=expected_replicates,strict_50_of_50=bool(good.all()),scope='conditional_geographic_weight_perturbation_not_probability_CI')

if __name__=='__main__':
 assert objective_knee(np.arange(101)*.1)['status']=='no_knee'
 a=np.r_[np.arange(51)*.1,5+np.arange(1,51)*.001];r=objective_knee(a)
 assert r['status']=='candidate_knee' and abs(r['selected_merge']-50)<=1
 assert objective_knee([0,1,2])['status']=='no_knee_insufficient_merge_path'
 assert not accept_stable_cut([.99]*49,[.1]*49)['accepted']
 assert accept_stable_cut([.99]*49+[float('nan')],[.1]*50)['accepted']
 assert not accept_stable_cut([.99]*39+[float('nan')]*11,[.1]*50)['accepted']
 assert accept_stable_cut([.99]*50,[.1]*50)['accepted']
 print('Knee/no-knee/short-path/failed-stability counterexamples PASS')

import numpy as np
from build import elbow,fit_spectrum
# PurelinearSSEcurve has no engineering elbow, rather than forced K.
linear=[{'K':k,'sse':11-k,'positive_provider_class_counts':[100]*k}for k in range(1,11)];assert elbow(linear)['K'] is None
flat=[{'K':k,'sse':0.,'positive_provider_class_counts':[100]*k}for k in range(1,11)];assert elbow(flat)['K'] is None
# Exacttwo-slopepiecewise kink at3 is recovered, then invalidtinyclass rejected.
kink=[{'K':k,'sse':(11-2*k if k<=3 else 5-.1*(k-3)),'positive_provider_class_counts':[100]*k}for k in range(1,11)];assert elbow(kink)['K']==3
kink[2]['positive_provider_class_counts']=[100,100,1];assert elbow(kink)['K']is None
rng=np.random.default_rng(7);x=np.r_[rng.normal(-3,.05,100),rng.normal(0,.05,100),rng.normal(3,.05,100)];curve,e,fits=fit_spectrum(x,np.ones(len(x)));assert [r['K']for r in curve]==list(range(1,11))
for k,(mu,b,label)in fits.items():
 assert np.all(np.diff(mu)>0) and np.array_equal(label,np.searchsorted(b,x,side='left'))
 assert np.isclose(curve[k-1]['sse'],np.sum((x-mu[label])**2))
assert e['K']==3,(e,curve)
# Geographicweight perturbation may removeclasssupport; no fabricatedabsence.
w=np.r_[np.ones(100),np.zeros(100),np.ones(100)];c,e,f=fit_spectrum(x,w);assert sum(c[0]['positive_provider_class_counts'])==200
print('Linear/degenerate no-elbow, known3kink, minclassguard, allK SSE/order/boundaries, regionalzero-weight handling PASS')

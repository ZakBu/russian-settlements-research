#!/usr/bin/env python3
"""Independent metrics from CSV. Usage: file.csv y_col baseline_col augmented_col block_col metric(mae|brier).
Does not import learner or statistical_utils. Uses stdlib for point estimates.
"""
import csv,gzip,sys,math,json,hashlib,random
from collections import defaultdict
path,ycol,bcol,acol,blockcol,kind=sys.argv[1:]
if kind not in ("mae","brier"):raise ValueError("Choose mae or brier explicitly")
openfn=gzip.open if path.endswith('.gz') else open
blocks=defaultdict(lambda:[0.,0.,0]);seen=set();n=0
with openfn(path,'rt',newline='') as f:
 for r in csv.DictReader(f):
  uid=r['entity_uid']
  if uid in seen:raise ValueError('duplicate UID')
  seen.add(uid);y,b,a=map(float,[r[ycol],r[bcol],r[acol]])
  if not all(map(math.isfinite,(y,b,a))):raise ValueError('nonfinite')
  lb=(y-b)**2 if kind=='brier' else abs(y-b);la=(y-a)**2 if kind=='brier' else abs(y-a)
  v=blocks[r[blockcol]];v[0]+=lb;v[1]+=la;v[2]+=1;n+=1
sums=list(blocks.values());base=sum(x[0] for x in sums)/n;aug=sum(x[1] for x in sums)/n
rng=random.Random(20261018);boot=[]
for _ in range(1999):
 draw=rng.choices(sums,k=len(sums));boot.append(sum(x[0]-x[1] for x in draw)/sum(x[2] for x in draw))
boot.sort()
def quant(q):
 x=q*(len(boot)-1);i=int(x);return boot[i]+(boot[min(i+1,len(boot)-1)]-boot[i])*(x-i)
print(json.dumps({'input_sha256':hashlib.sha256(open(path,'rb').read()).hexdigest(),'n':n,'blocks':len(blocks),'metric':kind,'baseline_loss':base,'augmented_loss':aug,'delta':base-aug,'relative_gain':(base-aug)/base,'ci95_independent_rng':[quant(.025),quant(.975)],'ci_note':'Independent Python RNG, same block-bootstrap estimand; Monte Carlo endpoints need not match NumPy draw stream exactly','replicates':1999,'seed':20261018},indent=2))

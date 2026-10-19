#!/usr/bin/env python3
"""Independent compact raw-INN partitions, no repeated annual stock build.

Only INN, OKTMO, OKVED, section; bounded batches, compact integer join tables.
Independent relational merge versus the author's intersect1d/bincount approach.
"""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent/'wave2';O.mkdir(exist_ok=True)
GROUPS={'retail47':('G',{'47'}),'food56':('I',{'56'}),'education85':('P',{'85'}),'health86':('Q',{'86'}),'social8788':('Q',{'87','88'}),'repair95':('S',{'95'}),'personal96':('S',{'96'})}
def norm(s):
 z=s.astype('string').str.strip();return z.where(z.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
def read(y,lookup):
 path=R/f'economy/remote_selected/rfsd_{y}_identity_function_selected.parquet';inns=[];points=[];masks=[]
 for b in pq.ParquetFile(path).iter_batches(batch_size=100000,columns=['inn','oktmo','okved','okved_section']):
  d=b.to_pandas();d=d[d.inn.astype('string').str.fullmatch('[0-9]{10}',na=False)].copy();inns.append(d.inn.to_numpy().astype(np.uint64));points.append(norm(d.oktmo).map(lookup).fillna(-1).to_numpy(dtype=np.int32));prefix=d.okved.astype('string').str[:2];mask=np.zeros(len(d),np.uint8)
  for gi,(g,(sec,ps)) in enumerate(GROUPS.items()):mask+=((prefix.isin(ps)&d.okved_section.eq(sec)).fillna(False).to_numpy(dtype=np.uint8))*(2**gi)
  masks.append(mask)
 return pd.DataFrame({'inn':np.concatenate(inns),'point':np.concatenate(points),'mask':np.concatenate(masks)})
def main():
 p=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet',columns=['id','oktmo_2021']);lookup=pd.Series(np.arange(len(p),dtype=np.int32),index=norm(p.oktmo_2021));n=len(p);author=pd.read_csv(R/'economy/pinned_calendar/adjacent_year_INN_cohorts.csv');functions=pd.read_csv(R/'economy/pinned_calendar/adjacent_same_INN_same_point_function_transitions.csv');previous=None;rows=[];frows=[];checks=[];sources={};bitcount=np.array([i.bit_count() for i in range(128)],np.uint8)
 def ck(n,v):checks.append({'name':n,'pass':bool(v)})
 for year in range(2011,2026):
  current=read(year,lookup);source=R/f'economy/remote_selected/{year}_acquisition.json';sources[str(year)]=json.loads(source.read_text())['selected_file_sha256']
  ck(f'identity_unique_{year}',current.inn.is_unique)
  if previous is not None:
   joined=previous.merge(current,on='inn',how='inner',suffixes=('_a','_b'),validate='one_to_one',sort=False);x=joined.point_a.to_numpy();y=joined.point_b.to_numpy();both=(x>=0)&(y>=0);same=both&(x==y)
   vals={'valid_INN_from':len(previous),'valid_INN_to':len(current),'common_INN':len(joined),'only_from_INN_not_proven_death':len(previous)-len(joined),'only_to_INN_not_proven_birth':len(current)-len(joined),'same_exact_point':int(same.sum()),'different_exact_points':int((both&~same).sum()),'exact_from_only':int(((x>=0)&(y<0)).sum()),'exact_to_only':int(((x<0)&(y>=0)).sum()),'neither_exact':int(((x<0)&(y<0)).sum())};rows.append(dict(from_year=year-1,to_year=year,**vals));aa=author[author.from_year.eq(year-1)&author.to_year.eq(year)].iloc[0]
   for k,v in vals.items():ck(f'partition_{year-1}_{year}_{k}',v==aa[k])
   # Union the activity masks of identities that remain at the same exact point.
   # OR is sufficient for presence and avoids duplicating author bincount code.
   left=np.zeros(n,np.uint8);right=np.zeros(n,np.uint8);loc=x[same];np.bitwise_or.at(left,loc,joined.mask_a.to_numpy()[same]);np.bitwise_or.at(right,loc,joined.mask_b.to_numpy()[same])
   for feature in list(GROUPS)+['direct_diversity_ge1','direct_diversity_ge2','direct_diversity_ge3']:
    if feature in GROUPS:
     bit=2**list(GROUPS).index(feature);va=(left&bit)>0;vb=(right&bit)>0
    else:k=int(feature[-1]);va=bitcount[left]>=k;vb=bitcount[right]>=k
    vals={'points_from':int(va.sum()),'points_to':int(vb.sum()),'witness_lost':int((va&~vb).sum()),'witness_gained':int((~va&vb).sum()),'witness_retained':int((va&vb).sum()),'unobserved_both':int((~va&~vb).sum())};ar=functions[functions.from_year.eq(year-1)&functions.to_year.eq(year)&functions.feature.eq(feature)].iloc[0]
    for k,v in vals.items():ck(f'cohort_function_{year-1}_{year}_{feature}_{k}',v==ar[k])
    frows.append(dict(from_year=year-1,to_year=year,feature=feature,**vals))
   del joined,left,right
  previous=current;print('Independent compact INN cohort through',year,flush=True)
 pd.DataFrame(rows).to_csv(O/'independent_adjacent_INN_partitions.csv',index=False);pd.DataFrame(frows).to_csv(O/'independent_adjacent_same_point_function_transitions.csv',index=False)
 result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','n_checks':len(checks),'checks':checks,'source_selected_file_SHA256':sources,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'interpretation':'Matched/missing INN in annual panels and exact registration-code changes. No physical service birth, closure, enterprise relocation, employment or functional capture inferred.'};(O/'INN_COHORT_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

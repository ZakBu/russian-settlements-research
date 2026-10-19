#!/usr/bin/env python3
"""Independent set reconstruction of fixed source boundaries and census zeros."""
from pathlib import Path
import json,hashlib
import pandas as pd
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet').set_index('id')
 m=pd.read_csv(R/'model/results/documented_external_memberships.csv')
 a=pd.read_csv(R/'model/results/fixed_source_catchment_demography.csv')
 checks=[];rows=[]
 for keys,d in m.groupby(['source_id','destination_uid','function_group'],sort=True):
  orig=sorted(set(d.origin_uid));z=p.loc[orig];src,dst,fun=keys
  author=a[a.source_id.eq(src)&a.destination_uid.eq(dst)&a.function_group.eq(fun)]
  checks.append({'name':'one_row_'+'|'.join(keys),'pass':len(author)==1});au=author.iloc[0]
  r=dict(source_id=src,destination_uid=dst,function_group=fun,n_origins=len(orig))
  checks.append({'name':'origin_count_'+'|'.join(keys),'pass':len(orig)==au.n_origins})
  for y in [2002,2010,2021]:
   v=z[f'population_{y}'];r[f'population_{y}']=float(v.sum(min_count=1));r[f'zeros_{y}']=int(v.eq(0).sum());r[f'missing_{y}']=int(v.isna().sum())
   checks.extend([{'name':f'{kind}_{y}_'+'|'.join(keys),'pass':val==au[col]} for kind,val,col in [('sum',r[f'population_{y}'],f'population_{y}'),('zeros',r[f'zeros_{y}'],f'n_zero_population_{y}'),('missing',r[f'missing_{y}'],f'n_missing_population_{y}')]])
  checks.append({'name':'no_backcast_'+'|'.join(keys),'pass':not au.service_historical_presence_asserted})
  rows.append(r)
 # Verify Konakovo positively named point groups without interpreting source
 # name changes as opening/closure. Preserve unmatched origins separately.
 hpath=R/'history/konakovo_edges_by_year.csv'
 if hpath.exists():
  h=pd.read_csv(hpath);out=[]
  for origin,z in h.groupby('origin_name'):
   if set(z.year)!={2021,2026}:continue
   aa=z[z.year.eq(2021)];bb=z[z.year.eq(2026)]
   out.append(dict(origin=origin,n_before=len(aa),n_after=len(bb),provider_before='|'.join(sorted(set(aa.provider_settlement))),provider_after='|'.join(sorted(set(bb.provider_settlement))),same_place=set(aa.provider_settlement)==set(bb.provider_settlement)))
  pd.DataFrame(out).to_csv(O/'independent_konakovo_places.csv',index=False)
 pd.DataFrame(rows).to_csv(O/'independent_fixed_catchment_demography.csv',index=False)
 audit={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'n_checks':len(checks),'membership_rows':len(m),'membership_unique_quads':len(m.drop_duplicates()),'source_boundaries':len(rows),'source_sha256':{str(f.relative_to(B)):sha(f) for f in [R/'model/results/documented_external_memberships.csv',R/'model/results/fixed_source_catchment_demography.csv']},'interpretation':'Demography inside fixed documentary sets; census years do not backdate function existence. Missing evidence is not proof of no function.'}
 (O/'GRAPH_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=lambda x:x.item())+'\n')
 print(audit['status'],len(checks),flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()

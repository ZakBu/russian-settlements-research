"""Descriptive robustness, fixed primary matching graph; no re-selection of pairs."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd

def main(a):
 out=Path(a.output);out.mkdir(exist_ok=True,parents=True)
 raw=pd.read_csv(a.input,usecols=['entity_uid','population_2002','population_2021','settlement_name_2002','settlement_name_2021','population_value_quality_2002','population_value_quality_2021'])
 pts=pd.read_csv(a.points,usecols=['entity_uid','region','grid25','grid50','grid100','grid50shift25'])
 d=raw.merge(pts,on='entity_uid',validate='one_to_one');rows=[]
 for kind in ['region','grid25','grid50','grid100','grid50shift25']:
  for unit,g in d.groupby(kind):
   g=g.sort_values(['population_2002','entity_uid'],ascending=[False,True]);n=len(g);k=int(np.ceil(n*.1));p=g[['population_2002','population_2021']].to_numpy(float);s=p.sum(axis=0);t=p[:k].sum(axis=0)
   r={'kind':kind,'unit':str(unit),'n':n,'largest_uid':g.entity_uid.iloc[0],'largest_name2002':g.settlement_name_2002.iloc[0],'largest_population2002':p[0,0],'largest_population2021':p[0,1],'original_top10_count':k}
   r['delta_primary_pp']=100*(t[1]/s[1]-t[0]/s[0]) if min(s)>0 else np.nan
   ss=s-p[0];tt=t-p[0];r['delta_without_largest_pp']=100*(tt[1]/ss[1]-tt[0]/ss[0]) if min(ss)>0 else np.nan
   # No new top group is chosen after removing the largest member.
   for yr in [2002,2021]:
    vc=g['population_value_quality_'+str(yr)].fillna('UNKNOWN').value_counts();r['dominant_quality'+str(yr)]=vc.index[0];r['dominant_quality_fraction'+str(yr)]=vc.iloc[0]/n
   rows.append(r)
 u=pd.DataFrame(rows);u.to_csv(out/'largest_node_influence.csv',index=False)
 use=['kind','a','b','similar_loss','concentration_gap_pp','rms_difference','max_abs_difference','a_dominant_region','b_dominant_region']
 pairs=pd.read_csv(a.pairs,usecols=use);p=pairs[pairs.similar_loss].copy()
 u=u[['kind','unit','delta_without_largest_pp']]
 p=p.merge(u.rename(columns={'unit':'a','delta_without_largest_pp':'a_exlargest'}),on=['kind','a'],validate='many_to_one').merge(u.rename(columns={'unit':'b','delta_without_largest_pp':'b_exlargest'}),on=['kind','b'],validate='many_to_one')
 p['exlargest_gap_pp']=abs(p.a_exlargest-p.b_exlargest)
 rr=[]
 for kind,g in p.groupby('kind'):
  for metric in ['concentration_gap_pp','exlargest_gap_pp']:
   rr.append({'kind':kind,'variant':metric,'n_pairs':len(g),'n_unique_units':len(set(g.a)|set(g.b)),'q10':g[metric].quantile(.1),'median':g[metric].median(),'q90':g[metric].quantile(.9)})
 pd.DataFrame(rr).to_csv(out/'c1_sensitivity_summary.csv',index=False)
 loo=[]
 for kind in ['region','grid50']:
  g=p[p.kind==kind]
  for region in sorted(set(g.a_dominant_region)|set(g.b_dominant_region)):
   h=g[(g.a_dominant_region!=region)&(g.b_dominant_region!=region)]
   loo.append({'kind':kind,'excluded_dominant_region':region,'n_pairs':len(h),'median_gap_pp':h.concentration_gap_pp.median(),'p90_gap_pp':h.concentration_gap_pp.quantile(.9)})
 pd.DataFrame(loo).to_csv(out/'c1_leave_region_out.csv',index=False)
 small=pairs[['kind','a','b','rms_difference','max_abs_difference']];small.to_csv(out/'comparison_registry_compact.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 # Whole graph is reconstructible from compact keys + territory passports, including all outcomes.
 receipt={'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'inputs':{v:hashlib.sha256(Path(getattr(a,v)).read_bytes()).hexdigest() for v in ['input','points','pairs']},'outputs':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()},'n_complete_pairs':len(pairs),'fixed_membership_after_largest_removal':True,'no_ci_no_p':True}
 (out/'c1_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(rr,ensure_ascii=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser()
 for x in ['input','points','pairs','output']:ap.add_argument('--'+x,required=True)
 main(ap.parse_args())

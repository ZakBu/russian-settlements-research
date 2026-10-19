"""Descriptive RFSD sector specialization, not employment or demonstrated centre functions.
Primary: organization count share>=.20, LQ>=1.25, N_zone>=5; no tuning to population outcomes.
Sensitivity: revenue weights, strict house/nonimputed, 1/5/10km address thresholds.
"""
import argparse,pathlib,json,os,hashlib
import pandas as pd,numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--projection',type=pathlib.Path,required=True);ap.add_argument('--out',type=pathlib.Path);a=ap.parse_args();O=a.out or a.projection/'functional';O.mkdir(parents=True,exist_ok=True);m=json.loads((a.projection/'FINISHED.json').read_text());assert all(hashlib.sha256((a.projection/x['name']).read_bytes()).hexdigest()==x['sha256'] for x in m['outputs'])
f=pd.read_parquet(a.projection/'financial_observations.parquet');s=pd.read_parquet(a.projection/'sector_sensitivity.parquet');GROUP=['year','max_distance_km','quality'];KEY=['center_id']+GROUP
assert not f.duplicated(KEY).any();checks=[]
def ck(n,v):assert v,n;checks.append(dict(check=n,passed=True))
ss=s.groupby(KEY).agg(n_organizations=('n_organizations','sum'),revenue_thousand_rub_nominal=('revenue_thousand_rub_nominal','sum')).reset_index();j=f.merge(ss,on=KEY,validate='one_to_one',how='outer',suffixes=('_f','_s'),indicator=True);ck('exact group conservation',j['_merge'].eq('both').all());ck('each unit count conserved',j.n_organizations_f.eq(j.n_organizations_s).all());ck('each unit revenue conserved',np.allclose(j.revenue_thousand_rub_nominal_f,j.revenue_thousand_rub_nominal_s,rtol=1e-11,atol=1e-4))
profiles=[];types=[]
for basis,col in [('count','n_organizations'),('revenue','revenue_thousand_rub_nominal')]:
 z=s.copy();zone=z.groupby(KEY)[col].sum().rename('zone_weight').reset_index();national=z.groupby(GROUP+['okved_section'])[col].sum().rename('national_sector_weight').reset_index();nat=z.groupby(GROUP)[col].sum().rename('national_total_weight').reset_index();z=z.merge(zone,on=KEY,validate='many_to_one').merge(national,on=GROUP+['okved_section'],validate='many_to_one').merge(nat,on=GROUP,validate='many_to_one');z=z.merge(f[KEY+['n_organizations']],on=KEY,validate='many_to_one',suffixes=('','_zone'));z['share']=z[col]/z.zone_weight.replace(0,np.nan);z['national_share']=z.national_sector_weight/z.national_total_weight.replace(0,np.nan);z['location_quotient']=z.share/z.national_share.replace(0,np.nan);z['basis']=basis;z['qualifies']=(z.n_organizations_zone>=5)&z.share.ge(.2)&z.location_quotient.ge(1.25)&~z.okved_section.isin(['UNKNOWN','missing','nan']);z['qualifies_sector_min5_sensitivity']=z.qualifies&z.n_organizations.ge(5);profiles.append(z)
 for key,g in z.groupby(KEY):
  selected=g[g.qualifies].sort_values(['share','location_quotient','okved_section'],ascending=[False,False,True]);N=int(g.n_organizations_zone.iloc[0]);special='|'.join(selected.okved_section);category='insufficient_reporters' if N<5 else ('no_qualifying_specialization' if selected.empty else selected.okved_section.iloc[0]);row=dict(zip(KEY,key));row.update(basis=basis,N_zone=N,dominant_specialization=category,qualifying_sectors=special,n_qualifying_sectors=len(selected),top_share=float(selected.share.iloc[0]) if len(selected) else np.nan,top_LQ=float(selected.location_quotient.iloc[0]) if len(selected) else np.nan);types.append(row)
def atomic(d,name,kind):
 dest=O/name;tmp=O/(name+'.tmp')
 if kind=='parquet':d.to_parquet(tmp,index=False);back=pd.read_parquet(tmp)
 else:d.to_csv(tmp,index=False,compression='gzip' if kind=='gzip' else None);back=pd.read_csv(tmp,compression='gzip' if kind=='gzip' else None)
 assert back.shape==d.shape and list(back.columns)==list(d.columns)
 os.replace(tmp,dest)
profiles=pd.concat(profiles,ignore_index=True);types=pd.DataFrame(types);atomic(profiles,'sector_profiles.parquet','parquet');atomic(profiles,'sector_profiles.csv.gz','gzip');atomic(types,'functional_types.csv','csv');atomic(types,'functional_types.parquet','parquet')
comparisons=[]
base=types[(types.quality=='baseline')&(types.max_distance_km==5)&(types.basis=='count')]
for (q,d,b),g in types.groupby(['quality','max_distance_km','basis']):
 p=base.merge(g,on=['center_id','year'],suffixes=('_primary','_alternative'),validate='one_to_one');eligible=p[(p.N_zone_primary>=5)&(p.N_zone_alternative>=5)];comparisons.append(dict(quality=q,max_distance_km=int(d),basis=b,n_common_units=len(p),n_common_N_ge5=len(eligible),dominant_agreement=float(eligible.dominant_specialization_primary.eq(eligible.dominant_specialization_alternative).mean()),all_specializations_agreement=float(eligible.qualifying_sectors_primary.eq(eligible.qualifying_sectors_alternative).mean())))
atomic(pd.DataFrame(comparisons),'classification_sensitivity.csv','csv');(O/'definition.json').write_text(json.dumps(dict(primary=dict(basis='organization count',share_min=.20,LQ_min=1.25,N_zone_min=5,address_max_distance_km=5,quality='baseline'),sensitivity=dict(bases=['count','revenue'],distance_km=[1,5,10],quality=['baseline','strict house/nonimputed']),unknown='UNKNOWN included in denominators but not assigned as a specialization',units='thousand nominal rubles; no deflation',not_measured=['employment','production place','commuting','service flows'],commercial_coverage='Financial/state/religious/budget noneligible or nonfiling organizations underrepresented; no-service conclusions prohibited'),indent=2));(O/'verification.json').write_text(json.dumps(dict(passed=True,checks=checks,n_profiles=len(profiles),n_types=len(types)),indent=2));print('PASS',len(profiles),'profiles',len(types),'types',flush=True)

finished=dict(input_model_sha256=m['model_sha256'],outputs=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(O.glob('*')) if p.is_file() and not p.name.endswith('.tmp') and p.name!='FINISHED.json']);tmp=O/'FINISHED.json.tmp';tmp.write_text(json.dumps(finished,indent=2));os.replace(tmp,O/'FINISHED.json')

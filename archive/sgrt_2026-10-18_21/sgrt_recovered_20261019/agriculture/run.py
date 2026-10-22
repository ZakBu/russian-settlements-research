"""CLI: official municipal crop structure; ecological SGRT matrix crosswalk."""
import argparse,json,hashlib
from pathlib import Path
import pandas as pd,numpy as np,pyarrow.parquet as pq
P=argparse.ArgumentParser();P.add_argument('--source',required=True);P.add_argument('--panel',required=True);P.add_argument('--membership',required=True);P.add_argument('--out',default=str(Path(__file__).parent));a=P.parse_args();O=Path(a.out);O.mkdir(parents=True,exist_ok=True)
# Exact names; overlapping children never added to a parent aggregate.
N={'total':['Вся посевная площадь','Посевная площадь сельскохозяйственных культур — всего','Сельскохозяйственные культуры — всего'], 'grain':['Зерновые и зернобобовые культуры — всего'],'technical':['Технические культуры — всего'],'potato':['Картофель'],'vegetables':['Овощи — всего','Овощи (без высадков)'],'fodder':['Кормовые культуры — всего'],'melon':['Бахчевые продовольственные культуры']}
lookup={v:k for k,vs in N.items() for v in vs};pieces=[];names=set();f=pq.ParquetFile(a.source)
if (O/'municipal_series_2006_2024.parquet').exists() and (O/'schema.json').exists() and json.loads((O/'schema.json').read_text()).get('extractor_version')=='crop-v2-strip-six-observed-20261019':
 assert hashlib.sha256(Path(a.source).read_bytes()).hexdigest()=='e6ca2906f49fd0fe561ae98f535206990cebc2675884571bced546c3374c198d'
 r=pd.read_parquet(O/'municipal_series_2006_2024.parquet')
else:
 for b in f.iter_batches(batch_size=50000):
  d=b.to_pandas();d['kultur_raw']=d.kultur;d['kultur']=d.kultur.str.strip();d=d[d.mun_level.eq('Муниципальное образование верхнего уровня')&d.kategor.eq('Хозяйства всех категорий')&d.indicator_code.isin(['Y48007010','Y48007018'])].copy()
  names.update(d.kultur.unique())
  keep=d.indicator_code.eq('Y48007010')|d.kultur.isin(lookup)
  if keep.any():pieces.append(d[keep])
 r=pd.concat(pieces,ignore_index=True);r['group']=np.where(r.indicator_code.eq('Y48007010'),'production',r.kultur.map(lookup));r.to_parquet(O/'municipal_series_2006_2024.parquet',index=False);r.to_csv(O/'municipal_series_2006_2024.csv.gz',index=False)
 (O/'schema.json').write_text(json.dumps({'extractor_version':'crop-v2-strip-six-observed-20261019','schema':str(f.schema_arrow),'source_rows':f.metadata.num_rows,'selected_rows':len(r),'selected_culture_names':sorted(str(v) for v in names),'groups':N},ensure_ascii=False,indent=2))
r['nonmissing']=r.indicator_value.notna();r.groupby(['year','indicator_code','group','indicator_unit'],dropna=False).agg(rows=('oktmo','size'),municipalities=('oktmo','nunique'),nonmissing=('nonmissing','sum')).reset_index().to_csv(O/'series_coverage.csv',index=False)
key=['oktmo','year','group'];dup=r.duplicated(key,False);r[dup].to_csv(O/'duplicates_quarantined.csv.gz',index=False);clean=r[~dup].copy();c=clean[clean.year.eq(2021)&clean.group.ne('production')].pivot(index='oktmo',columns='group',values='indicator_value').reset_index()
for k in N:
 if k not in c:c[k]=np.nan
known=list(N)[1:];c['sum6']=c[known].sum(axis=1,min_count=6);c['other_residual']=c.total-c.sum6;c['tolerance_ha']=np.maximum(1e-8,c.total.abs()*.02)
c['known_sum_partial']=c[known].sum(axis=1,min_count=1);c['inconsistent']=c.total.lt(0)|c[known].lt(0).any(axis=1)|(c.known_sum_partial.gt(c.total+c.tolerance_ha))|(c.total.eq(0)&c[known].gt(0).any(axis=1))
# Only explicit total zero with no positive partial values permits zero profile.
zero=c.total.eq(0)&~c[known].gt(0).any(axis=1);c.loc[zero,known+['other_residual']]=0
c['complete']=c[['total']+known+['other_residual']].notna().all(axis=1)&~c.inconsistent
c.loc[c.complete&c.other_residual.lt(0),'other_residual']=0
c[c.inconsistent].to_csv(O/'inconsistent_totals_quarantined.csv',index=False);c.to_csv(O/'municipal_crop_profiles_2021.csv',index=False)
meta=clean[clean.year.eq(2021)&clean.group.eq('total')][['oktmo','municipality','oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to','year','indicator_unit']];c=c.merge(meta,on='oktmo',how='left',validate='one_to_one')
pan=pd.read_parquet(a.panel);mem=pd.read_parquet(a.membership) if a.membership.endswith('.parquet') else pd.read_csv(a.membership)
if 'center_id' not in mem:raise ValueError('membership must have id,center_id')
x=mem[['id','center_id']].merge(pan[['id','municipality_oktmo8_2021','population_2010','population_2021','municipality_context_status','municipality_source_row_ambiguous']],on='id',how='left',validate='one_to_one');x=x.rename(columns={'municipality_oktmo8_2021':'oktmo'});x['oktmo']=x.oktmo.astype('string')
# The 2021 bridge is NOT a historical municipality reconstruction.
x[['id','center_id','oktmo','municipality_context_status','municipality_source_row_ambiguous']].to_parquet(O/'settlement_municipality_zone.parquet',index=False)
z=x.dropna(subset=['oktmo','center_id']);w=z.groupby(['oktmo','center_id']).agg(n=('id','size'),population2010=('population_2010','sum'),population2021=('population_2021','sum')).reset_index();w['weight_count']=w.n/w.groupby('oktmo').n.transform('sum')
for y in [2010,2021]:
 den=w.groupby('oktmo')['population'+str(y)].transform('sum');w['weight_population'+str(y)]=np.where(den>0,w['population'+str(y)]/den,w.weight_count)
for scheme in ['count','population2010','population2021']:assert np.allclose(w.groupby('oktmo')['weight_'+scheme].sum(),1)
w.to_csv(O/'municipality_zone_matrix.csv.gz',index=False);wa=w.groupby('oktmo').agg(zones=('center_id','nunique'),settlements=('n','sum'),largest_population2021_share=('weight_population2021','max')).reset_index();wa.to_csv(O/'crosswalk_audit.csv',index=False)
allzones=x.groupby('center_id').size().rename('zone_settlements').reset_index();allresult=[];balances=[];groups=known+['other_residual'];profile_ok=c[c.complete]
for scheme in ['population2021','population2010','count']:
 j=w.merge(profile_ok,on='oktmo',how='inner',validate='many_to_one');weight='weight_'+scheme
 for g in ['total']+groups:j['allocated_'+g]=j[g]*j[weight]
 agg=j.groupby('center_id')[['allocated_'+g for g in ['total']+groups]].sum().reset_index();covered=z[z.oktmo.isin(profile_ok.oktmo)].groupby('center_id').size().rename('covered_settlements').reset_index();out=allzones.merge(covered,on='center_id',how='left').merge(agg,on='center_id',how='left');out['covered_settlements']=out.covered_settlements.fillna(0);out['coverage']=out.covered_settlements/out.zone_settlements;out['scheme']=scheme
 arr=out[['allocated_'+g for g in groups]].to_numpy();den=out.allocated_total.to_numpy();shares=np.divide(arr,den[:,None],out=np.zeros_like(arr),where=den[:,None]>0);out['dominant_group']=[groups[i] for i in np.argmax(shares,axis=1)];out['dominance']=np.max(shares,axis=1)
 for cv in [.6,.7,.8,.9,1.0]:
  for dv in [.5,.6,.7]:
   o=out.copy();o['coverage_threshold']=cv;o['dominance_threshold']=dv;o['functional_context']=np.select([o.coverage.lt(cv)|o.allocated_total.isna(),o.allocated_total.eq(0),o.dominance.ge(dv)],['missing','zero_sown',o.dominant_group],default='mosaic');allresult.append(o)
 for g in ['total']+groups:
  src=j[['oktmo',g]].drop_duplicates();before=src[g].sum();after=j['allocated_'+g].sum();assert np.isclose(before,after);balances.append(dict(scheme=scheme,group=g,source_sum=before,allocated_sum=after,abs_error=abs(before-after)))
res=pd.concat(allresult,ignore_index=True);res.to_parquet(O/'zone_crop_context.parquet',index=False);pd.DataFrame(balances).to_csv(O/'mass_balance.csv',index=False)
main=res[res.scheme.eq('population2021')&res.coverage_threshold.eq(.8)&res.dominance_threshold.eq(.6)];main.to_csv(O/'zone_crop_profile_main.csv',index=False)
res.groupby(['scheme','coverage_threshold','dominance_threshold','functional_context']).size().rename('zones').reset_index().to_csv(O/'threshold_sensitivity.csv',index=False)
# Pairwise scheme agreement at fixed declared thresholds, unknowns separately retained.
ss=res[res.coverage_threshold.eq(.8)&res.dominance_threshold.eq(.6)].pivot(index='center_id',columns='scheme',values='functional_context');ss['agreement_population2021_vs_count']=ss.population2021.eq(ss['count']);ss.to_csv(O/'weight_sensitivity.csv')
pins=[Path(a.source),Path(a.panel),Path(a.membership)];audit={'source_version':'20250918','observation_year':2021,'bridge_year':2021,'source_rows':f.metadata.num_rows,'series_rows':len(r),'municipal_profiles':len(c),'complete_profiles':int(c.complete.sum()),'inconsistent_profiles':int(c.inconsistent.sum()),'duplicate_rows':int(dup.sum()),'municipalities_crosswalk':len(wa),'municipalities_split':int(wa.zones.gt(1).sum()),'legacy_allocation_diagnostic_classes':main.functional_context.value_counts().to_dict(),'scheme_agreement_population2021_count':float(ss.agreement_population2021_vs_count.mean()),'mass_checks':len(balances),'inputs':[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in pins]};(O/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))

# SCIENTIFIC PRIMARY: municipal type composition, no hectare allocation interpretation.
vals=c[known].fillna(0).to_numpy();tot=c.total.to_numpy();sh=np.divide(vals,tot[:,None],out=np.zeros_like(vals),where=tot[:,None]>0);c['municipal_dominance']=sh.max(axis=1);c['municipal_dominant_group']=[known[i] for i in sh.argmax(axis=1)];c['sum_known_share']=np.divide(vals.sum(axis=1),tot,out=np.zeros(len(c)),where=tot>0)
c['municipal_profile']=np.select([c.inconsistent|c.total.isna(),c.total.eq(0),c.municipal_dominance.ge(.5),c[known].notna().all(axis=1)&c.sum_known_share.ge(.9)],['missing','zero_sown',c.municipal_dominant_group,'mixed'],default='missing');c.to_csv(O/'municipal_crop_profiles_2021.csv',index=False)
cl=c[c.municipal_profile.ne('missing')][['oktmo','municipal_profile']];zx=z.merge(cl,on='oktmo',how='left',validate='many_to_one');zx['valid']=zx.municipal_profile.notna();rows=[];cats=known+['mixed','zero_sown'];compositions=[]
for scheme in ['count','population2010','population2021']:
 zx['vote_weight']=1. if scheme=='count' else zx[scheme.replace('population','population_')].astype(float)
 zonepop=zx.groupby('center_id').vote_weight.transform('sum');zx.loc[zonepop.eq(0),'vote_weight']=1.
 votes=zx[zx.valid].groupby(['center_id','municipal_profile']).vote_weight.sum().unstack(fill_value=0).reindex(columns=cats,fill_value=0)
 totals=zx.groupby('center_id').vote_weight.sum();covered_n=zx.groupby('center_id').valid.sum();all_n=x.groupby('center_id').size();cs=votes.div(votes.sum(axis=1),axis=0);zs=all_n.to_frame('zone_settlements').join(covered_n.rename('covered_settlements')).join(cs.add_prefix('share_')).fillna({'covered_settlements':0});zs['coverage']=zs.covered_settlements/zs.zone_settlements
 for k in cats:
  if 'share_'+k not in zs:zs['share_'+k]=0
 zs['dominance']=zs[['share_'+k for k in cats]].max(axis=1);zs['dominant_profile']=zs[['share_'+k for k in cats]].fillna(0).idxmax(axis=1).str.replace('share_','',regex=False);zs['scheme']=scheme;zs=zs.reset_index();zs['membership_status']=np.where(zs.center_id.eq('UNASSIGNED'),'unassigned','calculated');zs.loc[zs.center_id.eq('UNASSIGNED'),['coverage','covered_settlements']]=0;zs.loc[zs.center_id.eq('UNASSIGNED'),['dominance']+['share_'+k for k in cats]]=np.nan;zs.loc[zs.dominance.isna()|zs.coverage.eq(0),'dominant_profile']='unobserved';compositions.append(zs)
 for cv in [.6,.7,.8,.9,1.0]:
  for dv in [.5,.6,.7]:
   oo=zs.copy();oo['coverage_threshold']=cv;oo['dominance_threshold']=dv;oo['functional_context']=np.select([oo.coverage.lt(cv)|oo.dominance.isna(),oo.dominance.ge(dv)],['missing',oo.dominant_profile],default='mosaic');rows.append(oo)
ft=pd.concat(rows,ignore_index=True);ft.to_parquet(O/'zone_functional_composition.parquet',index=False);fm=ft[ft.scheme.eq('count')&ft.coverage_threshold.eq(.8)&ft.dominance_threshold.eq(.6)];fm.to_csv(O/'zone_functional_main.csv',index=False);ft.groupby(['scheme','coverage_threshold','dominance_threshold','functional_context']).size().rename('zones').reset_index().to_csv(O/'functional_threshold_sensitivity.csv',index=False)
fwide=ft[ft.coverage_threshold.eq(.8)&ft.dominance_threshold.eq(.6)].pivot(index='center_id',columns='scheme',values='functional_context');fwide.to_csv(O/'functional_weight_sensitivity.csv');audit['main_interpretation']='share of settlement points whose 2021 municipality has crop profile; NOT share of crops';audit['functional_main_classes']=fm.functional_context.value_counts().to_dict();audit['municipal_class_counts']=c.municipal_profile.value_counts().to_dict();audit['functional_count_population2010_agreement']=float(fwide['count'].eq(fwide.population2010).mean());audit['functional_count_population2021_agreement']=float(fwide['count'].eq(fwide.population2021).mean());(O/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print('FUNCTIONAL',json.dumps(audit,ensure_ascii=False))

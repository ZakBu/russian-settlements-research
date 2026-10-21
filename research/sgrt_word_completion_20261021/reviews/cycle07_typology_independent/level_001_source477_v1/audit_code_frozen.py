"""Independent vectorized actual state/rate/label/confidence replay. No producer imports."""
from pathlib import Path
import argparse,json,hashlib,time
import numpy as np,pandas as pd
LABELS={'growth':'рост','stable':'стабильность','decline':'убыль','extinction_observed':'наблюдаемое обнуление','emergence_observed':'рост из наблюдаемого нуля','observed_zero_both':'оба наблюдения нулевые','unavailable':'динамика недоступна','not_applicable':'не применимо'}
NAMES={'atomic_settlement':'отдельное поселение','rural_zone':'система с сельским окружением','local_without_rural_zone':'локальная система без сельского окружения','rural_composition_unknown':'система с неустановленным составом окружения','external_context':'неаддитивный внешний контекст','superregional_overlay':'надрегиональное перекрывающееся объединение','protected_carry':'защищённая переносимая строка'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',required=True);ap.add_argument('--classified',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();h=Path(a.output);assert not h.exists();h.mkdir(parents=True);cp=Path(a.contract);c=json.loads(cp.read_text());p=Path(a.classified);watched={str(cp):sha(cp),str(Path(c['units_path'])):sha(c['units_path']),str(p/'complete_typology.parquet'):sha(p/'complete_typology.parquet'),str(p/'trajectory_evidence.parquet'):sha(p/'trajectory_evidence.parquet'),str(p/'receipt.json'):sha(p/'receipt.json')};assert watched[c['units_path']]==c['units_sha256'];u=pd.read_parquet(c['units_path']).set_index('unit_id',drop=False);ty=pd.read_parquet(p/'complete_typology.parquet').set_index('unit_id',drop=False).loc[u.index];ev=pd.read_parquet(p/'trajectory_evidence.parquet');checks=[];bad=[]
 def ck(k,b,d=None):checks.append({'check':k,'passed':bool(b),'detail':d})
 ck('all_unique_exact_output_units',ty.index.is_unique and u.index.is_unique and set(ty.index)==set(u.index));ck('primary_threshold',c['primary_annual_delta']==.0025)
 idx=u.index;atomic=u.kind.eq('atomic_settlement');nr=u[c['rural_member_count_column']];nu=u[c['unknown_role_member_count_column']];structure=pd.Series(np.select([u.unit_role.eq('protected_carry'),atomic,u.kind.eq('external_context_anchor'),u.kind.eq('superregional_overlay'),nr.isna()|nu.isna()|nu.ne(0),nr.gt(0)],['protected_carry','atomic_settlement','external_context','superregional_overlay','rural_composition_unknown','rural_zone'],default='local_without_rural_zone'),index=idx)
 # Current primary contract admits exactly one focal; multicenter alternatives never substituted.
 central=u[c['central_object_ids_column']].map(json.loads);ck('everycentral_exact_onefocal',all(len(v)==1 and v==[str(core)] for v,core in zip(central,u.core_id)))
 def states(obj,a,b,delta):
  sp=c['objects'][obj];av=pd.to_numeric(u[sp['population'][str(a)]],errors='coerce');bv=pd.to_numeric(u[sp['population'][str(b)]],errors='coerce');ca=u[sp['complete'][str(a)]].eq(True);cb=u[sp['complete'][str(b)]].eq(True);active=atomic if obj=='own' else ~atomic;app=pd.Series(True,index=idx,dtype='boolean')
  if obj=='rural':app=~structure.str.endswith('local_without_rural_zone');ca=ca&nu.eq(0);cb=cb&nu.eq(0)
  if sp.get('applicable_column'):app=app.astype('boolean')&u[sp['applicable_column']].astype('boolean')
  observed=ca&cb&av.notna()&bv.notna()&np.isfinite(av)&np.isfinite(bv)&av.ge(0)&bv.ge(0)&app.eq(True)
  st=pd.Series('unavailable',index=idx);st.loc[app.eq(False)]='not_applicable';rate=pd.Series(np.nan,index=idx)
  with np.errstate(divide='ignore',invalid='ignore'):
   r=np.expm1(np.log(bv/av)/(b-a))
  both=observed&av.gt(0)&bv.gt(0);rate.loc[both]=r[both];tie=np.isclose(abs(r),delta,rtol=1e-10,atol=1e-14);st.loc[both]='stable';st.loc[both&(r>delta)&~tie]='growth';st.loc[both&(r< -delta)&~tie]='decline';st.loc[observed&av.eq(0)&bv.eq(0)]='observed_zero_both';st.loc[observed&av.eq(0)&bv.gt(0)]='emergence_observed';st.loc[observed&av.gt(0)&bv.eq(0)]='extinction_observed';rate.loc[observed&av.gt(0)&bv.eq(0)]=-1.
  return st,rate,app,ca,cb,active,av,bv
 periods=[(2002,2010),(2010,2021),(2002,2021)];cache={};expected=[]
 for obj in ['own','center','rural','system']:
  for aa,bb in periods:
   st,rt,app,ca,cb,active,av,bv=states(obj,aa,bb,.0025);cache[(obj,aa,bb)]=(st,rt,app);z=pd.DataFrame({'unit_id':idx,'object':obj,'period':f'{aa}-{bb}','start_year':aa,'end_year':bb,'start_population_raw':av.to_numpy(),'end_population_raw':bv.to_numpy(),'start_complete':ca.to_numpy(),'end_complete':cb.to_numpy(),'applicable':app.to_numpy(),'annual_rate':rt.to_numpy(),'state':st.to_numpy(),'delta':.0025,'population_source_columns':json.dumps([c['objects'][obj]['population'][str(aa)],c['objects'][obj]['population'][str(bb)]])});expected.append(z.loc[active.to_numpy()])
 expected=pd.concat(expected,ignore_index=True);keys=['unit_id','object','period'];ck('every_evidence_key_exact',not ev.duplicated(keys).any() and set(map(tuple,ev[keys].values))==set(map(tuple,expected[keys].values)));ev=ev.set_index(keys).sort_index();expected=expected.set_index(keys).loc[ev.index]
 for col in expected:
  x=ev[col];y=expected[col]
  if col in ['annual_rate','start_population_raw','end_population_raw','delta']:
   ok=np.isclose(pd.to_numeric(x).to_numpy(dtype=float,na_value=np.nan),pd.to_numeric(y).to_numpy(dtype=float,na_value=np.nan),rtol=1e-10,atol=1e-12,equal_nan=True)
  else:ok=(x.eq(y)|(x.isna()&y.isna())).fillna(False).to_numpy()
  ck('every_evidence_'+col,np.all(ok),{'rows':len(expected),'mismatches':int((~ok).sum())})
 recent={o:cache[(o,2010,2021)][0] for o in ['own','center','rural','system']};altcache={d:{o:states(o,2010,2021,d)[0] for o in recent} for d in [0.,.005]};nobs={};napp={};nsup={};expectedrows=[]
 # Scalar serialization only after independent vectorized source rates/states; formula functions never imported.
 qdata=u[c['quality_columns']].to_dict('index');contextlists={k:[] for k in idx}
 for w in c.get('context_witnesses',[]):
  v=u[w['column']];positive=v.eq(True).fillna(False) if w['kind']=='boolean' else pd.to_numeric(v,errors='coerce').gt(0)
  for k in idx[positive]:contextlists[k].append(w['label'])
 adverse={k:[] for k in idx}
 for w in c.get('quality_uncertainty_rules',[]):
  v=u[w['column']];flag=~v.eq(True).fillna(False) if w['rule']=='not_true' else pd.to_numeric(v,errors='coerce').isna()|pd.to_numeric(v,errors='coerce').gt(0)
  for k in idx[flag]:adverse[k].append(w['label'])
 def ktype(s,ss):return 'T:'+s+'|'+','.join(o+'='+v for o,v in ss.items())
 for k,isatom in zip(idx,atomic):
  active=['own'] if isatom else ['center','rural','system'];ss={o:recent[o].loc[k] for o in active};struct=structure.loc[k];pk=ktype(struct,ss);obs=sum(st not in ['unavailable','not_applicable'] for st in ss.values());apps=sum(cache[(o,2010,2021)][2].loc[k] is not False and cache[(o,2010,2021)][2].loc[k]!=False for o in active);support=sum(cache[(o,aa,bb)][0].loc[k] not in ['unavailable','not_applicable'] for o in active for aa,bb in periods);context='|'.join(sorted(set(contextlists[k]))) if contextlists[k] else 'no_positive_witness_in_available_sources';alternatives={str(d):ktype(struct,{o:altcache[d][o].loc[k] for o in active}) for d in [0.,.005] if ktype(struct,{o:altcache[d][o].loc[k] for o in active})!=pk};q={col:(None if pd.isna(v) else v.item() if hasattr(v,'item') else v) for col,v in qdata[k].items()};conf='structural_only' if obs==0 else 'partial_demographic_support' if obs<apps else 'tentative_source_quality' if adverse[k] else 'source_supported_numeric'
  expectedrows.append({'unit_id':k,'unit_name':str(u.loc[k,c['unit_name_column']]) if c.get('unit_name_column') and pd.notna(u.loc[k,c['unit_name_column']]) else str(k),'level':u.loc[k,c['level_column']],'structural_class':struct,'primary_type_id':pk,'primary_type_name':NAMES[struct]+': '+'; '.join(o+' — '+LABELS[v] for o,v in ss.items()),'trajectory_class':json.dumps(ss,ensure_ascii=False),'trajectory_all_periods':';'.join(f'{o}:{aa}-{bb}={cache[(o,aa,bb)][0].loc[k]}' for o in active for aa,bb in periods),'functional_context':context,'complete_profile_id':pk+'|context='+context,'classification_confidence':conf,'observed_dimension_count':obs,'applicable_dimension_count':apps,'observed_object_period_count':support,'source_quality':json.dumps(q,ensure_ascii=False,default=str),'source_quality_flags':json.dumps(adverse[k],ensure_ascii=False),'alternative_type':json.dumps(alternatives,ensure_ascii=False),'central_object_definition':u.loc[k,c['central_object_definition_column']],'central_object_ids':json.dumps(sorted(central.loc[k])),'unit_role':u.loc[k,c['unit_role_column']],'n_underlying_object_series':obs,'statistical_independence_claimed':False,'historical_boundary_equivalence_claimed':False})
 exp=pd.DataFrame(expectedrows).set_index('unit_id',drop=False).loc[idx];jsoncols={'trajectory_class','source_quality','source_quality_flags','alternative_type','central_object_ids'}
 for col in exp:
  x=ty[col];y=exp[col];ok=x.map(json.loads).eq(y.map(json.loads)) if col in jsoncols else (x.eq(y)|(x.isna()&y.isna())).fillna(False);ck('every_type_field_'+col,ok.all(),{'rows':len(exp),'mismatches':int((~ok).sum())})
  for k in idx[~ok][:3]:bad.append({'unit_id':k,'field':col,'actual':str(x.loc[k]),'expected':str(y.loc[k])})
 ck('all_frozen_inputs_unchanged',all(sha(f)==s for f,s in watched.items()));ok=all(x['passed'] for x in checks);rec={'status':'ACCEPTED_INDEPENDENT_COMPLETE_CLASSIFIER_OUTPUT' if ok else 'REJECTED','all_checks_passed':ok,'n_checks':len(checks),'n_failed':sum(not x['passed'] for x in checks),'checks':checks,'n_units':len(exp),'n_types':int(exp.primary_type_id.nunique()),'n_trajectory_rows':len(expected),'accepted_typology_sha256':sha(p/'complete_typology.parquet') if ok else None,'accepted_trajectory_sha256':sha(p/'trajectory_evidence.parquet') if ok else None,'source_normalized_units_sha256':sha(c['units_path']),'source_input_sha256':watched,'code_sha256':sha(__file__),'unit_role_counts':exp.unit_role.value_counts().to_dict(),'classification_confidence_counts':exp.classification_confidence.value_counts().to_dict(),'seconds':time.monotonic()-START,'scope':'All actual measured labels, exact names/IDs, sourcequality/functional annotations, allperiod states/rates/zeros/applicability and0/.5percent alternative classifications. Does not confirm causal Word mechanism or observed OD.'};(h/'audit.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');pd.DataFrame(bad).to_csv(h/'mismatch_witnesses.csv',index=False);print(json.dumps({k:rec[k] for k in ['status','n_checks','n_failed','n_units','n_types','seconds']},ensure_ascii=False));print(json.dumps([x for x in checks if not x['passed']],ensure_ascii=False))
START=time.monotonic()
if __name__=='__main__':main()

"""Independent vectorized trajectory/type replay; producer modules are never imported."""
import json,hashlib,sys,gc
from pathlib import Path
import numpy as np,pandas as pd
B=Path(__file__).resolve().parents[2];O=Path(__file__).parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def states(a,b,ca,cb,dt,app,delta):
 a=np.asarray(a,float);b=np.asarray(b,float);valid=np.asarray(ca,bool)&np.asarray(cb,bool)&np.isfinite(a)&np.isfinite(b)&(a>=0)&(b>=0);app=np.asarray(app,bool);s=np.full(len(a),'unavailable',dtype=object);rate=np.full(len(a),np.nan);s[~app]='not_applicable';valid&=app
 s[valid&(a==0)&(b==0)]='observed_zero_both';s[valid&(a==0)&(b>0)]='emergence_observed';s[valid&(a>0)&(b==0)]='extinction_observed';rate[valid&(a>0)&(b==0)]=-1
 p=valid&(a>0)&(b>0);rate[p]=np.expm1(np.log(b[p]/a[p])/dt);s[p]='stable';near=np.isclose(abs(rate),delta,rtol=1e-10,atol=1e-14);s[p&(rate>delta)&~near]='growth';s[p&(rate < -delta)&~near]='decline';return s,rate

def run(contract,outpath):
 c=json.loads(contract.read_text());out=Path(outpath);u=pd.read_parquet(c['units_path']).set_index('unit_id',drop=False);t=pd.read_parquet(out/'complete_typology.parquet').set_index('unit_id',drop=False);e=pd.read_parquet(out/'trajectory_evidence.parquet');checks=[];bad=[]
 def ck(k,v):checks.append(k);bad.append(k) if not bool(v) else None
 scope=json.loads((out/'PROFILE_SCOPE.json').read_text());ck('explicit_NOT_PROJECTED_scope',scope['status']=='NOT_PROJECTED_FOR_LIGHTWEIGHT_SENSITIVITY_NOT_ABSENCE' and scope['primary_population_type_comparison_allowed'] is True and scope['full_functional_profile_comparison_allowed'] is False and scope['functional_context_empty_registry_is_not_evidence_of_absence'] is True and scope['classification_receipt_sha256']==sha(out/'receipt.json'));ck('sourcehash',sha(c['units_path'])==c['units_sha256']);ck('allunits',u.index.is_unique and t.index.is_unique and set(u.index)==set(t.index));t=t.reindex(u.index)
 atomic=u.kind.eq('atomic_settlement');struct=pd.Series(np.where(atomic,'atomic_settlement',np.where(u.n_unknown_role_external_settlements.gt(0),'rural_composition_unknown',np.where(u.n_rural_external_settlements.gt(0),'rural_zone','local_without_rural_zone'))),index=u.index);struct[u.kind.eq('external_context_anchor')]='external_context';struct[u.kind.eq('superregional_overlay')]='superregional_overlay';struct[u.unit_role.eq('protected_carry')]='protected_carry';ck('all_structural_classes',t.structural_class.eq(struct).all());active={};allstates={k:[] for k in u.index};expected_ev=[];recent={};alt={0.:{},.005:{}}
 for obj,spec in c['objects'].items():
  use=atomic if obj=='own' else ~atomic;ids=u.index[use];d=u.loc[ids];app=~struct.loc[ids].str.endswith('local_without_rural_zone') if obj=='rural' else pd.Series(True,index=ids);active[obj]=ids
  if spec.get('applicable_column'):app&=d[spec['applicable_column']].fillna(False)
  for a,b in [(2002,2010),(2010,2021),(2002,2021)]:
   ca=d[spec['complete'][str(a)]].astype(bool);cb=d[spec['complete'][str(b)]].astype(bool)
   if obj=='rural':ca&=d.n_unknown_role_external_settlements.eq(0);cb&=d.n_unknown_role_external_settlements.eq(0)
   pa=d[spec['population'][str(a)]];pb=d[spec['population'][str(b)]];ss,rr=states(pa,pb,ca,cb,b-a,app,.0025);ep=pd.DataFrame({'unit_id':ids,'object':obj,'period':f'{a}-{b}','state':ss,'annual_rate':rr,'start_population_raw':pa.to_numpy(),'end_population_raw':pb.to_numpy(),'start_complete':ca.to_numpy(),'end_complete':cb.to_numpy(),'applicable':app.to_numpy()});expected_ev.append(ep)
   for i,s in zip(ids,ss):allstates[i].append(f'{obj}:{a}-{b}={s}')
   if a==2010:
    recent[obj]=pd.Series(ss,index=ids)
    for delta in alt:alt[delta][obj]=pd.Series(states(pa,pb,ca,cb,b-a,app,delta)[0],index=ids)
 expected=pd.concat(expected_ev,ignore_index=True);key=['unit_id','object','period'];ck('unique_evidence',not e.duplicated(key).any() and len(e)==len(expected));ev=e.set_index(key).sort_index();ex=expected.set_index(key).sort_index();ck('all_evidence_keys',ev.index.equals(ex.index))
 for col in ['state','start_complete','end_complete','applicable']:ck('all3period_'+col,ev[col].eq(ex[col]).all())
 for col in ['annual_rate','start_population_raw','end_population_raw']:ck('all3period_'+col,np.isclose(ev[col].to_numpy(float),ex[col].to_numpy(float),rtol=1e-10,atol=1e-14,equal_nan=True).all())
 recentframe=pd.DataFrame(recent);expectedkeys=[];expectedalts=[];traj=[]
 for ident in u.index:
  objs=['own'] if atomic.loc[ident] else ['center','rural','system'];pairs={obj:recentframe.loc[ident,obj] for obj in objs};pk='T:'+struct.loc[ident]+'|'+','.join(obj+'='+pairs[obj] for obj in objs);expectedkeys.append(pk);traj.append(pairs);aa={}
  for delta in alt:
   ak='T:'+struct.loc[ident]+'|'+','.join(obj+'='+alt[delta][obj].loc[ident] for obj in objs)
   if ak!=pk:aa[str(delta)]=ak
  expectedalts.append(aa)
 ck('all_current_primary_type',t.primary_type_id.tolist()==expectedkeys);ck('all_current_trajectory',all(a==b for a,b in zip(t.trajectory_class.map(json.loads),traj)));ck('all_delta_sensitivities',all(a==b for a,b in zip(t.alternative_type.map(json.loads),expectedalts)));ck('all3period_orderedtrajectory',t.trajectory_all_periods.tolist()==[';'.join(allstates[i]) for i in u.index]);ck('roles',t.unit_role.eq(u.unit_role).all());ck('centralsets',all(json.loads(a)==sorted(json.loads(b)) for a,b in zip(t.central_object_ids,u.central_object_ids_json)));ck('no_invented_context',t.functional_context.eq('no_positive_witness_in_available_sources').all() and not c['context_witnesses'])
 evrecent=expected[expected.period.eq('2010-2021')];obs=evrecent.state.isin(['growth','stable','decline','extinction_observed','emergence_observed','observed_zero_both']).groupby(evrecent.unit_id).sum().reindex(u.index);appn=evrecent.applicable.groupby(evrecent.unit_id).sum().reindex(u.index);periodn=expected.state.isin(['growth','stable','decline','extinction_observed','emergence_observed','observed_zero_both']).groupby(expected.unit_id).sum().reindex(u.index)
 ck('observed_dimensions',t.observed_dimension_count.eq(obs).all());ck('applicable_dimensions',t.applicable_dimension_count.eq(appn).all());ck('allperiod_supported_count',t.observed_object_period_count.eq(periodn).all());adverse=pd.Series(False,index=u.index)
 for rule in c['quality_uncertainty_rules']:
  v=u[rule['column']];adverse|=~v.fillna(False) if rule['rule']=='not_true' else (v.isna()|v.gt(0))
 confidence=np.where(obs.eq(0),'structural_only',np.where(obs.lt(appn),'partial_demographic_support',np.where(adverse,'tentative_source_quality','source_supported_numeric')));ck('all_confidence',np.array_equal(t.classification_confidence,confidence));ck('source_end',sha(c['units_path'])==c['units_sha256'])
 r={'status':'ACCEPTED_INDEPENDENT_ALL_PERIODS_LIGHT_TYPES' if not bad else 'REJECTED','all_checks_passed':not bad,'n_failed':len(bad),'n_checks':len(checks),'checks':checks,'failures':bad,'accepted_units_sha256':c['units_sha256'],'complete_typology_sha256':sha(out/'complete_typology.parquet'),'evidence_sha256':sha(out/'trajectory_evidence.parquet'),'n_units':len(u),'n_object_period_rows':len(e),'classifier_contract_sha256':sha(contract),'profile_scope_sha256':sha(out/'PROFILE_SCOPE.json'),'code_sha256':sha(__file__),'types_scope':'every unit, all3periods,currenttype,delta0/.005,confidence; geographic resolution is not functional order'}
 dst=O/(out.parent.name+'_'+out.name+'_type_audit.json');dst.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(dst.name,r['status'],bad,flush=True)
 return r
if __name__=='__main__':
 pairs=json.loads(Path(sys.argv[1]).read_text())
 for row in pairs:run(Path(row['contract']),Path(row['output']));gc.collect()

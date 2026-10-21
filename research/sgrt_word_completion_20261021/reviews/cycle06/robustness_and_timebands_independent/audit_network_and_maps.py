#!/usr/bin/env python3
"""Independent source route scan, every rural gradient, core and four point fields."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=next(p for p in H.parents if (p/'.git').exists());R=ROOT/'robustness/cycle06_access_v2_baseline';M=ROOT/'model/output_cycle06_access_v2_baseline';P=ROOT/'maps/cycle06_access_v2_directed_timebands';checks=[];pins={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rd(p):pins[str(p)]=sha(p);return pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
def js(p):pins[str(p)]=sha(p);return json.loads(p.read_text())
def check(s,v,d=None):checks.append(dict(check=s,pass_=bool(v),detail=d));assert v,s+' '+str(d)
def clos(a,b,tol=1e-7):return (pd.isna(a) and pd.isna(b)) or (pd.notna(a) and pd.notna(b) and abs(float(a)-float(b))<=tol*max(1,abs(float(b))))
def slope(x,y,w=None):
 ok=np.isfinite(x)&np.isfinite(y)
 if w is not None:ok &=np.isfinite(w)
 x=x[ok];y=y[ok];w=np.ones(len(x)) if w is None else w[ok]
 if len(x)<5 or len(np.unique(x))<3:return np.nan
 design=np.column_stack([np.ones(len(x)),x/60]);return float(np.linalg.lstsq(design*np.sqrt(w[:,None]),y*np.sqrt(w),rcond=None)[0][1])
def run():
 for d in [R,P]:
  f=js(d/'freeze_manifest.json')['files'];check('all_frozen_files:'+d.name,all(sha(d/k)==(v['sha256'] if isinstance(v,dict) else v) for k,v in f.items()))
 cfg=js(ROOT/'model_inputs_cycle06/final_access_v2/config_baseline_final.json');nodes=rd(M/'nodes.parquet').set_index('id');mem=rd(M/'memberships.parquet').set_index('id');systems=rd(M/'systems.parquet').set_index(['level','center_id']);c=rd(M/'candidate_centers.parquet').set_index('id');pairs=rd(R/'rural_population_direct_network_pairs.parquet');grad=rd(R/'system_network_gradients.parquet').set_index(['level','center_id']);ledger=rd(P/'np_point_timebands.parquet');targets=rd(P/'selected_targets.parquet');mp=REPO/cfg['travel_manifest'];matrix=js(mp);orig=rd(mp.parent/matrix['origin_mapping']['path']);dest=rd(mp.parent/matrix['destination_mapping']['path']);snap=rd(mp.parent/'settlement_road_snap.parquet').set_index('id');D=len(dest);o=orig.set_index('id');d=dest.set_index('id')
 ordinary=nodes._population_axis_row.fillna(False);rural=ordinary&nodes.accepted_statistical_rural_role2021.eq(True).fillna(False);expected=[]
 for level in sorted(pairs.level.unique()):
  z=mem.loc[rural&mem[f'center_id_l{level}'].notna(),[f'center_id_l{level}']].reset_index();z.columns=['id','center_id'];z=z[z.id.ne(z.center_id)];z['level']=level;expected.append(z)
 expected=pd.concat(expected);check('all448567_rural_pairs_exact_frame',set(map(tuple,pairs[['id','center_id','level']].to_numpy()))==set(map(tuple,expected[['id','center_id','level']].to_numpy())) and len(pairs)==len(expected))
 for field in ['population_2010','population_2021','original_population_2010']:
  expected=pairs.id.map(nodes[field]);check('pair_source_values:'+field,np.allclose(pd.to_numeric(pairs[field]),pd.to_numeric(expected),equal_nan=True))
 check('V3roles_known_true_only',pairs.statistical_rural_role2021.eq(True).all())
 v=pairs.population_2010.gt(0)&pairs.population_2021.ge(0);change=(100*(pairs.population_2021/pairs.population_2010-1)).where(v);check('allpair_population_changes_and_zero',np.allclose(change,pairs.population_change_percent,equal_nan=True))
 # Four target choice from dated own population, never rank/Ci.
 allowed=ordinary&nodes.source_record_id_2021.notna()&nodes.accepted_formal_settlement_subtype2021.eq('город')&nodes.population_2021.ge(100000)&~nodes.axis_kind.fillna('').str.contains('territory|external_service',case=False);largest=nodes[allowed].reset_index().sort_values(['population_2021','id'],ascending=[False,True]).head(2).id.tolist();wantedtargets=['ctx:RU-FED-MOW','ctx:RU-FED-SPB']+largest;check('fourtarget_population_only_selection',targets.id.tolist()==wantedtargets)
 check('allmaporigin_rows_exact',len(ledger)==int(ordinary.sum())*4 and set(ledger.origin_id)==set(nodes.index[ordinary]) and not ledger.duplicated(['origin_id','target_id']).any())
 native=ledger.origin_id.map(nodes.source_record_id_2021).notna();check('dated_vs_historical_mapframe',ledger.native2021_frame.equals(native))
 pkeys=(pairs.id.map(o.origin_index)*D+pairs.center_id.map(d.destination_index));valid=pkeys.notna();wanted=np.sort(pkeys[valid].astype('int64').unique());times=np.full(len(wanted),np.nan,dtype='float32');seen=np.zeros(len(wanted),dtype=bool);mapchunks=[];targetidx=set(targets.id.map(d.destination_index));oc=orig.snap_km.to_numpy(float)*4;dc=dest.snap_km.to_numpy(float)*4;oids=orig.id.to_numpy();dids=dest.id.to_numpy()
 for item in matrix['parts']:
  file=mp.parent/item['path'];check('rawmatrixpart:'+item['path'],sha(file)==item['sha256']);pins[str(file)]=item['sha256'];x=pq.read_table(file,columns=['origin_index','destination_index','network_minutes']);oi=x['origin_index'].to_numpy();di=x['destination_index'].to_numpy();network=x['network_minutes'].to_numpy();key=oi.astype('int64')*D+di;pos=np.searchsorted(wanted,key);take=pos<len(wanted);take[take]&=wanted[pos[take]]==key[take]
  if take.any():
   ii=pos[take];check('unique_directpairs:'+item['path'],not seen[ii].any());total=(network[take]+np.asarray(oc[oi[take]]+dc[di[take]],dtype='float32')).astype('float32');total[oids[oi[take]]==dids[di[take]]]=0;times[ii]=total;seen[ii]=True
  z=np.isin(di,list(targetidx))
  if z.any():
   total=(network[z]+np.asarray(oc[oi[z]]+dc[di[z]],dtype='float32')).astype('float32');total[oids[oi[z]]==dids[di[z]]]=0;mapchunks.append(pd.DataFrame(dict(origin_id=oids[oi[z]],target_id=dids[di[z]],rawtotal=total)))
 ix=np.searchsorted(wanted,pkeys.fillna(-1).astype('int64'));expected=np.full(len(pairs),np.nan);ok=valid.to_numpy();expected[ok]=times[ix[ok]];check('every_rural_pair_actual_directed_time',np.allclose(expected,pairs.direct_network_minutes,equal_nan=True,rtol=0,atol=0))
 raw=pd.concat(mapchunks);merged=ledger.merge(raw,on=['origin_id','target_id'],how='left',validate='one_to_one');check('all4_fields_every_directedtime',np.allclose(merged.rawtotal,merged.directed_total_minutes,equal_nan=True,rtol=0,atol=0));upper=np.array([15,30,45,60,90,120,180,360]);codes=np.full(len(ledger),-1);known=ledger.directed_total_minutes.notna();codes[known]=np.searchsorted(upper,np.minimum(ledger.loc[known,'directed_total_minutes'],360),side='left');check('all695424_exact_bandcodes',np.array_equal(codes,ledger.time_band_code));check('unknown_stays_NA',ledger.loc[~known,'time_band_code'].eq(-1).all() and ledger.loc[~known,'missing_route_is_not_zero_or_infinite'].all())
 status=pd.Series('not_recorded_within_bounded_source_matrix_reason_unknown',index=ledger.index);inorig=ledger.origin_id.isin(o.index);snapaccepted=ledger.origin_id.map(snap.accepted_snap).fillna(False);xy=ledger.origin_id.map(nodes.lon).between(-180,180)&ledger.origin_id.map(nodes.lat).between(-90,90);status.loc[~inorig]='origin_not_in_matrix_frame';status.loc[~inorig&~snapaccepted]='origin_snap_rejected';status.loc[~inorig&~xy]='origin_coordinates_unavailable';status.loc[~ledger.target_id.isin(d.index)]='target_not_in_matrix_frame';status.loc[known]='directed_route_recorded';check('allmap_missing_statuses',status.equals(ledger.route_status))
 # Every system's gradient: independent least-squares linear algebra and rankcorr.
 recalculated=[]
 for key,g in pairs.groupby(['level','center_id'],observed=True):
  row=grad.loc[key];z=g[g.population_change_percent.notna()&g.direct_network_minutes.notna()];x=z.direct_network_minutes.to_numpy();y=z.population_change_percent.to_numpy();w=z.population_2010.to_numpy();positive=z[z.population_2021.gt(0)];primary=z[z.primary2010_supported];common=z[z.original_population_change_percent.notna()]
  vals={'slope_change_pp_per60min':slope(x,y),'slope_population2010_weighted':slope(x,y,w),'slope_excluding_zero2021':slope(positive.direct_network_minutes.to_numpy(),positive.population_change_percent.to_numpy()),'slope_primary2010_only':slope(primary.direct_network_minutes.to_numpy(),primary.population_change_percent.to_numpy()),'slope_reviewed2010_on_common':slope(common.direct_network_minutes.to_numpy(),common.population_change_percent.to_numpy()),'slope_original2010_on_common':slope(common.direct_network_minutes.to_numpy(),common.original_population_change_percent.to_numpy())}
  vals['spearman_rho']=z.direct_network_minutes.rank().corr(z.population_change_percent.rank()) if len(z)>=5 and z.direct_network_minutes.nunique()>=3 and z.population_change_percent.nunique()>1 else np.nan
  check('all_slope_variants:'+str(key),all(clos(row[k],v,1e-7) for k,v in vals.items()));check('all_sample_counts:'+str(key),row.n_rural_units==len(g) and row.n_direct_network_times==g.direct_network_minutes.notna().sum() and row.n_valid_time_and_demographic_pairs==len(z) and row.n_population2021_zero_in_valid_pairs==z.population_2021.eq(0).sum() and row.n_baseline2010_zero==g.population_2010.eq(0).sum());recalculated.append(dict(level=key[0],center_id=key[1],**vals))
 shares=rd(R/'center_share_and_network_gradients.parquet').set_index(['level','center_id'])
 for year in [2010,2021]:
  valid=systems[f'system_population_complete_{year}']&systems[f'system_population_known_sum_{year}'].gt(0)&systems[f'center_population_{year}'].notna();expected=(systems[f'center_population_{year}']/systems[f'system_population_known_sum_{year}']).where(valid);check('every_system_centershare:'+str(year),np.allclose(expected,shares['center_population_share_'+str(year)].reindex(expected.index),equal_nan=True))
 # Conditional core counterfactual from saved pre-clamp raw top Huff only.
 core=rd(R/'protected_core_counterfactual.parquet').set_index('id');rawalt=mem.raw_model_center_id.where(mem.raw_top_probability.ge(cfg['model']['minimum_choice_probability']));base=mem.assigned_center_id;same=(base.eq(rawalt)&base.notna()&rawalt.notna())|(base.isna()&rawalt.isna());changed=~same;check('nonprotected_unchanged',not changed[~mem.protected_core].any());check('all4009_core_alt',core.counterfactual_no_core_override_l1.astype('string').fillna('__NA__').equals(rawalt.reindex(core.index).astype('string').fillna('__NA__')));check('changed_core_counts',int(changed[mem.protected_core].sum())==3080 and int(changed[mem.protected_core&mem.index.isin(c.index[c.intrinsic_empirical_rank.eq(1)])].sum())==1201)
 pd.DataFrame(recalculated).to_parquet(H/'all3001_independent_gradient_refits.parquet',index=False);out=dict(status='INDEPENDENT_ALL_PAIR_DIRECTED_TIME_GRADIENT_CORE_AND_TIMEBAND_MATH_ACCEPTED',all_checks_passed=True,n_checks=len(checks),n_failed=0,checks=checks,source_sha256=pins,rural_pair_rows=len(pairs),system_gradient_rows=len(grad),point_timeband_rows=len(ledger),four_target_ids=wantedtargets,all_zero_endpoint_and_missing_route_rules_preserved=True,not_causal_or_observed_flow_or_continuous_zone=True,robustness_freeze_sha256=sha(R/'freeze_manifest.json'),timeband_freeze_sha256=sha(P/'freeze_manifest.json'),model_manifest_sha256=sha(M/'output_manifest.json'),code_sha256=sha(Path(__file__)));(H/'network_timeband_math_admission.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['checks','source_sha256']},indent=2))
if __name__=='__main__':run()

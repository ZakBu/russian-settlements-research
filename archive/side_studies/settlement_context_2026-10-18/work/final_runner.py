"""Locked retrospective evaluation. Commit predictions before parsing holdout labels.

No tuning. All fitting uses development labels; audit had previously summarized the
whole panel, so this is a current-run assessment, never historically unseen evidence.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import argparse,hashlib,json,time,sys,platform
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression,Ridge
from threadpoolctl import threadpool_limits
sys.path.insert(0,str(Path(__file__).resolve().parent/'e1'))
sys.path.insert(0,str(Path(__file__).resolve().parent/'statistics'))
from model_executor import features,read_dev_outcomes,build_model,predict,losses,score,sha,PARAMS
from statistical_utils import split_blocks,buffered_train_mask,paired_block_bootstrap
SEED=20261018

def design(f,direction,radius=30,raw_control=False,nn_control=False):
    x,base,_=features(f);base=list(base)
    if nn_control:
        x['nn_shape']=f.nn5_normalized;x['nn_distance']=np.log1p(f.nn1_km);base+=['nn_shape','nn_distance']
    r=radius
    if direction=='E1':
        extra=['history','zero_fraction','log_pair_count','coverage']
        x[extra[0]]=f[f'r{r}_history_symmetric_change'];x[extra[1]]=f[f'r{r}_history_zero_fraction']
        x[extra[2]]=np.log1p(f[f'r{r}_history_pair_count'])
        x[extra[3]]=np.divide(f[f'r{r}_history_pair_count'],f[f'r{r}_count_all'],out=np.full(len(f),np.nan),where=f[f'r{r}_count_all']>0)
        if raw_control:
            x['raw_log_mass2002']=np.log1p(f[f'r{r}_history_mass2002']);base+=['raw_log_mass2002']
    else:
        extra=['maxshare','logeffective_n','loglarger_distance','loglarger_ratio','degenerate','no_larger']
        x[extra[0]]=f[f'r{r}_maxshare'];x[extra[1]]=np.log1p(f[f'r{r}_effective_n'])
        x[extra[2]]=np.log1p(f.nearest_larger_km);x[extra[3]]=np.log1p(f.nearest_larger_size_ratio)
        x[extra[4]]=(f[f'r{r}_count_positive']<=1)|(f[f'r{r}_mass2010']<=0);x[extra[5]]=~np.isfinite(f.nearest_larger_km)
    return x.replace([np.inf,-np.inf],np.nan),base,extra

def linear_model(task):
    return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),
        LogisticRegression(C=1,max_iter=1000,random_state=SEED) if task=='zero' else Ridge(alpha=10))

def shuffle_block(x,cols,mask,block,rng):
    x=x.copy()
    for b in np.unique(block[mask]):
        ids=np.flatnonzero(mask&(block==b));x.iloc[ids,x.columns.get_indexer(cols)]=x.iloc[rng.permutation(ids)][cols].to_numpy()
    return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--features',required=True);ap.add_argument('--raw',required=True)
    ap.add_argument('--lock',required=True);ap.add_argument('--output',required=True);ap.add_argument('--original-features');ap.add_argument('--drift-features')
    ap.add_argument('--refits',type=int,default=20);a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    if any((out/n).exists() for n in ['evaluation.json','prediction_commitment.json','label_reveal_started.json']):raise RuntimeError('Existing evaluated/committed run: use a new amended run_id; never overwrite')
    lock=json.loads(Path(a.lock).read_text());assert lock['status']=='locked_for_remaining_retrospective_evaluation'
    assert sha(a.features)==lock['features_sha256'];assert sha(a.raw)==lock['input_sha256'];assert sha(__file__)==lock['final_runner_sha256']
    assert a.refits==lock['reweighted_fit_replicates']
    root=Path(__file__).resolve().parent
    for dep,digest in lock['dependencies_sha256'].items():assert sha(root/dep)==digest
    for axis in ['original','drift']:
        value=getattr(a,axis+'_features')
        assert bool(value)==bool(lock['sensitivity_features_sha256'].get(axis))
        if value:assert sha(value)==lock['sensitivity_features_sha256'][axis]
    f=pd.read_csv(a.features);blocks,hold,fold=split_blocks(f.longitude_2010,f.latitude_2010)
    split=pd.DataFrame({'entity_uid':f.entity_uid,'block_id':blocks,'holdout':hold,'fold':fold})
    split.to_csv(out/'split_manifest.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    assert sha(out/'split_manifest.csv.gz')==lock['split_sha256']
    p=f.population_2010.to_numpy(float);train0=(~hold)&(p>0);test=hold&(p>0)
    # Read only training outcomes. Holdout remains unparsed until predictions persist.
    trainp=f.entity_uid.map(read_dev_outcomes(a.raw,set(f.loc[train0,'entity_uid']))).to_numpy(float)
    assert np.isnan(trainp[hold]).all();assert np.isfinite(trainp[train0]).all();assert (trainp[train0]>=0).all()
    ys={'zero':(trainp==0).astype(float),'change':2*(trainp-p)/(trainp+p)}
    predictions=pd.DataFrame({'entity_uid':f.loc[test,'entity_uid'],'block_id':blocks[test]})
    configs=[]
    for direction in ['E1','E2']:
        configs += [dict(id=direction+'_primary',direction=direction),dict(id=direction+'_r10',direction=direction,radius=10),
                    dict(id=direction+'_r60',direction=direction,radius=60),dict(id=direction+'_nn',direction=direction,nn_control=True),
                    dict(id=direction+'_buffer100',direction=direction,buffer=100),dict(id=direction+'_linear',direction=direction,family='linear')]
    configs += [dict(id='E1_raw_control',direction='E1',raw_control=True),dict(id='E1_permuted',direction='E1',permuted=True)]
    for axis in ['original','drift']:
        if getattr(a,axis+'_features'):
            for d in ['E1','E2']:configs.append(dict(id=d+'_'+axis,direction=d,axis=axis))
    assert [c['id'] for c in configs]==lock['config_ids']
    runs=[];refit_predictions={};rng=np.random.default_rng(SEED)
    for conf in configs:
        cid=conf['id'];task='zero' if conf['direction']=='E1' else 'change';ff=f
        if conf.get('axis'):ff=pd.read_csv(getattr(a,conf['axis']+'_features'));assert (ff.entity_uid==f.entity_uid).all()
        x,base,extra=design(ff,conf['direction'],conf.get('radius',30),conf.get('raw_control',False),conf.get('nn_control',False))
        # Original-axis sensitivity keeps selected-axis risk/target fixed; own covariates follow variant axis.
        train=buffered_train_mask(f.latitude_2010,f.longitude_2010,train0,test,conf.get('buffer',60))
        nearest=BallTree(np.deg2rad(f.loc[test,['latitude_2010','longitude_2010']]),metric='haversine').query(np.deg2rad(f.loc[train,['latitude_2010','longitude_2010']]),k=1)[0][:,0]*6371.0088
        assert nearest.min()>=conf.get('buffer',60)-1e-6
        if conf.get('permuted'):
            x=shuffle_block(x,extra,train,blocks,rng);x=shuffle_block(x,extra,test,blocks,rng)
        t=time.time();run={'id':cid,'task':task,'direction':conf['direction'],'config':conf,'train_n':int(train.sum()),'test_n':int(test.sum()),
                         'train_blocks':len(set(blocks[train])),'test_blocks':len(set(blocks[test])),'minimum_train_test_km':float(nearest.min()),'baseline_columns':base,'additional_columns':extra}
        models={}
        for label,cols in [('baseline',base),('augmented',base+extra)]:
            with threadpool_limits(limits=2):
                m=linear_model(task) if conf.get('family')=='linear' else build_model(task)
                m.fit(x.loc[train,cols],ys[task][train]);pr=predict(m,x.loc[test,cols],task)
            predictions[cid+'_'+label]=pr;models[label]=m
        if cid in ['E1_primary','E2_primary']:
            # Random block reweighting stability fits, not exact duplicated bootstrap refits. Labels unopened.
            ub=np.unique(blocks[train]);preds=[]
            for rep in range(a.refits):
                drawn=rng.choice(ub,len(ub),replace=True);freq={b:int((drawn==b).sum()) for b in ub};w=np.array([freq[b] for b in blocks[train]])
                pair=[]
                for cols in [base,base+extra]:
                    with threadpool_limits(limits=2):
                        m=build_model(task);m.fit(x.loc[train,cols],ys[task][train],sample_weight=w);pair.append(predict(m,x.loc[test,cols],task))
                preds.append(pair)
            refit_predictions[cid]=np.asarray(preds)
        run['seconds']=time.time()-t;runs.append(run);print(json.dumps({'fitted':cid,'train_n':run['train_n'],'seconds':run['seconds']}),flush=True)
    predictions.to_parquet(out/'predictions_before_labels.parquet',index=False)
    predsha=sha(out/'predictions_before_labels.parquet')
    (out/'prediction_commitment.json').write_text(json.dumps({'created_unix':time.time(),'prediction_sha256':predsha,'protocol_sha256':sha(a.lock),'code_sha256':sha(__file__),'holdout_labels_parsed':0,'configs':runs},indent=2))
    # Single fixed reveal. This point must not trigger model or feature selection.
    (out/'label_reveal_started.json').write_text(json.dumps({'created_unix':time.time(),'prediction_sha256':predsha,'lock_sha256':sha(a.lock),'no_restart_without_amendment':True}))
    holdp=f.entity_uid.map(read_dev_outcomes(a.raw,set(f.loc[test,'entity_uid']))).to_numpy(float)[test]
    assert np.isfinite(holdp).all();assert (holdp>=0).all();observed={'zero':(holdp==0).astype(float),'change':2*(holdp-p[test])/(holdp+p[test])}
    predictions['observed_zero']=observed['zero'];predictions['observed_change']=observed['change']
    summaries=[];subsets=[]
    for run in runs:
        cid=run['id'];task=run['task'];y=observed[task];pb=predictions[cid+'_baseline'].to_numpy();pa=predictions[cid+'_augmented'].to_numpy()
        lb=losses(y,pb,task);la=losses(y,pa,task);interval=paired_block_bootstrap(blocks[test],lb,la)
        row={'id':cid,'task':task,'baseline':score(y,pb,task),'augmented':score(y,pa,task),'interval':interval,'relative_gain':float((lb.mean()-la.mean())/lb.mean()),'primary':cid in ['E1_primary','E2_primary']}
        if cid in refit_predictions:
            prs=refit_predictions[cid];deltas=[float((losses(y,z[0],task)-losses(y,z[1],task)).mean()) for z in prs]
            row['training_refit_delta_quantiles']=np.quantile(deltas,[.025,.5,.975]).tolist();row['training_refit_replicates']=len(deltas)
            np.save(out/(cid+'_training_refit_predictions.npy'),prs,allow_pickle=False)
        summaries.append(row)
        for name,mask in [('outside_capital100km',~f.capital_within100km.to_numpy()[test]),('protected2010',f.population_value_quality_2010.str.startswith('secondary',na=False).to_numpy()[test]),('other_quality2010',~f.population_value_quality_2010.str.startswith('secondary',na=False).to_numpy()[test])]:
            if mask.sum():subsets.append({'id':cid,'subset':name,'n':int(mask.sum()),'baseline_loss':float(lb[mask].mean()),'augmented_loss':float(la[mask].mean()),'delta':float((lb[mask]-la[mask]).mean()),'evaluation_only_no_refit':True})
    predictions.to_parquet(out/'predictions.parquet',index=False)
    pd.DataFrame(subsets).to_csv(out/'subgroup_sensitivity.csv',index=False)
    (out/'evaluation.json').write_text(json.dumps({'status':'computed_single_locked_reveal','lock_sha256':sha(a.lock),'prediction_commitment_sha256':predsha,'rows_master':len(f),'risk_n':int((p>0).sum()),'development_risk_n':int(train0.sum()),'holdout_risk_n':int(test.sum()),'holdout_zero_n':int(observed['zero'].sum()),'holdout_blocks':len(set(blocks[test])),'results':summaries,'configs':runs,'seed':SEED,'params':PARAMS,'python':platform.python_version(),'interpretation':'Conditional descriptive uncertainty; no calibrated p-values, no causal or national-universe inference. Block-reweighted-fit quantiles are stability diagnostics, not complete confidence intervals.'},ensure_ascii=False,indent=2))
    print(json.dumps({'status':'completed','primary':[s for s in summaries if s['primary']]},ensure_ascii=False),flush=True)

if __name__=='__main__':main()

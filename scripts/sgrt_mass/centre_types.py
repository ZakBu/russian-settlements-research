#!/usr/bin/env python3
"""Cluster recorded/modelled centre profiles, never infer SGRT boundaries.

Population, distinct recorded service channels and single-function demographic
support are descriptive axes. They must not be fed back into attraction weights.
Unknown institution-to-NP identity and nonadditive federal aggregates remain
explicit additional types instead of receiving fictitious census populations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

SEED=20261024
MODELS={
    'population_only':['log_population_2021'],
    'population_and_functions':['log_population_2021','known_function_count'],
    'population_functions_and_support':['log_population_2021','known_function_count','log_max_single_function_external_population'],
    'population_and_sectors':['log_population_2021','known_sector_count'],
}


def column(frame,candidates,*,required=True):
    for name in candidates:
        if name in frame:return name
    if required:raise ValueError('Missing one of columns: '+', '.join(candidates))
    return None


def sector(service):
    text=str(service).lower()
    if text.startswith(('medical','healthcare')):return 'healthcare'
    if text.startswith(('school','preschool','vocational','higher','education')):return 'education'
    if text.startswith(('employment','labour','labor','workplace','jobs')):return 'employment'
    if text.startswith(('trade','retail','commerce','market')):return 'commerce'
    if text.startswith(('admin','government')):return 'administration'
    return 'other:'+text


def function_channel(service):
    value=str(service)
    return 'preschool' if value=='preschool_official' else value


def build_profiles(units,reference,*,scenario=None,combine_source_layers=False):
    """One profile per accepted NP or individual unknown-NP centre.

    Demographic support is MAX across separate functional memberships, never
    their sum. The same residents may belong to several overlapping functions.
    Only credited, ordinary census populations become the population feature.
    """
    data=units.copy()
    scenario_col=column(data,['scenario','source_scenario','model_scenario'],required=False)
    if scenario_col:
        values=data[scenario_col].dropna().astype(str).unique()
        if combine_source_layers and scenario is not None:raise ValueError('Choose a scenario or complementary source layers, not both')
        if combine_source_layers and not set(values)<={'registry_or_address_np','physical_sites'}:
            raise ValueError('Only the explicitly named complementary geometry source layers can be combined')
        if len(values)>1 and scenario is None and not combine_source_layers:raise ValueError('Multiple scenarios: select one explicitly')
        if scenario is not None:data=data[data[scenario_col].astype(str).eq(scenario)].copy()
    if data.empty:raise ValueError('No units in selected scenario')
    source_col=column(data,['center_source_record_id','centre_source_record_id','selected_provider_source_record_id','center_id'],required=False)
    key_col=column(data,['center_key','centre_key','provider_id','center_id','unit_id','center_source_record_id','centre_source_record_id'])
    service_col=column(data,['service_code','service_order'])
    support_col=column(data,['external_population_2021','external_population','surroundings_population_2021','external_current_population','max_single_function_external_population'],required=False)
    count_col=column(data,['n_populated_external','external_positive_credited_settlements','external_populated_members'],required=False)
    data['source_record_id']=data[source_col] if source_col else None
    data['source_record_id']=data.source_record_id.where(data.source_record_id.notna()&data.source_record_id.astype(str).str.startswith('2021:'),None)
    raw_keys=data[key_col].astype(str)
    site_keys=raw_keys.where(raw_keys.str.startswith('site:'),'site:'+raw_keys)
    data['centre_key']=np.where(data.source_record_id.notna(),'np:'+data.source_record_id.astype(str),site_keys)
    data['sector']=data[service_col].map(sector)
    data['normalized_function_channel']=data['function_channel'].fillna(data[service_col].map(function_channel)) if 'function_channel' in data else data[service_col].map(function_channel)
    data['external_support']=pd.to_numeric(data[support_col],errors='coerce') if support_col else np.nan
    if data.external_support.dropna().lt(0).any():raise ValueError('Negative demographic support')
    data['external_populated_count']=pd.to_numeric(data[count_col],errors='coerce') if count_col else np.nan
    if data.external_populated_count.dropna().lt(0).any():raise ValueError('Negative external member count')
    ref=reference.copy()
    refkey=column(ref,['source_record_id','source_record_id_2021'])
    if ref[refkey].dropna().duplicated().any():raise ValueError('Nonunique census reference ID')
    ref=ref[ref[refkey].notna()].set_index(refkey)
    popcol=column(ref,['population_2021','population','effective_population_2021'])
    creditcol=column(ref,['credit_2021','working_credit_present','working_credit_present_2021'],required=False)
    rolecol=column(ref,['population_role'],required=False)
    rows=[]
    for key,g in data.groupby('centre_key',sort=True):
        ids=g.source_record_id.dropna().unique()
        sid=ids[0] if len(ids)==1 else None
        if len(ids)>1:raise ValueError('Centre key has conflicting census identities')
        r=ref.loc[sid] if sid in ref.index else None
        role=r[rolecol] if r is not None and rolecol else None
        external_context=role=='external_context_nonadditive'
        credited=bool(r[creditcol]) if r is not None and creditcol and pd.notna(r[creditcol]) else False
        population=float(r[popcol]) if r is not None and pd.notna(r[popcol]) and credited and role=='ordinary_settlement_record' else np.nan
        if pd.notna(population) and population<0:raise ValueError('Negative credited centre population')
        support=float(g.external_support.max()) if g.external_support.notna().any() else np.nan
        sectors=sorted(set(g.sector))
        function_count=int(g.normalized_function_channel.nunique())
        if 'known_function_count' in g:
            declared=pd.to_numeric(g.known_function_count,errors='coerce').dropna().unique()
            if len(declared)>1 or (len(declared)==1 and declared[0]!=function_count):
                raise ValueError('Provided known_function_count is not distinct service-channel count; regenerate the unit file')
        row={'centre_key':key,'center_source_record_id':sid,'center_name':r.get('name',r.get('settlement_name_2021',sid)) if r is not None else None,
            'region':r.get('region',r.get('region_norm_2021',None)) if r is not None else None,
            'population_role':role,'population_credit_present_2021':credited,'centre_population_2021':population,
            'known_sector_count':len(sectors),'known_sectors':'|'.join(sectors),
            'known_service_count':int(g[service_col].nunique()),'known_function_count':function_count,
            'known_function_channels':'|'.join(sorted(g.normalized_function_channel.astype(str).unique())),
            'known_service_codes':'|'.join(sorted(g[service_col].astype(str).unique())),
            'known_functions_are_lower_bound':True,'institution_inventory_complete':False,
            'max_single_function_external_population':support,
            'external_demographic_support_partial':bool(pd.to_numeric(g.external_population_unresolved_records,errors='coerce').fillna(0).gt(0).any()) if 'external_population_unresolved_records' in g else None,
            'external_demographic_support_completeness_known':'external_population_unresolved_records' in g,
            'max_single_function_external_populated_settlements':float(g.external_populated_count.max()) if g.external_populated_count.notna().any() else np.nan,
            'support_aggregation':'maximum_single_function_not_sum_of_overlapping_memberships',
            'external_population_measure_is_observed_clients':False,'not_for_gravity_mass_calibration':True,
            'selected_scenario':scenario if scenario is not None else 'complementary_source_layers:'+'|'.join(sorted(g[scenario_col].astype(str).unique())) if combine_source_layers and scenario_col else str(g[scenario_col].iloc[0]) if scenario_col else 'single_input_scenario'}
        row['has_known_populated_external_members']=bool(row['max_single_function_external_populated_settlements']>0) if pd.notna(row['max_single_function_external_populated_settlements']) else None
        if external_context:status='external_context_nonadditive'
        elif sid is None:status='unknown_centre_np_identity'
        elif r is None:status='centre_id_absent_from_reference'
        elif role!='ordinary_settlement_record':status='nonordinary_or_unverified_population_role'
        elif pd.isna(population):status='missing_credited_centre_population'
        elif pd.isna(support):status='missing_external_demographic_support'
        else:status='features_available_source_network_incomplete'
        row.update(data_completeness=status,clustering_feature_complete=status=='features_available_source_network_incomplete',
                   log_population_2021=np.log1p(population) if pd.notna(population) else np.nan,
                   log_max_single_function_external_population=np.log1p(support) if pd.notna(support) else np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def elbow_k(metrics):
    """Geometric elbow of normalized inertia, reported independently of silhouette."""
    d=metrics[metrics.k.ge(2)].sort_values('k')
    if len(d)<3:return None
    x=d.k.to_numpy(float);y=d.inertia.to_numpy(float)
    if np.ptp(x)==0 or np.ptp(y)==0:return None
    x=(x-x.min())/np.ptp(x);y=(y-y.min())/np.ptp(y)
    distance=np.abs(x+y-1)/np.sqrt(2)
    return int(d.iloc[int(np.argmax(distance))].k)


def fit_variant(profiles,features,*,max_k=8,silhouette_sample=3000):
    if max_k<2 or silhouette_sample<3:raise ValueError('Need max_k>=2 and silhouette_sample>=3')
    x=profiles[features].to_numpy(dtype=float)
    if not np.isfinite(x).all():raise ValueError('Missing or infinite clustering features')
    scaled=StandardScaler().fit(x)
    z=scaled.transform(x)
    unique=len(np.unique(z,axis=0));n=len(z)
    if n==0:raise ValueError('No eligible centre profiles')
    top=min(max_k,n-1,unique)
    metrics=[];fits={}
    rng=np.random.default_rng(SEED)
    assessment=np.sort(rng.choice(n,size=min(silhouette_sample,n),replace=False))
    for k in [1,*range(2,top+1)]:
        model=KMeans(n_clusters=k,random_state=SEED,n_init=20,max_iter=300,tol=1e-4,algorithm='lloyd')
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            model.fit(z)
        labels=model.labels_;fits[k]=model
        sampled_labels=labels[assessment]
        score=float(silhouette_score(z[assessment],sampled_labels,metric='euclidean')) if 1<len(np.unique(sampled_labels))<len(assessment) else np.nan
        metrics.append({'k':k,'inertia':float(model.inertia_),'silhouette':score,'fitted_centres':n,
                        'unique_feature_profiles':unique,'silhouette_sample_count':len(assessment),
                        'silhouette_sample_clusters':len(np.unique(sampled_labels)),
                        'candidate_for_silhouette_selection':k>=2,'random_seed':SEED,'n_init':20})
    table=pd.DataFrame(metrics)
    valid=table[table.candidate_for_silhouette_selection&table.silhouette.notna()]
    chosen=int(valid.sort_values(['silhouette','k'],ascending=[False,True]).k.iloc[0]) if len(valid) else 1
    def ordered_labels(raw):
        medians=profiles.assign(_cluster=raw).groupby('_cluster')[['centre_population_2021','max_single_function_external_population','known_function_count','known_sector_count']].median()
        ordered=medians.sort_values(['centre_population_2021','max_single_function_external_population','known_function_count','known_sector_count']).index.tolist()
        rank={int(label):i for i,label in enumerate(ordered)}
        return np.array([rank[int(label)] for label in raw],dtype=int)
    model=fits[chosen];labels=ordered_labels(model.labels_)
    distances=model.transform(z)
    minimum=np.min(distances,axis=1)
    second=np.partition(distances,1,axis=1)[:,1] if chosen>1 else np.full(n,np.nan)
    margin=np.divide(second-minimum,second,out=np.zeros(n),where=second>0) if chosen>1 else np.full(n,np.nan)
    alternative=elbow_k(table)
    partitions={k:ordered_labels(fit.labels_) for k,fit in fits.items()}
    result={'labels':labels,'distance':minimum,'separation_margin':margin,'selected_k':chosen,
            'partitions_by_k':partitions,'elbow_labels':partitions.get(alternative),
            'elbow_k':alternative,'features':features,'feature_means':dict(zip(features,scaled.mean_.tolist())),
            'feature_scales':dict(zip(features,scaled.scale_.tolist())),
            'selection':'maximum_sample_silhouette; smaller_k_if_exact_tie' if chosen>1 else 'single_cluster_insufficient_distinct_profiles_for_silhouette'}
    return result,table


def classify(profiles,*,max_k=8,silhouette_sample=3000):
    out=profiles.copy()
    eligible=out.clustering_feature_complete.eq(True)
    metrics=[];choices={};sensitivity=[]
    out['scale_type']=out.data_completeness
    out['scale_type_index']=pd.Series(pd.NA,index=out.index,dtype='Int64')
    out['scale_type_is_spatial_hierarchy_level']=False
    out['source_coverage_uncertainty']=True
    if not eligible.any():return out,pd.DataFrame(),pd.DataFrame(),{'eligible_centres':0,'selected_k':None}
    frame=out.loc[eligible].copy()
    for name,features in MODELS.items():
        result,table=fit_variant(frame,features,max_k=max_k,silhouette_sample=silhouette_sample)
        table['variant']=name;metrics.append(table)
        choices[name]=result
        out['scale_type_'+name]=pd.Series(pd.NA,index=out.index,dtype='Int64')
        out.loc[eligible,'scale_type_'+name]=result['labels']
        out['elbow_type_'+name]=pd.Series(pd.NA,index=out.index,dtype='Int64')
        if result['elbow_labels'] is not None:out.loc[eligible,'elbow_type_'+name]=result['elbow_labels']
        for k,labels in result['partitions_by_k'].items():
            field=f'profile_cluster_{name}_k{k}'
            out[field]=pd.Series(pd.NA,index=out.index,dtype='Int64')
            out.loc[eligible,field]=labels
    main=choices['population_functions_and_support']
    out.loc[eligible,'scale_type_index']=main['labels']
    out.loc[eligible,'scale_type']=['scale_'+str(v) for v in main['labels']]
    out.loc[eligible,'cluster_distance_standardized']=main['distance']
    out.loc[eligible,'cluster_separation_margin_not_probability']=main['separation_margin']
    for a in MODELS:
        for b in MODELS:
            if a>=b:continue
            sensitivity.append({'variant_a':a,'variant_b':b,'centres':len(frame),
                'adjusted_rand_index':float(adjusted_rand_score(choices[a]['labels'],choices[b]['labels'])),
                'k_a':choices[a]['selected_k'],'k_b':choices[b]['selected_k'],
                'meaning':'partition_sensitivity_to_feature_set_not_out_of_sample_accuracy'})
    summary={'eligible_centres':len(frame),'excluded_or_additional_types':len(out)-len(frame),
             'selected_k':main['selected_k'],'elbow_k':main['elbow_k'],
             'variants':{name:{k:v for k,v in result.items() if k not in ['labels','distance','separation_margin','partitions_by_k','elbow_labels']} for name,result in choices.items()},
             'feature_weights':'equal_weight_after_z_standardization_of_named_axes',
             'labels_ordered_by':'cluster_median_credited_population_then_external_support_then_function_channels_then_sectors',
             'not_spatial_hierarchy':True,'not_population_threshold_delineation':True,
             'not_for_attraction_mass_calibration':True,'institution_network_is_incomplete':True,
             'silhouette_is_not_validation_of_sgrt':True,
             'functional_complexity_definition':'number_of_distinct_recorded_service_channels_not_objects_or_binary_sector_count'}
    summary['main_partition_ARI_with_known_sector_count']=float(adjusted_rand_score(frame.known_sector_count,main['labels']))
    summary['main_cluster_by_sector_count']=frame.assign(scale_type_index=main['labels']).groupby(['scale_type_index','known_sector_count']).size().rename('centres').reset_index().to_dict('records')
    summary['elbow_partitions_saved_as_alternatives_not_spatial_levels']=True
    summary['source_coverage_review_required_before_interpreting_functional_scale']=True
    summary['eligible_profiles_with_partial_external_demography']=int(frame.external_demographic_support_partial.eq(True).sum()) if 'external_demographic_support_partial' in frame else None
    summary['eligible_centres_with_known_populated_external_members']=int(frame.has_known_populated_external_members.eq(True).sum()) if 'has_known_populated_external_members' in frame else None
    return out,pd.concat(metrics,ignore_index=True),pd.DataFrame(sensitivity),summary


def save(frame,path):
    frame.to_parquet(path.with_suffix('.parquet'),index=False,compression='zstd')
    frame.to_csv(path.with_suffix('.csv'),index=False)


def plot_diagnostics(metrics,summary,out):
    if metrics.empty or not metrics.k.ge(2).any():return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'population_only':'#89999F','population_and_functions':'#438879',
            'population_functions_and_support':'#236A95','population_and_sectors':'#C57737'}
    styles={'population_only':(':','^'),'population_and_functions':('--','s'),
            'population_functions_and_support':('-','o'),'population_and_sectors':('-.','D')}
    labels={'population_only':'только людность','population_and_functions':'людность + функции',
            'population_functions_and_support':'людность + функции + опора','population_and_sectors':'людность + секторы'}
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(12,5.5),facecolor='#FAFBF9')
    for name in ['population_functions_and_support','population_and_functions','population_only','population_and_sectors']:
        d=metrics[metrics.variant.eq(name)].sort_values('k');base=d[d.k.eq(1)].inertia.iloc[0];d=d[d.k.ge(2)]
        linestyle,marker=styles[name]
        axes[0].plot(d.k,d.inertia/base if base else d.inertia*0,marker=marker,ls=linestyle,color=colors[name],label=labels[name],lw=1.7,ms=4)
        axes[1].plot(d.k,d.silhouette,marker=marker,ls=linestyle,color=colors[name],label=labels[name],lw=1.7,ms=4)
    for ax,title in zip(axes,['Инерция при разных k','Силуэт при разных k']):
        ax.set_title(title,loc='left',fontsize=13,fontweight='bold',color='#24333E')
        ax.set_xlabel('число кластеров k');ax.set_xticks(sorted(metrics.loc[metrics.k.ge(2),'k'].unique()))
        ax.spines[['top','right']].set_visible(False);ax.grid(color='#E8ECEC',lw=.7);ax.set_axisbelow(True)
    axes[0].set_ylabel('инерция / инерция одного кластера')
    axes[1].set_ylabel('средний силуэт на оценочной выборке')
    if summary.get('elbow_k') is not None:
        axes[0].axvline(summary['elbow_k'],color='#24333E',ls='--',lw=1)
        axes[0].text(.97,.96,f'локоть основного: {summary["elbow_k"]}',transform=axes[0].transAxes,ha='right',va='top',fontsize=9)
    if summary.get('selected_k') is not None:
        axes[1].axvline(summary['selected_k'],color='#24333E',ls='--',lw=1)
        axes[1].text(.97,.96,f'максимум основного: {summary["selected_k"]}',transform=axes[1].transAxes,ha='right',va='top',fontsize=9)
    fig.suptitle('Профили центров по доступным данным: число групп',x=.075,ha='left',fontsize=17,fontweight='bold',color='#24333E')
    handles,legend=axes[0].get_legend_handles_labels()
    fig.legend(handles,legend,loc='lower center',bbox_to_anchor=(.51,.085),ncol=2,frameon=False,fontsize=9)
    n=summary['eligible_centres'];sample=int(metrics.silhouette_sample_count.max())
    fig.text(.075,.035,f'Обучение: {n:,} центров; оценка силуэта: {sample:,}. Неполная сеть услуг; это не уровни районов.'.replace(',',' '),fontsize=9,color='#596A73')
    fig.subplots_adjust(left=.075,right=.97,top=.80,bottom=.31,wspace=.28)
    fig.savefig(out/'centre_type_diagnostics.png',dpi=170,facecolor=fig.get_facecolor())
    fig.savefig(out/'centre_type_diagnostics.pdf',facecolor=fig.get_facecolor());plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['units','reference','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--scenario')
    parser.add_argument('--combine-source-layers',action='store_true',help='Explicitly combine complementary medical NP and physical education-site layers, never alternative screening scenarios')
    parser.add_argument('--max-k',type=int,default=8)
    parser.add_argument('--silhouette-sample',type=int,default=3000)
    args=parser.parse_args()
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    fingerprints={'units':digest(args.units),'reference':digest(args.reference),'code':digest(__file__)}
    profiles=build_profiles(pd.read_parquet(args.units),pd.read_parquet(args.reference),scenario=args.scenario,combine_source_layers=args.combine_source_layers)
    types,metrics,sensitivity,summary=classify(profiles,max_k=args.max_k,silhouette_sample=args.silhouette_sample)
    if fingerprints!={'units':digest(args.units),'reference':digest(args.reference),'code':digest(__file__)}:
        raise RuntimeError('Unit/reference/code snapshot changed during centre classification; rerun on frozen inputs')
    args.output.mkdir(parents=True,exist_ok=True)
    save(types,args.output/'centre_profiles_and_types')
    save(metrics,args.output/'k_diagnostics')
    save(sensitivity,args.output/'feature_sensitivity')
    grouped=types[types.clustering_feature_complete].groupby('scale_type').agg(
        centres=('centre_key','size'),population_p50=('centre_population_2021','median'),population_min=('centre_population_2021','min'),
        population_max=('centre_population_2021','max'),known_sector_p50=('known_sector_count','median'),
        known_function_p50=('known_function_count','median'),
        max_single_function_external_population_p50=('max_single_function_external_population','median'))
    save(grouped.reset_index(),args.output/'scale_type_summary')
    summary.update(all_centres=len(types),additional_type_counts=types[~types.clustering_feature_complete].scale_type.value_counts().to_dict())
    summary['input_sha256']=fingerprints
    plot_diagnostics(metrics,summary,args.output)
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

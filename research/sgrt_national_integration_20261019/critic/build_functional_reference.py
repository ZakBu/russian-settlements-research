"""National source comparison and descriptive positive-evidence reference.

No centre labels, interaction assignment, service radii, flows, or policy ranking.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd

RAWFUNCTIONS=['retail','food_service','education','healthcare','social_care','repair','personal','veterinary','pharmacy','banking','postal_service','marketplace_pickup']
FUNCTIONS=['trade_access']+RAWFUNCTIONS[1:-1]
POI={'school':'education','preschool':'education','other_education':'education','hospital':'healthcare','healthcare':'healthcare','veterinary':'veterinary','pharmacy':'pharmacy','bank':'banking','atm':'banking','post_office':'postal_service','postal_collection_point':'postal_service','market':'trade_access','retail_store':'trade_access','food_service':'food_service'}
def collapse(raw):return np.column_stack([raw[:,0]|raw[:,-1],raw[:,1:-1]])
BINS={'coarse':[0,100,500,1000,3000,10000,50000,100000,np.inf],
      'fine':[0,50,100,250,500,1000,2500,5000,10000,25000,50000,100000,np.inf]}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ref(frame,values,bins,minn):
    valid=(values>0)&frame.population_2021.gt(0)&frame.population_2021.notna()
    z=frame.loc[valid,['region']].copy();z['size_bin']=bins[valid].astype('string');z['k']=values[valid];z['_row']=np.flatnonzero(valid)
    reg=z.groupby(['region','size_bin'],dropna=False).k.agg(['size','median']).reset_index();nat=z.groupby('size_bin',dropna=False).k.agg(['size','median']).reset_index()
    z=z.merge(reg,on=['region','size_bin'],validate='many_to_one').merge(nat,on='size_bin',suffixes=('_reg','_rf'),validate='many_to_one')
    z['regional_rank']=(z.groupby(['region','size_bin']).k.rank(method='average')-.5)/z.size_reg
    z['national_rank']=(z.groupby('size_bin').k.rank(method='average')-.5)/z.size_rf
    regional=z.size_reg.ge(minn);fallback=~regional&z.size_rf.ge(minn);good=regional|fallback
    result=pd.DataFrame(index=frame.index,columns=['referenceN','reference_median','reference_midrank','observed_diversity_minus_reference_median'],dtype='float64')
    scope=np.full(len(frame),'not_in_positive_evidence_reference',object);scope[valid]='insufficient_positive_reference'
    rr=z.loc[good,'_row'].astype(int).to_numpy();choose=regional[good].to_numpy()
    median=np.where(choose,z.loc[good,'median_reg'],z.loc[good,'median_rf']);result.loc[rr,'reference_median']=median
    result.loc[rr,'referenceN']=np.where(choose,z.loc[good,'size_reg'],z.loc[good,'size_rf'])
    result.loc[rr,'reference_midrank']=np.where(choose,z.loc[good,'regional_rank'],z.loc[good,'national_rank'])
    result.loc[rr,'observed_diversity_minus_reference_median']=values[rr]-median
    scope[rr]=np.where(choose,'same_region_size_bin_positive_evidence','RF_same_size_bin_positive_evidence_fallback')
    result['reference_scope']=pd.array(scope,dtype='string');return result
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--out',type=Path,default=Path(__file__).parent);a=ap.parse_args();b=a.base;o=a.out;o.mkdir(parents=True,exist_ok=True)
    sp=b/'national_integration_20261019/screening';audit=json.loads((sp/'SCREENING_AUDIT.json').read_text());assert audit['places_loaded'] and audit['pass'],'Wait for final Places-enabled screening'
    p=sp/'support_point_profiles.parquet';d=pd.read_parquet(p);assert len(d)==142570 and d.id.is_unique
    assert sha(sp/'support_point_screening.py')==audit['code_sha256'],'Screening outputs precede current code'
    for path,meta in audit['inputs'].items():assert sha(b/path)==meta['sha256'],f'Stale screening input:{path}'
    def mask(prefix,unmerged=True):
        names=[prefix+('_unmerged_function_' if unmerged else '_function_')+f+'_witness' for f in (RAWFUNCTIONS if unmerged else FUNCTIONS)];assert set(names)<=set(d)
        return d[names].fillna(False).to_numpy(bool)
    legalraw=mask('legal_native');lcondraw=mask('legal_conditional');physicalraw=mask('physical_baseline');pcondraw=mask('physical_conditional')
    wbraw=np.zeros_like(legalraw);wbraw[:,-1]=d.wb_strict_focus_published_locations.gt(0).to_numpy()
    wp=b/'national_integration_20261019/services/wb_name_relaxed_features.parquet';w=pd.read_parquet(wp);assert w.id.is_unique and set(w.id)==set(d.id);w=w.set_index('id').reindex(d.id)
    wbrelraw=np.zeros_like(legalraw);wbrelraw[:,-1]=w.wb_name_relaxed_inclusive_focus_locations.gt(0).to_numpy()
    assert (wbrelraw|wbraw==wbrelraw).all()
    rawbundles={'legal_native':legalraw,'physical_baseline':physicalraw,'physical_plus_wb_strict':physicalraw|wbraw,'baseline':legalraw|physicalraw|wbraw,'conditional_without_wb_relaxation':lcondraw|pcondraw|wbraw,'conditional_with_wb_relaxation':lcondraw|pcondraw|wbrelraw}
    bundles={k:collapse(v) for k,v in rawbundles.items()}
    legal=collapse(legalraw);physical=collapse(physicalraw);wb=collapse(wbraw);wbrel=collapse(wbrelraw)
    out=d[['id','name','type','region','lat','lon','population_2021']].copy()
    for label,edges in BINS.items():out['population2021_'+label+'_bin']=pd.cut(out.population_2021,edges,right=False,include_lowest=True).astype('string');out.loc[~out.population_2021.gt(0),'population2021_'+label+'_bin']=pd.NA
    summaries=[];sensitivity=[];geo=[];checks=[]
    counts={key:v.sum(axis=1) for key,v in bundles.items()}
    out['physical_new_any_vs_legal']=physical.any(axis=1)&~legal.any(axis=1)
    out['physical_adds_any_function_vs_legal']=(physical&~legal).any(axis=1)
    out['baseline_new_multi_vs_legal']=(counts['baseline']>=2)&(counts['legal_native']<2)
    out['physical_new_multi_vs_legal']=(counts['physical_baseline']>=2)&(counts['legal_native']<2)
    out['baseline_any_category_sensitive_to_conditional']=(np.minimum(counts['baseline'],2)!=np.minimum(counts['conditional_without_wb_relaxation'],2))
    out['additional_group_if_wb_name_relaxed']=(wbrel&~wb).any(axis=1)
    for key,arr in bundles.items():
        k=counts[key];out[key+'_listed_function_diversity']=k
        out[key+'_listed_signature']=['|'.join(np.array(FUNCTIONS)[row]) for row in arr]
        primary=ref(out,k,out.population2021_coarse_bin,30)
        for c in primary:out[key+'_'+c]=primary[c].to_numpy()
        for binning,minn in [('coarse',30),('coarse',60),('fine',30),('fine',60)]:
            rr=primary if (binning,minn)==('coarse',30) else ref(out,k,out['population2021_'+binning+'_bin'],minn)
            delta=rr.observed_diversity_minus_reference_median;v=delta.notna();common=v&primary.observed_diversity_minus_reference_median.notna()
            sensitivity.append({'bundle':key,'binning':binning,'minimum_referenceN':minn,'positive_listed_points':int((k>0).sum()),'reference_available':int(v.sum()),'regional_reference':int(rr.reference_scope.eq('same_region_size_bin_positive_evidence').sum()),'RF_fallback':int(rr.reference_scope.eq('RF_same_size_bin_positive_evidence_fallback').sum()),'above_reference_median':int(delta.gt(0).sum()),'below_reference_median':int(delta.lt(0).sum()),'common_with_primary':int(common.sum()),'above_median_flag_agreement_on_common':float(delta[common].gt(0).eq(primary.loc[common,'observed_diversity_minus_reference_median'].gt(0)).mean()) if common.any() else None})
        summaries.append({'bundle':key,'rows':len(out),'positive_listed_points':int((k>0).sum()),'one_group':int((k==1).sum()),'multiple_groups':int((k>=2).sum()),'no_accepted_listing_unknown_true_functions':int((k==0).sum()),'population_zero_with_positive_listing':int(((k>0)&out.population_2021.eq(0)).sum()),'reference_available':int(primary.reference_median.notna().sum()),'above_reference_median':int(primary.observed_diversity_minus_reference_median.gt(0).sum()),'is_external_centre_count':False})
        for dimension in ['region','population2021_coarse_bin']:
            temp=out[[dimension,'physical_new_any_vs_legal','physical_adds_any_function_vs_legal','baseline_new_multi_vs_legal']].copy();temp['positive']=k>0;temp['multiple']=k>=2;temp['above_reference']=primary.observed_diversity_minus_reference_median.gt(0).to_numpy();temp['reference_available']=primary.reference_median.notna().to_numpy();gg=temp.groupby(dimension,dropna=False).agg(points=('positive','size'),positive=('positive','sum'),multiple=('multiple','sum'),above_reference=('above_reference','sum'),reference_available=('reference_available','sum'),physical_new_any_vs_legal=('physical_new_any_vs_legal','sum'),physical_adds_any_function_vs_legal=('physical_adds_any_function_vs_legal','sum'),baseline_new_multi_vs_legal=('baseline_new_multi_vs_legal','sum')).reset_index().rename(columns={dimension:'stratum'});gg['dimension']=dimension;gg['bundle']=key;geo.append(gg)
        checks.append({'name':'reference_positive_only_'+key,'pass':not primary.loc[k==0,'reference_median'].notna().any()})
        checks.append({'name':'reference_excludes_population_zero_'+key,'pass':not primary.loc[out.population_2021.eq(0),'reference_median'].notna().any()})
        checks.append({'name':'minimum_referenceN_'+key,'pass':bool(primary.referenceN.dropna().ge(30).all())})
    out['actual_external_centrality_demonstrated']=False;out['measured_service_capacity_surplus']=False;out['reference_comparison_is_policy_ranking']=False
    out.to_parquet(o/'national_functional_reference.parquet',index=False);out.to_csv(o/'national_functional_reference.csv.gz',index=False)
    pd.DataFrame(summaries).to_csv(o/'source_bundle_comparison.csv',index=False);pd.DataFrame(sensitivity).to_csv(o/'reference_sensitivity.csv',index=False);pd.concat(geo,ignore_index=True).to_csv(o/'geography_and_size.csv',index=False)
    bdelta=out.baseline_observed_diversity_minus_reference_median
    examples=pd.concat([out[bdelta.gt(0)].sort_values(['baseline_observed_diversity_minus_reference_median','baseline_listed_function_diversity'],ascending=False).head(30).assign(example_role='above_same_size_reference_not_confirmed_centre'),out[bdelta.lt(0)].sort_values(['baseline_observed_diversity_minus_reference_median','population_2021']).head(30).assign(example_role='below_reference_not_unimportant_or_no_function'),out[out.population_2021.eq(0)&out.baseline_listed_function_diversity.gt(0)].head(20).assign(example_role='cross_date_population0_listing_positive_review')],ignore_index=True);examples.to_csv(o/'positive_negative_cases.csv',index=False)
    checks += [{'name':'full142570UID','pass':len(out)==142570 and out.id.is_unique and out.id.equals(d.id)},{'name':'eleven_semantic_groups','pass':len(FUNCTIONS)==11},{'name':'baseline_screening_masks_agree','pass':np.array_equal(bundles['baseline'],mask('baseline',False))},{'name':'conditional_superset','pass':bool((bundles['baseline']|bundles['conditional_without_wb_relaxation']==bundles['conditional_without_wb_relaxation']).all())},{'name':'WBrelaxed_separate_and_superset','pass':bool((wbrel|wb==wbrel).all())},{'name':'no_false_external_centrality','pass':not out.actual_external_centrality_demonstrated.any()}]
    # Confidence is a relative source filter, not a calibrated existence probability.
    pp=b/'national_integration_20261019/places/places_objects_and_crosswalk.parquet'
    places=pd.read_parquet(pp,columns=['source_place_id','baseline_uid','source_confidence','source_operating_status','function_group','name_signal_ozon','name_signal_wildberries'])
    eligible=places.baseline_uid.notna()&places.function_group.isin(POI)&places.source_operating_status.ne('permanently_closed')
    index=pd.Index(out.id);findex={f:i for i,f in enumerate(FUNCTIONS)};confsummary=[];confgeo=[];confout=out[['id']].copy();previous=None
    for tag,threshold in [('primary_positive_or_unknown',None),('ge0p5',.5),('ge0p8',.8),('ge0p95',.95)]:
        take=eligible&((places.source_confidence.gt(0)|places.source_confidence.isna()) if threshold is None else places.source_confidence.ge(threshold))
        selected=places[take];arr=np.zeros_like(physical)
        row=index.get_indexer(selected.baseline_uid);col=selected.function_group.map(POI).map(findex).to_numpy(int);assert (row>=0).all();arr[row,col]=True
        if threshold is None:checks.append({'name':'primary_physical_reconstructed_from_eligible_nonzero_confidence_records','pass':np.array_equal(arr,physical)})
        if previous is not None:checks.append({'name':'confidence_function_subset_'+tag,'pass':bool((arr|previous==previous).all())})
        previous=arr
        combined=legal|arr|wb
        for key,mat in [('physical_baseline',arr),('baseline',combined)]:
            k=mat.sum(axis=1);rr=ref(out,k,out.population2021_coarse_bin,30);primarydelta=out[key+'_observed_diversity_minus_reference_median'];common=rr.reference_median.notna()&primarydelta.notna();delta=rr.observed_diversity_minus_reference_median;original=bundles[key]
            fixed=(pd.Series(k,index=out.index)-out[key+'_reference_median']).where((k>0)&out[key+'_reference_median'].notna())
            confsummary.append({'threshold':tag,'minimum_confidence':threshold,'bundle':key,'retained_baseline_linked_requested_POI_records':len(selected),'positive_listed_UID':int((k>0).sum()),'multiple_groups_UID':int((k>=2).sum()),'reference_available':int(rr.reference_median.notna().sum()),'above_recomputed_reference_median':int(delta.gt(0).sum()),'below_recomputed_reference_median':int(delta.lt(0).sum()),'above_fixed_primary_reference_median':int(fixed.gt(0).sum()),'fixed_primary_reference_available_positive_UID':int(fixed.notna().sum()),'same_exact_function_set_as_primary_UID':int((mat==original).all(axis=1).sum()),'primary_positive_lost':int((original.any(axis=1)&~mat.any(axis=1)).sum()),'common_reference_UID':int(common.sum()),'above_median_agreement_with_primary_on_common':float(delta[common].gt(0).eq(primarydelta[common].gt(0)).mean()) if common.any() else None,'score_is_calibrated_probability':False})
            if key=='baseline':
                confout[tag+'_listed_function_diversity']=k;confout[tag+'_reference_median']=rr.reference_median;confout[tag+'_referenceN']=rr.referenceN;confout[tag+'_observed_diversity_minus_reference_median']=delta;confout[tag+'_observed_diversity_minus_fixed_primary_median']=fixed
                z=out[['region']].copy();z['positive']=k>0;z['multiple']=k>=2;z['positive_lost_vs_primary']=original.any(axis=1)&~mat.any(axis=1);z['any_function_lost_vs_primary']=(original&~mat).any(axis=1);gg=z.groupby('region',dropna=False).agg(points=('positive','size'),positive=('positive','sum'),multiple=('multiple','sum'),positive_lost_vs_primary=('positive_lost_vs_primary','sum'),any_function_lost_vs_primary=('any_function_lost_vs_primary','sum')).reset_index();gg['threshold']=tag;confgeo.append(gg)
    confout.to_parquet(o/'confidence_reference_by_point.parquet',index=False);pd.DataFrame(confsummary).to_csv(o/'confidence_sensitivity.csv',index=False);pd.concat(confgeo,ignore_index=True).to_csv(o/'confidence_changes_by_region.csv',index=False)
    # Separate sensitivity for the false retail+pickup duplication of a single PVZ.
    brandretail=places.function_group.eq('retail_store')&(places.name_signal_ozon|places.name_signal_wildberries)
    keep=eligible&~brandretail&(places.source_confidence.gt(0)|places.source_confidence.isna())
    stripped=np.zeros_like(physicalraw);selected=places[keep];row=index.get_indexer(selected.baseline_uid);rawmap={k:('retail' if v=='trade_access' else v) for k,v in POI.items()};rawindex={f:i for i,f in enumerate(RAWFUNCTIONS)};col=selected.function_group.map(rawmap).map(rawindex).to_numpy(int);stripped[row,col]=True
    rawfiltered=legalraw|stripped|wbraw
    grouping=[]
    for key,mat in [('primary_11_trade_access',bundles['baseline']),('unmerged12',rawbundles['baseline']),('unmerged12_without_brand_retail_POI',rawfiltered),('primary11_without_brand_retail_POI',collapse(rawfiltered))]:
        k=mat.sum(axis=1);rr=ref(out,k,out.population2021_coarse_bin,30);delta=rr.observed_diversity_minus_reference_median
        grouping.append({'semantic_variant':key,'positive_UID':int((k>0).sum()),'multiple_groups_UID':int((k>=2).sum()),'reference_available':int(rr.reference_median.notna().sum()),'above_reference_median':int(delta.gt(0).sum()),'excluded_source_brand_retail_baseline_POI_records':int((eligible&brandretail).sum()) if 'without_brand' in key else 0,'classification_is_actual_centrality':False})
    pd.DataFrame(grouping).to_csv(o/'trade_pickup_grouping_sensitivity.csv',index=False)
    pd.testing.assert_frame_equal(out,pd.read_parquet(o/'national_functional_reference.parquet'));checks.append({'name':'whole_parquet_readback','pass':True})
    report={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','rows':len(out),'columns':len(out.columns),'checks':checks,'checks_passed':sum(c['pass'] for c in checks),'checks_total':len(checks),'FUNCTIONS':FUNCTIONS,'reference_semantics':'descriptive_median_and_midrank_among_positive_listed_evidence;self_included;no_training_or_independent_validation_claim','minimum_primary_referenceN':30,'population_year':2021,'source_dates':'RFSD2025;WB2026-10-19;Overture2026-09-23.1','missing_evidence_not_no_function':True,'inputs':{str(q.relative_to(b)):sha(q) for q in [p,sp/'SCREENING_AUDIT.json',wp,pp]},'producer_sha256':sha(Path(__file__)),'external_centrality_proven_UID':0,'confidence_source':'https://docs.overturemaps.org/guides/places/#confidence-score','confidence_semantics':'relative_filter_not_strictly_comparable_across_providers;0_certain_nonexistence;unknown_score_not_zero;operating_status_separate'}
    (o/'FUNCTIONAL_REFERENCE_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');assert report['status']=='PASS';print(json.dumps({k:v for k,v in report.items() if k not in ['checks','inputs']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

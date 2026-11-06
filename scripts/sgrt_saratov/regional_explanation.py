"""Whole-oblast contrasts and observation bias, not inferred settlement systems.

Source settlement classes and empirical rural size quartiles are descriptive
strata. They never define centre ranks, suburbs or functional boundaries.
Municipal agriculture/sector values stay on one row per parent territory.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd


def unique(frame, key, name):
    if frame[key].isna().any() or frame[key].duplicated().any():
        raise ValueError(name+' needs unique, nonmissing '+key)


def group_summary(g):
    pop=pd.to_numeric(g.population_2021,errors='coerce')
    workers=pd.to_numeric(g.partial_organisation_workforce_2025,errors='coerce')
    known=workers.notna()
    if (known & ~g.partial_workforce_status.eq('observed_partial_organisation_workforce')).any() or ((~known)&g.partial_workforce_status.eq('observed_partial_organisation_workforce')).any():
        raise ValueError('Contradictory numeric workforce and source status')
    if (~np.isfinite(workers[known]) | workers[known].lt(0)).any():
        raise ValueError('Invalid reported partial organisation workforce')
    eligible=g.population_eligible_2002_strict.eq(True)&g.population_eligible_2021_strict.eq(True)
    z=g[eligible]
    a=float(z.population_2002.sum()) if len(z) else None
    b=float(z.population_2021.sum()) if len(z) else None
    total=float(pop.sum())
    out={'records':len(g),'inhabited_records_2021':int(pop.gt(0).sum()),
         'published_zero_records_2021':int(pop.eq(0).sum()),
         'population_2021_known_records':int(pop.notna().sum()),'known_population_2021':total,
         'numeric_partial_worker_records':int(known.sum()),
         'numeric_zero_worker_records':int(workers.eq(0).sum()),
         'source_suppressed_worker_records':int(g.partial_workforce_status.eq('source_suppressed').sum()),
         'worker_population_2021_at_numeric_records':float(pop[known].sum()),
         'worker_np_coverage_share':float(known.mean()) if len(g) else None,
         'worker_population_coverage_share':float(pop[known].sum()/total) if total>0 else None,
         'known_subset_partial_organisation_workers_2025':float(workers[known].sum()) if known.any() else None,
         'numeric_strict_record_pairs_2002_2021':int(eligible.sum()),
         'numeric_strict_pairs_population_2002':a,'numeric_strict_pairs_population_2021':b,
         'reported_population_change_percent_on_same_record_pairs':100*(b/a-1) if a is not None and a>0 else None,
         'positive_change_record_pairs':int(z.population_2021.gt(z.population_2002).sum()),
         'appearance_from_published_zero_record_pairs':int((z.population_2002.eq(0)&z.population_2021.gt(0)).sum()),
         'negative_change_record_pairs':int(z.population_2021.lt(z.population_2002).sum()),
         'unchanged_record_pairs':int(z.population_2021.eq(z.population_2002).sum()),
         'numeric_pair_unavailable_records':int((~eligible).sum()),
         'known_model_coordinate_records':int(g.model_lat.notna().sum()),
         'historical_boundary_equivalence_proven':False,
         'worker_statistic_is_resident_employment_or_complete_jobs':False}
    out['worker_records_without_numeric_value']=len(g)-int(known.sum())
    out['unknown_worker_records']=int((~known & ~g.partial_workforce_status.eq('source_suppressed')).sum())
    for family in ['school','medical_basic','grocery']:
        k=g[family+'_known_local_supply_preferred'].eq(True)
        out[family+'_known_local_np']=int(k.sum())
        out[family+'_local_presence_unknown_np']=len(g)-int(k.sum())
        out[family+'_known_local_population_2021']=float(pop[k].sum())
    return out


def build_np(context,roster,links,documented_members):
    unique(context,'source_record_id','context');unique(roster,'source_record_id','roster')
    if set(context.source_record_id)!=set(roster.source_record_id):
        raise ValueError('Whole-oblast context and spatial axes differ')
    columns=['source_record_id','lat','lon','row_index','road_endpoint_accepted']
    x=context.merge(roster[columns].rename(columns={'lat':'model_lat','lon':'model_lon'}),
                    on='source_record_id',how='left',validate='one_to_one',suffixes=('','_roster'))
    selected=links[links.evidence_scenario.eq('all_dated_known')]
    if selected.duplicated(['origin_id','family']).any():raise ValueError('Repeated preferred functional outcome')
    differences=[]
    for family in ['school','medical_basic','grocery']:
        q=selected[selected.family.eq(family)].set_index('origin_id')
        if set(q.index)!=set(x.source_record_id):raise ValueError('Function does not cover the full axis: '+family)
        x[family+'_known_local_supply_preferred']=x.source_record_id.map(q.known_local_supply).eq(True)
        old=x[family+'_known_local_presence'].eq(True)
        for r in x[old.ne(x[family+'_known_local_supply_preferred'])].itertuples(index=False):
            differences.append({'source_record_id':r.source_record_id,'name':r.name,'family':family,
                'context_local_presence_flag':bool(getattr(r,family+'_known_local_presence')==True),
                'preferred_functional_local_supply_flag':bool(getattr(r,family+'_known_local_supply_preferred')),
                'resolution':'use_preferred_functional_links_for_current_function_observability; preserve_context'})
    d=documented_members[documented_members.membership_basis.astype(str).str.startswith('documented_')]
    if not set(d.source_record_id)<=set(x.source_record_id):raise ValueError('Document sample outside oblast')
    x['in_documented_control_sample']=x.source_record_id.isin(d.source_record_id)
    x['rural_size_quartile_2021']='not_rural_positive_population'
    rural=x.settlement_class.eq('rural')&x.population_2021.gt(0)
    bins=pd.qcut(x.loc[rural,'population_2021'],4,duplicates='drop')
    for rank,interval in enumerate(bins.cat.categories,1):
        ids=bins.index[bins.eq(interval)];lo=x.loc[ids,'population_2021'].min();hi=x.loc[ids,'population_2021'].max()
        x.loc[ids,'rural_size_quartile_2021']=f'Q{rank}: {lo:g}–{hi:g}'
    x['size_quartiles_are_centre_levels_or_suburb_boundaries']=False
    x['settlement_class_scope']='mapping_of_published_2021_NP_type_not_measured_urban_lifestyle'
    return x,pd.DataFrame(differences,columns=['source_record_id','name','family','context_local_presence_flag','preferred_functional_local_supply_flag','resolution'])


def summarize_groups(x):
    rows=[]
    for label,g in [('whole_oblast',x),('documented_control_sample',x[x.in_documented_control_sample])]:
        rows.append({'dimension':'sample','group':label,**group_summary(g)})
    for dimension in ['settlement_class','rural_size_quartile_2021']:
        for label,g in x.groupby(dimension,dropna=False,sort=True):
            rows.append({'dimension':dimension,'group':str(label),**group_summary(g)})
    return pd.DataFrame(rows)


def municipal_comparison(x,agriculture,workforce):
    a=agriculture.copy();a['municipality_code']=a.municipality_code.astype('string')
    unique(a,'municipality_code','agriculture')
    out=[]
    for code,g in x[x.agri_municipality_code.notna()].groupby('agri_municipality_code',sort=True):
        rural=g[g.settlement_class.eq('rural')]
        out.append({'municipality_code':str(code),'assigned_np_records':len(g),
            'assigned_rural_np_records':len(rural),
            **{'rural_'+k:v for k,v in group_summary(rural).items()}})
    t=a.merge(pd.DataFrame(out),on='municipality_code',how='left',validate='one_to_one')
    w=workforce.copy();w['municipality_code']=w.municipality_code.astype('string')
    w=w[w.year.eq(2025)]
    unique(w,'municipality_code','2025 municipal workforce')
    t=t.merge(w,on='municipality_code',how='left',validate='one_to_one',suffixes=('','_workforce'))
    for component in ['grain_sown','feed_sown']:
        numerator=t[f'agri_{component}_ha_2021_municipal_context']
        denominator=t.agri_sown_area_ha_2021_municipal_context
        ratio=numerator/denominator.where(denominator.gt(0))
        t[component+'_share_of_sown_2021']=ratio
        t[component+'_share_outside_unit_interval']=ratio.notna()&~ratio.between(0,1)
    t['agriculture_or_sector_workers_allocated_to_NP']=False
    t['observed_rural_population_change_is_explained_causally']=False
    return t


def transport_associations(x,costs):
    rows=[]
    if costs is None:return x,pd.DataFrame(columns=['group','pairwise_cases','spearman_rank_correlation'])
    c=np.load(costs,mmap_mode='r')
    if c.shape!=(len(x),len(x)):raise ValueError('Regional costs do not match complete NP axes')
    for city in ['Саратов','Энгельс']:
        target=x[x.name.eq(city)&x.settlement_type_2021.eq('город')]
        if len(target)!=1:raise ValueError('Unique city endpoint required: '+city)
        j=int(target.iloc[0].row_index)
        values=np.array(c[x.row_index.to_numpy(dtype=int),j],dtype=float)
        x['archived_minutes_to_'+city]=np.where(np.isfinite(values),values,np.nan)
    x['archived_minutes_to_nearer_saratov_engels']=x[['archived_minutes_to_Саратов','archived_minutes_to_Энгельс']].min(axis=1,skipna=True)
    for label,g in [('whole_oblast',x),('rural_published_type',x[x.settlement_class.eq('rural')])]:
        q=g[['archived_minutes_to_nearer_saratov_engels','annualized_population_change_percent_2002_2021_strict','population_2002']].dropna()
        finite=np.isfinite(q).all(axis=1);q=q[finite]
        rho=float(q.iloc[:,0].rank().corr(q.iloc[:,1].rank())) if len(q)>2 else None
        partial=None
        if len(q)>3:
            ranked=q.rank().to_numpy(dtype=float)
            control=np.column_stack([np.ones(len(q)),ranked[:,2]])
            residual=ranked[:,:2]-control@np.linalg.lstsq(control,ranked[:,:2],rcond=None)[0]
            if np.std(residual[:,0])>0 and np.std(residual[:,1])>0:
                partial=float(np.corrcoef(residual.T)[0,1])
        rows.append({'group':label,'pairwise_cases':len(q),'spearman_rank_correlation':rho,
            'partial_spearman_controlling_population_2002':partial,
            'time_is_2021_model_not_observed_travel':True,
            'all_russian_only_transit_in_archived_costs_verified':False,
            'correlation_identifies_suburbs_or_causal_effects':False})
    return x,pd.DataFrame(rows)


def compare_population_and_known_workers(x,population_maxima,worker_fields):
    """Rank two different known-source fields at matching old kernel scales.

    Unknown workers do not become observed zero: only the pre-existing known
    subset potential is compared. No rank is interpreted as complete job
    centrality, worker productivity, a service centre or a settlement level.
    """
    pop=population_maxima[population_maxima.neighbour_count.eq(6)&population_maxima.include_self.eq(True)].copy()
    if not pop.common_population_surface.eq(True).all():raise ValueError('Population comparison needs the common own-inclusive field')
    key=['source_record_id','kernel','half_time_minutes']
    pop=pop.rename(columns={'half_time':'half_time_minutes','value':'population_potential_with_self'})
    if pop.duplicated(key).any() or worker_fields.duplicated(key).any():raise ValueError('Repeated field scenario')
    if not worker_fields.field_cost_scope.eq('full_unbounded_directed_car_graph').all() or worker_fields.route_cost_horizon_minutes.notna().any():
        raise ValueError('Worker scenarios are not the same unbounded-cost scope')
    cols=key+['known_partial_worker_potential_with_self','known_partial_worker_potential_external',
              'own_partial_worker_observation','own_worker_observation_known','field_status',
              'all_workplaces_or_all_workers_potential_upper','complete_workplace_capacity_known',
              'kernel_is_empirically_calibrated_to_work_trips','worker_source_year','road_source_year']
    t=worker_fields[cols].merge(pop[key+['population_potential_with_self']],on=key,how='left',validate='one_to_one')
    t=t.merge(x[['source_record_id','name','district','settlement_class','population_2021']],on='source_record_id',validate='many_to_one')
    summaries=[]
    for (kernel,half),g in t.groupby(['kernel','half_time_minutes'],sort=True):
        ok=g.population_potential_with_self.notna()&g.known_partial_worker_potential_with_self.notna()
        j=g.index[ok]
        t.loc[j,'population_potential_regional_rank']=g.loc[j,'population_potential_with_self'].rank(ascending=False,method='average')
        t.loc[j,'known_worker_subset_potential_regional_rank']=g.loc[j,'known_partial_worker_potential_with_self'].rank(ascending=False,method='average')
        a=t.loc[j,'population_potential_regional_rank'];b=t.loc[j,'known_worker_subset_potential_regional_rank']
        summaries.append({'kernel':kernel,'half_time_minutes':float(half),'paired_regional_records':len(j),
            'spearman_population_vs_known_worker_potential_ranks':float(a.corr(b)) if len(j)>2 else None,
            'comparison_is_complete_employment_or_service_hierarchy':False})
    t['known_worker_rank_advantage_over_population_rank']=t.population_potential_regional_rank-t.known_worker_subset_potential_regional_rank
    t['worker_field_is_known_subset_not_full_job_capacity']=True
    t['field_difference_establishes_functional_centre_or_commuting']=False
    return t,pd.DataFrame(summaries)


def describe_population_basins(x,membership):
    """Vectorised description of conditional field basins, not proof of systems."""
    key=['scenario_id','basin_id']
    if membership.duplicated(['scenario_id','source_record_id']).any():
        raise ValueError('Population basin table repeats an origin in one scenario')
    chosen=membership[membership.status.eq('resolved_regional_peak')&membership.assignment_unique.eq(True)&membership.core_id.notna()].copy()
    columns=['source_record_id','population_2002','population_2021','population_eligible_2002_strict',
             'population_eligible_2021_strict','partial_organisation_workforce_2025',
             'partial_workforce_status','settlement_class','agri_municipality_code']+[f+'_known_local_supply_preferred' for f in ['school','medical_basic','grocery']]
    keep=key+['source_record_id','core_id','kernel','half_time','neighbour_count','topology']
    z=chosen[keep].merge(x[columns],on='source_record_id',how='left',validate='many_to_one')
    if z.population_2021.isna().any():raise ValueError('Resolved basin origin outside the full context')
    z['_external']=z.source_record_id.ne(z.core_id)
    z['_rural_external']=z._external&z.settlement_class.eq('rural')
    cores=z.assign(_core=(~z._external).astype(int)).groupby(key)._core.sum()
    if not cores.eq(1).all():raise ValueError('Each resolved basin must contain exactly one core record')
    eligible=z.population_eligible_2002_strict.eq(True)&z.population_eligible_2021_strict.eq(True)
    numeric=z.partial_organisation_workforce_2025.notna()
    z['_paired']=eligible.astype(int);z['_workers_numeric']=numeric.astype(int)
    z['_workers_suppressed']=z.partial_workforce_status.eq('source_suppressed').astype(int)
    z['_workers_unknown']=(~numeric&~z.partial_workforce_status.eq('source_suppressed')).astype(int)
    z['_paired_population_2002']=z.population_2002.where(eligible)
    z['_paired_population_2021']=z.population_2021.where(eligible)
    z['_population_with_numeric_workers']=z.population_2021.where(numeric,0)
    for family in ['school','medical_basic','grocery']:
        z['_'+family+'_known']=z[family+'_known_local_supply_preferred'].eq(True).astype(int)
    metadata=z.groupby(key,sort=True).agg(kernel=('kernel','first'),half_time=('half_time','first'),
        neighbour_count=('neighbour_count','first'),topology=('topology','first'),core_id=('core_id','first'))
    components=[]
    sums=['population_2021','_paired','_paired_population_2002','_paired_population_2021',
          'partial_organisation_workforce_2025','_workers_numeric','_workers_suppressed','_workers_unknown',
          '_population_with_numeric_workers','_school_known','_medical_basic_known','_grocery_known']
    for component,mask in [('all_members',pd.Series(True,index=z.index)),('core',~z._external),
                           ('external',z._external),('rural_external',z._rural_external)]:
        g=z[mask].groupby(key,sort=True)
        q=g[sums].sum(min_count=1).reindex(metadata.index)
        q['records']=g.size().reindex(metadata.index,fill_value=0)
        q['distinct_municipal_contexts']=g.agri_municipality_code.nunique().reindex(metadata.index,fill_value=0)
        for col in ['_paired','_workers_numeric','_workers_suppressed','_workers_unknown','_school_known','_medical_basic_known','_grocery_known']:
            q[col]=q[col].fillna(0).astype(int)
        q['component']=component
        q['paired_population_complete']=q.records.gt(0)&q._paired.eq(q.records)
        if component=='rural_external':
            unknown=z[z._external&~z.settlement_class.isin(['urban','rural'])].groupby(key).size().reindex(metadata.index,fill_value=0)
            q['paired_population_complete']=q.paired_population_complete&unknown.eq(0)
        q['reported_direction_2002_2021']=np.select([
            q.paired_population_complete&q._paired_population_2021.gt(q._paired_population_2002),
            q.paired_population_complete&q._paired_population_2021.lt(q._paired_population_2002),
            q.paired_population_complete&q._paired_population_2021.eq(q._paired_population_2002)],
            ['growth','decline','unchanged'],default='unknown')
        q['paired_known_subset_population_change_percent']=100*(q._paired_population_2021/q._paired_population_2002.where(q._paired_population_2002.gt(0))-1)
        q['full_component_population_change_percent']=q.paired_known_subset_population_change_percent.where(q.paired_population_complete)
        q['worker_host_population_coverage_share']=q._population_with_numeric_workers/q.population_2021.where(q.population_2021.gt(0))
        q=q.rename(columns={'_paired':'paired_numeric_records','_paired_population_2002':'paired_known_population_2002',
            '_paired_population_2021':'paired_known_population_2021','partial_organisation_workforce_2025':'known_subset_partial_workers_2025',
            '_workers_numeric':'numeric_worker_records','_workers_suppressed':'source_suppressed_worker_records',
            '_workers_unknown':'unknown_worker_records','_population_with_numeric_workers':'population_at_numeric_worker_records',
            '_school_known':'school_known_local_records','_medical_basic_known':'medical_basic_known_local_records','_grocery_known':'grocery_known_local_records'})
        components.append(q.reset_index())
    out=pd.concat(components,ignore_index=True).merge(metadata.reset_index(),on=key,validate='many_to_one')
    out['proves_functional_settlement_system']=False
    out['historic_boundary_equivalence_established']=False
    out['municipal_output_or_full_employment_allocated']=False
    p=out.pivot(index=key,columns='component',values='reported_direction_2002_2021')
    profile=metadata.reset_index()
    profile['core_rural_reported_record_pair_type']=[
        p.loc[(r.scenario_id,r.basin_id),'core']+'__'+p.loc[(r.scenario_id,r.basin_id),'rural_external']
        if 'unknown' not in [p.loc[(r.scenario_id,r.basin_id),'core'],p.loc[(r.scenario_id,r.basin_id),'rural_external']] else 'unknown'
        for r in profile.itertuples(index=False)]
    profile['population_field_partition_not_validated_functional_system']=True
    return out,profile



def basin_temporal_sensitivity(context, membership, evidence_variant):
    """Describe fixed population-field compositions; do not infer historic systems."""
    key=['scenario_id','basin_id']
    unique(context,'source_record_id','temporal basin context')
    if membership.duplicated(['scenario_id','source_record_id']).any():raise ValueError('Repeated basin origin')
    chosen=membership[membership.status.eq('resolved_regional_peak')&membership.assignment_unique.eq(True)&membership.core_id.notna()]
    cols=['source_record_id','settlement_class']+[f'population_{y}' for y in [2002,2010,2021]]+[f'population_eligible_{y}_{m}' for y in [2002,2010,2021] for m in ['accepted','strict']]
    z=chosen[key+['source_record_id','core_id']].merge(context[cols],on='source_record_id',validate='many_to_one')
    z['_external']=z.source_record_id.ne(z.core_id)
    if not z.assign(_core=(~z._external).astype(int)).groupby(key)._core.sum().eq(1).all():raise ValueError('Missing unique basin core')
    index=z.groupby(key).size().index
    unknown=z[z._external&~z.settlement_class.isin(['urban','rural'])].groupby(key).size().reindex(index,fill_value=0)
    rows=[]
    for label,mask in [('all_members',pd.Series(True,index=z.index)),('core',~z._external),('external',z._external),('rural_external',z._external&z.settlement_class.eq('rural')),('urban_external',z._external&z.settlement_class.eq('urban')),('unknown_type_external',z._external&~z.settlement_class.isin(['urban','rural']))]:
        q=z[mask].copy();n=q.groupby(key).size().reindex(index,fill_value=0)
        for mode in ['accepted','strict']:
            for start,end in [(2002,2010),(2010,2021),(2002,2021)]:
                eligible=q[f'population_eligible_{start}_{mode}'].eq(True)&q[f'population_eligible_{end}_{mode}'].eq(True)&q[f'population_{start}'].notna()&q[f'population_{end}'].notna()
                g=q[eligible].groupby(key)
                paired=g.size().reindex(index,fill_value=0)
                a=g[f'population_{start}'].sum(min_count=1).reindex(index)
                b=g[f'population_{end}'].sum(min_count=1).reindex(index)
                complete=n.gt(0)&paired.eq(n)
                if label=='rural_external':complete=complete&unknown.eq(0)
                direction=np.select([complete&b.gt(a),complete&b.lt(a),complete&b.eq(a)],['growth','decline','unchanged'],default='unknown')
                t=pd.DataFrame({'records':n,'paired_eligible_records':paired,'complete_component':complete,'paired_known_population_start':a,'paired_known_population_end':b,'reported_direction':direction,'unknown_type_external_records':unknown}).reset_index()
                t['component']=label;t['start_year']=start;t['end_year']=end;t['evidence_mode']=mode;t['population_evidence_variant']=evidence_variant
                t['paired_known_subset_change_percent']=100*(t.paired_known_population_end/t.paired_known_population_start.where(t.paired_known_population_start.gt(0))-1)
                t['full_component_change_percent']=t.paired_known_subset_change_percent.where(t.complete_component)
                t['historical_boundaries_reconstructed']=False;t['population_scope_comparability_verified']=False;t['proves_functional_system']=False
                rows.append(t)
    components=pd.concat(rows,ignore_index=True)
    p=components.pivot(index=key+['population_evidence_variant','evidence_mode','start_year','end_year'],columns='component',values='reported_direction').reset_index()
    p['joint_core_rural_reported_type']=np.where(p.core.ne('unknown')&p.rural_external.ne('unknown'),p.core+'__'+p.rural_external,'unknown')
    return components,p


def run_basin_only(input_root, membership_path, output, baseline_np_path):
    """Refresh only basin descriptions, with a separately labelled 2010 overlay."""
    root,output=Path(input_root),Path(output);output.mkdir(parents=True,exist_ok=True)
    membership=pd.read_parquet(membership_path)
    x=pd.read_parquet(baseline_np_path)
    if membership.scenario_id.nunique()!=18:raise ValueError('Expected the eighteen full-radius scenarios')
    if 'comparison_rule' in membership and not membership.comparison_rule.eq('full_radius').all():raise ValueError('Unexpected comparison rule')
    components,profiles=describe_population_basins(x,membership)
    tables={'population_basin_explanatory_components':components,'population_basin_explanatory_profiles':profiles}
    coverage=membership[['scenario_id','source_record_id','status']].merge(x[['source_record_id','settlement_class','population_2021']],on='source_record_id',validate='many_to_one')
    coverage['positive_population_record']=coverage.population_2021.gt(0).astype(int)
    coverage['published_zero_record']=coverage.population_2021.eq(0).astype(int)
    tables['population_basin_assignment_coverage']=coverage.groupby(['scenario_id','status','settlement_class'],dropna=False).agg(records=('source_record_id','size'),population_2021=('population_2021','sum'),positive_population_records=('positive_population_record','sum'),published_zero_records=('published_zero_record','sum')).reset_index()
    c=[];p=[]
    for variant,folder in [('foundation','context_physical_official'),('primary2010_separate_overlay','context_physical_official_primary2010')]:
        ctx=pd.read_parquet(root/folder/'np_context.parquet')
        if set(ctx.source_record_id)!=set(x.source_record_id):raise ValueError('Temporal context differs from full oblast roster')
        a,b=basin_temporal_sensitivity(ctx,membership,variant);c.append(a);p.append(b)
    tables['population_basin_temporal_components']=pd.concat(c,ignore_index=True)
    tables['population_basin_temporal_profiles']=pd.concat(p,ignore_index=True)
    key=['scenario_id','basin_id','evidence_mode','start_year','end_year']
    compare=p[0][key+['joint_core_rural_reported_type']].merge(p[1][key+['joint_core_rural_reported_type']],on=key,validate='one_to_one',suffixes=('_foundation','_primary2010'))
    compare['both_joint_types_complete']=compare.joint_core_rural_reported_type_foundation.ne('unknown')&compare.joint_core_rural_reported_type_primary2010.ne('unknown')
    compare['comparable_joint_type_changed']=compare.both_joint_types_complete&compare.joint_core_rural_reported_type_foundation.ne(compare.joint_core_rural_reported_type_primary2010)
    compare['evidence_or_type_status_changed']=compare.joint_core_rural_reported_type_foundation.ne(compare.joint_core_rural_reported_type_primary2010)
    compare['scope_comparability_verified']=False
    tables['population_basin_primary2010_comparison']=compare
    trajectory_key=['scenario_id','basin_id','population_evidence_variant','evidence_mode']
    temporal=tables['population_basin_temporal_profiles']
    trajectories=temporal[temporal.start_year.eq(2002)&temporal.end_year.eq(2010)].drop(columns=['start_year','end_year']).merge(
        temporal[temporal.start_year.eq(2010)&temporal.end_year.eq(2021)].drop(columns=['start_year','end_year']),on=trajectory_key,validate='one_to_one',suffixes=('_2002_2010','_2010_2021'))
    for component in ['all_members','core','external','rural_external','urban_external','unknown_type_external']:
        a=trajectories[component+'_2002_2010'];b=trajectories[component+'_2010_2021']
        trajectories[component+'_trajectory']=np.where(a.ne('unknown')&b.ne('unknown'),a+'__'+b,'unknown')
    trajectories['historic_compositions_and_scope_verified']=False
    tables['population_basin_three_census_trajectories']=trajectories
    summary={'regional_records':len(x),'scenarios':membership.scenario_id.nunique(),'conditional_basin_profiles':len(profiles),'historical_boundaries_reconstructed':False,'proves_functional_systems':False,'population_evidence_variants':['foundation','primary2010_separate_overlay'],'temporal_status_comparisons':[]}
    for (mode,start,end),g in compare.groupby(['evidence_mode','start_year','end_year']):
        summary['temporal_status_comparisons'].append({'mode':mode,'start_year':int(start),'end_year':int(end),'conditional_basins':len(g),'both_complete':int(g.both_joint_types_complete.sum()),'type_changed_among_both_complete':int(g.comparable_joint_type_changed.sum()),'evidence_or_type_status_changed':int(g.evidence_or_type_status_changed.sum())})
    for name,t in tables.items():t.to_parquet(output/(name+'.parquet'),index=False,compression='zstd');t.to_csv(output/(name+'.csv'),index=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def run(input_root,documented_members,output,regional_costs=None,basin_membership=None):
    root,output=Path(input_root),Path(output);output.mkdir(parents=True,exist_ok=True)
    context=pd.read_parquet(root/'context_physical_official/np_context.parquet')
    roster=pd.read_parquet(root/'fields/regional_roster.parquet')
    links=pd.read_parquet(root/'physical_official/functional_links.parquet')
    members=pd.read_parquet(documented_members)
    x,differences=build_np(context,roster,links,members)
    x,transport=transport_associations(x,regional_costs)
    groups=summarize_groups(x)
    municipalities=municipal_comparison(x,pd.read_parquet(root/'context_physical_official/municipal_agriculture_context.parquet'),pd.read_parquet(root/'context_physical_official/municipal_workforce_summary.parquet'))
    worker=root/'context/known_partial_worker_fields.parquet'
    if worker.exists():
        field_comparison,field_summary=compare_population_and_known_workers(x,pd.read_parquet(root/'organisation/point_maxima.parquet'),pd.read_parquet(worker))
    else:
        field_comparison=pd.DataFrame();field_summary=pd.DataFrame()
    if basin_membership is not None:
        basin_components,basin_profiles=describe_population_basins(x,pd.read_parquet(basin_membership))
    else:
        basin_components=pd.DataFrame();basin_profiles=pd.DataFrame()
    frames={'population_basin_explanatory_components':basin_components,'population_basin_explanatory_profiles':basin_profiles,'population_worker_field_comparison':field_comparison,'population_worker_field_summary':field_summary,'np_explanation':x,'regional_group_comparisons':groups,'municipal_context_comparison':municipalities,
            'context_function_flag_disagreements':differences,'transport_associations':transport}
    for name,f in frames.items():
        f.to_parquet(output/(name+'.parquet'),index=False,compression='zstd')
        if name!='np_explanation':f.to_csv(output/(name+'.csv'),index=False)
    allrow=groups[(groups.dimension.eq('sample'))&groups.group.eq('whole_oblast')].iloc[0]
    docrow=groups[(groups.dimension.eq('sample'))&groups.group.eq('documented_control_sample')].iloc[0]
    report={'schema':'sgrt.saratov.regional_explanation.v1','regional_records':len(x),
        'regional_population_2021':float(allrow.known_population_2021),
        'documented_control_records':int(docrow.records),'documented_control_population_2021':float(docrow.known_population_2021),
        'documented_control_population_share':float(docrow.known_population_2021/allrow.known_population_2021),
        'documented_control_urban_source_records':int(x[x.in_documented_control_sample].settlement_class.eq('urban').sum()),
        'regional_positive_change_record_pairs':int(allrow.positive_change_record_pairs),
        'documented_control_positive_change_record_pairs':int(docrow.positive_change_record_pairs),
        'numeric_worker_np_coverage_share':float(allrow.worker_np_coverage_share),
        'worker_host_record_population_coverage_share':float(allrow.worker_population_coverage_share),
        'context_vs_preferred_function_disagreements':differences.groupby('family').size().to_dict(),
        'conditional_population_basin_profiles':len(basin_profiles),'conditional_basins_are_validated_functional_systems':False,'municipal_rows':len(municipalities),'np_with_agriculture_context_key':int(x.agri_municipality_code.notna().sum()),'matching_population_worker_field_scenarios':len(field_summary),'transport_associations_calculated':regional_costs is not None,
        'original_population_or_context_overwritten':False,
        'literature_basis':['ZUBAREVICH2011_FOUR_RUSSIAS','CLASSIC_C02','CLASSIC_C01'],
        'interpretation_limits':['The document sample is a selected rural service-control cohort, not the population from which an oblast settlement-system typology can be inferred.',
          'Partial organisation workers are not resident employed people or complete jobs; their host-NP population coverage is not worker coverage.',
          'Municipal output and sector statistics stay municipal; associations do not allocate them to villages or establish causality.',
          'Published NP type, numerical population size, transport position and functional system rank are distinct.',
          'Matched reported record values do not prove unchanged historic boundaries.']}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--documented-members',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--regional-costs',type=Path);p.add_argument('--basin-membership',type=Path);a=p.parse_args()
    print(json.dumps(run(a.input_root,a.documented_members,a.output,a.regional_costs,a.basin_membership),ensure_ascii=False,indent=2))

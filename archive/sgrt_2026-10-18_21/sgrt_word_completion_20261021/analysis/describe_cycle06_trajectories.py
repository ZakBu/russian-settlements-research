"""Three demographic objects over all census periods; unknown is never a zero."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def run(model,output):
    if (output/'receipt.json').exists():raise FileExistsError('Use a new output directory')
    output.mkdir(parents=True,exist_ok=True)
    source=model/'systems.parquet';before=sha(source);d=pd.read_parquet(source)
    manifest_path=model/'output_manifest.json';manifest=json.loads(manifest_path.read_text())
    if manifest['files']['systems.parquet']['sha256']!=before:raise ValueError('Systems differ from completed model')
    nodes_path=model/'nodes.parquet'
    if sha(nodes_path)!=manifest['files']['nodes.parquet']['sha256']:raise ValueError('Nodes differ from completed model')
    source_nodes=pd.read_parquet(nodes_path,columns=['id','_population_axis_row'])
    additive=d.center_id.map(source_nodes.set_index('id')._population_axis_row).fillna(False)
    frames=[];coverage=[]
    for initial,final in [(2002,2010),(2010,2021),(2002,2021)]:
        for kind,prefix,completeness in [('center','center_population_',None),
                ('rural_surround','rural_external_population_known_sum_','rural_external_population_complete_'),
                ('whole_system','system_population_known_sum_','system_population_complete_')]:
            x=d[['level','center_id','name','region']].copy()
            a=pd.to_numeric(d[prefix+str(initial)],errors='coerce');b=pd.to_numeric(d[prefix+str(final)],errors='coerce')
            complete=a.notna()&b.notna()
            if completeness:complete &= d[completeness+str(initial)].fillna(False)&d[completeness+str(final)].fillna(False)
            if kind=='rural_surround':complete &= d.rural_role_complete.fillna(False)
            source_cohort_complete=complete.copy()
            if kind=='whole_system':complete &= additive & d['center_population_'+str(initial)].notna() & d['center_population_'+str(final)].notna()
            valid=complete&a.gt(0)
            # Extinction is an observed -100% change/-100% annual rate, while a
            # zero starting denominator has no defined percentage growth rate.
            rate=(b/a).pow(1/(final-initial))-1
            x['center_is_additive_source_member']=additive
            x['source_member_cohort_numeric_complete_pair']=source_cohort_complete
            x['population_sum_scope']='rural_surround' if kind=='rural_surround' else 'own_center' if kind=='center' else 'additive_source_member_cohort'
            x['whole_including_center_complete_pair']=complete if kind=='whole_system' else pd.NA
            x['initial_year']=initial;x['final_year']=final;x['population_object']=kind
            x['population_initial_known_sum']=a;x['population_final_known_sum']=b
            x['numeric_complete_pair']=complete;x['initial_zero_with_complete_pair']=complete&a.eq(0)
            x['percentage_change_defined']=valid;x['population_absolute_change']=(b-a).where(complete)
            x['population_change_percent']=((b/a-1)*100).where(valid)
            x['population_annual_rate']=rate.where(valid)
            x['population_ratio']= (b/a).where(valid)
            x['trajectory_class']=pd.Series(pd.NA,index=x.index,dtype='string')
            x.loc[valid,'trajectory_class']=np.select([rate[valid].lt(-.0025),rate[valid].gt(.0025)],['decline','growth'],default='stable')
            x['stability_annual_epsilon']=.0025
            x['primary_exact_system_pair']=d['system_population_exact_primary_supported_'+str(initial)]&d['system_population_exact_primary_supported_'+str(final)]
            x['historical_boundary_equivalence_proven']=False
            x['not_independent_causal_or_forecast_validation']=True
            for level,q in x.groupby('level'):
                coverage.append({'level':int(level),'initial_year':initial,'final_year':final,'population_object':kind,'all_systems':len(q),'numeric_complete_pairs':int(q.numeric_complete_pair.sum()),'percentage_change_defined':int(q.percentage_change_defined.sum()),'zero_initial_complete_pairs':int(q.initial_zero_with_complete_pair.sum()),'growth':int(q.trajectory_class.eq('growth').sum()),'stable':int(q.trajectory_class.eq('stable').sum()),'decline':int(q.trajectory_class.eq('decline').sum()),'median_annual_rate':float(q.population_annual_rate.median()) if q.population_annual_rate.notna().any() else None})
            frames.append(x)
    result=pd.concat(frames,ignore_index=True)
    result.to_parquet(output/'all_system_center_rural_census_trajectories.parquet',index=False)
    pd.DataFrame(coverage).to_csv(output/'trajectory_coverage.csv',index=False)
    if sha(source)!=before:raise RuntimeError('Input changed during trajectory calculation')
    receipt={'status':'COMPUTED_PENDING_INDEPENDENT_REVIEW','model_output':str(model),'systems_sha256':before,'model_output_manifest_sha256':sha(manifest_path),'nodes_sha256':sha(nodes_path),'external_core_whole_including_center_unknown_not_imputed':True,'code_sha256':sha(Path(__file__)),'trajectory_rows':len(result),'periods':[[2002,2010],[2010,2021],[2002,2021]],'objects':['center','rural_surround','whole_system'],'missing_population_and_role_propagated':True,'zero_initial_percentage_undefined':True,'known_zeros_retained':True,'stability_epsilon_scenario':.0025,'primary_exactness_is_system_scope_not_historical_geometry_validation':True,'outputs':{p.name:sha(p) for p in output.iterdir() if p.is_file()}}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'rows':len(result),'coverage_rows':len(coverage)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.model_output,a.output)

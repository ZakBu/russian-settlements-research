"""Describe accepted coordinate claims without equating admission with calibration."""
from collections import Counter
import pandas as pd
import duckdb

def build(state,ordinary,POINTS,joint,componentpoints,full,point,OUT):
    fields=['point_origin_kind','coordinate_quality','application_inference_kind']
    con=duckdb.connect(config={'threads':1,'memory_limit':'512MB'})
    frame=con.execute('SELECT target_source_record_id,'+','.join(fields)+' FROM read_parquet(?)',[str(POINTS)]).fetchdf()
    raw={r['target_source_record_id']:r for r in frame.to_dict('records')}
    counts=Counter()
    for sid in ordinary.source_record_id:
        if sid not in point: continue
        r=state.point_rows[sid]
        q=raw[sid] if r['point_ledger_path']==str(POINTS) else r
        y=int(state.by_id.loc[sid,'census_year'])
        for f in fields:
            v=q.get(f)
            label='not_recorded' if v is None or pd.isna(v) or str(v)=='' else str(v)
            counts[(y,f,label)]+=1
    rows=[{'year':y,'claim_field':f,'claimed_value':v,'accepted_point_rows':n} for (y,f,v),n in sorted(counts.items())]
    pd.DataFrame(rows).to_csv(OUT/'coordinate_origin_claimed_quality_counts.csv',index=False)
    partial=ordinary[ordinary.source_record_id.isin(joint-componentpoints)].copy()
    byroot={r:g for r,g in state.obs[state.obs.source_record_id.isin(full)].groupby('root')}
    partial['component_missing_own_point_years']=partial.root.map(lambda root:','.join(str(int(r.census_year)) for r in byroot[root].itertuples() if r.source_record_id not in point))
    partial[['source_record_id','census_year','settlement_name','region_norm','population','component_missing_own_point_years']].to_csv(OUT/'own_point_full3_components_missing_other_year_points.csv',index=False)
    residual=[]
    for y,g in ordinary.groupby('census_year'):
        for name,ids in [('missing_own_point_and_missing_full3',set(g.source_record_id)-point-full),('missing_own_point_but_full3',(set(g.source_record_id)&full)-point),('own_point_but_missing_full3',(set(g.source_record_id)&point)-full)]:
            take=g[g.source_record_id.isin(ids)]
            residual.append({'year':int(y),'reason_axis':name,'rows':len(take),'source_population':int(take.population.sum()),'unknown_population_rows':int(take.population.isna().sum())})
    pd.DataFrame(residual).to_csv(OUT/'strict_joint_residual_reason_axes.csv',index=False)
    return {'counts':rows,'calibration_asserted':False,'admission_status_means':'Reviewed point-use claim, with the recorded provider/origin and inference limitations; origin and claimed quality are not accuracy validation.','own_point_full3_but_other_year_point_missing':{'rows':len(partial),'components':partial.root.nunique(),'by_year':{int(y):{'rows':len(g),'population':int(g.population.sum())} for y,g in partial.groupby('census_year')}},'strict_joint_residual_reason_axes':residual}

"""Descriptive distance gradients inside fixed document-level catchments."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

R=Path(__file__).resolve().parent
AXIS=R.parent/'anchor_research_20261019/data/point_axis.parquet'
OLD=R.parent/'anchor_research_20261019/model/documented_graph/service_edges_calculated.csv'

def run():
    p=pd.read_parquet(AXIS).set_index('id')
    f=R/'model/results/canonical_documented_external_memberships.csv';d=pd.read_csv(f)
    old=pd.read_csv(OLD);bad=set(old.loc[old.geometry_status.eq('coordinate_conflict_quarantined'),'origin_uid'].dropna())
    out=R/'gradients';out.mkdir(exist_ok=True);rows=[];detail=[]
    keys=['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level']
    for key,g in d.groupby(keys,dropna=False):
        g=g.drop_duplicates('origin_uid');q=p.loc[key[2]];vals=[]
        for u in g.origin_uid:
            z=p.loc[u];status='coordinate_conflict_quarantined' if u in bad else 'eligible'
            v=[z.lat,z.lon,q.lat,q.lon,z.population_2010,z.population_2021]
            if not np.isfinite(v).all():status='missing_coordinate_or_population'
            lat1,lat2=np.deg2rad([z.lat,q.lat]);dl=np.deg2rad(z.lon-q.lon)
            h=np.sin((lat1-lat2)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin(dl/2)**2
            dist=float(6371.0088*2*np.arctan2(np.sqrt(np.clip(h,0,1)),np.sqrt(np.clip(1-h,0,1)))) if status=='eligible' else np.nan
            y=float(np.log1p(z.population_2021)-np.log1p(z.population_2010)) if status=='eligible' else np.nan
            detail.append(dict(zip(keys,key),origin_uid=u,origin_name=z['name'],center_name=q['name'],distance_km=dist,log1p_change_2010_2021=y,population_2010=z.population_2010,population_2021=z.population_2021,geometry_status=status))
            if status=='eligible':vals.append((dist,y))
        a=np.asarray(vals);estimate=len(a)>=5 and np.ptp(a[:,0])>1e-9
        slope=float(np.polyfit(a[:,0],a[:,1],1)[0]) if estimate else np.nan
        rho=float(spearmanr(a[:,0],a[:,1]).statistic) if estimate and np.ptp(a[:,1])>0 else np.nan
        rows.append(dict(zip(keys,key),center_name=q['name'],n_documented_origins=len(g),n_eligible=len(a),n_excluded=len(g)-len(a),minimum_n_for_descriptive_fit=5,fit_status='descriptive_only' if estimate else 'insufficient_observations_or_distance_variation',slope_log1p_change_per_km=slope,spearman=rho,p_value_computed=False,historical_membership_backcast=False))
    x=pd.DataFrame(rows);z=pd.DataFrame(detail)
    for n,t in [('distance_gradients',x),('gradient_points',z)]:t.to_csv(out/f'{n}.csv',index=False);t.to_parquet(out/f'{n}.parquet',index=False)
    checks={'all_canonical_edges_represented_once':len(z)==len(d),'quarantined_distance_not_used':bool(z.loc[z.origin_uid.isin(bad),'distance_km'].isna().all()),'zero_population_retained':int(z.population_2010.eq(0).sum())==int(p.loc[list(d.origin_uid),'population_2010'].eq(0).sum()),'all_groups_present':len(x)==len(d.groupby(keys,dropna=False)),'no_p_values':not x.p_value_computed.any(),'no_historical_backcast':not x.historical_membership_backcast.any(),'slopes_only_minimum5':bool(x.loc[x.n_eligible.lt(5),'slope_log1p_change_per_km'].isna().all())}
    audit={'status':'PASS' if all(checks.values()) else 'FAIL','groups':len(x),'descriptive_fits':int(x.fit_status.eq('descriptive_only').sum()),'source_memberships':len(d),'quarantined_uid_list':sorted(bad),'checks':checks,'inputs':{str(t.relative_to(R.parent)):hashlib.sha256(t.read_bytes()).hexdigest() for t in [AXIS,OLD,f]},'interpretation':'Unweighted descriptive log1p population-change gradient over direct distances inside fixed dated source memberships. Repeated years and source catchments are not independent. No measured historical service boundary, causal effect or universal slope.'}
    (out/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');assert all(checks.values());print(json.dumps({k:v for k,v in audit.items() if k not in ['inputs','quarantined_uid_list']},ensure_ascii=False))

if __name__=='__main__':run()

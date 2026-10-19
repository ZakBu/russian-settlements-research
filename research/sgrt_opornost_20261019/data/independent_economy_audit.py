"""Independent RFSD2021 readback; BallTree/haversine instead of author's xyz KDTree."""
from pathlib import Path
import argparse, hashlib, json, re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.neighbors import BallTree

R=6371.0088

def hdist(a,b):
    a,b=np.deg2rad(a),np.deg2rad(b)
    z=np.sin((a[:,0]-b[:,0])/2)**2+np.cos(a[:,0])*np.cos(b[:,0])*np.sin((a[:,1]-b[:,1])/2)**2
    return 2*R*np.arctan2(np.sqrt(np.clip(z,0,1)),np.sqrt(np.clip(1-z,0,1)))

def normalize_codes(series):
    # Width 8 denotes a municipality, so it cannot be promoted to a settlement.
    return series.astype('string').str.strip().map(lambda x: x.zfill(11) if pd.notna(x) and re.fullmatch('[0-9]{10,11}',x) else None)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();out=root/'data/statistics';out.mkdir(parents=True,exist_ok=True)
    panel=root/'data/point_axis.parquet'
    raw=root.parent/'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_2021_selected.parquet'
    author=root/'economy/coded_results/2021/points_economic_features.parquet'
    p=pd.read_parquet(panel);result=pd.read_parquet(author)
    code=normalize_codes(p.oktmo_2021);assert code.notna().all() and code.is_unique
    dictionary=dict(zip(code,p.index));coords=p[['lat','lon']].to_numpy();tree=BallTree(np.deg2rad(coords),metric='haversine')
    tests=[]
    def ck(name,ok,details=None):
        tests.append(dict(test=name,passed=bool(ok),details=details))
        if not ok:raise AssertionError((name,details))
    ck('code_width_unit_tests', normalize_codes(pd.Series(['12345678','1234567890','01234567890','bad',None])).tolist()==[None,'01234567890','01234567890',None,None])
    ck('leading_zero_dictionary_no_collisions',code.is_unique,{'10_digit_restored':int(p.oktmo_2021.astype(str).str.len().eq(10).sum())})
    inn=pq.read_table(raw,columns=['inn']).to_pandas().inn;goodinn=inn.notna()&inn.fillna('').str.strip().ne('')
    ck('all_nonmissing_INNs_unique',not inn[goodinn].duplicated().any(),{'rows':len(inn),'missing':int((~goodinn).sum())});del inn,goodinn
    sectors=list('ABCDEFGHIJKLMNOPQRSTU')+['UNKNOWN'];slookup={s:i for i,s in enumerate(sectors)}
    group_defs={'retail47':('G',['47']),'food56':('I',['56']),'accommodation55':('I',['55']),
        'education85':('P',['85']),'health86':('Q',['86']),'social8788':('Q',['87','88']),
        'repair95':('S',['95']),'personal96':('S',['96']),'finance64to66':('K',['64','65','66']),'admin84':('O',['84'])}
    integer_fields=['legal_entities','exact_code_entities','coordinate_fallback_entities','entities_unknown_coordinates','entities_coordinates_gt5km','entities_coordinates_gt50km','financial_eligible_reports']+[g+'_legal_entities' for g in group_defs]
    counts={mode:pd.DataFrame(0,index=p.index,columns=integer_fields,dtype=np.int64) for mode in ['coded_baseline','coded_strict_house_5km']}
    sec={mode:np.zeros((len(p),len(sectors)),dtype=np.int64) for mode in counts}
    revenue={mode:np.zeros(len(p)) for mode in counts};maximum={mode:np.zeros(len(p)) for mode in counts}
    balance=dict(total=0,missing_inn=0,federal=0,exact=0,fallback=0,unlinked=0,ambiguous_eligible_fallback=0)
    code_widths={};geo_samples=[]
    cols=['inn','oktmo','lat','lon','geocoding_quality','okved','okved_section','line_2110','eligible','filed','articulated','outlier','imputed']
    for batch in pq.ParquetFile(raw).iter_batches(columns=cols,batch_size=100000):
        d=batch.to_pandas();n=len(d);balance['total']+=n
        okinn=(d.inn.notna()&d.inn.fillna('').str.strip().ne('')).to_numpy();balance['missing_inn']+=int((~okinn).sum())
        cod=normalize_codes(d.oktmo);assigned=cod.map(dictionary).fillna(-1).astype(int).to_numpy()
        federal=cod.fillna('').str[:2].isin(['40','45']).to_numpy()&okinn;balance['federal']+=int(federal.sum())
        exact=(assigned>=0)&okinn&~federal;balance['exact']+=int(exact.sum())
        valid=(d.lat.between(-90,90)&d.lon.between(-180,180)).to_numpy();q=d.geocoding_quality.fillna('').to_numpy()
        attempt=(~exact)&(~federal)&okinn&valid&np.isin(q,['house','street'])
        fallback=np.zeros(n,dtype=bool);nearest=np.full(n,-1,dtype=int)
        if attempt.any():
            ds,ids=tree.query(np.deg2rad(d.loc[attempt,['lat','lon']].to_numpy()),k=2)
            ds*=R;fallback[attempt]=(ds[:,0]<=1)&(ds[:,1]-ds[:,0]>.25);nearest[attempt]=ids[:,0]
            balance['ambiguous_eligible_fallback']+=int(((ds[:,0]<=1)&(ds[:,1]-ds[:,0]<=.25)).sum())
            if len(geo_samples)<24:
                for j in range(min(3,len(ds))):geo_samples.append(dict(distance=ds[j,0],first=int(ids[j,0]),second_distance=ds[j,1],second=int(ids[j,1]),origin=d.loc[attempt,['lat','lon']].to_numpy()[j].tolist()))
        assigned=np.where(exact,assigned,np.where(fallback,nearest,-1));selected=exact|fallback
        balance['fallback']+=int(fallback.sum());balance['unlinked']+=int((~selected&okinn&~federal).sum())
        distance=np.full(n,np.inf);vv=selected&valid
        distance[vv]=hdist(d.loc[vv,['lat','lon']].to_numpy(),coords[assigned[vv]])
        ss=d.okved_section.map(slookup).fillna(len(sectors)-1).astype(int).to_numpy()
        pref=d.okved.fillna('').astype(str).str.extract(r'^(\d{2})',expand=False).fillna('').to_numpy()
        rev=d.line_2110.to_numpy();financial=(d.eligible.eq(1)&d.filed.eq(1)&d.articulated.eq(1)&d.outlier.eq(0)).to_numpy()&np.isfinite(rev)&(rev>=0)
        for mode in counts:
            mask=selected if mode=='coded_baseline' else selected&(q=='house')&(distance<=5)
            counts[mode]['legal_entities']+=np.bincount(assigned[mask],minlength=len(p))
            for col,sub in [('exact_code_entities',exact),('coordinate_fallback_entities',fallback),('entities_unknown_coordinates',~valid),('entities_coordinates_gt5km',valid&(distance>5)),('entities_coordinates_gt50km',valid&(distance>50))]:
                counts[mode][col]+=np.bincount(assigned[mask&sub],minlength=len(p))
            # Independent pandas groupby, not author's np.add.at.
            grouped=pd.DataFrame({'i':assigned[mask],'s':ss[mask]}).value_counts()
            if len(grouped):sec[mode][grouped.index.get_level_values(0),grouped.index.get_level_values(1)]+=grouped.to_numpy()
            for g,(s,pr) in group_defs.items():
                take=mask&(ss==slookup[s])&np.isin(pref,pr)
                counts[mode][g+'_legal_entities']+=np.bincount(assigned[take],minlength=len(p))
            fs=mask&financial
            if mode!='coded_baseline':fs&=d.imputed.eq(0).to_numpy()
            counts[mode]['financial_eligible_reports']+=np.bincount(assigned[fs],minlength=len(p))
            fg=pd.DataFrame({'i':assigned[fs],'r':rev[fs]}).groupby('i').r.agg(['sum','max'])
            revenue[mode][fg.index]+=fg['sum'].to_numpy();maximum[mode][fg.index]=np.maximum(maximum[mode][fg.index],fg['max'].to_numpy())
        for w,c in d.oktmo.astype('string').str.len().fillna(-1).value_counts().items():code_widths[str(w)]=code_widths.get(str(w),0)+int(c)
    ck('global_rows_exhaustive_balance',balance['total']==sum(balance[k] for k in ['missing_inn','federal','exact','fallback','unlinked']),balance)
    for mode,c in counts.items():
        z=result[result.quality_mode.eq(mode)].set_index('id').loc[p.id]
        ck(mode+'_full_unique_point_axis',len(z)==len(p) and z.index.is_unique)
        for col in integer_fields:
            ck(mode+'_'+col,np.array_equal(c[col].to_numpy(),z[col].to_numpy()),{'sum':int(c[col].sum())})
        ck(mode+'_revenue_sum_all_points',np.allclose(revenue[mode],z.known_nominal_revenue_thousand_rub,rtol=1e-12,atol=1e-6))
        maxshare=np.divide(maximum[mode],revenue[mode],out=np.full(len(p),np.nan),where=revenue[mode]>0)
        ck(mode+'_maximum_firm_share',np.allclose(maxshare,z.max_legal_entity_revenue_share,equal_nan=True,rtol=1e-12))
        for s in 'GIPQ':ck(mode+'_section_'+s,np.array_equal(sec[mode][:,slookup[s]],z['section_'+s+'_legal_entities']))
        ck(mode+'_unknown_section',np.array_equal(sec[mode][:,-1],z.unknown_section_legal_entities))
        known=sec[mode][:,:-1].sum(axis=1);shares=np.divide(sec[mode][:,:-1],known[:,None],out=np.zeros_like(sec[mode][:,:-1],dtype=float),where=known[:,None]>0)
        entropy=-(shares*np.log(np.where(shares>0,shares,1))).sum(axis=1)
        ck(mode+'_Shannon_all_points',np.allclose(entropy,z.section_shannon,rtol=0,atol=1e-12))
        ck(mode+'_section_diversity',np.array_equal((sec[mode][:,:-1]>0).sum(axis=1),z.section_diversity))
        ck(mode+'_broad_services',np.array_equal(sum(sec[mode][:,slookup[s]] for s in 'GIPQ'),z.broad_service_legal_entities))
        direct=['retail47','food56','education85','health86','social8788','repair95','personal96']
        ck(mode+'_consumer_services',np.array_equal(c[[g+'_legal_entities' for g in direct]].sum(axis=1),z.direct_consumer_service_legal_entities))
        ck(mode+'_consumer_diversity',np.array_equal(c[[g+'_legal_entities' for g in direct]].gt(0).sum(axis=1),z.direct_consumer_function_diversity))
    # Independently verify all-NP haversine nearest neighbors for deterministic samples.
    for i,s in enumerate(geo_samples):
        full=hdist(np.repeat(np.array([s['origin']]),len(coords),axis=0),coords);ix=np.argsort(full)[:2]
        ck('fallback_all_point_distance_sample_'+str(i),np.allclose(full[ix],[s['distance'],s['second_distance']],atol=1e-7,rtol=0))
    c1=counts['coded_baseline'];c2=counts['coded_strict_house_5km']
    ck('strict_subset_of_baseline_every_point',c2.le(c1).all().all())
    geo=pd.read_parquet(root/'economy/results/2021/points_economic_features.parquet')
    geometric=geo[geo.quality_mode.eq('baseline_house_street') & geo.max_distance_km.eq(1.0)] if 'max_distance_km' in geo else None
    summary=dict(status='PASS',checks_passed=len(tests),author='anchor_data; axis/linker author; independent of RFSD/GIS implementation',
        independent_method='pandas groupby/BallTree haversine/full-point sample checks; did not import author calculation code',balance=balance,code_widths=code_widths,
        baseline_legal_entities=int(c1.legal_entities.sum()),strict_legal_entities=int(c2.legal_entities.sum()),
        baseline_points_observed=int(c1.legal_entities.gt(0).sum()),strict_points_observed=int(c2.legal_entities.gt(0).sum()),
        final_readback_SHA256=hashlib.sha256(author.read_bytes()).hexdigest(),
        caveats=['2021 legal address not activity/job/client flow','8-digit municipality cannot identify point','2016 projected through 2021 dictionary not historical administrative crosswalk','strict rule is sensitivity not confidence interval'],checks=tests)
    (out/'independent_economy_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    pd.DataFrame(tests).to_csv(out/'independent_economy_checks.csv',index=False)
    print(json.dumps({k:v for k,v in summary.items() if k!='checks'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

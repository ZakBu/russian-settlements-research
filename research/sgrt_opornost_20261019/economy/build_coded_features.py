#!/usr/bin/env python3
"""Exact settlement OKTMO with independent coordinate cross-check; no basin input."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree
from build_point_features import COLS,GROUPS,SECTIONS,R,sha,xyz,dump

def codes(s):
    s=s.astype('string').str.strip()
    return s.where(s.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)

def run(root,out,year):
    out.mkdir(parents=True,exist_ok=True)
    panelpath=root/'research/sgrt_recovered_20261019/data/panel.parquet'
    source=root/f'inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet'
    pp=['id','name','type','region','lat','lon','population_2021','oktmo_2021']
    p=pq.read_table(panelpath,columns=pp).to_pandas();n=len(p);pc=codes(p.oktmo_2021)
    assert pc.notna().all() and pc.is_unique
    lookup=pd.Series(np.arange(n),index=pc)
    tree=cKDTree(xyz(p.lat.to_numpy(),p.lon.to_numpy()))
    sections=np.zeros((2,n,len(SECTIONS)),dtype=np.int64)
    groups=np.zeros((2,n,len(GROUPS)),dtype=np.int64)
    finances=np.zeros((2,n),dtype=np.int64);revenues=np.zeros((2,n));maxrev=np.zeros((2,n))
    accepted_code=np.zeros((2,n),dtype=np.int64);accepted_fallback=np.zeros((2,n),dtype=np.int64)
    coord_unknown=np.zeros((2,n),dtype=np.int64);coord_far5=np.zeros((2,n),dtype=np.int64);coord_far50=np.zeros((2,n),dtype=np.int64)
    rows=0;notaccepted=0;missinginn=0;exact_count=0;fallback_count=0
    classifypairs={'retail47':'G','food56':'I','accommodation55':'I','education85':'P',
      'health86':'Q','social8788':'Q','repair95':'S','personal96':'S','finance64to66':'K','admin84':'O'}
    lut={s:i for i,s in enumerate(SECTIONS)}
    pf=pq.ParquetFile(source)
    # Establish key uniqueness again, independent of geometric processing output.
    inns=pq.read_table(source,columns=['inn']).to_pandas().inn;validinn=inns.notna()&inns.fillna('').str.strip().ne('')
    assert not inns[validinn].duplicated().any();del inns,validinn
    for b in pf.iter_batches(batch_size=100000,columns=COLS+['oktmo']):
        d=b.to_pandas();rows+=len(d)
        goodinn=(d.inn.notna()&d.inn.fillna('').str.strip().ne('')).to_numpy();missinginn+=int((~goodinn).sum())
        coded=codes(d.oktmo).map(lookup).fillna(-1).astype(int).to_numpy()
        exact=(coded>=0)&goodinn;exact_count+=int(exact.sum())
        valid=(d.lat.between(-90,90)&d.lon.between(-180,180)).to_numpy()
        near=np.full(len(d),-1,dtype=int);nd=np.full(len(d),np.inf);gap=np.full(len(d),-1.)
        if valid.any():
            chord,ix=tree.query(xyz(d.lat.to_numpy()[valid],d.lon.to_numpy()[valid]),k=2,workers=2)
            dd=2*R*np.arcsin(np.clip(chord/2,0,1));near[valid]=ix[:,0];nd[valid]=dd[:,0];gap[valid]=dd[:,1]-dd[:,0]
        q=d.geocoding_quality.fillna('').to_numpy()
        fallback=(~exact)&goodinn&valid&np.isin(q,['house','street'])&(nd<=1)&(gap>.25)
        fallback_count+=int(fallback.sum());assigned=np.where(exact,coded,np.where(fallback,near,-1))
        selected=exact|fallback;notaccepted+=int((~selected&goodinn).sum())
        distance=np.full(len(d),np.inf)
        take=selected&valid
        if take.any():
            orig=xyz(d.lat.to_numpy()[take],d.lon.to_numpy()[take]);dest=xyz(p.lat.to_numpy()[assigned[take]],p.lon.to_numpy()[assigned[take]])
            distance[take]=2*R*np.arcsin(np.clip(np.linalg.norm(orig-dest,axis=1)/2,0,1))
        sec=d.okved_section.map(lut).fillna(len(SECTIONS)-1).astype(int).to_numpy()
        pref=d.okved.fillna('').astype(str).str.extract(r'^(\d{2})',expand=False).fillna('').to_numpy()
        rev=pd.to_numeric(d.line_2110,errors='coerce').to_numpy()
        f=(d.eligible.eq(1)&d.filed.eq(1)&d.articulated.eq(1)&d.outlier.eq(0)).to_numpy()&np.isfinite(rev)&(rev>=0)
        for qi in range(2):
            sel=selected if qi==0 else selected&(q=='house')&(distance<=5)
            np.add.at(sections[qi],(assigned[sel],sec[sel]),1)
            for gi,(label,ps) in enumerate(GROUPS.items()):
                t=sel&np.isin(pref,list(ps))&(sec==lut[classifypairs[label]])
                np.add.at(groups[qi,:,gi],assigned[t],1)
            fs=sel&f
            if qi==1:fs &= d.imputed.eq(0).to_numpy()
            np.add.at(finances[qi],assigned[fs],1);np.add.at(revenues[qi],assigned[fs],rev[fs]);np.maximum.at(maxrev[qi],assigned[fs],rev[fs])
            for arr,mask in [(accepted_code,exact),(accepted_fallback,fallback),(coord_unknown,~valid),(coord_far5,valid&(distance>5)),(coord_far50,valid&(distance>50))]:
                t=sel&mask;np.add.at(arr[qi],assigned[t],1)
    frames=[];coverage=[];checks=[]
    for qi,label in enumerate(['coded_baseline','coded_strict_house_5km']):
        df=p.drop(columns=['oktmo_2021']).copy();df['year']=year;df['quality_mode']=label
        c=sections[qi];df['legal_entities']=c.sum(axis=1);known=c[:,:-1].sum(axis=1)
        sh=np.divide(c[:,:-1],known[:,None],out=np.zeros_like(c[:,:-1],dtype=float),where=known[:,None]>0)
        df['section_shannon']=-(sh*np.log(np.where(sh>0,sh,1))).sum(axis=1)
        df['section_diversity']=(c[:,:-1]>0).sum(axis=1);df['unknown_section_legal_entities']=c[:,-1]
        for s in 'GIPQ':df['section_'+s+'_legal_entities']=c[:,lut[s]]
        df['broad_service_legal_entities']=sum(c[:,lut[s]] for s in 'GIPQ')
        for gi,g in enumerate(GROUPS):df[g+'_legal_entities']=groups[qi,:,gi]
        gs=['retail47','food56','education85','health86','social8788','repair95','personal96']
        df['direct_consumer_service_legal_entities']=sum(df[g+'_legal_entities'] for g in gs)
        df['direct_consumer_function_diversity']=sum(df[g+'_legal_entities'].gt(0).astype(int) for g in gs)
        df['financial_eligible_reports']=finances[qi];df['known_nominal_revenue_thousand_rub']=revenues[qi]
        df['max_legal_entity_revenue_share']=np.divide(maxrev[qi],revenues[qi],out=np.full(n,np.nan),where=revenues[qi]>0)
        for arr,name in [(accepted_code,'exact_code_entities'),(accepted_fallback,'coordinate_fallback_entities'),(coord_unknown,'entities_unknown_coordinates'),(coord_far5,'entities_coordinates_gt5km'),(coord_far50,'entities_coordinates_gt50km')]:df[name]=arr[qi]
        df['rfds_presence_status']=np.where(df.legal_entities>0,'observed_legal_address_presence','no_accepted_RFSD_witness_not_function_absence')
        frames.append(df)
        coverage.append({'year':year,'mode':label,'np_total':n,'entities':int(df.legal_entities.sum()),'np_with_entities':int(df.legal_entities.gt(0).sum()),
         'direct_service_entities':int(df.direct_consumer_service_legal_entities.sum()),'np_direct_service':int(df.direct_consumer_service_legal_entities.gt(0).sum()),
         'np_education85':int(df.education85_legal_entities.gt(0).sum()),'np_health86':int(df.health86_legal_entities.gt(0).sum()),
         'np_two_direct_functions':int(df.direct_consumer_function_diversity.ge(2).sum()),'np_three_direct_functions':int(df.direct_consumer_function_diversity.ge(3).sum()),
         'exact_code_entities':int(accepted_code[qi].sum()),'coordinate_fallback_entities':int(accepted_fallback[qi].sum()),
         'unknown_coordinates':int(coord_unknown[qi].sum()),'coordinates_gt5km':int(coord_far5[qi].sum()),'coordinates_gt50km':int(coord_far50[qi].sum())})
        checks.append({'check':label+'_link_balance','pass':int(df.legal_entities.sum())==int(accepted_code[qi].sum()+accepted_fallback[qi].sum())})
    df=pd.concat(frames,ignore_index=True);df.to_parquet(out/'points_economic_features.parquet',index=False);df.to_csv(out/'points_economic_features.csv.gz',index=False,compression='gzip')
    pd.testing.assert_frame_equal(df,pq.read_table(out/'points_economic_features.parquet').to_pandas())
    checks += [{'check':'strict_subset_all_sectors','pass':bool((sections[1]<=sections[0]).all())},
      {'check':'full_points_each_mode','pass':len(df)==2*n and not df.duplicated(['id','year','quality_mode']).any()},
      {'check':'source_rows_balance','pass':rows==exact_count+fallback_count+notaccepted+missinginn},
      {'check':'unique_normalized_settlement_codes','pass':bool(pc.is_unique)},
      {'check':'whole_table_readback','pass':True},{'check':'no_outcome_or_old_zones','pass':not any('zone' in c or 'growth' in c or 'basin' in c for c in pp)}]
    audit={'year':year,'rows':rows,'missing_inn':missinginn,'exact_code_matches':exact_count,'coordinate_fallback':fallback_count,'unlinked_valid_inn':notaccepted,'profiles':coverage,
      'source_sha256':sha(source),'panel_sha256':sha(panelpath),'code_sha256':sha(Path(__file__)),
      'code_reference_year':2021,'2016_historical_code_crosswalk_proven':False,'geography_inconsistency_retained_in_baseline':True}
    dump(out/'coverage.json',audit);dump(out/'checks.json',checks)
    assert all(x['pass'] for x in checks)
    print(json.dumps({'year':year,'checks':len(checks),'coverage':coverage},ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--restored',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--years',nargs='+',type=int,default=[2021,2016]);a=ap.parse_args()
    for y in a.years:run(a.restored,a.out/str(y),y)

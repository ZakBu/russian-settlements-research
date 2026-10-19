#!/usr/bin/env python3
"""RFSD legal-address features of observed settlements; no catchment input."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

R = 6371.0088
RADII = [0.5, 1.0, 2.0, 5.0]
SECTIONS = list('ABCDEFGHIJKLMNOPQRSTU') + ['UNKNOWN']
GROUPS = {'retail47': {'47'}, 'food56': {'56'}, 'accommodation55': {'55'},
          'education85': {'85'}, 'health86': {'86'}, 'social8788': {'87', '88'},
          'repair95': {'95'}, 'personal96': {'96'}, 'finance64to66': {'64','65','66'},
          'admin84': {'84'}}
COLS = ['inn','eligible','filed','articulated','imputed','outlier','line_2110',
        'okved','okved_section','lat','lon','geocoding_quality']

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def xyz(lat,lon):
    la=np.radians(lat);lo=np.radians(lon)
    return np.c_[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]

def dump(p,obj):
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def run(panel_path,source,year,out):
    start=time.time();out.mkdir(parents=True,exist_ok=True)
    pp=['id','name','type','region','lat','lon','population_2010','population_2021']
    points=pq.read_table(panel_path,columns=pp).to_pandas()
    assert points.id.is_unique and points[['lat','lon']].notna().all().all()
    n=len(points);tree=cKDTree(xyz(points.lat.to_numpy(),points.lon.to_numpy()))
    pf=pq.ParquetFile(source)
    assert set(COLS).issubset(pf.schema_arrow.names)
    dump(out/'schema.json',{'rows':pf.metadata.num_rows,'columns_read':COLS,'schema':str(pf.schema_arrow)})
    inns=pq.read_table(source,columns=['inn']).to_pandas().inn
    missing=inns.isna() | inns.fillna('').str.strip().eq('')
    ndups=int(inns[~missing].duplicated(keep=False).sum())
    assert ndups==0, f'Conflicting duplicate INNs: {ndups}'
    missing_inn=int(missing.sum());del inns,missing
    sec_counts=np.zeros((2,4,n,len(SECTIONS)),dtype=np.int32)
    grp_counts=np.zeros((2,4,n,len(GROUPS)),dtype=np.int32)
    fin_counts=np.zeros((2,4,n),dtype=np.int32)
    revenues=np.zeros((2,4,n),dtype=np.float64)
    maxrev=np.zeros((2,4,n),dtype=np.float64)
    cov={'year':year,'source_rows':pf.metadata.num_rows,'missing_inn':missing_inn,
         'duplicate_nonmissing_inn_rows':ndups,'quality_counts':{},'invalid_coordinate_or_inn':0,
         'valid_coordinates_and_inn':0,'nearest_distance_histogram':{},'ambiguity_within_025km':0}
    bal=np.zeros((2,4,4),dtype=np.int64) # accepted,ambiguous,outside,quality_rejected
    quality_names=['baseline_house_street','strict_house']
    sec_lut={x:i for i,x in enumerate(SECTIONS)}
    quality_counts={};hist=np.zeros(8,dtype=np.int64)
    for batch in pf.iter_batches(batch_size=100000,columns=COLS):
        d=batch.to_pandas();q=d.geocoding_quality.fillna('MISSING').astype(str)
        for k,v in q.value_counts().items():quality_counts[k]=quality_counts.get(k,0)+int(v)
        valid=(d.inn.notna() & d.inn.fillna('').str.strip().ne('') &
               d.lat.between(-90,90) & d.lon.between(-180,180))
        cov['invalid_coordinate_or_inn']+=int((~valid).sum());d=d.loc[valid].reset_index(drop=True)
        cov['valid_coordinates_and_inn']+=len(d)
        if not len(d):continue
        chord,ix=tree.query(xyz(d.lat.to_numpy(),d.lon.to_numpy()),k=2,workers=2)
        dist=2*R*np.arcsin(np.clip(chord/2,0,1));near=ix[:,0];amb=(dist[:,1]-dist[:,0])<=.25
        hist+=np.histogram(dist[:,0],bins=[0,.5,1,2,5,10,50,100,np.inf])[0]
        cov['ambiguity_within_025km']+=int(amb.sum())
        q=d.geocoding_quality.fillna('').astype(str).to_numpy()
        sec=d.okved_section.fillna('UNKNOWN').map(sec_lut).fillna(len(SECTIONS)-1).astype(int).to_numpy()
        # RFSD harmonises industry identifiers; require section correspondence for two-digit labels.
        prefix=d.okved.fillna('').astype(str).str.extract(r'^(\d{2})',expand=False).fillna('').to_numpy()
        rev=pd.to_numeric(d.line_2110,errors='coerce').to_numpy()
        eligible=(d.eligible.eq(1)&d.filed.eq(1)&d.articulated.eq(1)&d.outlier.eq(0)).to_numpy()
        eligible &= np.isfinite(rev)&(rev>=0)
        for qi,qname in enumerate(quality_names):
            goodq=np.isin(q,['house','street']) if qi==0 else q=='house'
            goodfin=eligible if qi==0 else eligible & d.imputed.eq(0).to_numpy()
            for ri,radius in enumerate(RADII):
                inside=dist[:,0]<=radius
                accept=goodq & inside & ~amb
                bal[qi,ri]+=[int(accept.sum()),int((goodq&inside&amb).sum()),
                             int((goodq&~inside).sum()),int((~goodq).sum())]
                np.add.at(sec_counts[qi,ri],(near[accept],sec[accept]),1)
                for gi,(label,prefs) in enumerate(GROUPS.items()):
                    take=accept & np.isin(prefix,list(prefs))
                    # Old OKVED1 codes must not masquerade as modern service groups.
                    expected={'retail47':'G','food56':'I','accommodation55':'I','education85':'P',
                              'health86':'Q','social8788':'Q','repair95':'S','personal96':'S',
                              'finance64to66':'K','admin84':'O'}[label]
                    take &= sec==sec_lut[expected]
                    np.add.at(grp_counts[qi,ri,:,gi],near[take],1)
                f=accept&goodfin
                np.add.at(fin_counts[qi,ri],near[f],1)
                np.add.at(revenues[qi,ri],near[f],rev[f])
                np.maximum.at(maxrev[qi,ri],near[f],rev[f])
    cov['quality_counts']=quality_counts
    cov['nearest_distance_histogram']=dict(zip(['0-.5','.5-1','1-2','2-5','5-10','10-50','50-100','100+'],map(int,hist)))
    checks=[];coverage_rows=[];mainframes=[];sectorframes=[]
    for qi,qname in enumerate(quality_names):
        for ri,radius in enumerate(RADII):
            c=sec_counts[qi,ri];tot=c.sum(axis=1);known=c[:,:-1].sum(axis=1)
            shares=np.divide(c[:,:-1],known[:,None],out=np.zeros_like(c[:,:-1],dtype=float),where=known[:,None]>0)
            entropy=-(shares*np.log(np.where(shares>0,shares,1))).sum(axis=1)
            feat=points.copy();feat['year']=year;feat['quality_mode']=qname;feat['geocode_radius_km']=radius
            feat['legal_entities']=tot;feat['unknown_section_legal_entities']=c[:,-1]
            feat['section_diversity']=(c[:,:-1]>0).sum(axis=1);feat['section_shannon']=entropy
            for s in ['G','I','P','Q']:feat['section_'+s+'_legal_entities']=c[:,sec_lut[s]]
            feat['broad_service_legal_entities']=sum(c[:,sec_lut[s]] for s in ['G','I','P','Q'])
            for gi,label in enumerate(GROUPS):feat[label+'_legal_entities']=grp_counts[qi,ri,:,gi]
            feat['direct_consumer_service_legal_entities']=sum(feat[x+'_legal_entities'] for x in ['retail47','food56','education85','health86','social8788','repair95','personal96'])
            feat['direct_consumer_function_diversity']=sum(feat[x+'_legal_entities'].gt(0).astype(int) for x in ['retail47','food56','education85','health86','social8788','repair95','personal96'])
            feat['financial_eligible_reports']=fin_counts[qi,ri]
            feat['known_nominal_revenue_thousand_rub']=revenues[qi,ri]
            feat['max_legal_entity_revenue_share']=np.divide(maxrev[qi,ri],revenues[qi,ri],out=np.full(n,np.nan),where=revenues[qi,ri]>0)
            pop=feat.population_2021.to_numpy()
            feat['broad_service_per_1000_own_pop2021']=np.divide(1000*feat.broad_service_legal_entities,pop,out=np.full(n,np.nan),where=pop>0)
            feat['rfds_presence_status']=np.where(tot>0,'observed_legal_address_presence','no_accepted_RFSD_witness_not_function_absence')
            if radius==1:mainframes.append(feat)
            active=np.flatnonzero(tot)
            for si,s in enumerate(SECTIONS):
                present=active[c[active,si]>0]
                sectorframes.append(pd.DataFrame({'id':points.id.iloc[present].to_numpy(),'year':year,
                  'quality_mode':qname,'geocode_radius_km':radius,'section':s,'legal_entities':c[present,si]}))
            balance=bal[qi,ri]
            crow={'year':year,'quality_mode':qname,'radius_km':radius,'accepted_legal_entities':int(tot.sum()),
             'np_any_entity':int((tot>0).sum()),'np_broad_service':int(feat.broad_service_legal_entities.gt(0).sum()),
             'np_direct_consumer_service':int(feat.direct_consumer_service_legal_entities.gt(0).sum()),
             'np_education':int(feat.education85_legal_entities.gt(0).sum()),'np_health':int(feat.health86_legal_entities.gt(0).sum()),
             'np_financial':int((fin_counts[qi,ri]>0).sum()),'accepted_financial_reports':int(fin_counts[qi,ri].sum()),
             'ambiguous_legal_entities':int(balance[1]),'outside_radius':int(balance[2]),'quality_rejected':int(balance[3])}
            coverage_rows.append(crow)
            checks += [{'check':f'{qname}_{radius}_partition_balance','pass':int(balance.sum())==cov['valid_coordinates_and_inn']},
                       {'check':f'{qname}_{radius}_aggregate_balance','pass':int(tot.sum())==int(balance[0])},
                       {'check':f'{qname}_{radius}_finite_entropy','pass':bool(np.isfinite(entropy).all())}]
    for ri,radius in enumerate(RADII):
        checks.append({'check':f'{radius}_strict_subset_presence','pass':bool((sec_counts[1,ri]<=sec_counts[0,ri]).all())})
        checks.append({'check':f'{radius}_strict_subset_finance','pass':bool((fin_counts[1,ri]<=fin_counts[0,ri]).all())})
    for qi in range(2):
        for ri in range(1,4):checks.append({'check':f'{qi}_{RADII[ri]}_monotone_radius','pass':bool((sec_counts[qi,ri]>=sec_counts[qi,ri-1]).all())})
    main=pd.concat(mainframes,ignore_index=True);main.to_parquet(out/'points_economic_features.parquet',index=False)
    main.to_csv(out/'points_economic_features.csv.gz',index=False,compression='gzip')
    sectors=pd.concat(sectorframes,ignore_index=True);sectors.to_parquet(out/'point_sector_sensitivity.parquet',index=False)
    pd.DataFrame(coverage_rows).to_csv(out/'coverage_by_mode.csv',index=False)
    checks.append({'check':'main_all_points_each_quality_mode','pass':len(main)==2*n and not main.duplicated(['id','year','quality_mode']).any()})
    read=pq.read_table(out/'points_economic_features.parquet').to_pandas()
    pd.testing.assert_frame_equal(main,read)
    checks.append({'check':'whole_table_parquet_readback','pass':True})
    cov['modes']=coverage_rows;cov['elapsed_seconds']=time.time()-start
    dump(out/'coverage.json',cov);dump(out/'checks.json',checks)
    dump(out/'provenance.json',{'panel':{'path':str(panel_path),'sha256':sha(panel_path)},'source':{'path':str(source),'sha256':sha(source)},
          'code_sha256':sha(Path(__file__)),'forbidden_input_fields':['zone_id','basin_id','growth','population_change'],
          'allowed_panel_columns':pp,'geocode_ambiguity_margin_km':.25,'no_catchment_inputs':True,
          'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='provenance.json'}})
    assert all(c['pass'] for c in checks)
    print(json.dumps({'year':year,'checks':len(checks),'main_rows':len(main),'primary':[r for r in coverage_rows if r['radius_km']==1]},ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--restored',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--years',nargs='+',type=int,default=[2021,2016]);args=ap.parse_args()
    for y in args.years:run(args.restored/'research/sgrt_recovered_20261019/data/panel.parquet',args.restored/f'inputs/recovery_inputs/enrichment/rfsd_{y}_selected.parquet',y,args.out/str(y))

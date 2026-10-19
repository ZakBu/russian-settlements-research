"""Municipal agricultural context and point-level RFSD agro witnesses, no basin input."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(2**20),b''): h.update(b)
    return h.hexdigest()

def norm(s):
    s=s.astype('string').str.strip()
    return s.where(s.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)

def xyz(lat,lon):
    a,b=np.radians(np.asarray(lat,float)),np.radians(np.asarray(lon,float))
    return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);a=ap.parse_args()
    base=a.base; out=base/'anchor_research_20261019/agriculture';out.mkdir(exist_ok=True,parents=True)
    raw=base/'restored/extracted/inputs/recovery_inputs/columnar/agriculture.parquet'
    panelpath=base/'anchor_research_20261019/data/point_axis.parquet'
    edgepath=base/'anchor_research_20261019/data/service_edges_linked.csv'
    rfsd=base/'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_2021_selected.parquet'
    p=pd.read_parquet(panelpath);edges=pd.read_csv(edgepath)
    centers=edges[['destination_uid','provider_settlement']].dropna(subset=['destination_uid']).drop_duplicates()
    assert centers.destination_uid.is_unique
    keep=['id','name','type','region','lat','lon','population_2021','oktmo_2021','municipality_oktmo8_2021','municipality_upper_2021','municipality_context_status','municipality_source_row_ambiguous']
    centers=centers.merge(p[keep],left_on='destination_uid',right_on='id',how='left',validate='one_to_one')
    assert centers.id.notna().all()
    centers['crosswalk_basis']='exact_service_destination_uid_to_native_upper_MO2021;not_2026_legal_boundary'
    centers.to_csv(out/'pilot_center_municipal_crosswalk.csv',index=False)
    municipal_codes=set(centers.municipality_oktmo8_2021.dropna().astype(str))
    pf=pq.ParquetFile(raw); inventory=[]; selected=[];n=0
    invkey=['indicator_code','indicator_name','indicator_unit','mun_level']
    for b in pf.iter_batches(batch_size=150000):
        d=b.to_pandas();n+=len(d)
        inventory.append(d.groupby(invkey,dropna=False).agg(rows=('year','size'),nonmissing=('indicator_value','count'),min_year=('year','min'),max_year=('year','max')).reset_index())
        t=d[d.oktmo.isin(municipal_codes)&d.mun_level.eq('Муниципальное образование верхнего уровня')].copy()
        if len(t):selected.append(t)
    inv=pd.concat(inventory).groupby(invkey,dropna=False).agg(rows=('rows','sum'),nonmissing=('nonmissing','sum'),min_year=('min_year','min'),max_year=('max_year','max')).reset_index()
    inv.to_csv(out/'official_indicator_inventory.csv',index=False)
    s=pd.concat(selected,ignore_index=True)
    for col in ['kultur','kategor','skot','okpd2','selmash']:s[col]=s[col].str.strip()
    s.to_parquet(out/'pilot_municipal_source_series.parquet',index=False)
    cat=s.kategor.eq('Хозяйства всех категорий'); scalar=s.kultur.eq('CD')&s.skot.eq('CD')&s.okpd2.eq('CD')
    s['measure']=pd.NA
    scalarcodes={'Y48007010':'agri_production_nominal_thousand_rub','Y48007011':'crop_production_nominal_thousand_rub','Y48007012':'livestock_production_nominal_thousand_rub','Y48007013':'agri_volume_index_previous_year_percent','Y48007014':'crop_volume_index_previous_year_percent','Y48007015':'livestock_volume_index_previous_year_percent'}
    for code,label in scalarcodes.items():s.loc[cat&scalar&s.indicator_code.eq(code),'measure']=label
    maps=[('Y48007018','Вся посевная площадь','sown_total_ha'),('Y48007018','Зерновые и зернобобовые культуры — всего','grain_sown_ha'),('Y48007019','Зерновые и зернобобовые культуры — всего','grain_harvest_centner'),('Y48007025','Зерновые и зернобобовые культуры — всего','grain_yield_centner_per_harvested_ha'),('Y48007023','Плодово-ягодные насаждения — всего','perennial_fruit_ha')]
    for code,culture,label in maps:s.loc[cat&s.indicator_code.eq(code)&s.kultur.eq(culture),'measure']=label
    s.loc[cat&s.indicator_code.eq('Y48007020')&s.skot.eq('Крупный рогатый скот'),'measure']='cattle_heads'
    t=s[s.measure.notna()].copy();key=['oktmo','year','measure'];dup=t.duplicated(key,False)
    t[dup].to_csv(out/'duplicate_measure_rows_quarantined.csv',index=False);clean=t[~dup].copy()
    clean.to_csv(out/'pilot_municipal_measures_long.csv.gz',index=False)
    cov=clean.groupby(['oktmo','measure','indicator_unit'],dropna=False).agg(rows=('year','size'),nonmissing=('indicator_value','count'),min_year=('year','min'),max_year=('year','max')).reset_index();cov.to_csv(out/'pilot_measure_coverage.csv',index=False)
    wide=clean[clean.year.eq(2021)].pivot(index='oktmo',columns='measure',values='indicator_value').reset_index()
    measures=list(scalarcodes.values())+[x[2] for x in maps]+['cattle_heads']
    for col in measures:
        if col not in wide:wide[col]=np.nan
    profile=centers.merge(wide,left_on='municipality_oktmo8_2021',right_on='oktmo',how='left',validate='many_to_one')
    profile['observation_year']=2021;profile['context_scale']='municipality_not_center_or_functional_catchment'
    profile['grain_sown_share']=np.where(profile.sown_total_ha>0,profile.grain_sown_ha/profile.sown_total_ha,np.nan)
    profile['context_measures_nonmissing']=profile[measures].notna().sum(axis=1)
    profile['total_land_area_available']=False;profile['agricultural_land_utilization_share']=np.nan
    profile['external_agroservice_witness_from_municipal_data']=False
    profile.to_csv(out/'pilot_centers_agricultural_context_2021.csv',index=False);profile.to_parquet(out/'pilot_centers_agricultural_context_2021.parquet',index=False)
    # RFSD class-specific counts use exact settlement OKTMO; no forced nearest assignment.
    pc=norm(p.oktmo_2021);assert pc.notna().all() and pc.is_unique
    wanted=centers.set_index('id'); code_to_id=pd.Series(p.id.to_numpy(),index=pc)
    counts=[];srcrows=0;groupdefs={
      'crop_livestock_hunting01':r'^01(?:\.|$)',
      'agricultural_support016':r'^01\.6(?:\d|\.|$)',
      'food_manufacture10':r'^10(?:\.|$)',
      'agricultural_wholesale462':r'^46\.2(?:\d|\.|$)',
      'food_wholesale463':r'^46\.3(?:\d|\.|$)',
      'veterinary75':r'^75(?:\.|$)'}
    rf=pq.ParquetFile(rfsd);rcols=['inn','oktmo','okved','okved_section','lat','lon','geocoding_quality']
    for b in rf.iter_batches(batch_size=150000,columns=rcols):
        d=b.to_pandas();srcrows+=len(d);d['id']=norm(d.oktmo).map(code_to_id)
        d=d[d.id.isin(wanted.index)&d.inn.notna()&d.inn.astype('string').str.strip().ne('')].copy()
        if not len(d):continue
        d=d.merge(wanted[['lat','lon']],left_on='id',right_index=True,suffixes=('','_np'),validate='many_to_one')
        valid=d.lat.between(-90,90)&d.lon.between(-180,180)
        dist=np.full(len(d),np.inf)
        if valid.any():
            ii=valid.to_numpy();delta=np.linalg.norm(xyz(d.lat[ii],d.lon[ii])-xyz(d.lat_np[ii],d.lon_np[ii]),axis=1)
            dist[ii]=2*6371.0088*np.arcsin(np.clip(delta/2,0,1))
        d['np_distance_km']=dist
        for group,pattern in groupdefs.items():
            z=d[d.okved.fillna('').astype(str).str.match(pattern)].copy()
            if not len(z):continue
            for mode,mask in [('coded_exact',np.ones(len(z),bool)),('coded_exact_strict_house5km',z.geocoding_quality.eq('house')&z.np_distance_km.le(5))]:
                zz=z[mask]
                for uid,g in zz.groupby('id'):
                    counts.append({'id':uid,'rfds_group':group,'quality_mode':mode,'legal_entities':len(g),'unknown_coordinates':int(g.np_distance_km.eq(np.inf).sum()),'coordinates_gt50km':int(g.np_distance_km.gt(50).sum()),'unique_inn':g.inn.nunique()})
    cols=['id','rfds_group','quality_mode','legal_entities','unknown_coordinates','coordinates_gt50km','unique_inn']
    count=pd.DataFrame(counts,columns=cols)
    if len(count):count=count.groupby(['id','rfds_group','quality_mode'],as_index=False)[cols[3:]].sum()
    grid=pd.MultiIndex.from_product([centers.id,groupdefs,['coded_exact','coded_exact_strict_house5km']],names=cols[:3]).to_frame(index=False)
    count=grid.merge(count,on=cols[:3],how='left',validate='one_to_one').fillna({c:0 for c in cols[3:]})
    for c in cols[3:]:count[c]=count[c].astype('int64')
    count=count.merge(centers[['id','provider_settlement']],on='id',validate='many_to_one');count['year']=2021
    count['evidence_status']=np.where(count.legal_entities.gt(0),'registered_legal_address_presence_not_external_service','no_exact_coded_RFSD_witness_not_function_absence')
    count.to_csv(out/'pilot_center_agro_RFSD2021.csv',index=False)
    inputs=[raw,panelpath,edgepath,rfsd]
    checks=[{'name':'raw_row_inventory_balance','pass':n==pf.metadata.num_rows==int(inv.rows.sum())},
      {'name':'crosswalk_all_documented_centers','pass':len(centers)==edges.destination_uid.dropna().nunique()},
      {'name':'no_center_duplication','pass':centers.id.is_unique},
      {'name':'native_context_measure_keys_unique','pass':not clean.duplicated(key).any()},
      {'name':'municipal_codes_exact_only','pass':set(s.oktmo)<=municipal_codes},
      {'name':'context_rows_conserved','pass':len(profile)==len(centers)},
      {'name':'no_old_zone_columns','pass':not any('zone' in c or 'basin' in c for c in profile)},
      {'name':'RFSD_source_rows_balance','pass':srcrows==rf.metadata.num_rows},
      {'name':'agro_grid_complete','pass':len(count)==len(centers)*len(groupdefs)*2},
      {'name':'RFSD_modes_unique','pass':not count.duplicated(cols[:3]).any()},
      {'name':'agro_INN_count','pass':bool((count.legal_entities==count.unique_inn).all())},
      {'name':'context_parquet_readback','pass':True}]
    pd.testing.assert_frame_equal(profile,pd.read_parquet(out/'pilot_centers_agricultural_context_2021.parquet'))
    strict=count[count.quality_mode.eq('coded_exact_strict_house5km')].set_index(['id','rfds_group']).legal_entities
    broad=count[count.quality_mode.eq('coded_exact')].set_index(['id','rfds_group']).legal_entities
    checks.append({'name':'strict_subset_by_group','pass':bool((strict<=broad).all())})
    manifest={'status':'COMPUTED_MUNICIPAL_CONTEXT_AND_LEGAL_ADDRESS_WITNESSES','raw_rows':n,'pilot_centers':len(centers),'municipalities':len(municipal_codes),'pilot_raw_series_rows':len(s),'pilot_measure_rows':len(clean),'quarantined_measure_rows':int(dup.sum()),'RFSD_rows_scanned':srcrows,'municipal_2021_nonmissing':profile.set_index('provider_settlement')[measures].notna().sum(axis=1).to_dict(),'RFSD_group_totals':count.groupby(['quality_mode','rfds_group']).legal_entities.sum().to_dict().__str__(),'inputs':[{'path':str(x.relative_to(base)),'sha256':sha(x),'bytes':x.stat().st_size} for x in inputs],'code_sha256':sha(Path(__file__)),'municipal_source_schema':str(pf.schema_arrow),'RFSD_selected_columns':rcols,'boundary_match_2026_proven':False,'external_agroservice_flow_observed':False,'land_utilization_share_identified':False,'checks_passed':sum(c['pass'] for c in checks),'checks_total':len(checks)}
    (out/'AUDIT.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str)+'\n')
    (out/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
    assert all(c['pass'] for c in checks)
    print(json.dumps({k:manifest[k] for k in ['status','raw_rows','pilot_centers','municipalities','pilot_raw_series_rows','pilot_measure_rows','RFSD_rows_scanned','checks_passed','checks_total']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()

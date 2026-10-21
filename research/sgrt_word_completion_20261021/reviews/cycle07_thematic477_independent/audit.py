"""Independent finite-source audit: exhaustive NumPy distances, no producer imports."""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'typology2021_cycle07/recovery477_relink'
checks=[]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def check(name,ok):
    checks.append({'check':name,'passed':bool(ok)})
    if not ok:raise AssertionError(name)
def distance(a,b):
    a=np.radians(a);b=np.radians(b)
    dl=a[:,None,0]-b[None,:,0];dn=a[:,None,1]-b[None,:,1]
    q=np.sin(dl/2)**2+np.cos(a[:,None,0])*np.cos(b[None,:,0])*np.sin(dn/2)**2
    return 2*6371.0088*np.arctan2(np.sqrt(np.clip(q,0,1)),np.sqrt(np.clip(1-q,0,1)))
def eq(a,b):return a.eq(b).fillna(False)|(a.isna()&b.isna())
def flag(d,col,values):
    expected=pd.Series(pd.array([True if x else None for x in values],dtype='boolean'),index=d.index)
    check(col,eq(d[col],expected).all())
def norm(s):return re.sub('[^а-яa-z0-9]+',' ',str(s or '').casefold().replace('ё','е')).strip()

def main():
    proto=json.loads((OUT/'preregistration.json').read_text())
    watched={str(ROOT/p):v for p,v in proto['inputs_sha256'].items()}
    ownproto=json.loads((OUT/'own_functions_supplemental_protocol.json').read_text())
    watched.update({str(ROOT/p):v for p,v in ownproto['new_inputs_sha256'].items()})
    for p,v in watched.items():check('source_pin:'+p,sha(Path(p))==v)
    outputpins={str(p):sha(p) for p in OUT.glob('*') if p.is_file()}
    cols=['id','name','type','lat','lon','population_2021','is_additive_source_unit','axis_kind']
    axis=pd.read_parquet(ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet',columns=cols)
    patch=pd.read_parquet(ROOT/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet').set_index('id')
    valid=axis.population_2021.notna()&axis.is_additive_source_unit.fillna(False)&~axis.axis_kind.fillna('').str.contains('territory',case=False)
    oldref=axis.loc[valid&np.isfinite(axis[['lat','lon']].to_numpy(float)).all(axis=1)].copy()
    new=axis.loc[axis.id.isin(patch.index)].sort_values('id').copy()
    check('reference477_new_na_coords',len(new)==477 and new[['lat','lon']].isna().all().all())
    new['lat']=new.id.map(patch.new_lat);new['lon']=new.id.map(patch.new_lon)
    ref=pd.concat([oldref,new],ignore_index=True)
    check('source_reference_counts',len(oldref)==154132 and len(ref)==154609 and ref.id.is_unique)
    changedlinks=[];competition=[];tables={}
    for fam,source,output in [
        ('industry_resource','typology2021_cycle05/industry_resource/industry_resource_objects_2021.parquet','industry_resource_objects_relinked.parquet'),
        ('recreation','model_inputs_cycle05/thematic2021/recreation_canonical_site_links.parquet','recreation_canonical_site_links.parquet')]:
        a=pd.read_parquet(ROOT/source);b=pd.read_parquet(OUT/output)
        check(fam+':source_row_identity',len(a)==len(b) and a.site_id.equals(b.site_id))
        changedcols={'nearest_axis_id','nearest_distance_km','count_eligible'}
        check(fam+':all_source_fields_preserved',a.drop(columns=list(changedcols&set(a))).equals(b[a.columns].drop(columns=list(changedcols&set(a)))))
        expectids=a.nearest_axis_id.copy();expectdist=a.nearest_distance_km.copy()
        for start in range(0,len(a),512):
            z=a.iloc[start:start+512];good=np.isfinite(z[['lat','lon']].to_numpy(float)).all(axis=1)
            goodz=z.loc[good];ds=distance(goodz[['lat','lon']].to_numpy(float),new[['lat','lon']].to_numpy(float))
            for k,(idx,row) in enumerate(goodz.iterrows()):
                best=ds[k].min();prev=float(row.nearest_distance_km) if pd.notna(row.nearest_distance_km) else np.inf
                if best<=prev+1e-7:
                    ties=np.flatnonzero(ds[k]<=best+1e-7);chosen=ties[0];change=best<prev-1e-7
                    competition.append((fam,row.site_id,change,[str(new.id.iloc[j]) for j in ties]))
                    if change:
                        expectids.at[idx]=new.id.iloc[chosen];expectdist.at[idx]=ds[k,chosen]
                        changedlinks.append((fam,str(row.site_id)))
        check(fam+':all_nearest_owners',eq(expectids,b.nearest_axis_id).all())
        check(fam+':distance_missingness',np.array_equal(expectdist.isna(),b.nearest_distance_km.isna()))
        err=np.abs(expectdist.to_numpy(float)-b.nearest_distance_km.to_numpy(float))
        check(fam+':all_nearest_distances',np.all(np.isnan(err)|(err<1e-7)))
        check(fam+':old_owner_retained_on_ties',eq(b.previous_nearest_axis_id,a.nearest_axis_id).all() and eq(b.previous_nearest_distance_km,a.nearest_distance_km).all())
        tables[fam]=b
    ledger=pd.read_parquet(OUT/'all_competitive_new_sourcepoint_links.parquet')
    expected={(f,str(s)):(c,t) for f,s,c,t in competition}
    check('all_competitive_source_rows',len(ledger)==len(expected))
    for row in ledger.itertuples():
        change,ties=expected[(row.family,str(row.site_id))]
        check('competition:'+row.family+':'+str(row.site_id),change==row.changed and ties==[str(t['id']) for t in json.loads(row.all_new477_minimum_ties_json)])
    check('changed_link_count111',len(changedlinks)==111)
    summaries=[]
    oldpaths={'industry_resource':'typology2021_cycle05/industry_resource/settlement_industry_resource_features_2021.parquet','recreation':'model_inputs_cycle05/thematic2021/settlement_recreation_features_full_axis.parquet','agro_processing':'typology2021_cycle05/own_function_rules/agro_processing_v1/settlement_literal_agro_processing_evidence_2021.parquet'}
    files={'industry_resource':'settlement_industry_resource_features_2021.parquet','recreation':'settlement_recreation_features_2021.parquet','agro_processing':'settlement_literal_agro_processing_evidence_2021.parquet'}
    obj=tables['industry_resource'];di=pd.read_parquet(OUT/files['industry_resource'])
    for pred,col,lim in [('source_resource_predicate','osm_resource_site_geometries_within5km',5),('source_industrial_predicate','osm_industrial_geometries_within3km',3)]:
        for raw in [False,True]:
            use=obj if raw else obj.loc[obj.site_id.eq(obj.canonical_site_id)]
            use=use.loc[use[pred]&~use.inactive_source_asserted&use.nearest_distance_km.le(lim)]
            counts=use.nearest_axis_id.value_counts();cc=col+('_raw_assertions' if raw else '')
            check(cc,np.array_equal(di.id.map(counts).fillna(0).to_numpy(),di[cc].to_numpy()))
    for f,c in [('mapped_resource_site_context_evidence','osm_resource_site_geometries_within5km'),('mapped_industrial_site_context_evidence','osm_industrial_geometries_within3km')]:flag(di,f,di[c].gt(0))
    rec=tables['recreation'];dr=pd.read_parquet(OUT/files['recreation'])
    check('recreation_count_eligible',rec.count_eligible.equals(rec.nearest_distance_km.le(3)&~rec.inactive_source_asserted))
    for group,col in [('accommodation','osm_accommodation_points_within3km'),('allotments','osm_allotment_geometries_within3km')]:
        counts=rec.loc[rec.count_eligible&rec.source_group.eq(group)].nearest_axis_id.value_counts()
        check(col,np.array_equal(dr.id.map(counts).fillna(0).to_numpy(),dr[col].to_numpy()))
    for f,c in [('recreation_facility_evidence','osm_accommodation_points_within3km'),('dacha_landuse_evidence','osm_allotment_geometries_within3km')]:flag(dr,f,dr[c].gt(0))
    flag(dr,'recreation_dacha_evidence',dr[['osm_accommodation_points_within3km','osm_allotment_geometries_within3km']].sum(axis=1).gt(0))
    ag=pd.read_parquet(OUT/'literal_processing_source_assertions.parquet');oldag=pd.read_parquet(ROOT/'typology2021_cycle05/own_function_rules/agro_processing_v1/literal_processing_source_assertions.parquet')
    names=ref.name.map(norm).to_numpy();agcols={'strict_explicit_uid','strict_source_distance_km','explicit_locality_link_status','all_same_name_candidate_UIDs_json','canonical_explicit_identity_conflict','count_eligible_processing_witness'}
    check('72_strict_assertions_source_immutable',len(ag)==72 and oldag.drop(columns=list(agcols)).equals(ag[oldag.columns].drop(columns=list(agcols))))
    for row in ag.itertuples():
        tags=json.loads(row.source_tags_json);local=next((tags[k] for k in ['addr:city','addr:village','addr:hamlet','addr:place','is_in:city'] if tags.get(k)),None)
        name=re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',norm(local))
        candidates=ref.loc[names==name] if name else ref.iloc[:0]
        if len(candidates) and np.isfinite([row.lat,row.lon]).all():
            dd=distance(np.array([[row.lat,row.lon]]),candidates[['lat','lon']].to_numpy(float))[0]
            candidates=candidates.loc[dd<=5]
        else:candidates=ref.iloc[:0]
        ids=sorted(candidates.id.astype(str));actual=[str(h['id']) for h in json.loads(row.all_same_name_candidate_UIDs_json)]
        check('agro_full_homonym_ball:'+str(row.site_id),ids==actual and (str(row.strict_explicit_uid)==ids[0] if len(ids)==1 else pd.isna(row.strict_explicit_uid)))
        if len(ids)==1:
            dd=distance(np.array([[row.lat,row.lon]]),candidates[['lat','lon']].to_numpy(float))[0,0]
            check('agro_strict_distance:'+str(row.site_id),abs(dd-row.strict_source_distance_km)<1e-7)
    eligible=~ag.explicit_lifecycle_or_nonoperating_source&~ag.inactive_source_asserted
    conflicts=ag.loc[eligible&ag.strict_explicit_uid.notna()].groupby('canonical_site_id').strict_explicit_uid.nunique()
    conflict=ag.canonical_site_id.isin(conflicts[conflicts>1].index)
    check('agro_canonical_conflicts',ag.canonical_explicit_identity_conflict.equals(conflict))
    good=eligible&ag.strict_explicit_uid.notna()&~conflict
    check('agro_final_witnesses11',ag.count_eligible_processing_witness.equals(good) and good.sum()==11)
    da=pd.read_parquet(OUT/files['agro_processing']);counts=ag.loc[good].drop_duplicates(['strict_explicit_uid','canonical_site_id']).strict_explicit_uid.value_counts()
    check('agro_final_NP_counts10',np.array_equal(da.id.map(counts).fillna(0),da.own2021_strict_literal_agroprocessing_source_sites) and len(counts)==10)
    flag(da,'agro_processing_function_evidence',da.own2021_strict_literal_agroprocessing_source_sites.gt(0))
    changed=[]
    for fam,newtab in [('industry_resource',di),('recreation',dr),('agro_processing',da)]:
        old=pd.read_parquet(ROOT/oldpaths[fam]);check(fam+':full_feature_ids',old.id.equals(newtab.id) and old.columns.equals(newtab.columns))
        permitted={'industry_resource':{'osm_resource_site_geometries_within5km','osm_resource_site_geometries_within5km_raw_assertions','osm_industrial_geometries_within3km','osm_industrial_geometries_within3km_raw_assertions','mapped_resource_site_context_evidence','mapped_industrial_site_context_evidence'},'recreation':{'osm_accommodation_points_within3km','osm_allotment_geometries_within3km','recreation_facility_evidence','dacha_landuse_evidence','recreation_dacha_evidence'},'agro_processing':{'own2021_strict_literal_agroprocessing_source_sites','agro_processing_function_evidence'}}[fam]
        check(fam+':noncomputed_feature_fields_immutable',old.drop(columns=list(permitted)).equals(newtab.drop(columns=list(permitted))))
        for col in old.columns.drop('id'):
            for idx in np.flatnonzero(~eq(old[col],newtab[col]).to_numpy(bool)):
                changed.append((fam,str(newtab.id.iloc[idx]),col,str(old[col].iloc[idx]),str(newtab[col].iloc[idx]),newtab.id.iloc[idx] in patch.index))
    changes=pd.read_parquet(OUT/'all_changed_feature_cells.parquet')
    check('all321_changed_feature_cells',len(changed)==321 and set(changed)==set(changes.itertuples(index=False,name=None)))
    check('all117_affected_NP',len({x[1] for x in changed})==117)
    oldown=pd.read_parquet(ROOT/'typology2021_cycle05/own_function_rules/settlement_own_function_evidence_2021.parquet');own=pd.read_parquet(OUT/'settlement_own_function_evidence_2021.parquet')
    columns={'commerce':{'own2021_strict_large_retail_source_sites':'services_osm2021_large_retail_baseline_count','own2021_strict_physical_administration_source_sites':'services_osm2021_administration_baseline_count'},'education':{'own2021_strict_school_source_sites':'education_osm2021_school_baseline_count'},'medical':{'own2021_strict_general_clinical_source_sites':'medical_osm_baseline_healthcare_sites_count'}}
    varied=set()
    for fam,mapping in columns.items():
        source=pd.read_parquet(ROOT/f'model_inputs_cycle07/institutional_relink477_v1/{fam}/settlement_features_full_axis.parquet',columns=['id',*mapping.values()])
        check(fam+':strict_source_axis',own.id.equals(source.id))
        for col,key in mapping.items():check('own_source:'+col,own[col].equals(source[key]));varied.add(col)
    seat=own.admin2021_upper_municipal_center_evidence.eq(True).fillna(False)
    trade=own.own2021_strict_large_retail_source_sites.gt(0);gov=own.own2021_strict_physical_administration_source_sites.gt(0)
    school=own.own2021_strict_school_source_sites.gt(0);clinic=own.own2021_strict_general_clinical_source_sites.gt(0)
    for col,value in {'trade_and_administration_function_evidence':trade&gov,'basic_administrative_service_function_evidence':seat&school&clinic,'basic_administrative_service_with_physical_admin_evidence':seat&school&clinic&gov}.items():
        flag(own,col,value);varied.add(col);check('own_flags_unchanged:'+col,own[col].equals(oldown[col]))
    check('other_own_source_fields_unchanged',oldown.drop(columns=list(varied)).equals(own.drop(columns=list(varied))))
    ownchanges=[]
    for col in own.columns.drop('id'):
        for idx in np.flatnonzero(~eq(oldown[col],own[col]).to_numpy(bool)):
            ownchanges.append((str(own.id.iloc[idx]),col,str(oldown[col].iloc[idx]),str(own[col].iloc[idx])))
    ownledger=pd.read_parquet(OUT/'own_function_changed_cells.parquet')
    check('one_raw_own_count_cell_ledger',len(ownchanges)==1 and set(ownchanges)==set(ownledger.itertuples(index=False,name=None)))
    check('all_inputs_unchanged',all(sha(Path(p))==v for p,v in watched.items()))
    check('all_outputs_unchanged',all(sha(Path(p))==v for p,v in outputpins.items()))
    receipt={'status':'ACCEPTED_INDEPENDENT_FINITE_THEMATIC477_RELINK','all_checks_passed':all(c['passed'] for c in checks),'n_checks':len(checks),'review_code_sha256':sha(Path(__file__)),'method':'All265542sourceobjects compared exhaustively to477newcoordinates in NumPy, no producer/BallTree import; all72strictname homonym candidate sets replayed; allnationalfeaturecounts recomputed inclwithdrawals; fixed ownfunction co-presence replayed','source_sha256':watched,'output_sha256':outputpins,'checks':checks,'mass_or_hierarchy_admission':False}
    (HERE/'audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(receipt['status'],len(checks))

if __name__=='__main__':main()

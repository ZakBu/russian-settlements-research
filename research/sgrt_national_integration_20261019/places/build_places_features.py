"""Technical identity candidates for a national physical-place publication snapshot."""
from pathlib import Path
import json,re,struct,hashlib,datetime,os,gc
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree
from extract_ru_places import country_mask

R=Path(__file__).resolve().parent
AXIS=R.parents[1]/'anchor_research_20261019/data/point_axis.parquet'
RELEASE='2026-09-23.1'

def save_parquet(frame,path):
    pending=path.with_suffix('.parquet.partial');frame.to_parquet(pending,index=False)
    with pending.open('rb') as durable:os.fsync(durable.fileno())
    read=pq.read_table(pending);assert len(read)==len(frame) and read.column_names==list(frame.columns)
    pending.replace(path)

def norm(s):
    if s is None:return ''
    s=str(s).lower().replace('ё','е')
    s=re.sub(r'\([^)]*\)',' ',s)
    s=re.sub(r'^(?:город|село|деревня|поселок|посёлок|пгт|пос\.|п\.|с\.|д\.|г\.)\s*','',s)
    return re.sub(r'[^a-zа-я0-9]+',' ',s).strip()

def xyz(lat,lon):
    la,lo=np.deg2rad(lat),np.deg2rad(lon)
    return np.c_[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]

def geometry_point(blob):
    endian='<' if blob[0]==1 else '>'
    typ=struct.unpack(endian+'I',blob[1:5])[0];offset=9 if typ&0x20000000 else 5
    assert typ&0xff in [1],f'Unexpected geometry type{typ}'
    return struct.unpack(endian+'dd',blob[offset:offset+16])

def group(category,hierarchy,basic,name):
    cats=set([category,basic,*([] if hierarchy is None else list(hierarchy))]);cats.discard(None);cats.discard('')
    if not cats:return 'unknown_999',999,'missing_source_taxonomy'
    if cats & {'pharmacy','drugstore'}:return 'pharmacy',30,'source_taxonomy'
    if cats & {'bank','credit_union','bank_or_credit_union'}:return 'bank',40,'source_taxonomy'
    if cats & {'atm','automated_teller_machine'}:return 'atm',41,'source_taxonomy'
    if cats & {'post_office','postal_service'}:return 'post_office',50,'source_taxonomy'
    if cats & {'mailbox','post_box'}:return 'postal_collection_point',51,'source_taxonomy'
    if cats & {'market','marketplace','farmers_market','flea_market','public_market','wholesale_market','food_market','bazaar'}:return 'market',60,'source_taxonomy'
    if cats & {'school','primary_school','secondary_school','middle_school','high_school','elementary_school','public_school','private_school'}:return 'school',10,'source_taxonomy'
    if cats & {'preschool','kindergarten','nursery_school','day_care','child_care','day_care_preschool'}:return 'preschool',11,'source_taxonomy'
    if cats & {'college','university','higher_education','vocational_school','education','college_university'}:return 'other_education',12,'source_taxonomy'
    if cats & {'veterinarian','veterinary_clinic','veterinary_service'}:return 'veterinary',23,'source_taxonomy'
    if cats & {'hospital'}:return 'hospital',20,'source_taxonomy'
    if cats & {'health_and_medical','healthcare','health_care','medical_center','medical_clinic','health_clinic','doctor','doctors','dentist','dental_clinic','community_health_center','family_practice'}:
        return ('healthcare',21,'source_taxonomy_and_fap_name_candidate') if re.search(r'\bфап\b|фельдшер',str(name).lower()) else ('healthcare',21,'source_taxonomy')
    if cats & {'shopping','retail','retail_store','grocery_store','supermarket','convenience_store','department_store','discount_store','shopping_mall','food_and_grocery'}:return 'retail_store',70,'source_taxonomy'
    if cats & {'restaurant','food_and_drink','food_and_beverage','cafe','bar'}:return 'food_service',80,'source_taxonomy'
    return 'outside_requested_functions',0,'source_category_not_mapped_to_requested_function'

def main():
    axis=pd.read_parquet(AXIS)
    files=sorted((R/'selected').glob('overture_ru_selected_*.parquet'))
    if not files:raise RuntimeError('No extracted source files')
    frames=[]
    for file in files:
        d=pq.read_table(file).to_pandas()
        if len(d):d['source_part']=file.name;frames.append(d)
    data=pd.concat(frames,ignore_index=True)
    acquisition=json.loads((R/'ACQUISITION.json').read_text())
    assert acquisition['all_files_scoped'] and len(data)==acquisition['selected_rows']
    print('Selected source rows',len(data),flush=True)
    assert data.id.is_unique,'Repeated source GERS identifiers require a source conflict audit'
    coords=np.array([geometry_point(b) for b in data.geometry]);data['longitude']=coords[:,0];data['latitude']=coords[:,1]
    old=R.parents[1]/'anchor_research_20261019/model/documented_graph/service_edges_calculated.csv'
    old_geometry=pd.read_csv(old)
    quarantine=set(old_geometry.loc[old_geometry.geometry_status.eq('coordinate_conflict_quarantined'),'origin_uid'].dropna())
    valid=np.isfinite(axis.lat)&np.isfinite(axis.lon)&~axis.id.isin(quarantine)
    ap=axis[valid].copy().reset_index(drop=True);tree=cKDTree(xyz(ap.lat.to_numpy(),ap.lon.to_numpy()))
    distances,near=tree.query(xyz(data.latitude.to_numpy(),data.longitude.to_numpy()),k=16,workers=4)
    distances=2*6371.0088*np.arcsin(np.clip(distances/2,0,1))
    n_names=ap.name.map(norm).to_numpy();uids=ap.id.to_numpy();regions=ap.region.to_numpy()
    name_index={}
    for j,n in enumerate(n_names):name_index.setdefault(n,[]).append(j)
    axis_xyz=xyz(ap.lat.to_numpy(),ap.lon.to_numpy())
    source_xyz=xyz(data.latitude.to_numpy(),data.longitude.to_numpy())
    inside=country_mask(data.longitude.to_numpy(),data.latitude.to_numpy())
    rows=[]
    for i,record in enumerate(data.itertuples(index=False,name=None)):
        if i and i%50000==0:print('Crosswalk objects',i,flush=True)
        source=dict(zip(data.columns,record))
        name=(source.get('names') or {}).get('primary');tax=source.get('taxonomy') or {}
        addresses=source.get('addresses');addresses=[] if addresses is None else list(addresses)
        localities={norm(a.get('locality')) for a in addresses if a.get('locality')};localities.discard('')
        countries={a.get('country') for a in addresses if a.get('country')}
        country_ru='RU' in countries;country_conflict=bool((countries and not country_ru and inside[i]) or len(countries)>1)
        freeforms=[a.get('freeform') for a in addresses if a.get('freeform')]
        addrnames=set()
        for address in freeforms:
            for hit in re.finditer(r'(?:^|[,;])\s*(?:город|село|деревня|пос[её]лок|пгт|г\.|с\.|д\.|п\.)\s*([^,;]+)',address,re.I):
                addrnames.add(norm(hit.group(1)))
        def name_candidates(names):
            js=sorted({j for n in names for j in name_index.get(n,[])})
            if not js:return []
            ds=2*6371.0088*np.arcsin(np.clip(np.linalg.norm(axis_xyz[js]-source_xyz[i],axis=1)/2,0,1))
            return [(int(j),float(dist)) for j,dist in zip(js,ds) if dist<=10]
        exact=name_candidates(localities);conditional=name_candidates(addrnames)
        same=[x for x in exact if x[1]<=5]
        baseline_uid=None;conditional_uid=None;status='unresolved_no_address_identity'
        if len(exact)==1 and same and not country_conflict:
            baseline_uid=uids[same[0][0]];status='baseline_exact_address_locality_within5km_unique_all_name_matches10km'
        elif len(exact)==1:
            conditional_uid=uids[exact[0][0]];status='conditional_locality_or_country_conflict'
        elif len(exact)>1:status='ambiguous_address_locality'
        elif len(conditional)==1 and conditional[0][1]<=5 and not country_conflict:
            conditional_uid=uids[conditional[0][0]];status='conditional_typed_freeform_address_within5km'
        elif len(conditional)>1:status='ambiguous_typed_address'
        nearest_uid=uids[near[i,0]];nearest_distance=float(distances[i,0])
        cand=nearest_uid if baseline_uid is None and conditional_uid is None and nearest_distance<=10 and not country_conflict else None
        source_regions={norm(a.get('region')) for a in addresses if a.get('region')}
        lat,lon=source['latitude'],source['longitude'];scope='axis_linkage_eligible'
        if 32.4<=lon<=36.65 and 44.2<=lat<=46.4:scope='external_southern_geography_no_UID_in_reference_bbox'
        if baseline_uid is None and (localities|source_regions)&{'москва','moscow','moskva'} and 36.2<=lon<=38.7 and 54.7<=lat<=56.3:scope='external_moscow_explicit_source_address'
        if baseline_uid is None and (localities|source_regions)&{'санкт петербург','saint petersburg','st petersburg','sankt peterburg'} and 28.5<=lon<=31.9 and 58.9<=lat<=61:scope='external_saint_petersburg_explicit_source_address'
        # Without an address identity, avoid mapping city-core POI to a nearby village.
        if scope=='axis_linkage_eligible' and baseline_uid is None and conditional_uid is None:
            for clat,clon,label in [(55.7558,37.6176,'moscow'),(59.9343,30.3351,'saint_petersburg')]:
                center=xyz(np.array([clat]),np.array([clon]))[0]
                km=2*6371.0088*np.arcsin(np.clip(np.linalg.norm(source_xyz[i]-center)/2,0,1))
                if km<=20:scope=f'external_{label}_core_coordinate_candidate_not_legal_mask'
        if scope!='axis_linkage_eligible':baseline_uid=None;conditional_uid=None;cand=None;status='external_geography_preserved_without_settlement_assignment'
        family,code,family_evidence=group(tax.get('primary'),tax.get('hierarchy'),source.get('basic_category'),name)
        operating=source.get('operating_status');operating='unknown' if not operating else operating
        signal_name=str(name or '').lower().replace('ё','е')
        signals={label:bool(re.search(pattern,signal_name)) for label,pattern in {'fap':r'\bфап\b|фельдшер','school':r'\bшкол[аы]\b|общеобразовательн','market':r'\bрынок\b|\bбазар\b|\bmarket\b','ozon':r'\bozon\b|\bозон\b','wildberries':r'\bwildberries\b|вайлдберриз'}.items()}
        distance_by_uid={uids[j]:dist for j,dist in exact+conditional}
        linked=baseline_uid or conditional_uid or cand
        linked_distance=(distance_by_uid.get(linked,nearest_distance) if linked else None)
        rows.append({'source_place_id':source['id'],'source_version':source['version'],'source_release':RELEASE,'source_part':source['source_part'],'primary_name':name,'longitude':source['longitude'],'latitude':source['latitude'],'source_confidence':source['confidence'],'source_operating_status':operating,'source_category':tax.get('primary'),'source_basic_category':source.get('basic_category'),'source_taxonomy_json':json.dumps(tax,ensure_ascii=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)),'function_group':family,'function_group_code':code,'function_group_evidence':family_evidence,'addresses_json':json.dumps(addresses,ensure_ascii=False),'sources_json':json.dumps(source.get('sources'),ensure_ascii=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)),'country_values':'|'.join(sorted(countries)),'source_country_ru':country_ru,'coarse_naturalearth_rus_inside':bool(inside[i]),'country_polygon_conflict':country_conflict,'source_geography_scope':scope,'baseline_uid':baseline_uid,'conditional_uid':conditional_uid,'nearest_candidate_uid':cand,'nearest_uid_unaccepted':nearest_uid,'nearest_distance_km':nearest_distance,'linked_distance_km':linked_distance,'crosswalk_status':status,'address_identity_candidate_uids':'|'.join(sorted({uids[x[0]] for x in exact+conditional})),'external_service_catchment_observed':False,'physical_operation_independently_verified':False,'observation_year':2026,**{f'name_signal_{k}':v for k,v in signals.items()}})
    # The crosswalk is complete: avoid retaining source object columns and
    # coordinate work arrays while materializing the output DataFrame.
    del frames,data,d,coords,near,distances,source_xyz,axis_xyz,inside
    gc.collect()
    long=pd.DataFrame(rows)
    del rows
    gc.collect()
    save_parquet(long,R/'places_objects_and_crosswalk.parquet')
    long.to_csv(R/'places_objects_and_crosswalk.csv.gz',index=False,compression='gzip',chunksize=2500)
    save_parquet(long.loc[long.source_geography_scope.ne('axis_linkage_eligible')],R/'places_external_geography.parquet')
    wide=axis[['id']].copy().set_index('id')
    families=['school','preschool','other_education','hospital','healthcare','veterinary','pharmacy','bank','atm','post_office','postal_collection_point','market','retail_store','food_service','unknown_999']
    for mode,uidcol in [('baseline','baseline_uid'),('conditional','conditional_uid'),('nearest_candidate','nearest_candidate_uid')]:
        linked=long[long[uidcol].notna()]
        count=linked.groupby(uidcol).size();wide[f'places_{mode}_all_categories_count']=count.reindex(wide.index,fill_value=0).astype('int32')
        not_closed=linked[linked.source_operating_status.ne('permanently_closed')&linked.source_confidence.ne(0)]
        target_all=linked[~linked.function_group.isin(['outside_requested_functions','unknown_999'])]
        target=target_all[target_all.source_operating_status.ne('permanently_closed')&target_all.source_confidence.ne(0)]
        c=target.groupby(uidcol).size();wide[f'places_{mode}_requested_function_count']=c.reindex(wide.index,fill_value=0).astype('int32')
        div=target.groupby(uidcol).function_group.nunique();wide[f'places_{mode}_requested_function_diversity']=div.reindex(wide.index,fill_value=0).astype('int16')
        for family in families:
            cc=not_closed.loc[not_closed.function_group.eq(family)].groupby(uidcol).size();wide[f'places_{mode}_{family}_count']=cc.reindex(wide.index,fill_value=0).astype('int32')
        for signal in ['fap','school','market','ozon','wildberries']:
            cc=not_closed.loc[not_closed[f'name_signal_{signal}']].groupby(uidcol).size();wide[f'places_{mode}_name_signal_{signal}_count']=cc.reindex(wide.index,fill_value=0).astype('int32')
        for status in sorted(set(long.source_operating_status.unique())|{'unknown','open','permanently_closed'}):
            cc=target_all.loc[target_all.source_operating_status.eq(status)].groupby(uidcol).size();wide[f'places_{mode}_operating_{status}_count']=cc.reindex(wide.index,fill_value=0).astype('int32')
    wide['places_source_release']=RELEASE;wide['places_source_year']=2026
    wide['places_baseline_positive_listed_function_evidence']=wide.places_baseline_requested_function_count.gt(0)
    wide['places_baseline_link_unknown']=wide.places_baseline_all_categories_count.eq(0)
    wide['places_true_function_absence_established']=False
    wide['places_source_is_complete_facility_census']=False
    wide=wide.reset_index()
    save_parquet(wide,R/'places_settlement_features.parquet')
    wide.to_csv(R/'places_settlement_features.csv.gz',index=False,compression='gzip',chunksize=2500)
    long.groupby(['function_group','source_category'],dropna=False).size().rename('n_objects').reset_index().to_csv(R/'category_audit.csv',index=False)
    quality=long[['source_confidence','function_group','source_operating_status']].copy()
    quality['confidence_band']=pd.cut(quality.source_confidence,[-1,0,.5,.8,.95,1.0001],labels=['zero','gt0_to0p5','gt0p5_to0p8','gt0p8_to0p95','gt0p95_to1']).astype('string').fillna('unknown')
    quality.groupby(['function_group','source_operating_status','confidence_band'],dropna=False,observed=True).size().rename('n_objects').reset_index().to_csv(R/'source_quality_audit.csv',index=False)
    long.crosswalk_status.value_counts().rename_axis('status').reset_index(name='n_objects').to_csv(R/'crosswalk_status_audit.csv',index=False)
    make_audit(axis,long,wide,quarantine,acquisition['selected_rows'])

def make_audit(axis,long,wide,quarantine,selected_count):
    checks={'all142570uid_exactly_once':len(wide)==142570 and wide.id.is_unique and set(wide.id)==set(axis.id),'source_ids_unique':long.source_place_id.is_unique,'baseline_not_nearest_only':long.loc[long.baseline_uid.notna(),'crosswalk_status'].str.startswith('baseline_exact_address').all(),'unknown999_retained':int(long.function_group_code.eq(999).sum())==int(long.function_group.eq('unknown_999').sum()),'all_objects_preserved':len(long)==selected_count,'candidate_layers_do_not_overlap_per_object':long[['baseline_uid','conditional_uid','nearest_candidate_uid']].notna().sum(axis=1).le(1).all(),'external_geography_has_no_axis_assignment':long.loc[long.source_geography_scope.ne('axis_linkage_eligible'),['baseline_uid','conditional_uid','nearest_candidate_uid']].isna().all().all(),'quarantined_axis_coordinate_not_used':not any(set(long[c].dropna())&quarantine for c in ['baseline_uid','conditional_uid','nearest_candidate_uid']),'no_service_flows_invented':not long.external_service_catchment_observed.any(),'no_physical_operation_claim':not long.physical_operation_independently_verified.any(),'unknown_not_true_zero':not wide.places_true_function_absence_established.any()}
    counts={}
    for mode,uidcol in [('baseline','baseline_uid'),('conditional','conditional_uid'),('nearest_candidate','nearest_candidate_uid')]:
        x=long[long[uidcol].notna()];target=~x.function_group.isin(['outside_requested_functions','unknown_999']);closed=x.source_operating_status.eq('permanently_closed');counts[mode]={'objects':len(x),'unique_uid':x[uidcol].nunique(),'percent_of142570':100*x[uidcol].nunique()/142570,'requested_function_objects':int((target&~closed).sum()),'known_closed_requested_objects':int((target&closed).sum())}
    audit={'status':'PASS' if all(checks.values()) else 'FAIL','release':RELEASE,'source_objects':len(long),'functions':long.function_group.value_counts().to_dict(),'operating_status':long.source_operating_status.value_counts().to_dict(),'wide_rows':len(wide),'wide_columns':len(wide.columns),'counts':counts,'positive_baseline_uid':int(wide.places_baseline_positive_listed_function_evidence.sum()),'unknown_baseline_uid':int(wide.places_baseline_link_unknown.sum()),'true_zero_established_uid':0,'country_polygon_conflict_objects':int(long.country_polygon_conflict.sum()),'ambiguous_objects':int(long.crosswalk_status.str.startswith('ambiguous').sum()),'unresolved_objects':int(long[['baseline_uid','conditional_uid','nearest_candidate_uid']].isna().all(axis=1).sum()),'checks':checks,'axis_sha256':hashlib.sha256(AXIS.read_bytes()).hexdigest(),'outputs_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'places_objects_and_crosswalk.parquet',R/'places_settlement_features.parquet']},'scope':'Technical object-to-settlement identity crosswalk; baseline is not external centrality, catchment, capacity or independently observed operation. Counts include all published operating statuses, provided separately.'}
    base_ids=set(long.baseline_uid.dropna());conditional_ids=set(long.conditional_uid.dropna());candidate_ids=set(long.nearest_candidate_uid.dropna())
    audit.update(conditional_additional_uid_without_baseline=len(conditional_ids-base_ids),nearest_additional_uid_without_baseline_or_conditional=len(candidate_ids-base_ids-conditional_ids),source_geography_scope_counts=long.source_geography_scope.value_counts().to_dict(),source_country_value_counts=long.country_values.value_counts().to_dict(),source_ru_objects=int(long.source_country_ru.sum()),coarse_rus_mask_objects=int(long.coarse_naturalearth_rus_inside.sum()),quarantined_axis_uid_list=sorted(quarantine),source_country_and_coarse_mask_are_separate=True,primary_function_counts_exclude_reported_permanently_closed=True)
    audit['scope']='Technical object-to-settlement identity crosswalk. Published records including closed are retained in catalogue; primary function/name counts exclude permanently_closed, unknown operation stays unknown. Neither baseline nor proximity proves external centrality, catchment, capacity or independently observed operation.'
    def typed(v):
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v).__name__)
    encoded=json.dumps(audit,ensure_ascii=False,indent=2,default=typed)+'\n'
    pending=R/'AUDIT.json.partial';pending.write_text(encoded);pending.replace(R/'AUDIT.json');print(encoded);assert all(checks.values())

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--finalize-existing',action='store_true');args=parser.parse_args()
    if args.finalize_existing:
        axis=pd.read_parquet(AXIS);long=pd.read_parquet(R/'places_objects_and_crosswalk.parquet');wide=pd.read_parquet(R/'places_settlement_features.parquet')
        old=pd.read_csv(R.parents[1]/'anchor_research_20261019/model/documented_graph/service_edges_calculated.csv')
        quarantine=set(old.loc[old.geometry_status.eq('coordinate_conflict_quarantined'),'origin_uid'].dropna())
        make_audit(axis,long,wide,quarantine,json.loads((R/'ACQUISITION.json').read_text())['selected_rows'])
    else:main()

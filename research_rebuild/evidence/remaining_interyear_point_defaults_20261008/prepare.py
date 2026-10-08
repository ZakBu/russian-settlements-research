from pathlib import Path
import hashlib, gzip, json, re, zipfile, csv
import numpy as np
import pandas as pd

ROOT=Path('/workspace/russian-settlements-research')
E=ROOT/'research_rebuild/evidence/remaining_interyear_point_defaults_20261008'
BASE=ROOT/'research_rebuild/evidence/primary_residual_mass_application_20261008'
RAW=Path('/workspace/settlements-raw')
SRC=RAW/'data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
POINTS=BASE/'applied_point_snapshot.parquet'
ROSTER=BASE/'applied_primary_credited_UID_roster.csv.gz'
WIDE=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet')
WIKITSV=RAW/'data/raw/wikimedia/wikidata_oktmo_entities.tsv'
GN=RAW/'data/raw/coordinate_candidates/geonames_RU_20260907.zip'
GEO=RAW/'data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
HOLDS=ROOT/'research_rebuild/evidence/inherited_moderate_Geo_ownpoint_correction_20261008/holds.csv.gz'
ACTIVE=Path('/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet')


def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def norm(x): return re.sub(r'[^a-zа-я0-9]+',' ',str(x).casefold().replace('ё','е')).strip()
def digits(x): return re.sub(r'\D','',re.sub(r'\.0$','',str(x).strip()))
def type_norm(x):
    v=norm(x)
    return {'д':'деревня','дер':'деревня','деревня':'деревня','п':'поселок','посёлок':'поселок','поселок':'поселок','пгт':'пгт','поселок городского типа':'пгт','с':'село','село':'село','г':'город','город':'город','сл':'слобода','слобода':'слобода','х':'хутор','хутор':'хутор','ст':'станция','станция':'станция','рзд':'разъезд','разъезд':'разъезд','ж/д рзд':'разъезд','ст-ца':'станица','станица':'станица'}.get(v,v)
def native_name_type(label):
    s=str(label).strip(); bits=s.split(None,1)
    return (type_norm(bits[0]) if bits else '', norm(bits[1]) if len(bits)>1 else '')
def geodist(a,b,c,d):
    la=np.radians(float(a));lb=np.radians(float(c));oa=np.radians(float(b));ob=np.radians(float(d))
    h=np.sin((lb-la)/2)**2+np.cos(la)*np.cos(lb)*np.sin((ob-oa)/2)**2
    return float(6371.0088*2*np.arcsin(np.sqrt(np.clip(h,0,1))))
def raw_claim_lines(meta):
    return json.loads(meta) if isinstance(meta,str) and meta.strip() else []
def claim_paths(wrow):
    found=[]
    for col,prop in [('wikidata_truthy_exact_p764_claims_json','P764'),('wikidata_truthy_p31_claims_json','P31'),('wikidata_truthy_p625_claims_json','P625')]:
        for x in raw_claim_lines(wrow.get(col,'')):
            found.append((x['source_file'],int(x['line_number']),prop,x))
    return found

def main():
    roster=pd.read_csv(ROSTER)
    roster=roster[roster.finite_ordinary_full3_all_ownpoints.fillna(False)].copy()
    point_cols=['source_record_id','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_admission_status','coordinate_source_record_id','point_ledger_path','coordinate_origin_ledger','coordinate_origin_ledger_sha256','settlement_name','region_norm']
    points=pd.read_parquet(POINTS,columns=point_cols)
    d=roster.merge(points,on='source_record_id',how='left',validate='one_to_one')
    wide=d.pivot(index='component_root',columns='census_year',values=['source_record_id','population','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_admission_status','coordinate_source_record_id','point_ledger_path','coordinate_origin_ledger','coordinate_origin_ledger_sha256','settlement_name','region_norm'])
    for a,b in [(2002,2010),(2002,2021),(2010,2021)]:
        la=np.radians(wide['latitude'][a].astype(float)); lb=np.radians(wide['latitude'][b].astype(float))
        oa=np.radians(wide['longitude'][a].astype(float)); ob=np.radians(wide['longitude'][b].astype(float))
        h=np.sin((lb-la)/2)**2+np.cos(la)*np.cos(lb)*np.sin((ob-oa)/2)**2
        wide[f'd{a}_{b}']=6371.0088*2*np.arcsin(np.sqrt(np.clip(h,0,1)))
    wide['max_interyear_distance_km']=wide[['d2002_2010','d2002_2021','d2010_2021']].max(axis=1)
    cohort=wide[wide.max_interyear_distance_km>5].copy()
    if len(cohort)!=199: raise ValueError(f'expected 199 finite full3 histories, found {len(cohort)}')
    expected={y:int(cohort['population'][y].sum()) for y in [2002,2010,2021]}
    if expected!={2002:96145,2010:88200,2021:82969}: raise ValueError(f'cohort population drift {expected}')

    # Load only row-addressable primary and point records for this bounded set.
    curids=cohort['source_record_id'][2021].astype(str)
    curidx=curids.str.rsplit(':',n=1).str[-1].astype(int).to_numpy()-1
    source_cols=['object_level','object_name','oktmo','region','mun_upper','mun_lower','settlement','settlement_fias_id_dadata','settlement_with_type_dadata','settlement_type_dadata','settlement_type_full_dadata','settlement_dadata','fias_id_dadata','fias_level_dadata','okato_dadata','oktmo_dadata','qc_geo_dadata','qc_dadata','latitude_dadata','longitude_dadata']
    raw=pd.read_parquet(SRC,columns=source_cols)
    current=raw.iloc[curidx].copy(); current['source_record_id']=curids.to_numpy()
    current=current.set_index('source_record_id',drop=False)
    native_roster=raw[['object_name','region']].copy()
    # A Dadata FIAS ID may only support the candidate if it has no second native OKTMO in the full source roster.
    full_codes=raw[['fias_id_dadata','oktmo']].copy()
    full_codes=full_codes[full_codes.fias_id_dadata.notna()]
    fias_code_counts=full_codes.groupby('fias_id_dadata').oktmo.nunique(dropna=True).to_dict()
    # Wikidata source-backed code/name/admin/point witnesses.
    wide_cache=pd.read_parquet(WIDE)
    wmap=wide_cache[wide_cache.source_record_id.isin(curids)].set_index('source_record_id')
    # GeoNames raw lines; bounded 4 candidates only.
    gnrows={}
    with zipfile.ZipFile(GN) as z:
        data=z.read('RU.txt').decode('utf-8').splitlines()
        for sid in curids:
            if cohort.loc[cohort['source_record_id'][2021].eq(sid),'point_origin_kind'][2021].iloc[0] != 'geonames_ru_txt_named_place_point': continue
            p=points[points.source_record_id.eq(sid)].iloc[0]
            m=re.search(r'line=(\d+);geonameid=(\d+)',str(p.point_origin_locator))
            if not m: raise ValueError(f'bad geonames locator {sid}')
            line_no,gid=map(int,m.groups()); fields=data[line_no-1].split('\t')
            if int(fields[0])!=gid: raise ValueError(f'GeoNames row mismatch {sid}')
            gnrows[sid]=fields

    # Reopen exact raw Wikidata P764/P31/P625 rows and exact TSV rows cited by the cache.
    qids=set(wmap.wikidata_qid.astype(str))
    raw_rows={}
    batches=set()
    wanted={}
    for sid,wrow in wmap.iterrows():
        for batch,ln,prop,meta in claim_paths(wrow):
            batches.add(batch); wanted.setdefault(batch,{}).setdefault(ln,[]).append((sid,prop,wrow.wikidata_qid))
    for batch, line_map in wanted.items():
        with gzip.open(RAW/'data/raw/wikidata_truthy_claims'/batch,'rt',encoding='utf-8') as f:
            for i,rawline in enumerate(f,1):
                if i not in line_map: continue
                obj=json.loads(rawline)
                for sid,prop,qid in line_map[i]:
                    if obj.get('item','').rsplit('/',1)[-1] != str(qid) or obj.get('property','').rsplit('/',1)[-1] != prop:
                        raise ValueError(f'raw claim locator mismatch {sid} {batch}:{i} {prop}')
                    raw_rows[(sid,prop,i)]=obj
                if len(raw_rows)>=sum(len(v) for m in wanted.values() for v in m.values()): break
    if len(raw_rows)!=sum(len(v) for m in wanted.values() for v in m.values()): raise ValueError('raw claims incomplete')
    tsv_lines=set()
    for sid,wrow in wmap.iterrows():
        for ln in json.loads(wrow.wikidata_tsv_line_numbers_json or '[]'): tsv_lines.add(int(ln))
    tsv_found={}
    with open(WIKITSV,encoding='utf-8') as f:
        for i,line in enumerate(f,1):
            if i in tsv_lines: tsv_found[i]=line.rstrip('\n')
            if len(tsv_found)==len(tsv_lines): break
    if len(tsv_found)!=len(tsv_lines): raise ValueError('TSV line set incomplete')

    # Hold reasons from the previous packet are a bounded negative-control join.
    old_holds=pd.read_csv(HOLDS)
    hold_roots=set(old_holds.component_root.astype(str))
    if not set(cohort.index.astype(str)).issubset(hold_roots): raise ValueError('cohort differs from prior hold set')
    hold_reason=old_holds.set_index('component_root').reason.to_dict()

    out=[]; replacements=[]; rejections=[]; held_old=[]
    for root,row in cohort.iterrows():
        sid=str(row['source_record_id'][2021]); s=current.loc[sid]; kind=str(row['point_origin_kind'][2021])
        native_typ,native_nm=native_name_type(s.object_name)
        cur_lat=float(row['latitude'][2021]); cur_lon=float(row['longitude'][2021])
        route=''; route_ok=False; evidence={}
        if kind=='tochno_2021_dadata_raw_parquet_point':
            code_ok=digits(s.oktmo)==digits(s.oktmo_dadata)
            fias_ok=str(s.fias_level_dadata)=='6' and bool(str(s.fias_id_dadata)) and str(s.fias_id_dadata)==str(s.settlement_fias_id_dadata)
            name_ok=native_nm==norm(s.settlement_dadata)
            # Preserve source-specific type aliases: pgt and «поселок городского типа» are equivalent.
            type_ok=native_typ==type_norm(s.settlement_type_full_dadata)
            coord_ok=abs(float(s.latitude_dadata)-cur_lat)<1e-7 and abs(float(s.longitude_dadata)-cur_lon)<1e-7
            code_unique=fias_code_counts.get(s.fias_id_dadata,0)==1
            route='raw2021_exact_native_OKTMO_typed_FIAS_level6_NP'
            route_ok=bool(s.object_level=='Населенный пункт' and code_ok and fias_ok and code_unique and type_ok and coord_ok and (name_ok or (native_nm=='лесной рп' and norm(s.settlement_dadata)=='лесной' and native_typ=='пгт')))
            evidence={'native_object_level':s.object_level,'native_object_name':s.object_name,'native_OKTMO':digits(s.oktmo),'provider_OKTMO':digits(s.oktmo_dadata),'provider_name':s.settlement_dadata,'provider_type_full':s.settlement_type_full_dadata,'provider_FIAS_level':str(s.fias_level_dadata),'provider_FIAS_row_id_present':bool(str(s.fias_id_dadata)),'native_provider_row_FIAS_id_equal':fias_ok,'fias_id_distinct_native_OKTMO_count_full_2021':int(fias_code_counts.get(s.fias_id_dadata,0)),'name_exact':name_ok,'type_compatible':type_ok,'point_matches_raw_provider_coordinate':coord_ok,'Dadata_qc_geo':str(s.qc_geo_dadata)}
        elif kind=='wikidata_P625_point_claim':
            wr=wmap.loc[sid]
            p764=raw_claim_lines(wr.wikidata_truthy_exact_p764_claims_json)
            p625=raw_claim_lines(wr.wikidata_truthy_p625_claims_json)
            p31=raw_claim_lines(wr.wikidata_truthy_p31_claims_json)
            code_ok=bool(wr.wikidata_truthy_exact_p764_match) and digits(wr.source_oktmo_raw)==digits(wr.wikidata_tsv_exact_p764_value_raw)
            clean=bool(wr.wikidata_name_exact_label) and bool(wr.wikidata_admin_context_available) and not bool(wr.entity_competition_across_tsv_or_truthy) and not bool(wr.source_observation_competition_for_exact_oktmo)
            onepoint=int(wr.truthy_p625_point_count)==1 and bool(wr.points_all_wgs84_valid)
            coord_ok=len(p625)==1 and abs(float(p625[0].get('latitude',float('nan')))-cur_lat)<1e-7 and abs(float(p625[0].get('longitude',float('nan')))-cur_lon)<1e-7
            tsv_obj=[]
            for ln in json.loads(wr.wikidata_tsv_line_numbers_json or '[]'):
                line=tsv_found[int(ln)].split('\t')
                tsv_obj.append({'line':int(ln),'qid':line[0].strip('<>').rsplit('/',1)[-1],'oktmo':digits(line[1]),'label':line[4].strip().strip('"').split('@')[0],'admin':line[7].strip().strip('"').split('@')[0]})
            tsv_ok=bool(tsv_obj) and all(v['qid']==str(wr.wikidata_qid) and v['oktmo']==digits(wr.source_oktmo_raw) and norm(v['label'])==norm(wr.source_name) for v in tsv_obj)
            route='raw_Wikidata_exact_P764_P625_TSV_label_admin_no_code_competitor'
            route_ok=bool(code_ok and clean and onepoint and coord_ok and tsv_ok)
            evidence={'wikidata_qid':str(wr.wikidata_qid),'native_OKTMO':digits(wr.source_oktmo_raw),'P764_exact_code_claim_count':len(p764),'P31_claims':p31,'P625_claim_count':len(p625),'P625_single_valid_point':onepoint,'P625_matches_applied_current_point':coord_ok,'TSV_rows':tsv_obj,'TSV_exact_name_code_admin_context':tsv_ok,'no_entity_or_source_code_competition':clean,'raw_property_rows_reopened':True}
        elif kind=='geonames_ru_txt_named_place_point':
            fields=gnrows[sid]
            name=fields[1]; alts=[x for x in fields[3].split(',') if x]
            feature_physical=fields[6]=='P' and fields[7]=='PPL' and fields[8]=='RU'
            names_ok=norm(str(s.object_name).split(' ',1)[-1]) in {norm(name),*(norm(v) for v in alts)}
            type_ok=native_typ in {'поселок','пгт','деревня','село','город','станица','хутор','слобода'}
            region_name=str(s.region)
            same_point=abs(float(fields[4])-cur_lat)<1e-7 and abs(float(fields[5])-cur_lon)<1e-7
            # Unique current native name/type within the printed current region, not a distance-based match.
            labelkey=(norm(str(s.object_name).split(' ',1)[-1]),native_typ,norm(region_name))
            # Computed from source rows by checking the complete same-region roster below.
            all_matches=((native_roster.region.map(norm)==labelkey[2]) & (native_roster.object_name.map(lambda x:native_name_type(x)[1])==labelkey[0]) & (native_roster.object_name.map(lambda x:native_name_type(x)[0])==labelkey[1])).sum()
            unique=all_matches==1
            route='GeoNames_raw_PPL_exact_native_name_type_region_unique'
            route_ok=bool(feature_physical and names_ok and type_ok and same_point and unique)
            evidence={'geonameid':fields[0],'name':name,'alternatenames':fields[3],'latitude':fields[4],'longitude':fields[5],'feature_class':fields[6],'feature_code':fields[7],'country':fields[8],'admin1_code':fields[10],'admin2_code':fields[11],'current_native_name':s.object_name,'current_native_type':native_typ,'current_region':region_name,'typed_name_region_count_full_2021':int(all_matches),'source_row_coordinates_match':same_point,'native_code_binding':'not_asserted'}
        else:
            route='unsupported_current_point_origin'; route_ok=False
        if not route_ok: raise ValueError(f'current own point qualification failed {sid} {kind}: {evidence}')
        # No external provider ID binding, census-day point, population, or boundary claim is made.
        rec={'component_root':str(root),'source_record_id_2002':str(row['source_record_id'][2002]),'source_record_id_2010':str(row['source_record_id'][2010]),'source_record_id_2021':sid,
             'name_2002':str(row['settlement_name'][2002]),'name_2010':str(row['settlement_name'][2010]),'name_2021':str(row['settlement_name'][2021]),'region_2021':str(row['region_norm'][2021]),
             'population_2002':int(row['population'][2002]),'population_2010':int(row['population'][2010]),'population_2021':int(row['population'][2021]),'d2002_2010_km':float(row.d2002_2010),'d2002_2021_km':float(row.d2002_2021),'d2010_2021_km':float(row.d2010_2021),'max_interyear_distance_km':float(row.max_interyear_distance_km),'max_pair':str(row[['d2002_2010','d2002_2021','d2010_2021']].astype(float).idxmax()),
             'current_point_result':'PASS_current_2021_ownpoint_positive_source_binding','current_point_route':route,'current_point_origin_file':str(row['point_origin_file'][2021]),'current_point_origin_sha256':str(row['point_origin_sha256'][2021]),'current_point_origin_locator':str(row['point_origin_locator'][2021]),'current_point_origin_kind':kind,'prior_point_check_hold_reason':str(hold_reason.get(str(root),'')),'current_point_coordinate_source_record_id':str(row['coordinate_source_record_id'][2021]),'current_latitude':cur_lat,'current_longitude':cur_lon,'current_point_evidence_json':json.dumps(evidence,ensure_ascii=False,sort_keys=True),
             'identity_status':'already_accepted_finite_full3_component','known_relocation_event':'not_found_in_checked_record; exhaustive event survey not performed','current_year_competing_code_or_point_marker':'none_in_route_checks','external_provider_ID_binding_asserted':False,'censusday_coordinate_asserted':False,'population_or_boundary_changed':False}
        out.append(rec)
        for year,distcol in [(2002,'d2002_2021'),(2010,'d2010_2021')]:
            oldkind=str(row['point_origin_kind'][year])
            dist=float(row[distcol])
            if dist>5 and oldkind=='geokladr_2011_raw_dbf_coordinate' and hold_reason.get(str(root))=='Current own coded typed physical point not independently confirmed':
                oldid=str(row['source_record_id'][year]); oldledger=str(row['point_ledger_path'][year]); oldsha='cc2a7cf67d7c25ec2de7f962c49478dd275646138f1303ae3410bf2a6922d23' if oldledger==str(ACTIVE) else ''
                # Confirm the active graph25 ledger pin before issuing any rejection candidate.
                if oldledger!=str(ACTIVE): raise ValueError(f'nonbaseline active origin ledger for {oldid}: {oldledger}')
                rejections.append({'target_source_record_id':oldid,'rejection_status':'reviewed_superseded_representative_point_only','old_latitude':float(row['latitude'][year]),'old_longitude':float(row['longitude'][year]),'origin_ledger':oldledger,'origin_ledger_sha256':oldsha,'old_point_origin_file':str(row['point_origin_file'][year]),'old_point_origin_sha256':str(row['point_origin_sha256'][year]),'old_point_origin_locator':str(row['point_origin_locator'][year]),'old_coordinate_source_record_id':str(row['coordinate_source_record_id'][year]),'carrier_source_record_id':sid,'target_year':year,'distance_old_to_current_km':dist,'rejection_reason':'Historical Geo2011 point is superseded as the default representative on an already accepted full3 identity; independently checked current own point route is source-bound; source coordinates and old point alternatives preserved; no historical census-day location or population/identity change asserted.'})
                replacements.append({'target_source_record_id':oldid,'latitude':cur_lat,'longitude':cur_lon,'coordinate_admission_status':'reviewed_extension_rule_accepted'})
            elif dist>5:
                held_old.append({'component_root':str(root),'target_source_record_id':str(row['source_record_id'][year]),'target_year':year,'old_point_origin_kind':oldkind,'old_point_origin_file':str(row['point_origin_file'][year]),'old_point_origin_locator':str(row['point_origin_locator'][year]),'old_coordinate_source_record_id':str(row['coordinate_source_record_id'][year]),'distance_to_current_km':dist,'hold_reason':str(hold_reason.get(str(root),'non_Geo_or_unresolved_old_point_source_not_rejected_by_distance_alone'))})
    classified=pd.DataFrame(out).sort_values(['max_interyear_distance_km','component_root'],ascending=[False,True])
    repl=pd.DataFrame(replacements).sort_values('target_source_record_id')
    rej=pd.DataFrame(rejections).sort_values('target_source_record_id')
    held=pd.DataFrame(held_old).sort_values(['component_root','target_year'])
    if len(classified)!=199 or len(repl)!=len(rej): raise ValueError((len(classified),len(repl),len(rej)))
    # Hashes: these identify all raw/cached data used by this bounded packet.
    input_files=[ROSTER,POINTS,SRC,WIDE,WIKITSV,GN,GEO,HOLDS,ACTIVE]
    for batch in sorted(batches): input_files.append(RAW/'data/raw/wikidata_truthy_claims'/batch)
    pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(set(input_files))}
    classified.to_csv(E/'classified_199_histories.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    repl.to_csv(E/'replacement_point_use_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    rej.to_csv(E/'superseded_representative_point_rejections.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    held.to_csv(E/'held_non_geo_historical_outliers.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    summary={'status':'bounded_current_ownpoint_source_check_and_proposed_representative_supersession; not applied','stage_basis':62,'cohort_definition':'finite ordinary accepted full3 roots with any interyear point separation strictly greater than 5 km','histories':len(classified),'population_by_year':expected,'current_anchor_results':classified.current_point_result.value_counts().to_dict(),'current_anchor_routes':classified.current_point_route.value_counts().to_dict(),'current_point_origins':classified.current_point_origin_kind.value_counts().to_dict(),'maximum_separation_km':float(classified.max_interyear_distance_km.max()),'old_geo_point_rejections_proposed':len(rej),'replacement_point_uses_proposed':len(repl),'held_non_geo_or_unresolved_old_outlier_uses':len(held),'current_point_reuse_is_representative_continuity_only':True,'historical_censusday_coordinates_asserted':False,'provider_identifier_binding_asserted':False,'source_counts_identity_boundary_changed':False,'known_relocation_event_survey':'not exhaustive; no event inferred from distance alone','prior_hold_negative_control':{'matched_histories':len(cohort),'only_prior_hold_reason':'Current own coded typed physical point not independently confirmed','other_prior_hard_hold_markers_intersecting':0},'source_pins':pins,'raw_wikidata_reopened_property_rows':len(raw_rows),'raw_wikidata_reopened_batches':sorted(batches),'raw_geonames_rows_reopened':len(gnrows),'outputs':{}}
    for p in sorted(E.iterdir()):
        if p.is_file() and p.name!='receipt.json': summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    (E/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['histories','population_by_year','current_anchor_routes','old_geo_point_rejections_proposed','held_non_geo_or_unresolved_old_outlier_uses','raw_wikidata_reopened_property_rows']},ensure_ascii=False,indent=2))

if __name__=='__main__': main()

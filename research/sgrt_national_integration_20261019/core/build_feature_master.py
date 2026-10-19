#!/usr/bin/env python3
"""Materialize nationwide settlement features by audited left one-to-one joins.

Original census/identity fields are byte-value preserved. Registered organization
and delivery-location witnesses are attributes, not demonstrated catchments.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,platform,time,sys,shlex,tempfile,os
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
WORK=ROOT.parent
PREVIOUS=WORK/'functional_dynamics_20261019'
AXIS=WORK/'anchor_research_20261019/data/point_axis.parquet'
ANNUAL=PREVIOUS/'economy/pinned_calendar/point_exact_code_witnesses_2011_2025.parquet'
TRAJECTORY=PREVIOUS/'economy/pinned_calendar/point_witness_trajectories_2011_2025.parquet'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()

def fsync_file(path):
    with open(path,'rb') as f:os.fsync(f.fileno())

def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

class Assembly:
    def __init__(self,axis):
        self.axis=axis
        self.frame=axis.copy()
        self.inputs={};self.joins=[];self.dictionary=[];self.coverage=[]
        self.track(AXIS)
        for c in axis.columns:self.dictionary.append(dict(column=c,layer='original_64_field_axis',source_path=str(AXIS.relative_to(WORK)),source_columns=c,evidence_class='original_identity_or_population_context',unit='see_original_source_metadata',comment='Original field retained unchanged; census zeros are not missing'))
        for y in [1989,2002,2010,2021]:
            p=axis[f'population_{y}']
            self.coverage.append(dict(layer='original_census_common_cohort',year=y,rows=len(axis),uid_with_observed_population=int(p.notna().sum()),uid_with_zero_population=int(p.eq(0).sum()),uid_population_missing=int(p.isna().sum()),population_sum_in_observed_cohort=float(p.sum()),interpretation='partial1989_reference_only_not_complete_historical_RF' if y==1989 else 'population_in_frozen_common_settlement_cohort_not_complete_country_total'))

    def track(self,path):
        path=Path(path)
        if str(path) not in self.inputs:self.inputs[str(path)]=dict(sha256=sha(path),bytes=path.stat().st_size)

    def join(self,features,name,source_paths,source_columns=None,comment=''):
        assert 'id' in features and features.id.notna().all() and features.id.is_unique,(name,'nonunique_or_missing_key')
        assert set(features.id)<=set(self.axis.id),(name,'keys_outside_frozen_axis')
        before=len(self.frame);oldcols=list(self.frame.columns)
        common=[c for c in features if c!='id' and c in self.frame]
        if common:
            left=self.frame.set_index('id')[common].reindex(features.id).reset_index(drop=True)
            right=features[common].reset_index(drop=True)
            pd.testing.assert_frame_equal(left,right,check_dtype=False,check_exact=True)
        addition=features.drop(columns=common)
        self.frame=self.frame.merge(addition,on='id',how='left',sort=False,validate='one_to_one')
        assert len(self.frame)==before==142570
        assert self.frame.id.equals(self.axis.id)
        for p in source_paths:self.track(p)
        for c in addition:
            if c=='id':continue
            evidence='registered_organization_witness' if name.startswith('econom') else ('coordinate_candidate_not_confirmed_place_identity' if (name.startswith('wb') or name.startswith('places')) and 'candidate' in c else 'conditional_source_location_link_not_baseline' if 'conditional' in name or 'conditional' in c else 'source_name_coordinate_location_witness' if name.startswith('wb') or name.startswith('places') else 'municipal_context' if name.startswith('agri') else 'derived_witness_trajectory')
            unit='nominal_thousand_rub' if 'thousand_rub' in c else ('hectares' if '_ha' in c else 'ratio_or_fraction' if 'share' in c else 'source_record_or_location_count' if c.endswith(('_locations','_legal_entities','_reporting_entities')) else 'see_feature_name_and_layer_README')
            self.dictionary.append(dict(column=c,layer=name,source_path='|'.join(str(Path(p).relative_to(WORK)) for p in source_paths),source_columns=(source_columns or {}).get(c,c),evidence_class=evidence,unit=unit,comment=comment))
        self.joins.append(dict(layer=name,rows_before=before,input_rows=len(features),matched_uid_count=int(self.axis.id.isin(features.id).sum()),rows_after=len(self.frame),columns_added=len(addition.columns)-1,existing_columns_verified=len(common),row_order_preserved=True,join='left_one_to_one'))
        print(f'Joined {name}: {self.frame.shape}; verified {len(common)} shared columns exactly',flush=True)
        return len(addition.columns)-1

def native_economy(a):
    # Inspect schema before column selection; all other raw organization columns stay unread.
    cols=pq.ParquetFile(ANNUAL).schema.names
    metrics=[c for c in cols if c.endswith('_legal_entities') or c in ['legal_entities','direct_consumer_function_diversity']]
    selected=['id','year','quality_mode','witness_status']+metrics
    d=pd.read_parquet(ANNUAL,columns=selected)
    assert len(d)==142570*15 and set(d.year)==set(range(2011,2026))
    assert not d.duplicated(['id','year']).any()
    assert set(d.quality_mode)=={'exact_settlement_code_only'}
    assert not d[metrics].isna().any().any() and d[metrics].ge(0).all().all()
    assert d.groupby('year').id.nunique().eq(142570).all()
    # Pivot numeric and textual blocks independently: mixing them would coerce
    # every count to object dtype before Parquet round-trip.
    wide=d.pivot(index='id',columns='year',values=metrics)
    wide.columns=[f'econ_native_{int(y)}_{c}' for c,y in wide.columns]
    status=d.pivot(index='id',columns='year',values='witness_status')
    status.columns=[f'econ_native_{int(y)}_witness_status' for y in status.columns]
    wide=pd.concat([wide,status],axis=1)
    wide=wide.reindex(a.axis.id).reset_index()
    wide['econ_native_quality_mode']='exact_settlement_code_only'
    info=PREVIOUS/'economy/RFSD_PINNED_DATASET_INFO.json'
    a.track(info)
    wide['econ_native_dataset_revision']=json.loads(info.read_text())['sha']
    wide['econ_native_geography_status']='year_specific_legal_codes_projected_to_frozen2021_settlement_dictionary_not_historical_boundaries'
    mapping={f'econ_native_{y}_{c}':f'{c};year={y};quality_mode=exact_settlement_code_only' for y in range(2011,2026) for c in metrics+['witness_status']}
    mapping.update(econ_native_quality_mode='quality_mode',econ_native_dataset_revision='RFSD_PINNED_DATASET_INFO.json:sha',econ_native_geography_status='analysis_metadata:frozen2021_code_dictionary_projection')
    a.join(wide,'economy_native_15_years',[ANNUAL,info],source_columns=mapping,comment='Pinned RFSD release; exact frozen settlement-code projection. Zero means no accepted registration witness, not absence of a physical function; no jobs/catchments inferred.')
    for y in range(2011,2026):
        yy=d[d.year.eq(y)]
        assert a.frame[f'econ_native_{y}_legal_entities'].sum()==yy.legal_entities.sum()
        a.coverage.append(dict(layer='economy_native',year=y,rows=len(yy),uid_with_registered_entities=int(yy.legal_entities.gt(0).sum()),uid_with_direct_consumer_witness=int(yy.direct_consumer_function_diversity.gt(0).sum()),registered_entity_count=int(yy.legal_entities.sum()),interpretation='registration_witness_not_physical_function_or_employment'))
    del d,wide
    t=pd.read_parquet(TRAJECTORY)
    ignore={'id','name','region','lat','lon','population_2010','population_2021','population_bin_2021'}
    tc=[c for c in t if c not in ignore]
    t=t[['id']+tc].rename(columns={c:'econ_native_trajectory_'+c for c in tc})
    a.join(t,'economy_native_trajectory',[TRAJECTORY],source_columns={'econ_native_trajectory_'+c:c for c in tc},comment='Trajectories of accepted registration witnesses on a constant point-code axis; no automatic physical opening/closure.')
    for y in [2021,2025]:
        p=PREVIOUS/f'economy/pinned_sector_calendar/point_sector_witnesses_{y}.parquet'
        cols=pq.ParquetFile(p).schema.names
        metrics=[c for c in cols if c not in ['id','year','quality_mode']]
        e=pd.read_parquet(p,columns=['id','year','quality_mode']+metrics)
        assert set(e.year)=={y} and set(e.quality_mode)=={'exact_settlement_code_only'}
        e=e.drop(columns=['year','quality_mode']).rename(columns={c:f'econ_native_{y}_{c}' for c in metrics})
        a.join(e,f'economy_native_sections_{y}',[p],source_columns={f'econ_native_{y}_{c}':f'{c};year={y}' for c in metrics},comment='21 OKVED sections of registered legal organizations, not physical employment or functional catchments.')

def fallback_wb(a):
    p=PREVIOUS/'marketplaces/wb_delivery_locations_ru_20261019.parquet'
    d=pd.read_parquet(p,columns=['object_id','typePoint','settlement_uid','focus_scope','observed_date','link_status'])
    assert d.object_id.is_unique
    resolved=d[d.settlement_uid.notna()].copy()
    assert set(resolved.settlement_uid)<=set(a.axis.id)
    # Keep all delivery subtypes separate. Types 8/34 are one explicit narrow scenario.
    c=pd.crosstab(resolved.settlement_uid,resolved.typePoint)
    c.columns=[f'wb_source_type_{int(k)}_count_20261019' for k in c.columns]
    c=c.reindex(a.axis.id,fill_value=0)
    c['wb_all_published_delivery_location_count_20261019']=c.sum(axis=1)
    focus=resolved[resolved.focus_scope.eq(True)].groupby('settlement_uid').size()
    c['wb_focus_type8_34_count_20261019']=focus.reindex(c.index,fill_value=0)
    c=c.astype('int32').reset_index().rename(columns={'settlement_uid':'id'})
    if 'id' not in c:c=c.rename(columns={c.columns[0]:'id'})
    a.join(c,'wb_fallback_all_types',[p],comment='Provider source_country=ru partition, not a national boundary mask. Names+coordinates linkage; all types separate, no equivalence to public pickup assumed. Zero means no linked accepted witness, not physical absence. Observation2026-10-19, not opening date.')
    assert a.frame.wb_all_published_delivery_location_count_20261019.sum()==len(resolved)
    a.coverage.append(dict(layer='wb_fallback',year=2026,rows=len(d),linked_source_locations=len(resolved),unlinked_or_ambiguous_source_locations=len(d)-len(resolved),uid_with_delivery_location=resolved.settlement_uid.nunique(),source_partition='ru_not_territorial_boundary_mask'))

def build(out,csv=True):
    start=datetime.now(timezone.utc).isoformat();tick=time.monotonic();out.mkdir(parents=True,exist_ok=True)
    producer_sha=sha(__file__)
    axis=pd.read_parquet(AXIS)
    assert axis.shape==(142570,64) and axis.id.is_unique and axis.id.notna().all()
    a=Assembly(axis)
    print('Loaded original142570×64 axis',flush=True)
    native_economy(a)
    print(f'Native RFSD15years and sections assembled: {a.frame.shape}',flush=True)
    econ=ROOT/'economy/economy_features.parquet'
    if econ.exists():
        a.track(econ)
        a.join(pd.read_parquet(econ),'economy_extended',[econ],comment='Additional sensitivity/registered finance fields; native overlap must agree exactly. Read economy audit for mode/date/unit definitions.')
    wb=ROOT/'services/wb_settlement_features.parquet'
    if wb.exists():
        a.track(wb)
        a.join(pd.read_parquet(wb),'wb_national_all_types',[wb],comment='Root national provider-location package, separate subtypes and linkage uncertainty; no external flow demonstrated.')
        a.coverage.append(dict(layer='wb_national_all_types',year=2026,rows=len(a.frame),uid_with_strict_location=int(a.frame.wb_strict_all_types_locations.gt(0).sum()),strict_location_count=int(a.frame.wb_strict_all_types_locations.sum()),uid_with_coordinate_candidate_location=int(a.frame.wb_coordinate_candidate_all_types_locations.gt(0).sum()),coordinate_candidate_layer_location_count=int(a.frame.wb_coordinate_candidate_all_types_locations.sum()),interpretation='strict_and_nearest_coordinate_candidate_separate_not_observed_service_flows'))
    else:fallback_wb(a)
    relaxed=ROOT/'services/wb_name_relaxed_features.parquet'
    if relaxed.exists():
        a.track(relaxed);relaxed_features=pd.read_parquet(relaxed)
        if relaxed_features.wb_name_relaxed_additional_locations.sum()>0:
            a.join(relaxed_features,'wb_name_relaxed_conditional',[relaxed],comment='Conditional same-name/coordinate link with relaxed settlement-type label; inclusive baseline+conditional counts retained separately from strict baseline, not confirmed consumer flows.')
            a.coverage.append(dict(layer='wb_name_relaxed_conditional',year=2026,rows=len(a.frame),conditional_additional_source_locations=int(a.frame.wb_name_relaxed_additional_locations.sum()),uid_receiving_additional_conditionally_linked_locations=int(a.frame.wb_name_relaxed_additional_locations.gt(0).sum()),uid_with_inclusive_location=int(a.frame.wb_name_relaxed_inclusive_all_types_locations.gt(0).sum()),interpretation='conditional_linkage_sensitivity_not_replacement_of_strict_source_identity'))
    agri=ROOT/'agriculture/point_municipal_agriculture.parquet'
    if agri.exists():
        a.track(agri)
        a.join(pd.read_parquet(agri),'agriculture_municipal_context',[agri],comment='Native municipal context attached to points. Repeated municipal values must not be summed over settlements or treated as measured settlement specialization.')
        a.coverage.append(dict(layer='agriculture_municipal_context',year=2021,rows=len(a.frame),uid_with_municipal_series=int(a.frame.agri_municipality_series_matched.sum()),uid_with_2021_profile=int(a.frame.agri_profile2021_covered.sum()),uid_with_latest_crop_observation=int(a.frame.agri_latest_crop_observed.sum()),uid_with_production_observation=int(a.frame.agri_production_observed.sum()),interpretation='context_replicated_by_municipality_not_point_measurement_or_sum_over_points'))
    places=ROOT/'places/places_settlement_features.parquet'
    if places.exists():
        a.track(places)
        a.join(pd.read_parquet(places),'places_physical_location_witnesses',[places],comment='Published physical-place evidence; baseline/conditional/coordinate-candidate modes remain separate, and locations do not establish external service flows. Check release, category and coverage audits.')
    # Critical conservation: compare all original fields, including zero census values,
    # original missingness and source metadata, to the untouched source dataframe.
    pd.testing.assert_frame_equal(a.frame[axis.columns],axis,check_exact=True)
    assert not a.frame.columns.duplicated().any()
    for p,record in a.inputs.items():assert sha(p)==record['sha256'],f'Input changed during assembly: {p}'
    frame=a.frame
    frame.attrs={'role':'national_settlement_feature_master_not_demonstrated_SGRT','original_columns':list(axis.columns),'sources':a.inputs,'row_key':'id','original_rows':142570}
    pqpath=out/'feature_master.parquet'
    with tempfile.NamedTemporaryFile(dir=out,prefix='.feature_master_',suffix='.parquet',delete=False) as f:temp_parquet=Path(f.name)
    frame.to_parquet(temp_parquet,index=False,compression='zstd',row_group_size=50000)
    fsync_file(temp_parquet);fsync_dir(out)
    readback=pd.read_parquet(temp_parquet)
    pd.testing.assert_frame_equal(frame,readback,check_exact=True)
    print(f'Parquet written and every cell read back exactly: {frame.shape}',flush=True)
    outputs={'feature_master.parquet':{'bytes':temp_parquet.stat().st_size,'sha256':sha(temp_parquet)}}
    if csv:
        cp=out/'feature_master.csv.gz'
        with tempfile.NamedTemporaryFile(dir=out,prefix='.feature_master_',suffix='.csv.gz',delete=False) as f:temp_csv=Path(f.name)
        frame.to_csv(temp_csv,index=False,compression={'method':'gzip','compresslevel':3},chunksize=10000)
        fsync_file(temp_csv)
        # CSV is an interchange copy: typed authoritative source remains Parquet.
        csvkeys=pd.read_csv(temp_csv,usecols=['id'])
        assert csvkeys.id.equals(axis.id)
        temp_csv.replace(cp)
        fsync_dir(out)
        outputs[cp.name]={'bytes':cp.stat().st_size,'sha256':sha(cp),'key_order_readback':'PASS'}
        print(f'CSV.gz written and all142570 keys/order checked: {cp.stat().st_size}bytes',flush=True)
    pd.DataFrame(a.dictionary).to_csv(out/'feature_dictionary.csv',index=False)
    pd.DataFrame(a.coverage).to_csv(out/'coverage_audit.csv',index=False)
    pd.DataFrame(a.joins).to_csv(out/'join_audit.csv',index=False)
    schema={'rows':len(frame),'columns':len(frame.columns),'key':'id','fields':[{'name':field.name,'arrow_type':str(field.type),'nullable':field.nullable,'pandas_dtype':str(frame[field.name].dtype)} for field in pq.read_schema(temp_parquet)]}
    (out/'SCHEMA.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2))
    # Publish the binary last: a previous environment-level local-file truncation
    # happened only after streaming another large artifact. Flush both file and
    # containing directory and verify the FINAL pathname from a fresh open.
    fsync_file(temp_parquet);temp_parquet.replace(pqpath);fsync_dir(out)
    final_readback=pd.read_parquet(pqpath)
    pd.testing.assert_frame_equal(frame,final_readback,check_exact=True)
    assert sha(pqpath)==outputs['feature_master.parquet']['sha256']
    assert sha(__file__)==producer_sha,'Producer code changed during run; rerun the frozen version'
    layers={j['layer'] for j in a.joins}
    audit=dict(status='PASS',rows=len(frame),columns=len(frame.columns),producer_sha256=producer_sha,original_rows=142570,original_columns=64,cohort_scope='frozen_common_reference142570_settlement_axis_not_all_settlements_of_every_year_or_all_territories',all_original_fields_exactly_preserved=True,all_original_zero_values_preserved=True,unique_nonnull_id=True,one_row_per_original_settlement=True,new_spatial_assignments_performed_by_core=0,source_coordinate_candidate_features_retained_separately='wb_national_all_types' in layers,features_are_demonstrated_sgrt=False,authoritative_format='Parquet',missing_agriculture_module='agriculture_municipal_context' not in layers,extended_economy_module='economy_extended' in layers,root_wb_module='wb_national_all_types' in layers,wb_name_relaxed_conditional_module='wb_name_relaxed_conditional' in layers,places_module='places_physical_location_witnesses' in layers,inputs={str(Path(p).relative_to(WORK)):v for p,v in a.inputs.items()},joins=a.joins,outputs=outputs,parquet_all_cells_exact_readback=True)
    (out/'MASTER_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    receipt={'started_utc':start,'finished_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-tick,'actual_command':shlex.join(['python']+sys.argv),'exit_status':'PASS','rows':len(frame),'columns':len(frame.columns),'python':platform.python_version(),'pandas':pd.__version__,'outputs':outputs}
    (out/'ACTUAL_COMMAND_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    fsync_file(out/'MASTER_AUDIT.json');fsync_file(out/'ACTUAL_COMMAND_RECEIPT.json');fsync_dir(out)
    assert pq.ParquetFile(pqpath).metadata.num_rows==142570
    assert sha(pqpath)==outputs['feature_master.parquet']['sha256'],'Published Parquet changed after final receipt'
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out-dir',type=Path,default=HERE);ap.add_argument('--no-csv',action='store_true');arg=ap.parse_args();build(arg.out_dir,csv=not arg.no_csv)

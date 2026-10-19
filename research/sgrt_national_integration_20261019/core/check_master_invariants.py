#!/usr/bin/env python3
"""Substantive readback checks of nationwide joins, zeros, finance and axis support."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

H=Path(__file__).resolve().parent;ROOT=H.parent;W=ROOT.parent

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()

def blocks(cols,size=16):
    for i in range(0,len(cols),size):yield cols[i:i+size]

def check():
    master=H/'feature_master.parquet';schema=pq.read_schema(master);names=schema.names
    audit=json.loads((H/'MASTER_AUDIT.json').read_text());checks=[]
    def yes(n,b):checks.append({'name':n,'pass':bool(b)});assert b,n
    ids=pd.read_parquet(master,columns=['id']).id
    axispath=W/'anchor_research_20261019/data/point_axis.parquet';axiscols=pq.read_schema(axispath).names
    axisids=pd.read_parquet(axispath,columns=['id']).id
    yes('142570_rows_nonnull_unique_original_uid',len(ids)==142570 and ids.notna().all() and ids.is_unique and ids.equals(axisids))
    for cols in blocks(axiscols):pd.testing.assert_frame_equal(pd.read_parquet(master,columns=cols),pd.read_parquet(axispath,columns=cols),check_exact=True)
    yes('all64_original_fields_exact',True)
    for y in [2002,2010,2021]:
        c=f'population_{y}';yes(f'original_{y}_zeros_preserved',pd.read_parquet(master,columns=[c])[c].eq(0).equals(pd.read_parquet(axispath,columns=[c])[c].eq(0)))
    yes('column_names_unique',len(names)==len(set(names)))
    for p,v in audit['inputs'].items():yes('current_input_sha:'+p,sha(W/p)==v['sha256'])
    for name,path in [('economy',ROOT/'economy/economy_features.parquet'),('wb',ROOT/'services/wb_settlement_features.parquet'),('wb_name_relaxed_conditional',ROOT/'services/wb_name_relaxed_features.parquet'),('agri',ROOT/'agriculture/point_municipal_agriculture.parquet'),('places',ROOT/'places/places_settlement_features.parquet')]:
        if not path.exists():continue
        fids=pd.read_parquet(path,columns=['id']).id
        yes(name+'_one_row_per_reference_uid',fids.is_unique and set(fids)==set(ids))
        order=pd.Index(fids).get_indexer(ids)
        for cols in blocks([c for c in pq.read_schema(path).names if c!='id']):
            left=pd.read_parquet(master,columns=cols);right=pd.read_parquet(path,columns=cols).iloc[order].reset_index(drop=True)
            pd.testing.assert_frame_equal(left,right,check_dtype=False,check_exact=True)
            del left,right
        yes(name+'_every_joined_cell_exact',True)
    annual=W/'functional_dynamics_20261019/economy/pinned_calendar/point_exact_code_witnesses_2011_2025.parquet'
    metrics=[c for c in pq.read_schema(annual).names if c.endswith('_legal_entities') or c in ['legal_entities','direct_consumer_function_diversity','witness_status']]
    for y in range(2011,2026):
        f=pd.read_parquet(annual,columns=['id']+metrics,filters=[('year','=',y)]).set_index('id').reindex(ids)
        f.columns=[f'econ_native_{y}_{c}' for c in f.columns]
        pd.testing.assert_frame_equal(pd.read_parquet(master,columns=list(f.columns)),f.reset_index(drop=True),check_dtype=False,check_exact=True)
        yes(f'native_{y}_every_uid_metric_and_witness_status_exact',True);del f
    for amount in [c for c in names if c.startswith('econ_') and c.endswith('_thousand_rub')]:
        prefix=amount.removesuffix('_thousand_rub');n=prefix+'_reporting_entities';known=prefix+'_known'
        if n not in names:continue
        cols=[amount,n]+([known] if known in names else []);d=pd.read_parquet(master,columns=cols)
        yes(amount+'_unreported_is_null',d.loc[d[n].eq(0),amount].isna().all())
        if known in d:yes(amount+'_known_flag_consistent_with_reporting_count',d[known].eq(d[n].gt(0)).all())
    for mode in ['strict','coordinate_candidate']:
        total=f'wb_{mode}_all_types_locations';types=[c for c in names if c.startswith(f'wb_{mode}_type_') and c.endswith('_locations')]
        if total not in names:continue
        d=pd.read_parquet(master,columns=types+[total,f'wb_{mode}_focus_types_locations'])
        yes('wb_'+mode+'_type_counts_conserve_all_locations',np.array_equal(d[types].sum(axis=1).to_numpy(),d[total].to_numpy()))
        yes('wb_'+mode+'_focus_8_34_separate',np.array_equal(d[f'wb_{mode}_focus_types_locations'].to_numpy(),(d[f'wb_{mode}_type_8_locations']+d[f'wb_{mode}_type_34_locations']).to_numpy()))
    dictionary=pd.read_csv(H/'feature_dictionary.csv');yes('one_dictionary_entry_per_feature',len(dictionary)==len(names) and dictionary.column.is_unique and set(dictionary.column)==set(names))
    if 'wb_name_relaxed_additional_locations' in names:
        d=pd.read_parquet(master,columns=['wb_name_relaxed_inclusive_all_types_locations','wb_strict_all_types_locations','wb_name_relaxed_additional_locations'])
        yes('wb_conditional_additions_do_not_overwrite_baseline',np.array_equal(d.wb_name_relaxed_inclusive_all_types_locations.to_numpy(),(d.wb_strict_all_types_locations+d.wb_name_relaxed_additional_locations).to_numpy()))
    ext=H/'feature_master_extended142572.parquet'
    if ext.exists():
        t=pq.read_table(ext,columns=['id','axis_kind'])
        yes('extended142572_unique_uid',len(t)==142572 and len(set(t.column('id').to_pylist()))==142572)
        yes('extended_exact_two_territorial_rows',t.column('axis_kind').to_pylist().count('federal_city_territory_aggregate')==2)
        for cols in blocks(names):
            a=pq.read_table(ext,columns=cols).slice(0,142570).replace_schema_metadata(None);b=pq.read_table(master,columns=cols).replace_schema_metadata(None)
            assert a.equals(b),cols;del a,b
        yes('extended_original_values_and_arrow_types_exact',True)
        p=pq.ParquetFile(ext);last=p.num_row_groups-1;last_n=p.metadata.row_group(last).num_rows
        for cols in blocks([c for c in names if c.startswith('econ_native_')]):
            tail=p.read_row_group(last,columns=cols).slice(last_n-2,2)
            assert all(tail.column(c).null_count==2 for c in cols)
        yes('federal_all_native_fields_unknown_not_zero',True)
    result={'status':'PASS','verification_mode':'all_values_checked_in16_column_blocks','checks_passed':len(checks),'checks_total':len(checks),'rows':len(ids),'columns':len(names),'checks':checks}
    (H/'INVARIANTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False,indent=2))

if __name__=='__main__':check()

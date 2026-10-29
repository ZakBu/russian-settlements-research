"""Verify six inherited tables against the immutable published v1 reference.

The original eight-decimal controls remain unequal and are never replaced.
This separately checks arithmetic reproducibility with the pre-existing
close_numeric criterion, while requiring exact keys, metadata, classifications,
missingness and infinity signs. It does not establish a CPU/BLAS cause.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_saratov.cloud_isochrones import table_control
from scripts.sgrt_saratov.regional_independent_checks import close_numeric

REFERENCE_V1_BYTES=645292645
REFERENCE_V1_SHA256='2328cf7a6b2572c84e8cdf6450c5563feb956e32c1ccfc8d72ba174e05d6a9b2'
SIX_TABLES=(
    'fields/fields.parquet', 'fields/halo_fields.parquet',
    'field_sensitivity/ordinary_horizon480_reference/fields.parquet',
    'field_sensitivity/ordinary_horizon480_reference/halo_fields.parquet',
    'context/known_partial_worker_fields.parquet', 'organisation/point_maxima.parquet',
)
EXPECTED_COUNTS={'tables':239,'matrices':6,'geojson':19,'scientific_summaries':26}


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def json_sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def require(condition,message):
    if not condition:raise ValueError(message)


def control_differences(expected,actual):
    require(set(expected)==set(actual),'Original control top-level schema differs')
    for section,count in EXPECTED_COUNTS.items():
        require(isinstance(expected.get(section),dict) and isinstance(actual.get(section),dict),
                'Missing control section: '+section)
        require(len(expected[section])==count and len(actual[section])==count,
                'Unexpected controlled result count: '+section)
        require(set(expected[section])==set(actual[section]),'Controlled result identities differ: '+section)
    for key in expected.keys()-EXPECTED_COUNTS.keys():
        require(expected[key]==actual[key],'Control metadata differs: '+key)
    require(expected.get('numeric_decimal_places')==8,'Eight-decimal source control required')
    differences={k for k in expected['tables'] if expected['tables'][k]!=actual['tables'][k]}
    require(differences==set(SIX_TABLES),'Differences are not exactly the six inherited table hashes')
    for name in SIX_TABLES:
        left,right=expected['tables'][name],actual['tables'][name]
        require(left.get('sha256')!=right.get('sha256'),'Missing original SHA mismatch: '+name)
        require({k:v for k,v in left.items() if k!='sha256'}=={k:v for k,v in right.items() if k!='sha256'},
                'Table control differs in more than SHA: '+name)
    for section in ('matrices','geojson','scientific_summaries'):
        require(expected[section]==actual[section],'Additional scientific differences: '+section)


def read_member(archive,member,temporary):
    require(sum(i.filename==member for i in archive.infolist())==1,
            'A unique fixed scientific member is required: '+member)
    data=archive.read(member)
    temporary.write_bytes(data)
    return pd.read_parquet(temporary),table_control(temporary),hashlib.sha256(data).hexdigest()


def table_comparison(reference,fresh,name):
    require(list(reference.columns)==list(fresh.columns),'Column identities/order differ: '+name)
    require(len(reference)==len(fresh),'Table row counts differ: '+name)
    keys=['source_record_id','kernel','half_time','include_self']
    if name.startswith('context/'):
        keys=['source_record_id','kernel','half_time_minutes']
    if name.startswith('organisation/'):
        keys+=['neighbour_count']
    require(set(keys).issubset(reference),'Missing fixed scientific keys: '+name)
    require(not reference.duplicated(keys).any() and not fresh.duplicated(keys).any(),
            'Duplicate scientific keys: '+name)
    reference=reference.sort_values(keys).reset_index(drop=True)
    fresh=fresh.sort_values(keys).reset_index(drop=True)
    try:pd.testing.assert_frame_equal(reference[keys],fresh[keys],check_exact=True)
    except AssertionError as error:raise ValueError('Scientific row identities differ: '+name) from error
    float_stats={};exact_nonfloat=[];finite_total=0;round8_total=0
    for column in reference:
        left,right=reference[column],fresh[column]
        require(left.dtype==right.dtype,'Data type differs: '+name+'.'+column)
        missing_left,missing_right=left.isna().to_numpy(),right.isna().to_numpy()
        require(np.array_equal(missing_left,missing_right),'Missing-value mask differs: '+name+'.'+column)
        if pd.api.types.is_float_dtype(left.dtype):
            x=left.to_numpy(dtype=float,na_value=np.nan);y=right.to_numpy(dtype=float,na_value=np.nan)
            require(np.array_equal(np.isposinf(x),np.isposinf(y)) and np.array_equal(np.isneginf(x),np.isneginf(y)),
                    'Infinity signs/masks differ: '+name+'.'+column)
            finite=np.isfinite(x);indices=np.flatnonzero(finite);finite_total+=len(indices)
            require(all(close_numeric(float(y[i]),float(x[i])) for i in indices),
                    'Pre-existing arithmetic tolerance exceeded: '+name+'.'+column)
            changed=indices[x[indices]!=y[indices]]
            error=np.abs(y[changed]-x[changed]);denominator=np.maximum(np.abs(x[changed]),np.abs(y[changed]))
            relative=np.divide(error,denominator,out=np.zeros_like(error),where=denominator!=0)
            rounded=sum(round(float(x[i]),8)!=round(float(y[i]),8) for i in changed);round8_total+=rounded
            float_stats[column]={'finite_cells_compared':len(indices),'missing_cells':int(missing_left.sum()),
                'positive_infinity_cells':int(np.isposinf(x).sum()),'negative_infinity_cells':int(np.isneginf(x).sum()),
                'different_numeric_cells':len(changed),'round8_different_cells':int(rounded),
                'max_absolute_difference':float(error.max(initial=0.)),
                'max_symmetric_relative_difference':float(relative.max(initial=0.))}
        else:
            known=~missing_left
            require(np.array_equal(left.loc[known].to_numpy(),right.loc[known].to_numpy()),
                    'Non-floating value/classification differs: '+name+'.'+column)
            exact_nonfloat.append(column)
    return {'rows':len(reference),'columns':list(reference.columns),'scientific_keys':keys,
        'keys_dtypes_missingness_and_infinity_signs_exact':True,
        'nonfloat_columns_exact':exact_nonfloat,'nonfloat_changed_cells':0,
        'boolean_classification_changed_cells':0,'finite_float_cells_compared':finite_total,
        'round8_different_cells':round8_total,'float_columns':float_stats,
        'max_absolute_difference':max((v['max_absolute_difference'] for v in float_stats.values()),default=0.)}


def compare_preserved(fresh_zip,reference_v1_zip,expected_control,actual_control):
    """Return a deterministic proof or raise ValueError; never mutate controls.

    The caller separately verifies complete ZIP inventory and all other result
    members. This function reads exactly the six fixed result members, so the
    same proof applies to the diagnostic and subsequently packaged full ZIP.
    """
    reference_v1_zip=Path(reference_v1_zip);fresh_zip=Path(fresh_zip)
    require(reference_v1_zip.stat().st_size==REFERENCE_V1_BYTES,'Published v1 archive byte size differs')
    require(sha(reference_v1_zip)==REFERENCE_V1_SHA256,'Published v1 archive SHA256 differs')
    require(close_numeric.__kwdefaults__=={'absolute':1e-7,'relative':1e-11},
            'The pre-existing arithmetic criterion has changed')
    control_differences(expected_control,actual_control)
    reports={}
    with zipfile.ZipFile(reference_v1_zip) as reference,zipfile.ZipFile(fresh_zip) as fresh,tempfile.TemporaryDirectory() as directory:
        temporary=Path(directory)
        for index,name in enumerate(SIX_TABLES):
            member='results/'+name
            old,old_control,old_sha=read_member(reference,member,temporary/f'reference_{index}.parquet')
            new,new_control,new_sha=read_member(fresh,member,temporary/f'fresh_{index}.parquet')
            require(old_control==expected_control['tables'][name],
                    'Published v1 table is not the unchanged expected baseline: '+name)
            require(new_control==actual_control['tables'][name],
                    'Fresh table does not match the preserved actual control: '+name)
            report=table_comparison(old,new,name)
            report.update(reference_member_sha256=old_sha,fresh_member_sha256=new_sha,
                original_expected_table_control=copy.deepcopy(expected_control['tables'][name]),
                original_actual_table_control=copy.deepcopy(actual_control['tables'][name]))
            reports[name]=report
    return {'schema':'sgrt.saratov.preserved_numeric_comparison.v1',
        'strict_control_equal':False,'scientific_results_reproduce_with_existing_arithmetic_tolerance':True,
        'original_eight_decimal_control_mismatch_preserved':True,'six_table_hash_differences':6,
        'exact_other_table_control_matches':233,'exact_matrix_control_matches':6,
        'exact_geojson_control_matches':19,'exact_scientific_summary_matches':26,
        'reference_archive':{'release_tag':'sgrt-saratov-fields-20261029-v1','bytes':REFERENCE_V1_BYTES,
            'sha256':REFERENCE_V1_SHA256,'six_reference_tables_match_expected_control':True},
        'expected_control_canonical_json_sha256':json_sha(expected_control),
        'actual_control_canonical_json_sha256':json_sha(actual_control),
        'arithmetic_criterion':{'existing_function':'scripts.sgrt_saratov.regional_independent_checks.close_numeric',
            'absolute':1e-7,'relative':1e-11,'formula':'abs(actual-expected) <= absolute + relative*max(abs(actual),abs(expected))',
            'function_source_sha256':hashlib.sha256(inspect.getsource(close_numeric).encode()).hexdigest(),
            'criterion_changed':False},
        'all_nonfloat_keys_classifications_missingness_and_infinity_signs_exact':True,
        'all_finite_values_compared_with_existing_criterion':True,
        'finite_float_cells_compared':sum(r['finite_float_cells_compared'] for r in reports.values()),
        'round8_different_cells':sum(r['round8_different_cells'] for r in reports.values()),
        'max_absolute_difference':max(r['max_absolute_difference'] for r in reports.values()),
        'tables':reports,'floating_difference_cause_established':False,
        'cpu_blas_dispatch_is_a_hypothesis_not_a_proven_cause':True,
        'complete_archive_inventory_checked_by_this_function':False}


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('fresh-zip','reference-v1-zip','expected-control','actual-control','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();proof=compare_preserved(a.fresh_zip,a.reference_v1_zip,
        json.loads(a.expected_control.read_text()),json.loads(a.actual_control.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(proof,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k!='tables'},ensure_ascii=False))


if __name__=='__main__':main()

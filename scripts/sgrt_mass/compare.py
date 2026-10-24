#!/usr/bin/env python3
"""Compare scientific output tables, never require machine-dependent PDF bytes."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def json_differences(a,b,path=""):
    if isinstance(a,dict) and isinstance(b,dict):
        return [row for key in sorted(set(a)|set(b)) for row in json_differences(a.get(key),b.get(key),path+"/"+key)]
    if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        return [row for i,(x,y) in enumerate(zip(a,b)) for row in json_differences(x,y,path+"/"+str(i))]
    if a==b:return []
    return [{"field":path,"source":str(a)[:500],"recomputed":str(b)[:500]}]


def compare(source,recomputed):
    records=[]
    source_tables={p.relative_to(source).as_posix():p for folder in ['model','centre_types','audit/lo_normative_comparison'] for p in (source/folder).rglob('*.parquet')}
    target_tables={p.relative_to(recomputed).as_posix():p for folder in ['model','centre_types','audit/lo_normative_comparison'] for p in (recomputed/folder).rglob('*.parquet')}
    extra=sorted(set(target_tables)-set(source_tables));missing=sorted(set(source_tables)-set(target_tables))
    for relative,path in sorted(source_tables.items()):
        if relative in missing:continue
        other=target_tables[relative];record={'path':relative,'source_sha256':digest(path),'recomputed_sha256':digest(other)}
        a=pd.read_parquet(path);b=pd.read_parquet(other)
        record.update(rows_source=len(a),rows_recomputed=len(b),columns_source=len(a.columns),columns_recomputed=len(b.columns))
        try:
            pd.testing.assert_frame_equal(a,b,check_dtype=False,check_exact=False,rtol=0,atol=1e-8,check_categorical=False)
            record['status']='equal_with_atol_1e-8'
        except AssertionError as error:
            record['status']='different';record['detail']=str(error)[:6000]
        numeric={}
        if len(a)==len(b):
            for col in set(a.select_dtypes(include='number').columns)&set(b.select_dtypes(include='number').columns):
                av=a[col].to_numpy(dtype=float,na_value=np.nan);bv=b[col].to_numpy(dtype=float,na_value=np.nan)
                finite=np.isfinite(av)&np.isfinite(bv)
                delta=float(np.max(np.abs(av[finite]-bv[finite]))) if finite.any() else 0.0
                if delta:numeric[col]=delta
        record['numeric_nonzero_max_abs_differences']=numeric
        records.append(record)
    metadata=[]
    for folder in ['model','centre_types','audit/lo_normative_comparison','figures']:
        for path in sorted((source/folder).glob('*.json')):
            relative=path.relative_to(source);other=recomputed/relative
            if not other.exists():metadata.append({'path':str(relative),'status':'missing_recomputed'});continue
            a=json.loads(path.read_text());b=json.loads(other.read_text())
            metadata.append({'path':str(relative),'identical_json_values':a==b,'source_sha256':digest(path),'recomputed_sha256':digest(other),
                'differing_fields':json_differences(a,b)[:200],
                'note':'Provenance paths, input/code SHA, PDF metadata and timestamps require separate interpretation; scientific tables compared independently.'})
    differences=[r['path'] for r in records if r['status']=='different']
    return {'status':'passed' if not differences and not extra and not missing else 'failed','absolute_numeric_tolerance':1e-8,'relative_numeric_tolerance':0,
        'missing':missing,'unexpected':extra,'different':differences,'table_count':len(records),'tables':records,'metadata_separate':metadata,
        'pdf_or_png_byte_equality_required':False,'new_federal_scan_claimed':False,'new_road_routing_claimed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--recomputed',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=compare(a.source,a.recomputed);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['tables','metadata_separate']},indent=2))
    raise SystemExit(0 if result['status']=='passed' else 1)

#!/usr/bin/env python3
"""Independent pivot-based check of every strict centre/member pair.

Does not import the star builder or its admission function. Tests the declared
three-function model, not real trips, completeness or facility operation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

CORE=['medical_basic','school','grocery']
LIMITS={'daily_20_school30_wb':{'medical_basic':30.,'school':30.,'grocery':20.},
        'daily_10_school15_wb':{'medical_basic':30.,'school':15.,'grocery':10.},
        'daily_30_school30_wb':{'medical_basic':30.,'school':30.,'grocery':30.}}


def expected_pairs(edges,reference,limits):
    core=edges[edges.service_family.isin(CORE)].copy()
    if core.duplicated(['origin_id','service_family']).any():raise ValueError('Repeated origin/family')
    limit=core.service_family.map(limits)
    known=core.provider_site_id.notna()
    cost=pd.to_numeric(core.cost_minutes,errors='coerce')
    admitted=known & (core.local_service_present.fillna(False) | (np.isfinite(cost)&cost.ge(0)&cost.le(limit)))
    chosen=core[admitted & core.provider_settlement_id.notna()]
    pivot=chosen.pivot(index='origin_id',columns='service_family',values='provider_settlement_id').reindex(columns=CORE)
    same=pivot.notna().all(axis=1)&pivot.medical_basic.eq(pivot.school)&pivot.school.eq(pivot.grocery)
    triples=pivot[same].medical_basic
    own=set(triples[triples.index.to_series().eq(triples)].index)
    ref=reference.dropna(subset=['source_record_id']).set_index('source_record_id')
    if not ref.index.is_unique:raise ValueError('Reference identity not unique')
    # Independent literal check on the declared census frame: both explicit
    # source parts and ambiguous uses of the word are excluded from this subset.
    whole=~ref.name.fillna('').str.contains(r'\bчаст(?:ь|и)\b',case=False,regex=True)
    for flag in ['is_settlement_part','settlement_is_part','population_unit_is_part']:
        if flag in ref:whole &= ~ref[flag].astype('string').str.lower().isin(['true','1','yes'])
    positive=whole&ref.population_2021.gt(0)&ref.analysis_origin.fillna(False)
    ordinary=ref.population_role.eq('ordinary_settlement_record')&ref.budget_population_credit.fillna(False)
    external_ok=set(ref.index[positive&ordinary])
    centre_ok=set(ref.index[positive&(ordinary|ref.population_role.eq('external_context_nonadditive'))])
    external={(o,c) for o,c in triples.items() if o!=c and o in external_ok and c in own&centre_ok}
    centres={c for _,c in external}
    return external|{(c,c) for c in centres}


def verify(expected,members):
    if members.duplicated(['origin_id','centre_settlement_id']).any():raise ValueError('Duplicate member pair')
    actual=set(zip(members.origin_id,members.centre_settlement_id))
    if expected!=actual:
        raise ValueError(f'Strict subset mismatch: missing {len(expected-actual)}, extra {len(actual-expected)}')
    return {'centre_member_pairs':len(actual),'centres':len({c for _,c in actual}),
            'external_pairs':sum(o!=c for o,c in actual),'all_pairs_equal':True}


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--edges',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--scenarios',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    edges=pd.read_parquet(a.edges);ref=pd.read_parquet(a.reference);results={};inputs={str(a.edges):sha(a.edges),str(a.reference):sha(a.reference)}
    for sid,limits in LIMITS.items():
        path=a.scenarios/sid/'strict_three_core_memberships.parquet'
        results[sid]=verify(expected_pairs(edges,ref,limits),pd.read_parquet(path));inputs[str(path)]=sha(path)
    result={'check':'independent_pivot_and_admission_rule_vs_every_strict_pair','scenarios':results,
            'input_sha256':inputs,'code_sha256':sha(Path(__file__)),'does_not_validate_observed_trips':True}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(results))

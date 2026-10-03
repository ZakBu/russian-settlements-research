"""Propose noncity modern points with independently named historical code support.

All emitted records remain candidates. Provider code normalization is restricted
to the explicit numeric-serialization rule, never native census identifiers.
"""
import argparse
from pathlib import Path
import json
import pandas as pd
from .coordinate_ledger import norm, typekey
from .historical_named_points import sha

PGT_TYPES={'пгт','поселок городского типа','рабочий поселок','курортный поселок','дачный поселок'}

def compatible_type(source_type, provider_type):
    if norm(source_type)=='пгт':return norm(provider_type) in PGT_TYPES
    return bool(typekey(source_type)) and typekey(source_type)==typekey(provider_type)

def run(output):
    if output.exists():raise FileExistsError('New immutable output required')
    root=Path('/workspace/settlements-work')
    paths={'historical_candidates':root/'coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet',
           'provider_ledger':root/'coordinates/ledger/coordinate_screen.parquet',
           'accepted_modern_points':root/'coordinates/accepted_modern_v1/accepted_point_uses.parquet',
           'region_screen':root/'coordinates/region_screen_v1/region_point_screen.parquet'}
    c=pd.read_parquet(paths['historical_candidates'])
    c=c[c.census_year.eq(2021)&~c.type_norm.eq('город')&c.historical_named_point_candidate].copy()
    cols=['source_record_id','provider_settlement_name','provider_settlement_type_full',
          'provider_settlement_fias_duplicate_count','baseline_provider_coordinate_conflict']
    p=pd.read_parquet(paths['provider_ledger'],columns=cols)
    c=c.merge(p,on='source_record_id',how='left',validate='one_to_one')
    c['provider_own_name_matches_source']=[norm(a)==norm(b) and bool(norm(a)) for a,b in zip(c.settlement_name,c.provider_settlement_name)]
    c['provider_type_compatible_with_source']=[compatible_type(a,b) for a,b in zip(c.type_norm,c.provider_settlement_type_full)]
    c['proposed_rule_pass']=c.source_object_is_naselenniy_punkt.eq(True)&c.source_is_aggregate_scope.eq(False)&c.provider_fias_level.isin(['4','6'])&(c.modern_provider_code_matches_historical_code|c.modern_numeric_provider_code_agrees_historical_code)&c.modern_provider_to_historical_point_km.le(1)&c.provider_general_fias_duplicate_count.le(1)&c.provider_coordinate_duplicate_count.le(1)&c.provider_own_name_matches_source&c.provider_type_compatible_with_source&~c.baseline_provider_coordinate_conflict.fillna(False)
    known=set(pd.read_parquet(paths['accepted_modern_points'],columns=['target_source_record_id']).target_source_record_id)
    c['already_accepted_target']=c.source_record_id.isin(known)
    candidate=c[c.proposed_rule_pass&~c.already_accepted_target].copy()
    seed='modern-historical-code-point-review-20261003'
    candidate['sample_hash']=candidate.source_record_id.map(lambda s:__import__('hashlib').sha256((seed+'|'+s).encode()).hexdigest())
    candidate['population_band']=pd.cut(candidate.population,[-1,0,99,999,float('inf')],labels=['zero','1-99','100-999','1000plus']).astype(str)
    sample=candidate.sort_values('sample_hash').groupby(['type_norm','population_band'],observed=True,group_keys=False).head(2)
    output.mkdir(parents=True)
    c.to_parquet(output/'candidate_screen.parquet',index=False)
    candidate.to_parquet(output/'new_point_candidates.parquet',index=False)
    sample.to_parquet(output/'fixed_sample.parquet',index=False)
    receipt={'status':'candidate_only_no_admissions','candidate_count':len(candidate),'recorded_population':int(candidate.population.sum()),
             'fixed_sample_count':len(sample),'sample_seed':seed,'inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()},
             'outputs':{p.name:sha(p) for p in output.glob('*.parquet')},'builder_sha256':sha(Path(__file__)),
             'type_rule':'source generic pgt allows explicit working/resort/dacha/pgt provider type; other types exact canonical match',
             'limits':'Candidate only; whole source/event/point/source-provenance checks and independent application acceptance required.'}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k in ['status','candidate_count','recorded_population','fixed_sample_count']}))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);run(p.parse_args().output)

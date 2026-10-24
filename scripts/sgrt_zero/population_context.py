#!/usr/bin/env python3
"""Separate administrative city context from the additive ordinary NP budget."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

SCOPE='ordinary_settlement_record_with_year_credit_only; excludes_nonadditive_city_administrative_aggregates'


def build_population_context(members,reference):
 if members.duplicated(['unit_id','origin_id']).any():raise ValueError('Repeated membership row')
 cities=reference[reference.population_role.eq('external_context_nonadditive')&reference.source_record_id.notna()].copy()
 if not cities.source_record_id.is_unique:raise ValueError('Repeated nonadditive city context identity')
 columns=['source_record_id','name','population_role']+[f'population_{y}' for y in [2002,2010,2021]]
 linked=members[['unit_id','origin_id']].merge(cities[columns],left_on='origin_id',right_on='source_record_id',how='inner',validate='many_to_one')
 context={}
 for uid,g in linked.groupby('unit_id',sort=False):
  items=[]
  for _,r in g.sort_values('source_record_id').iterrows():
   item={'source_record_id':r.source_record_id,'name':r['name'],
    'population_role':r.population_role,'scope':'administrative_city_aggregate_not_population_of_reconstructed_service_unit',
    'added_to_ordinary_member_budget':False}
   for y in [2002,2010,2021]:
    value=r[f'population_{y}'];item[f'population_{y}_context']=None if pd.isna(value) else float(value)
   items.append(item)
  context[uid]=json.dumps(items,ensure_ascii=False,sort_keys=True)
 out=members[['unit_id']].drop_duplicates().copy()
 out['contains_nonadditive_city_context']=out.unit_id.isin(context)
 out['city_population_context_json']=out.unit_id.map(context).fillna('[]')
 out['ordinary_member_population_scope']=SCOPE
 out['full_unit_population_established']=False
 out['city_context_population_is_additive']=False
 return out


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',type=Path,required=True)
 p.add_argument('--analysis-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();reference=pd.read_parquet(a.reference);records={};a.output.mkdir(parents=True,exist_ok=True)
 paths=sorted(set(a.analysis_root.glob('hierarchy/*/level0_memberships.parquet'))|set(a.analysis_root.glob('upward/*/*/memberships.parquet'))|set(a.analysis_root.glob('upward_extended/*/*/*/memberships.parquet')))
 for path in paths:
  before=sha(path);result=build_population_context(pd.read_parquet(path),reference)
  relative=path.relative_to(a.analysis_root);target=a.output/relative.parent/'population_context.parquet';target.parent.mkdir(parents=True,exist_ok=True)
  result.to_parquet(target,index=False,compression='zstd')
  if before!=sha(path):raise RuntimeError('Membership changed while deriving population context')
  records[str(relative)]={'units':len(result),'city_context_units':int(result.contains_nonadditive_city_context.sum()),'source_sha256':before,'output':str(target.relative_to(a.output)),'output_sha256':sha(target)}
 (a.output/'summary.json').write_text(json.dumps({'reference_sha256':sha(a.reference),'code_sha256':sha(__file__),'ordinary_member_population_scope':SCOPE,'no_population_budgets_or_assignments_changed':True,'tables':records},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()

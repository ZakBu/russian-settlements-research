#!/usr/bin/env python3
"""Illustrative audited code-link examples, not a representative sample."""
from pathlib import Path
import argparse,pandas as pd,pyarrow.parquet as pq
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));a=ap.parse_args();root=a.base/'functional_dynamics_20261019/economy';data=root/'address_audit_2021_2025'
 p=pq.read_table(data/'point_code_alias_sensitivity_2025.parquet').to_pandas()
 old=pq.read_table(root/'pinned_calendar/point_exact_code_witnesses_2011_2025.parquet',columns=['id','direct_consumer_function_diversity'],filters=[('year','=',2021)]).to_pandas().set_index('id')
 aliases=pd.read_csv(data/'conditional_code_aliases.csv');aliases=aliases[aliases.accepted_sensitivity_alias].copy();aliases['code_2025']=aliases.code_2025.astype('string').str.zfill(11)
 panel=pq.read_table(a.base/'restored/extracted/research/sgrt_recovered_20261019/data/panel.parquet',columns=['id','oktmo_2021']).to_pandas().set_index('id')
 cases=p[(p.native_direct_diversity_2025==0)&(p.conditional_alias_direct_diversity_2025>=2)&p.population_2021.between(500,5000)].sort_values(['conditional_alias_direct_diversity_2025','population_2021'],ascending=False).head(12)
 cases=cases[['id','name','region','population_2021','native_direct_diversity_2025','conditional_alias_direct_diversity_2025']].copy();cases['direct_diversity_2021']=cases.id.map(old.direct_consumer_function_diversity);cases['reference_oktmo_2021']=cases.id.map(panel.oktmo_2021).str.zfill(11)
 cases=cases.merge(aliases[['reference_id','code_2025','training_INN','heldout_INN','heldout_matches']],left_on='id',right_on='reference_id',how='left',validate='one_to_many').drop(columns='reference_id');cases.to_csv(data/'alias_case_examples.csv',index=False)
 print(f'Illustrative examples: {len(cases)} rows')
if __name__=='__main__':main()

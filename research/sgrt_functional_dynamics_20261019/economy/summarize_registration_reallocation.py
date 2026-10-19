#!/usr/bin/env python3
"""Describe code/address redistribution; never call it transfer of activity."""
import argparse
from pathlib import Path
import pandas as pd,numpy as np,pyarrow.parquet as pq
from build_dynamics import dump,sha,save
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--panel',type=Path,required=True);a=ap.parse_args()
 p=pq.read_table(a.panel,columns=['id','name','type','population_2021','region']).to_pandas().set_index('id')
 z=pq.read_table(a.out/'registered_point_code_transitions.parquet').to_pandas()
 for side in ['origin','destination']:
  for col in ['population_2021','region','name','type']:z[f'{side}_{col}']=z[f'{side}_id'].map(p[col])
  z[f'{side}_size_class']=pd.cut(z[f'{side}_population_2021'],[-1,0,499,4999,19999,99999,np.inf],labels=['0','1–499','500–4999','5000–19999','20000–99999','100000+']).astype('string').fillna('unknown')
 src=z.origin_population_2021;dst=z.destination_population_2021
 z['destination_size_relation']=np.select([src.isna()|dst.isna(),dst>src,dst<src],['unknown','larger','smaller'],default='same_population')
 z['region_relation']=np.where(z.origin_region==z.destination_region,'same_region','different_region')
 summary=z.groupby(['origin_size_class','destination_size_class','destination_size_relation','region_relation'],dropna=False,observed=True).common_INN_count.sum().reset_index()
 summary.to_csv(a.out/'registration_reallocation_size_summary.csv',index=False)
 z.groupby(['origin_type','destination_type'],dropna=False).common_INN_count.sum().rename('common_INN_count').reset_index().to_csv(a.out/'registration_reallocation_type_summary.csv',index=False)
 save(z,a.out/'registered_point_code_transitions_enriched')
 audit={'common_INN_different_exact_code_points':int(z.common_INN_count.sum()),'n_unique_ordered_point_pairs':len(z),'destination_size_relation':{str(k):int(v) for k,v in z.groupby('destination_size_relation').common_INN_count.sum().items()},'region_relation':{str(k):int(v) for k,v in z.groupby('region_relation').common_INN_count.sum().items()},'size_reference_year':2021,'physical_relocation_or_function_transfer_proven':False,'interpretation':'different_exact_registration_code_of_same_INN; possible_code_change_or_address_change; not_physical_branch_relocation','pass':int(z.common_INN_count.sum())==50994,'source_sha256':sha(a.out/'registered_point_code_transitions.parquet')}
 dump(a.out/'registration_reallocation_audit.json',audit);assert audit['pass'];print(audit)
if __name__=='__main__':main()

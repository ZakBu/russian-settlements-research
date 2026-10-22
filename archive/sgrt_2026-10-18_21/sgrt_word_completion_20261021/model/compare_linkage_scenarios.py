"""Compare explicit-locality and coordinate-candidate assignments; no identity assumption."""
from pathlib import Path
import argparse,json
import pandas as pd
import numpy as np

def compare(baseline,inclusive,output):
 output.mkdir(parents=True,exist_ok=True)
 a=pd.read_parquet(baseline/'memberships.parquet');b=pd.read_parquet(inclusive/'memberships.parquet')
 required=['id','assigned_center_id','assignment_status']
 z=a[required].merge(b[required],on='id',suffixes=('_baseline','_inclusive'),validate='one_to_one',how='outer',indicator=True)
 if not z._merge.eq('both').all():raise ValueError('Scenario axes differ')
 z['assignment_equal']=z.assigned_center_id_baseline.fillna('__UNASSIGNED__').eq(z.assigned_center_id_inclusive.fillna('__UNASSIGNED__'))
 nodes=pd.read_parquet(baseline/'nodes.parquet',columns=['id','population_2021','_population_axis_row']);z=z.merge(nodes,on='id',validate='one_to_one')
 z.to_parquet(output/'origin_linkage_sensitivity.parquet',index=False)
 ordinary=z._population_axis_row.fillna(False);known=z.population_2021.notna()&ordinary
 p=z.loc[known,'population_2021'];equal=z.loc[known,'assignment_equal']
 receipt={'status':'COMPUTED_CONDITIONAL_ON_BOTH_NETWORK_SCENARIOS','axis_rows':len(z),'equal_assignment_rows':int(z.assignment_equal.sum()),'equal_assignment_fraction':float(z.assignment_equal.mean()),'population_axis_equal_assignment_fraction':float(z.loc[ordinary,'assignment_equal'].mean()),'known_population_equal_assignment_fraction2021':float(p[equal].sum()/p.sum()) if p.sum()>0 else None,'linkage_ambiguity_not_validation':True,'source_coordinate_candidates_are_not_confirmed_own_services':True}
 (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--inclusive',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();compare(a.baseline,a.inclusive,a.output)

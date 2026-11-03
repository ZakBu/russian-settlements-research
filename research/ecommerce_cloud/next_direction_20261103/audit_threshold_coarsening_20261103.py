#!/usr/bin/env python3
"""Count KOUZh rural adults in the size bin crossing the historic Ozon cutoff.

Does not classify exposure, recover settlement identifiers or infer online trips.
"""
import csv,json,math,argparse
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def num(v):
 try:
  x=float(v.replace(',','.'));return x if math.isfinite(x) else None
 except (ValueError,AttributeError):return None
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--inputs',type=Path,default=ROOT/'work/ecommerce_flows_20261026')
 p.add_argument('--output',type=Path,default=ROOT/'work/ecommerce_next_20261103/identification/threshold_coarsening.json')
 args=p.parse_args();out=[]
 for year in (2018,2022,2024):
  bins=defaultdict(lambda:[0,0.0]);excluded=0
  with (args.inputs/f'{year}_individual.csv').open(encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f,delimiter=';'):
    age=num(r['H01_02']);w=num(r['KVZV'])
    if num(r['H00_04'])!=2 or age is None or age<15 or w is None or w<=0:continue
    # The same 15+ interview base as the purchase geography report.
    if r['I04_03_01'].strip()=='':excluded+=1;continue
    size=num(r['R_1_1']);bins[int(size) if size is not None else -99][0]+=1;bins[int(size) if size is not None else -99][1]+=w
  n=sum(v[0] for v in bins.values());wn=sum(v[1] for v in bins.values())
  out.append({'year':year,'cohort':'rural age15plus, positive weight, nonblank food+hygiene geography','n':n,'weighted_n':wn,'excluded_blank_food_geography_n':excluded,'bins':{str(k):{'n':v[0],'weighted_n':v[1],'weighted_pct':100*v[1]/wn} for k,v in sorted(bins.items())},'threshold_3500_inside_size9':True,'actual_eligible_or_exposed_people_estimated':False})
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

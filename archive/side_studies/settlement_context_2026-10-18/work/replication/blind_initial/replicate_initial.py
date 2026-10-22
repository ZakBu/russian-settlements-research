#!/usr/bin/env python3
"""Independent CSV/gzip/Decimal control audit. No main-analysis imports."""
import csv, gzip, hashlib, json, sys, platform, subprocess
from pathlib import Path
from decimal import Decimal, InvalidOperation
from collections import Counter
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
years=('2002','2010','2021')
stats={y:Counter() for y in years}; sums={y:Decimal(0) for y in years}
quality={y:Counter() for y in years}; transitions={a+'_'+b:Counter() for a,b in [('2002','2010'),('2010','2021'),('2002','2021')]}
uids=Counter(); coords=Counter(); quality2010rows=Counter(); region_counts=Counter(); total=0
nonfinite_examples=[]; negative_examples=[]
def number(s):
 if not s.strip(): return None,'missing'
 try:
  v=Decimal(s)
 except InvalidOperation:return None,'unparseable'
 if not v.is_finite():return None,'nonfinite'
 return v,'numeric'
def state(v,s):return s if v is None else ('negative' if v<0 else 'zero' if v==0 else 'positive')
with gzip.open(p,'rt',encoding='utf-8-sig',newline='') as f:
 reader=csv.DictReader(f); fields=reader.fieldnames
 for row in reader:
  total+=1; uid=row['entity_uid'];uids[uid]+=1; vals={}
  for y in years:
   v,s=number(row['population_'+y]); vals[y]=(v,s);stats[y][s]+=1; quality[y][row['population_value_quality_'+y]]+=1
   if v is not None:
    sums[y]+=v;stats[y][state(v,s)]+=1
    if v!=v.to_integral_value():stats[y]['noninteger']+=1
    if v<0 and len(negative_examples)<10:negative_examples.append([uid,y,str(v)])
  for k,c in transitions.items():
   a,b=k.split('_'); c[state(*vals[a])+'->'+state(*vals[b])]+=1
  lat,ls=number(row['latitude_2010']);lon,os=number(row['longitude_2010'])
  if lat is None or lon is None:coords['invalid_or_missing']+=1
  elif -90<=lat<=90 and -180<=lon<=180:coords['valid_global_range']+=1
  else:coords['outside_global_range']+=1
  coords['coordinate_admission:'+row['coordinate_admission_status_2010']]+=1
  region_counts[row['effective_region_norm_2010']]+=1
receipt={'status':'computed','independent_scope':'Separate agent; standard-library CSV/gzip/Decimal implementation; no main analysis code or result read before this receipt. Not independent new data. Prior instructions contained expected row count and hash, so identity validation is not blinded to those expectations.', 'utc':datetime.now(timezone.utc).isoformat(),'input':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size,'rows':total,'columns':len(fields),'unique_uid':len(uids),'empty_uid_count':uids.get('',0),'duplicate_uid_count':sum(n-1 for n in uids.values()),'population':{y:dict(stats[y],sum_decimal=str(sums[y])) for y in years},'quality_flags':{y:dict(quality[y]) for y in years},'transitions':{k:dict(v) for k,v in transitions.items()},'coordinates_2010':dict(coords),'region_counts_2010':dict(region_counts),'negative_examples':negative_examples,'environment':{'python':sys.version,'platform':platform.platform()},'main_results_seen':False,'remaining':['100 independent spherical queries after geometric target contract','saved prediction metrics and train/test overlap','one independent fit under frozen specification']}
out=Path(__file__).with_name('receipt.json');out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['sha256','rows','columns','unique_uid','duplicate_uid_count','population','transitions','coordinates_2010']},ensure_ascii=False,indent=2))

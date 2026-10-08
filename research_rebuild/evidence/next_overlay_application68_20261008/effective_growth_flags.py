from pathlib import Path
import csv,gzip,json,hashlib,collections,math
Z=Path(__file__).resolve().parent;D=Path('/workspace/settlements-delivery/working-full-chain-20261007');P=D/'ordinary_full3_with_primary_population_sources.csv.gz'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
r=json.loads((Z/'application_receipt.json').read_text());assert sha(P)==r['output_pins'][str(P)]['sha256'];counts=collections.Counter();flags=[];rows=0
with gzip.open(P,'rt',newline='') as f:
 for x in csv.DictReader(f):
  rows+=1
  for a,b in [(2002,2010),(2010,2021),(2002,2021)]:
   u=float(x['population_'+str(a)]);v=float(x['population_'+str(b)]);assert math.isfinite(u) and math.isfinite(v) and min(u,v)>=0
   status=''
   if u>0 and v>0:
    if v/u>=20:status='positive_ratio_at_least20'
    elif u/v>=20:status='negative_ratio_at_least20'
   elif u==0 and v>0:status='zero_to_positive_ratio_undefined'
   elif u>0 and v==0:status='positive_to_zero_ratio_undefined'
   if status:
    counts[f'{a}_{b}:{status}']+=1
    flags.append(dict(entity_uid=x['entity_uid'],from_year=a,to_year=b,from_population=u,to_population=v,ratio=v/u if u else '',status=status,from_source_record_id=x.get('source_record_id_'+str(a),''),to_source_record_id=x.get('source_record_id_'+str(b),''),from_population_quality=x.get('population_value_quality_'+str(a),''),to_population_quality=x.get('population_value_quality_'+str(b),'')))
out=Z/'effective_population_growth_screen68.csv.gz'
with out.open('wb') as raw:
 with gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gf:
  import io
  with io.TextIOWrapper(gf,encoding='utf8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(flags[0]));w.writeheader();w.writerows(flags)
receipt={'status':'screened_effective_primary_counts_without_smoothing_or_dropping','stage':68,'wide_rows':rows,'flagged_unique_entities':len(set(x['entity_uid'] for x in flags)),'flagged_pair_rows':len(flags),'pair_counts':dict(counts),'threshold':'positive finite ratios >=20 in either direction; zero transitions separately, undefined percent','flags_are_not_proven_errors':True,'calibrated_confidence_or_accuracy_not_claimed':True,'input_sha256':sha(P),'output_sha256':sha(out),'implementation_sha256':sha(Path(__file__))}
receipt.update(finite_positive_ratio_unique_entities=len({x['entity_uid'] for x in flags if 'ratio_at_least20' in x['status']}), finite_positive_ratio_pair_rows=sum('ratio_at_least20' in x['status'] for x in flags), zero_transition_unique_entities=len({x['entity_uid'] for x in flags if 'ratio_undefined' in x['status']}))
(Z/'effective_population_growth_screen68_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))

"""Read-only exact same-year accepted own-point collision screen; no exemptions."""
from pathlib import Path
import argparse,hashlib,json,datetime,math
import pandas as pd

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);args=parser.parse_args();src=Path(args.input);out=Path(args.output);out.mkdir(parents=True,exist_ok=True);input_sha=sha(src);d=pd.read_csv(src,low_memory=False);assert d.source_record_id.is_unique
 yes=d.has_ownpoint.astype(str).str.lower().isin(['true','1']);p=d.loc[yes].copy();keys=['census_year','accepted_ownpoint_latitude','accepted_ownpoint_longitude'];assert set(keys)<=set(p.columns)
 for key in keys:p[key]=pd.to_numeric(p[key],errors='raise')
 assert p[keys].notna().all().all() and all(math.isfinite(float(v))for key in keys[1:]for v in p[key]);sizes=p.groupby(keys,dropna=False).size().rename('record_count');groups=sizes[sizes.ge(2)].reset_index().sort_values(keys);groups.insert(0,'collision_group_id',range(1,len(groups)+1));rows=p.merge(groups,on=keys,how='inner',validate='many_to_one').sort_values(['collision_group_id','source_record_id']);groups.to_csv(out/'exact_sameyear_coordinate_groups.csv',index=False,float_format='%.17g');rows.to_csv(out/'exact_sameyear_coordinate_collision_records.csv.gz',index=False,float_format='%.17g');assert sha(src)==input_sha
 receipt=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),input_file=str(src),input_sha256=input_sha,input_rows=len(d),has_ownpoint_rows=len(p),has_ownpoint_by_year={str(k):int(v)for k,v in p.groupby('census_year').size().items()},comparison='Exact equality of parsed numeric accepted_ownpoint latitude and longitude within identical census_year; every has_ownpoint=True record included; no exclusions, rounding, tolerance, root deduplication or identity inference.',collision_groups=len(groups),collision_records=len(rows),data_modified=False,script_file=str(Path(__file__).resolve()),script_sha256=sha(__file__),pandas_version=pd.__version__,outputs=[dict(file=f.name,sha256=sha(f),bytes=f.stat().st_size)for f in [out/'exact_sameyear_coordinate_groups.csv',out/'exact_sameyear_coordinate_collision_records.csv.gz']]);(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Audit legacy selected columns versus the independently acquired pinned source."""
import argparse,json
from pathlib import Path
import pyarrow.parquet as pq
from build_dynamics import sha,dump
COLS=['inn','oktmo','okved','okved_section','filed']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--out',type=Path,required=True);ap.add_argument('--years',type=int,nargs='+',default=[2016,2021]);a=ap.parse_args();rows=[]
 for yr in a.years:
  old=a.base/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{yr}_selected.parquet';new=a.base/f'functional_dynamics_20261019/economy/remote_selected/rfsd_{yr}_identity_function_selected.parquet'
  x=pq.read_table(old,columns=COLS);y=pq.read_table(new,columns=COLS)
  rows.append({'year':yr,'legacy_rows':len(x),'pinned_rows':len(y),'columns':COLS,'complete_ordered_five_column_table_equal':x.equals(y,check_metadata=False),'legacy_sha256':sha(old),'pinned_selected_sha256':sha(new),'interpretation':'Equality checks only these five columns; financial fields/geocodes outside this comparison are not asserted identical.'})
 dump(a.out,{'comparisons':rows,'actual_comparison_completed':True});print(json.dumps(rows))
if __name__=='__main__':main()

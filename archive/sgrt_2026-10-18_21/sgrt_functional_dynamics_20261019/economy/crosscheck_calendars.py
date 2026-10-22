#!/usr/bin/env python3
"""Reconcile separately computed narrow and broad pipelines on every point/year."""
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
from build_dynamics import dump,sha
EXPECTED={'retail47':'G','food56':'I','education85':'P','health86':'Q','social8788':'Q','repair95':'S','personal96':'S','accommodation55':'I','finance64to66':'K','admin84':'O'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();checks=[];p=a.root/'pinned_calendar/point_exact_code_witnesses_2011_2025.parquet'
 for yr in range(2011,2026):
  narrow=pq.read_table(p,columns=['id','year','legal_entities']+[g+'_legal_entities' for g in EXPECTED],filters=[('year','=',yr)]).to_pandas().set_index('id')
  broad=pq.read_table(a.root/f'pinned_sector_calendar/point_sector_witnesses_{yr}.parquet').to_pandas().set_index('id').reindex(narrow.index)
  checks.append({'check':f'axes_{yr}','pass':len(narrow)==len(broad)==142570 and narrow.index.is_unique and broad.index.is_unique})
  checks.append({'check':f'exact_entity_counts_independent_pipelines_{yr}','pass':bool((narrow.legal_entities==broad.legal_entities).all())})
  for g,s in EXPECTED.items():checks.append({'check':f'{g}_subset_section_{s}_{yr}','pass':bool((narrow[g+'_legal_entities']<=broad[f'section_{s}_legal_entities']).all())})
 dump(a.root/'CALENDAR_CROSSCHECK.json',{'checks':checks,'pass':all(c['pass'] for c in checks),'description':'Author internal cross-pipeline consistency; not external validation of physical objects or independent statistical replication.','code_sha256':sha(Path(__file__))});assert all(c['pass'] for c in checks)
 print(json.dumps({'checks':len(checks),'pass':True}))
if __name__=='__main__':main()

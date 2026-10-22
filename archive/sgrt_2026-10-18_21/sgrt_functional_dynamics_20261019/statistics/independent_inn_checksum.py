#!/usr/bin/env python3
"""Syntax is distinct from the 10-digit legal-entity INN checksum."""
from pathlib import Path
import json
import numpy as np,pandas as pd,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent/'wave2';O.mkdir(exist_ok=True)
def main():
 rows=[];weights=np.array([2,4,10,3,5,9,4,6,8],np.uint64)
 for year in range(2011,2026):
  path=R/f'economy/remote_selected/rfsd_{year}_identity_function_selected.parquet'
  if not path.exists():continue
  n=0;validn=0;bad=0
  for batch in pq.ParquetFile(path).iter_batches(columns=['inn'],batch_size=100000):
   s=batch.column(0).to_pandas().astype('string');n+=len(s);valid=s.str.fullmatch(r'\d{10}',na=False);v=s[valid].astype(np.uint64).to_numpy();validn+=len(v)
   digits=np.column_stack([(v//np.uint64(10**power))%np.uint64(10) for power in range(9,0,-1)])
   expected=((digits*weights).sum(axis=1)%11)%10;bad+=int((expected!=v%10).sum())
  rows.append(dict(year=year,source_rows=n,syntactically_ten_digits=validn,invalid_syntax=n-validn,checksum_invalid_but_retained=bad))
 d=pd.DataFrame(rows);d.to_csv(O/'independent_INN_checksum.csv',index=False);author=pd.read_csv(R/'economy/pinned_calendar/coverage_2011_2025.csv');z=d.merge(author,on='year',suffixes=('_independent','_author'))
 checks={'all_15_years':len(d)==15,'source_rows':z.source_rows_independent.eq(z.source_rows_author).all(),'syntax_counts':z.syntactically_ten_digits.eq(z.valid_inn_rows).all(),'checksum_counts':z.checksum_invalid_but_retained.eq(z.checksum_invalid_INN_retained).all()}
 (O/'INN_CHECKSUM_AUDIT.json').write_text(json.dumps({'status':'PASS' if all(checks.values()) else 'FAIL','checks':{k:bool(v) for k,v in checks.items()},'interpretation':'Ten-digit syntax is not checksum/EGRUL validation. Checksum-invalid rows retained as in source, not silently removed. A passed checksum does not establish a legal entity is active.'},ensure_ascii=False,indent=2)+'\n');print('INN checksum audit',checks);assert all(checks.values())
if __name__=='__main__':main()

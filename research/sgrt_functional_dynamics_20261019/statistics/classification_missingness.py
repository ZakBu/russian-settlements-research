#!/usr/bin/env python3
"""Measure incomplete activity classification independently of service absence."""
from pathlib import Path
import json, hashlib
import pandas as pd
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent
def main():
 p=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet',columns=['id','oktmo_2021'])
 norm=lambda s:s.astype('string').str.strip().where(s.astype('string').str.strip().str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
 mapping=pd.Series(p.id.to_numpy(),index=norm(p.oktmo_2021));rows=[];raw={}
 for y in [2016,2021]:
  d=pd.read_parquet(B/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{y}_selected.parquet',columns=['inn','okved','okved_section','oktmo'])
  d=d[d.inn.astype('string').str.fullmatch(r'\d{10}',na=False)].copy()
  d['incomplete']=~d.okved.astype('string').str.match(r'^\d{2}',na=False)|d.okved_section.isna()|d.okved_section.eq('')
  d['id']=norm(d.oktmo).map(mapping)
  for scope,z in [('all_valid_INN',d),('exact_point_code',d[d.id.notna()])]:
   rows.append(dict(year=y,scope=scope,n_entities=len(z),n_incomplete_classification=int(z.incomplete.sum()),fraction=float(z.incomplete.mean()),n_points_with_incomplete_classification=int(z.loc[z.incomplete,'id'].nunique())))
  raw[y]=d[['inn','id','incomplete']]
 c=raw[2016].merge(raw[2021],on='inn',suffixes=('_2016','_2021'),validate='one_to_one')
 same=c.id_2016.notna()&c.id_2021.notna()&c.id_2016.eq(c.id_2021)
 transition=[]
 for scope,z in [('all_common_INN',c),('same_exact_point_common_INN',c[same])]:
  for a in [False,True]:
   for b in [False,True]:
    transition.append(dict(scope=scope,incomplete_2016=a,incomplete_2021=b,n_entities=int((z.incomplete_2016.eq(a)&z.incomplete_2021.eq(b)).sum())))
 pd.DataFrame(rows).to_csv(O/'classification_missingness.csv',index=False);pd.DataFrame(transition).to_csv(O/'classification_missingness_common_INN.csv',index=False)
 (O/'CLASSIFICATION_AUDIT.json').write_text(json.dumps({'status':'DESCRIPTIVE_AUDIT','rows':rows,'transitions':transition,'source_interpretation':'RFSD primary paper reports harmonization to OKVED2 and activity-code imputation from adjacent years; this audit measures remaining incompleteness, not a demonstrated version mismatch. Missing classification is not absence of a service.','source_url':'https://www.nature.com/articles/s41597-025-05150-1','raw_harmonization_code_independently_reproduced':False,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
 print(pd.DataFrame(rows).to_string(index=False),flush=True)
if __name__=='__main__':main()

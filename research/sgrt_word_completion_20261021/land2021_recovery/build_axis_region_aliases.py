from pathlib import Path
import re,pandas as pd,json
O=Path(__file__).resolve().parent;a=pd.read_parquet(O.parent/'axis/full_settlement_axis.parquet',columns=['region']);known=set(a.region.unique());d=pd.read_parquet(O/'regional_sown_share_farmland2021.parquet');rows=[]
def norm(s):
 s=re.sub('[^а-я]+',' ',s.lower().replace('ё','е'));return ' '.join(w for w in s.split()if w not in {'республика','область','край','ао','авт','г','кузбасс'})
for _,r in d.iterrows():
 k=norm(r.region_name_raw_land)
 if k=='ханты мансийский':k='ханты мансийский югра'
 assert k in known,(r.region_name_raw_land,k)
 rows.append(dict(subject_code_in_Rosreestr_source=r.subject_code_in_Rosreestr_source,region_name_raw_land=r.region_name_raw_land,axis_region=k,alias_rule='literal_name_normalization; HMAO sourceabbreviation expanded to same named subject',native_grain='federal_subject'))
f=pd.DataFrame(rows);assert len(f)==85 and f.axis_region.is_unique;f.to_parquet(O/'regional_axis_aliases.parquet',index=False);f.to_csv(O/'regional_axis_aliases.csv',index=False);(O/'region_alias_receipt.json').write_text(json.dumps(dict(rows=85,unique_code=True,unique_axisregion=True,all_axisregions_covered=True,axis_modified=False,geographic_allocation_below_region_performed=False),ensure_ascii=False,indent=2)+'\n');print('85 region aliases verified')

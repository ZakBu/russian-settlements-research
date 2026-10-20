from pathlib import Path
import pandas as pd,re,json,hashlib
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010');P=RAW/'vologda_extracted/Населенные пункты.xlsx';OUT=ROOT/'vologda';OUT.mkdir(exist_ok=True)
def clean(v):return ''if pd.isna(v)else re.sub(r'\s+',' ',str(v)).strip()
types={'г.':'город','пгт':'пгт','деревня':'деревня','село':'село','посёлок':'посёлок','поселок':'посёлок','хутор':'хутор','починок':'починок','железнодорожная станция':'железнодорожная станция','железнодорожная казарма':'железнодорожная казарма','местечко':'местечко','разъезд':'разъезд','станция':'станция','населённый пункт':'населённый пункт'}
pat=re.compile(r'^('+'|'.join(re.escape(x)for x in sorted(types,key=len,reverse=True))+r')\s+(.+)$',re.I)
sha=hashlib.sha256(P.read_bytes()).hexdigest();d=pd.read_excel(P,header=None);rows=[];controls=[];county='';municipal=''
def num(x):
 if pd.isna(x):return None
 if isinstance(x,(int,float)):return int(x)
 s=clean(x);return int(s)if s.isdigit()else None
for i,r in d.iterrows():
 label=clean(r.iloc[0]);m=pat.match(label)
 if not label:continue
 if 'муниципальный район' in label.lower()or (label.startswith('Городской округ')and'области'not in label):county=label;municipal=''
 elif re.search(r'\b(?:сельское|городское) поселение\b',label,re.I):municipal=label
 values=[num(x)for x in r.iloc[1:4]]
 if not any(x is not None for x in values)and not m:continue
 row={'source_record_id':f'VOLOGDA2010:01-04:r{i+1}','census_year':2010,'census_reference_date':'2010-10-14','population_scope':'permanent_residents_at_census_in_2010_boundaries','region':'вологодская','source_page':None,'source_sheet':'01-04','source_row':i+1,'raw_caption':label,'primary_population':values[0],'primary_men':values[1],'primary_women':values[2],'raw_population':clean(r.iloc[1]),'raw_men':clean(r.iloc[2]),'raw_women':clean(r.iloc[3]),'sex_sum_valid':None if any(x is None for x in values)else values[0]==values[1]+values[2],'official_county':county,'official_municipality':municipal,'source_sha256':sha,'source_path':str(P),'source_grade':'official_primary_2010_full_locality_XLSX_table1_10R','not_model_input_without_root_review':True,'blank_or_dash_not_silently_zero':True}
 if m:row.update(settlement_name=m[2].strip(),settlement_type=types[m[1].lower()]);rows.append(row)
 else:row['row_role']='municipal_or_population_aggregate_control';controls.append(row)
f=pd.DataFrame(rows);c=pd.DataFrame(controls);f.to_parquet(OUT/'primary_source_NP_inventory.parquet',index=False);f.to_csv(OUT/'primary_source_NP_inventory.csv.gz',index=False);c.to_parquet(OUT/'primary_aggregate_controls.parquet',index=False)
r={'source_bytes':P.stat().st_size,'source_sha256':sha,'source_rows':len(d),'literal_NP_rows':len(f),'numeric_population_NP_rows':int(f.primary_population.notna().sum()),'NULL_dash_or_blank_NP_rows':int(f.primary_population.isna().sum()),'types':f.settlement_type.value_counts().to_dict(),'NP_numeric_population_sum':int(f.primary_population.sum()),'region_control_population':1202444,'NP_sum_minus_region_control':int(f.primary_population.sum()-1202444),'rural_NP_numeric_population_sum':int(f[~f.settlement_type.isin(['город','пгт'])].primary_population.sum()),'official_rural_control':352591,'rural_NP_rows':int((~f.settlement_type.isin(['город','пгт'])).sum()),'sex_sum_failures':int(f.sex_sum_valid.eq(False).sum()),'municipal_controls_not_promoted':len(c),'dash_population_interpretation':'NULL until exact source legend validated; not equivalent to absent NP record'};(OUT/'parse_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2))

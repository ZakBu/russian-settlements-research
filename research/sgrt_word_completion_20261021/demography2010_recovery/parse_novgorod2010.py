from pathlib import Path
import pandas as pd,re,json,hashlib
R=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010');O=R/'novgorod';O.mkdir(exist_ok=True);P=RAW/'novgorod2010_allNP.pdf';sha=hashlib.sha256(P.read_bytes()).hexdigest()
types={'усадьба':'усадьба','г.':'город','железнодорожная станция':'железнодорожная станция','населенный пункт':'населённый пункт','населённый пункт':'населённый пункт','деревня':'деревня','посёлок':'посёлок','поселок':'посёлок','село':'село','город':'город','пгт':'пгт','рабочий посёлок':'пгт','рабочий поселок':'пгт','разъезд':'разъезд','станция':'станция','местечко':'местечко','хутор':'хутор'};pat=re.compile(r'^('+'|'.join(re.escape(t)for t in sorted(types,key=len,reverse=True))+r')\s+(.+)$',re.I);nums=re.compile(r'^(.*?)\s{2,}(-|\d+)\s+(-|\d+)\s+(-|\d+)\s+(-|\d+(?:\.\d+)?)\s+(-|\d+(?:\.\d+)?)\s*$')
county='';municipal='';pending='';rows=[];controls=[];unparsed=[];line=0
for pi,page in enumerate((RAW/'novgorod2010_layout.txt').read_text().split('\f'),1):
 for li,s in enumerate(page.splitlines(),1):
  line+=1;t=s.strip()
  if re.fullmatch(r'[А-ЯЁ -]+РАЙОН',t):county=t.title();municipal='';pending='';continue
  if re.search(r'(?:сельское|городское) поселение',t):municipal=t;pending='';continue
  m=nums.match(s)
  if m:
   label=m[1].strip();label=(pending+' '+label).strip()if pending else label;pending='';mm=pat.match(label)
   vals=[int(x)if x.isdigit()else None for x in m.groups()[1:4]]
   row=dict(source_record_id=f'NOVGOROD2010:PDFp{pi}:line{li}',census_year=2010,census_reference_date='2010-10-14',population_scope='permanent_residents_at_census_in_2010_boundaries',region='новгородская',source_page=pi,source_printed_page=pi+30,source_line_start=li,source_line_end=li,raw_caption=label,primary_population=vals[0],primary_men=vals[1],primary_women=vals[2],raw_population=m[2],raw_men=m[3],raw_women=m[4],sex_sum_valid=None if any(x is None for x in vals)else vals[0]==vals[1]+vals[2],official_county=county,official_municipality=municipal,source_sha256=sha,source_path=str(P),source_grade='official_primary_2010_all_NP_municipal_district_table12_PDF',raw_pdf_line=s,not_model_input_without_root_review=True,blank_or_dash_not_silently_zero=True)
   if mm and not label.endswith(')'):row.update(settlement_name=mm[2],settlement_type=types[mm[1].lower()]);rows.append(row)
   else:controls.append(row)
  elif t in types:pending=t
  elif pat.match(t)and not t.endswith(')')and not any(x in t for x in ['Мужчины','Женщины']):pending=t
  elif pending and t and not t.isdigit():unparsed.append([pi,li,pending,t]);pending=''
f=pd.DataFrame(rows);c=pd.DataFrame(controls);f.to_parquet(O/'primary_source_NP_inventory.parquet',index=False);f.to_csv(O/'primary_source_NP_inventory.csv.gz',index=False);c.to_parquet(O/'primary_aggregate_controls.parquet',index=False);(O/'unparsed_caption_candidates.json').write_text(json.dumps(unparsed,ensure_ascii=False,indent=2));print('NP',len(f),'types',f.settlement_type.value_counts().to_dict(),'sum',f.primary_population.sum(),'NULL',f.primary_population.isna().sum(),'sexerrors',f.sex_sum_valid.eq(False).sum(),'counties',f.official_county.nunique(),'unparsed',unparsed[:10]);print(c[c.raw_caption.eq('Все население')][['official_county','primary_population']].to_string(index=False));print('control sum',c[c.raw_caption.eq('Все население')].primary_population.sum())

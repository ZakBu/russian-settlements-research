"""Literal scoped PDF parser. Municipality aggregates never become settlement rows."""
from pathlib import Path
import re,json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010');PDF=RAW/'bash_archived_original.pdf';OUT=ROOT/'bashkortostan';OUT.mkdir(exist_ok=True)
pat=re.compile(r'^(\s*)(.*?)\s{2,}(-|\d+)\s+(-|\d+)\s+(-|\d+)\s+(-|\d+(?:[,.]\d+)?)\s+(-|\d+(?:[,.]\d+)?)\s*$')
typepat=re.compile(r'^(населенный пункт|рабочий поселок|поселок городского типа|город|г\.|деревня|село|пос[её]лок|хутор)(?:\s+|(?=[А-ЯЁ]))(.+)$');tm={'населенный пункт':'населённый пункт','рабочий поселок':'пгт','поселок городского типа':'пгт','город':'город','г.':'город','деревня':'деревня','село':'село','поселок':'посёлок','посёлок':'посёлок','хутор':'хутор'}
newrow=re.compile(r'^(?:Муниципальный район|Сельское поселение|Городское поселение|Городской округ|населенный пункт|рабочий поселок|поселок городского типа|город|г\.|деревня|село|пос[её]лок|хутор)(?:\s|$|(?=[А-ЯЁ]))')
sourcehash=hashlib.sha256(PDF.read_bytes()).hexdigest();rows=[];controls=[];unresolved=[];county='';municipal='';pending=[];pendingln=None
for page,text in enumerate((RAW/'bash2010_layout.txt').read_text().split('\f'),1):
 if page<10:continue
 lines=text.splitlines();pending=[];pendingln=None
 for ln,line in enumerate(lines,1):
  if not line.strip():continue
  m=pat.match(line)
  if m:
   label=m[2].strip()
   if pending:label=' '.join(pending+[label]);start=pendingln
   else:start=ln
   pending=[];pendingln=None
   if label.startswith('Городской округ') or label.startswith('Муниципальный район'):county=label;municipal=''
   elif label.startswith(('Сельское поселение','Городское поселение')):municipal=label
   np=typepat.match(label)
   values=[0 if m[k]=='-' else int(m[k])for k in [3,4,5]]
   row={'source_record_id':f'BASH2010:p{page}:l{start}-{ln}','census_year':2010,'census_reference_date':'2010-10-14','population_scope':'permanent_residents_at_census_in_2010_boundaries','region':'башкортостан','source_page':page,'source_line_start':start,'source_line_end':ln,'raw_caption':label,'primary_population':values[0],'primary_men':values[1],'primary_women':values[2],'raw_population':m[3],'raw_men':m[4],'raw_women':m[5],'count_interpretation':'literal_number_or_zero_from_explicit_page3_dash_phenomenon_absent_legend','sex_sum_valid':values[0]==values[1]+values[2],'official_county':county,'official_municipality':municipal,'source_sha256':sourcehash,'source_path':str(PDF),'source_grade':'official_primary_2010_full_locality_bulletin','raw_pdf_lines_json':json.dumps(lines[start-1:ln],ensure_ascii=False),'not_model_input_without_root_review':True}
   if np:
    row.update(settlement_name=np[2].strip(),settlement_type=tm[np[1].lower()]);rows.append(row)
   else:
    row['row_role']='municipal_or_population_aggregate_control';controls.append(row)
   continue
  s=line.strip()
  if newrow.match(s):
   if pending:unresolved.append({'page':page,'line':pendingln,'pending_caption':' '.join(pending),'reason':'new_caption_before_numeric_row'})
   pending=[s];pendingln=ln
  elif pending:
   if not re.match(r'^(Продолжение|Муж|Жен|чины|щины|процентов|В общей|населения)',s)and not re.fullmatch(r'\d+',s):pending.append(s)
 if pending:unresolved.append({'page':page,'line':pendingln,'pending_caption':' '.join(pending),'reason':'end_page_without_numeric_row'})
d=pd.DataFrame(rows);c=pd.DataFrame(controls);d.to_parquet(OUT/'primary_source_NP_inventory.parquet',index=False);d.to_csv(OUT/'primary_source_NP_inventory.csv.gz',index=False);c.to_parquet(OUT/'primary_aggregate_controls.parquet',index=False);(OUT/'unparsed_caption_candidates.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2)+'\n')
r={'source_bytes':PDF.stat().st_size,'source_sha256':sourcehash,'all_pages':153,'table_pages':'10–153','literal_NP_rows':len(d),'types':d.settlement_type.value_counts().to_dict(),'NP_population_sum':int(d.primary_population.sum()),'region_control_population':4072292,'NP_sum_minus_region_control':int(d.primary_population.sum()-4072292),'rural_NP_population_sum':int(d[~d.settlement_type.isin(['город','пгт'])].primary_population.sum()),'official_rural_control':1610640,'rural_NP_rows':int((~d.settlement_type.isin(['город','пгт'])).sum()),'official_rural_count_control':4532,'sex_sum_failures':int((~d.sex_sum_valid).sum()),'unparsed_caption_candidates':len(unresolved),'municipal_controls_not_promoted':len(c),'source_blank_to_zero':False,'source_dash_interpreted_per_document_page3_legend':True,'zero_population_NP_rows':int(d.primary_population.eq(0).sum())};(OUT/'parse_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2))

from pathlib import Path
import re,json,hashlib,pandas as pd,gzip
E=Path(__file__).resolve().parent;PDF=E/'tula_2010_official_Tom1.pdf';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();PDFHASH=sha(PDF);text=gzip.open(E/'tula_2010_layout.txt.gz','rt').read();pages=text.split('\f');active=False;county='';countyrow='';muni='';rows=[];controls=[];unknown=[]
pat=re.compile(r'^(\s*)(.+?)\s{2,}(-|\d+)\s+(-|\d+)\s+(-|\d+)(?:\s|$)');typ=re.compile(r'^(сельский поселок|слобода|г\.|город|пгт|деревня|село|пос[её]лок|станция|хутор)\s+(.+)$',re.I);tm={'сельский поселок':'посёлок','слобода':'слобода','г.':'город','город':'город','пгт':'пгт','деревня':'деревня','село':'село','посёлок':'посёлок','поселок':'посёлок','станция':'станция','хутор':'хутор'};value=lambda x:None if x=='-'else int(x)
for page,txt in enumerate(pages,1):
 lines=txt.splitlines()
 if '12. ЧИСЛЕННОСТЬ НАСЕЛЕНИЯ ГОРОДСКИХ ОКРУГОВ' in txt:active=True
 if active and 'МЕТОДОЛОГИЧЕСКИЕ ПОЯСНЕНИЯ'in txt:active=False
 if not active:continue
 for ln,line in enumerate(lines,1):
  m=pat.match(line)
  if not m:continue
  label=m[2].strip();endln=ln
  if ln<len(lines)and lines[ln].strip()and not pat.match(lines[ln])and not any(q in lines[ln]for q in ['——','Продолжение','Мужчины','Женщины','население','населения']):
   label+=' '+lines[ln].strip();endln=ln+1
  nums=[value(m[k])for k in [3,4,5]];np=typ.match(label)
  if 'муниципальный район'in label or label.startswith('Городской округ '):
   county=label;countyrow=f'PDFpage{page}:line{ln}';muni=''
   if label=='Городской округ рабочий поселок'and ln<len(lines):county+=' '+lines[ln].strip()
  elif re.search(r'\b(?:городское|сельское) поселение\b',label,re.I):muni=label
  if np:
   t=tm[np[1].casefold()];name=re.sub(r'\s+(рп|дп|кп)$','',np[2],flags=re.I);r=dict(primary_source_record_id=f'TULA2010:Table12:PDFpage{page}:line{ln}',census_year=2010,region='тульская',settlement_type=t,settlement_name=name,raw_NP_caption=label,official_population=nums[0],official_men=nums[1],official_women=nums[2],raw_count_cells_json=json.dumps([m[k]for k in [3,4,5]],ensure_ascii=False),raw_pdf_line=line,source_pdf_page=page,source_line=ln,source_line_end=endln,official_county=county,county_header_locator=countyrow,official_municipality=muni,source_path=str(PDF.resolve()),source_sha256=PDFHASH,census_reference_date='2010-10-14',publication_year=2012,source_grade='direct_official_primary_2010_NP_publication',population_cell_numeric=nums[0]is not None,count_sex_consistency='PASS'if all(x is not None for x in nums)and nums[0]==nums[1]+nums[2]else'literal_unknown_sex_or_population'if any(x is None for x in nums)else'FAIL');rows.append(r)
  else:
   controls.append(dict(page=page,line=ln,caption=label,population=nums[0],men=nums[1],women=nums[2],raw_line=line))
   if not any(q in label.casefold()for q in ['населени','поселени','район','округ','область']):unknown.append(controls[-1])
d=pd.DataFrame(rows);d.to_csv(E/'tula_primary2010_full_NP_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(controls).to_csv(E/'tula_primary_aggregate_controls.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'status':'literal_source_NP_inventory_not_applied','NP_rows':len(d),'numeric_NP_rows':int(d.official_population.notna().sum()),'NULL_population_rows':int(d.official_population.isna().sum()),'numeric_NP_sum':int(d.official_population.sum()),'official_region_population':1553925,'difference':int(d.official_population.sum())-1553925,'count_sex_FAIL':int(d.count_sex_consistency.eq('FAIL').sum()),'unknown_numeric_captions':unknown,'primary_source_sha256':PDFHASH,'output_pins':{x:sha(E/x)for x in ['tula_primary2010_full_NP_inventory.csv.gz','tula_primary_aggregate_controls.csv.gz']}};(E/'tula_literal_parse_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2)[:6000]);
with gzip.GzipFile(str(E/'tula_2010_layout.txt.gz'),'wb',mtime=0)as f:f.write(text.encode())
if (E/'tula_2010_layout.txt').exists():(E/'tula_2010_layout.txt').unlink()

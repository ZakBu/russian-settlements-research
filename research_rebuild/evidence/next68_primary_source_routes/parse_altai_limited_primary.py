from pathlib import Path
import re,json,hashlib,gzip,pandas as pd
E=Path(__file__).resolve().parent;p=E/'altai_2010_official_Tom1.pdf';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();h=sha(p);txt=(E/'altai_2010_layout.txt').read_text();pages=txt.split('\f');rows=[];controls=[];active=False;county='';pat=re.compile(r'^\s*(.+?)\s{2,}(-|\d+)\s+(-|\d+)\s+(-|\d+)(?:\s|$)');tp=re.compile(r'^(г\.|рп|пгт|пос[её]лок|село)\s+(.+)$',re.I);tm={'г.':'город','рп':'пгт','пгт':'пгт','поселок':'посёлок','посёлок':'посёлок','село':'село'}
for page,t in enumerate(pages,1):
 if '5. ЧИСЛЕННОСТЬ НАСЕЛЕНИЯ КРАЯ, РАЙОНОВ'in t:active=True
 if active and '6. ГРУППИРОВКА'in t:active=False
 if not active:continue
 for ln,line in enumerate(t.splitlines(),1):
  m=pat.match(line)
  if not m:continue
  label=m[1].strip();nums=[None if m[k]=='-'else int(m[k])for k in [2,3,4]];q=tp.match(label)
  if re.search(r'район$',label)and not label.startswith(('Железнодорожный','Индустриальный','Ленинский','Октябрьский','Центральный')):county=label
  if q and not any(z in label for z in ['подчиненными','администрации']):
   name=re.sub(r'\s*\(рц\)$','',q[2]);rows.append(dict(source_record_id=f'ALTAI2010:Table5:PDFpage{page}:line{ln}',census_year=2010,region='алтайский',settlement_type=tm[q[1].casefold()],settlement_name=name,raw_NP_caption=label,population=nums[0],men=nums[1],women=nums[2],source_pdf_page=page,source_line=ln,raw_pdf_line=line,printed_district=county,source_path=str(p.resolve()),source_sha256=h,source_grade='direct_official_primary2010_limited_NP_table',publication_year=2012,table_scope='ruraldistrictcentres_and_ruralNP_atleast3000_plusurbanNP',is_complete_all_smallNP_inventory=False))
  else:controls.append(dict(page=page,line=ln,caption=label,population=nums[0],men=nums[1],women=nums[2],raw_line=line))
d=pd.DataFrame(rows);d.to_csv(E/'altai_primary2010_limited_NP_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(controls).to_csv(E/'altai_primary2010_table5_aggregate_and_otherNP_controls.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'status':'limited_scope_primary_publication_no_new_claims','named_NP_rows':len(d),'named_NP_population_sum':int(d.population.sum()),'official_regional_control':2419755,'all_smallNP_coverage':False,'control_remainder_not_allocated':2419755-int(d.population.sum()),'source_primary_sha256':h,'scope_proof':'PDFpage2 explicit ruraldistrictcentres and ruralNP3000+; Table5 title repeated same scope; прочие сельские населенные пункты aggregate retained ascontrol, not fabricated individualNP','license_printed':'Перепечатке и тиражированию не подлежит. При использовании информации данной публикации ссылка на нее обязательна.','no_individual_NP_claims_from_parent_counts':True,'output_pins':{x:sha(E/x)for x in ['altai_primary2010_limited_NP_inventory.csv.gz','altai_primary2010_table5_aggregate_and_otherNP_controls.csv.gz']}};(E/'altai_limited_source_inventory_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
with gzip.GzipFile(str(E/'altai_2010_layout.txt.gz'),'wb',mtime=0)as f:f.write(txt.encode())
(E/'altai_2010_layout.txt').unlink()

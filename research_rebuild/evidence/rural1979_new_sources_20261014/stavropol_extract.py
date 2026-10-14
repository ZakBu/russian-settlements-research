import xlrd,json,re,hashlib,collections
from pathlib import Path
root=Path('/workspace/shared/rural1979_new_sources');p=root/'stavropol/Cis89_02.xls';b=xlrd.open_workbook(p,formatting_info=True);s=b.sheet_by_index(0);rows=[];notes=[];district=None;selsovet=None;urban_parent=None
for i in range(s.nrows):
 v=s.row_values(i);name=str(v[1]).strip();code=str(v[0]).strip();font=b.font_list[b.xf_list[s.cell_xf_index(i,1)].font_index]
 if name.endswith('район'):district=name;selsovet=None;urban_parent=None
 if code.startswith('074') and len(code)==8 and code.endswith('000') and name.startswith('г.'):district=None;selsovet=None;urban_parent=name
 if 'сельсовет' in name.lower() and not name.lower().startswith('сельсоветы'):selsovet=name
 if not code or not re.fullmatch(r'\d{8}|\d{11}',code):
  if i>1135:notes.append({'excel_row':i+1,'raw_cells':v})
  continue
 level='rural_locality' if re.match(r'^(село |пос[её]лок |хутор |станица |деревня |аул )',name) else 'other_or_aggregate'
 if level=='rural_locality':
  rows.append(dict(region='Ставропольский край',district_context=district,urban_parent_context=urban_parent,selsovet_context=selsovet,settlement_type=name.split(' ')[0],name_clean=re.sub(r'\s*(?:\d+\)|\*\*?\)|\(р\.ц\.\)|\(\d{2}\.).*$', '',name).strip(),okato=code,name_raw=name,source_object_level=level,excel_sheet=s.name,excel_row=i+1,pop1989=v[2],pop2002=v[3],male1989=v[5],female1989=v[8],male2002=v[6],female2002=v[9],raw_cells=v,font_bold=bool(font.bold),font_italic=bool(font.italic),admission_block=bool(font.italic or font.bold or 'Этока 5)' in name),administrative_change_marker=bool(re.search(r'\d+\)|\*\*\)',name)),population_basis='unspecified_population_in_publication',source_1989_basis='1989 census adjusted for administrative-territorial changes registered after census',source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_url='http://stavrop.gks.ru/perepis/vpn2002/informaciya/Cis89_02.zip',retrieval_url='https://web.archive.org/web/20131015043725id_/http://stavrop.gks.ru/perepis/vpn2002/informaciya/Cis89_02.zip',retrieved_date='2026-10-14'))
(root/'stavropol_rows.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows));(root/'stavropol_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2));print(dict(rows=len(rows),bold=sum(r['font_bold'] for r in rows),italic=sum(r['font_italic'] for r in rows),valid_1989=sum(isinstance(r['pop1989'],(int,float)) for r in rows),sexsum_errors=sum(isinstance(r['pop1989'],(int,float)) and isinstance(r['male1989'],(int,float)) and isinstance(r['female1989'],(int,float)) and r['pop1989']!=r['male1989']+r['female1989'] for r in rows)))

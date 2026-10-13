from pathlib import Path
import pandas as pd,openpyxl,xlrd,json,hashlib,re
from bs4 import BeautifulSoup
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');W=Path('/workspace/settlements-work/sources/r2-missing');pins={}
def sha(f):
 v=hashlib.sha256(Path(f).read_bytes()).hexdigest();pins[str(f)]=v;return v
def clean(v):return re.sub(r'\s+',' ',str(v)).strip()
f=R/'research_rebuild/evidence/over500_north_20261009/direct_native_witnesses.csv.gz';sha(f);d=pd.read_csv(f,keep_default_na=False);d=d[d.literal_label_population_passed.eq(False)];assert len(d)==14
html=W/'arkhangelsk_2010_archived_original.html';hs=sha(html);trs=BeautifulSoup(html.read_bytes(),'html.parser').find('table').find_all('tr');kal=W/'kaliningrad_tom1.xlsx';ks=sha(kal);assert ks=='7e17a4bdb54e3ee8ff014c4311396f84c01b7f3ed38d12f4f9c1f9e6b100705f';ss=openpyxl.load_workbook(kal,data_only=True)['4'];tv=Path('/workspace/settlements-raw/data/raw/2002/015_90ef69f659_02c_Tver_obl.xls');ts=sha(tv);tt=xlrd.open_workbook(tv).sheet_by_name('!!!');out=[]
for r in d.to_dict('records'):
 sid=r['source_record_id'];row=dict(r);parents=[]
 if sid.startswith('ARK'):
  n=int(sid.rsplit('tr',1)[1]);cells=[clean(x.get_text(' ',strip=True)) for x in trs[n].find_all(['td','th'],recursive=False)];nonempty=[x for x in cells if x];label,pop=nonempty[:2];county=sub=None
  for i in range(n-1,-1,-1):
   text=clean(trs[i].get_text(' ',strip=True))
   if sub is None and 'сельское поселение' in text.lower():sub=(i,text)
   if 'муниципальный район' in text.lower():county=(i,text);break
  assert county and sub;f=html;digest=hs;sheet='html_table1';loc=f'table1 tr[{n}] 0-based / HTML row {n+1} 1-based; first/second nonempty cells';countytext=re.sub(r'\s+\d[\d ]*$','',county[1]);subtext=re.sub(r'\s+\d[\d ]*$','',sub[1]);cloc=f'table1 tr[{county[0]}] 0-based';sloc=f'table1 tr[{sub[0]}] 0-based';parents=[{'locator':cloc,'literal':county[1]},{'locator':sloc,'literal':sub[1]}];rawtype='посёлок' if label.startswith('посёлок') else 'деревня' if label.startswith('деревня') else 'населённый пункт'
 elif sid.startswith('KAL'):
  n=int(sid.rsplit('R',1)[1]);cells=[c.value for c in ss[n]];label,pop=cells[:2];county=sub=None
  for i in range(n-1,0,-1):
   c=ss.cell(i,1);v=c.value
   if v and sub is None and c.alignment.indent==3:sub=(i,v)
   if v and c.alignment.indent==1:county=(i,v);break
  assert county and sub;f=kal;digest=ks;sheet='4';loc=f"'4'!A{n}:F{n}; 1-based Excel row";countytext=county[1];subtext=sub[1];cloc=f"'4'!A{county[0]}:F{county[0]}";sloc=f"'4'!A{sub[0]}:F{sub[0]}";parents=[{'locator':cloc,'cells':[c.value for c in ss[county[0]]]},{'locator':sloc,'cells':[c.value for c in ss[sub[0]]]}];rawtype='посёлок'
 else:
  n=2583;cells=tt.row_values(n-1);label,pop=cells[3:5];f=tv;digest=ts;sheet='!!!';loc="'!!!'!D2583:E2583; 1-based Excel row";countytext=cells[1];subtext=tt.cell_value(2581,2);cloc="'!!!'!B2583";sloc="'!!!'!C2582:D2582";parents=[{'locator':cloc,'literal':countytext},{'locator':sloc,'cells':tt.row_values(2581)}];rawtype='ж/д ст.'
 assert float(pop)==float(r['native_population']),(sid,pop,r['native_population']);name=clean(r['native_name']).lower().replace('ё','е');literal=clean(label).lower().replace('ё','е');assert name in literal or literal.replace('населенный пункт ','') in name,(sid,name,literal)
 row.update(source_file=str(f),source_sha256=digest,source_row=n,source_sheet=sheet,source_locator=loc,raw_row_cells_json=json.dumps(cells,ensure_ascii=False,default=str),literal_label_population_passed=True,raw_source_label=label,raw_source_type=rawtype,raw_population_value=float(pop),actual_printed_county=countytext,actual_county_locator=cloc,actual_county_key=clean(countytext).lower(),primary_native_parent_header=subtext,primary_native_parent_locator=sloc,primary_native_parent_cells_json=json.dumps(parents,ensure_ascii=False,default=str),own_native_OKATO='',own_native_OKTMO='',own_native_code_status='not published in inspected source row/header; unknown',selected_type_preserved=True,native_quality_preserved=True,raw_type_matches_selected=(rawtype==r['native_type']),source_type_discrepancy='raw source посёлок vs selected село; do not silently repair selected type' if rawtype=='посёлок' and r['native_type']=='село' else '',source_admission_or_identity_decisions=0)
 out.append(row)
z=pd.DataFrame(out);assert z.source_record_id.is_unique;z.to_csv(O/'recovered_direct_native_witnesses.csv',index=False);(O/'source_manifest.json').write_text(json.dumps(pins,indent=2));receipt={'recovered':len(z),'exact_population_checks_passed':int(z.literal_label_population_passed.sum()),'custom_ARK_2010':int(z.source_record_id.str.startswith('ARK').sum()),'custom_KAL_2010':int(z.source_record_id.str.startswith('KAL').sum()),'Kulitsa2002':1,'type_discrepancies_documented':z[z.source_type_discrepancy.ne('')].source_record_id.tolist(),'native_population_quality_and_selected_types_changed':False,'point_or_edge_admissions':0};(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))

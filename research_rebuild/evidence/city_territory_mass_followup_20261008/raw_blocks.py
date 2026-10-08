from pathlib import Path
import xlrd
root=Path('/workspace/settlements-raw/data/raw')
for file,sheet,label,col in [('2010/008_342f3c208b_16._20Сиб_ФО_2010.xls','Sib','г. Барнаул',4),('2010/013_f60b2d2bcf_5._20Belg_Bryan_Vlad_Voron_Ivanov_Kalug_20L1_ethn_2010.xls','Data Sheet','г. Владимир',4),('2010/014_5ca759eea0_5._20Nizheg_Kirov_202010.xls','Data Sheet','Киров',4)]:
 s=xlrd.open_workbook(str(root/file)).sheet_by_name(sheet)
 hits=[n for n in range(s.nrows) if label==str(s.cell_value(n,col)).strip() or (label=='Киров' and str(s.cell_value(n,col)).strip()=='Ленинский район' and str(s.cell_value(n,3))=='Киров')]
 print(file,hits)
 for hit in hits:
  for n in range(hit,min(s.nrows,hit+145 if label=='Киров' else hit+40)):print(n+1,s.row_values(n)[:8])
for file in ['2002/057_9b18a354f1_02c_Sverdlovskaja_oblast.xls','2002/075_4c0ad1427f_02c_Sakha.xls','2002/047_9960082a3e_02c_Kirovskaja_new.xls']:
 if not (root/file).exists():continue
 s=xlrd.open_workbook(str(root/file)).sheet_by_index(0)
 for n in range(min(170,s.nrows)):
  if n<55 or (file.endswith('new.xls') and n>125):print(file,n+1,s.row_values(n)[:4])

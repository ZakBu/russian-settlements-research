import xlrd,pathlib,hashlib,json
Z=pathlib.Path(__file__).parent;cases=[('2002','048_4f024587eb_02c_Nizhegorod_obl_new.xls','11',[455]),('2010','014_5ca759eea0_5._20Nizheg_Kirov_202010.xls','Data Sheet',[265]),('2002','040_95a4475637_02c_Rostov_obl.xls','Sheet1',[2178]),('2010','004_486e984bdc_12._20Астр_Волгог_Ростов.xls','Южный',[3584]),('2002','032_184285f8dd_02c_kalmyk.xls','Sheet1',[279]),('2010','007_27e8a60d91_15._20Kalmykia.xls','калмыкия',[150])];out=[]
for yr,file,sh,targets in cases:
 p=pathlib.Path('/workspace/settlements-raw/data/raw')/yr/file;b=xlrd.open_workbook(str(p),on_demand=True);s=b.sheet_by_name(sh);rows=[]
 for target in targets:
  for i in range(max(0,target-26),min(s.nrows,target+3)):rows.append({'row_1based':i+1,'literal':s.row_values(i)})
 out.append({'source_file':str(p),'source_sha256':hashlib.file_digest(open(p,'rb'),'sha256').hexdigest(),'sheet':sh,'target_rows_1based':targets,'rows':rows});b.release_resources()
(Z/'literal_primary_native_witnesses.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('witnesses',len(out))

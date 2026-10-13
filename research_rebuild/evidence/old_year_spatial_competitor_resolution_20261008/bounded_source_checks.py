import pandas as pd,duckdb,json,re,struct,xlrd,sys,hashlib
from pathlib import Path
O=Path(__file__).parent;sys.path.insert(0,'/workspace/russian-settlements-research/research_rebuild/mass_linkage');from current_chain_state_20261007 import normalize,distance_km
f=pd.read_csv(O/'candidate_source_bound_spatial_edges.csv',dtype={'historical_okato_2009_raw':str,'historical_okato_2011_raw':str});top=f.nlargest(5,'old_population');rest=f[~f.from_source_record_id.isin(top.from_source_record_id)].sample(15,random_state=20261008);sample=pd.concat([top,rest]);c=duckdb.connect();meta=c.execute('select source_record_id,source_sheet,source_row,source_name_raw from read_parquet(?) where source_record_id in(select unnest(?))',['/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',sample.from_source_record_id.tolist()]).fetchdf().set_index('source_record_id');books={};out=[];dbf=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
with dbf.open('rb') as stream:
 hd=stream.read(32);hlen,rlen=struct.unpack_from('<HH',hd,8);fields=[];offset=1
 while True:
  desc=stream.read(32)
  if desc[0]==13:break
  field=desc[:11].split(b'\0')[0].decode();width=desc[16];fields.append((field,offset,width));offset+=width
 for z in sample.to_dict('records'):
  sid=z['from_source_record_id'];m=meta.loc[sid];p=next(v for v in [Path(z['old_source_file']),Path('/workspace/settlements-raw')/z['old_source_file'],Path('/workspace/russian-settlements-research')/z['old_source_file'],Path('/workspace/settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx') if z['old_source_file'].endswith('kaliningrad_2010_tom1.xlsx') else Path('/nonexistent')] if v.exists());sheet=str(m.source_sheet);rn=int(m.source_row);
  if p.suffix=='.pdf':
   import subprocess
   pg=int(re.search(r':p([0-9]+):',sid)[1]);text=subprocess.check_output(['pdftotext','-f',str(pg),'-l',str(pg),'-layout',str(p),'-']).decode();line=next(t for t in text.splitlines() if normalize(z['name']) in normalize(t));vals=re.split(r'\s{2,}',line.strip())
  elif p.suffix=='.xlsx':
   import openpyxl
   book=books.setdefault(str(p),openpyxl.load_workbook(p,read_only=True,data_only=True));sh=book[sheet] if sheet in book.sheetnames else book.worksheets[int(sheet)];vals=[x.value for x in sh[rn]]
  else:
   book=books.setdefault(str(p),xlrd.open_workbook(str(p)));sh=book.sheet_by_name(sheet) if sheet in book.sheet_names() else book.sheet_by_index(int(sheet));vals=sh.row_values(rn-1)
  labels=[(i,str(v)) for i,v in enumerate(vals) if isinstance(v,str) and normalize(z['name']) in normalize(v)];assert labels,(sid,vals);li,label=labels[0];nums=[]
  for v in vals[li+1:]:
   txt=str(v).replace(' ','').replace('\u00a0','')
   if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',txt):nums.append(float(txt))
  assert nums and nums[0]==z['old_population'],(sid,vals,nums,z['old_population']);record=int(z['old_raw_record_1based']);stream.seek(hlen+(record-1)*rlen);data=stream.read(rlen);raw={n:data[o:o+w].decode('cp1251').strip() for n,o,w in fields};gc=''.join(raw[k].zfill(n) for k,n in [('TER',2),('KOD1',3),('KOD2',3),('KOD3',3)]);assert gc==z['historical_okato_2011_raw'];assert (float(raw['LAT']),float(raw['LONG']))==(z['old_raw_latitude'],z['old_raw_longitude']);assert normalize(z['name']) in normalize(raw['NAME1']);out.append({'source_record_id':sid,'name':z['name'],'actual_raw_census_label':label,'actual_first_reported_population':nums[0],'actual_source_row_1based':rn,'actual_source_sheet':sheet,'raw_census_row_json':json.dumps(vals,ensure_ascii=False),'raw_dbf_record_1based':record,'raw_own_code':gc,'raw_own_label':raw['NAME1'],'raw_own_type':raw.get('SCOKATO'),'raw_record_sha256':hashlib.sha256(data).hexdigest(),'original_native_row_and_raw_point_binding_pass':True})
pd.DataFrame(out).to_csv(O/'fixed15_largest5_actual_source_checks.csv',index=False);print('actual source records checked',len(out),'all passed')

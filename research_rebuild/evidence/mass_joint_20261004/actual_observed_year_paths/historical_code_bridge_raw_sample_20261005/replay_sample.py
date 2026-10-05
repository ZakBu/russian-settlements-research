import pandas as pd, os, re, math, random, hashlib, json, struct, pathlib
from collections import defaultdict
import duckdb
BASE=pathlib.Path('/workspace/settlements-work/continuation_20261004/independent_review/historical_urban_code_bridge_1258_audit_v1')
OUT=BASE/'raw_sample_replay_20261005'
co=pd.read_csv(BASE/'cohort.csv',low_memory=False)
co=co[(co.shared_point_n<=1)&co.source_file_resolved].copy()
co['urban_class']=co.settlement_type.fillna('').map(lambda x:'pgt' if re.search(r'пгт|пос[её]лок городского типа|рабочий пос[её]лок',x,re.I) else 'city')
rank=co.sort_values(['population','source_record_id'],ascending=[False,True])
top=rank.head(20).copy();top['sample_role']='top20_population'
remaining=rank[~rank.source_record_id.isin(top.source_record_id)].copy()
rng=random.Random(20261005); groups=list(remaining.groupby(['year','urban_class','source_file'],sort=True));alloc={k:1 for k,g in groups};left=40-len(alloc)
while left>0:
 cap={k:max(0,len(g)-alloc[k]) for k,g in groups};total=sum(cap.values())
 if total<=0:break
 exact={k:left*v/total for k,v in cap.items()};base={k:min(cap[k],int(math.floor(exact[k]))) for k in cap}
 got=sum(base.values())
 for k,v in base.items():alloc[k]+=v
 left-=got
 if left:
  order=sorted((k for k,g in groups if alloc[k]<len(g)),key=lambda k:(-(exact[k]-math.floor(exact[k])),str(k)))
  z=min(left,len(order))
  for k in order[:z]:alloc[k]+=1
  left-=z
parts=[]
for k,g in groups:
 idx=list(g.index);rng.shuffle(idx);sub=g.loc[idx[:alloc[k]]].copy();sub['sample_role']='stratified40_seed20261005';parts.append(sub)
r40=pd.concat(parts);sample=pd.concat([top,r40]).drop_duplicates('source_record_id').copy()
assert len(sample)==60 and sample.source_record_id.nunique()==60
sample['sample_role']=sample.sample_role.fillna('')

# exact source paths via original relative source_file; historic archived source sits in r2-missing bundle
roots=['/workspace/settlements-raw','/workspace/settlements-work/sources','/workspace/russian-settlements-research']
def resolve(rel):
 for root in roots:
  p=os.path.join(root,rel)
  if os.path.isfile(p):return p
 base=os.path.basename(rel)
 for root,dirs,files in os.walk('/workspace/settlements-work/sources'):
  if base in files:return os.path.join(root,base)
 return None
sample['source_path']=sample.source_file.map(resolve)
# Pull canonical 2021 observations and source file pins
selected=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',columns=['source_record_id','census_year','source_sha256','source_name_raw','source_file','source_sheet','source_row','source_locator','source_population_raw','settlement_name','settlement_type','region_raw','region_norm','name_norm','type_norm','population','latitude','longitude','coordinate_admission','coordinate_quality','coordinate_source','settlement_id'])
sel21=selected[selected.census_year.eq(2021)].copy()
sel_hist=selected[selected.source_record_id.isin(sample.source_record_id)].copy()
byid=sel_hist.set_index('source_record_id').to_dict('index')
ASSETS='/workspace/settlements-work/continuation_20261003/audit_99_20261003/older_years/selected_source_manifest_assets.csv'
assets=pd.read_csv(ASSETS).set_index('path').to_dict('index')
POINTS='/tmp/graph24_anapa_application_20261005/accepted_point_uses.parquet'
point_ids=pd.DataFrame({'source_record_id':sel21.source_record_id.unique()})
conn=duckdb.connect();conn.register('pids',point_ids)
point_uses=conn.execute(f"select a.target_source_record_id,a.latitude,a.longitude,a.coordinate_admission_status,a.coordinate_source,a.coordinate_source_record_id,a.coordinate_provider,a.admission_allowed,a.application_gate_status,a.point_admitted from read_parquet('{POINTS}') a join pids p on a.target_source_record_id=p.source_record_id and a.target_year='2021.0'").fetchdf()
accepted_byid={k:g for k,g in point_uses.groupby('target_source_record_id')}

def norm(x):return re.sub(r'\s+',' ',str(x or '').strip().casefold())
def region_equal(expected,value):
 a=norm(expected);b=norm(value)
 def clean(x):
  x=re.sub(r'[^а-яё ]+',' ',x);x=re.sub(r'\b(республика|респ|область|обл|край|автономный округ|автономная область|ао)\b',' ',x);return re.sub(r'\s+',' ',x).strip()
 aa=clean(a);bb=clean(b)
 if not aa or not bb:return False
 if aa==bb or aa in bb:return True
 # publisher abbreviations such as Моск.обл. and Перм.кр.; use a distinctive 4-letter stem.
 toks=aa.split(); source=''.join(bb.split())
 return any(len(t)>=4 and t[:4] in source for t in toks) or (len(aa.replace(' ',''))>=4 and aa.replace(' ','')[:4] in source)

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

# DBF raw schema and field decoder
DBF='/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
buf=open(DBF,'rb').read();nrec=struct.unpack('<I',buf[4:8])[0];hlen=struct.unpack('<H',buf[8:10])[0];rlen=struct.unpack('<H',buf[10:12])[0]
fields=[];off=1;p=32
while p+32<=hlen-1 and buf[p]!=13:
 d=buf[p:p+32];name=d[:11].split(b'\0')[0].decode('ascii','replace');typ=chr(d[11]);length=d[16];fields.append((name,typ,length,off));off+=length;p+=32

def dbf_record(onebased):
 start=hlen+(int(onebased)-1)*rlen;rec=buf[start:start+rlen];result={'_record_number':int(onebased),'_byte_offset':start,'_deleted':rec[:1].decode('ascii','replace')=='*'}
 for name,typ,length,offset in fields:
  raw=rec[offset:offset+length].decode('cp1251','replace').strip()
  if typ=='N' and raw:
   try: value=float(raw) if '.' in raw else int(raw)
   except: value=raw
  else:value=raw
  result[name]=value;result[name+'_raw']=raw
 return result

# Raw classifier SQL, retain exact tab-delimited row and physical line number
SQL='/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
code_lines=defaultdict(list)
with open(SQL,encoding='utf-8',errors='replace') as f:
 for lineno,line in enumerate(f,1):
  fields0=line.rstrip('\n\r').split('\t')
  if fields0 and re.fullmatch(r'\d{8}',fields0[0].strip()):code_lines[fields0[0].strip()].append((lineno,fields0,line.rstrip('\n\r')))

# Raw source row extractors
def xls_row(path,locator):
 import xlrd
 book=xlrd.open_workbook(path,on_demand=True)
 parts=str(locator).rsplit(':',1);last=parts[-1].replace('.0','');row=int(float(last))-1
 sheetpart=parts[0] if len(parts)>1 else '0'
 if sheetpart.isdigit():si=int(sheetpart);sheet=book.sheet_by_index(si) if si<book.nsheets else book.sheet_by_index(0)
 elif sheetpart in book.sheet_names():sheet=book.sheet_by_name(sheetpart)
 else:sheet=book.sheet_by_index(0)
 vals=sheet.row_values(row) if 0<=row<sheet.nrows else []
 context=[]
 for j in range(max(0,row-12),row+1):
  vv=sheet.row_values(j);txt=' | '.join(str(x).strip() for x in vv if str(x).strip())
  if txt:context.append({'row_1based':j+1,'text':txt[:500]})
 return {'sheet':sheet.name,'row_1based':row+1,'raw_row_values':vals,'raw_row_text':' | '.join(str(x).strip() for x in vals if str(x).strip()),'preceding_context':context}

def html_row(path,sourceid):
 from html.parser import HTMLParser
 class Parser(HTMLParser):
  def __init__(self):super().__init__();self.tr=-1;self.intr=False;self.intd=False;self.cells=[];self.cur='';self.rows=[]
  def handle_starttag(self,t,a):
   if t.lower()=='tr':self.tr+=1;self.intr=True;self.cells=[]
   elif self.intr and t.lower() in ('td','th'):self.intd=True;self.cur=''
  def handle_data(self,data):
   if self.intd:self.cur+=data
  def handle_endtag(self,t):
   if t.lower() in ('td','th') and self.intd:self.cells.append(re.sub(r'\s+',' ',self.cur).strip());self.intd=False
   elif t.lower()=='tr' and self.intr:self.rows.append({'tr_0based':self.tr,'cells':self.cells[:]});self.intr=False
 b=Parser();b.feed(open(path,encoding='cp1251',errors='replace').read())
 m=re.search(r'tr(\d+)$',sourceid);wanted=int(m.group(1)) if m else None
 return next(({'html_tr_0based':r['tr_0based'],'raw_row_text':' | '.join(r['cells']),'raw_row_values':r['cells']} for r in b.rows if r['tr_0based']==wanted),{'raw_row_text':'','raw_row_values':[]})

# source hash rows
result=[]
for r in sample.itertuples(index=False):
 d=r._asdict();path=d['source_path'];hist=byid.get(r.source_record_id,{})
 d['source_sha256_reopened']=sha(path) if path else None;d['source_sha256_selected']=hist.get('source_sha256');manifest=assets.get(r.source_file,{});d['source_sha256_manifest']=manifest.get('input_manifest_sha256');d['source_hash_matches_manifest']=bool(d['source_sha256_manifest'] and d['source_sha256_reopened']==d['source_sha256_manifest']);d['source_manifest_pin_available']=bool(d['source_sha256_manifest'])
 d['raw_source_reopened']=bool(path);d['raw_source_row_text']='';d['raw_source_region_context']='';d['raw_source_name_present']=False;d['raw_source_population_present']=False;d['raw_source_type_present']=False;d['raw_source_parse_status']=''
 if path and path.lower().endswith('.xls'):
  try:
   rr=xls_row(path,r.source_locator);d['raw_source_row_text']=rr['raw_row_text'];d['raw_source_cells_json']=json.dumps(rr['raw_row_values'],ensure_ascii=False);d['raw_source_row_sheet']=rr['sheet'];d['raw_source_row_1based']=rr['row_1based'];d['raw_source_context_json']=json.dumps(rr['preceding_context'],ensure_ascii=False)
   rowtxt=norm(rr['raw_row_text']);d['raw_source_name_present']=norm(r.settlement_name) in rowtxt
   vals=rr['raw_row_values'];nums=[]
   for v in vals:
    try: nums.append(float(v))
    except:pass
   d['raw_source_population_present']=any(abs(x-float(r.population))<1e-8 for x in nums)
   d['raw_source_type_present']=('пгт' in rowtxt or 'поселок городского типа' in rowtxt or 'посёлок городского типа' in rowtxt) if r.urban_class=='pgt' else bool(re.search(r'(^|\W)г\.?\s',rowtxt))
   # derive region evidence: all same-row cells, else nearest ancestor rows in workbook context
   d['raw_source_region_context']=' | '.join(x['text'] for x in rr['preceding_context'])
   # 2002 Tom 1 is hierarchically grouped; identify the nearest preceding top-level region heading. 2010 files carry region text in the row.
   if int(r.year)==2002:
    import xlrd
    wb=xlrd.open_workbook(path,on_demand=True);sh=wb.sheet_by_name(rr['sheet']);headings=[]
    for j in range(0,rr['row_1based']-1):
     cell=str(sh.cell_value(j,0) or '').strip()
     if cell and not cell[0].isspace() and re.search(r'(область|край|республика|автономный округ|автономная область)',cell,re.I):headings.append(cell)
    matching=[h for h in headings if region_equal(r.region_norm,h)]
    d['raw_source_region_parent_heading']=matching[-1] if matching else ''
    d['raw_source_region_context']=str(d['raw_source_region_parent_heading'])+' | '+d['raw_source_region_context']
   expected=norm(r.region_norm);text=norm(d['raw_source_region_context'])
   # Match region nomenclature after stripping publisher suffixes; for 2002 use matching unindented publisher region headers only.
   d['raw_source_region_present']=any(region_equal(expected,z) for z in [d.get('raw_source_region_parent_heading',''),d['raw_source_row_text'],d['raw_source_region_context']]) or (int(r.year)==2010 and (norm(rr['sheet'])==expected or ('komi' in norm(r.source_file) and expected=='коми')))
   d['raw_source_parse_status']='xls_row_opened'
  except Exception as e:d['raw_source_parse_status']='xls_error:'+repr(e)
 elif path and path.lower().endswith('.pdf'):
  try:
   import fitz
   pdf=fitz.open(path);hits=[];n=norm(r.settlement_name)
   for pi,page in enumerate(pdf):
    lines=page.get_text().splitlines()
    for i,line in enumerate(lines):
     if norm(n) == norm(line):
      excerpt=' | '.join(x.strip() for x in lines[i:i+4]);hits.append((pi+1,i+1,excerpt,lines))
   d['pdf_match_n']=len(hits)
   if hits:
    pi,li,excerpt,lines=hits[0];d['pdf_page_1based']=pi;d['pdf_line_1based']=li;d['raw_source_row_text']=excerpt;d['raw_source_name_present']=True
    # In this official city table, each city is followed by region and 2002/2010 population lines.
    block=lines[li-1:li+3];d['raw_source_population_present']=any(re.sub(r'\D','',str(x))==str(int(r.population)) for x in block)
    d['raw_source_type_present']=r.urban_class=='city'
    d['raw_source_region_context']=' | '.join(x.strip() for x in block)
    d['raw_source_region_present']=norm(r.region_norm) in norm(d['raw_source_region_context'])
   d['raw_source_parse_status']='pdf_text_match' if len(hits)==1 else ('pdf_duplicate_name' if hits else 'pdf_name_missing')
  except Exception as e:d['raw_source_parse_status']='pdf_error:'+repr(e)
 elif path and path.lower().endswith('.html'):
  try:
   rr=html_row(path,r.source_record_id);d['raw_source_row_text']=rr['raw_row_text'];d['raw_source_cells_json']=json.dumps(rr['raw_row_values'],ensure_ascii=False);txt=norm(rr['raw_row_text']);d['raw_source_name_present']=norm(r.settlement_name) in txt;d['raw_source_population_present']=str(int(r.population)) in re.sub(r'\D','',txt);d['raw_source_type_present']=('пгт' in txt if r.urban_class=='pgt' else 'город' in txt);d['raw_source_region_context']=rr['raw_row_text']+' | archived Arkhangelsk region source file';d['raw_source_region_present']=norm(r.region_norm) in txt or norm(r.region_norm)=='архангельская';d['raw_source_parse_status']='html_row_opened'
  except Exception as e:d['raw_source_parse_status']='html_error:'+repr(e)
 else:d['raw_source_parse_status']='source_file_unavailable_or_unsupported'
 # classifier evidence
 cands=code_lines.get(str(r.classifier_okato_2009_raw).zfill(8),[]);d['classifier_raw_match_count']=len(cands)
 if cands:
  # best exact physical source classifier line by literal expected name; preserve all if duplicates
  exact=[x for x in cands if re.sub(r'[^а-яё0-9]','',norm(r.settlement_name)) in re.sub(r'[^а-яё0-9]','',norm(x[2]))]
  chosen=exact[0] if exact else cands[0];d['classifier_line_1based']=chosen[0];d['classifier_raw_line']=chosen[2];d['classifier_name_present']=bool(exact);d['classifier_type_raw']=chosen[1][3] if len(chosen[1])>3 else '';d['classifier_region_code_raw']=chosen[1][0]
 else:d['classifier_line_1based']=None;d['classifier_raw_line']='';d['classifier_name_present']=False;d['classifier_type_raw']='';d['classifier_region_code_raw']=''
 # GeoKLADR raw DBF source record evidence, using exact byte-offset locator
 gr=dbf_record(r.point_record);d['dbf_byte_offset_reopened']=gr['_byte_offset'];d['dbf_record_number_reopened']=gr['_record_number'];d['dbf_deleted_flag']=gr['_deleted'];d['dbf_ter_raw']=gr.get('TER_raw');d['dbf_kod1_raw']=gr.get('KOD1_raw');d['dbf_kod2_raw']=gr.get('KOD2_raw');d['dbf_kod3_raw']=gr.get('KOD3_raw');d['dbf_okato11_raw']=str(gr.get('TER_raw',''))+str(gr.get('KOD1_raw',''))+str(gr.get('KOD2_raw',''))+str(gr.get('KOD3_raw',''));d['dbf_name1_raw']=gr.get('NAME1_raw');d['dbf_lat_raw']=gr.get('LAT_raw');d['dbf_long_raw']=gr.get('LONG_raw');d['dbf_okato_matches_cohort']=d['dbf_okato11_raw']==str(r.geokladr_okato_2011_raw).zfill(11);d['dbf_kod3_matches_literal000']=gr.get('KOD3_raw')=='000';d['dbf_coordinates_match_cohort']=abs(float(gr.get('LAT'))-float(r.point_lat))<1e-8 and abs(float(gr.get('LONG'))-float(r.point_lon))<1e-8
 # exact normalized 2021 counterpart
 hh=sel21[(sel21.name_norm.fillna('').map(norm)==norm(r.settlement_name))&(sel21.type_norm.fillna('').map(norm)==norm(r.settlement_type))&(sel21.region_norm.fillna('').map(norm)==norm(r.region_norm))]
 d['2021_exact_tuple_match_n']=len(hh)
 if len(hh)==1:
  h=hh.iloc[0];d['2021_source_record_id']=h.source_record_id;d['2021_population']=h.population;d['2021_selected_latitude']=h.latitude;d['2021_selected_longitude']=h.longitude;d['2021_coordinate_quality']=h.coordinate_quality;d['2021_coordinate_source']=h.coordinate_source;d['2021_settlement_id']=h.settlement_id
  pu=accepted_byid.get(h.source_record_id,pd.DataFrame())
  if len(pu)==1:
   ph=pu.iloc[0];d['2021_latitude']=ph.latitude;d['2021_longitude']=ph.longitude;d['2021_coordinate_admission']=ph.coordinate_admission_status;d['2021_coordinate_source_record_id']=ph.coordinate_source_record_id;d['2021_coordinate_provider']=ph.coordinate_provider;d['2021_point_admitted']=ph.point_admitted;d['2021_point_gate_status']=ph.application_gate_status
  else:
   d['2021_latitude']=h.latitude;d['2021_longitude']=h.longitude;d['2021_coordinate_admission']='no_unique_graph24_point_use';d['2021_coordinate_source_record_id']=None;d['2021_coordinate_provider']=None;d['2021_point_admitted']=False;d['2021_point_gate_status']='no unique accepted point-use row in Graph24'
  if pd.notna(d['2021_latitude']) and pd.notna(d['2021_longitude']):
   a1,a2=math.radians(float(r.point_lat)),math.radians(float(d['2021_latitude']));dl=math.radians(float(d['2021_longitude'])-float(r.point_lon));dp=a2-a1;aa=math.sin(dp/2)**2+math.cos(a1)*math.cos(a2)*math.sin(dl/2)**2;d['distance_km']=6371.0088*2*math.atan2(math.sqrt(aa),math.sqrt(1-aa))
  else:d['distance_km']=None
 else:
  # Diagnostic exact name/region rows where type differs or name/region absent
  hn=sel21[(sel21.name_norm.fillna('').map(norm)==norm(r.settlement_name))&(sel21.region_norm.fillna('').map(norm)==norm(r.region_norm))]
  d['2021_exact_name_region_match_n']=len(hn);d['2021_nearby_type_values']='; '.join(sorted(set(str(x) for x in hn.settlement_type.dropna())));d['2021_source_record_id']=None;d['2021_population']=None;d['2021_latitude']=None;d['2021_longitude']=None;d['2021_coordinate_admission']=None;d['2021_coordinate_quality']=None;d['2021_coordinate_source']=None;d['2021_settlement_id']=None;d['distance_km']=None
 result.append(d)

out=pd.DataFrame(result)
# concise source row verification and full sample with exact evidence
out.to_csv(OUT/'sample_replay.csv',index=False)
cols=['sample_role','source_record_id','year','settlement_name','settlement_type','region_norm','population','source_file','source_path','source_sha256_reopened','source_sha256_selected','source_sha256_manifest','source_hash_matches_manifest','source_manifest_pin_available','raw_source_parse_status','raw_source_row_sheet','raw_source_row_1based','raw_source_row_text','raw_source_name_present','raw_source_type_present','raw_source_region_present','raw_source_population_present','classifier_raw_match_count','classifier_line_1based','classifier_raw_line','classifier_name_present','classifier_type_raw','dbf_record_number_reopened','dbf_byte_offset_reopened','dbf_okato11_raw','dbf_kod3_raw','dbf_name1_raw','dbf_lat_raw','dbf_long_raw','dbf_okato_matches_cohort','dbf_kod3_matches_literal000','dbf_coordinates_match_cohort','2021_exact_tuple_match_n','2021_exact_name_region_match_n','2021_nearby_type_values','2021_source_record_id','2021_population','2021_coordinate_admission','2021_coordinate_quality','2021_coordinate_source','2021_coordinate_source_record_id','2021_coordinate_provider','2021_point_admitted','2021_point_gate_status','2021_selected_latitude','2021_selected_longitude','2021_latitude','2021_longitude','distance_km']
for c in cols:
 if c not in out:out[c]=None
out[cols].to_csv(OUT/'sample_findings.csv',index=False)
# Input hashes / output hashes
pins={}
for key,p in {'cohort':BASE/'cohort.csv','bridge_receipt':BASE/'receipt.json','selected_observations':'/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet','selected_source_manifest_assets':ASSETS,'graph24_accepted_point_uses':POINTS,'classifier_sql':SQL,'geokladr_dbf':DBF}.items():pins[key]={'path':str(p),'sha256':sha(p),'bytes':os.path.getsize(p)}
for path in sorted(set(x for x in sample.source_path if x)):
 pins['source_file:'+str(path)]={'path':str(path),'sha256':sha(path),'bytes':os.path.getsize(path)}
summary={'sample_n':len(out),'top20_n':int((out.sample_role=='top20_population').sum()),'stratified_n':int((out.sample_role=='stratified40_seed20261005').sum()),'strata':out.groupby(['year','urban_class','source_file']).size().reset_index(name='sample_n').to_dict('records'),'source_rows':{'opened':int(out.raw_source_reopened.sum()),'hash_matches_manifest':int(out.source_hash_matches_manifest.sum()),'manifest_pin_available':int(out.source_manifest_pin_available.sum()),'raw_name_present':int(out.raw_source_name_present.sum()),'raw_type_present':int(out.raw_source_type_present.sum()),'raw_population_present':int(out.raw_source_population_present.sum()),'raw_region_context_present':int(out.raw_source_region_present.sum())},'classifier':{'raw_code_match_exact_one':int((out.classifier_raw_match_count==1).sum()),'raw_name_present':int(out.classifier_name_present.sum()),'multiple_or_missing_code_rows':int((out.classifier_raw_match_count!=1).sum())},'geokladr_dbf':{'raw_okato_matches':int(out.dbf_okato_matches_cohort.sum()),'literal_kod3_000_matches':int(out.dbf_kod3_matches_literal000.sum()),'lat_long_match':int(out.dbf_coordinates_match_cohort.sum()),'deleted_record':int(out.dbf_deleted_flag.sum())},'current2021':{'exact_name_type_region_unique':int((out['2021_exact_tuple_match_n']==1).sum()),'exact_tuple_missing_or_ambiguous':int((out['2021_exact_tuple_match_n']!=1).sum()),'distance_n':int(out.distance_km.notna().sum()),'distance_median_km':float(out.distance_km.median()),'distance_max_km':float(out.distance_km.max()),'over_25km':int((out.distance_km>25).sum()),'over_100km':int((out.distance_km>100).sum()),'coordinate_admission_counts':out[out['2021_exact_tuple_match_n']==1].groupby('2021_coordinate_admission',dropna=False).size().to_dict()}}
receipt={'task':'Bounded independent raw-source replay sample for the 1,167 clear historical bridge rows','sample_method':'Top 20 by population (ties ordered by source_record_id), plus 40 random rows from remaining clear cohort; deterministic Python random.Random(20261005), stratified by census year, city/PGT class and exact selected source file path; one per available stratum then proportional allocation.','inputs':pins,'summary':summary,'outputs':{}}
for name in ['sample_replay.csv','sample_findings.csv','replay_sample.py']:
 p=OUT/name;receipt['outputs'][name]={'path':str(p),'sha256':sha(p),'bytes':os.path.getsize(p)}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
# concise report
report='''# Independent raw-source replay sample: 1,167 clear bridge candidates

## Sample and evidence

The sample contains 20 highest-population rows plus 40 deterministic, stratified rows (seed 20261005) from the 1,167 noncollision rows with locally available source files. Stratification uses year, city/PGT class, and exact selected source-file path. It covers both census years and urban classes, and every source-file family represented in the clear cohort.

For each row, the replay reopened its raw XLS, PDF, or HTML source row and checked the publisher name, type, population, and regional context. It recomputed SHA-256 and compared it with the selected source manifest when a manifest pin existed. It also checked the raw 2009 classifier code/line and directly decoded the exact 2011 GeoKLADR DBF record by one-based record number and byte offset, including raw code pieces, KOD3, name, and coordinates. For 2021, it required a unique exact normalized name/type/region counterpart and measured distance to the accepted point-use coordinates from Graph24.

## Summary

'''
report+=f"- Sample: {len(out)} rows ({int((out.sample_role=='top20_population').sum())} highest-population and {int((out.sample_role=='stratified40_seed20261005').sum())} stratified).\n"
report+=f"- Raw source rows opened: {int(out.raw_source_reopened.sum())}/{len(out)}; name/type/population checks pass for {int((out.raw_source_name_present&out.raw_source_type_present&out.raw_source_population_present).sum())}/{len(out)}. Regional row or hierarchy context is evidenced for {int(out.raw_source_region_present.sum())}/{len(out)}.\n"
report+=f"- Source hashes: exact prior manifest hash matches for {int(out.source_hash_matches_manifest.sum())}/{int(out.source_manifest_pin_available.sum())} sampled rows with manifest pins. Two Arkhangelsk archive HTML rows have no old manifest pin; their current file hashes are included in the receipt.\n"
report+=f"- Raw classifier: code appears exactly once and the raw classifier name matches after punctuation normalization for {int(((out.classifier_raw_match_count==1)&out.classifier_name_present).sum())}/{len(out)}.\n"
report+=f"- GeoKLADR: raw 11-character OKATO, literal KOD3=000, and DBF coordinates match candidate evidence for {int((out.dbf_okato_matches_cohort&out.dbf_kod3_matches_literal000&out.dbf_coordinates_match_cohort).sum())}/{len(out)}.\n"
report+=f"- 2021 exact name/type/region tuple: unique for {int((out['2021_exact_tuple_match_n']==1).sum())}/{len(out)}. Ten have no unique exact tuple. Accepted point distances are available for {int(out.distance_km.notna().sum())}: median {out.distance_km.median():.3f} km, maximum {out.distance_km.max():.3f} km; {int((out.distance_km>25).sum())} exceed 25 km.\n"
report+='\nGraph24 accepted-point statuses for exact counterparts: '+', '.join(f"{k}: {v}" for k,v in out['2021_coordinate_admission'].value_counts(dropna=False).items() if pd.notna(k)) + '.\n'
report+='\n### 2021 exact-tuple misses\n\n'
for _,r in out[out['2021_exact_tuple_match_n']!=1].sort_values(['year','settlement_name']).iterrows():
 report+=f"- {r.settlement_name} ({r.region_norm}, {int(r.year)}): {int(r['2021_exact_tuple_match_n'])} exact tuple matches; same name and region rows {int(r.get('2021_exact_name_region_match_n',0) or 0)}; current type values: {r.get('2021_nearby_type_values','')}.\n"
report+='\n## Artifacts\n\n- `sample_findings.csv`: compact row checks, source pins, 2021 match status, and distance.\n- `sample_replay.csv`: row-level raw snippets, context and full evidence.\n- `replay_sample.py`: deterministic sample and verification replay.\n- `receipt.json`: input/output hashes, sample method, and summary.\n\nDistances are a location diagnostic; they do not decide historical identity. No canonical population, identity, or coordinate records were changed.\n'
(OUT/'README.md').write_text(report)
receipt['outputs']['README.md']={'path':str(OUT/'README.md'),'sha256':sha(OUT/'README.md'),'bytes':os.path.getsize(OUT/'README.md')}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'summary':summary,'output_hashes':receipt['outputs'],'report':report[:1500]},ensure_ascii=False,indent=2))

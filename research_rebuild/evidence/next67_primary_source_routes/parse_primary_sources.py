from pathlib import Path
import pandas as pd,xlrd,email,re,json,hashlib,collections
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();clean=lambda x:re.sub(r'\s+',' ',str(x)).strip();norm=lambda x:re.sub(r'[^а-яa-z0-9]+',' ',clean(x).casefold().replace('ё','е').replace('ѐ','е')).strip()
T=[('железнодорожный разъезд','железнодорожный разъезд'),('маяк','маяк'),('железнодорожная площадка посёлок','железнодорожная площадка посёлок'),('железнодорожная будка','железнодорожная будка'),('железнодорожная станция','железнодорожная станция'),('разъезд посёлок','разъезд посёлок'),('разъезд поселок','разъезд посёлок'),('отдельный дом','отдельный дом'),('дом отдыха','дом отдыха'),('населенный пункт','населённый пункт'),('посёлок городского типа','пгт'),('поселок городского типа','пгт'),('посёлок','посёлок'),('поселок','посёлок'),('деревня','деревня'),('станция','станция'),('станица','станица'),('кордон','кордон'),('казарма','казарма'),('площадка','площадка'),('усадьба','усадьба'),('починок','починок'),('будка','будка'),('хутор','хутор'),('село','село'),('пгт','пгт'),('г.','город'),('дер.','деревня'),('п.','посёлок'),('с.','село'),('д.','деревня')]
def splitnp(n):
 for prefix,t in T:
  if n.casefold().startswith(prefix.casefold()+' '):return t,n[len(prefix):].strip()
 return None

def val(x):
 if isinstance(x,(int,float)):return int(x)
 x=clean(x)
 return int(x.replace(' ',''))if re.fullmatch(r'\d[\d ]*',x)else None
rows=[];controls=[];unresolved=[];sourceheaders=[]
for region,file in [('пермский','perm_2010_original_archived.xls'),('приморский','prim_2010_original_archived.mht')]:
 p=E/file;records=[]
 if p.suffix=='.xls':
  b=xlrd.open_workbook(p,formatting_info=True);s=b.sheet_by_index(0)
  for i in range(s.nrows):
   vv=s.row_values(i);records.append((i+1,vv,b.xf_list[s.cell(i,0).xf_index].alignment.indent_level,'01-04'))
 else:
  m=email.message_from_bytes(p.read_bytes())
  for part in m.walk():
   if part.get_content_type()=='text/html'and 'sheet001' in part.get('Content-Location',''):
    soup=BeautifulSoup(part.get_payload(decode=True).decode(part.get_content_charset()or'windows-1251'),'html.parser');tab=soup.find('table')
    for i,tr in enumerate(tab.find_all('tr')):
     cells=tr.find_all(['td','th'],recursive=False);vv=[c.get_text(' ',strip=True)for c in cells];records.append((i+1,vv,None,'MIMEpart:sheet001.htm:table1'))
 parent_NP_control_rows=set()
 if p.suffix=='.xls':
  for j,(rr,vv,ii,ss) in enumerate(records[:-2]):
   nxt=records[j+1]; child=records[j+2]
   if splitnp(clean(vv[0])) and clean(nxt[1][0])=='Сельское население' and nxt[2]>ii and child[2]>nxt[2] and splitnp(clean(child[1][0])):
    parent_NP_control_rows.add(rr)
 county='';countyrow=None;muni='';munirow=None
 for rn,vv,indent,sheet in records:
  if not vv:continue
  n=clean(vv[0]);pval=val(vv[1])if len(vv)>1 else None;male=val(vv[2])if len(vv)>2 else None;female=val(vv[3])if len(vv)>3 else None;np=splitnp(n)
  if rn<8:sourceheaders.append(dict(region=region,source_file=file,row=rn,caption=n,raw_cells=vv))
  # Only explicitly printed proper municipal county/GO headers update district context. City wards remain controls.
  if re.search(r'\bмуниципальный район\b',n,re.I)or (re.search(r'\bгородской округ\b',n,re.I)and not re.search(r'городские округа',n,re.I)):
   county=n;countyrow=rn;muni='';munirow=None
  elif re.search(r'\b(?:городское|сельское) поселение\b',n,re.I):muni=n;munirow=rn
  if rn in parent_NP_control_rows:
   controls.append(dict(region=region,source_file=file,row=rn,caption=n,population=pval,kind='intersettlement_administrative_parent_repeated_by_deeper_literal_NP',style_indent=indent));continue
  if re.search(r'Межселенные территории',n,re.I):muni='';munirow=None
  if np:
   t,name=np;rows.append(dict(primary_source_record_id=('PERM2010'if region=='пермский'else'PRIM2010')+':'+sheet+':row'+str(rn),census_year=2010,region=region,settlement_type=t,settlement_name=name,type_norm=norm(t),name_norm=norm(name),raw_NP_caption=n,official_population=pval,official_men=male,official_women=female,raw_population_cell=vv[1]if len(vv)>1 else '',raw_men_cell=vv[2]if len(vv)>2 else '',raw_women_cell=vv[3]if len(vv)>3 else '',raw_count_cells_json=json.dumps(vv[1:4],ensure_ascii=False),population_cell_numeric=pval is not None,count_sex_consistency='PASS'if pval is not None and male is not None and female is not None and pval==male+female else 'one_or_more_literal_unknown'if None in [pval,male,female]else 'FAIL',official_county=county,official_county_header_row=countyrow,official_municipality=muni,official_municipality_header_row=munirow,source_path=str(p.resolve()),source_sha256=sha(p),source_sheet=sheet,source_row=rn,source_population_column_zero_based=1,source_style_indent=indent,source_grade='direct_official_primary_2010_NP_publication',census_reference_date='2010-10-14',publication_date_unknown=True,raw_dash_preserved_as_NULL=pval is None))
  else:
   kind='aggregate_control'if any(q in n.casefold()for q in ['населени','поселени','район','округ','территори'])else'unknown_or_header';controls.append(dict(region=region,source_file=file,row=rn,caption=n,population=pval,kind=kind,style_indent=indent))
   if pval is not None and rn>8 and kind=='unknown_or_header':unresolved.append(dict(region=region,row=rn,caption=n,population=pval,raw=vv))
d=pd.DataFrame(rows);assert not (d.count_sex_consistency=='FAIL').any();d.to_csv(E/'parsed_primary_2010_NP_inventory.csv.gz',index=False);pd.DataFrame(controls).to_csv(E/'parsed_source_aggregate_controls.csv.gz',index=False);(E/'source_header_and_unclassified_numeric_readback.json').write_text(json.dumps({'header_rows':sourceheaders,'unclassified_numeric_rows':unresolved},ensure_ascii=False,indent=2));r={'status':'literal_hierarchical_primaryNPinventory_not_applied','regions':{},'input_pins':{file:sha(E/file)for file in ['perm_2010_original_archived.xls','prim_2010_original_archived.mht']},'unclassified_numeric_rows':len(unresolved),'NULL_dash_not_zero':True,'aggregate_controls_not_NP':True}
for reg,g in d.groupby('region'):
 r['regions'][reg]={'NP_rows':len(g),'numeric_NP_rows':int(g.official_population.notna().sum()),'NULL_NP_rows':int(g.official_population.isna().sum()),'numeric_NP_population_sum':int(g.official_population.sum()),'official_region_population':2635276 if reg=='пермский'else 1956497,'numeric_NP_sum_minus_official_region':int(g.official_population.sum())-(2635276 if reg=='пермский'else 1956497),'full_typed_name_competition_keys':int(g.groupby(['type_norm','name_norm']).size().gt(1).sum())}
r['output_pins']={p.name:sha(p)for p in [E/'parsed_primary_2010_NP_inventory.csv.gz',E/'parsed_source_aggregate_controls.csv.gz',E/'source_header_and_unclassified_numeric_readback.json']};(E/'primary_parse_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))

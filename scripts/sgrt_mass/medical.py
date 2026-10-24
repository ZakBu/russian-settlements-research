#!/usr/bin/env python3
"""Parse every saved regional Grok medical source without treating legal addresses as sites.

This reads the pinned Git text extraction. Except where separately verified,
primary hashes are inherited from its download log, not a claim of fresh download.
Variable spreadsheet headers are detected by their literal labels. PDF/unsupported
sources remain explicit held input instead of fabricated medical objects.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, subprocess, sys, urllib.request, zipfile
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

COMMIT='c5116d1360d5c97e71aeec52a9b8e182dbcfb8ea'
PREFIX='sgrt/sources/medicine/'

def clean(value):
 return re.sub(r'\s+',' ',str('' if value is None else value).replace('_x000D_',' ')).strip()
def norm(value):return clean(value).casefold().replace('ё','е')
def short_hash(value):return hashlib.sha256(value.encode()).hexdigest()[:24]

def materialize(repo, dest, commit=COMMIT):
 dest.mkdir(parents=True,exist_ok=True)
 if subprocess.run(['git','cat-file','-e',commit+'^{commit}'],cwd=repo,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
  subprocess.run(['git','fetch','--no-tags','origin',commit],cwd=repo,check=True)
 paths=subprocess.check_output(['git','ls-tree','-rz','--name-only',commit],cwd=repo).decode().split('\0')
 for p in paths:
  if p.startswith(PREFIX) and ('/tables/' in p or p.endswith(('registry_inventory.csv','download_log.csv'))):
   out=dest/Path(p).name
   data=subprocess.check_output(['git','show',commit+':'+p],cwd=repo)
   if not out.exists() or out.read_bytes()!=data:out.write_bytes(data)

SUPPLEMENTAL_SOURCES=[dict(region='Вологодская',url='https://new.oms35.ru/upload/Reestr/MO/Reestr_MO_2026_1.xlsx',filename='supplement_vologda2026.xlsx',sha256='8509c4ba7a1e8882d4bdcb4281994268764448dcbe4546243fdc01a140fe8122',sheet='актуализированный на 02.09.2026',expected_data_rows=1967),dict(region='Удмуртия',url='https://www.tfoms18.ru/media/files/trmo2026.zip',filename='supplement_udmurtia2026.xlsx',sha256='595f3b2879758145b51c7c2027f97da4d3ac1cf77f4b22ab6b511548abfb61cb',archive_filename='supplement_udmurtia2026.zip',archive_sha256='e51c3359a47d590d944e9db03b8ae20800bc9501a96f33ccc5241a19760a727e',archive_member='ТРМО 01-10-2026 07-35.xlsx',sheet='report',expected_data_rows=2476)]

def prepare_supplements(input_dir):
 import openpyxl
 logs=[]
 for source in SUPPLEMENTAL_SOURCES:
  workbook=input_dir/source['filename']
  if source.get('archive_filename'):
   archive=input_dir/source['archive_filename']
   if not archive.exists():
    with urllib.request.urlopen(source['url'],timeout=60) as response:archive.write_bytes(response.read())
   if hashlib.sha256(archive.read_bytes()).hexdigest()!=source['archive_sha256']:raise ValueError('Supplemental archive changed')
   if not workbook.exists():
    with zipfile.ZipFile(archive) as z:workbook.write_bytes(z.read(source['archive_member']))
  elif not workbook.exists():
   with urllib.request.urlopen(source['url'],timeout=60) as response:workbook.write_bytes(response.read())
  if hashlib.sha256(workbook.read_bytes()).hexdigest()!=source['sha256']:
   raise ValueError('Supplemental primary workbook changed; reinspect '+source['url'])
  book=openpyxl.load_workbook(workbook,read_only=True,data_only=True)
  sheet=book[source['sheet']];name=Path(source['filename']).stem+'.tsv'
  row_map={};nonempty=0;data=[]
  for excelrow,row in enumerate(sheet.iter_rows(values_only=True),1):
   values=[clean(v) for v in row]
   if not any(values):continue
   nonempty+=1;row_map[str(nonempty)]=excelrow;data.append([sheet.title]+values)
  book.close()
  with (input_dir/name).open('w',encoding='utf-8',newline='') as h:csv.writer(h,delimiter='\t',lineterminator='\n').writerows(data)
  mapname=Path(source['filename']).stem+'_excelrows.json'
  (input_dir/mapname).write_text(json.dumps({name:row_map},ensure_ascii=False)+'\n')
  logs.append(dict(region=source['region'],url=source['url'],result='saved',sha256=source.get('archive_sha256',source['sha256']),workbook_sha256=source['sha256'],files=name,primary_workbook_supplement=True,excel_row_map_filename=mapname,selected_sheet=source['sheet'],expected_data_rows=source['expected_data_rows']))
 (input_dir/'supplemental_sources.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2)+'\n')
 return logs


def field_for(label):
 s=norm(label)
 if s in ['инн','инн/кпп']:return 'inn'
 if s.startswith('полное наименование') and 'учредител' not in s and ('медицинской организации' in s or s=='полное наименование'):return 'organization_name'
 if s.startswith(('сокращенное наименование','краткое наименование')) and 'учредител' not in s:return 'organization_short_name'
 if s.startswith('адрес мо в пределах') or s.startswith('место нахождения и адрес медицинской организации'):return 'legal_address'
 if 'адрес' in s and ('оказания медицинской помощи' in s or 'оказания медицинских услуг' in s) and 'уникальн' not in s:return 'activity_address'
 if s.startswith('место нахождения и адрес филиала'):return 'branch_address'
 if 'уникальн' in s and 'адрес' in s and 'оказания' in s:return 'activity_address_id'
 if s.startswith('наименование структурного подразделения'):return 'subdivision_name'
 if s.startswith('oid') and 'структурного' in s:return 'subdivision_oid'
 if s.startswith('oid') and 'фрмо' in s:return 'organization_oid'
 if s.startswith('код структурного подразделения') and 'едином реестре' not in s:return 'subdivision_code'
 if s.startswith('код структурного подразделения') and 'едином реестре' in s:return 'subdivision_registry_code'
 if s.startswith(('вид медицинской помощи','виды медицинской помощи')):return 'care_type_literal'
 if s.startswith(('условия медицинской помощи','условия оказания медицинской')):return 'care_conditions_literal'
 if s.startswith(('профиль медицинской помощи','профили медицинской помощи','профили оказываемой')):return 'care_profile_literal'
 if s.startswith('вид медицинской организации'):return 'organization_type_literal'
 if s.startswith('дата включения'):return 'inclusion_date_literal'
 if s.startswith('дата исключения'):return 'exclusion_date_literal'
 if s.startswith('причина исключения'):return 'exclusion_reason_literal'
 if s.startswith('сведения о структурных подразделениях медицинской организации'):return 'subdivision_description_literal'
 return None

FIELDS=['organization_name','organization_short_name','inn','organization_oid','legal_address','activity_address','branch_address','activity_address_id','subdivision_name','subdivision_oid','subdivision_code','subdivision_registry_code','care_type_literal','care_conditions_literal','care_profile_literal','organization_type_literal','inclusion_date_literal','exclusion_date_literal','exclusion_reason_literal','subdivision_description_literal']
ORG_FIELDS=['organization_name','organization_short_name','inn','organization_oid','legal_address','organization_type_literal']

def primary_scope_flags(row):
 name=norm(row.get('subdivision_name',''))
 profile=norm(row.get('care_profile_literal',''))
 scope_name=re.split(r'(?<!\w)(?:ул\.?|улица|пер\.?|переулок)(?=\s|,)',name,maxsplit=1)[0]
 school_scope=bool(re.search(r'образовательн.{0,40}(?:организац|учрежд|школ)|дошкольн.{0,30}(?:отделен|кабинет|групп)|(?:школьн|дошкольн).{0,20}мед|(?:медицинск.{0,15}кабинет|медкабинет|медпункт|отделение|медицинск.{0,20}пункт|пункт медицинск).{0,120}(?:школ|образовательн|дошкольн|детск.{0,8}сад)|\b(?:мбоу|моу|сош|мбдоу|мдоу|доу)\b|помощ.{0,70}несовершеннолетн',scope_name))
 restricted=school_scope or bool(re.search(r'здравпункт|предрейс|послерейс|исправительн|следственн.{0,10}изолятор',name))
 pediatric=('педиатрии' in profile and not re.search(r'лечебному делу|\bтерапии\b|общей врачебной практике|общей практике',profile))
 # Some register profiles aggregate an entire license. A narrow named unit
 # does not become broad primary care merely because that list says therapy.
 narrow=bool(re.search(r'стомат|зубн|лаборатор|ультразвук|\bузи\b|рентген|физиотерап|массаж|прививоч|процедурн|скорой|неотложн|реанимац|стерилизац|дневной стационар|круглосуточный стационар|приемн.{0,5}отделен|кабинет функциональн|отделен.{0,20}диагност|отделен.{0,20}профилактик',name))
 reasons=[]
 if restricted:reasons.append('restricted_or_workplace_access_signal')
 if school_scope:reasons.append('school_or_preschool_medical_service_restricted_contingent')
 if pediatric:reasons.append('pediatric_only_profile_no_adult_general_offer')
 if narrow:reasons.append('narrow_unit_name_conflicts_with_broad_primary_interpretation')
 return dict(school_or_preschool_medical_scope_signal=school_scope,restricted_access_signal=restricted,pediatric_only_signal=pediatric,narrow_unit_name_ambiguity_signal=narrow,public_primary_eligibility_reason='|'.join(reasons) if reasons else 'no_exclusion_signal_not_proof_of_unrestricted_access')


def classify(row):
 n=norm(row['subdivision_name']); t=norm(row['care_type_literal']); p=norm(row['care_profile_literal']);c=norm(row['care_conditions_literal'])
 # A laboratory or dental-only 'primary' unit does not establish broad primary care.
 general=bool(re.search(r'лечебному делу|\bтерапии\b|общей врачебной практике|общей практике|\bпедиатрии\b',p))
 fap=bool(re.search(r'\bфап\b|фельдшерско.?акушерск|фельдшерский пункт|фельдшерско.?здрав',n))
 ambulatory=('амбулаторно' in c)
 physician=('первичная врачебная медико-санитарная помощь' in t and ambulatory and general)
 basic=fap or physician or (general and ambulatory and 'первичная доврачебная медико-санитарная помощь' in t)
 inpatient=bool(re.search(r'(^|[,;]\s*)стационарно\b',c))
 specialized=bool(re.search(r'(^|[,;]\s*)специализированная медицинская помощь',t)) or 'высокотехнологичная' in t
 day='в дневном стационаре' in c
 result=[]
 if basic:result.append(('medical_basic_primary','named_FAP' if fap else 'primary_care_literal_plus_general_profile_and_ambulatory'))
 if physician:result.append(('medical_physician_primary','primary_physician_care_literal_plus_general_profile_and_ambulatory'))
 if inpatient:result.append(('medical_inpatient','explicit_stationary_condition_not_day_hospital'))
 if specialized:result.append(('medical_specialized','explicit_specialized_or_hightechnology_care_not_primary_specialized_only'))
 if day:result.append(('medical_day_hospital','explicit_day_hospital_condition'))
 return result

def self_test_classification():
 def row(name,care='первичная врачебная медико-санитарная помощь',conditions='Амбулаторно',profile='терапии'):
  return dict(subdivision_name=name,care_type_literal=care,care_conditions_literal=conditions,care_profile_literal=profile)
 assert 'medical_basic_primary' in dict(classify(row('ФАП',care='первичная доврачебная медико-санитарная помощь',profile='лечебному делу')))
 assert 'medical_physician_primary' not in dict(classify(row('ФАП',care='первичная доврачебная медико-санитарная помощь')))
 assert 'medical_inpatient' not in dict(classify(row('Дневной стационар',conditions='В дневном стационаре')))
 assert 'medical_specialized' not in dict(classify(row('Стоматолог',care='первичная специализированная медико-санитарная помощь',profile='стоматологии терапевтической')))
 for name in ['Клинико-диагностическая лаборатория','Стоматологический кабинет','Кабинет УЗИ','Кинешемская станция скорой помощи']:
  assert primary_scope_flags(row(name))['narrow_unit_name_ambiguity_signal']
 assert not primary_scope_flags(row('Кабинет врача общей практики'))['narrow_unit_name_ambiguity_signal']
 for name in ['Медицинский кабинет средней образовательной школы','Медпункт МБОУ СОШ','Отделение организации медицинской помощи несовершеннолетним в образовательных организациях','Медицинский пункт общеобразовательной школы']:
  assert primary_scope_flags(row(name))['school_or_preschool_medical_scope_signal'],name
 for name in ['Фельдшерско-акушерский пункт "Школьненский"','Фельдшерско-акушерский пункт (дНижние Нарыкары, улШкольная, дом 14-а)']:
  assert not primary_scope_flags(row(name))['school_or_preschool_medical_scope_signal'],name
 return 15


def parse_sources(input_dir, output, commit=COMMIT):
 output.mkdir(parents=True,exist_ok=True)
 logs=list(csv.DictReader((input_dir/'download_log.csv').open(encoding='utf-8')))
 records=[];coverage=[];held=[];sourcefiles=[]
 supplement_log=input_dir/'supplemental_sources.json'
 if supplement_log.exists():logs+=json.loads(supplement_log.read_text())
 for source_no,log in enumerate(logs):
  if log['result']!='saved':
   coverage.append(dict(source_region_literal=log['region'],source_url=log['url'],result=log['result'],parsed_rows=0,held_rows=0,reason='not_downloaded_as_table',source_id='MEDGROK:'+str(source_no)))
   continue
  sid='MEDGROK:'+short_hash(log['url'])
  state={};lastorg={};sheet_no=Counter();sourcecount=Counter();pdfcount=0
  excelrowmap=json.loads((input_dir/log['excel_row_map_filename']).read_text()) if log.get('excel_row_map_filename') else {}
  for filename in log['files'].split():
   path=input_dir/filename
   if not path.exists():raise FileNotFoundError(path)
   sourcefiles.append(dict(source_id=sid,path=filename,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
   for partrow,cells in enumerate(csv.reader(path.open(encoding='utf-8'),delimiter='\t'),1):
    sourcecount['input_rows']+=1
    if len(cells)<2:
     pdfcount+=1
     # Preserve unsupported PDF text at source file/row; no loose address guesses.
     continue
    sheet=cells[0];row=[clean(x) for x in cells[1:]];sheet_no[sheet]+=1
    header_candidate=any(v.casefold() in ['инн','инн/кпп'] or v.startswith('Сведения об адресах оказания') for v in row)
    detected={field_for(v):i for i,v in enumerate(row) if field_for(v)} if header_candidate else {}
    # Literal header, not an organization whose name happens to contain a keyword.
    isheader=(len(detected)>=3 and ('inn' in detected or 'activity_address' in detected or 'organization_name' in detected))
    if isheader:
     previous=state.get(sheet,{})
     previous.update(detected);state[sheet]=previous;sourcecount['header_rows']+=1;continue
    mapping=state.get(sheet,{})
    if not mapping and log['region']=='Тверская' and len(row)>=10 and re.fullmatch(r'[0-9a-f-]{36}',row[2],re.I) and re.fullmatch(r'\d{12,}',row[3]) and row[6].startswith('1.2.643.'):
     mapping={'organization_short_name':0,'activity_address':1,'activity_address_id':2,'subdivision_code':3,'subdivision_registry_code':4,'subdivision_name':5,'subdivision_oid':6,'care_type_literal':7,'care_conditions_literal':8,'care_profile_literal':9};state[sheet]=mapping
    if not mapping:
     sourcecount['no_header_rows']+=1;continue
    values={f:row[i] if i<len(row) else '' for f,i in mapping.items()}
    if all(re.fullmatch(r'\d+(?:\.0)?',v) for v in row if v):
     sourcecount['numeric_column_header_rows']+=1;continue
    validinn=bool(re.match(r'^\d{10}(?:\D|$)|^\d{12}(?:\D|$)',values.get('inn','')))
    has_activity=bool(values.get('activity_address') or values.get('branch_address'))
    has_subdivision=bool(values.get('subdivision_name') or values.get('subdivision_oid'))
    if not validinn and not (has_activity and (has_subdivision or values.get('care_type_literal') or values.get('organization_name'))) and not (has_subdivision and values.get('care_type_literal')):
     sourcecount['other_metadata_or_unparsed_rows']+=1;continue
    previous=lastorg.get(sheet,{})
    if values.get('organization_name') and values.get('organization_name')!=previous.get('organization_name'):previous={}
    if validinn:
     inn=re.match(r'\d+',values['inn']).group()
     if previous.get('inn')!=inn:previous={}
     values['inn']=inn
    for f in ORG_FIELDS:
     if values.get(f):previous[f]=values[f]
     elif f in previous:values[f]=previous[f]
    lastorg[sheet]=previous
    result={f:values.get(f,'') for f in FIELDS}
    if not result['activity_address'] and result['branch_address']:
     result['activity_address']=result['branch_address']; address_basis='explicit_branch_address_not_legal_address'
    elif result['activity_address']:address_basis='explicit_address_of_care'
    else:address_basis='no_activity_address_legal_not_substituted'
    # A sheet explicitly labelled2023 cannot be silently relabelled2026.
    years=re.findall(r'20(?:0\d|1\d|2\d|3\d)',sheet)
    sourceyear=int(years[0]) if len(set(years))==1 else 2026
    obj='medrow:'+short_hash('|'.join([sid,filename,str(partrow)]))
    result.update(object_id=obj,source_id=sid,source_region_literal=log['region'],source_url=log['url'],primary_sha256_in_download_log=log.get('sha256',''),primary_workbook_sha256=log.get('workbook_sha256',''),primary_freshly_downloaded=bool(log.get('primary_workbook_supplement')),source_commit=None if log.get('primary_workbook_supplement') else commit,source_part=filename,source_row=partrow,source_sheet=sheet,source_nonempty_sheet_row=sheet_no[sheet],source_excel_row=excelrowmap.get(filename,{}).get(str(partrow)),source_year=sourceyear,source_year_basis='explicit_sheet_year' if years else 'registry_download_inventory_2026',source_year_conflict_with_inventory=sourceyear!=2026,address_basis=address_basis,registered_exclusion_present=bool(result['exclusion_date_literal']),inn_syntax_valid=validinn,capacity_total=None,actual_operational_status_checked=False,observed_flow=False)
    location=result['activity_address_id'] or norm(result['activity_address'])
    result['reported_location_id']='medloc:'+short_hash(location) if location else None
    result['unit_id']='medunit:'+short_hash('|'.join([result['subdivision_oid'] or result['subdivision_code'] or result['subdivision_name'],result['inn'],location]))
    classes=classify(result)
    result.update(primary_scope_flags(result))
    result['service_codes']='|'.join(c for c,b in classes);result['service_bases_json']=json.dumps(dict(classes),ensure_ascii=False)
    records.append(result);sourcecount['parsed_rows']+=1
    if not result['activity_address']:sourcecount['no_activity_address']+=1
  coverage.append(dict(source_region_literal=log['region'],source_url=log['url'],source_id=sid,result='parsed_structured' if sourcecount['parsed_rows'] else 'held_pdf_or_unsupported_header',parsed_rows=sourcecount['parsed_rows'],held_rows=pdfcount+sourcecount['no_header_rows']+sourcecount['other_metadata_or_unparsed_rows'],reason='PDF_text_not_address_site_records' if pdfcount else '',**{k:v for k,v in sourcecount.items() if k!='parsed_rows'}))
  if log.get('expected_data_rows') and sourcecount['parsed_rows']!=int(log['expected_data_rows']):raise ValueError('Supplemental rows not fully parsed: '+log['region'])
  if pdfcount:held.append(dict(source_id=sid,source_region_literal=log['region'],source_url=log['url'],reason='PDF_text_requires_separate_layout_parser_not_recast_as_objects',input_text_lines=pdfcount))
 sites=pd.DataFrame(records)
 sites.to_parquet(output/'sites_raw.parquet',index=False);sites.to_csv(output/'sites_raw.csv.gz',index=False)
 pd.DataFrame(coverage).to_csv(output/'source_coverage.csv',index=False)
 pd.DataFrame(held).to_csv(output/'held_sources.csv',index=False)
 (output/'input_files.json').write_text(json.dumps(sourcefiles,ensure_ascii=False,indent=2)+'\n')
 return sites,pd.DataFrame(coverage)

def coverage_by_settlement(matched,supply,reference,output):
 r=reference[reference.ordinary_spatial_2021].copy()
 if r.source_record_id.duplicated().any():raise ValueError('Repeated settlement denominator')
 def band(v):
  if pd.isna(v):return 'unknown'
  if v==0:return '0'
  if v<100:return '1-99'
  if v<1000:return '100-999'
  if v<10000:return '1000-9999'
  return '10000+'
 r['population_band']=r.population_2021.map(band)
 r['with_any_registry_address']=r.source_record_id.isin(matched.source_record_id.dropna())
 service_cols=[]
 for code in ['medical_basic_primary','medical_physician_primary','medical_inpatient','medical_specialized','medical_day_hospital']:
  col='with_'+code;r[col]=r.source_record_id.isin(supply.loc[supply.service_code.eq(code),'source_record_id']);service_cols.append(col)
 r['population_known']=r.population_2021.notna();r['inhabited_record']=r.population_2021.gt(0)
 agg={'source_record_id':'size','credit_2021':'sum','population_known':'sum','inhabited_record':'sum','with_any_registry_address':'sum',**{c:'sum' for c in service_cols}}
 table=r.groupby(['region','population_band'],dropna=False).agg(agg).rename(columns={'source_record_id':'ordinary_spatial_2021_records','credit_2021':'credited_2021_records'}).reset_index()
 for col in ['with_any_registry_address']+service_cols:table[col+'_fraction']=table[col]/table.ordinary_spatial_2021_records
 table['denominator_scope']='accepted_ordinary_spatial_2021_records_including_zero_population; not_accuracy'
 table.to_csv(output/'settlement_coverage_region_size.csv',index=False)
 return table

def attach_and_supply(sites, population, output):
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
 from scripts.sgrt_mass.match import build_reference,match_addresses
 reference=build_reference(population)
 matched=match_addresses(sites,reference,address_col='activity_address',region_col='source_region_literal')
 # Keep explicit non-geographic/dated exclusions out of the current routing offer.
 matched.to_parquet(output/'sites_matched_or_held.parquet',index=False)
 good=matched[matched.source_record_id.notna() & matched.activity_address.ne('')].copy()
 good.to_parquet(output/'sites_matched.parquet',index=False)
 matched[matched.source_record_id.isna()].to_parquet(output/'sites_held.parquet',index=False)
 matched[matched.source_record_id.isna()].to_csv(output/'sites_held.csv.gz',index=False)
 evidence=[]
 for row in good.itertuples(index=False):
  if row.registered_exclusion_present or row.source_year_conflict_with_inventory:continue
  for code in row.service_codes.split('|'):
   if code and not (code in ['medical_basic_primary','medical_physician_primary'] and (row.restricted_access_signal or row.pediatric_only_signal or row.narrow_unit_name_ambiguity_signal)):evidence.append(dict(object_id=row.object_id,unit_id=row.unit_id,reported_location_id=row.reported_location_id,source_record_id=row.source_record_id,service_code=code,source_id=row.source_id,source_year=row.source_year,service_basis=json.loads(row.service_bases_json)[code],source_part=row.source_part,source_row=row.source_row))
 ev=pd.DataFrame(evidence)
 ev.to_parquet(output/'service_evidence.parquet',index=False)
 supply=[]
 for (sid,code),g in ev.groupby(['source_record_id','service_code'],sort=True):
  supply.append(dict(provider_id='medical:'+code+':'+sid,source_record_id=sid,service_code=code,supply_status='observed',source_id='|'.join(sorted(set(g.source_id))),source_year=2026,service_basis='distinct_settlement_service_presence_from_literal_registry_evidence',source_records=len(g),distinct_registered_units=g.unit_id.nunique(),distinct_reported_address_keys=g.reported_location_id.nunique(),capacity_total=None,observed_flow=False))
 supply=pd.DataFrame(supply);supply.to_parquet(output/'supply.parquet',index=False);supply.to_csv(output/'supply.csv',index=False)
 joined=matched.merge(reference.loc[reference.source_record_id.notna(),['source_record_id','region','population_2021']],on='source_record_id',how='left',validate='many_to_one')
 def size(v):
  if pd.isna(v):return 'population_unknown_or_unmatched'
  if v==0:return '0'
  if v<100:return '1-99'
  if v<1000:return '100-999'
  if v<10000:return '1000-9999'
  return '10000+'
 joined['population_band']=joined.population_2021.map(size)
 joined.groupby(['source_region_literal','match_status','population_band'],dropna=False).size().rename('registry_rows').reset_index().to_csv(output/'match_coverage_region_size.csv',index=False)
 coverage_by_settlement(matched,supply,reference,output)
 return matched,supply

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path('.'));p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--materialize',action='store_true');p.add_argument('--population',type=Path);p.add_argument('--skip-match',action='store_true');a=p.parse_args()
 self_test_classification()
 if a.materialize:materialize(a.repo,a.input)
 prepare_supplements(a.input)
 sites,coverage=parse_sources(a.input,a.output)
 summary={'source_commit':COMMIT,'input_tables':len(list(a.input.glob('*.tsv'))),'saved_source_rows':int(coverage.result.isin(['parsed_structured','held_pdf_or_unsupported_header']).sum()),'parsed_region_sources':int(coverage.parsed_rows.gt(0).sum()),'normalized_rows':len(sites),'rows_with_activity_address':int(sites.activity_address.ne('').sum()),'registered_excluded_rows':int(sites.registered_exclusion_present.sum()),'rows_with_classified_service':int(sites.service_codes.ne('').sum()),'not_observed_patient_flows':True,'not_national_complete_registry':True}
 if not a.skip_match:
  if not a.population:raise ValueError('--population required unless --skip-match')
  matched,supply=attach_and_supply(sites,a.population,a.output);summary.update(matched_rows=int(matched.source_record_id.notna().sum()),matched_settlements=int(matched.source_record_id.nunique()),settlement_service_offers=len(supply))
 (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

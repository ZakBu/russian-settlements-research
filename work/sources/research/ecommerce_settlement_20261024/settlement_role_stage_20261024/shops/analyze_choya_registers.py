"""Physical shop rows in dated official Choya dislocations, with explicit exclusions.
Run with PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 this_file.py.
Raw DOCX/XLS source rows and official totals are retained; no missing count imputation.
"""
from pathlib import Path
from collections import Counter
import json,re,hashlib,csv,unicodedata
import pandas as pd
import xlrd
from docx import Document

OUT=Path(__file__).resolve().parent
RAW=OUT/'raw'
BASE=OUT.parent.parent
KEY='source_record_id_2021'
d=pd.read_parquet(BASE/'national/national_target_source2021.parquet')
npbase=d.loc[d.region_2021.eq('алтай') & d.district_2021.str.contains('Чой',na=False)].copy()
assert len(npbase)==21
name_lookup={}
for _,r in npbase.iterrows():
 name_lookup.setdefault(str(r.name_2021).lower().replace('ё','е'),[]).append(r)


def clean(x):
 return re.sub(r'\s+',' ',str(x if x is not None else '')).strip()

def norm(x):
 x=unicodedata.normalize('NFKC',clean(x)).lower().replace('ё','е')
 return ' '.join(re.sub(r'[^\w\s-]',' ',x).split())

def parse_number(x):
 try:
  n=float(str(x).strip().rstrip('.'))
  return int(n) if n==int(n) else None
 except (ValueError,TypeError):return None

def get_settlement(address):
 # Match an explicit NP prefix; municipality name/owner/legal address are never used.
 text=clean(address).lower().replace('ё','е')
 candidates=[]
 for n,rr in name_lookup.items():
  rx=r'(?:^|[\s,;])(?:село|с\.?|поселок|п\.?|деревня|д\.?)[ ]*'+re.escape(n)+r'(?=$|[^\w-])'
  if re.search(rx,text):candidates+=rr
 unique={r[KEY]:r for r in candidates}
 if len(unique)!=1:return None,'unresolved_or_ambiguous_explicit_settlement'
 r=next(iter(unique.values()))
 return r,'exact_explicit_settlement_in_fixed_region_district'

rows_out=[];excluded=[];operator_rows=[];totals=[];rawtrade={};audit=[]
for year in range(2019,2027):
 if year<=2020:
  file=f'choya_{year}_0.docx'
  doc=Document(RAW/file)
  table=doc.tables[0]
  rows=[[c.text for c in r.cells] for r in table.rows]
  addr_col=7;area_col=9
  sheet='table1'
 else:
  file=f'choya_{year}_0.xls'
  wb=xlrd.open_workbook(RAW/file)
  ss=[s for s in wb.sheets() if s.name.lower().strip()=='торговый реестр']
  assert len(ss)==1
  sh=ss[0];sheet=sh.name
  rows=[sh.row_values(i) for i in range(sh.nrows)]
  addr_col=4;area_col=7
 rawtrade[str(year)]=rows
 title=' '.join(clean(x) for r in rows[:4] for x in r)
 dates=re.findall(r'01\.01\.20\d\d',title)
 assert dates and set(dates)=={f'01.01.{year}'},(year,dates)
 major='unknown';category=None;prevno=None
 expected={};parsed=Counter();included=Counter()
 for i,r in enumerate(rows,1):
  rr=[clean(x) for x in r]
  uniq=list(dict.fromkeys(v for v in rr if v))
  text=' '.join(uniq)
  t=norm(text)
  first=norm(rr[0])
  if first.startswith('предприятия торговли'):
   major='shops';continue
  if first.startswith('предприятия мелкой'):
   major='small_nonstationary';category=None;continue
  if first.startswith('предприятия общественного') or first.startswith('рестораны кафе'):
   major='catering';category=None;continue
  if first.startswith('предприятия хлебопечения'):
   major='baking';category=None;continue
  if first.startswith('аптеки'):
   major='pharmacy';category=None;continue
  if first.startswith('автозаправоч'):
   major='fuel';category=None;continue
  if major=='shops':
   if first.startswith('непродовольственные'):
    category='nonfood';prevno=None;continue
   if first.startswith('продоволь') and (not rr[1] or norm(rr[1])==first):
    category='food';prevno=None;continue
   if first.startswith('смешанные'):
    category='mixed';prevno=None;continue
  if 'итого' in first or first.startswith('итоги'):
   m=re.search(r'(?:итого|итоги).*?\b(\d+)\b',clean(rr[0]),re.I)
   # Some report summary labels reside in the second DOCX grid cell.
   if not m:m=re.search(r'(?:итого|итоги).*?\b(\d+)\b',text,re.I)
   if m:
    overall=any(w in first for w in ['магазинов','предприятий торговли'])
    totals.append({'year':year,'observation_date':f'{year}-01-01','major':major,
     'category':'overall' if overall else category,'reported_count':int(m.group(1)),
     'source_file':file,'source_sheet':sheet,'source_row':i,'text_raw':text})
    if major=='shops' and not overall and category:expected[category]=int(m.group(1))
   continue
  if len(r)<=addr_col:continue
  address=rr[addr_col]
  no=parse_number(r[0])
  if year<=2020:
   names=[v for v in rr[1:5] if v and parse_number(v) is None]
   name=names[0] if names else ''
  else:name=rr[1]
  if not name or not address or 'местонахожд' in norm(address) or 'место нахождения' in norm(address):continue
  if no is None:
   if major=='shops' and category:
    operator_rows.append({'year':year,'category':category,'preceding_number':prevno,
     'name_raw':name,'address_raw':address,'source_file':file,'source_row':i,
     'interpretation':'unnumbered_operator_or_detail_row_not_counted_as_additional_shop'})
   continue
  prevno=no
  parsed[category if major=='shops' else major]+=1
  settlement,status=get_settlement(address)
  marker=bool(re.search(r'озон|ozon|wildber|вайлд|вилд|\bwb\b|выдач|маркетплейс',text,re.I))
  gas=bool(re.search(r'\bазс\b|автозаправ',name,re.I))
  nto=bool(re.search(r'киоск|ларек|ларёк|автолав|передвиж|палатк',name,re.I))
  classification=('pickup_marker_requires_combination_review' if marker else
                  'fuel_related_shop_excluded' if gas else
                  'nonstationary_named_object_excluded' if nto else
                  'ordinary_shop_numbered_entry' if major=='shops' and category else
                  'other_function_excluded')
  record={'observation_date':f'{year}-01-01','year':year,'category':category,
   'source_number':no,'name_raw':name,'address_raw':address,
   'area_raw':str(r[area_col]),'major_section':major,'classification':classification,
   'marketplace_marker':marker,'pickup_combination_status':'explicit_marker_requires_review' if marker else 'no_explicit_marker_combination_unknown',
   'postal_shop_name_flag':bool(re.search(r'почтамп|почта|уфпс|почтов',name,re.I)),
   'settlement_link_status':status,
   KEY:None if settlement is None else settlement[KEY],
   'name_2021':None if settlement is None else settlement.name_2021,
   'is_choya_centre':None if settlement is None else settlement.name_2021=='Чоя',
   'source_file':file,'source_sheet':sheet,'source_row':i}
  if classification=='ordinary_shop_numbered_entry':
   rows_out.append(record);included[category]+=1
  else:excluded.append(record)
 audit.append({'year':year,'internal_date_verified':True,'source_file':file,'source_trade_rows':len(rows),
   'numbered_shop_rows_before_exclusions':sum(parsed[k] for k in ['food','nonfood','mixed']),
   'parsed_by_category':{k:parsed[k] for k in ['food','nonfood','mixed']},
   'reported_by_category':expected,
   'ordinary_shop_rows_after_exclusions':sum(included.values()),
   'included_by_category':dict(included),
   'normalized_trade_content_hash_without_title':hashlib.sha256(json.dumps(rows[5:],ensure_ascii=False,sort_keys=True).encode()).hexdigest()})

shops=pd.DataFrame(rows_out)
assert shops[['source_file','source_sheet','source_row']].duplicated().sum()==0
# Two explicit, evidence-documented spelling repairs are sensitivity only.
# Original strict links are never overwritten.
reviewed=[]
for r in shops.itertuples(index=False):
    entry=r._asdict()
    candidate=None;reason=None
    if pd.isna(entry.get(KEY)):
        if re.search(r'(?<!\w)\.Чоя\b',r.address_raw,re.I):
            candidate='Чоя';reason='truncated NP prefix; explicit .Чоя in fixed Choya district'
        if re.search(r'с\.\s*Караккоша\b',r.address_raw,re.I) and 'Строител' in r.address_raw:
            candidate='Каракокша';reason='source spelling transposition; same named shop/street1/1 listed correctly in2019/2020'
    if candidate:
        found=npbase.loc[npbase.name_2021.eq(candidate)]
        assert len(found)==1
        entry['reviewed_source_record_id_2021']=found.iloc[0][KEY]
        entry['reviewed_name_2021']=candidate
        entry['reviewed_link_reason']=reason
    else:
        entry['reviewed_source_record_id_2021']=entry.get(KEY)
        entry['reviewed_name_2021']=entry.get('name_2021')
        entry['reviewed_link_reason']='strict_link_retained'
    reviewed.append(entry)
shops=pd.DataFrame(reviewed)
shops.to_csv(OUT/'choya_numbered_ordinary_shop_entries_2019_2026.csv',index=False)
shops.loc[shops.reviewed_link_reason.ne('strict_link_retained'),
    ['year','source_file','source_row','name_raw','address_raw',
     'reviewed_source_record_id_2021','reviewed_name_2021','reviewed_link_reason']].to_csv(
    OUT/'choya_reviewed_spelling_alias_sensitivity.csv',index=False)
shops.groupby(['observation_date','reviewed_source_record_id_2021','reviewed_name_2021','category'],
    dropna=False).size().reset_index(name='listed_ordinary_shop_entries').to_csv(
    OUT/'choya_shop_counts_reviewed_sensitivity.csv',index=False)

pd.DataFrame(excluded).to_csv(OUT/'choya_excluded_objects.csv',index=False)
pd.DataFrame(operator_rows).to_csv(OUT/'choya_unnumbered_operator_rows.csv',index=False)
pd.DataFrame(totals).to_csv(OUT/'choya_reported_totals.csv',index=False)
(RAW/'choya_trade_tables_extracted.json').write_text(json.dumps(rawtrade,ensure_ascii=False,indent=2))

# Only observed positive entries are aggregated; absent village×date cells remain missing.
agg=shops.groupby(['observation_date',KEY,'name_2021','category'],dropna=False).size().reset_index(name='listed_shop_entries')
agg.to_csv(OUT/'choya_observed_shop_entries_by_settlement_category.csv',index=False)
npagg=shops.groupby(['observation_date',KEY,'name_2021'],dropna=False).size().reset_index(name='listed_ordinary_shop_entries')
npagg.to_csv(OUT/'choya_observed_shop_entries_by_settlement.csv',index=False)
# Preserve every accepted NP in a panel, but missing registry occurrence is UNKNOWN, not zero.
frames=[]
for year in range(2019,2027):
 f=npbase[[KEY,'name_2021','type_2021','region_2021','district_2021','population_2021']].copy()
 f['observation_date']=f'{year}-01-01'
 f=f.merge(npagg,on=[KEY,'name_2021','observation_date'],how='left',validate='one_to_one')
 f['registry_evidence_status']=f.listed_ordinary_shop_entries.notna().map({True:'positive_listed_entries',False:'not_observed_not_zero_no_verified_complete_inventory'})
 frames.append(f)
pd.concat(frames,ignore_index=True).to_csv(OUT/'choya_settlement_panel_unknowns_preserved.csv',index=False)

# Evidence of changes in a list, not confirmed business closure/opening.
summary=shops.groupby(['year','is_choya_centre'],dropna=False).size().reset_index(name='listed_entries')
summary.to_csv(OUT/'choya_centre_surroundings_observed_entries.csv',index=False)
reviewed_roles=shops.copy()
reviewed_roles['role']=reviewed_roles.reviewed_name_2021.eq('Чоя').map({True:'centre',False:'surroundings'})
rolecat=reviewed_roles.groupby(['year','role','category']).size().unstack().reset_index()
rolecat['all_observed']=rolecat[['food','nonfood','mixed']].sum(axis=1,min_count=3)
rolecat.to_csv(OUT/'choya_centre_surroundings_reviewed_sensitivity.csv',index=False)
semantic_counts=Counter()
for year,rr in rawtrade.items():
 for i,row in enumerate(rr,1):
  text=' '.join(str(c) for c in row)
  if re.search(r'озон|ozon|wildber|вайлд|вилд|\bwb\b|выдач|маркетплейс',text,re.I):semantic_counts[year]+=1

manifest={'study':'settlement-level feasibility of ordinary physical shop outcomes',
 'download_manifest':'raw/choya_download_manifest.json','source_index':'raw/choya_register_index.html',
 'snapshot_dates':list(shops.observation_date.unique()),'source_internal_dates_match_index':True,
 'reviewed_spelling_sensitivity_rows':int(shops.reviewed_link_reason.ne('strict_link_retained').sum()),
 'shop_rows':len(shops),'excluded_object_rows':len(excluded),'unnumbered_operator_detail_rows':len(operator_rows),
 'unknown_settlement_shop_rows':int(shops[KEY].isna().sum()),
 'positive_settlements_by_date':shops.groupby('observation_date')[KEY].nunique().to_dict(),
 'marketplace_marked_rows_in_trade_table':dict(semantic_counts),
 'postal_shop_name_rows':int(shops.postal_shop_name_flag.sum()),
 'count_discrepancy_years':[r['year'] for r in audit if r['parsed_by_category']!=r['reported_by_category']],
 'identical_trade_content_years_2022_2023':audit[3]['normalized_trade_content_hash_without_title']==audit[4]['normalized_trade_content_hash_without_title'],
 'marketplace_marker_interpretation':'zero explicit textual markers does not prove no unrecorded combined shop+pickup functions',
 'count_unit':'numbered physical shop entries in dedicated retail sections; not legal entities, rubrics or addresses',
 'missing_policy':'all21 fixed census2021 settlements retained; absent observations UNKNOWN, not zero',
 'address_policy':'explicit NP prefix plus unique name within fixed RepublicAltai/ChoyaDistrict; no legal-address inference',
 'audit':audit,
 'limits':['reporting completeness/continuous updating unverified','numbering and section totals can disagree',
           '2025 additional sheet tradingregistry2 is an employment-oriented reformatted list, not an independent snapshot; main dated sector sheet used',
           'two operators at one shop address are not automatically two shops; unnumbered detail rows excluded and retained separately',
           'same address can contain multiple numbered shops, no address-only deduplication',
           'a listed-entry loss is not independently verified closure','no causal effect inferred',
           'one district demonstrates availability, not national representativeness'],
 'checks':'PASS unique source-row identities, internal dates, explicit source sections and exclusions; report count discrepancies separately',
 'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUT/'acquisition_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False,indent=2))

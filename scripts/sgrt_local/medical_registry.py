"""Read the newly downloaded primary workbook; compare Grok's full TSV text.

No relations or operational capacities are inferred. The 19 settlements are
selected using the accepted IDs already established by the service study.
"""
from pathlib import Path
import argparse, csv, collections, hashlib, json, re, urllib.request
import openpyxl
import pandas as pd
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--nodes',type=Path,required=True,help='nodes.parquet from the accepted 19-settlement service fragment')
parser.add_argument('--grok-parts-dir',type=Path,help='Optional frozen11TSVparts from pinned Grok commit for full-cell comparison')
parser.add_argument('--fetch',action='store_true',help='Download the pinned primary workbook if absent')
args=parser.parse_args()
ROOT=args.output; (ROOT/'input').mkdir(parents=True,exist_ok=True)
SOURCE_ID='TFOMS_RB_2026_REGISTRY'
SOURCE_COMMIT='c5116d1360d5c97e71aeec52a9b8e182dbcfb8ea'
SOURCE_URL='https://tfoms-rb.ru/sites/default/files/0092-2026.xlsx'
EXPECTED='fce8cc4a7c5e938d80491aaa1eb0213f432d3d31d5f3f1ad32c4059ddeb6984a'
raw=ROOT/'input/0092-2026.xlsx'
if args.fetch and not raw.exists():
 with urllib.request.urlopen(SOURCE_URL,timeout=60) as response: raw.write_bytes(response.read())
if hashlib.sha256(raw.read_bytes()).hexdigest()!=EXPECTED: raise ValueError('Primary workbook changed: reinspection required')

def norm(v): return '' if v is None else str(v).replace('\t',' ').replace('\r',' ').replace('\n',' ').strip()
book=openpyxl.load_workbook(raw,read_only=True,data_only=True)
primary=[]
for sheet in book:
 for number,row in enumerate(sheet.iter_rows(values_only=True),1):
  cells=[norm(v) for v in row]
  if not any(cells):continue
  primary.append((sheet.title,number,cells))
textrows=[]
for path in sorted(args.grok_parts_dir.glob('bashkortostan_reestr_2026_part*.tsv')) if args.grok_parts_dir else []:
 for number,row in enumerate(csv.reader(path.open(encoding='utf-8'),delimiter='\t'),1):
  textrows.append((path.name,number,row))
assert len(primary)==5050
comparison=None
if args.grok_parts_dir:
 assert len(primary)==len(textrows)==5050
 for (sheet,number,cells),(part,partrow,row) in zip(primary,textrows):
  assert row==[sheet]+cells,(number,part,partrow)
 comparison=True
if not textrows: textrows=[('',None,[]) for _ in primary]
fields={0:'organization_number',2:'organization_unique_id',3:'organization_registry_number',4:'organization_oms_code',5:'organization_full_name',6:'organization_name',7:'inn',10:'organization_oid',17:'legal_address',21:'activity_address',22:'activity_address_fias_id',23:'subdivision_code',24:'subdivision_registry_code',25:'subdivision_name',26:'subdivision_oid',27:'care_type_literal',28:'care_conditions_literal',29:'care_profile_literal',30:'inclusion_date_literal',31:'exclusion_date_literal',32:'exclusion_reason_literal'}
rows=[]
for (sheet,number,cells),(part,partrow,tsvrow) in zip(primary,textrows):
 if not cells[0].isdigit() or not re.fullmatch(r'\d{10}|\d{12}',cells[7]):continue
 row={name:cells[i] for i,name in fields.items()}
 row.update(excel_sheet=sheet,excel_row=number,tsv_part=part,tsv_row=partrow,source_id=SOURCE_ID,source_commit=SOURCE_COMMIT,source_url=SOURCE_URL,registry_year=2026,capacity_total=None,actual_patient_flow_observed=False)
 rows.append(row)
allrows=pd.DataFrame(rows)
uch=allrows[allrows.organization_name.eq('ГБУЗ РБ УЧАЛИНСКАЯ ЦРБ')].copy()
node=pd.read_parquet(args.nodes)
lookup=node.set_index('name').source_record_id.to_dict()
match=[];homonyms=[]
for row in rows:
 names=[name for name in lookup if re.search(r'(?<![А-Яа-яЁё])'+re.escape(name)+r'(?![А-Яа-яЁё])',row['activity_address'],re.I)]
 if not names:continue
 for name in names:
  r=dict(row,matched_name=name)
  if re.search(r'Учалинск\w*\s+(?:район|р-н)',row['activity_address'],re.I) and 'Башкортостан' in row['activity_address']:
   r.update(source_record_id=lookup[name],match_status='accepted_unique_exact_name_in_activity_address_Uchaly_Bashkortostan_context',evidence_kind='registry_activity_address_not_attachment',actual_operational_status_independently_checked=False)
   match.append(r)
  else:
   r.update(match_status='held_homonymous_place_wrong_or_missing_district',source_record_id=None)
   homonyms.append(r)
local=pd.DataFrame(match);held=pd.DataFrame(homonyms)
counts=local.groupby('matched_name').size().to_dict()
status=node[['source_record_id','name','core_fragment']].copy()
status['registry_subdivision_rows']=status.name.map(counts).fillna(0).astype(int)
status['local_offer_state']=status.registry_subdivision_rows.map(lambda n:'registry_listed_activity_site' if n else 'not_found_in_this_registry_not_confirmed_absent')
for name,frame in [('uchaly_all_organization_rows',uch),('local19_registry_rows',local),('held_homonymous_rows',held),('settlement_offer_evidence',status)]:
 frame.to_csv(ROOT/(name+'.csv'),index=False);frame.to_parquet(ROOT/(name+'.parquet'),index=False)
summary=dict(source_id=SOURCE_ID,primary_url=SOURCE_URL,primary_sha256=EXPECTED,primary_bytes=raw.stat().st_size,source_commit=SOURCE_COMMIT,all_primary_nonempty_rows=len(primary),all_tsv_rows=len(textrows) if comparison else None,all_tsv_cells_equal_fresh_primary=comparison,comparison_normalization='str(value), tab/CR/LF replaced with spaces, outer whitespace stripped; not workbook formatting or merged-cell equivalence',registry_data_rows=len(allrows),nonempty_metadata_rows=len(primary)-len(allrows),uchaly_hospital_rows=len(uch),local19_activity_rows=len(local),local19_settlements_with_activity_rows=int(status.registry_subdivision_rows.gt(0).sum()),local19_settlements_not_found=int(status.registry_subdivision_rows.eq(0).sum()),held_homonym_rows=len(held),distinct_activity_address_fias_ids=int(local.activity_address_fias_id.nunique()),distinct_subdivision_codes=int(local.subdivision_code.nunique()),distinct_subdivision_oids=int(local.subdivision_oid.nunique()),distinct_parent_organizations=int(local.inn.nunique()),no_exclusion_date_on_local_rows=bool(local.exclusion_date_literal.eq('').all()),nodes_sha256=hashlib.sha256(args.nodes.read_bytes()).hexdigest(),checked_date='2026-10-24',core_status=status[status.core_fragment].to_dict('records'),source_semantics='OMS_registry_for2026; inclusion_date_is_not_opening_date; absence_is_not_absent_supply; branch_or_organization_ownership_is_not_patient_referral; total_capacity_unknown',raw_header_row5=[norm(v) for v in list(book.active.iter_rows(min_row=5,max_row=5,values_only=True))[0]])
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='raw_header_row5'},ensure_ascii=False,indent=2))

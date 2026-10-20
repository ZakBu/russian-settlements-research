#!/usr/bin/env python3
"""Separate same-document address inventory; frozen sampling/linkage ledger untouched."""
from pathlib import Path
import re,json,hashlib,datetime
import pandas as pd
from lxml import html
H=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_holdout2021');SOURCE=RAW/'kaluga2021_garant_candidate.html';PDF=H/'sources/kaluga20210730_493_official.pdf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
WATCH=[H/'holdout2021_raw_row_ledger.parquet',H/'holdout2021_attachment_rows.parquet',H/'holdout2021_source_freeze_receipt.json',H/'holdout2021_protocol.json'];before={p.name:sha(p) for p in WATCH}
root=html.fromstring(SOURCE.read_bytes());tables=root.xpath('//table');schema=[]
for i,t in enumerate(tables):
 rows=t.xpath('.//tr');head=[]
 for ri,tr in enumerate(rows[:3]):head.append([{'text':' '.join(' '.join(c.itertext()).split()),'rowspan':c.get('rowspan','1'),'colspan':c.get('colspan','1')} for c in tr.xpath('./td|./th')])
 schema.append({'html_table_index':i,'rows':len(rows),'headers':head,'rowspans_total':len(t.xpath('.//*[@rowspan]')),'data_rowspan_count_after_two_headers':sum(len(tr.xpath('./td[@rowspan]')) for tr in rows[2:]),'preceding_titles':[' '.join(' '.join(x.itertext()).split()) for x in list(t.itersiblings(preceding=True))[:4]],'source_sha256':sha(SOURCE)})
(H/'holdout2021_all_table_schemas.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n')
axis=pd.read_parquet(H.parent/'axis/full_settlement_axis.parquet');axis=axis[axis.region.str.contains('калужск',case=False,na=False)]
TYPES={'г':'город','с':'село','д':'деревня','п':'посёлок','пгт':'пгт','р.п':'пгт','х':'хутор'}
def typed(raw):
 m=re.search(r'(?:^|[,;]\s*)(г|с|д|п|пгт|р\.п|х)\.\s*([^,;]+)',raw)
 if not m:return None,None,None,'no_explicit_typed_locality'
 typ=TYPES[m[1]];name=m[2].strip();v=axis[axis.name.eq(name)&axis.type.eq(typ)]
 return (v.iloc[0].id,name,typ,'literal_unique_region_name_type') if len(v)==1 else (None,name,typ,'ambiguous_or_absent_literal')
def canon(s):
 # Abbreviation equivalences only for organizational form; never infer a locality from adjectives.
 s=s.casefold();s=re.sub(r'\(фельдшерско-акушерский пункт\)','',s)
 s=re.sub(r'[^\w]+','',s).replace('_','').replace('№','').replace('n','')
 for a,b in [('государственноебюджетноеучреждениездравоохранениякалужскойобласти','гбузко'),('центральнаямежрайоннаябольница','цмб'),('центральнаярайоннаябольница','црб')]:s=s.replace(a,b)
 return s
address=[]
for ti,start in [(7,3),(8,3),(9,3),(10,2),(11,2)]:
 for ri,tr in enumerate(tables[ti].xpath('.//tr')[start:],start):
  cells=[' '.join(' '.join(c.itertext()).split()) for c in tr.xpath('./td|./th')]
  if not cells[0].isdigit():continue
  parent=cells[1];unit=cells[2] if ti<10 else cells[4];addr=cells[3] if ti<10 else cells[5];declared=None if ti<10 else cells[6];npid,name,typ,status=typed(declared or addr)
  labels=[unit]
  if ti>=10:labels.append(cells[8])
  pc=canon(parent);clean=[]
  for label in labels:
   lc=canon(label);clean.append(lc)
   if pc and lc.startswith(pc) and len(lc)>len(pc):clean.append(lc[len(pc):])
  address.append({'address_record_index':len(address),'html_table_index':ti,'html_row_index':ri,'html_cell_parent':1,'html_cell_unit':2 if ti<10 else 4,'html_cell_address':3 if ti<10 else 5,'html_cell_explicit_NP':None if ti<10 else 6,'parent_MO_name_raw':parent,'parent_MO_INN_raw':None if ti<10 else cells[2],'object_unit_name_raw':unit,'additional_unit_name_raw':None if ti<10 else cells[8],'actual_or_project_address_raw':addr,'explicit_typed_NP_raw':declared,'destination_id':npid,'destination_literal_name':name,'destination_literal_type':typ,'destination_link_status':status,'planned_module_address_only':ti==9,'address_relation_class':'planned_modular_object_location' if ti==9 else 'normative_inventory_object_or_building_location','legal_entity_address_is_headquarters':False,'facility_operating_in2021_proven_by_address':False,'source_document_date':'2021-07-30','source_url':'https://base.garant.ru/401569870/','source_html_sha256':sha(SOURCE),'official_pdf_sha256':sha(PDF),'source_locator':f'table[{ti+1}]/tr[{ri+1}]','official_pdf_page':97 if ti==7 else 98 if ti==8 and ri==3 else None,'official_pdf_page_status':'visually_verified' if ti==7 or (ti==8 and ri==3) else 'exact_HTML_cell_locator; officialPDFindividualpage_pending','canonical_unit_keys_json':json.dumps(sorted(set(clean)),ensure_ascii=False),'canonical_parent_key':pc,'raw_cells_json':json.dumps(cells,ensure_ascii=False)})
a=pd.DataFrame(address);a.to_parquet(H/'holdout2021_same_document_address_inventory.parquet',index=False)
old=pd.read_parquet(H/'holdout2021_attachment_rows.parquet');links=[];candidates=[]
for row in old.itertuples(index=False):
 key=canon(row.provider_name_raw);matches=[]
 for x in address:
  keys=json.loads(x['canonical_unit_keys_json'])
  if key and key in keys:matches.append(x)
 # One named unit may recur in equipment rows; accept NP only if every matched nonmissing location agrees and none is unresolved.
 physical=[x for x in matches if not x['planned_module_address_only']];ids={x['destination_id'] for x in physical if x['destination_id'] is not None};resolved=bool(physical) and len(ids)==1 and all(x['destination_id'] is not None for x in physical)
 for x in matches:
  candidates.append({'raw_source_row_index':row.raw_source_row_index,'provider_name_raw':row.provider_name_raw,'address_record_index':x['address_record_index'],'relation_type':'named_physical_unit_address' if not x['planned_module_address_only'] else 'planned_module_context_only','object_unit_name_raw':x['object_unit_name_raw'],'parent_MO_name_raw':x['parent_MO_name_raw'],'parent_MO_INN_raw':x['parent_MO_INN_raw'],'actual_or_project_address_raw':x['actual_or_project_address_raw'],'destination_id':x['destination_id'],'source_locator':x['source_locator'],'source_document_date':'2021-07-30','source_html_sha256':sha(SOURCE),'official_pdf_sha256':sha(PDF),'join_rule':'exact_unit_label_after_explicit_parent_prefix_and_legal_form_normalization; no fuzzy adjective or geographic inference'})
 links.append({'raw_source_row_index':row.raw_source_row_index,'origin_id':row.origin_id,'provider_name_raw':row.provider_name_raw,'frozen_destination_id':row.destination_id,'enriched_physical_unit_destination_id':next(iter(ids)) if resolved else None,'enrichment_status':'unique_same_document_named_unit_typed_address' if resolved else 'multiple_or_unresolved_source_addresses' if physical else 'only_planned_module_addresses' if matches else 'no_exact_named_unit_address_join','address_record_indices_json':json.dumps([x['address_record_index'] for x in matches]),'nonplan_address_candidates':len(physical),'planned_module_candidates':len(matches)-len(physical),'old_ledger_mutated':False,'model_agreement_read':False,'patient_trip_asserted':False,'source_document_year':2021})
pd.DataFrame(links).to_parquet(H/'holdout2021_address_enriched_linkage_sidecar.parquet',index=False);pd.DataFrame(candidates).to_parquet(H/'holdout2021_address_join_sourcecells.parquet',index=False)
assert before=={p.name:sha(p) for p in WATCH}
receipt={'status':'SAME_DOCUMENT_ADDRESS_PATH_IMPLEMENTED_PENDING_INDEPENDENT_CELL_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'all_table_schemas':len(schema),'frozen_Table1_data_rowspans':0,'parent_column_lost':False,'address_tables_html_indices':[7,8,9,10,11],'address_inventory_rows':len(a),'strict_typed_address_rows':int(a.destination_id.notna().sum()),'sidecar_rows':len(links),'joined_sourcecell_rows':len(candidates),'resolved_same_document_physical_unit_rows':sum(x['enriched_physical_unit_destination_id'] is not None for x in links),'newly_resolved_vs_frozen_rows':sum(x['frozen_destination_id'] is None and x['enriched_physical_unit_destination_id'] is not None for x in links),'still_unresolved_after_sidecar_rows':sum(x['frozen_destination_id'] is None and x['enriched_physical_unit_destination_id'] is None for x in links),'frozen_ledger_hashes_unchanged':before,'source_identity_rule':'unit equality after documentedorganizationalformformatnormalization; unique explicittypedNP; ambiguousNA; moduleplans excludedfromaccepted2021physicaladdress','no_parent_MO_headquarters_inferred':True,'administrative_parent_cells_retained':True,'no_passing_reference_to_word_model':True,'model_agreement_read':False,'all642samplingrows_preserved':True,'individual_locators':'preciseHTML2021table/row/cell locators for all; officialPDFexactperrowpages mostly pendingindependentreview','scope':'Address identity enrichment, not evidence of patienttrip, functioning2021capacity, parentcatchment, or modelaccuracy','source_sha256':sha(SOURCE),'official_pdf_sha256':sha(PDF),'outputs':{n:sha(H/n) for n in ['holdout2021_all_table_schemas.json','holdout2021_same_document_address_inventory.parquet','holdout2021_address_enriched_linkage_sidecar.parquet','holdout2021_address_join_sourcecells.parquet']}}
(H/'holdout2021_address_feasibility_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['outputs','frozen_ledger_hashes_unchanged']},ensure_ascii=False))

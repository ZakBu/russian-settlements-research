#!/usr/bin/env python3
"""Record independent visual source decisions; never reads model outputs/assignments."""
from pathlib import Path
import hashlib,json,re,datetime
import pandas as pd
H=Path(__file__).resolve().parent; AXIS=H.parent/'axis/full_settlement_axis.parquet'
# Explicit page decisions independently read from official scan renders, not inferred
# from model, OCR scores, or agreement. PDF 1-based physical pages.
VISUAL_PAGES={4:29,5:29,7:30,14:30,22:31,23:31,57:34,60:34,64:35,69:35,72:35,84:36,94:37,122:40,167:43,179:44,188:45,202:46,208:47,212:47,220:48,230:49,254:53,266:54,272:55,276:55,280:55,281:55,284:55,285:56,321:59,323:59,325:59,336:60,356:62,390:65,415:67,445:69,538:77,600:85}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
paths={'official_pdf':H/'sources/kaluga20210730_493_official.pdf','axis':AXIS,'attachment_rows':H/'holdout2021_attachment_rows.parquet','raw_row_ledger':H/'holdout2021_raw_row_ledger.parquet','source_freeze_receipt':H/'holdout2021_source_freeze_receipt.json','protocol':H/'holdout2021_protocol.json','sourceclass_amendment':H/'holdout2021_sourceclass_amendment.json','model_freeze_receipt':H/'holdout2021_model_freeze_receipt.json','review_code':Path(__file__)}
before={k:sha(v) for k,v in paths.items()}
assert before['official_pdf']=='4fd94192431472a9c96db5e47df39f0670aef91234ca2dfba50e6fafeb519637'
freeze=json.loads(paths['source_freeze_receipt'].read_text())
assert before['attachment_rows']==freeze['attachment_rows_sha256']
assert before['raw_row_ledger']==freeze['raw_row_ledger_sha256']
d=pd.read_parquet(paths['attachment_rows']);d=d[d.destination_id.notna()].copy();assert set(d.raw_source_row_index)==set(VISUAL_PAGES) and len(d)==40
raw=pd.read_parquet(paths['raw_row_ledger']).set_index('raw_source_row_index');axis=pd.read_parquet(AXIS);assert axis.id.is_unique
a=axis.set_index('id');rows=[]
T={'город':'г','деревня':'д','село':'с','посёлок':'п','пгт':'пгт'}
for r in d.itertuples(index=False):
 uid=r.destination_id; ar=a.loc[uid];cells=json.loads(raw.loc[r.raw_source_row_index,'raw_cells_json']);assert cells[:4]==[r.provider_name_raw,r.provider_type_raw,r.origin_name_type_raw,r.attached_population_raw]
 # Independent lookup in all axis records, constrained to explicit source region,
 # target's literal name and type. Names and types were visually checked above.
 cand=axis[(axis.region=='калужская')&(axis.name==ar['name'])&(axis.type==ar['type'])]
 provider_token=re.compile(r'(?<!\w)'+re.escape(T[ar['type']])+r'\.\s*'+re.escape(ar['name'])+r'(?!\w)')
 match=provider_token.search(r.provider_name_raw)
 assert len(cand)==1 and cand.iloc[0].id==uid and match
 origin_resolved=pd.notna(r.origin_id);orig=a.loc[r.origin_id] if origin_resolved else None
 same=bool(origin_resolved and r.origin_id==uid)
 if origin_resolved:
  oc=axis[(axis.region=='калужская')&(axis.name==orig['name'])&(axis.type==orig['type'])]
  origin_unique=bool(len(oc)==1 and oc.iloc[0].id==r.origin_id)
 else:origin_unique=False
 household=bool(r.is_household_unit);pop=float(r.attached_population_raw)
 if r.raw_source_row_index==281:
  decision='EXCLUDED_HOUSEHOLD_AND_CONFLICTING_SETTLEMENT_TYPES';reason='Official p55: provider д. Пробуждение, served cell Пробуждение п. Both distinct axis entities exist; no dated equivalence. Not an external attachment.'
 elif household and not origin_resolved:
  decision='EXCLUDED_HOUSEHOLD_ORIGIN_UNRESOLVED';reason='Household item, attached population0; served name lacks parsed type or spelling differs. No origin ID repair inferred.'
 elif household:
  decision='EXCLUDED_HOUSEHOLD_UNIT_ZERO_ATTACHED_POPULATION';reason='Household item is not a medical center or whole-settlement assignment; attached population0. Literal place only accepted.'
 elif pop==0:
  decision='ACCEPTED_LITERAL_LOCAL_PROVIDER_RECORD_ZERO_ATTACHMENT';reason='Provider location and served settlement literal verified; attached population0 does not establish a positive attachment population. Self location, not an external pair.'
 else:
  decision='ACCEPTED_LOCAL_NORMATIVE_ATTACHMENT_LABEL';reason='Positive attached population and explicit same settlement/provider location; no evidence all residents are covered or that observed trips occurred. No intersettlement pair.'
 row={'raw_source_row_index':int(r.raw_source_row_index),'official_pdf_page':VISUAL_PAGES[r.raw_source_row_index],'official_locator':f'PDF physical page {VISUAL_PAGES[r.raw_source_row_index]}, Table1, provider cell: {r.provider_name_raw}; served cell: {r.origin_name_type_raw}', 'provider_name_raw':r.provider_name_raw,'provider_type_raw':r.provider_type_raw,'origin_name_type_raw':r.origin_name_type_raw,'attached_population_raw':r.attached_population_raw,'destination_id':uid,'destination_axis_name':ar['name'],'destination_axis_type':ar['type'],'destination_axis_region':ar['region'],'destination_axis_id_unique':True,'destination_literal_region_name_type_unique':True,'destination_source_type_and_name_token':match.group(0),'origin_id':r.origin_id,'origin_axis_name':orig['name'] if origin_resolved else None,'origin_axis_type':orig['type'] if origin_resolved else None,'origin_axis_region':orig['region'] if origin_resolved else None,'origin_literal_region_name_type_unique':origin_unique,'same_resolved_origin_destination':same,'is_household_unit':household,'origin_scope_as_printed':'named settlement label; no street/house restriction in origin cell','provider_address_is_origin_scope':False,'whole_NP_all_residents_verified':False,'positive_normative_attachment_label_accepted':bool(not household and pop>0 and origin_unique and same),'provider_location_literal_accepted':True,'accepted_intersettlement_comparable_pair':False,'decision':decision,'reason':reason,'visually_reviewed_official_cells':'provider name/location, provider type, directly served settlement, attached population','visual_transcription_match':'confirmed aside from whitespace/line wraps and №/N typography; source contradictions preserved','reviewer':'Codex /root/agro_demographic_context; independent of ledger author /root/road_accessibility','official_pdf_sha256':before['official_pdf'],'frozen_attachment_rows_sha256':before['attachment_rows'],'axis_sha256':before['axis'],'model_assignments_read':False,'model_agreement_computed':False}
 rows.append(row)
out=pd.DataFrame(rows);out.to_csv(H/'holdout2021_independent_source_review.csv',index=False)
after={k:sha(v) for k,v in paths.items()};assert before==after
review={'status':'INDEPENDENT_SOURCE_REVIEW_COMPLETE_NO_ACCEPTED_INTERSETTLEMENT_PAIRS','reviewer':'Codex /root/agro_demographic_context','ledger_author':'Codex /root/road_accessibility','reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'review_scope':'All40 provider-ID-resolved frozen rows; four source cells visually read against official scans on27 physical PDF pages. Remaining602 data rows not independently cell-verified in this review.','visual_method':'Official PDF rendered with PyMuPDF at1.8scale; first56% of landscape page contains provider, type, served settlement, attached population and planned capacity. Seven contact sheets manually inspected. OCR/transcription used for navigation only.','visual_physical_pages':sorted(set(VISUAL_PAGES.values())),'table_header_verified_page':29,'header_origin_cell_literal':'Непосредственно обслуживаемые населенные пункты, закрепленные по участковому принципу','header_population_cell_literal':'Численность населения в обслуживаемых населенных пунктах, закрепленных по участковому принципу (прикрепленное)','reviewed_rows':40,'provider_location_literals_unique_in_regional_axis':40,'household_rows_excluded':int(out.is_household_unit.sum()),'nonhousehold_local_provider_records':int((~out.is_household_unit).sum()),'positive_local_normative_attachment_labels':int(out.positive_normative_attachment_label_accepted.sum()),'zero_attached_nonhousehold_provider_rows':out.loc[(~out.is_household_unit)&out.attached_population_raw.eq('0'),'raw_source_row_index'].tolist(),'resolved_identical_origin_destination_rows':int(out.same_resolved_origin_destination.sum()),'origin_unresolved_rows':out.loc[out.origin_id.isna(),'raw_source_row_index'].tolist(),'conflicting_type_rows':[281],'accepted_intersettlement_comparable_pairs':0,'scope_conclusion':'Named served-settlement labels do not certify every resident is assigned. Provider street/house address does not restrict origin to those houses. Household registry items cannot be promoted into whole-NP medical centers/attachments. City hospital/child-consultation totals can cover population subsets. All10 nonhousehold resolved records are local; no independent intersettlement destination test is supported by this resolved subset.','all642_source_rows_accepted':False,'official_pdf_individual_pages_accepted_for_this40':True,'model_assignments_read':False,'model_agreement_computed':False,'model_parameters_changed':False,'frozen_protocol_or_ledger_rewritten':False,'source_sha256_before':before,'source_sha256_after':after,'source_unchanged_verified':before==after,'review_csv_sha256':sha(H/'holdout2021_independent_source_review.csv'),'exceptions':out.loc[~out.positive_normative_attachment_label_accepted,['raw_source_row_index','official_pdf_page','decision','reason']].to_dict(orient='records'),'acceptance_limit':'Source-only acceptance of nine local positive normative attachment labels, one zero-attachment provider record, and40 literal provider locations. This does not authorize agreement metrics from household, unresolved, conflicting, zero or self-location records as external functional validation.'}
(H/'holdout2021_independent_source_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:review[k] for k in ['status','reviewed_rows','household_rows_excluded','nonhousehold_local_provider_records','positive_local_normative_attachment_labels','resolved_identical_origin_destination_rows','origin_unresolved_rows','accepted_intersettlement_comparable_pairs']},ensure_ascii=False))

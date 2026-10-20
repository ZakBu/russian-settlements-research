#!/usr/bin/env python3
"""Freeze every source row before metrics; literal-only census IDs, uncertain locators explicit."""
from pathlib import Path
import json,hashlib,re,datetime
import pandas as pd,numpy as np
from lxml import html
from sklearn.feature_extraction.text import TfidfVectorizer
H=Path(__file__).resolve().parent;R=H.parent;RAW=Path('/workspace/scratch/sgrt_holdout2021');PDF=RAW/'kaluga2021_official_http_pdf.pdf';HTML=RAW/'kaluga2021_garant_candidate.html'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(PDF)=='4fd94192431472a9c96db5e47df39f0670aef91234ca2dfba50e6fafeb519637'
freeze=json.loads((H/'holdout2021_model_freeze_receipt.json').read_text());assert sha(Path(freeze['model_manifest_path']))==freeze['model_manifest_sha256'],'Fixedmodelbyteschanged'
axis=pd.read_parquet(R/'axis/full_settlement_axis.parquet');axis=axis[axis.region.str.contains('калужск',case=False,na=False)]
rows=html.fromstring(HTML.read_bytes()).xpath('//table')[5].xpath('.//tr');assert len(rows)==644
rawrows=[]
for i,tr in enumerate(rows):
 cells=[' '.join(' '.join(c.itertext()).split()) for c in tr.xpath('./td|./th')]
 rawrows.append({'raw_source_row_index':i,'source_row_kind':'header' if i<2 else 'data','raw_cells_json':json.dumps(cells,ensure_ascii=False),'html_table_index':5,'html_row_index':i,'html_locator':f'table[6]/tr[{i+1}]','html_source_sha256':sha(HTML),'official_source_sha256':sha(PDF),'official_document_date':'2021-07-30','official_document_number':'493'})
pd.DataFrame(rawrows).to_parquet(H/'holdout2021_raw_row_ledger.parquet',index=False)
TYPES={'г':'город','с':'село','д':'деревня','п':'посёлок','рп':'пгт','пгт':'пгт','х':'хутор'}
def strict_id(raw):
 raw=raw.strip();match=re.fullmatch(r'(.+?)\s+(г|с|д|п|рп|пгт|х)\.?',raw)
 if not match:return None,'unparsed_literal_name_type',None,None
 name=match[1].strip();typ=TYPES[match[2]];cand=axis[axis.name.eq(name)&axis.type.eq(typ)]
 return (cand.iloc[0].id,'literal_unique_region_name_type',name,typ) if len(cand)==1 else (None,'ambiguous_literal' if len(cand)>1 else 'no_exact_literal_match',name,typ)
provider_patterns=[]
for a in axis[axis.type.isin(['город','пгт','село','деревня','посёлок'])].itertuples(index=False):
 short={'город':'г','пгт':'пгт','село':'с','деревня':'д','посёлок':'п'}[a.type]
 provider_patterns.append((a.id,re.compile(r'(?<![\w])'+re.escape(short)+r'\.\s*'+re.escape(a.name)+r'(?![\w])')))
def provider_id(raw):
 # Explicit standalone place spelling and type only; no adjective/district-name inference.
 found=[uid for uid,pattern in provider_patterns if pattern.search(raw)]
 return (found[0],'explicit_literal_provider_location_unique') if len(found)==1 else (None,'no_unique_explicit_literal_provider_location')

records=[]
for i,tr in enumerate(rows[2:],2):
 cells=[' '.join(' '.join(c.itertext()).split()) for c in tr.xpath('./td|./th')];provider,kind,origin=cells[:3];oid,ostatus,oname,otype=strict_id(origin);did,dstatus=provider_id(provider)
 records.append({'raw_source_row_index':i,'provider_name_raw':provider,'provider_type_raw':kind,'origin_name_type_raw':origin,'attached_population_raw':cells[3],'source_grain':'medicalorganization_or_structuralunit_attachment_registry','origin_id':oid,'origin_link_status':ostatus,'origin_literal_name':oname,'origin_literal_type':otype,'destination_id':did,'destination_link_status':dstatus,'provider_location_inferred_from_served_NP':False,'is_household_unit':kind=='Домовое хозяйство','explicit_scope':'first complete Table1 medicalorganizations/units providingprimarycare; all642data rows, not full patienttravel OD','official_pdf_start_page':29,'official_pdf_end_page':94,'official_pdf_page':None,'official_pdf_page_status':'appendix_range_verified_individual_page_not_yet_verified','source_url':'http://publication.pravo.gov.ru/file/pdf?eoNumber=4000202108050001','official_pdf_sha256':sha(PDF),'transcription_url':'https://base.garant.ru/401569870/','transcription_sha256':sha(HTML),'transcription_status':'secondaryHTML transcription paired with officialscannednormativeact; individual cells need independentvisualreview','model_output_read_for_linking':False,'comparison_performed':False})
df=pd.DataFrame(records)
# Page candidates are OCR navigation aids only. No fuzzy string match ever assigns IDs.
ocr=[];pages=list(range(29,95))
for page in pages:
 p=RAW/'ocr'/f'page_{page:03d}.txt';assert p.exists(),p;ocr.append(p.read_text())
texts=ocr+[r['provider_name_raw']+' '+r['origin_name_type_raw'] for r in records];vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=1);m=vec.fit_transform(texts);score=(m[len(pages):]@m[:len(pages)].T).toarray();n,k=score.shape
DP=np.full((n,k),-1e10);prev=np.zeros((n,k),dtype='int32');DP[0,0]=score[0,0]
for i in range(1,n):
 for j in range(k):
  lo=max(0,j-3);a=lo+int(np.argmax(DP[i-1,lo:j+1]));DP[i,j]=DP[i-1,a]+score[i,j];prev[i,j]=a
path=[k-1]
for i in range(n-1,0,-1):path.append(int(prev[i,path[-1]]))
path=path[::-1];df['official_pdf_page_candidate']=[pages[j] for j in path];df['official_page_candidate_score']=[float(score[i,j]) for i,j in enumerate(path)];df['official_page_candidate_method']='monotonicTfidfOCR navigation; NOT individually accepted page or IDlink'
df.to_parquet(H/'holdout2021_attachment_rows.parquet',index=False);df.to_csv(H/'holdout2021_attachment_rows.csv',index=False)
receipt={'status':'SOURCE_AND_ALL_ROWS_FROZEN_PENDING_INDEPENDENT_CELL_AND_LOCATOR_REVIEW','registered_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol_sha256':sha(H/'holdout2021_protocol.json'),'sourceclass_amendment_sha256':sha(H/'holdout2021_sourceclass_amendment.json'),'model_freeze_receipt_sha256':sha(H/'holdout2021_model_freeze_receipt.json'),'model_manifest_sha256':freeze['model_manifest_sha256'],'official_pdf':{'path':str(PDF),'url':'http://publication.pravo.gov.ru/file/pdf?eoNumber=4000202108050001','bytes':PDF.stat().st_size,'sha256':sha(PDF),'pages':374,'appendix_table':'Table1, substituted bysection1.6.1ofdecree','attachment_table_pdf_pages':[29,94],'document_date':'2021-07-30','document_number':'493','official_publication_number':'4000202108050001'},'transcription':{'url':'https://base.garant.ru/401569870/','bytes':HTML.stat().st_size,'sha256':sha(HTML),'table_index':5,'all_rows_including_headers':644,'all_data_rows':len(df),'selection':'every source table row; no modelagreement filter'},'strict_origin_linked_rows':int(df.origin_id.notna().sum()),'strict_provider_location_linked_rows':int(df.destination_id.notna().sum()),'ambiguous_missing_retained':True,'household_rows_retained':int(df.is_household_unit.sum()),'raw_row_ledger_sha256':sha(H/'holdout2021_raw_row_ledger.parquet'),'attachment_rows_sha256':sha(H/'holdout2021_attachment_rows.parquet'),'individual_pdf_page_candidates':'OCRnavigationonly; exactappendixrangeverified, perrowpagesnotindependentlyaccepted','comparison_performed':False,'model_parameters_changed':False,'source_relations_disclosed_to_modelagent':False,'kirov_status':'official2020programacquired; notdated2021eligibleattachmentcorpus;2024amendmentnotused','acquisition_result':'eligible2021officialKalugapublicationactuallyreceived; Kirov2021eligibleappendixnotacquired','interpretation':'normativeattachedproviderregistry, not observedpatienttrips; externalnewgeographicholdout aftermodelfreeze, not historicalblindtrial'}
(H/'holdout2021_source_freeze_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['status','strict_origin_linked_rows','strict_provider_location_linked_rows','household_rows_retained']}))

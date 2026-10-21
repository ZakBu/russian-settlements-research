#!/usr/bin/env python3
"""Entire2021 official schoolterritory-for-child-accounting appendix, no modelread."""
from pathlib import Path
import re,json,hashlib,datetime
import pandas as pd,fitz
HERE=Path(__file__).resolve().parent;BASE=HERE.parent;SRC=HERE/'sources/andreapol20210303_63.pdf'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v):return re.sub('[^а-я0-9]+',' ',str(v).lower().replace('ё','е')).strip()
def main():
 doc=fitz.open(SRC);pages=[p.get_text()for p in doc];text='\n'.join(pages);starts=[0]
 for p in pages[:-1]:starts.append(starts[-1]+len(p)+1)
 school=list(re.finditer(r'МОУ (?:АСОШ № [123]|Скудинская ООШ|Болотовская СОШ|Волокская ООШ|Хотилицкая ООШ)',text));assert len(school)==7
 corrections={'МОУ Болотовская СОШ':'МОУ Бологовская СОШ','Болотове':'Бологово','Лом и некое':'Ломинское','Ревя кино':'Ревякино','Кузнецове':'Кузнецово','Дмитрове':'Дмитрово','Пашкове':'Пашково','Поспелое':'Поспелово','Чирикове':'Чириково','Залоги':'Заноги','Наново':'Паново'}
 # Corrections are visual readings of the original PDFpages2/3, notgeocoder fixes.
 (HERE/'andreapol_visual_transcription_corrections.json').write_text(json.dumps({'method':'authorvisualreadback originalPDFpages2/3; pending independentreview','corrected_exact_ocr_values':corrections,'source_sha256':sha(SRC)},ensure_ascii=False,indent=2))
 rows=[];blocks=[]
 section_re=r'(Улицы|Переулки|Площади|Деревни|Поселки|Село|Хутор|Поселок|Сёла):'
 types={'Деревни':'деревня','Поселки':'посёлок','Поселок':'посёлок','Село':'село','Сёла':'село','Хутор':'хутор'}
 for i,m in enumerate(school):
  end=school[i+1].start()if i+1<len(school)else len(text);b=text[m.end():end];matches=list(re.finditer(section_re,b));provider=corrections.get(m.group(),m.group());blocks.append({'block':i+1,'provider_source_ocr':m.group(),'provider_visual_name':provider,'source_pages':sorted(set(j+1 for j,v in enumerate(starts)if v<end and (j==len(starts)-1 or starts[j+1]>m.start()))),'raw_full_block':b.strip()})
  for j,q in enumerate(matches):
   stop=matches[j+1].start()if j+1<len(matches)else len(b);raw=b[q.end():stop].strip();parts=raw.split(',')
   for itemno,item in enumerate(parts):
    cleaned=re.sub(r'\s+',' ',item).strip().rstrip('.').strip()
    if not cleaned:continue
    corrected=corrections.get(cleaned,cleaned);kind=q.group(1);pos=m.end()+q.end();sourcepage=max(k+1 for k,v in enumerate(starts)if v<=pos)
    # The firstASOШ2village section begins on page3; other section pages direct.
    rows.append({'source_row_id':f'and2021:b{i+1}:s{j+1}:i{itemno+1}','school_block':i+1,'provider_source_ocr':m.group(),'provider_source_name':provider,'source_page':sourcepage,'source_section':kind,'source_item_ocr':cleaned,'source_item_visual':corrected,'source_type':types.get(kind),'unit_kind':'settlement'if kind in types else'urban_street_or_square_source_fragment','relation_kind':'normative_school_territory_for_child_accounting_NOT_observed_attendance_or_trips','provider_physical_site_id':None,'provider_settlement_uid':None,'source_snapshot':'2021-03-03','source_decree':'Andреапольский МО Тверской области №63','source_sha256':sha(SRC),'source_selection':'entirefirstacquiredeligibleofficial2021appendix; all7schoolblocks/allsections/allitems; noassignmentbasedselection','manual_visual_correction':corrected!=cleaned})
 df=pd.DataFrame(rows);axis=pd.read_parquet(BASE/'axis/full_settlement_axis.parquet');a=axis[axis.region.eq('тверская')&axis.district_raw_2021.fillna('').str.contains('андреаполь',case=False)].copy();a['_n']=a.name.map(norm)
 # Source-native censuslocality IDs are linkable only when name AND explicittype
 # agree uniquely within the document's independently declared district.
 out=[]
 for _,r in df.iterrows():
  if r.unit_kind!='settlement':out.append({'origin_uid':None,'origin_link_status':'nonsettlement_streetretained','origin_candidates_json':'[]'});continue
  z=a[a['_n'].eq(norm(r.source_item_visual))];zt=z[z.type.eq(r.source_type)]
  if len(zt)==1:uid=zt.iloc[0].id;status='unique_name_explicit_type_declared2021district'
  elif len(zt)>1:uid=None;status='ambiguous_same_name_type_in_district'
  elif len(z):uid=None;status='source_native_type_conflict_pending_independentreview'
  else:uid=None;status='source_identity_unresolved_in_declared2021district'
  out.append({'origin_uid':uid,'origin_link_status':status,'origin_candidates_json':json.dumps(z[['id','name','type','district_raw_2021','population_2021']].to_dict('records'),ensure_ascii=False)})
 df=pd.concat([df,pd.DataFrame(out)],axis=1);df['source_duplicate_pair']=df.duplicated(['provider_source_name','source_item_visual','source_type'],keep=False)
 df.to_parquet(HERE/'andreapol2021_complete_source_ledger.parquet',index=False);pd.DataFrame(blocks).to_parquet(HERE/'andreapol2021_complete_school_blocks.parquet',index=False)
 # Provideridentity remains pending; do not infer location fromschoolname,
 # currentorglegaladdress or a municipalityheadquarters.
 receipt={'status':'ENTIRE_OFFICIAL2021_CORPUS_EXTRACTED_PENDING_INDEPENDENT_PAGE_AND_PROVIDER_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_url':'https://andreapolobr.ru/images/Постановление_63.pdf','source_pdf_sha256':sha(SRC),'pdf_pages':len(doc),'all_school_blocks':len(school),'all_source_item_rows':len(df),'source_settlement_rows':int(df.unit_kind.eq('settlement').sum()),'street_square_source_fragments_retained':int(df.unit_kind.ne('settlement').sum()),'origin_link_statuses':df.origin_link_status.value_counts().to_dict(),'origin_uids':int(df.origin_uid.nunique()),'source_duplicate_rows_retained':int(df.source_duplicate_pair.sum()),'author_has_read_model_assignments_or_agreement':False,'actual_attendance_or_trip_claim':False,'source_purpose':'Schools assignedterritories for identifying/registeringchildren0–18subjecttocompulsoryeducation; this decree alone doesnotestablish attendedschooloractualflows','physical_provider_locators_not_in_decree':True,'code_sha256':sha(Path(__file__)),'outputs_sha256':{p.name:sha(p)for p in [HERE/'andreapol2021_complete_source_ledger.parquet',HERE/'andreapol2021_complete_school_blocks.parquet',HERE/'andreapol_visual_transcription_corrections.json']}}
 (HERE/'andreapol2021_corpus_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

"""Literal historical school locality inventory from a regional codes appendix.

The PDF was created2013 and served with Last-Modified timestamp2014-02-07; its
order date/number are blank. This is historical named-organisation evidence,
not verified operation2026 or geocoded school buildings. No nearest-NP match.
"""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,unicodedata
from pathlib import Path
import pandas as pd

SOURCE_URL='https://www.uprobrbkmr.ru/itog_attest/prilozhenie_k_pr-o_kodakh_ou.pdf'
SOURCE_SHA='2efbea3a32d1a53e18bced493d91c976dca5e20f3bb70cc0b067f50860917937'
SOURCE_ID='SARATOV_EDUCATION_CODES_METADATA_2013_2014'


def norm(s):
    s=str(s).casefold().replace('ё','е').replace('ѐ','е')
    s=re.sub(r'[-–—]',' ',s)
    return re.sub(r'\s+',' ',s).strip()


def parse_layout(text):
    rows=[];cur=None;page=1
    for line in text.split('\n'):
        if '\f' in line:page+=line.count('\f');line=line.replace('\f','')
        m=re.match(r'^\s*(\d{3})\s+(\d{6})\s+(.+)',line)
        if m:
            if cur:rows.append(cur)
            cur={'ate':m[1],'organisation_code':m[2],'name':m[3].strip(),'source_pdf_page':page}
        elif cur and line.strip():
            # Standalone page numbers and district headings are not school names.
            if re.fullmatch(r'\s*\d{1,3}\s*',line):continue
            if re.fullmatch(r'\s*[А-ЯЁ][А-Яа-яё -]+ муниципальный район\s*',line):continue
            cur['name']+=' '+line.strip()
    if cur:rows.append(cur)
    for r in rows:r['name']=re.sub(r'\s+',' ',r['name']).strip()
    return pd.DataFrame(rows)


def school_scope(name):
    t=norm(name)
    primary=('начальн' in t and 'школ' in t) or 'младшего школьного возраста' in t
    if not primary and not any(x in t for x in ['общеобразовательн','гимназ','лицей']):return 'not_general_school'
    if ('дошкольн' in t and not primary) or any(x in t for x in ['профессиональн','агропромышлен','техникум','колледж','институт','университет']):return 'not_general_school'
    if any(x in t for x in ['коррекцион','санатор','интернат','специальн']):return 'special_or_boarding_scope'
    if any(x in t for x in ['вечерн','сменн','открытого типа','закрытого типа']):return 'evening_shift_or_restricted_scope'
    return 'ordinary_general_school_named_organisation'


def inferred_grades(name):
    t=norm(name)
    if any(x in t for x in ['средн','гимназ','лицей']):return '1–11'
    if 'основн' in t:return '1–9'
    if 'начальн' in t:return '1–4'
    return None


def explicit_locality_candidates(name,roster):
    """Accept only literal type+name occurrences, with explicit orthographic normalisation."""
    text=norm(name);hits=[]
    kinds={'село':r'(?:с\.|село|села)','посёлок':r'(?:п\.|пос\.|поселок|поселка)','город':r'(?:г\.|город|города)',
        'рабочий посёлок':r'(?:р\.?\s?п\.|рабочий поселок|рабочего поселка)',
        'хутор':r'(?:х\.|хутор|хутора)','деревня':r'(?:д\.|деревня|деревни)',
        'железнодорожный объект':r'(?:ст\.|станция|ж\.?д\.?\s?ст\.|ж\.?д\.?\s?рзд\.|разъезд)'}
    for r in roster.itertuples(index=False):
        prefix=kinds.get(str(r.settlement_type_2021))
        if prefix is None:continue
        literal=norm(r.name)
        pattern=r'(?<![а-яa-z])'+prefix+r'\s*'+re.escape(literal)+r'(?![а-яa-z])'
        matches=list(re.finditer(pattern,text))
        if matches:hits.append((r.source_record_id,max(x.start() for x in matches)))
    # A branch's explicit locality wins only if after the word филиал. Legal
    # parent's earlier locality must never become the branch's physical place.
    if 'филиал' in text:
        start=text.rfind('филиал');hits=[h for h in hits if h[1]>start]
    return sorted(set(x[0] for x in hits))


def link_records(records,roster):
    municipalities=roster.district.drop_duplicates().tolist()
    rural=[x for x in municipalities if 'муниципальный район' in x]
    authorities=records[records.organisation_code.str.endswith('000')].set_index('ate').name.to_dict()
    mapping={}
    for ate,name in authorities.items():
        body=norm(name).replace('саратовской области','')
        hits=[d for d in rural if norm(d.split()[0][:-2]) in body]
        if len(hits)==1:mapping[ate]=hits[0]
        elif 'саратов' in body and 'город' in body:mapping[ate]='Городской округ город Саратов'
        elif 'михайловский' in body:mapping[ate]='Городской округ поселок Михайловский'
        elif 'шиханы' in body:mapping[ate]='Городской округ город Шиханы'
        elif 'светл' in body:mapping[ate]='Городской округ поселок Светлый (ЗАТО)'
    out=[]
    for r in records.itertuples(index=False):
        scope=school_scope(r.name)
        if scope=='not_general_school':continue
        district=mapping.get(r.ate)
        subset=roster[roster.district.eq(district)] if district else roster.iloc[0:0]
        candidates=explicit_locality_candidates(r.name,subset)
        sid=candidates[0] if len(candidates)==1 else None
        record={'provider_id':'historical_school_code:'+r.organisation_code,'organisation_code':r.organisation_code,
            'ate':r.ate,'name':r.name,'district_context':district,'source_record_id':sid,
            'identity_status':'literal_type_and_locality_within_explicit_municipal_code' if sid else 'held_missing_or_multiple_literal_localities',
            'candidate_np_ids_json':json.dumps(candidates,ensure_ascii=False),'scope':scope,
            'grades_name_signal':inferred_grades(r.name),'grades_verified':False,'school_grades_verified':False,'grade_inferred_from_name':True,
            'service_code':'school_general','source_id':SOURCE_ID,'source_url':SOURCE_URL,
            'source_pdf_page':r.source_pdf_page,'source_year':None,
            'metadata_creation_year':2013,'metadata_last_modified_year':2014,
            'source_year_basis':'content_date_unknown_PDFcreation2013_HTTPlastmodified2014_orderdate_blank',
            'source_legal_status':'officially_hosted_appendix_order_date_and_number_blank',
            'historical_only':True,'operation2026_verified':False,'actual_operational_status_verified':False,
            'retrieval_year':2026,'retrieval_date_utc':'2026-10-28',
            'source_year_is_verified_operation_year':False,'observed_flow':False,
            'eligible_np_presence_proxy':bool(sid and scope=='ordinary_general_school_named_organisation'),
            'physical_route_seed_eligible':False,'location_precision':'literal_historical_named_organisation_locality_not_geocoded_building'}
        out.append(record)
    return pd.DataFrame(out),mapping


def run(pdf,roster,baseline_presence,output):
    pdf=Path(pdf);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest!=SOURCE_SHA:raise ValueError('Historical PDF differs from pinned source')
    layout=output/'historical_codes_layout.txt'
    subprocess.run(['pdftotext','-layout',str(pdf),str(layout)],check=True)
    records=parse_layout(layout.read_text());reference=pd.read_parquet(roster)
    schools,mapping=link_records(records,reference)
    records.to_parquet(output/'all_historical_codes.parquet',index=False)
    schools.to_parquet(output/'historical_school_localities.parquet',index=False)
    schools.to_csv(output/'historical_school_localities.csv',index=False)
    accepted=schools[schools.eligible_np_presence_proxy.eq(True)]
    baseline=pd.read_parquet(baseline_presence);known=set(baseline.loc[baseline.family.eq('school'),'source_record_id'].dropna().astype(str))
    new=sorted(set(accepted.source_record_id)-known)
    summary={'source_url':SOURCE_URL,'source_sha256':digest,'pdf_pages':161,'content_reference_year_unknown_metadata2013_2014_not_operation2026':True,
        'parsed_organisations':len(records),'school_records_all_scopes':len(schools),'school_scope_counts':schools.scope.value_counts().to_dict(),
        'linked_ordinary_records':len(accepted),'linked_ordinary_np':accepted.source_record_id.nunique(),
        'new_historical_np_vs_current_baseline':len(new),'baseline_known_school_np':len(known&set(reference.source_record_id)),
        'new_historical_np_ids':new,'code_to_municipality':mapping,'no_nearest_np_matching':True,
        'historical_presence_is_not_current_operation':True,'source_order_date_and_number_blank':True}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False),flush=True)
    return schools,summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['pdf','roster','baseline-presence','output']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();run(**vars(a))
if __name__=='__main__':main()

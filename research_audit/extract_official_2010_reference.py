"""Extract an independent, non-exhaustive census 2010 Table 5 reference.

No population replacement or entity certification. PDF pages 13–210 are the
verified Table 5 boundaries (printed pages 12–209); neighbouring tables differ.
Line numbers refer to pypdf text lines, not visual baseline coordinates.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import unicodedata
import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'
OUT = ROOT / 'research_audit/evidence'
NUM = re.compile(r'^(.*?)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s+(\d+,\d+|-)\s+(\d+,\d+|-)\s*$')
TYPE = re.compile(r'^(г\.|город|пгт|село|пос[еёѐ]лок|деревня|станица|хутор|аул|слобода|местечко|селение|кишлак)\s+(.+)$', re.I)


def norm(s):
    s = unicodedata.normalize('NFKC', str(s or '')).lower().replace('ѐ','е').replace('ё','е')
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', s)).strip()


def region_key(s):
    s = norm(s)
    s = re.sub(r'\b(республика|область|край|автономный|автономная|округ|г)\b', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return {'саха якутия':'саха', 'северная осетия алания':'северная осетия',
            'чувашская чувашия':'чувашская','ханты мансийский югра':'ханты мансийский'}.get(s,s)


def settlement(label):
    text = re.sub(r'^(Городское|Сельское) население\s*[-–]\s*', '', label)
    if re.search(r'подчиненн|администраци|населенными пунктами|включая', text, re.I):
        return None
    match = TYPE.match(text)
    if not match:
        return None
    typ, name = match.groups()
    typ = {'г.':'город','посёлок':'поселок','посѐлок':'поселок'}.get(typ.lower(),typ.lower())
    name = re.sub(r'\s*\((?:рц|цмр)\)\s*', '', name)
    name = re.sub(r'\s+(?:рп|кп|дп)\s*$', '', name).strip()
    return typ, name


def extract(pdf=PDF, output=OUT):
    output.mkdir(parents=True,exist_ok=True)
    reader = PdfReader(pdf)
    if len(reader.pages)!=1073:
        raise ValueError('PDF layout changed: review Table 5 boundaries before extraction')
    pages = []
    for i in range(12,210):
        text = reader.pages[i].extract_text()
        if i==12:
            assert '5. ЧИСЛЕННОСТЬ НАСЕЛЕНИЯ РОССИИ' in text
        else:
            assert 'таблицы 5' in text[:150], f'Unexpected table at PDF page {i+1}'
        for line_no,line in enumerate(text.splitlines(),1):
            pages.append({'pdf_page':i+1,'printed_page':i,'text_line':line_no,'raw_line':line})
    assert 'таблицы 4' in reader.pages[11].extract_text()
    assert '6. ГРУППИРОВКА' in reader.pages[210].extract_text()
    lines = pd.DataFrame(pages)
    lines.to_parquet(output/'official_2010_table5_lines.parquet',index=False)
    records=[]; unparsed=[]; region=None; district=None; parent=None; pending=[]
    for row in pages:
        text=row['raw_line'].strip()
        if not text: continue
        match=NUM.match(text)
        if not match:
            # Retain every line, and explicitly log unconsumed labels/footnotes.
            if TYPE.match(text) or re.match(r'^(Городское|Сельское) население\s*[-–]',text) or re.search(r'район|область|Республика|автономн|подчиненн|населенными пунктами',text):
                pending.append(row)
            else:
                unparsed.append(dict(row,reason='non_numeric_header_footer_or_unparsed',region_context=region))
            continue
        label,*values=match.groups()
        joined=pending+[row]
        if pending:
            label=' '.join([r['raw_line'].strip() for r in pending]+[label]).strip()
            pending=[]
        total,men,women=[0 if v=='-' else int(v) for v in values[:3]]
        is_region=(re.search(r'область|Республика|республика|край|автономный округ',label) is not None
                   and not re.search(r'район|подчиненн|без |население|в том числе',label))
        federal_city = re.match(r'^г\. (Москва|Санкт-Петербург)(?: - городское население)?$',label)
        if federal_city: is_region=True
        if is_region:
            region=('г. '+federal_city.group(1)) if federal_city else label
            district=None;parent=None
        elif re.match(r'^.+? район(?:\s|$)',label) and not TYPE.match(label):
            district=label.split(' - ')[0];parent=district
        elif re.search('подчиненн',label):
            district=None;parent=label
        parsed=settlement(label)
        kind='settlement' if parsed and not is_region else 'aggregate'
        rec=dict(reference_id=f'ROSSTAT2010:T5:p{row["pdf_page"]}:l{joined[0]["text_line"]}',
                 census_year=2010,pdf_page=row['pdf_page'],printed_page=row['printed_page'],
                 text_line_start=joined[0]['text_line'],text_line_end=row['text_line'],
                 label_raw=label,raw_lines=json.dumps(joined,ensure_ascii=False),
                 region_raw=region,district_raw=district,parent_context=parent,row_kind=kind,
                 population=total,men=men,women=women,total_equals_sexes=total==men+women,
                 dash_in_counts='-' in values[:3],regional_center='(рц)' in label,
                 settlement_type=parsed[0] if parsed else None,settlement_name=parsed[1] if parsed else None)
        rec['reference_status']='extracted_reference' if total==men+women and region else 'quarantined'
        if kind=='settlement' and (len(joined)>1 or not region):
            rec['reference_status']='needs_wrapped_label_review' if len(joined)>1 else 'quarantined'
        records.append(rec)
    unparsed.extend(dict(x,reason='unconsumed_pending_label',region_context=region) for x in pending)
    frame=pd.DataFrame(records)
    consumed=[(x['pdf_page'],x['text_line']) for rec in records for x in json.loads(rec['raw_lines'])]
    consumed += [(x['pdf_page'],x['text_line']) for x in unparsed]
    expected=[(x['pdf_page'],x['text_line']) for x in pages if x['raw_line'].strip()]
    assert len(consumed)==len(set(consumed)) and set(consumed)==set(expected), 'Source text line loss or reuse'
    assert frame.reference_id.is_unique
    frame['hierarchy_status']='sequential_pdf_context_not_identity_proof'
    frame['region_key']=frame.region_raw.map(region_key)
    frame['name_key']=frame.settlement_name.map(norm)
    frame['type_key']=frame.settlement_type.map(norm)
    frame.to_parquet(output/'official_2010_table5_reference.parquet',index=False)
    pd.DataFrame(unparsed).to_parquet(output/'official_2010_table5_unparsed.parquet',index=False)
    return frame


def compare(ref, output=OUT):
    numeric_records=len(ref)
    sex_failures=int((~ref.total_equals_sexes).sum())
    regions=int(ref.region_raw.nunique())
    # Independent hand-read fixtures include same-name different-district rows,
    # and a large settlement whose count differs materially from Lingvarium.
    for name,district,population in [('Комсомольское','Грозненский район',6945),
                                    ('Комсомольское','Гудермесский район',4392),
                                    ('Гой-Чу','Урус-Мартановский район',5078),
                                    ('Двубратский','Усть-Лабинский район',8541)]:
        hit=ref[ref.settlement_name.eq(name)&ref.district_raw.eq(district)]
        assert len(hit)==1 and int(hit.iloc[0].population)==population, (name,district)
    assert regions==83, 'Review missing or false region headings'
    census=pd.read_parquet(ROOT/'data/processed/census_crosswalk.parquet')
    census=census[census.census_year.eq(2010)].copy()
    census['region_key']=census.region_raw.map(region_key)
    census['name_key']=census.settlement_name.map(norm)
    census['type_key']=census.settlement_type.map(norm)
    key=['region_key','name_key','type_key']
    ref=ref[ref.row_kind.eq('settlement')].copy()
    ref['official_key_count']=ref.groupby(key).reference_id.transform('size')
    census['local_key_count']=census.groupby(key).source_record_id.transform('size')
    result=ref.merge(census[key+['source_record_id','population','district_raw','local_key_count']],
                     on=key,how='left',suffixes=('_official','_local'))
    result['comparison_status']='ambiguous_or_unmatched_candidate'
    unique=result.official_key_count.eq(1)&result.local_key_count.eq(1)&result.reference_status.eq('extracted_reference')
    result.loc[unique,'comparison_status']='unique_text_key_candidate_not_identity_proof'
    result['population_delta_local_minus_official']=result.population_local-result.population_official
    result['automatic_replacement_allowed']=False
    result.to_parquet(output/'official_2010_table5_comparison.parquet',index=False)
    summary={'pdf_path':str(PDF),'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),
      'table_pdf_pages_one_based':[13,210],'table_printed_pages':[12,209],
      'scope':'All urban settlements, rural district centres, and rural settlements >=3000 as published in Table 5; NOT an exhaustive all-settlement census.',
      'numeric_records':numeric_records,'regions':regions,'sex_sum_failures':sex_failures,
      'settlement_rows':len(ref),'unique_text_key_candidates':int(unique.sum()),
      'unique_candidates_with_population_difference':int((unique&result.population_delta_local_minus_official.ne(0)).sum()),
      'unique_candidates_official_population_sum':int(result.loc[unique,'population_official'].sum()),
      'unique_candidates_local_population_sum':int(result.loc[unique,'population_local'].sum()),
      'candidate_difference_counts':{'local_lower':int((unique&result.population_delta_local_minus_official.lt(0)).sum()),
                                     'local_higher':int((unique&result.population_delta_local_minus_official.gt(0)).sum())},
      'reviewed_large_discrepancy_context':[
          {'name':'Двубратский','pdf_page':81,'printed_page':80,'text_line':45,
           'official_total':8541,'men':5786,'women':2755,'context':'Separate settlement row among rural settlements of Усть-Лабинский район; not a row labelled with subordinate settlements.'},
          {'name':'Калининец','pdf_page':36,'printed_page':35,'text_line':19,
           'official_total':21774,'men':13153,'women':8621,'context':'Separate пгт row alongside Киевский, Кокошкино, Селятино in Наро-Фоминский район; not a city-with-subordinates aggregate.'}],
      'discrepancy_cause':'Unresolved. Institutional/military populations are a hypothesis, not established by this extraction.',
      'qa':['All nonempty PDF text lines retained exactly once as parsed-record provenance or unparsed log.',
            'Reference IDs unique.','83 region headings recovered.','Four hand-read district/name/population fixtures passed.'],
      'limitations':['Name+region+type is candidate evidence only.','No automatic replacement.','District context is extracted sequentially and requires review before use as identity proof.','All original text lines retained; wrapped labels flagged.','Dash counts provisionally parsed as zero, dash flag retained.']}
    (output/'official_2010_table5_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(result[unique].assign(abs_delta=lambda x:x.population_delta_local_minus_official.abs()).sort_values('abs_delta',ascending=False)[['region_raw','settlement_name','population_official','population_local','population_delta_local_minus_official']].head(25).to_string(index=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-extraction',action='store_true');args=parser.parse_args()
    ref=pd.read_parquet(OUT/'official_2010_table5_reference.parquet') if args.reuse_extraction else extract()
    compare(ref)

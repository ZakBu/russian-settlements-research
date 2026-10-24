#!/usr/bin/env python3
"""Rebuild source-bounded local service relations, without inferred patient trips.

The source PDF is scanned. Selected complete rows were visually transcribed from
its original pages 10 and 13; the PDF hash below pins the inspected document.
Unknown school grades and capacity dates are deliberately retained.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request
import pandas as pd

SOURCES = {
    'UCH2025_03224': ('uchaly_school_2025.pdf', 'https://uralsk1.ucoz.ru/Obrazovanie/2025_postanovlenie_territorii.pdf'),
    'UCH_FAP_REPORT': ('uchaly_fap.html', 'https://www.xn--90ad1cm.xn--p1ai/bylo-stalo'),
    'UCH_STRUCTURE': ('uchaly_structure.html', 'https://xn--90ad1cm.xn--p1ai/ob-uchrezhdenii/struktura'),
    'UCH_NEWS_CATEGORY': ('uchaly_news_all.html', 'https://xn--90ad1cm.xn--p1ai/ob-uchrezhdenii/novosti-uchrezhdeniya?limit=0'),
}
# Complete selected rows: ordinal, PDF page, school location, address,
# column-4 territory, explicitly grade-limited column-5 subsets.
ROWS = [
    (25, 13, 'Уральск', 'Советская, 4',
     ['Уральск','Истамгулово','Октябрьск','Ишкиново','Базаргулово','Амангильдино','Калуево','Малоказаккулово','Новобайрамгулово','Суяргулово','Мусино','Каипкулово'],
     {'school_upper': ['Амангильдино','Калуево','Малоказаккулово']}),
    (26, 13, 'Курама', 'Соловьиная, 9', ['Курама','Каримово'],
     {'school_lower_secondary': ['Курама','Каримово']}),
    (27, 13, 'Малоказаккулово', 'Советская, 36', ['Амангильдино','Калуево','Малоказаккулово'],
     {'school_lower_secondary': ['Амангильдино','Калуево','Малоказаккулово']}),
    (15, 10, 'Комсомольск', 'Школьная, 28', ['Курама','Каримово','Комсомольск','Тунгатарово','Старобайрамгулово','Старомуйнаково','Старобалбуково'],
     {'school_upper': ['Курама','Каримово']}),
]
CORE = {'Малоказаккулово','Амангильдино','Калуево','Уральск'}

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self, data):
        if data.strip(): self.parts.append(data.strip())

def text_of(path):
    h=Text(); h.feed(path.read_text(encoding='utf-8')); return re.sub(r'\s+',' ',' '.join(h.parts))

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20), b''): h.update(b)
    return h.hexdigest()

def write_table(frame, out, name):
    frame.to_csv(out/(name+'.csv'),index=False)
    frame.to_parquet(out/(name+'.parquet'),index=False)

def build(population, out, fetch=False):
    out.mkdir(parents=True,exist_ok=True); src=out/'sources';src.mkdir(exist_ok=True)
    manifests=[]
    for sid,(name,url) in SOURCES.items():
        p=src/name
        if fetch and not p.exists():
            req=urllib.request.Request(url,headers={'User-Agent':'sgrt-local-research/1'})
            try:
                with urllib.request.urlopen(req,timeout=60) as r: p.write_bytes(r.read())
            except OSError:
                if sid=='UCH_NEWS_CATEGORY': continue
                raise
        if not p.exists():
            if sid=='UCH_NEWS_CATEGORY': continue
            raise FileNotFoundError(f'{p}; use --fetch or provide frozen source')
        manifests.append(dict(source_id=sid,path='sources/'+name,url=url,bytes=p.stat().st_size,sha256=digest(p),read_scope='selected_original_scanned_PDF_pages1_3_10_13' if name.endswith('pdf') else 'selected_provider_statement_or_structure',materialized_file_mtime_utc=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()))
    pdf=src/SOURCES['UCH2025_03224'][0]
    if digest(pdf) != PDF_SHA256: raise ValueError('School PDF changed: reinspect selected original rows before reuse')
    fap=text_of(src/'uchaly_fap.html'); structure=text_of(src/'uchaly_structure.html')
    assert 'Малоказаккулово и Калуево' in fap and '330 человек' in fap and '52 ребенка' in fap
    assert 'Уральская УБ' in structure
    if not re.search(r'16 Уральская УБ .{0,100}?Участковая больница 10',structure):
        raise ValueError('Reinspect Ural hospital row: expected original row16 with10beds')
    for filename, text in [('uchaly_fap_excerpt.txt',fap),('uchaly_structure_excerpt.txt',structure)]:
        (src/filename).write_text(text,encoding='utf-8')
    news=src/'uchaly_news_all.html'; pubdate=None
    if news.exists():
        h=news.read_text(encoding='utf-8')
        # Restrict publication timestamp to the article containing the same FAP
        # statement; a date elsewhere on a category page is not its date.
        for article in re.findall(r'<article\b.*?</article>',h,flags=re.S|re.I):
            if 'Малоказаккулово и Калуево' in text_fragment(article):
                t=text_fragment(article)
                if re.search(r'09\.01\.2025\s+12:15',t):pubdate='2025-01-09'
    base=pd.read_parquet(population)
    frame=base[base.region_norm_2021.eq('башкортостан') & base.district_raw_2021.str.contains('Учалин',na=False)].copy()
    names=sorted({n for row in ROWS for n in row[4]})
    selected=[]; held=[]
    for name in names:
        candidate=frame[frame.settlement_name_2021.eq(name)]
        if len(candidate)!=1:
            held.append(dict(name=name,status='ambiguous_or_not_found_in_accepted_2021_context',candidate_count=len(candidate)));continue
        x=candidate.iloc[0]
        row=dict(source_record_id=x.source_record_id_2021,root=x.root,name=name,lon=x.accepted_longitude_2021,lat=x.accepted_latitude_2021,oktmo_2021=x.oktmo_2021,region='башкортостан',district=x.district_raw_2021,settlement_type=x.settlement_type_2021,core_fragment=name in CORE,match_method='unique_exact_name_within_region_and_Uchaly_district_then_2021_source_record_id',accepted_point_present=x.accepted_point_present_2021)
        for year in (2002,2010,2021):
            for col in ('population','effective_population','population_value_quality','source_record_id','working_credit_present'):
                row[f'{col}_{year}']=x[f'{col}_{year}']
        row['historical_boundary_equivalence_proven']=None
        selected.append(row)
    nodes=pd.DataFrame(selected); lookup=nodes.set_index('name').source_record_id.to_dict()
    links=[]; providers=[]
    def relation(origin,dest,code,sid,kind,date,locator,**kwargs):
        links.append(dict(link_id=f'L{len(links)+1:03d}',origin_id=lookup.get(origin),destination_id=lookup.get(dest),origin_name=origin,destination_name=dest,function='education' if code.startswith('school') else 'healthcare',service_order=code,service_code=code,evidence_kind=kind,source_id=sid,source_url=SOURCES[sid][1],document_date=date,observation_year=None,observed_flow=False,locator=locator,destination_settlement_accepted=True,building_destination_confirmed=False,geometry_kind='accepted_settlement_point_not_institution_building',external=origin!=dest,**kwargs))
    for number,page,dest,address,territory,levels in ROWS:
        for origin in territory:
            code=next((c for c,ns in levels.items() if origin in ns),'school_grade_unspecified')
            relation(origin,dest,code,'UCH2025_03224','normative_attachment','2025-03-12',f'PDF_page{page}_printed{page-2}_row{number}_columns4and5',grade_basis='explicit_column5' if code!='school_grade_unspecified' else 'column4_only_grade_not_specified',complete_selected_provider_territory=True)
        for code in levels:
            providers.append(dict(provider_id='school:'+dest,source_record_id=lookup.get(dest),provider_name='Школа '+dest,service_code=code,supply_status='observed',service_basis='explicit_grade_specific_territorial_attachment_in_original_act',source_id='UCH2025_03224',source_url=SOURCES['UCH2025_03224'][1],document_date='2025-03-12',observation_year=None,address_literal=address,address_kind='legal_address_in_school_act',geometry_kind='accepted_settlement_point_not_school_building',capacity_total=None,capacity_unit=None,capacity_observation_year=None,locator=f'PDF_page{page}_row{number}',complete_region_inventory=False))
        if dest in ['Уральск','Комсомольск']:
            providers.append(dict(provider_id='school:'+dest,source_record_id=lookup.get(dest),provider_name='Школа '+dest,service_code='school_lower_secondary',supply_status='proxy',service_basis='secondary_school_institution_type_not_explicit_grade_offer_for_own_territory',source_id='UCH2025_03224',source_url=SOURCES['UCH2025_03224'][1],document_date='2025-03-12',observation_year=None,address_literal=address,address_kind='legal_address_in_school_act',geometry_kind='accepted_settlement_point_not_school_building',capacity_total=None,capacity_unit=None,capacity_observation_year=None,locator=f'PDF_page{page}_row{number}',complete_region_inventory=False))
    for origin in ['Малоказаккулово','Калуево']:
        relation(origin,'Малоказаккулово','medical_primary_fap','UCH_FAP_REPORT','provider_reported_service',pubdate,'Было-стало; paragraph В ФАП д.Малоказаккулово',published_served_population=330,published_children=52,population_reference_date=None,publication_date_rechecked=bool(pubdate))
    providers.append(dict(provider_id='fap:Малоказаккулово',source_record_id=lookup['Малоказаккулово'],provider_name='ФАП Малоказаккулово',service_code='medical_primary_fap',supply_status='observed',service_basis='provider_explicitly_reports_two_served_villages',source_id='UCH_FAP_REPORT',source_url=SOURCES['UCH_FAP_REPORT'][1],document_date=pubdate,observation_year=None,address_literal=None,capacity_total=None,capacity_unit=None,capacity_observation_year=None,locator='Было-стало; first FAP paragraph',complete_region_inventory=False,published_served_population=330,published_children=52,population_reference_date=None))
    providers.append(dict(provider_id='hospital:Уральская_УБ',source_record_id=lookup['Уральск'],provider_name='Уральская УБ',service_code='medical_local_hospital',supply_status='observed',service_basis='provider_structure_names_Uralsk_local_hospital_settlement_inferred_from_name',source_id='UCH_STRUCTURE',source_url=SOURCES['UCH_STRUCTURE'][1],document_date=None,observation_year=None,address_literal=None,capacity_total=10.,capacity_unit='beds_total_not_vacant_beds_or_outpatient_slots',capacity_observation_year=None,locator='Наименование структурных подразделений / row16 Уральская УБ',complete_region_inventory=False))
    linkframe=pd.DataFrame(links); supply=pd.DataFrame(providers)
    for frame in [linkframe,supply]:
        frame['grade_span']=frame.service_code.map({'school_lower_secondary':'1-9','school_upper':'10-11'})
    for n,d in [('nodes',nodes),('links',linkframe),('supply',supply),('held_names',pd.DataFrame(held,columns=['name','status','candidate_count']))]:write_table(d,out,n)
    assert len(nodes)==19 and len(held)==0
    assert len(linkframe)==26 and linkframe.origin_id.notna().all() and linkframe.destination_id.notna().all()
    assert linkframe[linkframe.source_id.eq('UCH2025_03224')].groupby('destination_name').size().to_dict()=={'Комсомольск':7,'Курама':2,'Малоказаккулово':3,'Уральск':12}
    assert not linkframe.observed_flow.any()
    assert not linkframe.duplicated(['origin_id','destination_id','service_order']).any()
    summary=dict(nodes=len(nodes),source_relations=len(linkframe),external_relations=int(linkframe.external.sum()),known_provider_service_rows=len(supply),observed_offer_rows=int(supply.supply_status.eq('observed').sum()),school_provider_territory_sizes={'Уральск':12,'Комсомольск':7,'Малоказаккулово':3,'Курама':2},fap_published_population=330,fap_population_reference_date=None,fap_publication_date=pubdate,scope='complete_four_selected_school_territories_not_complete_district; two_village_FAP_statement; hospital_presence_not_patient_referral',population_base_sha256=digest(population),source_manifest=manifests,source_record_identity='accepted_2021_ID; inter-census identity and boundary equivalence not newly validated')
    (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary

def text_fragment(s):
    h=Text();h.feed(s);return re.sub(r'\s+',' ',' '.join(h.parts))

PDF_SHA256 = '6914efd5c8e33f3ef5410726098fc78876379649d097f41370782d32a71fea08'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--population',type=Path,required=True,help='Accepted settlements_census_wide.parquet')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fetch',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.population,a.output,a.fetch),ensure_ascii=False,indent=2))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXPERIMENTAL third-party Ozon city-name + WGS84-coordinate linkage.
Run with pyarrow and geographiclib; does not modify WB national or pilot outputs.
"""
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from geographiclib.geodesic import Geodesic

OUT = Path(__file__).resolve().parent
INPUT = OUT/'ozon_nutrygo_normalized_20260806.csv'
POP = OUT.parent/'pilot/inputs/data/population/settlements_census_long.parquet'
BASE = OUT/'national_base_all_wide.parquet'
NATIONAL_TARGET = OUT/'national_target_source2021.parquet'
PREFIX = re.compile(r'^(?:поселок\s+городского\s+типа|рабочий\s+поселок|городской\s+поселок|железнодорожная\s+станция|железнодорожный\s+разъезд|город|пгт|р\.?\s*п\.?|поселок|пос\.?|село|деревня|станица|ст\-ца|хутор|аул|г\.|п\.|с\.|д\.|х\.)\s+', re.I)


def norm(value):
    value = unicodedata.normalize('NFKC', value or '').lower().replace('ё','е')
    value = value.replace('\\u200b','').replace('\u200b','').replace('\xa0',' ')
    value = re.sub(r'[«»“”"\u2019]', '', value).strip()
    value = PREFIX.sub('', value).strip()
    value = re.sub(r'[-–—]', ' ', value)
    value = re.sub(r'\s+', ' ', value)
    return value.strip(' .,')


def finite(x):
    return isinstance(x, (int,float)) and math.isfinite(x)


def writecsv(name, rows):
    if not rows:
        (OUT/name).write_text('',encoding='utf-8')
        return
    with (OUT/name).open('w', encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    source = pq.read_table(POP,filters=[('census_year','=',2021)]).to_pylist()
    assert len({r['source_record_id'] for r in source})==len(source)
    physical = [r for r in source if r['population_scope']=='settlement' and r['is_additive_settlement_record'] is True]
    eligible = [r for r in physical if r['accepted_point_present'] is True and finite(r['accepted_latitude']) and finite(r['accepted_longitude'])]
    names=defaultdict(list)
    for r in eligible:names[norm(r['settlement_name'])].append(r)
    federal = {norm(r['settlement_name']):r for r in source if r['population_scope']=='federal_city_region'}
    points=list(csv.DictReader(INPUT.open(encoding='utf-8-sig')))
    assert len(points)==92503 and len({r['objectid'] for r in points})==len(points)
    assert Counter(r['raw_p'] for r in points)=={'0':87505,'1':4998}
    links=[]
    countmaps={radius:defaultdict(Counter) for radius in (1,5,10)}
    for obj in points:
        label=norm(obj['city_label'])
        try:lat,lon=float(obj['lat']),float(obj['lon'])
        except (ValueError,TypeError):lat,lon=None,None
        valid=finite(lat) and finite(lon) and -90<=lat<=90 and -180<=lon<=180
        row={'objectid':obj['objectid'],'city_label':obj['city_label'],'normalized_city_label':label,'address':obj['address'],'latitude':lat,'longitude':lon,'raw_p':obj['raw_p'],'point_type_inferred':'pickup_point' if obj['raw_p']=='0' else 'parcel_locker','raw_k':obj['raw_k'],'source_shard':obj['source_shard'],'declared_snapshot':obj['declared_snapshot'],'source_kind':obj['source_kind'],'federal_territory_context_source2021':None,'eligible_exact_name_candidates_n':len(names.get(label,[]))}
        if label in federal:
            row['federal_territory_context_source2021']=federal[label]['source_record_id']
        distances=[]
        if valid and label not in federal:
            for r in names.get(label,[]):
                # 0.1 degree latitude exceeds10km even at minimum meridional scale.
                if abs(r['accepted_latitude']-lat)>0.1:continue
                km=Geodesic.WGS84.Inverse(lat,lon,r['accepted_latitude'],r['accepted_longitude'])['s12']/1000
                if km<=10:distances.append((km,r))
        distances.sort(key=lambda t:(t[0],t[1]['source_record_id']))
        for radius in (1,5,10):
            candidates=[(km,r) for km,r in distances if km<=radius]
            if label in federal:status='federal_city_label_context_not_distributed'
            elif not valid:status='unresolved_invalid_coordinate'
            elif not label:status='unresolved_empty_city_label'
            elif not names.get(label):status='unresolved_no_exact_name_on_accepted_coordinate_axis'
            elif not candidates:status='unresolved_named_candidates_outside_radius'
            elif len(candidates)>1:status='ambiguous_multiple_exact_name_candidates_within_radius'
            else:status='accepted_unique_exact_name_within_radius'
            matched=candidates[0] if status.startswith('accepted_') else None
            row[f'link_status_{radius}km']=status
            row[f'named_candidates_within_{radius}km_n']=len(candidates)
            row[f'accepted_source_record_id_2021_{radius}km']=matched[1]['source_record_id'] if matched else None
            row[f'accepted_distance_WGS84_km_{radius}km']=matched[0] if matched else None
            row[f'accepted_region_{radius}km']=matched[1]['region_norm'] if matched else None
            row[f'accepted_working_credit_{radius}km']=matched[1]['working_credit_present'] if matched else None
            if matched:countmaps[radius][matched[1]['source_record_id']][obj['raw_p']]+=1
        links.append(row)
    countrows=[]
    for r in physical:
        x={'source_record_id_2021':r['source_record_id'],'name_2021':r['settlement_name'],'type_2021':r['settlement_type'],'region_2021':r['region_norm'],'district_2021':r['district_raw'],'accepted_point_present_2021':r['accepted_point_present'],'working_credit_present_2021':r['working_credit_present'],'population_2021':r['effective_population']}
        for radius in (1,5,10):
            c=countmaps[radius].get(r['source_record_id'],{})
            x[f'ozon_pickup_inferred_accepted_{radius}km_count']=c.get('0',0)
            x[f'ozon_locker_inferred_accepted_{radius}km_count']=c.get('1',0)
            x[f'ozon_all_inferred_accepted_{radius}km_count']=c.get('0',0)+c.get('1',0)
        x['ozon_zero_evidence_interpretation']='unknown_no_accepted_point_for_geolink' if r['accepted_point_present'] is not True else 'zero_accepted_records_in_partial_third_party_archive_not_confirmed_absence'
        countrows.append(x)
    counts={r['source_record_id_2021']:r for r in countrows}
    target=pq.read_table(NATIONAL_TARGET).to_pylist()
    combined=[]
    for r in target:
        x=dict(r);c=counts[r['source_record_id_2021']];x.update({k:v for k,v in c.items() if k.startswith('ozon_')})
        for radius in (1,5,10):
            for ozon_type in ('pickup','all'):
                op=c[f'ozon_{ozon_type}_inferred_accepted_{radius}km_count']>0
                for wbvariant,wbfield in [('baseline','WB_evidence_status'),('pointshift_sensitivity','WB_evidence_status_sensitivity')]:
                    ws=r[wbfield]
                    if ws=='positive':category='both_positive_accepted' if op else 'WB_positive_no_accepted_Ozon_partial_unknown'
                    elif ws=='zero_accepted_records_not_confirmed_absence':category='Ozon_positive_no_accepted_WB' if op else 'neither_accepted_not_confirmed_absence'
                    else:category='WB_unknown_Ozon_positive' if op else 'WB_unknown_Ozon_no_accepted_partial_unknown'
                    x[f'platform_category_{ozon_type}_{radius}km_{wbvariant}']=category
        combined.append(x)
    coverage={}
    for radius in (1,5,10):
        for ozon_type in ('pickup','all'):
            for wbvariant in ('baseline','pointshift_sensitivity'):
                catfield=f'platform_category_{ozon_type}_{radius}km_{wbvariant}'
                for label,keys in [('national',[]),('region',['region_2021']),('size',['size2021']),('region_size',['region_2021','size2021'])]:
                    groups=defaultdict(list)
                    for x in combined:groups[tuple(x.get(k) for k in keys)].append(x)
                    out=[]
                    for values,group in sorted(groups.items(),key=lambda t:tuple(map(str,t[0]))):
                        cc=Counter(x[catfield] for x in group);n=len(group)
                        row=dict(zip(keys,values));row.update({'settlements_n':n,'ozon_archive_partial':True,'ozon_type_inferred':ozon_type,'geolink_radius_km':radius,'WB_variant':wbvariant})
                        for category in ['both_positive_accepted','WB_positive_no_accepted_Ozon_partial_unknown','Ozon_positive_no_accepted_WB','neither_accepted_not_confirmed_absence','WB_unknown_Ozon_positive','WB_unknown_Ozon_no_accepted_partial_unknown']:
                            row[category+'_n']=cc[category]
                        row['ozon_positive_n']=cc['both_positive_accepted']+cc['Ozon_positive_no_accepted_WB']+cc['WB_unknown_Ozon_positive']
                        row['ozon_zero_accepted_partial_unknown_n']=n-row['ozon_positive_n']
                        row['WB_unknown_n']=cc['WB_unknown_Ozon_positive']+cc['WB_unknown_Ozon_no_accepted_partial_unknown']
                        row['ozon_positive_share_all_main_target']=row['ozon_positive_n']/n
                        assert sum(cc.values())==n
                        out.append(row)
                    assert sum(x['settlements_n'] for x in out)==len(target)
                    name=f'ozon_coverage_{label}_{ozon_type}_{radius}km_{wbvariant}.csv';writecsv(name,out)
                    if label=='national':coverage[f'{ozon_type}_{radius}km_{wbvariant}']=out[0]
    pq.write_table(pa.Table.from_pylist(links),OUT/'ozon_objectlinks_experimental.parquet',compression='zstd')
    pq.write_table(pa.Table.from_pylist(countrows),OUT/'ozon_counts_source2021_experimental.parquet',compression='zstd')
    pq.write_table(pa.Table.from_pylist(combined),OUT/'ozon_WB_comparison_main_target_experimental.parquet',compression='zstd')
    writecsv('ozon_counts_source2021_experimental.csv',countrows)
    pilot=OUT.parent/'pilot'
    centrechecks=list(csv.DictReader((pilot/'candidate_centres.csv').open(encoding='utf-8-sig')))
    neighbours=list(csv.DictReader((pilot/'candidate_neighbours.csv').open(encoding='utf-8-sig')))
    selected=[];seen=set()
    for role,rows in [('pilot_centre',centrechecks),('pilot_WBpositive_neighbour',[x for x in neighbours if x['commerce_wb20261021_baseline_focus_count'] and float(x['commerce_wb20261021_baseline_focus_count'])>0])]:
        for x in rows:
            sid=x['id']
            if sid in seen:continue
            seen.add(sid);c=counts[sid]
            selected.append({'pilot_role':role,'source_record_id_2021':sid,'name_2021':x['name'],'type_2021':x['type'],'WB_focus20261021_count':x['commerce_wb20261021_baseline_focus_count'],**{k:v for k,v in c.items() if k.startswith('ozon_')}})
    assert len(selected)==9
    writecsv('ozon_pilot_six_centres_three_WBpositive_neighbours.csv',selected)
    pilot_groups=defaultdict(list)
    for x in neighbours:pilot_groups[(x['centre_id'],x['centre_name'])].append(x)
    pilot_comparison=[]
    for (centre_id,centre_name),group in pilot_groups.items():
        x={'centre_id':centre_id,'centre_name':centre_name,'screened_neighbours_20km_n':len(group),'screen_is_functional_catchment':False}
        for radius in (1,5,10):
            positive=[r for r in group if counts[r['id']][f'ozon_pickup_inferred_accepted_{radius}km_count']>0]
            x[f'neighbour_Ozon_pickup_positive_{radius}km_link_n']=len(positive)
            x[f'neighbour_Ozon_positive_share_{radius}km_link']=len(positive)/len(group)
        x['WBpositive_neighbours_n']=sum(bool(r['commerce_wb20261021_baseline_focus_count']) and float(r['commerce_wb20261021_baseline_focus_count'])>0 for r in group)
        x['Ozonpositive5km_without_positive_WB_evidence_neighbours_n']=sum(counts[r['id']]['ozon_pickup_inferred_accepted_5km_count']>0 and (not r['commerce_wb20261021_baseline_focus_count'] or float(r['commerce_wb20261021_baseline_focus_count'])==0) for r in group)
        pilot_comparison.append(x)
    writecsv('ozon_pilot_neighbourhood_screening.csv',pilot_comparison)
    pilot_positive_neighbours=[]
    for r in neighbours:
        count=counts[r['id']]['ozon_pickup_inferred_accepted_5km_count']
        if count>0:
            pilot_positive_neighbours.append({'centre_id':r['centre_id'],'centre_name':r['centre_name'],'source_record_id_2021':r['id'],'neighbour_name':r['name'],'neighbour_type':r['type'],'screen_distance_to_centre_WGS84_km':r['distance_WGS84_geodesic_km'],'WB_evidence_status':r['WB_evidence_status'],'WB_focus20261021_count':r['commerce_wb20261021_baseline_focus_count'],'Ozon_pickup_inferred_accepted5km_count':count})
    writecsv('ozon_pilot_positive_neighbours_details.csv',pilot_positive_neighbours)
    fed=Counter((x['normalized_city_label'],x['raw_p']) for x in links if x['federal_territory_context_source2021'])
    writecsv('ozon_federal_city_context.csv',[{'normalized_federal_city_label':name,'raw_p':p,'inferred_type':'pickup_point' if p=='0' else 'parcel_locker','objects_n':n} for (name,p),n in sorted(fed.items())])
    summary={'analysis':'EXPERIMENTAL third-party Ozon name-coordinate geolink; descriptive cross-platform presence','declared_Ozon_snapshot':'2026-08-06 17:20','WB_snapshot':'2026-10-21','snapshots_are_contemporaneous':False,'Ozon_source_is_official_verified_registry':False,'Ozon_archive_total_unique_objects':len(points),'Ozon_type_scale':{'raw_p0':{'inferred_label':'pickup_point','objects_n':87505},'raw_p1':{'inferred_label':'parcel_locker','objects_n':4998},'raw_k':'retained without semantic interpretation; p0/p1 interpretation comes from third-party archive normalization, not independently confirmed platform schema'},'physical_source2021_n':len(physical),'physical_source2021_with_accepted_coordinates_n':len(eligible),'main_working_credit_target_n':len(target),'link_rule':'NFKC/lowercase/yo-e/quotes/hyphen-space/explicit-type-prefix normalization; city_label must equal normalized settlement name; unique exact-name candidate within WGS84 geodesic radius; no nearest-only, no fuzzy or address rescue. Candidate axis includes notcredited physical source records, which are excluded from main sums.','federal_rule':'Moscow/SaintPetersburg/Sevastopol city_label -> separate territory context, never distributed to small settlements.','source2021_join_rule':'Exact accepted source_record_id2021; WB national output remains unchanged.','link_status_counts':{},'accepted_type_counts_by_radius':{},'accepted_settlement_counts_by_radius':{},'main_coverage':coverage,'pilot_checks':selected,'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (INPUT,POP,BASE,NATIONAL_TARGET)],'cautions':['Third-party archive may omit objects; accepted positivity is evidence, zero is not absence.','Source snapshot label is not date of physical opening.','August Ozon and October WB2026 snapshots differ in time.','Geodesic name-coordinate linkage has no consumer-flow or catchment interpretation.','Coordinate radius is an object-identity screen, not service-access radius.','No standardized source region filter; same-name ambiguity inside radius stays unresolved.','Types are source-inferred; lockers kept separate from pickup points.','Candidate eligibility and sparse source coverage can affect differences between platforms.','This dataset cannot estimate marketplace effects or historical exposure.']}
    for radius in (1,5,10):
        statuses=Counter(x[f'link_status_{radius}km'] for x in links)
        assert sum(statuses.values())==len(points)
        accepted=[x for x in links if x[f'accepted_source_record_id_2021_{radius}km'] is not None]
        assert sum(sum(c.values()) for c in countmaps[radius].values())==len(accepted)
        summary['link_status_counts'][str(radius)]=dict(statuses)
        summary['accepted_type_counts_by_radius'][str(radius)]=dict(Counter(x['raw_p'] for x in accepted))
        summary['accepted_settlement_counts_by_radius'][str(radius)]={'all_physical_source2021':len(countmaps[radius]),'working_credit_main':sum((c[f'ozon_all_inferred_accepted_{radius}km_count']>0) and c['working_credit_present_2021'] is True for c in countrows)}
    summary['accepted_object_counts_main_vs_notcredited_by_radius']={str(radius):dict(Counter('main_working_credit' if x[f'accepted_working_credit_{radius}km'] is True else 'physical_notcredited' for x in links if x[f'accepted_source_record_id_2021_{radius}km'] is not None)) for radius in (1,5,10)}
    summary['pilot_neighbourhood_screening']=pilot_comparison
    summary['pilot_positive_neighbour_unique_source2021_n']=len({r['source_record_id_2021'] for r in pilot_positive_neighbours})
    summary['pilot_Ozon_positive_additional_to_positive_WB_unique_source2021_n']=len({r['source_record_id_2021'] for r in pilot_positive_neighbours if r['WB_evidence_status']!='positive_accepted_WB_focus'})
    summary['cross_platform_comparability_warning']='Ozon exact city-name5km p0 vs WB original address-name baseline10km types8/34 are different measurement rules, source scope and dates. Counts cannot establish relative commercial coverage or a2x market advantage.'
    (OUT/'ozon_summary_experimental.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    notes=['ЭКСПЕРИМЕНТАЛЬНЫЙ слой Ozon из стороннего архива. Сам архив не публикуется.', 'Основной профиль: уникальный НП с точно совпадающим нормализованным city_label и WGS84 расстоянием≤5км;1/10км — чувствительность. Все координаты НП взяты из accepted census20261022.', 'Кандидатная ось включает все физические строки2021 с accepted coordinates. Основные суммы используют только working_credit_present=True; notcredited не суммируются с основной осью.', 'Москва, Санкт-Петербург, Севастополь вынесены в федеральный context и не распределены по малым НП.', 'Коды raw_p:0 — предполагаемый ПВЗ,1 — предполагаемый постамат. Это интерпретация стороннего архива, не независимо проверенная схема Ozon. raw_k сохранён без толкования.', 'Два среза неодновременны: Ozon объявлен архивом06.08.2026, WB21.10.2026. Даты открытия неизвестны.', 'Ozon partial unknown: ноль принятых объектов не означает отсутствие ПВЗ. Ни neither accepted, ни WB-only accepted не доказывают отсутствия услуги другой платформы.', 'Сравнение имеет четыре категории для известного WB: both accepted; WB positive/no accepted Ozon; Ozon positive/no accepted WB; neither accepted. Неизвестный WB показан ещё двумя отдельными категориями с Ozon-positive либо без принятого Ozon.', 'Профиль5км: '+json.dumps(summary['link_status_counts']['5'],ensure_ascii=False),'Main pickup5км coverage: '+json.dumps(coverage['pickup_5km_baseline'],ensure_ascii=False),'В ozon_pilot_six_centres_three_WBpositive_neighbours.csv проверены6центров и3уникальных WB-positive НП окружения. Исходные файлы пилота и WB national не изменены.', 'Не применены nearest-only, fuzzy, адресная спасательная привязка и вывод о функциональном ареале. Нужна независимая адресная проверка принятых связей.']
    notes.append('Правила сопоставления платформ различаются: Ozon city-label5км,p0; WB исходная адресно-именная привязка10км,типы8/34. Вместе с разными датами/полнотой это запрещает вывод о превосходстве рыночного охвата Ozon из простого отношения числа НП.')
    notes.append('Дополнительно все486пар НП окружения проверены в ozon_pilot_neighbourhood_screening.csv. Круги20км остаются скринингом, радиусы1/5/10км относятся к привязке ОБЪЕКТА к НП, а не обслуживанию клиента.')
    notes.append('В окружении принято Ozon-p0 в '+str(summary['pilot_positive_neighbour_unique_source2021_n'])+' уникальныхНП; '+str(summary['pilot_Ozon_positive_additional_to_positive_WB_unique_source2021_n'])+' изних не имели положительного принятогоWB. Это дополнительные положительные свидетельства Ozon, не доказательство физического отсутствия WB и не датированное новое открытие.')
    (OUT/'ozon_notes_experimental.txt').write_text('\n'.join(notes)+'\n',encoding='utf-8')
    print(json.dumps({'objects':len(points),'status5km':summary['link_status_counts']['5'],'accepted_type_counts5km':summary['accepted_type_counts_by_radius']['5'],'accepted_settlements5km':summary['accepted_settlement_counts_by_radius']['5'],'coverage_main_pickup5km':coverage['pickup_5km_baseline'],'pilot_checks':selected},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

"""Link explicit 2025 school territories without collapsing branches to parents.

The literal transcription below is from the published annex to Pitersky
district order 07.04.2025 No34-r. It is an administrative admission geography,
not a measurement of journeys. A unique name with a conflicting settlement
kind remains a candidate and does not become an accepted link.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

SOURCE_ID = 'PITERSKY_SCHOOL_TERRITORIES_2025_34R'
SOURCE_URL = 'https://piterka-r64.gosweb.gosuslugi.ru/netcat_files/46/469/34r.docx'
SOURCE_DATE = '2025-04-07'

# annex_row, physical-campus place, legal-parent place, literal (kind, place)
ANNEX = [
    (1, 'Питерка', 'Питерка', [('село','Питерка'),('хутор','Доронкин')]),
    (2, 'Мироновка', 'Мироновка', [('село','Моршанка'),('село','Мироновка')]),
    (3, 'Агафоновка', 'Питерка', [('село','Агафоновка'),('посёлок','Первопитерский'),('железнодорожный объект','Питерка'),('хутор','Решетников'),('хутор','Светский')]),
    (4, 'Нариманово', 'Питерка', [('посёлок','Нариманово')]),
    (5, 'Малый Узень', 'Питерка', [('село','Малый Узень'),('железнодорожный объект','Малоузенск'),('хутор','Черемушки')]),
    (6, 'Запрудное', 'Питерка', [('село','Запрудное'),('посёлок','Ясновидовка'),('посёлок','Подольский'),('железнодорожный объект','Глубинный')]),
    (7, 'Нива', 'Питерка', [('посёлок','Нива'),('посёлок','Приозерный'),('хутор','Малый Славин'),('посёлок','Руновский'),('хутор','Крестьянка'),('хутор','Цепков'),('хутор','Широков'),('хутор','Попов'),('хутор','Антипенков'),('хутор','Желтый'),('хутор','Шлягин'),('хутор','Печнихин'),('хутор','Земцов')]),
    (8, 'Новореченский', 'Мироновка', [('посёлок','Новореченский'),('посёлок','Зеленый Луг')]),
    (9, 'Новотулка', 'Питерка', [('село','Новотулка'),('посёлок','Привольный'),('посёлок','Новый Путь'),('хутор','Верный')]),
    (10, 'Трудовик', 'Питерка', [('посёлок','Трудовик')]),
    (11, 'Алексашкино', 'Питерка', [('село','Алексашкино'),('посёлок','Опытная станция')]),
    (12, 'Козловка', 'Питерка', [('село','Козловка')]),
]


def normalized(value):
    return ' '.join(str(value).casefold().replace('ё','е').split())


def find_literal(roster, name, kind=None):
    matches = roster[roster['name'].map(normalized).eq(normalized(name))]
    if kind is not None:
        typed=matches[matches['settlement_type_2021'].map(normalized).eq(normalized(kind))]
        if len(typed)==1:
            row=typed.iloc[0]
            return row['source_record_id'], row['source_record_id'], 'explicit_district_name_and_compatible_kind'
    if len(matches) != 1:
        return None, None, 'missing_or_ambiguous_literal_place'
    row = matches.iloc[0]
    if kind is not None and normalized(row['settlement_type_2021']) != normalized(kind):
        return None, row['source_record_id'], 'literal_kind_conflict_held'
    return row['source_record_id'], row['source_record_id'], 'explicit_district_name_and_compatible_kind'


def build(roster):
    regional = roster[roster['district'].fillna('').str.contains('Питерский',case=False,regex=False)]
    if regional.empty:
        raise ValueError('No explicit Pitersky district census records')
    rows=[]
    for annex, campus, parent, places in ANNEX:
        campus_id, _, campus_status = find_literal(regional,campus)
        # The village is the legal-parent locality, not the railway station.
        parent_id, _, parent_status = find_literal(regional,parent,'село')
        if campus == 'Питерка':
            campus_id, _, campus_status = find_literal(regional,campus,'село')
        if not campus_id or not parent_id:
            raise ValueError('Explicit campus/parent locality not uniquely linked')
        for kind,name in places:
            origin,candidate,status=find_literal(regional,name,kind)
            selected=regional[regional.source_record_id.eq(candidate)]
            population=None if selected.empty else selected.iloc[0].population_2021
            rows.append({'source_id':SOURCE_ID,'source_url':SOURCE_URL,'source_date':SOURCE_DATE,
                'evidence_year':2025,'annex_row':annex,'origin_name_literal':name,
                'origin_kind_literal':kind,'origin_id':origin,'origin_candidate_id':candidate,
                'identity_status':status,'origin_population_2021':population,
                'campus_place_name':campus,'campus_id':campus_id,'legal_parent_place_name':parent,
                'legal_parent_np_id':parent_id,'service_family':'school',
                'relation_type':'documented_admission_catchment_not_observed_journey',
                'is_self_campus':origin == campus_id if origin else None,
                'observed_flow':False,'school_grades_verified':False,
                'temporal_status':'2025_annual_assignment_current_2026_operation_not_established'})
    result=pd.DataFrame(rows)
    if result[['origin_name_literal','origin_kind_literal']].duplicated().any():
        raise ValueError('Duplicate literal territorial assignment')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roster',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();d=build(pd.read_parquet(a.roster));a.output.parent.mkdir(parents=True,exist_ok=True)
    d.to_csv(a.output,index=False)
    print(json.dumps({'document_mentions':len(d),'accepted_links':int(d.origin_id.notna().sum()),
        'held_links':int(d.origin_id.isna().sum()),'physical_campuses':d.campus_id.nunique(),
        'legal_parent_places':d.legal_parent_np_id.nunique(),
        'external_accepted_links':int((d.origin_id.notna() & d.is_self_campus.eq(False)).sum()),
        'roster_sha256':hashlib.sha256(a.roster.read_bytes()).hexdigest()},ensure_ascii=False))


if __name__=='__main__':main()

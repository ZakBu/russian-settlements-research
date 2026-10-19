"""Rebuild validation ledgers from frozen, explicitly transcribed public sources.

These evidence records are excluded from calibration. All raw/capture hashes are
recomputed locally. No downloads, personal pupil lists or fitted thresholds.
"""
from pathlib import Path
import argparse, csv, hashlib, json, zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent

def write_csv(out,name,rows):
    fields=list(rows[0])
    with (out/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)

def main():
    a=argparse.ArgumentParser();a.add_argument('--out');args=a.parse_args()
    out=Path(args.out) if args.out else ROOT;out.mkdir(parents=True,exist_ok=True)
    sources=[
      dict(source_id='PLATINA_SELF_2024',url='https://platina.uralschool.ru/file/download?id=202',source_date='2024 reporting year; 2024/25 academic row',publisher='МБОУ Платинская ООШ',locator='PDF printed p7, lines261–294 in capture',raw_path='',capture='captures/validation_platina_tables.json',role='primary_provider_self_report',access='Web text available; raw HTTP503 twice'),
      dict(source_id='KONEVO_SELF_2024',url='https://soshkonevo.uralschool.ru/file/download?id=5376',source_date='2024 reporting year; signed website19.05.2025',publisher='МБОУ СОШ с.Конево',locator='II analytical part; Циклограмма звонков в2024; Отвоз обучающихся',raw_path='raw/konevo_self2024.zip',capture='captures/konevo_self2024.txt',role='primary_provider_self_report',access='HTTP200; payload is DOCX ZIP despite served application/zip'),
      dict(source_id='KONAKOVO_2019',url='https://konakovoregion.ru/ru/ob-otchete-glavy-konakovskogo-rayona-o-rezultatakh-svoey-deyatelnosti-i-administracii-0',source_date='2019 reporting year; published2020',publisher='Администрация Конаковского района',locator='Education section; website lines197–201',raw_path='raw/konakovo_2019.html',capture='captures/validation_search3.json',role='primary_municipal_retrospective_report',access='HTTP200'),
      dict(source_id='MALO_LIBRARY_HISTORY',url='https://www.uchaly-biblioteka.ru/modelnaya-selskaya-biblioteka-derevni-malokazakkulovo',source_date='publication date unknown; retrospective events1982,1989,2011,2017,2019',publisher='Центральная районная библиотека Учалинского района',locator='История библиотеки; paragraphs1,5,6',raw_path='raw/library_history.html',capture='captures/validation_sources3.json',role='primary_institutional_retrospective_history',access='HTTP200'),
      dict(source_id='KALUEVO_VILLAGE_SITE',url='https://kaluevo.wixsite.com/kaluevo/admissions',source_date='unknown; contains population asofMay2015',publisher='unidentified village-site author',locator='Как мы живём; last substantive paragraphs',raw_path='',capture='captures/validation_search5.json',role='secondary_unverified_authorship_not_accepted_primary',access='Search text; not accepted as independent primary proof'),
      dict(source_id='NEVYANSK_2018',url='https://www.duma-nevyansk.ru/acts/resheniya/resh-2019/045-24-04-2019/',source_date='2018 reporting year; act24.04.2019',publisher='Дума Невьянского городского округа',locator='Medical section, lines1697–1702 webcapture',raw_path='',capture='captures/validation_sources1.json',role='primary_municipal_retrospective_report',access='Webcapture; raw not downloaded'),
      dict(source_id='PLATINA_HISTORY_LEAD',url='https://pubsrv.uraic.ru/pressa/vremya/2013/vremya_6.pdf',source_date='17.01.2013; retrospective1960s',publisher='Время newspaper; source not fully obtained',locator='search lead only',raw_path='',capture='captures/validation_search2.json',role='lead_not_accepted_primary_full_text',access='RawHTTP503; webfetchunavailable; school history section has no substantive text'),
    ]
    for s in sources:
        for kind,field in [('raw','raw_path'),('capture','capture')]:
            p=ROOT/s[field] if s[field] else None
            s[kind+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest() if p and p.is_file() else ''
        s['retrieved_date_utc']='2026-10-19'
    write_csv(out,'source_ledger.csv',sources)
    def row(i,origin,dest,kind,status,sid,period,measure,lim):
        return dict(check_id=i,origin=origin,destination=dest,function_group='education',evidence_kind=kind,validation_status=status,source_id=sid,period=period,reported_measure=measure,limitation=lim,used_for_calibration=False)
    checks=[
      row('VAL01','Новая Тура','Платина','provider_report_external_transfer_origin_unspecified','specific_edge_unconfirmed','PLATINA_SELF_2024','2021/22–2024/25','11→12→19→22 school pupils; provider attributes growth to reassignment and pupils from city schools','Новая Тура не названа; всех новых учеников нельзя приписать деревне. Не число поездок.'),
      row('VAL02','Верх-Ис','Косья','no_independent_usage_record_found','unknown','', 'search19.10.2026','','Отсутствие найденного документа не доказывает отсутствия пользования.'),
      row('VAL03','Лабазка','Косья','no_independent_usage_record_found','unknown','', 'search19.10.2026','','Отсутствие найденного документа не доказывает отсутствия пользования.'),
      row('VAL04','Киприно','Конёво','reported_transport_organisation_schedule','transport_offer_not_observed_flow','KONEVO_SELF_2024','2024','Return departure14:30','Распорядок школы сообщает развоз; нет числа пассажиров и подтверждения каждого исполнения рейса.'),
      row('VAL05','Осиновка','Конёво','reported_transport_organisation_schedule','transport_offer_not_observed_flow','KONEVO_SELF_2024','2024','Return departure14:50','Направление origin→provider восстановлено по обратному школьному развозу; регулярность/пассажиры не измерены.'),
      row('VAL06','not_disaggregated_Konakovo_district','multiple_schools','reported_aggregate_transport_use','aggregate_usage_witness_no_od','KONAKOVO_2019','2019','548 children;39 routes;16 buses assigned14 institutions','Число детей не равно числу поездок; происхождения и школы по отдельности не раскрыты; не приписывать548 одномуцентру.'),
      row('VAL07','origins_unknown','гимназия№5 Конаково / Ручьи','reported_transport_nonoperation','negative_operational_witness_not_no_education','KONAKOVO_2019','2019','Transport not operating because of absent drivers','Нет подтверждения прекращения обучения; два места в одной фразе, не конструировать OD-связи.'),
      row('VAL08','Калуево','Малоказаккулово','unverified_village_site_usage_claim','secondary_only_not_accepted_primary','KALUEVO_VILLAGE_SITE','unknown','Children attend school/kindergarten in neighbouring village; bus provided','Авторство и дата неизвестны; число пользователей и фактические рейсы неизвестны.'),
      dict(row('VAL09','remote_villages_unspecified','Невьянская ЦРБ / mobile_units','reported_medical_transport_and_exams','aggregate_usage_witness_no_od','NEVYANSK_2018','2018','1500 examined by mobile fluorography; transport of remote villagers reported','Не разделены населённые пункты, направления и учреждения;1500 не число подвозимых кЦРБ.'),function_group='health'),
    ]
    write_csv(out,'actual_service_checks.csv',checks)
    counts=[]
    for year,school,pre,primary,lower,total in [('2021-2022',11,4,3,8,15),('2022-2023',12,4,5,7,16),('2023-2024',19,10,7,12,29),('2024-2025',22,9,9,13,31)]:
        counts.append(dict(provider='Платина',academic_year=year,school_pupils=school,preschool_children=pre,primary_pupils=primary,lower_secondary_pupils=lower,total_including_preschool=total,source_id='PLATINA_SELF_2024',scope='reported_institution_total_not_external_pupils',source_internal_discrepancy='Narrative on same page says18day+1home for2024; table retained as academic-year count, not silently reconciled'))
    write_csv(out,'platina_reported_contingent.csv',counts)
    events=[dict(event_id='LIB1982',function_group='library',event_year=1982,event_kind='physical_relocation_documentary',origin='Галиахмерово',destination='Калуево',source_id='MALO_LIBRARY_HISTORY',evidence_kind='institutional_retrospective_history',usage_flow_observed=False,limitation='Смена места учреждения; переориентация читателей и дата закрытия прежнего обслуживания не измерены'),dict(event_id='LIB1989',function_group='library',event_year=1989,event_kind='physical_relocation_documentary',origin='Калуево',destination='Малоказаккулово',source_id='MALO_LIBRARY_HISTORY',evidence_kind='institutional_retrospective_history',usage_flow_observed=False,limitation='Ретроспективное сообщение учреждения; не современная запись регистра и не поток читателей')]
    write_csv(out,'library_physical_relocations.csv',events)
    # Verify source transcription against raw original, not search snippet.
    z=zipfile.ZipFile(ROOT/'raw/konevo_self2024.zip');doc=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    text='\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in doc.findall('.//w:p',ns))
    (out/'konevo_self2024_extracted.txt').write_text(text)
    tests={'no_calibration_all_records':all(x['used_for_calibration'] is False for x in checks),'raw_docx_signature':z.testzip() is None,'konevo_return_schedule_literal':all(s in text for s in ['Отвоз обучающихся','Киприно','14.30','Осиновка','14.50']),'school_pupil_level_sums':all(x['primary_pupils']+x['lower_secondary_pupils']==x['school_pupils'] for x in counts),'total_including_preschool_balances':all(x['school_pupils']+x['preschool_children']==x['total_including_preschool'] for x in counts),'unique_checks':len({x['check_id'] for x in checks})==len(checks),'unknown_not_false_negative':all(x['validation_status']=='unknown' for x in checks if x['check_id'] in ['VAL02','VAL03']),'library_not_observed_flow':all(x['usage_flow_observed'] is False for x in events),'specific_new_tura_not_claimed_observed':checks[0]['validation_status']=='specific_edge_unconfirmed','raw_hashes_separate_captures':all(s['raw_sha256']!=s['capture_sha256'] for s in sources if s['raw_sha256'])}
    audit=dict(status='PASS' if all(tests.values()) else 'FAIL',checks=tests,passed=sum(tests.values()),total=len(tests),records=len(checks),named_school_od_with_measured_passenger_count=0,independence='Validator authored none of model formula/input school attachment transcriptions. Sources discovered after model freeze; excluded from calibration. This is post-development external triangulation, not a blinded holdout.',out_of_scope='No employment commute inferred from school bus.')
    (out/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    manifest={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='MANIFEST.json'}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()

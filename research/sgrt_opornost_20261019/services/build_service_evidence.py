"""Rebuild curated official catchment evidence; no radius, flow inference or geocoding.

Each named origin must occur in the saved source text. Browser-extracted captures are
hashed as text, never misrepresented as raw HTML/PDF byte hashes.
"""
from pathlib import Path
import csv, hashlib, json

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "SV2025": dict(region="Свердловская область", municipality="Нижнетуринский муниципальный округ", date="2025-03-05", capture="sverdlovsk_2025.web.txt", url="https://education-ntura.ru/2025/03/12/приём-в-первый-класс-2025-2026-учебного-года/", version="Приказ №70 от 05.03.2025; публикация 12.03.2025", level="general_education_admission_2025_2026", kind="statutory_school_catchment", complete="complete_official_table_for_admission; only selected external groups extracted", evidence="E2_normative_service_link", date_scope="2025/2026 учебный год; не исторический 2010"),
    "TV2021": dict(region="Тверская область", municipality="Конаковский район", date="2021-01-27", capture="tver_2021.web.txt", url="https://konakovoregion.ru/ru/o-zakreplenii-obrazovatelnykh-uchrezhdeniy-za-territoriyami-municipalnogo-obrazovaniya-konakovskiy", version="Постановление №37 от 27.01.2021, приложение", level="general_education", kind="statutory_school_catchment", complete="complete_official_appendix_displayed; three village school groups extracted", evidence="E2_normative_service_link", date_scope="Акт 2021 года; действие на 2026 год не установлено"),
    "NV2026": dict(region="Свердловская область", municipality="Невьянский муниципальный округ", date="2026-02-27", capture="nevyansk_pdf_tail.web.txt", url="https://soshkonevo.uralschool.ru/file/download?id=5628", version="Приказ №64-Д от 27.02.2026; приложения 1 и 2; PDF страницы 12 и 14 (1-based)", level="primary_basic_secondary_general", kind="statutory_school_catchment", complete="complete_rural_tables_appendix1_and2; self catchments kept separately; unnamed military unit excluded", evidence="E2_normative_service_link", date_scope="Вступает в силу 01.04.2026; не исторический 2010"),
    "BA_MED": dict(region="Республика Башкортостан", municipality="Учалинский район", date="", capture="bashkortostan_medical.web.txt", url="https://xn--90ad1cm.xn--p1ai/ob-uchrezhdenii/bylo-stalo", version="Официальная страница Учалинской ЦРБ «Было-стало», дата публикации не указана", level="feldsher_obstetric_primary_care", kind="provider_reported_service_catchment", complete="two_FAP_cases_only_not_complete_district_registry", evidence="E2_provider_statement_service_link", date_scope="Дата публикации неизвестна; retrieved 2026-10-19 не равно дате наблюдения")
}

# Only external named origins. Physical provider locations are inferred from the
# institution/site names; street address and coordinates require separate linkage.
GROUPS = [
    ("SV2025", "Нижняя Тура", "МАОУ СОШ №7 имени М.Г. Мансурова", "Большая Именная|Малая Именная|Большая Выя|Малая Выя", "table_row_SOSH7", 50, "planned_first_grade_places"),
    ("SV2025", "Косья", "МБОУ Косьинская СОШ", "Борисовский|Верх-Ис|Граневое|Лабазка|Покап", "table_row_Kosya", 5, "planned_first_grade_places"),
    ("SV2025", "Сигнальный", "МБОУ Сигнальненская СОШ", "Ермаковский|Черничный", "table_row_Signalny", 15, "planned_first_grade_places"),
    ("SV2025", "Платина", "МБОУ Платинская ООШ", "Новая Тура", "table_row_Platina", 5, "planned_first_grade_places"),
    ("TV2021", "Козлово", "МБОУ СОШ поселка Козлово", "Бережки|Бушмино|Гаврилково|Гришкино|Дмитрово|Долгая Пожня|Дорино|Заозерье|Зеленцино|Ивановское|Клещево|Койдиново|Курьяново|Павельцево|Синцово|Текстильщик|Узкол|Юрьево", "appendix_Kozlovo", None, "unknown"),
    ("TV2021", "Селихово", "МБОУ СОШ села Селихово", "Заречье|Сажино|Сорокопенино|Дубровки|Марьино|Филимоново|Поречье|Чублово", "appendix_Selikhovo", None, "unknown"),
    ("TV2021", "Ручьи", "МБОУ СОШ деревни Ручьи", "Сынково|Высоково|Данилово|Уразово|Крутец|Тарлаково|Трунино|Баранниково|Ботеново|Трубицино|Быстрово|Слободка|Рябиково|Захарово|Красинское|Дулово", "appendix_Ruchyi", None, "unknown"),
    ("NV2026", "Быньги", "МАОУ СОШ села Быньги", "Верхние Таволги|Нижние Таволги|Сербишино|Ударник|Аник", "PDF_p12_and_p14_rural_row2", None, "unknown"),
    ("NV2026", "Аятское", "МБОУ СОШ села Аятское", "Шайдуриха|Кунара|Плотина|Пьянково|Сосновка", "PDF_p12_and_p14_rural_row3", None, "unknown"),
    ("NV2026", "Конево", "МБОУ СОШ села Конево", "Гашени|Осиновка|Осиновский|Киприно|Корелы", "PDF_p12_and_p14_rural_row4", None, "unknown"),
    ("NV2026", "Калиново", "МБОУ СОШ поселка Калиново", "Невьянский Рыбзавод|Приозерный|Таватуй (Аятский сельсовет)", "PDF_p12_and_p14_rural_row5", None, "unknown"),
    ("NV2026", "Ребристый", "МБОУ СОШ поселка Ребристый", "Середовина|Федьковка", "PDF_p12_and_p14_rural_row7", None, "unknown"),
    ("NV2026", "Невьянск", "МАОУ СОШ №6 города Невьянска", "Вересковый|Шурала|Забельный", "PDF_p12_and_p14_rural_row8", None, "unknown"),
    ("BA_MED", "Малоказаккулово", "ФАП деревни Малоказаккулово", "Калуево", "provider_page_text_line102", 330, "total_attached_population_including_host_not_capacity"),
    ("BA_MED", "Батталово", "ФАП деревни Батталово", "Аслаево", "provider_page_text_line103", 233, "total_attached_population_including_host_not_capacity")
]

SELF_ONLY = [
    ("SV2025", "Ис", "МАОУ ИСОШ", "general_education_admission", "Only host settlement named in full 2025 admission table"),
    ("NV2026", "Цементный", "МАОУ СОШ поселка Цементный", "primary_basic_secondary_general", "Only host settlement in both full rural tables"),
    ("NV2026", "Аять", "МБОУ СОШ поселка Аять", "primary_basic_secondary_general", "Only host settlement in both full rural tables"),
    ("NV2026", "Таватуй", "МБОУ ООШ поселка Таватуй", "primary_basic_general_only", "Only host in appendix1; school absent from secondary-general appendix2; alternative secondary provider unknown")
]

PROVIDER_TYPES={"Нижняя Тура":"город","Косья":"посёлок","Сигнальный":"посёлок","Платина":"посёлок","Козлово":"посёлок","Селихово":"село","Ручьи":"деревня","Быньги":"село","Аятское":"село","Конево":"село","Калиново":"посёлок","Ребристый":"посёлок","Невьянск":"город","Малоказаккулово":"деревня","Батталово":"деревня"}
ORIGIN_TYPES={
    "Нижняя Тура":["деревня"]*4,"Косья":["посёлок"]*5,"Сигнальный":["посёлок"]*2,"Платина":["деревня"],
    "Козлово":["деревня"]*18,"Селихово":["деревня"]*8,"Ручьи":["деревня"]*15+["село"],
    "Быньги":["село","село","деревня","посёлок","посёлок"],"Аятское":["село","село","посёлок","деревня","деревня"],
    "Конево":["деревня","деревня","посёлок","село","село"],"Калиново":["посёлок"]*3,"Ребристый":["посёлок","село"],"Невьянск":["посёлок","село","посёлок"],"Малоказаккулово":["деревня"],"Батталово":["деревня"]
}

def dump_csv(name, rows):
    assert rows
    with (ROOT/name).open("w", encoding="utf-8", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

def main():
    rows=[]; providers=[]
    for source_id, center, school, origins, locator, amount, amount_meaning in GROUPS:
        source=SOURCES[source_id]
        capture=(ROOT/"captures"/source["capture"]).read_text(encoding="utf-8")
        assert center.casefold() in capture.casefold(), center
        provider_id=f"{source_id}:{center}:{school}"
        providers.append(dict(provider_id=provider_id,source_id=source_id,region=source["region"],municipality=source["municipality"],provider_settlement=center,provider_name=school,provider_location_evidence="institution_site_name_not_street_address",reported_quantity=amount,quantity_meaning=amount_meaning,full_capacity=None,latitude=None,longitude=None,origin_count=len(origins.split("|"))))
        assert len(ORIGIN_TYPES[center])==len(origins.split("|"))
        for origin,origin_type in zip(origins.split("|"),ORIGIN_TYPES[center]):
            assert origin.casefold() in capture.casefold(), origin
            assert origin != center
            rows.append(dict(edge_id=f"E{len(rows)+1:03d}",source_id=source_id,region=source["region"],municipality=source["municipality"],origin_name=origin,origin_type=origin_type,provider_settlement=center,provider_type=PROVIDER_TYPES[center],source_identity_note="literal пос./п. does not itself prove urban-type status; Таватуй (Аятский сельсовет) distinct from unsuffixed Таватуй until separately resolved",provider_id=provider_id,service_level=source["level"],link_kind=source["kind"],evidence_level=source["evidence"],source_document_date=source["date"],locator=locator,flow_count=None,actual_travel_observed=False,cohort_use="post_development_external_validation_not_blind_holdout",linkage_status="names_unlinked_to_population_panel",source_url=source["url"]))
    dump_csv("service_edges.csv",rows); dump_csv("providers.csv",providers)
    selfrows=[dict(source_id=s,settlement=c,provider=p,service_level=l,status="document_self_only_not_general_noncentrality",meaning=why) for s,c,p,l,why in SELF_ONLY]
    dump_csv("document_self_only.csv",selfrows)
    audits=[]
    for sid,s in SOURCES.items():
        b=(ROOT/"captures"/s["capture"]).read_bytes()
        audits.append(dict(source_id=sid,**s,retrieved_utc_date="2026-10-19",capture_sha256=hashlib.sha256(b).hexdigest(),capture_bytes=len(b),raw_source_bytes_sha256=None,raw_bytes_available=False,extracted_edges=sum(r["source_id"]==sid for r in rows),independent_flow_evidence=False))
    (ROOT/"source_audit.json").write_text(json.dumps(audits,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tests=[("external_edges_no_self_loops",all(r["origin_name"]!=r["provider_settlement"] for r in rows)),("unique_edge_ids",len({r["edge_id"] for r in rows})==len(rows)),("no_flow_claims",all(r["actual_travel_observed"] is False and r["flow_count"] is None for r in rows)),("no_radius_or_distance_input_fields",all(not any(k in r for k in ["radius","distance","population_maximum"]) for r in rows)),("all_origin_names_in_capture",all(r["origin_name"].casefold() in (ROOT/"captures"/SOURCES[r["source_id"]]["capture"]).read_text(encoding="utf-8").casefold() for r in rows)),("all_provider_names_have_origin_groups",all(p["origin_count"]>0 for p in providers)),("source_hashes_present",all(len(a["capture_sha256"])==64 for a in audits)),("raw_pdf_html_hashes_not_fabricated",all(a["raw_source_bytes_sha256"] is None for a in audits))]
    summary=dict(status="PASS" if all(ok for _,ok in tests) else "FAIL",n_external_edges=len(rows),n_providers=len(providers),n_regions=len({r["region"] for r in rows}),n_source_documents=len(SOURCES),n_document_self_only=len(selfrows),checks=[dict(name=n,pass_=ok) for n,ok in tests],note="Purposive pilot; no nationwide service coverage or observed OD trips; coordinates not assigned")
    (ROOT/"FINISHED.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__": main()

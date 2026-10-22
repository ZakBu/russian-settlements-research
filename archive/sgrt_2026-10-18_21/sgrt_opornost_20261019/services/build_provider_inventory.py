"""Exogenous school inventory from all provider rows of three official documents.

Catchment origins are never read for provider selection. Table-institution names
are inputs; origin-to-provider edges are a separately held-out outcome.
"""
from pathlib import Path
import csv, hashlib, json, re
ROOT=Path(__file__).resolve().parent

def main():
    rows=[]
    def add(source,region,municipality,center,name,level,locator):
        rows.append(dict(inventory_id=f"I{len(rows)+1:03d}",source_id=source,region=region,municipality=municipality,provider_settlement=center,provider_name=name,service_level=level,location_evidence="explicit_settlement_in_institution_name_or_official_table; street_coordinates_unverified",selection_basis="all_school_rows_in_document_not_external_catchment",has_school=True,school_count_at_node=None,capacity=None,longitude=None,latitude=None,locator=locator))
    s=(ROOT/"captures/sverdlovsk_2025.web.txt").read_text()
    matches=re.findall(r"^L\d+: (М[АБ]ОУ[^\n]+?)\s+\|",s,re.M)
    assert len(matches)==9,len(matches)
    for name in matches:
        center="Нижняя Тура"
        for pattern,c in [("ИСОШ","Ис"),("Косьинская","Косья"),("Сигнальненская","Сигнальный"),("Платинская","Платина")]:
            if pattern in name: center=c
        add("SV2025","Свердловская область","Нижнетуринский муниципальный округ",center,name,"general_education_admission_2025_2026","complete_table_all9schools")
    text=(ROOT/"captures/tver_2021.web.txt").read_text()
    matches=re.findall(r"^L\d+:\s+\|\s+(Муниципальное.+?)\s+\|",text,re.M)
    assert len(matches)==28,len(matches)
    ordered=["Конаково"]*8+["Радченко"]+["Редкино"]*3+["Изоплит"]+["Новозавидовский"]*2+["Козлово","Селихово","Ручьи","Вахонино","Завидово","Мокшино","Городня","Дмитрова Гора","Озерки","Первое Мая","Юрьево-Девичье","Старое Мелково","2-ое Моховое"]
    for name,center in zip(matches,ordered):
        assert center.casefold() in name.casefold(),(center,name)
        level="primary_general" if "начальная" in name else "primary_basic_general" if "основная" in name else "primary_basic_secondary_general"
        add("TV2021","Тверская область","Конаковский район",center,name,level,"complete_appendix_all28schools")
    # All city institutions and all rural institutions in the complete appendices.
    for n in range(1,7): add("NV2026","Свердловская область","Невьянский муниципальный округ","Невьянск",f"СОШ №{n} города Невьянска","primary_basic_secondary_general","PDF_appendix1_city_and_appendix2_city")
    add("NV2026","Свердловская область","Невьянский муниципальный округ","Невьянск","Вечерняя школа НМО","evening_general","PDF_p11_and_p13")
    for center,schoolkind in [("Цементный","СОШ"),("Быньги","СОШ"),("Аятское","СОШ"),("Конево","СОШ"),("Калиново","СОШ"),("Аять","СОШ"),("Ребристый","СОШ"),("Таватуй","ООШ")]:
        add("NV2026","Свердловская область","Невьянский муниципальный округ",center,f"{schoolkind} {center}","primary_basic_general" if schoolkind=="ООШ" else "primary_basic_secondary_general","PDF_p12_rural_all9rows; citySOSH6_not_duplicated")
    # 6 city + 1 evening + 8 rural = 15 unique organizations, not 16: one rural
    # catchment row names the city school №6 already counted above.
    assert len(rows)==52,len(rows)
    with (ROOT/"school_inventory.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    nodes={}
    for r in rows:
        key=r["region"],r["municipality"],r["provider_settlement"]
        if key not in nodes:nodes[key]=dict(region=key[0],municipality=key[1],name=key[2],school_inventory_records=0,has_school=True,source_ids=set(),latitude=None,longitude=None,selection_basis="all_institutions_in_official_school_document; NOT functional_center_certification",external_service_status="not_used_for_input_selection; edges_known_to_researchers_not_blind")
        nodes[key]["school_inventory_records"]+=1;nodes[key]["source_ids"].add(r["source_id"])
    for n in nodes.values():n["source_ids"]="|".join(sorted(n["source_ids"]))
    with (ROOT/"school_feature_nodes.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(next(iter(nodes.values()))));w.writeheader();w.writerows(nodes.values())
    summary=dict(status="PASS",inventory_records=len(rows),candidate_settlement_nodes=len(nodes),regions=len({r["region"] for r in rows}),source_counts={s:sum(r["source_id"]==s for r in rows) for s in ["SV2025","TV2021","NV2026"]},not_claimed="No service-center status from school presence alone; no capacity from planned first-grade admissions; no catchment edges used for selection",inventory_sha256=hashlib.sha256((ROOT/"school_inventory.csv").read_bytes()).hexdigest(),nodes_sha256=hashlib.sha256((ROOT/"school_feature_nodes.csv").read_bytes()).hexdigest())
    (ROOT/"INVENTORY_FINISHED.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":main()

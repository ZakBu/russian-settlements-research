"""Rebuild pilot medical objects, documented relations and paired tariff snapshots.

Standard library only. Reads frozen HTML/PDF-to-text; never invents flows from branches.
PDF text: pdftotext -layout captures/<stem>.pdf captures/<stem>.txt.
"""
from pathlib import Path
from html.parser import HTMLParser
import csv, re, json, hashlib, collections, datetime

ROOT=Path(__file__).resolve().parent
CAP=ROOT/'captures'
OBS='2026-10-19'

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,d):
        if d.strip():self.parts.append(d.strip())

class Tables(HTMLParser):
    def __init__(self): super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,t,a):
        if t=='tr':self.row=[]
        elif t in ('td','th') and self.row is not None:self.cell=[]
    def handle_endtag(self,t):
        if t in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        elif t=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None
    def handle_data(self,d):
        if self.cell is not None:self.cell.append(d)

def write(name, rows):
    cols=list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)

def main():
    meta=json.loads((CAP/'metadata.json').read_text())
    urls={r['source_id']:r['url'] for r in meta}
    texts={}
    for p in CAP.glob('*.html'):
        h=Text();h.feed(p.read_text(errors='replace'));texts[p.stem]='\n'.join(h.parts)
        p.with_suffix('.txt').write_text(texts[p.stem])
    objects=[];relations=[];snapshots=[]
    def add_object(oid,region,municipality,name,settlement,level,source,address='',date='',locator='',population='',staff='',status='listed_physical_site'):
        r=dict(object_id=oid,region=region,municipality=municipality,object_name=name,settlement=settlement,function_group='health',service_level=level,address=address,observed_date=OBS,source_document_date=date,source_id=source,source_url=urls[source],locator=locator,status=status,registered_population=population,medical_worker_present=staff,capacity='',latitude='',longitude='',limitation='No observed patient trips; published site list may be stale; capacity unknown unless separately sourced')
        objects.append(r);return r
    def add_relation(origin,dest,region,municipality,kind,level,source,date='',oid='',locator='',note=''):
        relations.append(dict(relation_id=f'MR{len(relations)+1:03}',origin=origin,destination=dest,origin_uid='',destination_uid='',region=region,municipality=municipality,function_group='health',service_level=level,relation_kind=kind,evidence_level='documented_provider_statement' if kind=='provider_reported_service' else 'documented_organizational' if kind=='institutional_subdivision' else 'documented_schedule_not_attendance',source_id=source,source_url=urls[source],source_document_date=date,observed_date=OBS,object_id=oid,locator=locator,note=note))
    # Full institutional address rows for the five rural FAP and the Is clinic.
    sv='Свердловская область';nt='Нижнетуринский муниципальный округ';nv='Невьянский муниципальный округ'
    nt_rows=[('Большая Именная','ФАП д. Большая Именная','ул. Юбилейная, д. 4'),('Новая Тура','ФАП д. Новая Тура','ул. Советская, д. 38'),('Косья','ФАП п. Косья','ул. Ленина, д. 38'),('Платина','ФАП п. Платина','ул. Зеленая, д. 18'),('Сигнальный','ФАП п. Сигнальный','ул. Клубная, д. 29а'),('Ис','Поликлиническое отделение № 2','ул. Советская, 9')]
    for i,(settle,name,addr) in enumerate(nt_rows):
        assert name in texts['nt_contacts'],name
        oid=f'NT_SITE_{i+1:02}'
        add_object(oid,sv,nt,name,settle,'FAP' if i<5 else 'outpatient_clinic','nt_contacts',addr,locator='Контакты: таблица Наименование и местонахождения; '+name)
        add_relation(settle,'Нижняя Тура',sv,nt,'institutional_subdivision','FAP' if i<5 else 'outpatient_clinic','nt_contacts',oid=oid,locator='Official hospital contacts table',note='Institutional organization only, no referral or patient flow implied')
    add_object('NT_HOSP',sv,nt,'Нижнетуринская ЦРБ','Нижняя Тура','district_hospital','nt_contacts','ул. 40-лет Октября, 22',locator='Местонахождение и почтовый адрес; clinical departments at address')
    # Kонаково: every named geographically separated unit on hospital homepage.
    tv='Тверская область';kon='Конаковский муниципальный округ'
    klist=[('Козлово','Козловская городская больница','local_hospital'),('Новозавидовский','Новозавидовская районная больница','local_hospital'),('Озерки','Озерецкая участковая больница','local_hospital'),('Первое Мая','Первомайская сельская участковая больница','local_hospital'),('Дмитрова Гора','Дмитрогорская сельская участковая больница','local_hospital'),('Вахонино','Вахонинская амбулатория','ambulatory'),('Мокшино','Мокшинская сельская амбулатория','ambulatory'),('Селихово','Селиховская сельская амбулатория','ambulatory'),('Старое Мелково','Мелковская амбулатория','ambulatory'),('Городня','Городенская амбулатория','ambulatory'),('Радченко','Радченковская амбулатория','ambulatory'),('Завидово','Завидовская сельская амбулатория','ambulatory'),('Юрьево-Девичье','Юрьево-Девичьеский ФАП','FAP'),('2-е Моховое','ФАП 2-ое Моховое','FAP'),('Ручьи','ФАП Ручьевской','FAP'),('Фёдоровское','ФАП Фёдоровский','FAP')]
    for i,(settle,name,level) in enumerate(klist):
        assert name in texts['kon_hospital'],name
        oid=f'KON_SITE_{i+1:02}'
        add_object(oid,tv,kon,name,settle,level,'kon_hospital',locator='Лечебно-профилактическая сеть / four FAP list; settlement cross-check municipal directory node/3507')
        add_relation(settle,'Конаково',tv,kon,'institutional_subdivision',level,'kon_hospital',oid=oid,locator='Homepage explicitly names separated subdivisions',note='Municipal directory supplies settlement identity; directory and homepage dates unknown, not a historic before/after')
    add_object('KON_HOSP',tv,kon,'Конаковская ЦРБ','Конаково','district_hospital','kon_hospital','ул. Энергетиков, 32',locator='Место нахождения; current inpatient/outpatient site')
    # Учалы: eight territorial units, all eight named in the structure listing.
    rb='Республика Башкортостан';uch='Учалинский район'
    ulist=[('Учалы','Учалинская УБ','local_hospital'),('Уральск','Уральская УБ','local_hospital'),('Миндяк','Миндякская УБ','local_hospital'),('Ильчигулово','Ильчигуловская УБ','local_hospital'),('Сафарово','Сафаровская ВА','ambulatory'),('Уразово','Уразовская ВА','ambulatory'),('Ахуново','Ахуновская ВА','ambulatory'),('Тунгатарово','Тунгатаровская ВА','ambulatory')]
    for i,(settle,name,level) in enumerate(ulist):
        assert name in texts['uch_structure'],name
        oid=f'UCH_SITE_{i+1:02}'
        add_object(oid,rb,uch,name,settle,level,'uch_structure',locator='Наименование структурных подразделений, items 9–16; settlement inferred from explicit territorial unit name; no street verified',status='physical_subdivision_named_settlement_inferred')
        # Same-name Учалы village versus city is deliberately disambiguated.
        objects[-1]['settlement_type']='село' if i==0 else ''
        add_relation(settle,'Учалы (город)',rb,uch,'institutional_subdivision',level,'uch_structure',oid=oid,locator='Structure list items 9–16',note='Territorial unit name gives candidate settlement; exact physical address not independently verified. Village Учалы differs from city Учалы')
    add_object('UCH_HOSP',rb,'город Учалы','Учалинская ЦРБ','Учалы','district_hospital','uch_structure','ул. Муртазина, 27',locator='Место нахождение учреждения; clinical and polyclinic structure')
    # Two explicit territorial service statements: own and external villages.
    for settle,external,pop,kids in [('Малоказаккулово','Калуево',330,52),('Батталово','Аслаево',233,50)]:
        assert f'{settle} и {external}' in texts['uch_before_after']
        oid='UCH_FAP_'+settle
        assert 'Опубликовано: 09.01.2025 12:15' in texts['uch_news']
        add_object(oid,rb,uch,'ФАП '+settle,settle,'FAP','uch_before_after',date='2025-01-09',locator='Было-стало; ФАП д.'+settle+'; publication date from identical article in uch_news.html',population=pop,status='provider_reported_operating_modular_FAP_replacing_old')
        for origin in [settle,external]:
            add_relation(origin,settle,rb,uch,'provider_reported_service','FAP','uch_before_after','2025-01-09',oid=oid,locator='Было-стало; serves two named villages; publication date in identical category article uch_news.html',note=f'Published total served population {pop}, children {kids}; population reference date unspecified, no measured trips; old building replaced, no inferred service birth')
    # Dated mobile clinic schedule. Preserve contradictory September heading.
    h=Tables();h.feed((CAP/'uch_announcements.html').read_text())
    planned=[]
    for row in h.rows:
        if len(row)==3 and row[0].strip().isdigit():
            date=re.sub(r'\s+','',row[1]);assert re.fullmatch(r'\d{2}\.10\.2026',date),date
            dt=datetime.datetime.strptime(date,'%d.%m.%Y').date().isoformat()
            for raw in row[2].split(','):
                settle=re.sub(r'^[дс]\.?\s*','',raw.strip())
                planned.append(dict(schedule_row=int(row[0]),scheduled_date=dt,destination=settle,source_id='uch_announcements',source_url=urls['uch_announcements'],heading_month='September',date_column_month='October',heading_date_conflict=True,implementation_status='not_observed',locator='schedule table row '+row[0]))
                add_relation('Учалы (мобильная служба)',settle,rb,uch,'scheduled_mobile_visit','mobile_FAP','uch_announcements',dt,locator='schedule table row '+row[0],note='Date is planned visit, NOT source publication or confirmed attendance. September heading conflicts with October row dates. Base assumed organizationally, not vehicle origin track')
    assert len({r['schedule_row'] for r in planned})==21
    # Full tariff rows in two original agreements, served population and staff.
    for year,stem,docdate in [(2025,'sv_tariff_2025_full','2024-12-24'),(2026,'sv_tariff_2026','2025-12-29')]:
        txt=(CAP/(stem+'.txt')).read_text();pages=txt.split('\f')
        for pno,page in enumerate(pages,1):
            for lineno,line in enumerate(page.splitlines(),1):
                if not re.search(r'^\s*(225|277)\s+Г[АБ]УЗ',line) or not re.search(r'\b111\d{3,4}\b',line):continue
                a=re.split(r'\s{2,}',line.strip());hospital=a[0];idx=next(j for j,x in enumerate(a) if re.fullmatch(r'111\d{3,4}',x));code=a[idx];tail=a[idx+1:]
                name=tail.pop(0) if tail[0] not in ('0','1') else 'ФАП д. Нижние Таволги (модульное здание)'
                region_flag,worker,staff,pop,women=tail[:5]
                pop=int(pop.replace(' ',''));women=int(women.replace(' ',''))
                settle=re.sub(r'^(?:Модульный )?ФАП\s*(?:д\.п\.|пос\.|д\.|п\.|с\.)?\s*','',name).strip()
                mobile='Мобильный' in name
                if mobile:settle=''
                elif 'Нижние Таволги' in name:settle='Нижние Таволги'
                elif 'д.п. Таватуй' in name:settle='Таватуй (дачный посёлок; identity unresolved)'
                record=dict(snapshot_id=f'{year}_{hospital}_{code}',organization_code=hospital,unit_code=code,unit_name=name,settlement=settle,region=sv,municipality=nv if hospital=='225' else nt,snapshot_date=f'{year}-01-01',source_document_date=docdate,registered_population=pop,registered_women_15_49=women,medical_worker_present=int(worker),fully_staffed=int(staff),mobile=mobile,source_id=stem,source_url=urls[stem],pdf_page=pno,pdf_line=lineno,source_row=line.strip(),evidence='tariff_registered_population_not_census_or_actual_visits',null_warning='Zero staff and zero attached population is not proven closure')
                snapshots.append(record)
                if year==2026:
                    add_object('SV_UNIT_'+hospital+'_'+code,sv,record['municipality'],name,settle,'mobile_FAP' if mobile else 'FAP',stem,date=docdate,locator=f'PDF page {pno}, line {lineno}, unit {code}',population=pop,staff=int(worker),status='tariff_listed_active_staff' if int(worker) else 'tariff_listed_zero_staff_not_proven_closed')
                    objects[-1]['unit_code']=code
                    if settle:add_relation(settle,'Невьянск' if hospital=='225' else 'Нижняя Тура',sv,record['municipality'],'institutional_subdivision','FAP',stem,f'{year}-01-01',oid='SV_UNIT_'+hospital+'_'+code,locator=f'PDF page {pno} unit {code}',note='Branch membership, not patient referral/flow. Distinct physical unit not automatically independent settlement center')
    assert collections.Counter(r['snapshot_date'] for r in snapshots)=={'2025-01-01':25,'2026-01-01':24}
    assert len({r['snapshot_id'] for r in snapshots})==49
    by={(r['snapshot_date'],r['organization_code'],r['unit_code']):r for r in snapshots}
    paired=[]
    keys=sorted({(r['organization_code'],r['unit_code']) for r in snapshots})
    for org,code in keys:
        before=by.get(('2025-01-01',org,code));after=by.get(('2026-01-01',org,code))
        if not after:status='absent_later_tariff_not_proven_closure'
        elif not before:status='newly_listed_not_proven_opening'
        elif before['medical_worker_present']==after['medical_worker_present']:status='same_staff_presence_flag'
        else:status='changed_staff_presence_flag'
        paired.append(dict(organization_code=org,unit_code=code,unit_name=(after or before)['unit_name'],settlement=(after or before)['settlement'],before_population=before['registered_population'] if before else '',after_population=after['registered_population'] if after else '',delta_population=after['registered_population']-before['registered_population'] if after and before else '',before_worker=before['medical_worker_present'] if before else '',after_worker=after['medical_worker_present'] if after else '',status=status,inference='No closed unit, transfer destination or catchment shift inferred from list absence or attached-count change'))
    sums=[]
    for org in ('225','277'):
        b=[r for r in snapshots if r['organization_code']==org and r['snapshot_date']=='2025-01-01'];a=[r for r in snapshots if r['organization_code']==org and r['snapshot_date']=='2026-01-01']
        pb=sum(r['registered_population'] for r in b);pa=sum(r['registered_population'] for r in a)
        sums.append(dict(organization_code=org,municipality=b[0]['municipality'],listed_units_2025=len(b),listed_units_2026=len(a),staffed_units_2025=sum(r['medical_worker_present'] for r in b),staffed_units_2026=sum(r['medical_worker_present'] for r in a),registered_population_2025=pb,registered_population_2026=pa,delta=pa-pb,percent=(pa/pb-1)*100))
    write('objects.csv',objects);write('relations.csv',relations);write('mobile_schedule.csv',planned);write('tariff_snapshots.csv',snapshots);write('tariff_changes.csv',paired);write('tariff_summary.csv',sums)
    # Duplicate sources are observations, not extra physical facilities.
    aliases=[dict(object_id='NT_SITE_01',same_physical_unit='SV_UNIT_277_111201',basis='same facility kind and settlement; website address only one side'),dict(object_id='NT_SITE_02',same_physical_unit='SV_UNIT_277_111204',basis='same facility kind and settlement'),dict(object_id='NT_SITE_03',same_physical_unit='SV_UNIT_277_111203',basis='same facility kind and settlement'),dict(object_id='NT_SITE_04',same_physical_unit='SV_UNIT_277_111209',basis='same settlement and current modular unit; old designation must not be added as extra function'),dict(object_id='NT_SITE_05',same_physical_unit='SV_UNIT_277_111206',basis='same facility kind and settlement')]
    write('object_aliases.csv',aliases)
    checks={'tariff_rows_49':len(snapshots)==49,'tariff_ids_unique':len({x['snapshot_id'] for x in snapshots})==49,'tariff_counts_nonnegative':all(x['registered_population']>=0 for x in snapshots),'tariff_women_not_above_total':all(x['registered_women_15_49']<=x['registered_population'] for x in snapshots),'schedule_rows_21':len({r['schedule_row'] for r in planned})==21,'schedule_month_conflict_retained':all(r['heading_date_conflict'] for r in planned),'two_FAP_four_memberships':sum(r['relation_kind']=='provider_reported_service' for r in relations)==4,'no_patient_flows_asserted':not any(r['relation_kind']=='observed_patient_flow' for r in relations),'objects_ids_unique':len(objects)==len({r['object_id'] for r in objects}),'relations_ids_unique':len(relations)==len({r['relation_id'] for r in relations}),'alias_pairs_known':all(a['object_id'] in {r['object_id'] for r in objects} and a['same_physical_unit'] in {r['object_id'] for r in objects} for a in aliases)}
    # Independently printed organization totals in the original tariff tables.
    for org,year,total in [('225',2025,5309),('225',2026,5223),('277',2025,1113),('277',2026,1063)]:
        checks[f'printed_tariff_total_{org}_{year}']=sum(r['registered_population'] for r in snapshots if r['organization_code']==org and r['snapshot_date']==f'{year}-01-01')==total
    audit=dict(status='PASS' if all(checks.values()) else 'FAIL',objects_observations=len(objects),object_alias_pairs=len(aliases),relations=len(relations),relation_kinds=dict(collections.Counter(x['relation_kind'] for x in relations)),tariff_summary=sums,paired_changes=dict(collections.Counter(x['status'] for x in paired)),schedule_rows=21,schedule_destination_events=len(planned),schedule_unique_destinations=len({r['destination'] for r in planned}),checks=checks,limits=['Object observation count includes source duplicates and zero-staff tariff units; not number of operating facilities','Institutional subdivision is organizational evidence, not destination of patient trips','No national functional SGRT delimitation','Undated page read 2026-10-19 is not a historical 2026 observation date'])
    (ROOT/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    manifest={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='MANIFEST.json' and '__pycache__' not in str(p)}
    (ROOT/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

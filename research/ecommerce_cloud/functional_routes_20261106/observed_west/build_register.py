"""Build small registers from retained search responses and selected primary HTML."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import csv, hashlib, json, re
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RAW = ROOT / 'work/ecommerce_functional_20261106/observed_west'
COHORT = ROOT / 'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024/system/centre_system_demography.csv'
REGIONS = ['тверская','новгородская','псковская','вологодская']
EXCLUDED = {'Новоржев':'population2002_below5000', 'Лихославль':'absent_fixed_centre_table','Западная Двина':'absent_fixed_centre_table','Сольцы':'absent_fixed_centre_table'}

def dump(name, rows):
    with (OUT/name).open('w', newline='') as f:
        w=csv.DictWriter(f,lineterminator='\n',fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

responses=json.loads((RAW/'search_responses.json').read_text())
df=pd.read_csv(COHORT)
old_names=set()
for path in (ROOT/'research/ecommerce_cloud/observed_operations_20261104').glob('systematic_review_search*.csv'):
    old=pd.read_csv(path)
    old_names.update(old['centre' if 'centre' in old else 'city'].str.replace('ё','е'))
centres=[];lookup={}
for name in dict.fromkeys(x['centre'] for x in responses):
    matches=df[(df.name_2021==name)&df.region_2021.isin(REGIONS)]
    assert len(matches)<=1,name
    r=matches.iloc[0] if len(matches) else None
    row={'centre':name,'region':None if r is None else r.region_2021,'population_2002':None if r is None else int(r.population_2002),'medium_primary2002':None if r is None else bool(r.medium_primary2002),'source_record_id_2021':None if r is None else r.source_record_id_2021,'in_fixed_analysis':name not in EXCLUDED,'exclusion_reason':EXCLUDED.get(name,''),'in_prior_24_centre_search':name.replace('ё','е') in old_names}
    if row['in_fixed_analysis']:
        assert row['medium_primary2002'] is True,name
        assert not row['in_prior_24_centre_search'],name
    centres.append(row);lookup[name]=row
assert sum(x['in_fixed_analysis'] for x in centres)==24
assert len(responses)==80
logs=[]
for r in sorted(responses,key=lambda x:x['i']):
    text='\n'.join(x.get('text','') for x in r['result'].get('content',[]) if x.get('type')=='text')
    urls=list(dict.fromkeys(re.findall(r'https?://[^\s)]+',text)))
    name=r['centre'];meta=lookup[name]
    status='no_eligible_change_case_in_screened_search'
    if r['i']==20:status='candidate_verified_named_prior_centre_Chudovo'
    if r['i']==75:status='retained_need_actual_failed_trip_to_Opochka_not_before_after'
    if r['i']==16:status='primary_owner_interview_non_OD_closures_and_retail_to_wholesale'
    if r['i']==67:status='reject_Pestovo_homonym_and_old_nonmedium_destination'
    if name in EXCLUDED:status='preliminary_excluded_cohort_check'
    logs.append({'query_id':f'W{r["i"]+1:03d}','phase':'bounded_fixed24' if meta['in_fixed_analysis'] else 'preliminary_excluded','centre':name,'region':meta['region'],'population2002':meta['population_2002'],'medium_primary2002':meta['medium_primary2002'],'query_exact':r['q'],'brand':r['brand'],'returned_urls_json':json.dumps(urls,ensure_ascii=False),'screening_result':status,'raw_response_path':str((RAW/'search_responses.json').relative_to(ROOT)),'raw_response_index':r['i'],'scope':'returned snippets and URLs; selected primary cards opened; not all reviews examined'})
# Four probes ran in one web call while the environment was starting. They are
# recorded separately and do not inflate the bounded three-query-per-centre set.
for n in ['Бежецк','Нелидово','Торопец','Валдай']:
    logs.append({'query_id':f'PROBE{len(logs)-79:02d}','phase':'initial_public_probe_not_in_bounded_count','centre':n,'region':lookup[n]['region'],'population2002':lookup[n]['population_2002'],'medium_primary2002':lookup[n]['medium_primary2002'],'query_exact':f'"в {n}" "Ozon"','brand':'Ozon','returned_urls_json':'','screening_result':'merged_public_search_output_not_separately_retained; repeated_in_bounded_search','raw_response_path':'','raw_response_index':'','scope':'initial merged result; no independent evidence admitted from probe'})
fixed=[x for x in logs if x['phase']=='bounded_fixed24']
assert len(fixed)==72
assert all(sum(r['centre']==c for r in fixed)==3 for c in lookup if lookup[c]['in_fixed_analysis'])
dump('centre_screening.csv',centres);dump('query_log.csv',logs)

cases=[('spasskaya_polist_reviews.html','Спасская Полисть','Новгородская область,Чудовский район,деревня Спасская Полисть,Молодёжная улица,2','168953117131','Чудово','named_prior_centre_local_receipt','Чудово','Удобно заказывать и забирать, раньше ездили в Чудово!'),('opochka_retained.html','Опочка','Псковская область,Опочка,Коммунальная улица,18А','52149445834','Опочка','actual_failed_trip_to_centre_PVZ','Из деревни','Из деревни, выезжаем очень редко. Срок доставки и хранения заказов приходится подгадывать. А тут еще и не смогли попасть! Ждать не смогли, так как автобус поджимает.'),('opochka_seasonal.html','Опочка','Псковская область,Опочка,улица Гагарина,109','148499735613','Опочка','seasonal_visit_receipt_context_not_rural_dependency','Приезжаю в Опочку','Приезжаю в Опочку летом и радуюсь, что здесь можно забирать свои заказы комфортно')]
extracts=[]
for filename,place,address,oid,centre,kind,pattern,excerpt in cases:
    html=(RAW/filename).read_text()
    state=json.loads(re.search(r'<script type="application/json" class="state-view">(.*?)</script>',html,re.S).group(1))
    found=[]
    def walk(obj):
        if isinstance(obj,dict):
            if isinstance(obj.get('text'),str) and pattern in obj['text'] and obj.get('businessId')==oid:found.append(obj)
            for v in obj.values():walk(v)
        elif isinstance(obj,list):
            for v in obj:walk(v)
    walk(state);assert len(found)==1,(filename,len(found))
    review=found[0];meta=lookup[centre]
    extracts.append({'evidence_id':f'WEST{len(extracts)+1:02d}','evidence_kind':kind,'review_id':review['reviewId'],'updatedTime_utc':review['updatedTime'],'display_date_iso':review['updatedTime'][:10],'platform':'Ozon','current_pvz_locality':place,'current_card_address':address,'address_observed_date':'2026-11-06','org_id':oid,'named_centre':centre,'population2002_centre':meta['population_2002'],'centre_medium_primary2002':meta['medium_primary2002'],'centre_source_record_id_2021':meta['source_record_id_2021'],'origin_locality':'','origin_status':'unknown','excerpt':excerpt,'source_url':f'https://yandex.com/maps/org/ozon/{oid}/reviews/','date_is_opening':False,'successful_receipt_in_reported_episode':False if kind=='actual_failed_trip_to_centre_PVZ' else 'reported_receipt_practice_no_transaction_log','evidence_limits':'voluntary public report; no trip counts; current card address not independently dated to historic review'})
for row in extracts:
    row['discovery_frame']='bounded_fixed24'
# An external lead is kept apart from the 24 preselected centres and queries.
ruza=df[(df.name_2021=='Руза')&(df.region_2021=='московская')]
assert len(ruza)==1 and bool(ruza.iloc[0].medium_primary2002)
ruza=ruza.iloc[0]
for review in json.loads((RAW/'oreshki_ruza_selected.json').read_text()):
    if 'за заказами' in review['text']:
        excerpt='теперь не нужно специально ездить в Рузу за заказами'
        kind='named_prior_centre_order_receipt_external_lead'
    else:
        excerpt='не надо ездить в Рузу за подарками для девочек'
        kind='named_prior_centre_gifts_external_lead_old_channel_unknown'
    assert excerpt in review['text']
    displayed=datetime.fromisoformat(review['updatedTime'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
    extracts.append({'evidence_id':f'WEST{len(extracts)+1:02d}','evidence_kind':kind,'review_id':review['reviewId'],'updatedTime_utc':review['updatedTime'],'display_date_iso':displayed,'platform':'Wildberries','current_pvz_locality':'Орешки','current_card_address':'Московская область,Рузский муниципальный округ,деревня Орешки,4/1','address_observed_date':'2026-11-06','org_id':'148433571902','named_centre':'Руза','population2002_centre':int(ruza.population_2002),'centre_medium_primary2002':bool(ruza.medium_primary2002),'centre_source_record_id_2021':ruza.source_record_id_2021,'origin_locality':'','origin_status':'unknown','excerpt':excerpt,'source_url':'https://yandex.com/maps/org/wildberries/148433571902/reviews/','date_is_opening':False,'successful_receipt_in_reported_episode':'reported_receipt_practice_no_transaction_log','evidence_limits':'external lead; two reviews of one PVZ,not two territories; date21.12.2024 belongs to another review without named Ruza','discovery_frame':'external_lead_not_fixed24'})
dump('primary_extracts.csv',extracts)
# A discovered lateral pickup switch is useful context but neither its old
# centre nor its current locality is the medium city Pestovo in Novgorod.
lat=json.loads((RAW/'pestovo_homonym_selected.json').read_text())
assert len(lat)==1
lateral={'evidence_id':'WEST_LATERAL01','review_id':lat[0]['reviewId'],'updatedTime_utc':lat[0]['updatedTime'],'source_url':'https://yandex.com/maps/org/ozon/79098315591/reviews/','current_card_address':'Московская область,городской округ Домодедово,СНТ Пестово-Пестово,1','old_destination_literal':'Мотякино','old_destination_identity':'unresolved;not_assigned_medium_status','origin_locality':'','excerpt':'Долгое время ездили с супругом на озон в Мотякино и как хорошо, что узнали, что есть поблизости еще один Озон в Пестово!','in_fixed24_denominator':False,'interpretation':'named lateral pickup switch;old place not resolved;not Novgorod Pestovo bypass'}
dump('adjacent_observations.csv',[lateral])
manifest=[]
for p in sorted(RAW.iterdir()):
    if p.is_file():manifest.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
source={'access_date':'2026-11-06','bounded_centres':24,'bounded_queries':72,'excluded_centres':4,'excluded_queries':8,'initial_merged_probes':4,'all_logged_queries':84,'new_named_former_medium_territories_in_bounded_search':1,'new_named_former_medium_territories_external_lead':1,'retained_need_failed_trip_territories':1,'probability_sample':False,'all_reviews_read':False,'cohort_file':str(COHORT.relative_to(ROOT)),'cohort_sha256':sha(COHORT),'primary_extracts':extracts,'adjacent_lateral_observation':lateral,'interview':{'title':'Как создать квиз, мурал и сеть пунктов выдачи заказов в Удомле. И при чем тут Водяной?','publisher':'Луч','publication_date':'2025-12-05','url':'https://goroda.media/kak-sozdat-kviz-mural-i-set-punktov-vydachi-zakazov-v-udomle-i-pri-chem-tut-vodyanoy/amp/','read_scope':'sections Первый бизнес and Как открыть пункт выдачи в атомном городе; publication date','evidence_kind':'first_person_owner_report_not_OD','findings':'own retail shop closed summer2025/wholesale continued;some unnamed rural and urban PVZ closed2025 as unprofitable; first point December2017','no_inference':'no observed reverse trip flow from rural closures; no causal retail effect estimate'},'raw_manifest':manifest,'privacy':'Published extracts omit reviewer names,profiles and unrelated personal histories; raw pages kept only in ignored work.'}
(OUT/'sources.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
print({'cohort_centres':24,'bounded_queries':len(fixed),'query_log_rows':len(logs),'primary_extracts':len(extracts)})

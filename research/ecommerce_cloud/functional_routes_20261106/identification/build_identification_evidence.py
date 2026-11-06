#!/usr/bin/env python3
"""Extract dated observations and their limits; no causal effect calculation.

Full third-party HTML/reviews stay in ignored work. Published small tables omit
reviewer names and full review texts. Latest page state is not a historical panel.
"""
import csv,hashlib,html,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
RAW=ROOT/'work/ecommerce_functional_routes_20261106/identification'
def save_csv(name,rows):
 with (HERE/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for row in rows for k in row)),lineterminator='\n');w.writeheader();w.writerows(rows)
def walk(x):
 if isinstance(x,dict):
  yield x
  for y in x.values():yield from walk(y)
 elif isinstance(x,list):
  for y in x:yield from walk(y)
def telegram_posts(s,channel):
 result={}
 for seg in re.split(r'(?=<div class="tgme_widget_message_wrap)',s):
  mid=re.search('data-post="'+re.escape(channel)+r'/(\d+)"',seg)
  text=re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>',seg,re.S)
  dt=re.search(r'<time[^>]+datetime="([^"]+)"',seg)
  if mid and text:
   result[mid.group(1)]={'datetime':dt.group(1) if dt else '', 'text':re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',text.group(1)))).strip()}
 return result
def main():
 source_rows=[]
 for name in ['initial_acquisition.json','further_acquisition.json']:
  source_rows+=json.loads((RAW/name).read_text())
 pinned=[r for r in source_rows if 'sha256'in r]
 for r in pinned:
  assert hashlib.sha256((ROOT/r['raw_path']).read_bytes()).hexdigest()==r['sha256']
 body=(RAW/'dubki_reviews.html').read_text();m=re.search(r'<script[^>]*class="state-view"[^>]*>(.*?)</script>',body,re.S);assert m
 state=json.loads(m.group(1));reviews={r['reviewId']:r for r in walk(state) if r.get('businessId')=='214328411004' and 'reviewId'in r and 'text'in r}
 cards=[r for r in walk(state) if str(r.get('id'))=='214328411004' and 'fullAddress'in r];assert len(cards)==1
 card=cards[0];assert 'Dubki' in card['fullAddress'] and 'Sovetskaya' in card['fullAddress']
 selected=[('oLFWvXySkgkK4EDwwuQPskb9kvmiKc9','2025-05-23','received_report_of_platform_reassigning_PVZ','Owner attribution is hearsay; reviewer reports changed assigned pickup, not completed journey to a named new place.',None,None),('XN6_BfP-kzFs1rZrZqxP8stJAaAtZtcGJ','2025-05-26','reported_actual_detour_after_orders_rerouted','Refers to prior review and same owner; not independent cause corroboration. New pickup address and frequency unknown.',15,20),('55Iad_unN5yTXwJo67txbBnAXUn8ism_7','2025-06-25','intention_not_to_use_platform_due_to_farther_alternative','Future/intended non-use is not observed abandonment. M.Kutuzova is an unlocated street/point, not identified medium centre.',None,None)]
 rows=[]
 for rid,day,outcome,limit,lo,hi in selected:
  r=reviews[rid];assert r['updatedTime'].startswith(day)
  rows.append({'org_id':'214328411004','review_id':rid,'review_updated_time':r['updatedTime'],'historical_date_status':'text_explicit_date_and_metadata' if day=='2025-05-23' else 'updatedTime_not_initial_creation_date','card_current_address':card['fullAddress'],'card_current_status':card.get('status',''),'outcome':outcome,'added_detour_minutes_lower':lo,'added_detour_minutes_upper':hi,'minutes_denominator':'one reviewer reported detour; no trip diary or sample denominator' if lo else '', 'new_destination_identified':False,'middle_centre_return_observed':False,'limit':limit,'primary_url':'https://yandex.com/maps/org/ozon/214328411004/reviews/'})
 save_csv('dubki_reverse_change.csv',rows)
 p=telegram_posts((RAW/'wb_partners_jan2024.html').read_text(),'wbsellerofficial')
 q=telegram_posts((RAW/'wb_shushary.html').read_text(),'wildberriesofficialcustomer')
 assert p['2006']['datetime'].startswith('2024-01-13') and 'Пскове, Туле и Москве' in p['2006']['text']
 assert p['2017']['datetime'].startswith('2024-01-14') and 'перенесли автопарк' in p['2017']['text'] and 'напрямую' in p['2017']['text']
 assert q['175']['datetime'].startswith('2024-01-16') and 'были перезаказаны' in q['175']['text']
 events=[
 {'source_id':'wb_partner_2006','reported_at':p['2006']['datetime'],'place':'Уткина Заводь, Санкт-Петербург','observation':'temporary FBS intake suspension due to overload from18:00','evidence_stage':'operator_report_of_intake_rule','alternative':'Псков; Тула; Москва','alternative_stage':'recommended_dropoff_not_confirmed_completed_delivery','unit':'logistics intake rule','actual_routed_volume':None},
 {'source_id':'wb_partner_2017','reported_at':p['2017']['datetime'],'place':'Шушары → Уткина Заводь','observation':'fleet moved to Utkinа Zavod; cargo previously passing via Saint Petersburg now directly to other cities','evidence_stage':'operator_report_of_completed_fleet_move_and_current_flow_change','alternative':'other cities not individually named','alternative_stage':'current_operator_report_not_order-level_records','unit':'reported route configuration','actual_routed_volume':None},
 {'source_id':'wb_customer_175','reported_at':q['175']['datetime'],'place':'Шушары; other warehouses','observation':'available replacement goods reordered from other warehouses','evidence_stage':'reorder_completed_but_delivery_still_future','alternative':'other warehouses not individually named','alternative_stage':'do_not_code_as_delivered','unit':'qualitative order status','actual_routed_volume':None},
 {'source_id':'ozon_novaya_riga_20220804','reported_at':'2022-08-04','place':'Новая Рига','observation':'many customer orders already cancelled and refunded','evidence_stage':'operator_report_of_completed_cancellation','alternative':'refund rather than delivered substitute','alternative_stage':'not_rerouted_customer_or_completed_shipment','unit':'qualitative order status','actual_routed_volume':None},
 {'source_id':'ozon_novaya_riga_20220804','reported_at':'2022-08-04','place':'crossdock consignments to Новая Рига on2022-08-03','observation':'goods to be placed at nearby warehouses; sellers to be notified later','evidence_stage':'announced_future_rerouting','alternative':'nearby warehouses not individually named in primary post','alternative_stage':'do_not_code_as_completed_arrival','unit':'qualitative future handling','actual_routed_volume':None}]
 save_csv('observed_disruption_events.csv',events)
 flows=[]
 for origin,dest,comp,factor in [('Регионы России','Москва','=',1.77),('Регионы России','Санкт-Петербург','=',1.44),('Москва','Регионы России','=',1.44),('Санкт-Петербург','Регионы России','=',1.74),('Регионы России','Москва и Санкт-Петербург вместе','=',1.60),('Хабаровский край','Москва','>',15),('Ярославская область','Москва','=',14),('Саратовская область','Москва','=',8),('Ярославская область','Санкт-Петербург','=',10),('Оренбургская область','Санкт-Петербург','=',7),('Тюменская область','Санкт-Петербург','=',5)]:
  flows.append({'source_id':'ozon_regional_flows20251127','period_current':'2025-10','period_comparison':'2024-10','origin':origin,'destination':dest,'reported_growth_factor_comparator':comp,'reported_growth_factor':factor,'normalised_2024_index':100,'normalised_2025_index':100*factor,'reported_measure':'goods supplies / cargo flow; physical unit not specified in release','absolute_volume_public':False,'complete_OD_matrix_public':False,'geo_semantics':'logistics-region directions; not established manufacturer residence or household residence','sample_type':'selected published directions, not representative route panel'})
 save_csv('regional_operator_flows.csv',flows)
 # The provider-rendered source response is a distinct retained artifact, not
 # an invented SHA of unavailable original HTML.
 web=RAW/'ozon_primary_webreader.json';assert web.exists();js=json.loads(web.read_text());joined='\n'.join(r.get('text','') for r in js.get('content',[]))
 assert '27.11.25' in joined and '12.02.26' in joined and '04.08.2022' in joined
 sources=[]
 for r in pinned:sources.append(dict(r,artifact_kind='original_http_html',historical_capture=False))
 shared={'retrieved_date':'2026-11-06','artifact_kind':'web_reader_provider_response_JSON_not_original_HTML','raw_path':str(web.relative_to(ROOT)),'sha256':hashlib.sha256(web.read_bytes()).hexdigest(),'original_http_download':'failed_redirect_loop; original HTML SHA unavailable','historical_capture':False}
 for sid,date,url in [('ozon_regional_flows20251127','2025-11-27','https://corp.ozon.ru/ru/sth/kakie-rossiyskie-regiony-lidiruyut-po-postavkam-tovarov-v-stolitsu-6be03e5a'),('ozon_longest_route20260212','2026-02-12','https://corp.ozon.ru/ru/sth/14-tysyach-kilometrov-ozon-raskryl-samyy-dlinnyy-logisticheskiy-marshrut-2025-goda-406408d0'),('ozon_novaya_riga_20220804','2022-08-04','https://seller.ozon.ru/media/news/novaya-riga-o-pozhare-na-sklade-i-ego-posledstviyah/')]:sources.append(dict(shared,source_id=sid,publication_date=date,url=url,read_scope='full principal article text from official site through web reader'))
 owner=ROOT/'work/ecommerce_functional_20261106/observed_west/udomlya_interview.html'
 if owner.exists():
  sources.append({'source_id':'udomlya_owner_interview20251205','url':'https://goroda.media/kak-sozdat-kviz-mural-i-set-punktov-vydachi-zakazov-v-udomle-i-pri-chem-tut-vodyanoy/amp/','publication_date':'2025-12-05','artifact_kind':'original_http_html_acquired_by_observed_west','raw_path':str(owner.relative_to(ROOT)),'sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),'read_scope':'sections Первый бизнес; Как открыть пункт выдачи в атомном городе','evidence':'first-person owner account; not audited accounts or observed customer OD'})
 meta={'retrieved_date':'2026-11-06','sources':sources,'event_source_post_ids':{'wb_partner_2006':'https://t.me/wbsellerofficial/2006','wb_partner_2017':'https://t.me/wbsellerofficial/2017','wb_customer_175':'https://t.me/wildberriesofficialcustomer/175'},'review_extraction_n_visible_unique':len(reviews),'review_selection':'3 issue-related reviews; two closure reports and one intention; not prevalence estimate','new_route_completed_volume_observed':False,'causal_effect_estimated':False,'large_source_bodies_published':False}
 (HERE/'primary_sources.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'dubki_selected_reviews':len(rows),'dated_disruption_records':len(events),'regional_growth_rows':len(flows),'causal_effect_estimated':False},ensure_ascii=False))
if __name__=='__main__':main()

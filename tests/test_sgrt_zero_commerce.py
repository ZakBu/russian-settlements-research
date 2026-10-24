import sys,unittest,json,tempfile,gzip
from unittest.mock import patch,MagicMock
from pathlib import Path
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.commerce import classify_osm,normalize_osm,normalize_wb,match_wb_addresses,np_offers,bind_explicit_city_contexts,write_pickup_variants,pickup_operator_code,normalize_yandex,write_grocery_host_variant,acquire_yandex_public_widget

def reference():
 return pd.DataFrame({'root':['r1','r2','r3'],'source_record_id':['a','b','c'],'name':['Берёзовка','Берёзовка','Саратов'],
  'region':['саратовская','саратовская','саратовская'],'region_norm':['саратовская']*3,
  'population_role':['ordinary_settlement_record']*3,'ordinary_spatial_2021':[True]*3,
  'lat':[50.,50.02,51.54],'lon':[45.,45.02,46.]})

def legacy():
 return pd.DataFrame({'root':['r1','r2','r3'],'source_record_id_2021':['a','b','c'],'id':['old-a','old-b','old-c'],
  'name':['Берёзовка','Берёзовка','Саратов'],'region':['саратовская']*3})

def osm_row(tags,**kwargs):
 row=dict(tags_json=json.dumps(tags,ensure_ascii=False),snapshot='2021-01-01T21:42:03Z',source_snapshot=None,
  source_start_date=None,source_end_date=None,lat=50.,lon=45.,count_eligible=True,recovery_status='source',
  baseline_uid='old-a',candidate_uid=None,link_status='explicit_address_locality_unique_within5km',
  source_address_locality='Берёзовка',canonical_site_id='osm:node:1',site_id='osm:node:1',name='Store',source_address_state='Саратовская область')
 row.update(kwargs);return row

class CommerceTests(unittest.TestCase):
 def test_name_alone_is_not_pickup(self):
  self.assertEqual(classify_osm({'name':'Медицинский центр Ozon','amenity':'clinic'})[0],'unclassified_commerce')
  self.assertEqual(classify_osm({'name':'Ozon','shop':'outpost'})[0],'parcel_pickup')
 def test_full_grocery_and_specialist_differ(self):
  self.assertEqual(classify_osm({'shop':'supermarket'})[0],'daily_grocery')
  self.assertEqual(classify_osm({'shop':'bakery'})[0],'daily_food_specialist')
  self.assertEqual(classify_osm({'amenity':'marketplace'})[0],'marketplace_unspecified_assortment')
 def test_closed_and_ended_stores_not_admitted(self):
  d=normalize_osm(pd.DataFrame([osm_row({'shop':'convenience','disused':'yes'}),osm_row({'shop':'convenience','end_date':'2016'},site_id='osm:node:2',canonical_site_id='osm:node:2')]),reference(),legacy())
  self.assertEqual(d.supply_status.tolist(),['excluded_lifecycle','excluded_temporal'])
 def test_nearest_legacy_candidate_does_not_create_identity(self):
  d=normalize_osm(pd.DataFrame([osm_row({'shop':'supermarket'},baseline_uid=None,candidate_uid='old-a',link_status='spatial_candidate_within2_5km_separated_not_identity_proof')]),reference(),legacy())
  self.assertTrue(d.source_record_id.isna().all());self.assertEqual(d.supply_status.iloc[0],'observed')
 def test_same_source_canonical_duplicate_is_only_one_supplier(self):
  d=normalize_osm(pd.DataFrame([osm_row({'shop':'supermarket'}),osm_row({'shop':'supermarket'},site_id='osm:way:2')]),reference(),legacy())
  self.assertEqual(d.supply_status.eq('observed').sum(),1)
 def test_explicit_negative_shop_not_service(self):
  d=normalize_osm(pd.DataFrame([osm_row({'shop':'vacant'})]),reference(),legacy())
  self.assertEqual(d.supply_status.iloc[0],'excluded_negative_shop')
 def test_ambiguous_same_name_is_not_nearest_identity(self):
  p=pd.DataFrame({'activity_address':['д. Берёзовка, улица Лесная 1'],'site_lat':[50.001],'site_lon':[45.001]})
  d=match_wb_addresses(p,reference());self.assertTrue(d.source_record_id.isna().all());self.assertEqual(d.np_identity_candidate_count.iloc[0],2)
 def test_street_name_does_not_create_locality(self):
  p=pd.DataFrame({'activity_address':['улица Саратов, дом 1'],'site_lat':[51.54],'site_lon':[46.]})
  d=match_wb_addresses(p,reference());self.assertTrue(d.source_record_id.isna().all())
 def test_wb_delivery_types_not_all_pickup(self):
  x=[{'country':'ru','items':[{'id':1,'typePoint':34,'address':'г. Саратов, улица Ленина 1','coordinates':[51.54,46.],'workTime':'daily','fittingRooms':1},{'id':2,'typePoint':2,'address':'г. Саратов, улица Ленина 2','coordinates':[51.54,46.]}]}]
  d=normalize_wb(x,reference());self.assertEqual(d.supply_status.tolist(),['observed','excluded_uninterpreted_delivery_type'])
  self.assertEqual(d.source_record_id.iloc[0],'c')
 def test_source_country_ru_not_boundary_proof(self):
  x=[{'country':'ru','items':[{'id':1,'typePoint':34,'address':'Баренцбург','coordinates':[50.,45.]}]}]
  d=normalize_wb(x,reference());self.assertEqual(d.supply_status.iloc[0],'excluded_known_foreign_country_label_conflict');self.assertTrue(d.source_record_id.isna().all())
 def test_sources_years_remain_separate_np_offers(self):
  d=pd.DataFrame({'provider_id':['1','2','3'],'source_record_id':['a']*3,'service_code':['parcel_pickup']*3,'supply_status':['observed']*3,'source_id':['osm','osm','wb'],'source_year':[2021,2021,2026],'source_snapshot':['2021-01-01','2021-01-01','2026-10-24']})
  s=np_offers(d);self.assertEqual(len(s),2);self.assertEqual(s.provider_records.tolist(),[2,1]);self.assertFalse(s.object_count_is_attraction_weight.any())
 def test_missing_population_ids_do_not_break_type_map(self):
  p=pd.DataFrame({'activity_address':['г. Саратов, улица Ленина 1'],'site_lat':[51.54],'site_lon':[46.]})
  w=pd.DataFrame({'source_record_id_2021':['a','b','c',None,None],'settlement_type_2021':['деревня','деревня','город','село','село']})
  d=match_wb_addresses(p,reference(),w);self.assertEqual(d.source_record_id.iloc[0],'c')

class FederalCommerceTests(unittest.TestCase):
 def context(self):
  r=reference()
  c=pd.DataFrame({'root':['m'],'source_record_id':['moscow-context'],'name':['Москва'],'region':['москва'],'region_norm':['москва'],
   'population_role':['external_context_nonadditive'],'ordinary_spatial_2021':[False],'lat':[55.75],'lon':[37.61]})
  return pd.concat([r,c],ignore_index=True)
 def test_explicit_city_context_not_nearest_owner(self):
  d=pd.DataFrame({'source_record_id':[None],'activity_address':['г. Москва, улица Ленина 1'],'source_address_locality':[None],'source_region_literal':[None],'tags_json':[None],'site_lat':[55.9],'site_lon':[37.9]})
  a=bind_explicit_city_contexts(d,self.context());self.assertEqual(a.source_record_id.iloc[0],'moscow-context');self.assertTrue(a.identity_is_nonadditive_territorial_context.iloc[0])
 def test_conflicting_region_does_not_bind_city(self):
  r=self.context();r=pd.concat([r,pd.DataFrame({'root':['o'],'source_record_id':['o'],'name':['Иное'],'region':['московская'],'region_norm':['московская'],'population_role':['ordinary_settlement_record'],'ordinary_spatial_2021':[True],'lat':[56.],'lon':[38.]})],ignore_index=True)
  d=pd.DataFrame({'source_record_id':[None],'activity_address':['Московская область, г. Москва, улица Ленина 1'],'source_address_locality':[None],'source_region_literal':[None],'tags_json':[None]})
  a=bind_explicit_city_contexts(d,r);self.assertTrue(a.source_record_id.isna().all())
 def test_precise_locality_has_priority_over_federal_city_name(self):
  d=pd.DataFrame({'source_record_id':['a'],'activity_address':['Москва, д. Березовка, улица Ленина 1'],'source_address_locality':['Березовка'],'source_region_literal':[None],'tags_json':[None]})
  a=bind_explicit_city_contexts(d,self.context());self.assertEqual(a.source_record_id.iloc[0],'a');self.assertFalse(a.identity_is_nonadditive_territorial_context.iloc[0])

class PickupOperatorTests(unittest.TestCase):
 def test_operator_codes_do_not_make_all_points_interchangeable(self):
  self.assertEqual(pickup_operator_code('ООО «Вайлдберриз»'),'wildberries')
  self.assertEqual(pickup_operator_code('Ozon.ru'),'ozon')
  self.assertIsNone(pickup_operator_code('Неизвестный магазин'))
 def test_current_wb_variant_excludes_old_and_other_operator_points(self):
  rows=pd.DataFrame({'provider_id':['w','o','old','u'],'source_record_id':['a']*4,'service_code':['parcel_pickup']*4,
    'supply_status':['observed']*4,'source_id':['WB_PUBLIC_MAP_20261024','OSM2021','OSM2021','OSM2021'],
    'source_year':[2026,2021,2021,2021],'source_snapshot':['2026-10-24','2021-01-01','2021-01-01','2021-01-01'],
    'operator':['Wildberries','Ozon','Wildberries',None]})
  with tempfile.TemporaryDirectory() as tmp:
   summary=write_pickup_variants(rows,Path(tmp))
   fresh=pd.read_parquet(Path(tmp)/'sites_wb_current.parquet')
   operators=pd.read_parquet(Path(tmp)/'operator_service_sites.parquet')
   self.assertEqual(fresh.provider_id.tolist(),['w'])
   self.assertFalse(fresh.counts_as_independent_service_channel.any())
   self.assertFalse(fresh.other_operator_can_replace_this_point_for_same_order.any())
   self.assertEqual(operators.loc[operators.provider_id.eq('u'),'supply_status'].iloc[0],'held_operator_compatibility_unknown')
   json.dumps(summary,allow_nan=False)

class YandexPublicWidgetTests(unittest.TestCase):
 def point(self,**extra):
  row={'id':'y1','operator_id':'market_l4g','type':'pickup_point','position':{'latitude':51.54,'longitude':46.},
   'address':{'country':'Россия','region':'Саратовская область','locality':'город Саратов','street':'улица Ленина','house':'1'},
   'available_for_dropoff':False,'is_yandex_branded':False,'is_market_partner':True,'deactivation_date':None}
  row.update(extra);return row
 def test_customer_pickup_does_not_require_sender_dropoff(self):
  d=normalize_yandex({'points':[self.point()]},reference())
  self.assertEqual(d.supply_status.iloc[0],'observed');self.assertEqual(d.source_record_id.iloc[0],'c')
  self.assertFalse(d.source_available_for_dropoff.iloc[0]);self.assertFalse(d.counts_as_independent_service_channel.any())
 def test_deactivated_point_rejected_future_date_retained(self):
  rows=[self.point(deactivation_date='2026-10-01'),self.point(id='y2',deactivation_date='2026-11-05')]
  d=normalize_yandex({'points':rows},reference())
  self.assertEqual(d.supply_status.tolist(),['excluded_deactivated_on_or_before_snapshot','observed'])
  self.assertTrue(d.future_deactivation_announced.iloc[1])
 def test_debt_prediction_is_not_actual_deactivation(self):
  d=normalize_yandex({'points':[self.point(deactivation_date_predicted_debt='2026-10-01')]},reference())
  self.assertEqual(d.supply_status.iloc[0],'observed')
 def test_warehouse_foreign_or_other_operator_not_yandex_customer_layer(self):
  foreign=self.point(id='foreign');foreign['address']['country']='Казахстан'
  rows=[self.point(type='warehouse'),self.point(id='other',operator_id='5post'),foreign]
  d=normalize_yandex({'points':rows},reference())
  self.assertEqual(d.supply_status.tolist(),['excluded_not_customer_pickup','excluded_other_operator','excluded_source_country'])

class FivePostTests(unittest.TestCase):
 def point(self,**extra):
  row={'id':'f1','operator_id':'5post','type':'pickup_point','position':{'latitude':51.54,'longitude':46.},
   'name':'5 Post (Пятерочка)','address':{'country':'Россия','region':'Саратовская область','locality':'город Саратов','street':'улица Ленина','house':'1','comment':'5post. Касса в магазине «Пятёрочка»'}}
  row.update(extra);return row
 def test_missing_country_stays_unknown(self):
  p=self.point();p['address']['country']=''
  d=normalize_yandex({'points':[p]},reference(),network_operator='5post')
  self.assertEqual(d.supply_status.iloc[0],'held_source_country_unknown')
 def test_pickup_name_not_sufficient_to_prove_host_store(self):
  p=self.point(id='f2');p['address']['comment']='Пункт 5Post расположен в ПВЗ Ozon'
  d=normalize_yandex({'points':[self.point(),p]},reference(),network_operator='5post')
  with tempfile.TemporaryDirectory() as tmp:
   summary=write_grocery_host_variant(d,Path(tmp))
   host=pd.read_parquet(Path(tmp)/'sites_grocery_current_host_proxy.parquet')
   offers=pd.read_parquet(Path(tmp)/'supply_grocery_current_host_proxy.parquet')
   self.assertEqual(summary['retailer_host_assertions'],1)
   self.assertEqual(host.provider_id.tolist(),['5post:f1']);self.assertEqual(host.supply_status.iloc[0],'proxy')
   self.assertTrue(host.parcel_order_compatibility_not_applicable.all());self.assertFalse(host.independent_store_inventory.any())
   self.assertEqual(offers.supply_status.iloc[0],'proxy');self.assertFalse(offers.default_external_seed_eligible.any())

class OperatorAcquisitionTests(unittest.TestCase):
 def test_existing_different_snapshot_is_not_overwritten(self):
  old=b'{"points": [{"id":"old"}]}'
  response=MagicMock();response.status=201;response.headers={'Content-Type':'application/json'};response.read.return_value=b'{"points": [{"id":"new"}]}'
  response.__enter__.return_value=response
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'yandex_public_widget_pickup_20261024.json.gz'
   with gzip.open(p,'wb') as stream:stream.write(old)
   original=p.read_bytes()
   with patch('scripts.sgrt_zero.commerce.urllib.request.urlopen',return_value=response):
    with self.assertRaisesRegex(ValueError,'different frozen operator snapshot'):acquire_yandex_public_widget(tmp)
   self.assertEqual(p.read_bytes(),original)

if __name__=='__main__':unittest.main()

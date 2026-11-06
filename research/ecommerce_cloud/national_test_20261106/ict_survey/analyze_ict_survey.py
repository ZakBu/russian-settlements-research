#!/usr/bin/env python3
"""National ICT microdata estimates: people placing physical-goods orders.

Repeated cross-sections, not net effects on settlements or journey substitution.
No individual records emitted. SAV metadata and respondent weights define units.
"""
from pathlib import Path
import argparse,csv,hashlib,json
import numpy as np
import pandas as pd
import pyreadstat
ROOT=Path(__file__).resolve().parents[4]
D=Path(__file__).resolve().parent
W=ROOT/'work/ecommerce_national_test_20261106/ict_survey'
PHYSICAL={1:'Предметы домашнего обихода',2:'Медицинские товары',5:'Одежда, обувь, спорттовары',17:'Косметика и парфюмерия',8:'Компьютерное оборудование',9:'Бытовая техника/электронное оборудование, телефоны, лампы, батарейки',12:'Продукты питания и бакалея',16:'Товары для творчества и хобби'}
EXCLUDED={4:'Книги, включая электронные: физическое/цифровое не разделено',6:'Видеоигры и обновления',7:'Программное обеспечение',10:'Телекоммуникационные услуги',11:'Финансовые услуги',13:'Билеты на развлекательные мероприятия',14:'Путешествия/билеты/бронирование',15:'Другое: предмет не установлен',18:'Фильмы',19:'Музыка',20:'Доставка готовой еды: смешение услуги и еды',21:'Ремонт/уборка',22:'Образовательные услуги'}
def write(name,rows):
 with (D/name).open('w',newline='') as f:
  wr=csv.DictWriter(f,lineterminator='\n',fieldnames=list(dict.fromkeys(k for r in rows for k in r)));wr.writeheader();wr.writerows(rows)
def main():
 pa=argparse.ArgumentParser();pa.add_argument('--years',nargs='+',type=int,default=[2024]);args=pa.parse_args()
 estimates=[];audits=[];data={};schemas=[]
 for year in args.years:
  p=W/f'IKT-{year}.sav';assert p.exists(),f'Missing pinned primary SAV: {p}'
  _,meta=pyreadstat.read_sav(p,metadataonly=True)
  fields=['TERRIT','POSEL','GOD','VESA_SVOD','NAS_POL','NAS_VOZR','Int1','IntP1']+[f'IntP2_{k}'for k in PHYSICAL]+['IntP5_1','IntP5_2','IntP5_3','IntP4_2']
  assert set(fields)<=set(meta.column_names), sorted(set(fields)-set(meta.column_names))
  assert 'респондента' in meta.column_names_to_labels['VESA_SVOD'].lower()
  assert meta.variable_value_labels['POSEL'][2.0]=='Сельское'
  d,_=pyreadstat.read_sav(p,usecols=fields,user_missing=True);assert d.GOD.eq(year).all()
  assert d.VESA_SVOD.notna().all() and d.VESA_SVOD.gt(0).all()
  assert d.NAS_VOZR.ge(15).all() and d.NAS_VOZR.notna().all()
  assert d.POSEL.isin([1,2]).all() and d.Int1.isin([1,2,3,4]).all()
  assert d.IntP1.isin([0,1,2,3,4]).all()
  assert (d.IntP1.eq(0)==d.Int1.isin([3,4])).all(), 'Structural skip differs'
  for k in PHYSICAL:assert d[f'IntP2_{k}'].isin([0,k]).all(),(year,k)
  for k in [1,2,3]:assert d[f'IntP5_{k}'].isin([0,k]).all()
  d['online12']=d.IntP1.isin([1,2]);d['physical8']=d[[f'IntP2_{k}'for k in PHYSICAL]].gt(0).any(axis=1)
  assert not (d.physical8&~d.online12).any()
  inconsistent_pickup=d.IntP5_2.gt(0)&~d.online12
  # Inconsistent raw delivery flags are audited, not interpreted as coherent orders.
  # Main physical intersection remains coherent because physical8 is nested in online12.
  d['age4']=pd.cut(d.NAS_VOZR,bins=[14,29,44,59,74],labels=['15–29','30–44','45–59','60–74'])
  data[year]=d
  audits.append({'year':year,'rows_n':len(d),'rural_rows_n':int(d.POSEL.eq(2).sum()),'min_age':int(d.NAS_VOZR.min()),'max_age':int(d.NAS_VOZR.max()),'population15plus_weight_sum':d.VESA_SVOD.sum(),'rural15plus_weight_sum':d.loc[d.POSEL.eq(2),'VESA_SVOD'].sum(),'respondent_weight':'VESA_SVOD','regions_n':d.TERRIT.nunique(),'missing_weight_rows_n':0,'nonpositive_weight_rows_n':0,'unknown_settlement_type_rows_n':0,'structural_skip_nonrecent_internet_rows_n':int(d.IntP1.eq(0).sum()),'selected_goods_without_last12m_buying_rows_n':int((d.physical8&~d.online12).sum()),'settlement_size_group_available':False,'named_settlements_available':False,'pickup_flag_without_online12_rows_n':int(inconsistent_pickup.sum()),'pickup_flag_without_online12_weight_sum':float(d.loc[inconsistent_pickup,'VESA_SVOD'].sum()),'pickup_flag_without_online12_rural15_74_rows_n':int((inconsistent_pickup & d.POSEL.eq(2) & d.NAS_VOZR.between(15,74)).sum()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  for name,label in meta.column_names_to_labels.items():
   if name in fields:schemas.append({'year':year,'field':name,'label':label,'value_labels_json':json.dumps(meta.variable_value_labels.get(name,{}),ensure_ascii=False)})
  for ages in ['15–74','15+']:
   a=d[d.NAS_VOZR.between(15,74)]if ages=='15–74'else d
   for geo,mask in [('all',pd.Series(True,index=a.index)),('urban',a.POSEL.eq(1)),('rural',a.POSEL.eq(2))]:
    g=a[mask];w=g.VESA_SVOD
    flags={'online_any_goods_or_services_last12m':g.online12,'physical8_any_last12m':g.physical8,'physical8_and_pickup_same_person':g.physical8&g.IntP5_2.gt(0),'physical8_and_delivery_to_buyer_same_person':g.physical8&g.IntP5_1.gt(0),'pickup_any_goods_or_services':g.online12&g.IntP5_2.gt(0),'online12_without_selected_physical8':g.online12&~g.physical8}
    flags.update({f'physical_category_{k}':g[f'IntP2_{k}'].gt(0)for k in PHYSICAL})
    for metric,yes in flags.items():
     estimates.append({'year':year,'age_universe':ages,'geography':geo,'metric':metric,'denominator':'all_persons_in_age_and_geography','unweighted_denominator_n':len(g),'unweighted_numerator_n':int(yes.sum()),'weighted_denominator_persons':float(w.sum()),'weighted_numerator_persons':float(w[yes].sum()),'pct':float(w[yes].sum()/w.sum()*100)})
    for metric,yes,den,denname in [('pickup_among_physical8',g.physical8&g.IntP5_2.gt(0),g.physical8,'persons_with_any_selected_physical8_order'),('delivery_among_physical8',g.physical8&g.IntP5_1.gt(0),g.physical8,'persons_with_any_selected_physical8_order'),('prefer_personal_purchases_among_recent_internet_nonbuyers',g.IntP4_2.gt(0),g.Int1.isin([1,2])&g.IntP1.isin([3,4]),'recent_internet_users_no_online_order_in_last12m')]:
     assert not(yes&~den).any(),(year,metric)
     estimates.append({'year':year,'age_universe':ages,'geography':geo,'metric':metric,'denominator':denname,'unweighted_denominator_n':int(den.sum()),'unweighted_numerator_n':int(yes.sum()),'weighted_denominator_persons':float(w[den].sum()),'weighted_numerator_persons':float(w[yes].sum()),'pct':float(w[yes].sum()/w[den].sum()*100)})
 write('ict_estimates.csv',estimates);write('ict_schema_fields.csv',schemas);write('ict_input_audit.csv',audits)
 mapping=[{'field':f'IntP2_{k}','label':v,'included_in_physical8':True,'reason':'Однозначная группа физических товаров; присутствует в формах2022 и2024'}for k,v in PHYSICAL.items()]+[{'field':f'IntP2_{k}','label':v,'included_in_physical8':False,'reason':'Услуга/электронный или смешанный носитель/неустановленный предмет'}for k,v in EXCLUDED.items()]
 write('physical_goods_definition.csv',mapping)
 # Independent official printed control, not a new estimate of physical goods.
 official={2022:{'all':53.7,'rural':40.4},2023:{'all':61.3,'rural':48.5},2024:{'all':71.6,'rural':61.9}}
 controls=[]
 for r in estimates:
  if r['age_universe']=='15–74' and r['metric']=='online_any_goods_or_services_last12m' and r['geography']in official.get(r['year'],{}):
   expected=official[r['year']][r['geography']];assert round(r['pct'],1)==expected
   controls.append({'year':r['year'],'geography':r['geography'],'age_universe':'15–74','metric':'any_goods_or_services_internet_order','calculated_pct':r['pct'],'official_pct':expected,'rounding_matches':True,'source':'Росстат, Российский статистический ежегодник2025,табл21.13,с459; официальныйPDF на публичномзеркале'})
 write('official_reproduction.csv',controls)
 if len(data)>1:
  base_year=min(data);base=data[base_year];base=base[base.POSEL.eq(2)&base.NAS_VOZR.between(15,74)]
  base_weights=base.groupby(['age4','NAS_POL'],observed=True).VESA_SVOD.sum();shares=base_weights/base_weights.sum()
  std=[]
  for year,d in data.items():
   g=d[d.POSEL.eq(2)&d.NAS_VOZR.between(15,74)].copy()
   g['physical_pickup']=g.physical8&g.IntP5_2.gt(0)
   for metric in ['physical8','physical_pickup','online12']:
    cells=g.groupby(['age4','NAS_POL'],observed=True).apply(lambda c:float((c[metric]*c.VESA_SVOD).sum()/c.VESA_SVOD.sum()),include_groups=False)
    assert set(cells.index)==set(shares.index)
    std.append({'year':year,'baseline_composition_year':base_year,'geography':'rural','age_universe':'15–74','metric':metric,'standardized_pct':float((cells*shares).sum()*100),'raw_pct':float((g[metric]*g.VESA_SVOD).sum()/g.VESA_SVOD.sum()*100),'standardization_cells_n':len(shares),'method':'direct_standardization_age4_by_sex; not causal adjustment'})
  write('ict_age_sex_standardized.csv',std)
 summary={'years':args.years,'source':'Public anonymised primary Rosstat ICT SPSS files, archived exact payload digests verified','person_weight':'VESA_SVOD','primary_age_universe':'15–74 to match published official table;15+ sensitivity also saved','physical_goods':'union of8 explicit physical groups; excludes mixed books,services,tickets,other','delivery':'Person-level intersection across12months; not identified same order,not local pickup,not only WB/Ozon','reference_window':'last12months,not calendar-year orders; IntP1recency not order frequency','geography':'urban/rural only; publicsizeclasses/namedNP not present','frame_note':'Official yearbook2025 says verbatim: данные до 2024 г. публикуются без учета итогов ВПН-2020. Inclusion of2024 not resolved by this wording alone; do not infer unchanged calibration or import KOУЖ frame assumptions.','source_files_unmodified':True,'no_design_standard_errors':'No validated PSU/strata/replicate-weight design in analysis; no causal SE or national net effect computed'}
 (D/'ict_analysis_metadata.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(pd.DataFrame(estimates).query("geography=='rural' and age_universe=='15–74' and metric in ['physical8_any_last12m','physical8_and_pickup_same_person','online_any_goods_or_services_last12m']")[['year','metric','unweighted_denominator_n','weighted_denominator_persons','pct']].to_string(index=False))
if __name__=='__main__':main()

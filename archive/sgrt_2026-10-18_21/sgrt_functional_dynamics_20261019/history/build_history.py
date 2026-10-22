"""Rebuild a documented 2023/2025/2026 school-service transition pilot.

No census quantity is a number of pupils or a measurement in the document year.
2023 handwritten transcription is explicitly page-referenced and visually checked.
"""
from pathlib import Path
import argparse, hashlib, json
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1] / 'anchor_research_20261019'
URL2023='https://education-ntura.ru/Документы/Документы_УО/Приказ_UO_65_20230303.PDF'
URL2025='https://education-ntura.ru/2025/03/12/приём-в-первый-класс-2025-2026-учебного-года/'
URL2026='https://education-ntura.ru/прием-в-общеобразовательную-организ/'

# Read against original PDF pages 3–4 (one based); not derived from the later graph.
CURATED2023=[
 ('S1','Нижняя Тура','МАОУ СОШ №1 имени Е.В. Панкратьева','город Нижняя Тура, улицы и переулок Речной','PDF_p3_row1'),
 ('S2','Нижняя Тура','МАОУ СОШ №2','город Нижняя Тура, улицы и переулок Бондина','PDF_p3_row2'),
 ('S3','Нижняя Тура','МАОУ СОШ №3','город Нижняя Тура, улицы и переулок Пирогова','PDF_p3_row3'),
 ('G','Нижняя Тура','МАОУ Нижнетуринская гимназия','город Нижняя Тура, улицы','PDF_p3_row4'),
 ('S7','Нижняя Тура','МАОУ СОШ №7 имени М.Г. Мансурова','город Нижняя Тура; станция ГРЭС; поселок Выя; деревни Новая Тура, Большая Именная, Малая Именная, Железенка; п/о Лесная сказка','PDF_p3_row5'),
 ('IS','Ис','МАОУ Исовская СОШ','город Нижняя Тура, посёлок Ис','PDF_p4_row6'),
 ('SIG','Сигнальный','МКОУ Сигнальненская СОШ','город Нижняя Тура, посёлки Сигнальный, Ермаковский, Черничный','PDF_p4_row7'),
 ('KOS','Косья','МБОУ Косьинская СОШ','город Нижняя Тура, посёлки Косья, Борисовский, Верх-Ис, Граневое, Лабазка, Покап','PDF_p4_row8'),
 ('PL','Платина','МБОУ Платинская ООШ','город Нижняя Тура, посёлок Платина','PDF_p4_row9')]

def sid(name):
 for token,key in [('ИСОШ','IS'),('Косьинская','KOS'),('Сигнальненская','SIG'),('Платинская','PL'),('НТГ','G')]:
  if token in name:return key
 for n in [1,2,3,7]:
  import re
  if re.search(r'№\s*'+str(n)+r'\b',name):return 'S'+str(n)
 raise ValueError(name)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT);args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
 schools=[]
 for k,place,name,territory,loc in CURATED2023:
  schools.append(dict(year=2023,source_id='NT2023',document_date='2023-03-03',document_number='65',school_key=k,provider_settlement=place,provider_name_literal=name,territory_literal=territory,locator=loc,source_url=URL2023,extraction='manual_visual_transcription_original_PDF',first_grade_plan=None,street_address=None,address_date=None,complete_school_list=True))
 for year,url,num,date in [(2025,URL2025,'70','2025-03-05'),(2026,URL2026,'79','2026-03-10')]:
  tab=pd.read_html(ROOT/f'raw/NT{year}_page.html')[0];assert len(tab)==10
  for i,row in tab.iloc[1:].iterrows():
   name,territory,cap=map(str,row.iloc[:3]);key=sid(name);place={'IS':'Ис','KOS':'Косья','SIG':'Сигнальный','PL':'Платина'}.get(key,'Нижняя Тура')
   import re
   am=re.search(r'адрес школы:\s*(.+?)\),',name)
   schools.append(dict(year=year,source_id=f'NT{year}',document_date=date,document_number=num,school_key=key,provider_settlement=place,provider_name_literal=name,territory_literal=territory,locator=f'HTML_table_row{i}',source_url=url,extraction='pandas_read_html_raw_official_page',first_grade_plan=int(float(cap)),street_address=am.group(1) if am else None,address_date=year if am else None,complete_school_list=True))
 inv=pd.DataFrame(schools)
 inv['territory_text_scope']=['2023 urban rows1–4 abbreviated street summary, row5 omits street list; rural rows6–9 preserve full right-column literal city prefix' if y==2023 else 'full raw HTML table cell' for y in inv.year]
 inv.to_csv(out/'school_inventory_by_year.csv',index=False)
 cityrows=[dict(year=2023,school_key=k,provider_settlement=place,source_fragment=territory,interpretation='source literally repeats city name; may be locality-address convention or broad urban attachment; not resolved by this study',handling='preserved literally; not exclusive settlement membership; urban origin omitted from rural-origin transition subset',locator=loc) for k,place,name,territory,loc in CURATED2023 if k in ['IS','SIG','KOS','PL']]
 for k,place,names in [('IS','Ис','город Нижняя Тура, посёлок Ис'),('SIG','Сигнальный','город Нижняя Тура, посёлки Сигнальный, Ермаковский, Черничный'),('KOS','Косья','город Нижняя Тура, посёлки Косья, Борисовский, Верх-Ис, Граневое, Лабазка, Покап'),('PL','Платина','город Нижняя Тура, посёлок Платина, деревня Новая Тура')]:
  cityrows.append(dict(year=2026,school_key=k,provider_settlement=place,source_fragment=names,interpretation='original PDF includes city prefix; official HTML territorial cell omits city prefix; unresolved literal source discrepancy',handling='both sources retained; do not infer urban-to-rural flow; subset only named rural origins',locator='original_PDF_p3_rows6to9'))
 city=pd.DataFrame(cityrows)
 city.to_csv(out/'urban_prefix_ambiguity_audit.csv',index=False)
 plan=inv[inv.year.isin([2025,2026])].pivot(index=['school_key','provider_settlement'],columns='year',values='first_grade_plan').reset_index().rename(columns={2025:'planned_first_grade_places_2025',2026:'planned_first_grade_places_2026'})
 plan['change']=plan.planned_first_grade_places_2026-plan.planned_first_grade_places_2025;plan['meaning']='planned_first_grade_admission_not_total_capacity_or_actual_students';plan.to_csv(out/'planned_first_grade_change.csv',index=False)
 ambiguous=[dict(feature=x,years='2023|2025|2026',status=s,handling='literal_table_preserved_not_new_settlement_edge') for x,s in [('Выя','2023 поселок; 2025/26 станция; not proven same as Большая/Малая Выя'),('ГРЭС','station not independently identified on immutable panel'),('Железенка','2023 деревня; later embedded in urban list; identity unresolved'),('Лесная сказка','2023 п/о; later embedded urban list; identity unresolved')]]
 pd.DataFrame(ambiguous).to_csv(out/'literal_feature_identity_audit.csv',index=False)
 linked=pd.read_csv(BASE/'data/service_edges_linked.csv');existing=linked[linked.source_id=='SV2025'].set_index('origin_name');panel=pd.read_parquet(BASE/'data/point_axis.parquet').set_index('id')
 # Only the 12 ordinary named settlement identities already independently resolved.
 # Four additional territorial features (Выя, ГРЭС, Железенка, Лесная сказка)
 # stay in the literal audit; their separate settlement identities are unresolved.
 maps={2023:{'S7':'Новая Тура|Большая Именная|Малая Именная','KOS':'Борисовский|Верх-Ис|Граневое|Лабазка|Покап','SIG':'Ермаковский|Черничный'},2025:{'S7':'Большая Именная|Малая Именная|Большая Выя|Малая Выя','KOS':'Борисовский|Верх-Ис|Граневое|Лабазка|Покап','SIG':'Ермаковский|Черничный','PL':'Новая Тура'}};maps[2026]=maps[2025].copy()
 edges=[]
 for year,groups in maps.items():
  for key,names in groups.items():
   school=inv[(inv.year==year)&(inv.school_key==key)].iloc[0]
   dest=linked[(linked.source_id=='SV2025')&(linked.provider_settlement==school.provider_settlement)].iloc[0].destination_uid
   for name in names.split('|'):
    e=existing.loc[name]; origin=e.origin_uid;p=panel.loc[origin]
    edges.append(dict(year=year,source_id=f'NT{year}',source_document_date=school.document_date,region='Свердловская область',municipality='Нижнетуринский муниципальный округ (название 2025–2026); городской округ (2023)',origin_name=name,origin_uid=origin,provider_settlement=school.provider_settlement,destination_uid=dest,school_key=key,provider_name=school.provider_name_literal,service_level='first_grade_admission_territorial_priority',relation_kind='normative_school_attachment',evidence_level='E2_documented_normative_link_not_observed_trip',origin_identity='previous_independent_exact_context_link',destination_identity='previous_independent_exact_context_link',complete_provider_universe_in_document=True,complete_ordinary_origins_in_literal_document=False,comparable_positive_assignment_across_years=True,zero_is_retained=True,locator=school.locator,source_url=school.source_url,**{f'population_{y}':p[f'population_{y}'] for y in [2002,2010,2021]},population_meaning='census_at_fixed_place_not_pupils_or_current_service_demand'))
 ed=pd.DataFrame(edges);ed.to_csv(out/'edges_by_year.csv',index=False);ed.to_parquet(out/'edges_by_year.parquet',index=False)
 trans=[]
 for a,b in [(2023,2025),(2025,2026),(2023,2026)]:
  old=ed[ed.year==a].set_index('origin_uid');new=ed[ed.year==b].set_index('origin_uid')
  for uid in old.index.union(new.index):
   x=old.loc[uid] if uid in old.index else None;y=new.loc[uid] if uid in new.index else None;p=panel.loc[uid]
   if x is None:status='new_explicit_mention_not_proven_new_function'
   elif y is None:status='not_explicit_later_not_proven_closure'
   elif x.school_key==y.school_key:status='same_provider_site_legal_name_changes_ignored'
   else:status='documented_assignment_changed'
   trans.append(dict(from_year=a,to_year=b,origin_uid=uid,origin_name=(x if x is not None else y).origin_name,old_school_key=x.school_key if x is not None else None,new_school_key=y.school_key if y is not None else None,old_provider=x.provider_settlement if x is not None else None,new_provider=y.provider_settlement if y is not None else None,status=status,positive_assignment_both_dates=x is not None and y is not None,source_relocation_not_measured=True,**{f'population_{z}':p[f'population_{z}'] for z in [2002,2010,2021]}))
 tr=pd.DataFrame(trans);tr.to_csv(out/'attachment_transitions.csv',index=False)
 sums=tr.groupby(['from_year','to_year','status'],dropna=False).agg(origins=('origin_uid','size'),census_population_2002=('population_2002','sum'),census_population_2010=('population_2010','sum'),census_population_2021=('population_2021','sum')).reset_index();sums.to_csv(out/'transition_summary.csv',index=False)
 ag=ed.groupby(['year','provider_settlement'],dropna=False).agg(external_origins=('origin_uid','nunique'),external_population_2002=('population_2002','sum'),external_population_2010=('population_2010','sum'),external_population_2021=('population_2021','sum'),zero_2021_origins=('population_2021',lambda x:int((x==0).sum()))).reset_index();ag.to_csv(out/'provider_external_population.csv',index=False)
 # Exact reallocation decomposition on common origin universe: hold census date fixed.
 common=set(ed[ed.year==2023].origin_uid)&set(ed[ed.year==2025].origin_uid)
 decomp=[]
 for place in sorted(inv.provider_settlement.unique()):
  sets={y:set(ed[(ed.year==y)&(ed.provider_settlement==place)].origin_uid)&common for y in [2023,2025]}
  for popyear in [2002,2010,2021]:
   vals={y:float(panel.loc[list(s),f'population_{popyear}'].sum()) for y,s in sets.items()}
   decomp.append(dict(provider_settlement=place,census_population_year=popyear,old_assignment_population=vals[2023],new_assignment_population=vals[2025],reallocation_effect=vals[2025]-vals[2023],origins_common=len(common),meaning='fixed_census_population_reallocated_by_document_not_population_change_2023_2025'))
 pd.DataFrame(decomp).to_csv(out/'fixed_population_reallocation.csv',index=False)
 checks=[('27_inventory_records',len(inv)==27),('9_distinct_schools_per_year',all(inv.groupby('year').school_key.nunique()==9)),('edges_unique',not ed.duplicated(['year','origin_uid']).any()),('10_12_12_edges',ed.groupby('year').size().to_dict()=={2023:10,2025:12,2026:12}),('one_changed_2023_2025',len(tr[(tr.from_year==2023)&(tr.to_year==2025)&(tr.status=='documented_assignment_changed')])==1),('no_changed_2025_2026',len(tr[(tr.from_year==2025)&(tr.to_year==2026)&(tr.status=='documented_assignment_changed')])==0),('reallocation_balances',all(pd.DataFrame(decomp).groupby('census_population_year').reallocation_effect.sum()==0)),('same12_origin_population_2025_2026',ed[ed.year==2025].population_2021.sum()==ed[ed.year==2026].population_2021.sum()),('zeros_retained',int((ed.population_2021==0).sum())==17),('all_positive_assignments_no_claimed_trip',ed.evidence_level.str.contains('not_observed_trip').all())]
 audit={'status':'PASS' if all(v for _,v in checks) else 'FAIL','checks':[{'name':k,'pass':bool(v)} for k,v in checks],'comparability':'Same municipal school-list frame; first-grade priority comparison; only origins positively named both years support reassignment; urban street changes and unresolved territorial features not interpreted as settlement changes.','schools':len(inv),'edges':len(ed),'changed_case':'Новая Тура: Нижняя Тура school7 → Платина OOШ, interval (2023-04-01,2025-04-01]; not actual travel and not proven capacity change.','capture_dates':'retrieved 2026-10-19; published/act dates stored separately','input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'raw').glob('*') if p.is_file()}}
 (out/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps(audit,ensure_ascii=False))
 assert audit['status']=='PASS'

if __name__=='__main__':main()

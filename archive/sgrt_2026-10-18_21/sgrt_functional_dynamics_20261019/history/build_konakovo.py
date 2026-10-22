"""Replay three visually transcribed school catchment groups, 2021 vs 2026.

Not all district origins are extracted; all 42 positive literal names are retained.
"""
from pathlib import Path
import argparse,json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent
GROUPS2026={
 'Козлово':'Бережки|Бушмино|Гаврилково|Гришкино|Дмитрово|Долгая Пожня|Дорино|Заозерье|Зеленцино|Ивановское|Клещево|Койдиново|Курьяново|Павельцево|Синцово|Текстильщик|Узкол|Юрьево',
 'Селихово':'Заречье|Сажино|Сорокопенино|Дубровки|Марьино|Филимоново|Поречье|Чублово',
 'Ручьи':'Сынково|Высоково|Данилово|Уразово|Крутец|Тарлаково|Трунино|Баранниково|Ботеново|Трубицино|Быстрово|Слободка|Рябиково|Захарово|Красинское|Дулово'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 e=pd.read_csv(ROOT.parents[1]/'anchor_research_20261019/data/service_edges_linked.csv');e=e[e.source_id=='TV2021'].copy();p=pd.read_parquet(ROOT.parents[1]/'anchor_research_20261019/data/point_axis.parquet').set_index('id')
 observed={(place,n) for place,names in GROUPS2026.items() for n in names.split('|')};assert observed==set(zip(e.provider_settlement,e.origin_name));assert len(observed)==42
 sources=json.loads((ROOT/'raw/TV_retrieval.json').read_text());urls={2021:next(x['url'] for x in sources if x['file']=='TV_unknown_attachment.pdf'),2026:next(x['url'] for x in sources if x['file']=='TV2026_attachment.pdf')}
 rows=[]
 for year in [2021,2026]:
  for _,x in e.iterrows():
   d=x.to_dict();d.update(year=year,source_id=f'TV{year}',source_document_date='2021-01-27' if year==2021 else '2026-03-18',document_number='37' if year==2021 else '471',service_level='general_education_territorial_attachment',relation_kind='normative_school_attachment',function_group='education',evidence_level='E2_documented_normative_link_not_observed_trip',coverage='three complete selected school groups of full28schoollist; not all external edges of district',locator='originalPDF2021pp5to6_rows16to18' if year==2021 else 'originalPDF2026p7_rows16to18',source_url=urls[year],complete_provider_universe_in_document=True,complete_origin_universe_for_selected_provider_groups=True,all_district_origins_extracted=False,provider_id=f'TV{year}:'+x.provider_settlement)
   for y in [2002,2010,2021]:d[f'population_{y}']=p.loc[x.origin_uid,f'population_{y}'] if pd.notna(x.origin_uid) else None
   rows.append(d)
 out=pd.DataFrame(rows);out.to_csv(a.out/'konakovo_edges_by_year.csv',index=False)
 t=e[['origin_uid','origin_name','provider_settlement','both_endpoints_linked']].copy();t['from_year']=2021;t['to_year']=2026;t['status']='same_provider_place';t['legal_name_change_not_closure']=t.provider_settlement.eq('Ручьи');t.to_csv(a.out/'konakovo_transitions.csv',index=False)
 audit=dict(status='PASS',two_dates=[2021,2026],edges_per_date=42,selected_provider_groups=3,same_provider_place_assignments=42,both_endpoint_resolved_per_date=int(e.both_endpoints_linked.sum()),unresolved_origins_retained_per_date=int((~e.both_endpoints_linked).sum()),provider_name_only_change='Ручьи school adds Василия Павловича Волкова; same place and same16externalorigins',visual_compare='original2021PDFpp5–6 and original2026PDFp7 read directly,18+8+16 names same; title2026PDFp1 date18.03.2026 No471',not_full_district_external_graph=True,not_actual_trips=True,sum_census_population_2021_resolved=float(out[out.year==2021].population_2021.sum()),source_bytes_sha256={f:hashlib.sha256((ROOT/'raw'/f).read_bytes()).hexdigest() for f in ['TV_unknown_attachment.pdf','TV2026_attachment.pdf']})
 (a.out/'KONAKOVO_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()

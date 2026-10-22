#!/usr/bin/env python3
"""Named municipal commuting context; no invented NP-level OD observations."""
from pathlib import Path
import json,re,hashlib
import pandas as pd
from lxml import html
H=Path(__file__).resolve().parent
A=pd.read_parquet(H.parent/'axis/full_settlement_axis.parquet')
htmlfile=H/'sources/demoscope_commuting2017.html';tree=html.fromstring(htmlfile.read_bytes());text=' '.join(' '.join(tree.itertext()).split())
for needle in ['46,0% по Солнечногорску','36,4% по Монино','68,6% по Подольску','ноябрь 2015']:
 assert needle in text,needle
rows=[]
for town,share in [('Солнечногорск',46.0),('Монино',36.4),('Подольск',68.6)]:
 c=A[A.name.eq(town)&A.region.str.contains('московск',case=False,na=False)]
 urban=c[c.type.isin(['город','пгт','посёлок городского типа','рабочий посёлок'])]
 if len(urban):c=urban
 assert len(c)==1,(town,len(c))
 rows.append(dict(id=c.iloc[0].id,named_context=town,destination='Москва',evidence_class='published_empirical_mobile_commuting_municipal_context',measurement_period='2015-11',publication_period='2017-05',source_grain='urban_rural_municipal_settlement_comparisons_not_each_NP',scope='Named source municipal settlement context; censusNP matches literal town name only',moscow_share_of_total_outbound_commuters_percent=share,denominator='all outbound commuters from named source area; NOT residents, employed residents or population',observed_NP_OD_matrix=False,source_raw_OD_open=False,all_villages_in_system_measured=False,commuting_observed_NP_flag_asserted=False,source_url='https://www.demoscope.ru/weekly/2017/0727/tema02.php',source_authors='Алла Махрова; Антон Бочкарев',source_sha256=hashlib.sha256(htmlfile.read_bytes()).hexdigest(),named_context_link='literal_unique_name_region_and_urban_type; no native2015municipal_polygon_crosswalk'))
p=H/'sources/odintsovo_architect2015.html';t=' '.join(' '.join(html.fromstring(p.read_bytes()).itertext()).split());assert 'Маятниковая миграция из-за отсутствия рабочих мест в Одинцово' in t
c=A[A.name.eq('Одинцово')&A.region.str.contains('московск',case=False,na=False)&A.type.eq('город')];assert len(c)==1
rows.append(dict(id=c.iloc[0].id,named_context='Одинцово',destination='Москва',evidence_class='named_official_qualitative_assessment_in_media_interview',measurement_period=None,publication_period='2015-03-30',source_grain='named_town_official_assessment_not_OD_count',scope='Chief municipal architect Кирилл Завражин discusses commuting and town jobs; no measured share',moscow_share_of_total_outbound_commuters_percent=None,denominator=None,observed_NP_OD_matrix=False,source_raw_OD_open=False,all_villages_in_system_measured=False,commuting_observed_NP_flag_asserted=False,source_url='https://oinfo.ru/news/?cpn=2&id=46918',source_authors='Галина Енина; интервью Кирилла Завражина',source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),named_context_link='literal_unique_name_region_and_city_type'))
d=pd.DataFrame(rows);d.to_parquet(H/'commuting_named_context.parquet',index=False)
r={'rows':len(d),'empirical_named_municipal_contexts':3,'qualitative_named_official_assessments':1,'settlement_feature_commuting_observed_mutated':False,'not_a_complete_OD_matrix':True,'scope':'Independent useful commuting context for named central places; no inference that every satellite village commutes or that percentages refer to all residents','further_source':'Ramen municipal masterplan2019balance+4600 hasmunicipalonlyscope; acquired byroot validation/commuting_source_acquisition.json, notattachedasNP'}
(H/'commuting_context_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))

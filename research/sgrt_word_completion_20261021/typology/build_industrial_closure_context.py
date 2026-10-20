#!/usr/bin/env python3
"""Primary historical loss of coal enterprises, without asserting loss of all industry."""
from pathlib import Path
import json,hashlib
import pandas as pd
from lxml import html
H=Path(__file__).resolve().parent
p=H/'sources/perm_ombudsman2002_coal_closures.html';s=' '.join(' '.join(html.fromstring(p.read_bytes()).itertext()).split())
assert 'городов Кизел, Губаха, Гремячинск и Чусовой' in s
assert 'уволенные в 1995 - 1998 годах с предприятий угольной промышленности' in s
operator=H/'sources/kizel_gis_operator2004.html';o=' '.join(' '.join(html.fromstring(operator.read_bytes()).itertext()).split())
assert 'прекратила добычу угля 1 апреля 2000 г.' in o
axis=pd.read_parquet(H.parent/'axis/full_settlement_axis.parquet');rows=[]
for town in ['Кизел','Губаха','Гремячинск','Чусовой']:
 c=axis[axis.name.eq(town)&axis.region.str.contains('перм',case=False,na=False)&axis.type.eq('город')];assert len(c)==1
 rows.append({'id':c.iloc[0].id,'name':town,'documented_local_coal_enterprise_closure_history':True,'closure_witness_period':'1995-1998','primary_publication_date':'2002-12-27','source_grain':'named_cities_and_liquidated_coal_organizations; nofullindustrialcensus','primary_source_role':'official_regional_ombudsman_document; legalreferenceGovernmentRF1068_1998_anddismissedcoalworkers','primary_source_url':'https://www.ombudsman.perm.ru/news/2002/12/27/142/','primary_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'event_within_2010_2021':False,'all_industrial_base_lost':None,'absence_of_compensating_industries_proven':None,'physical_industrial_decline_2010_2021_observed':None,'industrial_decline_evidence_asserted':False,'supporting_basin_source':'https://arcreview.esri-cis.ru/2004/10/14/monitoring-of-kizelovsky-coal-basin/','supporting_basin_source_scope':'Technicalmonitoringsystemproviderdescribes15minesatstartofrestructuringandlastbasinmineceased2000; basinwidefactnotentirecityindustry','source_authors_operator':'GISecologicalmonitoringdeveloperIBS/Data+; ArcReview2004-10-14'})
d=pd.DataFrame(rows);d.to_parquet(H/'industrial_closure_named_context.parquet',index=False)
r={'rows':4,'known_event_window':'1995-1998;basinlastmine2000','national_features_changed':False,'industrial_decline_evidence_remains_unknown':True,'semantics':'Proves historical withdrawal of local coal enterprises beyond merely monoindustrial designation; doesnotproveallindustrialbaseceased,uncompensatedcollapseornew2010–2021decline','source_dates':'Officialregionalombudsman2002; GISoperator2004'}
(H/'industrial_closure_context_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))

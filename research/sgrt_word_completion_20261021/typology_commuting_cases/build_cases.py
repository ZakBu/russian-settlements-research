#!/usr/bin/env python3
"""Extract published facts; never manufacture NP commuting from a municipality."""
from pathlib import Path
import hashlib,json,re
import pandas as pd
import fitz
H=Path(__file__).resolve().parent;R=H.parent;RAW=Path('/workspace/scratch/sgrt_commuting_cases')
PDF=RAW/'article_http.pdf';SOURCE='http://demoscope.ru/weekly/2017/0727/demoscope727.pdf'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,d):(H/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
d=fitz.open(PDF);assert len(d)==25
texts=[re.sub(r'\s+',' ',p.get_text()).strip() for p in d]
assert 'Рисунок 1.' in texts[6] and 'Таблица 4.' in texts[13]
assert 'матрица корреспонденций «дом-работа»' in texts[3]
axis=pd.read_parquet(R/'axis/full_settlement_axis.parquet')
def uid(name):
 v=axis[axis.name.eq(name)&axis.region.str.contains('московск',case=False,na=False)]
 u=v[v.type.isin(['город','пгт','посёлок городского типа','рабочий посёлок'])]
 if len(u):v=u
 assert len(v)==1,(name,len(v));return v.iloc[0].id
# Complete published factual Table4 (twelve rows across PDF pages14–15).
rail=[('Мытищи',1020.9,1029.5,7.1,6.2,14),('Железнодорожный',940.4,961.3,6.5,5.7,14),('Королев',859.5,880.6,6.0,5.3,14),('Одинцово',804.4,745.6,5.6,4.5,14),('Люберцы',690.9,677.0,4.8,4.0,14),('Подольск',606.5,630.6,4.2,3.8,15),('Балашиха (без учета Железнодорожного)',479.4,458.6,3.3,2.7,15),('Химки',450.8,504.6,3.1,3.0,15),('Красногорск',437.4,476.1,3.0,2.8,15),('Пушкино',417.5,488.1,2.9,2.9,15),('Долгопрудный',395.6,413.4,2.8,2.5,15),('Раменское',347.4,383.7,2.4,2.3,15)]
rows=[]
for name,feb,jul,sfeb,sjul,page in rail:
 needle='Королев' if name=='Королев' else name
 assert needle in ' '.join(texts[13:15]),name
 for v in [feb,jul,sfeb,sjul]:assert str(v).replace('.',',') in ' '.join(texts[13:15]),(name,v)
 rows.append(dict(source_name=name,flow_feb2014_thousand_passengers=feb,flow_jul2014_thousand_passengers=jul,share_feb2014_percent=sfeb,share_jul2014_percent=sjul,measurement_period='2014-02/2014-07',source_kind='RZD rail passenger statistics reproduced and analyzed by authors',source_grain='city_or_urban_okrug_station_passenger_context',denominator='total Moscow Oblast-to-Moscow suburban rail passenger flow in corresponding month; not population or employed residents',counts_are_unique_persons=False,counts_are_observed_home_work_commuters=False,mobile2015_measurement=False,pdf_page=page,locator='Table4; begins PDFp14, continues PDFp15',source_url=SOURCE,source_sha256=sha(PDF),population_cause_asserted=False))
pd.DataFrame(rows).to_parquet(H/'published_table4_rail2014.parquet',index=False);pd.DataFrame(rows).to_csv(H/'published_table4_rail2014.csv',index=False)
# Explicit named mobile shares only; no regression inversion or reading unlabelled dots.
mobile=[]
for name,value in [('Буньковское сельское поселение',9.9),('Солнечногорск',46.0),('Монино',36.4),('Подольск',68.6)]:
 assert str(value).replace('.',',')+'%' in texts[10]
 mobile.append(dict(named_area=name,context_NP_id=None if name.startswith('Буньков') else uid(name),moscow_share_of_outbound_commuters_percent=value,measurement_period='2015-11',publication_period='2017-05-01/2017-05-21',source_grain='municipal urban/rural settlement or urban okrug; not necessarily censusNP',denominator='all outbound home-work commuters from named municipality, NOT residents or working-age population',pdf_page=11,locator='paragraph beginning Так, при схожей удаленности',source_url=SOURCE,source_sha256=sha(PDF),national_commuting_observed_mutated=False))
pd.DataFrame(mobile).to_parquet(H/'explicit_mobile2015_named_shares.parquet',index=False)
# Requested six names: a map is published, but no recoverable named exact share table.
targets=[]
for name in ['Одинцово','Мытищи','Красногорск','Химки','Реутов']:
 rr=next((x for x in rows if x['source_name']==name),None)
 targets.append(dict(name=name,context_NP_id=uid(name),source_has_mobile2015_map=True,source_has_mobile2015_municipal_share_map=True,published_share_map_classes='<20%;20–40%;40–60%;60–80%;>80%',individual_map_band_digitized=False,mobile_map_locator='Figure7 PDFp13, municipality share classes; Figure1 PDFp7, absolute flows',explicit_named_mobile2015_share_published=False,exact_mobile2015_share=None,mobile_map_numerator='number working in old Moscow, thousand persons',mobile_map_denominator=None,share_map_denominator='all commuters leaving the municipality for work; NOT all residents',share_map_pdf_page=13,why_not_exact_share='Figure7 depicts municipal share bands, not exact percentages; no independently reviewed historical polygon matching/digitization completed; scatterplot dots are unlabelled; underlying OD table is not published',rail2014_table4_present=rr is not None,rail_locator=rr['locator'] if rr else None,scope_warning='NP ID is a literal-name geographic reference, not a verified historical municipality-to-NP crosswalk; no attribution to every NP resident',source_url=SOURCE,source_sha256=sha(PDF),national_commuting_observed_mutated=False))
pd.DataFrame(targets).to_parquet(H/'requested_target_assessments.parquet',index=False);pd.DataFrame(targets).to_csv(H/'requested_target_assessments.csv',index=False)
mapfacts={'source_url':'https://www.demoscope.ru/weekly/2017/0727/img/t_graf01.jpg','sha256':sha(RAW/'map01.jpg'),'bytes':(RAW/'map01.jpg').stat().st_size,'locator':'Figure1, PDFp7','year':2015,'grain':'MoscowOblast municipalities, NOT NP-level OD','destination':'old Moscow boundaries','metric':'number of commuters working in old Moscow, thousand persons','bands':['<1.0','1.1–5.0','5.1–10.0','10.1–25.0','25.1–50.0','50.1–100.0','>=100.1'],'denominator':None,'numeric_municipal_rows_digitized':False,'reason':'arrow overlaps and municipality boundaries do not permit reliable exact per-NP shares; map categories are not individual counts'}
dump('published_map_scope.json',mapfacts)
sharemap={'source_url':'https://www.demoscope.ru/weekly/2017/0727/img/t_graf07.jpg','sha256':sha(RAW/'map07.jpg'),'bytes':(RAW/'map07.jpg').stat().st_size,'locator':'Figure7, PDFp13','year':2015,'grain':'municipal urban/rural settlements and urban okrugs in MoscowOblast; NOT NP-level OD','numerator':'commuters working in Moscow','denominator':'all commuters leaving the municipality for work','metric':'percent','bands':['<20','20–40','40–60','60–80','>80'],'exact_values_published':False,'individual_target_bands_digitized':False,'boundary_inclusivity':'legend leaves exact20/40/60/80 boundary inclusion unspecified','model_inputs_changed':False}
dump('published_share_map_scope.json',sharemap)
source={'status':'PUBLISHED_PRIMARY_MAP_AND_EXPLICIT_CASES_RECOVERED_NOT_FULL_MUNICIPAL_OD','title':'Маятниковая миграция в Московском регионе: новые данные','authors':['Махрова А.Г.','Бочкарев А.Н.'],'publication':'Демоскоп Weekly №727–728,1–21мая2017','pdf_url':SOURCE,'pdf_bytes':PDF.stat().st_size,'pdf_sha256':sha(PDF),'pdf_pages':len(d),'source_methods_page':4,'method':'DIT Moscow anonymized big-three operator data, aggregated home-work matrix, 500m cells; aggregated temporal and municipal reports; no raw subscriber data acquired','mobile_main_snapshot':'November2015 (PDFp6); seasonal comparisons separately labeled','published_complete_municipal_share_map':'Figure7, PDFp13; five class bands and explicit denominator; original bytes acquired', 'full_named_mobile_OD_table_published_in_this_article':False,'explicit_mobile_named_cases':len(mobile),'requested_target_names':len(targets),'rail2014_table4_rows':len(rows),'data_not_interchangeable':'Rail2014 passengers include repeated travel and nonwork purposes; cannot substitute for mobile2015 worker shares','national_commuting_observed_mutated':False,'thresholds_changed':False,'model_inputs_changed':False,'raw_sources_cache':str(RAW),'independence':'These published observations were inspected during development; they are external evidence, not a blinded holdout','scope':'Municipal context, no causal interpretation and no forced assignment of Word type or NP commuting flags'}
dump('source_manifest.json',source)
print('BUILT',len(rows),'rail rows;',len(mobile),'named mobile cases;',len(targets),'target assessments')

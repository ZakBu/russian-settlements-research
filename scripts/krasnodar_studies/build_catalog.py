"""Build source-backed comparison layers, never inferred agglomeration polygons.

Inputs: accepted census wide Parquet; pinned ADM2 GeoJSON; five Nominatim
lookup/search JSON responses stored by name. Run with --raw-dir and --output.
Nominatim raw responses and generated geography belong in a versioned release.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import pyarrow.parquet as pq
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
ADM_SHA = '3c8dd7b7d6977c506c0cfb2c1b3a328df6abd585a709a468648a5e3566ff1bad'
CENSUS_URL = 'https://github.com/ZakBu/russian-settlements-research/releases/tag/sgrt-census-population-20261022-v1'
IUE_URL = 'https://www.urbaneconomics.ru/sites/default/files/dolgosrochnye_trendy_v_ekonomike_zhilishchnoi_i_gradostroitelnoi_sferah_krupneishih_gorodskih_aglomeracii_rossii_2023.pdf'
STRATEGY_URL = 'https://kuban.lc-av.ru/wp-content/uploads/2021/05/K30.-Strategy-210222-01_compressed.pdf'
ACCESS_URL = 'https://kubsau.ru/upload/iblock/9ad/9add66e6d6bda2fdb567002cadc0eb84.pdf'
YABL_URL = 'https://oreluniver.ru/public/file/archive/mtitm_ZHURNAL_3-1%2890%29_merged.pdf'
COMMON = ['r269701','r364116','r364150','r365144','r1850083','r365285','r953560']
EXTRA = ['r919011','r953559']
YABL_IDS = {'Яблоновское':5442463,'Старобжегокайское':5442459,'Тахтамукайское':5442460,'Афипсипское':5442457,'Адыгейск':1850083}
# Exact transcription of table 3, pp.204–205; minutes and km refer to 2019 publication.
POINTS = [
 ('Тимашевск',70,80,85,90,90),('Кореновск',67,80,80,100,90),
 ('Усть-Лабинск',70,82,90,93,90),('Горячий Ключ',60,79,100,85,90),
 ('Медведовская',50,60,63,None,60),('Динская',40,50,50,56,None),
 ('Васюринская',47,53,65,60,60),('Адыгейск',42,50,60,None,60),
 ('Северская',36,38,40,55,60),('Новомышастовская',42,50,60,None,60),
 ('Старокорсунская',32,35,38,None,30),('Тлюстенхабль',26,30,40,None,30),
 ('Яблоновский',15,27,43,None,30),('Марьянская',33,37,37,None,30),
 ('Новотитаровская',26,32,31,40,30)]


def dump(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')


def build(args):
    args.output.mkdir(parents=True,exist_ok=True)
    raw=args.adm2.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==ADM_SHA, 'Unpinned reference boundaries'
    refs={f['properties']['adm2_id']:f for f in json.loads(raw)['features']}
    studies=[]
    common_limit='Показан опубликованный состав на справочных контурах 28.09.2026. Историческая геометрия соответствующего года не восстановлена; реальные поездки здесь не измерены.'
    for study_id,title,year,ids,source,ref,summary,scope in [
      ('ieg-2018','ИЭГ и ДОМ.РФ: состав 2018 года',2018,COMMON+EXTRA,IUE_URL,'IUE_AGGLOMERATION_TRENDS2023','Девять муниципалитетов, использованных в сравнительном исследовании 2018 года. В последующем составе из него исключили Усть-Лабинский и Красногвардейский районы.','Первичный PDF ИЭГ 2023: приложение 5.1 и сравнительная таблица на печатных с. 59–61; состав 2018 воспроизведён в таблице, исходный отчёт 2018 здесь не прочитан.'),
      ('ieg-2023','Институт экономики города: состав 2023 года',2023,COMMON,IUE_URL,'IUE_AGGLOMERATION_TRENDS2023','Семь муниципалитетов, принятых ИЭГ в исследовании 2023 года. Авторы используют состав по документам планирования, без дополнительных изменений для Краснодара.','Первичный PDF: титул, методология с. 3, приложение 5.1 и сравнительная таблица с. 59–61.'),
      ('strategy-2017','Кубань-2030: стратегическая экономическая зона',2017,COMMON,STRATEGY_URL,'LCAV_KUBAN2030_SPATIAL2017','Семь муниципалитетов, предложенных разработчиком стратегии для совместного развития. Состав совпадает с вариантом ИЭГ 2023 года, но источник и задача другие.','Первичный PDF разработчика: титул © 2017 и слайды 59–60; данные на 2016 год. Дата в пути URL не считается датой документа.')]:
        features=[]
        for fid in ids:
            f=copy.deepcopy(refs[fid]); assert f['properties']['unit_key']=='RUS'
            f['properties'].update(id=fid,name=f['properties']['name'],studyId=study_id,studyTitle=title,sourceUrl=source,sourceReferenceId=ref,geometryDate='2026-09-28',geometryMeaning='Справочная муниципальная территория; не граница по наблюдаемым поездкам')
            assert shape(f['geometry']).is_valid
            features.append(f)
        filename=study_id+'.geojson';dump(args.output/filename,{'type':'FeatureCollection','features':features})
        studies.append(dict(id=study_id,title=title,year=year,authors='Консорциум Леонтьевский центр – AV Group' if year==2017 else 'Фонд «Институт экономики города»',sourceUrl=source,sourceDate='2017' if year==2017 else '2023',sourceDatePrecision='year',readScope=scope,summary=summary,whatBoundaryMeans='Перечень муниципальных участников стратегической экономической зоны.' if year==2017 else 'Муниципальный состав, используемый для сопоставления экономики, жилья и градостроительства.',geometryKind='polygon',geometryUrl=filename,geometryDate='2026-09-28',geometryDatePrecision='day',limitations=[common_limit,'Контур Горячего Ключа подписан по современному типу муниципального образования; административная история не реконструирована.'],sourceReferenceId=ref,featureCount=len(features),geometrySource='Terrae 2026.10 / OpenStreetMap',geometrySourceUrl='https://github.com/ZakBu/russian-settlements-research/releases/download/atlas-boundaries-20261026-v1/RUS-adm2.geojson',geometrySourceSha256=ADM_SHA))
    cols=['source_record_id_2021','settlement_name_2021','region_norm_2021','district_raw_2021','accepted_latitude_2021','accepted_longitude_2021']
    rows=pq.read_table(args.census,columns=cols).to_pylist()
    features=[]
    for i,(name,km,car,bus,rail,belt) in enumerate(POINTS,1):
        region='адыгея' if name in ['Адыгейск','Тлюстенхабль','Яблоновский'] else 'краснодарский'
        matched=[r for r in rows if r['settlement_name_2021']==name and r['region_norm_2021']==region]
        assert len(matched)==1,(name,len(matched))
        row=matched[0];lon=row['accepted_longitude_2021'];lat=row['accepted_latitude_2021']
        assert 38<lon<40 and 44<lat<46
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},'properties':dict(id='access2019-'+str(i),studyId='accessibility-2019',name=name,sourceUrl=ACCESS_URL,sourceReferenceId='GOVERDOVSKAYA_YAROTSKAYA2019',tableRow=i,distanceKm=km,carMinutes=car,busMinutes=bus,railMinutes=rail,authorsBeltMinutes=belt,tableYear=2019,source_record_id=row['source_record_id_2021'],censusYear=2021,region=region,district=row['district_raw_2021'],coordinateSource='Принятая база переписей, точка записи 2021 года',coordinateSnapshotDate='2026-10-13',geometryMeaning='Точка рассмотренного в статье НП; не оцифрованная граница авторов',classificationIssue='Превышает заявленный авторами 30-минутный пояс по всем опубликованным видам транспорта' if belt==30 and car>30 else ('В таблице есть, в словесном перечне поясов не указан' if belt is None else None))})
    dump(args.output/'accessibility-2019.geojson',{'type':'FeatureCollection','features':features})
    studies.append(dict(id='accessibility-2019',title='Говердовская и Яроцкая: транспортная доступность',year=2019,authors='М. Д. Говердовская; Е. В. Яроцкая',sourceUrl=ACCESS_URL,sourceDate='2019',sourceDatePrecision='year',readScope='Полный первичный текст с. 199–206; таблица 3 с. 204–205 и рисунок 1 на с. 205 визуально проверены.',summary='Пятнадцать пригородных населённых пунктов, рассмотренных в статье по времени поездки в Краснодар. По клику доступны опубликованные времена на автомобиле, автобусе и поезде; исходные пояса не заменены новым полигоном.',whatBoundaryMeans='В статье предложены пояса 30, 60, 90 минут. В этом слое показаны только рассмотренные точки, поскольку точный цифровой контур авторов не опубликован.',geometryKind='point',geometryUrl='accessibility-2019.geojson',geometryDate='2026-10-13',geometryDatePrecision='day',limitations=['Рисунок представляет небольшой растровый скриншот без координатной сетки; исходная геометрия авторов не получена и не оцифрована.','Координаты взяты из принятой базы переписи2021 года, а времена — из статьи 2019 года; современные времена не измерялись.','Три из пяти точек первого пояса превышают 30 минут в собственной таблице авторов; Динская есть в таблице, но пропущена в словесном перечне поясов.','Нет точной даты/часа измерений; авторский полигон и фактические изохроны не восстановлены.'],sourceReferenceId='GOVERDOVSKAYA_YAROTSKAYA2019',featureCount=15,geometrySource='Принятая база переписей 2002/2010/2021, срез 2026-10-13',geometrySourceUrl=CENSUS_URL))
    features=[]
    for prefix,osm_id in YABL_IDS.items():
        path=args.raw_dir/('nominatim-'+prefix+'.json');responses=json.loads(path.read_text())
        matching=[r for r in responses if r['osm_type']=='relation' and r['osm_id']==osm_id and r['type']=='administrative' and 'Адыгея' in r['display_name']]
        assert len(matching)==1,(prefix,matching)
        r=matching[0];geom=r['geojson'];assert geom['type'] in ['Polygon','MultiPolygon'];assert shape(geom).is_valid
        features.append({'type':'Feature','geometry':geom,'properties':dict(id='r'+str(osm_id),studyId='yablonovskaya-2025',name=r['name'],osmRelation=osm_id,osmUrl='https://www.openstreetmap.org/relation/'+str(osm_id),sourceUrl=YABL_URL,sourceReferenceId='KHAZHOKOVA_TKACHEVA2025_YABLONOVSKAYA',geometryDate='2026-10-31',geometryMeaning='Состав из научной статьи 2025 года на актуальных контурах OSM; историческая точность не установлена',geometrySource='OpenStreetMap / Nominatim',rawSha256=hashlib.sha256(path.read_bytes()).hexdigest())})
    dump(args.output/'yablonovskaya-2025.geojson',{'type':'FeatureCollection','features':features})
    studies.append(dict(id='yablonovskaya-2025',title='Хажокова и Ткачева: Яблоновская агломерация',year=2025,authors='С. С. Хажокова; Я. С. Ткачева',sourceUrl=YABL_URL,sourceDate='2025',sourceDatePrecision='year',readScope='Первичный PDF журнала: содержательные с. 58–63, 65–66; перечень пяти МО на с. 58–59.',summary='Пять муниципалитетов Адыгеи, перечисленных авторами при анализе транспортного обслуживания. Это отдельный исследовательский контур южнее Краснодара; сама статья описывает его транспортные связи с городом.',whatBoundaryMeans='Муниципальный состав в исследовании транспортного обслуживания, а не самостоятельно проверенная юридическая граница агломерации.',geometryKind='polygon',geometryUrl='yablonovskaya-2025.geojson',geometryDate='2026-10-31',geometryDatePrecision='day',limitations=['Перечень статьи 2025 года показан на актуальных контурах OSM, полученных 31.10.2026; геометрия 2025 года не восстановлена.','Численный критерий включения пяти МО и акт утверждения границ в статье не установлены.','Энемское и Козетское поселения отдельно не названы; они не дописаны по догадке.','Дата исходных обследований не установлена; пассажиропотоки нельзя автоматически датировать 2025 годом.'],sourceReferenceId='KHAZHOKOVA_TKACHEVA2025_YABLONOVSKAYA',featureCount=5,geometrySource='OpenStreetMap / Nominatim',geometrySourceUrl='https://nominatim.openstreetmap.org/',geometryAttribution='© OpenStreetMap contributors, ODbL 1.0'))
    for s in studies:
        p=args.output/s['geometryUrl'];s['geometrySha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    dump(args.output/'studies.json',studies)
    print(json.dumps({'studies':len(studies),'featureCounts':{s['id']:s['featureCount'] for s in studies}},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adm2',type=Path,default=ROOT/'.research-cache/site/districts.geojson')
    p.add_argument('--census',type=Path,default=ROOT/'.research-cache/site/inputs/data/population/settlements_census_wide.parquet')
    p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    build(p.parse_args())

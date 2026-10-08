"""One bounded batch of own-place articles, normal TLS, at most50 titles."""
from pathlib import Path
import datetime,gzip,hashlib,json,urllib.request,urllib.parse
OUT=Path(__file__).resolve().parent
TITLES=['Газ-Сале','Каменномост','Берёзовка (Бийский район)','Берёзовка (городской округ Бийск)',
 'Кузнечиха (Ярославский район)','Савино (Пермский район)','Беломестное (Орёл)','Зареченский (Орловская область)',
 'Хардиково','Авангард (Приморский край)','Озёрный (Мордовия)','Садовый (Минераловодский район)',
 'Зональный (Краснодарский край)','Центральный (Суворовский район)','Метлино (Челябинская область)',
 'Энергетик (Башкортостан)','Круглое Поле','Мочище (посёлок)','Казачьи Лагери','Чайковская (станция)',
 'Донское (Калининградская область)','Агроном (Липецкая область)','Ново-Писцово','Заклинье (Лужский район)',
 'Успенский (Московская область)','Двинской','Селекционной станции (Нижегородская область)',
 'Солидарность (посёлок)','Архангельское (Кимовский район)','Молодёжный (Московская область)',
 'Майский (Тульская область)','Посёлок имени Калинина (Нижегородская область)','Озёрки (Конаковский район)',
 'Первомайское (Тамбовская область)','Газ-Сале','Чална-1','Тальжино','Туношна-городок 26',
 'Белово (Алтайский край)','Уташ','Лумку-Корань','Урми (станция)','Ергач (станция)',
 'Старые Турбаслы','Тихоновка (Татарстан)','Синезерки','Горелки (Тула)','Октябрьский (Тульская область)',
 'Иншинский','Косая Гора']
TITLES=list(dict.fromkeys(TITLES));assert len(TITLES)<=50
def main():
    url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(dict(action='query',titles='|'.join(TITLES),prop='revisions|pageprops|coordinates',rvprop='ids|content|timestamp',rvslots='main',format='json',redirects=1,colimit='max'))
    request=urllib.request.Request(url,headers={'User-Agent':'SettlementResearch/1.0'})
    with urllib.request.urlopen(request,timeout=35) as response:body=response.read(6500000);status=response.status
    target=OUT/'own_wikipedia_batch.json.gz';target.write_bytes(gzip.compress(body,mtime=0));pages=json.loads(body).get('query',{}).get('pages',{})
    receipt=dict(status='captured_one_bounded_own_place_batch',UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),normal_TLS_verification=True,
        requested_titles=TITLES,request_url=url,HTTP_status=status,uncompressed_bytes=len(body),compressed_bytes=target.stat().st_size,
        captured_source_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),pages=[dict(title=p['title'],pageid=p.get('pageid'),missing='missing' in p,revid=p.get('revisions',[{}])[0].get('revid')) for p in pages.values()])
    (OUT/'fetch_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'titles':len(TITLES),'pages':receipt['pages']},ensure_ascii=False))
if __name__=='__main__':main()

from pathlib import Path
import pandas as pd,json,gzip,urllib.request,concurrent.futures,re,html
O=Path(__file__).parent;h=pd.read_csv(O/'article_binding_holds.csv.gz',keep_default_na=False);h=h[h.population.ge(400)&h.hold_reasons.str.contains('homonym|multiple_positive')].drop_duplicates('source_record_id');manifest=[]
def get(z):
 own=json.loads(z['native_primary_row_json']);code=str(own['oktmo']);code=code.zfill(11) if code.isdigit() and len(code) in [10,11] else code;u='https://classinform.ru/oktmo/'+code+'.html';p=O/f'homonym_owncode_{code}.html.gz'
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 (+bounded owncode context)'}),timeout=25).read(250000);p.write_bytes(gzip.compress(b,mtime=0));txt=html.unescape(re.sub('<[^>]+>',' ',b.decode('cp1251',errors='replace')));txt=re.sub(r'\s+',' ',txt);m=re.search(r'Пояснение:\s*([^<]+?)(?:Полная расшифровка|Комментарии|Другие коды|$)',txt);note=m[1].strip() if m else '';return {'source_record_id':z['source_record_id'],'native_owncode':code,'url':u,'file':str(p),'context_note':note,'dated_code_excerpt':txt[max(0,txt.find('Код ОКТМО '+code)):txt.find('Полная расшифровка')],'fetched_successfully':True}
 except Exception as ex:return {'source_record_id':z['source_record_id'],'native_owncode':code,'url':u,'failure':type(ex).__name__+':'+str(ex)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as t:r=list(t.map(get,h.to_dict('records')))
(O/'homonym_owncode_context_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False))

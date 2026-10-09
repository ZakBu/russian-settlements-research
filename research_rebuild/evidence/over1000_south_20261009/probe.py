from pathlib import Path
import pandas as pd,xlrd,json,re,hashlib,urllib.request,urllib.parse
Z=Path(__file__).parent;A=Z.parent/'main_axis_residual_application68_20261008';L=Z.parent/'next69_capacity_20261009/actual68_remaining_over1000.csv'
o=pd.read_parquet(A/'applied_state_observations.parquet');d=pd.read_csv(L);d=d[d.region_norm.isin(['краснодарский','ростовская','дагестан'])].copy();assert len(d)==58
books={};w=[]
for x in d.itertuples():
 p=Path('/workspace/settlements-raw')/x.source_file
 if x.census_year==2021:continue
 parts=x.source_record_id.split(':');sname=parts[-2];row=int(parts[-1]);b=books.setdefault(str(p),xlrd.open_workbook(p));s=b.sheet_by_index(int(sname)) if sname.isdigit() and sname not in b.sheet_names() else b.sheet_by_name(sname);vals=s.row_values(row-1);ctx=[{'row':i+1,'cells':s.row_values(i)} for i in range(max(0,row-7),min(s.nrows,row+2))];head=[{'row':i+1,'cells':s.row_values(i)} for i in range(row-1) if any(t in str(s.row_values(i)) for t in ['район','сельсов','сельский округ','подчин','г.','города','Городу','городской округ'])][-12:]
 w.append({'source_record_id':x.source_record_id,'source_file':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_sheet':s.name,'source_row_1based':row,'source_literal_cells_json':json.dumps(vals,ensure_ascii=False),'source_context_json':json.dumps(ctx,ensure_ascii=False),'source_header_path_json':json.dumps(head,ensure_ascii=False)})
pd.DataFrame(w).to_csv(Z/'literal_native_source_rows.csv.gz',index=False,compression={'method':'gzip','mtime':0});d.to_csv(Z/'all58_actual68_residual_membership.csv',index=False)
# Full native all-year namesakes are retained; similarity is not admission.
matchnames=['Манас','Манаскент','Гоцатль','Араблин','Арабляр','Ачису','Цияб','Гельбах','Банайюрт','Ахар','Новососит','Новосас','Уллу-Теркеме','Уллутеркеме','Герейхан','Отделение Совхоза','Львовский','Новокрест','Шушия','Ямансу','Шодрода','Шадрода','Дучи','Зори','Талги','Казачьи Лагери','Барановка','Красноярская','Зональный','Лорис','Алмазный','Заречный','Первомайский','Октябрьский','Соленовская','Трудовой','Саук','Темерницкий','Уташ','Бичев','Бичевой','Железнодорожный','Хуторской','Северный','Россошин','Новоселый','Николаевский','Садовый']
m=o[o.region_norm.isin(['краснодарский','ростовская','дагестан']) & o.settlement_name.str.contains('|'.join(map(re.escape,matchnames)),case=False,na=False)];m.to_csv(Z/'all_native_name_type_county_rivals.csv.gz',index=False,compression={'method':'gzip','mtime':0})
print('oldrows',len(w),'rivals',len(m));print(pd.DataFrame(w)[['source_record_id','source_literal_cells_json','source_header_path_json']].to_json(orient='records',force_ascii=False)[:100])
# Specific own articles, not search-first ties.
titles=['Манас (Дагестан)','Манаскент','Ачису','Большой Гоцатль','Араблинское','Цияб-Цолода','Гельбах','Банайюрт','Новососитли','Уллу-Теркеме','Герейхановское 2-е','Львовский № 1','Новокрестьяновское','Шушия','Шодрода','Дучи','Талги','Казачьи Лагери','Барановка (Хостинский район)','Барановка (Лазаревский район)','Красноярская','Зональный (Краснодар)','Лорис','Алмазный (Ростовская область)','Заречный (Белореченский район)','Первомайский (Горячий Ключ)','Октябрьский (хутор, Краснодар)','Солёновская','Трудовой (Ростовская область)','Саук-Дере','Темерницкий','Уташ','Бичевой','Железнодорожный (Зерноградский район)','Хуторской (Ростовская область)','Северный (Курганинский район)','Россошинский 1-й','Новосёлый 1-й','Николаевский (Пролетарский район)','Садовый (Крымский район)']
for batch in range(0,len(titles),10):
 names=titles[batch:batch+10];params={'action':'query','titles':'|'.join(names),'prop':'revisions|pageprops','rvprop':'content|ids|timestamp','rvslots':'main','format':'json','formatversion':'2','redirects':1};url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params);f=Z/f'wiki_articles_{batch//10:02}.json'
 if f.exists():continue
 try:
  response=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LocalityCensusEvidence/1.0'}),timeout=25);payload=response.read(1800000);f.write_bytes(payload);print(f.name,response.status,len(payload),flush=True)
 except Exception as e:print(type(e).__name__,str(e),flush=True)

from pathlib import Path
import pandas as pd,xlrd,json,hashlib,urllib.request,urllib.parse
Z=Path(__file__).parent;A=Z.parent/'main_axis_residual_application68_20261008';o=pd.read_parquet(A/'applied_state_observations.parquet');r=pd.read_csv(Z.parent/'over1000_root_20261009/handoff_south_other_actual101_roster.csv')
titles=['Синезерский','Березичский Стеклозавод','Резвань','Новый (Тахтамукайский район)','Красносельское (Кабардино-Балкария)','Учебное','Янтарное (Кабардино-Балкария)','Новый Беной','Червлённая-Узловая','Терский (Будённовский район)','Терский (Георгиевский район)','Сонский сельсовет','Озёрское (Сахалинская область)','Третий Северный','Северное (Калмыкия)','Арыг-Узю','Лондоко-завод','Козловка (Михайловский район)','Сятракасы (Чебоксарский район)','Берд-Юрт','Южное (Ингушетия)','Новый Бельтир','Павлоградка']
for b in range(0,len(titles),6):
 f=Z/f'wiki_{b//6}.json';params={'action':'query','titles':'|'.join(titles[b:b+6]),'prop':'revisions|pageprops','rvprop':'content|ids|timestamp','rvslots':'main','format':'json','formatversion':'2','redirects':1};url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params)
 if not f.exists():
  try:f.write_bytes(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LocalityCensusEvidence/1.0'}),timeout=30).read());print(f,len(f.read_bytes()),flush=True)
  except Exception as e:print(e,flush=True)
books={};w=[]
x=pd.read_csv(Z/'name_candidates.csv'); ids=set(x.source_record_id)|set(r.source_record_id)
for reg,term in [('кабардино балкарская','красносель|учебн|янтарн'),('калужская','березич'),('тыва','арыг.уз'),('сахалинская','озерск')]:ids.update(o[o.region_norm.eq(reg)&o.name_norm.fillna('').str.contains(term)].source_record_id)
for uid in ids:
 z=o[o.source_record_id.eq(uid)]
 if z.empty or uid.startswith('2021:'):continue
 z=z.iloc[0];p=Path('/workspace/settlements-raw')/z.source_file
 if not p.exists():continue
 parts=uid.split(':');sname=parts[-2]
 try:
  row=int(parts[-1]);book=books.setdefault(str(p),xlrd.open_workbook(p));s=book.sheet_by_index(int(sname)) if sname.isdigit() and sname not in book.sheet_names() else book.sheet_by_name(sname)
  ctx=[{'row':i+1,'cells':s.row_values(i)} for i in range(max(0,row-8),min(s.nrows,row+3))];heads=[{'row':i+1,'cells':s.row_values(i)} for i in range(row-1) if any(t in str(s.row_values(i)).lower() for t in ['район','сельсов','сельский округ','сельское посел','подчин','города','городской округ'])][-12:]
  w.append({'source_record_id':uid,'source_file':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_sheet':s.name,'source_row':row,'literal_cells':json.dumps(s.row_values(row-1),ensure_ascii=False),'context':json.dumps(ctx,ensure_ascii=False),'heads':json.dumps(heads,ensure_ascii=False)})
 except Exception as e:print(uid,e)
pd.DataFrame(w).to_csv(Z/'literal_source_witnesses.csv',index=False)

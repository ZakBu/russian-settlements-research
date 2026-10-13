from pathlib import Path
import pandas as pd,xlrd,json,hashlib,re
Z=Path(__file__).parent;A=Z.parent/'main_axis_residual_application68_20261008';o=pd.read_parquet(A/'applied_state_observations.parquet');w=[];sc=[]
checks=[('Берд-Юрт','ингушетия',['берд','berd']),('Южное','ингушетия',['южн','усадьб','мтс']),('Резвань','калужская',['резван']),('Новый Беной','чеченская',['новый беной','ново беной','беной','центор','центора']),('Новый Бельтир','алтай',['бельтир','белтир'])]
for title,reg,terms in checks:
 for year in [2002,2010,2021]:
  q=o[o.region_norm.eq(reg)&o.census_year.eq(year)];m=q[q.name_norm.fillna('').apply(lambda s:any(t in s for t in terms))];sc.append(dict(scope_id=title,census_year=year,native_region_records_screened=len(q),known_aliases=json.dumps(terms,ensure_ascii=False),retained_rivals=json.dumps(m.source_record_id.tolist()),selected_scope='certified68 native observations publication scope; no physical/legal absence asserted'))
  if year!=2021:
   for file in q.source_file.dropna().unique():
    p=Path('/workspace/settlements-raw')/file
    if not p.exists() or p.suffix.lower()!='.xls':continue
    b=xlrd.open_workbook(p)
    for s in b.sheets():
     # Full printed sheet screen records matches, even unparsed rows.
     found=[]
     for i in range(s.nrows):
      c=s.row_values(i); t=' '.join(str(a).lower().replace('-',' ') for a in c[:7]);
      if any(a in t for a in terms):found.append(dict(row=i+1,cells=c[:8]))
     w.append(dict(scope_id=title,census_year=year,file=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),sheet=s.name,rows_screened=s.nrows,alias_rivals_json=json.dumps(found,ensure_ascii=False)))
pd.DataFrame(sc).to_csv(Z/'complete_selected_publication_scans.csv',index=False);pd.DataFrame(w).to_csv(Z/'complete_printed_source_alias_scans.csv',index=False)
# Fresh finite source row witness for explicit rename rather than relying on provider pointers.
uid='2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1548';a=o[o.source_record_id.eq(uid)].iloc[0];p=Path('/workspace/settlements-raw')/a.source_file;s=xlrd.open_workbook(p).sheet_by_name('СК');i=1547
(Z/'centora_literal2010.json').write_text(json.dumps(dict(source_record_id=uid,file=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),locator='СК row1548 1based',context=[dict(row=j+1,cells=s.row_values(j)[:8]) for j in range(i-5,i+5)]),ensure_ascii=False,indent=2))

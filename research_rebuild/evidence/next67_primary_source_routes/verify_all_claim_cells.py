from pathlib import Path
import pandas as pd,xlrd,email,json,hashlib,re
from bs4 import BeautifulSoup
E=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();d=pd.read_csv(E/'ready_primary2010_regional_claims.csv.gz');b=xlrd.open_workbook(E/'perm_2010_original_archived.xls');s=b.sheet_by_name('01-04');msg=email.message_from_bytes((E/'prim_2010_original_archived.mht').read_bytes());part=next(p for p in msg.walk()if p.get_content_type()=='text/html'and 'sheet001' in p.get('Content-Location',''));table=BeautifulSoup(part.get_payload(decode=True).decode(part.get_content_charset()),'html.parser').find('table');trs=table.find_all('tr');v=lambda x:int(float(str(x).replace(' ','')))if re.fullmatch(r'\d+(?:\.0)?',str(x).replace(' ',''))else None
checks=[]
for r in d.itertuples():
 raw=s.row_values(int(r.official_source_row)-1)[:4]if r.region=='пермский'else[c.get_text(' ',strip=True)for c in trs[int(r.official_source_row)-1].find_all(['td','th'],recursive=False)][:4]
 caption=re.sub(r'\s+',' ',str(raw[0])).strip();assert caption==r.official_raw_NP_caption
 for j,k in [(1,'official_population'),(2,'official_men'),(3,'official_women')]:
  expected=getattr(r,k);observed=v(raw[j]);assert (pd.isna(expected)and observed is None)or expected==observed,(r.old_source_record_id,k,expected,observed)
 checks.append({'old_source_record_id':r.old_source_record_id,'official_source_record_id':r.official_source_record_id,'source_locator':r.official_source_locator,'independent_literal_cells_json':json.dumps(raw,ensure_ascii=False),'count_readback':'PASS'})
pd.DataFrame(checks).to_csv(E/'all_claims_independent_literal_cell_readback.csv.gz',index=False)
sample=[]
for reg,g in d.groupby('region'):
 sample.extend(pd.concat([g.nlargest(2,'delta'),g.nsmallest(1,'delta'),g.nsmallest(1,'official_population'),g[g.official_men.isna()|g.official_women.isna()].nsmallest(1,'official_population')]).drop_duplicates('old_source_record_id').to_dict('records'))
pd.DataFrame(sample).to_csv(E/'balanced_primary_source_review.csv',index=False)
r={'status':'PASS_all3066_actual_literal_count_and_caption_cells','claims':len(d),'primary_population':int(d.official_population.sum()),'numeric_total_with_NULL_sex_rows':int((d.official_men.isna()|d.official_women.isna()).sum()),'unknown_sex_not_zero':True,'no_count_used_for_identity':True,'claim_sha256':sha(E/'ready_primary2010_regional_claims.csv.gz'),'output_pins':{x:sha(E/x)for x in ['all_claims_independent_literal_cell_readback.csv.gz','balanced_primary_source_review.csv']}};(E/'all_claims_literal_readback_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,indent=2))

from pathlib import Path
from docx import Document
import pandas as pd,re,json,hashlib
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010/tver_extracted');P=RAW/'pub08-02.docx';OUT=ROOT/'tver';OUT.mkdir(exist_ok=True)
sha=hashlib.sha256((RAW/'pub08-02.doc').read_bytes()).hexdigest();doc=Document(P)
def clean(s):return re.sub(r'\s+',' ',s).strip()
def cells(tr):return [clean(' '.join(c.xpath('.//w:t/text()')))for c in tr.tc_lst]
def num(s):return int(s.replace(' ',''))if s.replace(' ','').isdigit()else None
types={'железнодорожная станция':'железнодорожная станция','железнодорожный разъезд':'железнодорожный разъезд','населенный пункт':'населённый пункт','населённый пункт':'населённый пункт','деревня':'деревня','поселок':'посёлок','посёлок':'посёлок','село':'село','хутор':'хутор','пгт':'пгт','г.':'город','станция':'станция','местечко':'местечко','разъезд':'разъезд','починок':'починок'}
pat=re.compile(r'^('+'|'.join(re.escape(x)for x in sorted(types,key=len,reverse=True))+r')\s*(.+)$',re.I)
county='';municipal='';ti=0;rows=[];controls=[];miss=[]
def make(ti,ri,label,v,county,municipal):
 raw=(v+['','',''])[:3];nn=[num(x)for x in raw]
 return dict(source_record_id=f'TVER2010:pub08-02:table{ti+1}:row{ri+1}',census_year=2010,census_reference_date='2010-10-14',population_scope='permanent_residents_at_census_in_2010_boundaries',region='тверская',source_page=None,source_table=ti+1,source_row=ri+1,raw_caption=label,primary_population=nn[0],primary_men=nn[1],primary_women=nn[2],raw_population=raw[0],raw_men=raw[1],raw_women=raw[2],sex_sum_valid=None if any(x is None for x in nn)else nn[0]==nn[1]+nn[2],official_county=county,official_municipality=municipal,source_sha256=sha,source_path=str(RAW/'pub08-02.doc'),source_grade='official_primary_2010_all_locality_DOC_Tom8',not_model_input_without_root_review=True,blank_or_dash_not_silently_zero=True)
for e in doc.element.body:
 if e.tag.endswith('}p'):
  s=clean(' '.join(e.xpath('.//w:t/text()')))
  if re.fullmatch(r'[А-Яа-яЁё -]+ муниципальный район',s):county=s;municipal=''
 elif e.tag.endswith('}tbl'):
  if ti==8:
   for ri,tr in enumerate(e.tr_lst):
    for label in cells(tr):
     m=re.match(r'^(г\.|пгт\.)\s*(.*?)\s+Всего\s*-\s*(\d+).*?мужчины\s*-\s*(\d+).*?женщины\s*-\s*(\d+)',label)
     if m:
      r=make(ti,ri,m[1]+m[2],[m[3],m[4],m[5]],'Городской округ '+m[2],'');r['source_record_id']+=':'+m[2];r.update(settlement_name=m[2],settlement_type='город'if m[1]=='г.'else'пгт');rows.append(r)
  if ti>=10:
   for ri,tr in enumerate(e.tr_lst):
    cc=cells(tr)
    if not cc:continue
    label=cc[0];m=pat.match(label)
    if re.search(r'(сельское|[Гг]ородское) поселение',label):municipal=label
    if m and len(cc)>=4:
     r=make(ti,ri,label,cc[1:4],county,municipal);r.update(settlement_name=m[2].strip(),settlement_type=types[m[1].lower()]);rows.append(r)
    elif len(cc)>=4 and num(cc[1])is not None:
     controls.append(make(ti,ri,label,cc[1:4],county,municipal))
    elif label and len(cc)>=4 and cc[1] not in ['','Мужчины и женщины, человек'] and not label.startswith(('Продолжение','Окончание')):miss.append([ti+1,ri+1,cc])
  ti+=1
f=pd.DataFrame(rows);c=pd.DataFrame(controls);f.to_parquet(OUT/'primary_source_NP_inventory.parquet',index=False);f.to_csv(OUT/'primary_source_NP_inventory.csv.gz',index=False);c.to_parquet(OUT/'primary_aggregate_controls.parquet',index=False);(OUT/'unparsed_nonempty_rows.json').write_text(json.dumps(miss,ensure_ascii=False,indent=2))
rural=~f.settlement_type.isin(['город','пгт']);r={'source_sha256':sha,'DOCX_derivative_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'literal_NP_rows':len(f),'rural_NP_rows':int(rural.sum()),'official_rural_NP_count':9532,'official_cities_count':23,'official_pgt_count':28,'types':f.settlement_type.value_counts().to_dict(),'numeric_population_NP_rows':int(f.primary_population.notna().sum()),'NULL_dash_blank_NP_rows':int(f.primary_population.isna().sum()),'numeric_population_sum':int(f.primary_population.sum()),'official_region_population':1353392,'numeric_sum_minus_region_control':int(f.primary_population.sum()-1353392),'official_urban_population':1011406,'observed_urban_sum':int(f[~rural].primary_population.sum()),'rural_numeric_population_sum':int(f[rural].primary_population.sum()),'source_grouping_uninhabited_rural_NP_count':2230,'rural_dash_population_NP_count':int((rural & f.raw_population.eq('-')).sum()),'sex_sum_failures':int(f.sex_sum_valid.eq(False).sum()),'missing_district_context_rows':int(f[rural].official_county.eq('').sum()),'unparsed_nonempty_rows':len(miss),'municipal_aggregate_controls_not_promoted':len(c),'dash_interpretation':'NULL; source groupings count provided for independent corroboration; no source dash legend located'};(OUT/'parse_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2))

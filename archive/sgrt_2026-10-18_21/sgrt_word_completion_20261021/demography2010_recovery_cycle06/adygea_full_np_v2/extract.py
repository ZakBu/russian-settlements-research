from pathlib import Path
import pandas as pd,re,json,hashlib,datetime
B=Path(__file__).resolve().parent;D=B.parent;R=D.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'\s+',' ',re.sub(r'[^\w\s]',' ',str(x).casefold().replace('ё','е').replace('ѐ','е'))).strip()
def parent(x):return re.sub(r'\s+',' ',re.sub(r'\b(муниципальный|район|района|городской|городского|округ|округа|г)\b',' ',norm(x))).strip()
source=D/'sources/adygea2010_population_archive.pdf';text=D/'sources/adygea2010_population_layout.txt';axis=R/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet';prior=D/'admitted_overlay_v1/full_axis_primary2010_overlay.parquet'
a=pd.read_parquet(axis);a=a[a.region.eq('адыгея')&a.source_record_id_2010.notna()].copy();a['namekey']=a.name.map(norm);a['typekey']=a.type.map(norm);a['parentkey']=a.district_raw_2010.map(parent)
p=pd.read_parquet(prior).set_index('id');rx=re.compile(r'\s{2,}([0-9]+|-)\s+([0-9]+|-)\s+([0-9]+|-)\s*$');typed=re.compile(r'^(г\.|пгт\.?|село|поселок|посёлок|станица|аул|хутор|деревня)\s+(.+)$',re.I);mp={'г.':'город','пгт.':'пгт','пгт':'пгт','поселок':'посёлок'};rows=[];district=None;settlement=None
for pi,page in enumerate(text.read_text().split('\f'),1):
 for li,line in enumerate(page.splitlines(),1):
  clean=line.strip()
  if 'район' in clean.casefold() and not re.match(r'^(станица|аул|пгт|село|хутор|поселок)',clean,re.I):
   district=re.split(r'\s*(?:–|-)?\s*(?:муниципальный\s+)?район',clean,flags=re.I)[0].strip()
  if re.match(r'^г\. (Майкоп|Адыгейск) с подчиненными',clean):district=re.match(r'^г\. (Майкоп|Адыгейск)',clean)[0]
  m=rx.search(line)
  if not m:continue
  label=line[:m.start()].strip();label='хутор Северо-Восточные Сады – центр поселения' if pi==5 and label=='поселения' and m[1]=='3393' else label;t=typed.match(label);literal=t is not None and 'с подчиненными'not in label.casefold()and'администрации'not in label.casefold()
  typ=mp.get(t[1].casefold(),t[1].casefold())if literal else None;name=re.split(r'\s*[–-]\s*(?:районный центр|центр поселени[яе])',t[2],flags=re.I)[0].strip()if literal else None
  r={'source_row_id':f'ADYGEA2010:pdfpage{pi}:layoutline{li}','source_pdf_page':pi,'source_layout_line':li,'source_label_raw':label,'source_raw_line':line,'source_total_cell_raw':m[1],'source_male_cell_raw':m[2],'source_female_cell_raw':m[3],'population2010':int(m[1])if m[1].isdigit()else None,'male2010':int(m[2])if m[2].isdigit()else None,'female2010':int(m[3])if m[3].isdigit()else None,'source_is_literal_np':literal,'source_type':typ,'source_name':name,'source_native2010_parent_raw':district,'source_pdf_sha256':sha(source) if not rows else rows[0]['source_pdf_sha256'],'source_date':'2010-10-14'};rows.append(r)
d=pd.DataFrame(rows);l=d[d.source_is_literal_np].copy();l['namekey']=l.source_name.map(norm);l['typekey']=l.source_type.map(norm);l['parentkey']=l.source_native2010_parent_raw.map(parent);out=[]
for r in l.to_dict('records'):
 c=a[a.namekey.eq(r['namekey'])&a.typekey.eq(r['typekey'])];s=l[l.namekey.eq(r['namekey'])&l.typekey.eq(r['typekey'])];uid=None;status='unmatched_literal_typed_name'
 if len(c)==1 and len(s)==1:uid=c.iloc[0].id;status='unique_native2010_region_type_name_in_both_full_inventories'
 else:
  cc=c[c.parentkey.eq(r['parentkey'])];ss=s[s.parentkey.eq(r['parentkey'])]
  if r['parentkey']and len(cc)==1 and len(ss)==1:uid=cc.iloc[0].id;status='unique_native2010_region_type_name_parent_in_both_full_inventories'
  elif len(c):status='ambiguous_native2010_identity'
 r.update(strict_uid=uid,identity_status=status,candidate_uids_json=json.dumps(c.id.tolist(),ensure_ascii=False),prior_effective_population2010=p.loc[uid,'reviewed_primary2010_population']if uid else None,prior_effective_quality2010=p.loc[uid,'reviewed_primary2010_quality']if uid else None)
 r['eligible_new_numeric_primary_candidate']=uid is not None and pd.notna(r['population2010'])and r['prior_effective_quality2010']=='secondary_confidentiality_protected_value_exact_scope_unverified';r['prior_primary_conflict']=uid is not None and pd.notna(r['population2010'])and str(r['prior_effective_quality2010'])!='secondary_confidentiality_protected_value_exact_scope_unverified'and r['population2010']!=r['prior_effective_population2010'];out.append(r)
f=pd.DataFrame(out);d.to_parquet(B/'all_source_rows.parquet',index=False);f.to_parquet(B/'all_literal_np_identity_candidates.parquet',index=False);f[f.eligible_new_numeric_primary_candidate].to_parquet(B/'new_numeric_primary_candidates.parquet',index=False);f[f.prior_primary_conflict].to_parquet(B/'prior_primary_conflicts.parquet',index=False)
assert len(f)==232 and f.population2010.sum()==439996
r={'status':'ACTUAL_FULL_REGIONAL_SOURCE_EXTRACTION_PENDING_INDEPENDENT_ADMISSION','source_rows':len(d),'literal_np_rows':len(f),'literal_types':f.source_type.value_counts().to_dict(),'literal_numeric_population_sum':int(f.population2010.sum()),'all_numeric_sex_sums_exact':bool(d.loc[d.population2010.notna()&d.male2010.notna()&d.female2010.notna()].eval('population2010==male2010+female2010').all()),'identity_statuses':f.identity_status.value_counts().to_dict(),'new_numeric_primary_candidates':int(f.eligible_new_numeric_primary_candidate.sum()),'prior_primary_conflicts':int(f.prior_primary_conflict.sum()),'literal_dash_population_unknown':int(f.population2010.isna().sum()),'source_axis_region_native_rows':len(a),'no_model_inputs_or_outcomes_read':True,'no_prior_or_frozen_overlay_mutation':True,'source_scope_caveat':'LiteralNP only; municipality/subordinate totals notNP. Dashes remain unknown.2010physicalscope not automatically2021sameboundary.'};(B/'extraction_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));files=[source,text,axis,prior,*[p for p in B.iterdir()if p.is_file()]];(B/'freeze_manifest.json').write_text(json.dumps({'files_sha256':{str(p):sha(p)for p in files}},ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))

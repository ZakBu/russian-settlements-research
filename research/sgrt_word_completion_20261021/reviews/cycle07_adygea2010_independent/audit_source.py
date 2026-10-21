from pathlib import Path
import fitz,pandas as pd,numpy as np,re,json,hashlib,unicodedata
R=Path(__file__).resolve().parents[2];H=Path(__file__).resolve().parent;D=R/'demography2010_recovery_cycle06';S=D/'adygea_full_np_v3';P=D/'sources/adygea2010_population_archive.pdf'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();checks=[]
def check(name,ok,detail=None):checks.append(dict(check=name,passed=bool(ok),detail=detail))
manifest=json.loads((S/'freeze_manifest.json').read_text())['files_sha256'];before={p:sha(p) for p in manifest};check('all_frozen_inputs_exact',before==manifest)
check('official_pdf_exact_sha',sha(P)=='58527bd270739749a9e5b04ed3f961b19c71a80f24d8b1bba26decf97d711e02')
doc=fitz.open(P);check('full_document_9pages',len(doc)==9);check('date_14October2010_and_units_people','14.10.2010' in doc[1].get_text() and '(человек)' in doc[1].get_text())
# Independent extraction: PDF word coordinate cells, not producer pdftotext/layout or parser.
raw=[];parent=None
for pi,page in enumerate(doc,1):
 words=page.get_text('words');nums=sorted([w for w in words if 360<w[0]<370 and re.fullmatch(r'\d+|-',w[4])],key=lambda w:w[1]);prev=-1
 for ni,total in enumerate(nums):
  y=total[1];trip=[]
  for left,right in [(360,370),(438,446),(502,510)]:
   c=[w for w in words if left<w[0]<right and abs(w[1]-y)<.6 and re.fullmatch(r'\d+|-',w[4])];assert len(c)==1,(pi,y,left,c);trip.append(c[0][4])
  leftwords=sorted([w for w in words if w[0]<350 and prev+.6<w[1]<=y+.6],key=lambda w:(round(w[1],1),w[0]));lines=[]
  for w in leftwords:
   if not lines or abs(lines[-1][0]-w[1])>.6:lines.append([w[1],[w]])
   else:lines[-1][1].append(w)
  ll=[' '.join(w[4] for w in sorted(ws,key=lambda w:w[0])) for yy,ws in lines]
  # Repeated table/title or previous-page continued heading not partof currentNP name.
  typedstarts=[i for i,l in enumerate(ll) if re.match(r'^(?:г\.|пгт\.?|станица|село|пос[её]лок|аул|хутор|деревня)\s',l,re.I)]
  label=' '.join(ll[typedstarts[0]:]) if typedstarts else ' '.join(ll)
  dist=re.search(r'\b(Гиагинский|Кошехабльский|Красногвардейский|Майкопский|Тахтамукайский|Теучежский|Шовгеновский)\s+(?:муниципальный\s+)?район',label,re.I)
  if dist:parent=dist[1]
  cityparent=re.match(r'г\.\s*(Майкоп|Адыгейск)\s+с\s+подчиненными',label,re.I)
  if cityparent:parent=cityparent[1]
  mt=re.match(r'^(г\.|пгт\.?|станица|село|пос[её]лок|аул|хутор|деревня)\s+(.+)$',label,re.I)
  literal=mt is not None and not re.search(r'подчиненн|администраци',label,re.I)
  typ=({'г.':'город','пгт.':'пгт','пгт':'пгт','поселок':'посёлок'}.get(mt[1].lower(),mt[1].lower())) if literal else None
  name=re.split(r'\s*[–-]\s*(?:центр\s+поселени[яе]|районный\s+центр)',mt[2],flags=re.I)[0].strip() if literal else None
  raw.append({'source_pdf_page':pi,'numeric_row_on_page':ni+1,'pdf_numeric_y':y,'label_pdf_words':label,'raw_total':trip[0],'raw_male':trip[1],'raw_female':trip[2],'is_literal':literal,'source_type':typ,'source_name':name,'parent_independent':parent,'population':float(trip[0]) if trip[0]!='-' else np.nan});prev=y
raw=pd.DataFrame(raw);raw.to_parquet(H/'independent_raw_pdf_cells.parquet',index=False)
prod=pd.read_parquet(S/'all_source_rows.parquet');check('all309_numeric_or_dash_rows_recovered',len(raw)==len(prod)==309)
for page,rr in raw.groupby('source_pdf_page'):
 pp=prod[prod.source_pdf_page==page]
 for nc,pc in [('raw_total','source_total_cell_raw'),('raw_male','source_male_cell_raw'),('raw_female','source_female_cell_raw')]:check(f'every_raw_cell_page{page}_{nc}',rr[nc].tolist()==pp[pc].tolist())
lit=raw[raw.is_literal].copy();check('all232_literalNPindependentlyclassified',len(lit)==232);check('literal_membership_flags_all309match',raw.is_literal.tolist()==prod.source_is_literal_np.tolist());check('literal_population_sum439996',lit.population.sum()==439996);check('7dash_unknown_notzero',lit.population.isna().sum()==7)
for i,row in raw.iterrows():
 if row.raw_total!='-' and row.raw_male!='-' and row.raw_female!='-':check(f'sex_sum_pdfpage{row.source_pdf_page}_row{row.numeric_row_on_page}',int(row.raw_total)==int(row.raw_male)+int(row.raw_female))
def textkey(s):return ' '.join(''.join(c if c.isalnum() else ' ' for c in unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е').replace('ѐ','е')).split())
def parkey(s):return ' '.join(w for w in textkey(s).split() if w not in {'г','муниципальный','район','района','городской','городского','округ','округа'})
axis=pd.read_parquet(R/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');a=axis[(axis.region=='адыгея')&axis.source_record_id_2010.notna()].copy();check('all232native2010axisrows',len(a)==232)
a['tuple']=[(textkey(t),textkey(n)) for t,n in zip(a.type,a.name)];a['pkey']=a.district_raw_2010.map(parkey);lit['tuple']=[(textkey(t),textkey(n)) for t,n in zip(lit.source_type,lit.source_name)];lit['pkey']=lit.parent_independent.map(parkey)
prior=pd.read_parquet(D/'admitted_overlay_v1/full_axis_primary2010_overlay.parquet').set_index('id');ids=[];statuses=[]
for ix,row in lit.iterrows():
 aa=a[a.tuple.map(lambda x:x==row.tuple)];ss=lit[lit.tuple.map(lambda x:x==row.tuple)];uid=None;status='unmatched_literal_typed_name'
 if len(aa)==1 and len(ss)==1:uid=aa.iloc[0].id;status='unique_native2010_region_type_name_in_both_full_inventories'
 else:
  aaa=aa[aa.pkey==row.pkey];sss=ss[ss.pkey==row.pkey]
  if row.pkey and len(aaa)==len(sss)==1:uid=aaa.iloc[0].id;status='unique_native2010_region_type_name_parent_in_both_full_inventories'
  elif len(aa):status='ambiguous_native2010_identity'
 ids.append(uid);statuses.append(status)
lit['strict_uid']=ids;lit['identity_status']=statuses;lit['prior_quality']=[prior.loc[i,'reviewed_primary2010_quality'] if i else None for i in ids];lit['prior_population']=[prior.loc[i,'reviewed_primary2010_population'] if i else np.nan for i in ids];lit['new_numeric']=[i is not None and np.isfinite(v) and q=='secondary_confidentiality_protected_value_exact_scope_unverified' for i,v,q in zip(ids,lit.population,lit.prior_quality)]
expected=pd.read_parquet(S/'all_literal_np_identity_candidates.parquet');check('every232_literal_name_type_exact',[(textkey(t),textkey(n)) for t,n in zip(lit.source_type,lit.source_name)]==[(textkey(t),textkey(n)) for t,n in zip(expected.source_type,expected.source_name)])
check('every232identity_status_exact',lit.identity_status.tolist()==expected.identity_status.tolist());check('every232UIDincludingheld_exact',lit.strict_uid.fillna('NA').tolist()==expected.strict_uid.fillna('NA').tolist());check('184additionalnumeric_candidates',lit.new_numeric.sum()==184)
new=pd.read_parquet(S/'new_numeric_primary_candidates.parquet');ours=lit[lit.new_numeric].set_index('strict_uid').population.sort_index();theirs=new.set_index('strict_uid').population2010.sort_index();check('every184candidateIDandvalue_exact',ours.equals(theirs.astype(float)));check('no_existing_primary_numeric_conflict',not ((lit.strict_uid.notna())&lit.population.notna()&lit.prior_quality.ne('secondary_confidentiality_protected_value_exact_scope_unverified')&lit.population.ne(lit.prior_population)).any());check('20unlinkedheld',lit.strict_uid.isna().sum()==20)
lit.to_parquet(H/'independent_literal_identity_readback.parquet',index=False)
check('all_inputs_unchanged_through_audit',{p:sha(p) for p in manifest}==before)
receipt={'status':'ACCEPTED_INDEPENDENT_SOURCE_CELLS_AND_NATIVE2010_IDENTITY' if all(x['passed'] for x in checks) else 'REJECTED','all_checks_passed':all(x['passed'] for x in checks),'checks':checks,'accepted_new_numeric_candidates_sha256':sha(S/'new_numeric_primary_candidates.parquet') if all(x['passed'] for x in checks) else None,'accepted_identity_statuses':['unique_native2010_region_type_name_in_both_full_inventories','unique_native2010_region_type_name_parent_in_both_full_inventories'] if all(x['passed'] for x in checks) else [],'source_sha256':sha(P),'identity_status_counts':lit.identity_status.value_counts().to_dict(),'native2010_temporal_boundary_equivalence_2021_proven':False,'own_independent_code_sha256':sha(__file__),'source_inputs_sha256':before,'source_scope':'All9PDFpages/309numericanddashrows via independent coordinatecells;232literalNP, allrawsexsums, 212strictnative2010identities;184newprimarypopulationcandidates. Directsourcepopulation, not fabricated laterboundaryequivalence; 20unlinked and7dashunknown retained.'}
(H/'audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'checks':len(checks),'failed':[x for x in checks if not x['passed']],'identities':receipt['identity_status_counts']},ensure_ascii=False,indent=2))

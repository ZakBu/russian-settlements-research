from pathlib import Path
import pandas as pd,xlrd,json,re,gzip,hashlib,subprocess
from pypdf import PdfReader
O=Path(__file__).resolve().parent
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
PDF=Path('/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf')
XLS=Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls')
REF=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet')
C=Path('/workspace/settlements-work/continuation_20261003/primary_population_next_cohort_probe_v1/remaining_table5_unique_candidates.csv')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).casefold().replace('ё','е').replace('ѐ','е')).strip()
def key(t,n):return norm(t),norm(n)
s=pd.read_parquet(SEL);s=s[(s.census_year==2010)&(s.region_raw=='московская')].copy();s['key']=s.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);sc=s.key.value_counts()
f=pd.read_parquet(REF);f=f[(f.region_key=='московская')&(f.row_kind=='settlement')].copy();f['key']=f.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);fc=f.key.value_counts()
# Scope repair: no district header precedes standalone independent city/ZATO rows on pages32–33.
# These inherited parent labels cannot establish municipal context.
f.loc[f.district_raw.isna(),'parent_context']=None
fm={r['key']:r for r in f.to_dict('records') if fc[r['key']]==1}
b=xlrd.open_workbook(XLS);sh=b.sheet_by_name('Data Sheet');seq=[]
pat=re.compile(r'^(г\.|город|пгт|деревня|пос[еёѐ]лок|село|хутор|станция)\s*(.+)$',re.I)
for i in range(sh.nrows):
 v=sh.row_values(i)
 if v[2]!='Моск.обл.':continue
 m=pat.match(str(v[3]).strip())
 if not m:continue
 t=norm(m[1]);t='город' if t=='г' else t;n=re.sub(r'\s+(рп|дп|кп)$','',m[2],flags=re.I);k=key(t,n)
 p=fm.get(k)
 # Target competition uses every selected MO NP; anchor exact typed names also require raw regional uniqueness below.
 seq.append({'row':i+1,'raw_label':v[3],'raw_population':v[4],'key':k,'primary':p})
rc=pd.Series([q['key'] for q in seq]).value_counts()
for q in seq:
 if rc[q['key']]!=1:q['primary']=None
ix={q['row']:i for i,q in enumerate(seq)}
c=pd.read_csv(C,low_memory=False);c=c[c.region_raw_r2=='московская'];c=c.merge(s[['source_record_id','population','population_value_quality','source_name_raw','key']],left_on='r2_source_record_id',right_on='source_record_id',suffixes=('','_current'));c=c[c.population_value_quality_current.str.startswith('secondary_confidentiality')]
reader=PdfReader(PDF);poppler=subprocess.check_output(['pdftotext','-layout',str(PDF),'-']).decode().split('\f');rows=[]
for r in c.to_dict('records'):
 n=int(r['source_row_x']);target=seq[ix[n]];p=f[f.reference_id==r['reference_id']].iloc[0].to_dict();old=s[s.source_record_id==r['source_record_id']].iloc[0]
 assert norm(target['raw_label'])==norm(old.source_name_raw) and float(target['raw_population'])==float(old.population)
 unique=sc.get(target['key'],0)==1 and rc.get(target['key'],0)==1 and fc.get(target['key'],0)==1
 page=int(p['pdf_page']);line=int(p['text_line_start']);txt=reader.pages[page-1].extract_text().splitlines();raw=txt[line-1];nums=[str(int(p[k])) for k in ['population','men','women']]
 assert int(p['population'])==int(p['men'])+int(p['women'])
 hits=[l for l in poppler[page-1].splitlines() if norm(p['settlement_name']) in norm(l) and any(re.findall(r'\d+',l)[j:j+3]==nums for j in range(len(re.findall(r'\d+',l))-2))]
 assert hits,(p['settlement_name'],page)
 district=norm(p['district_raw']) if pd.notna(p['district_raw']) else ''
 near=[];i=ix[n]
 for j in range(max(0,i-75),min(len(seq),i+76)):
  if j==i:continue
  q=seq[j];a=q['primary']
  if not a or pd.isna(a['district_raw']):continue
  near.append({'offset':j-i,'raw_row':q['row'],'raw_label':q['raw_label'],'official_reference_id':a['reference_id'],'official_district':a['district_raw']})
 prev=min([q for q in near if q['offset']<0],key=lambda q:abs(q['offset']),default=None);nxt=min([q for q in near if q['offset']>0],key=lambda q:abs(q['offset']),default=None)
 same=[q for q in near if norm(q['official_district'])==district]
 bracket=bool(district and prev and nxt and norm(prev['official_district'])==norm(nxt['official_district'])==district)
 block=bool(district and len(same)>=3 and any(q and norm(q['official_district'])==district for q in [prev,nxt]))
 status='ready_positive_literal_county_roster_context' if unique and (bracket or block) else 'held_source_municipal_context_insufficient'
 witnesses=[]
 for q in [prev,nxt]+same[:3]:
  if q and q not in witnesses:witnesses.append(q)
 rows.append({'old_source_record_id':r['source_record_id'],'old_population':int(old.population),'old_quality':old.population_value_quality,'old_source_file':old.source_file,'old_source_sheet':old.source_sheet,'old_source_row':n,'raw_old_NP_caption':target['raw_label'],'old_source_sha256':sha(XLS),'official_source_record_id':p['reference_id'],'official_population':int(p['population']),'official_men':int(p['men']),'official_women':int(p['women']),'official_name':p['settlement_name'],'official_type':p['settlement_type'],'official_district':p['district_raw'],'official_source_path':str(PDF),'official_source_sha256':sha(PDF),'official_page':page,'official_line_start':line,'official_line_end':int(p['text_line_end']),'independent_pypdf_line':raw,'independent_poppler_line':hits[0],'delta':int(p['population'])-int(old.population),'status':status,'context_method':'nearest_two_bracketing_exact_typed_NP_county_anchors' if bracket else 'at_least3_same_county_NP_anchors_with_nearest_match' if block else 'no_positive_context_gate','context_witnesses_json':json.dumps(witnesses,ensure_ascii=False),'selected_competitor_count':int(sc[target['key']]),'raw_full_MO_NP_competitor_count':int(rc[target['key']]),'official_Table5_competitor_count':int(fc[target['key']]),'population_used_for_context':False,'selection_applied':False})
d=pd.DataFrame(rows);d.to_csv(O/'moscow_all_primary_candidates.csv.gz',index=False,compression='gzip');ready=d[d.status.str.startswith('ready')];ready.to_csv(O/'moscow_ready_primary_override_candidates.csv.gz',index=False,compression='gzip')
rank=pd.read_csv('/workspace/russian-settlements-research/research_rebuild/evidence/working_full_chain_20261007/regional_official_2010_joint_gap_rank.csv');rank.sort_values('control_minus_selected_population',ascending=False).head(20).to_csv(O/'remaining_regional_source_deficit_priority_raw62.csv',index=False)
r={'status':'bounded_cached_official_MO_primary_candidates_context_review_no_State_mutation','current_effective_national2010_deficit':483034,'source_ready_region':'московская','regional_raw_selected_deficit':45910,'all_candidates':len(d),'all_candidate_delta':int(d.delta.sum()),'ready_rows':len(ready),'ready_old_population':int(ready.old_population.sum()),'ready_new_population':int(ready.official_population.sum()),'ready_candidate_delta_unapplied':int(ready.delta.sum()),'held_rows':len(d)-len(ready),'held_candidate_delta':int(d[~d.status.str.startswith('ready')].delta.sum()),'method_counts':d.context_method.value_counts().to_dict(),'source_scope':'National official Table5: explicit urbanNP/ruralcentres/large ruralNP only, not complete small-rural source. Aggregates excluded; no residual allocated. Source-context gate uses exact surrounding raw NP roster and explicit officialdistrict; NW rawpublication omits administrativecaptions.','no_new_network':True,'no_primary_reference_parent_inheritance_admission':True,'source_availability':'No complete cached official rural inventories for Moscow,NN,Primorye,Perm,Stavropol. Existing protected grouped XLS files are not exact official. NationalTable5 is available; source-ready opportunity selected by actual current remaining replacement gain.','inputs':{str(p):sha(p) for p in [SEL,PDF,XLS,REF,C]},'outputs':{}}
for p in O.glob('*.csv*'):r['outputs'][p.name]={'bytes':p.stat().st_size,'sha256':sha(p)}
(O/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['inputs','outputs']},ensure_ascii=False,indent=2))

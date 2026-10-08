from pathlib import Path
import pandas as pd,xlrd,json,re,hashlib,subprocess,collections,gzip
from pypdf import PdfReader
O=Path(__file__).resolve().parent
ROOT=O.parents[2];RAW=Path('/workspace/settlements-raw')
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');PDF=RAW/'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'
REF=Path('/workspace/settlements-work/continuation_20261003/population2010/tom1_table5_extraction/official_2010_table5_reference.parquet');C=Path('/workspace/settlements-work/continuation_20261003/primary_population_next_cohort_probe_v1/remaining_table5_unique_candidates.csv');PRIOR=O.parent/'official_population_residual_sources_20261008/followup_context_accepted_delta.csv.gz';CREDIT=O.parent/'primary_residual_mass_application_20261008/applied_primary_credited_UID_roster.csv.gz'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):
 z=re.sub(r'[^а-яa-z0-9]+',' ',str(x).casefold().replace('ё','е').replace('ѐ','е')).strip();return re.sub(r'\bимени\b','им',z)
def key(t,n):return norm(t),norm(n)
s=pd.read_parquet(SEL);s=s[s.census_year.eq(2010)].copy();s['key']=s.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1);sc={region:collections.Counter(g.key) for region,g in s.groupby('region_raw')};sd=s.set_index('source_record_id')
f=pd.read_parquet(REF);f=f[f.row_kind.eq('settlement')].copy();f['key']=f.apply(lambda r:key(r.settlement_type,r.settlement_name),axis=1)
# Never inherit a previous urban aggregate as municipality for a standalone regional NP.
f.loc[f.district_raw.isna(),'parent_context']=None
fm={};fc={};byid=f.set_index('reference_id').to_dict('index')
for region,g in f.groupby('region_key'):
 cnt=collections.Counter(g.key);fc[region]=cnt;fm[region]={r['key']:r for r in g.to_dict('records') if cnt[r['key']]==1}
c=pd.read_csv(C,low_memory=False);c=c[c.r2_source_record_id.isin(sd.index)];c['current_quality']=c.r2_source_record_id.map(sd.population_value_quality);c=c[c.current_quality.str.startswith('secondary_confidentiality')]
prior=pd.read_csv(PRIOR);already=set(prior.old_source_record_id);overlap=c[c.r2_source_record_id.isin(already)].copy();c=c[~c.r2_source_record_id.isin(already)]
books={};seqcache={};pins={str(p):sha(p) for p in [SEL,PDF,REF,C,PRIOR,CREDIT]};reader=PdfReader(PDF);pagecache={};poppler=subprocess.check_output(['pdftotext','-layout',str(PDF),'-']).decode().split('\f');rows=[]
pat=re.compile(r'^(г\.|город|пгт|деревня|д\.|пос[еёѐ]лок|село|с\.|станица|хутор|аул|починок|насел[её]нный пункт|станция|кишлак|заимка|слобода|выселок|разъезд)\s*(.+)$',re.I)
typemap={'г':'город','д':'деревня','с':'село'}
credits=pd.read_csv(CREDIT,keep_default_na=False);cm=credits.set_index('source_record_id').to_dict('index');creditids=set(cm)
for rawr in c.to_dict('records'):
 sid=rawr['r2_source_record_id'];old=sd.loc[sid];region=old.region_raw;p=byid[rawr['reference_id']];source=RAW/old.source_file;filekey=str(source)
 if filekey not in books:books[filekey]=xlrd.open_workbook(source);pins[filekey]=sha(source)
 sh=books[filekey].sheet_by_name(old.source_sheet);n=int(old.source_row);vals=sh.row_values(n-1)
 cap=[j for j,v in enumerate(vals[:12]) if norm(v)==norm(old.source_name_raw)]
 if len(cap)!=1:
  rows.append({'old_source_record_id':sid,'region':region,'status':'held_raw_caption_column_unresolved','old_population':old.population,'official_population':p['population'],'delta':int(p['population'])-int(old.population)});continue
 col=cap[0];popcols=[j for j in range(col+1,min(12,len(vals))) if isinstance(vals[j],(int,float)) and float(vals[j])==float(old.population)];assert popcols,(sid,vals[:12]);popcol=popcols[0];token=vals[2];cachekey=(filekey,old.source_sheet,token,region,col)
 if cachekey not in seqcache:
  seq=[]
  for i in range(sh.nrows):
   vv=sh.row_values(i)
   if vv[2]!=token:continue
   m=pat.match(str(vv[col]).strip())
   if not m:
    adjacent=norm(vv[col+1])
    amap={'город':'город','поселок':'поселок','деревня':'деревня','село':'село','рабочий поселок':'пгт','поселок городского типа':'пгт','рп':'пгт','пгт':'пгт','станица':'станица','хутор':'хутор','аул':'аул','п':'поселок','д':'деревня','с':'село'}
    if adjacent not in amap:continue
    t=amap[adjacent];name=str(vv[col])
   else:
    t=typemap.get(norm(m[1]),norm(m[1]));name=re.sub(r'\s+(рп|дп|кп)$','',m[2],flags=re.I)
   k=key(t,name)
   seq.append({'row':i+1,'raw_label':vv[col],'key':k,'primary':fm.get(region,{}).get(k)})
  rc=collections.Counter(q['key'] for q in seq)
  for q in seq:
   if rc[q['key']]!=1:q['primary']=None
  seqcache[cachekey]=(seq,{q['row']:i for i,q in enumerate(seq)},rc)
 seq,ix,rc=seqcache[cachekey]
 if n not in ix:
  rows.append({'old_source_record_id':sid,'region':region,'status':'held_source_caption_not_explicit_NP','old_population':old.population,'official_population':p['population'],'delta':int(p['population'])-int(old.population)});continue
 target=seq[ix[n]];k=target['key'];unique=sc.get(region,{}).get(k,0)==1 and rc.get(k,0)==1 and fc.get(region,{}).get(k,0)==1 and k==p['key']
 district=norm(p['district_raw']) if pd.notna(p['district_raw']) else '';near=[];i=ix[n]
 for j in range(max(0,i-75),min(len(seq),i+76)):
  if j==i:continue
  q=seq[j];a=q['primary']
  if not a or pd.isna(a['district_raw']):continue
  near.append({'offset':j-i,'raw_row':q['row'],'raw_label':q['raw_label'],'official_reference_id':a['reference_id'],'official_district':a['district_raw']})
 prev=min([q for q in near if q['offset']<0],key=lambda q:abs(q['offset']),default=None);nxt=min([q for q in near if q['offset']>0],key=lambda q:abs(q['offset']),default=None);same=[q for q in near if norm(q['official_district'])==district]
 bracket=bool(district and prev and nxt and norm(prev['official_district'])==norm(nxt['official_district'])==district);block=bool(district and len(same)>=3 and any(q and norm(q['official_district'])==district for q in [prev,nxt]));w=[]
 for q in [prev,nxt]+same[:3]:
  if q and q not in w:w.append(q)
 page=int(p['pdf_page']);start=int(p['text_line_start']);end=int(p['text_line_end'])
 if page not in pagecache:pagecache[page]=reader.pages[page-1].extract_text().splitlines()
 pdfraw=' | '.join(pagecache[page][start-1:end]);nums=[str(int(p[x])) for x in ['population','men','women']];hits=[];lines=poppler[page-1].splitlines()
 for li,line in enumerate(lines):
  ns=re.findall(r'\d+',line)
  if any(ns[j:j+3]==nums for j in range(len(ns)-2)) and norm(p['settlement_name']) in norm(' '.join(lines[max(0,li-2):li+1])):hits.append(' | '.join(lines[max(0,li-2):li+1]))
 sexes=int(p['population'])==int(p['men'])+int(p['women'])
 status='ready_positive_literal_county_roster_context' if unique and (bracket or block) and hits and sexes else 'held_full_competitor_or_municipal_context_or_count_readback'
 rows.append({'old_source_record_id':sid,'region':region,'old_population':int(old.population),'old_quality':old.population_value_quality,'old_source_file':old.source_file,'old_source_sheet':old.source_sheet,'old_source_row':n,'raw_old_NP_caption':target['raw_label'],'raw_population_cell_column_zero_based':popcol,'raw_population_cell':vals[popcol],'old_source_sha256':pins[filekey],'official_source_record_id':rawr['reference_id'],'official_population':int(p['population']),'official_men':int(p['men']),'official_women':int(p['women']),'official_name':p['settlement_name'],'official_type':p['settlement_type'],'official_district':p['district_raw'],'official_source_path':str(PDF),'official_source_sha256':pins[str(PDF)],'official_page':page,'official_line_start':start,'official_line_end':end,'independent_pypdf_lines':pdfraw,'independent_poppler_lines':hits[0] if hits else '', 'delta':int(p['population'])-int(old.population),'status':status,'context_method':'two_bracketing_exact_typed_NP_county_anchors' if bracket else '3_same_county_NP_anchors_plus_nearest_match' if block else 'municipal_context_not_established','context_witnesses_json':json.dumps(w,ensure_ascii=False),'selected_full_region_competitors':sc.get(region,{}).get(k,0),'raw_full_region_NP_competitors':rc.get(k,0),'official_Table5_competitors':fc.get(region,{}).get(k,0),'target_key_and_official_key_agree':k==p['key'],'independent_count_readback':bool(hits and sexes),'already_primary_UID_credited_post62':sid in creditids,'existing_entity_uid_post62':cm.get(sid,{}).get('entity_uid',''),'already_effective_prior_override':False,'population_used_for_binding_context':False,'selection_applied':False})
d=pd.DataFrame(rows);d.to_csv(O/'national_cached_Table5_all_remaining_candidates.csv.gz',index=False,compression='gzip');ready=d[d.status.str.startswith('ready')];ready.to_csv(O/'national_cached_Table5_ready_primary_override_candidates.csv.gz',index=False,compression='gzip');byregion=ready.groupby('region').agg(rows=('old_source_record_id','size'),old_population=('old_population','sum'),official_population=('official_population','sum'),delta=('delta','sum')).sort_values('delta',ascending=False);byregion.to_csv(O/'ready_by_region.csv');overlap[['r2_source_record_id','reference_id']].to_csv(O/'excluded_prior510_overlap.csv',index=False)
rank=pd.read_csv(O.parent/'working_full_chain_20261007/regional_official_2010_joint_gap_rank.csv');rank['effective_prior510_delta']=rank.control_region.eq('ленинградская').astype(int)*10478;rank['effective_selected_population']=rank.selected_population+rank.effective_prior510_delta;rank['effective_source_deficit']=rank.official_population-rank.effective_selected_population;rank.sort_values('effective_source_deficit',ascending=False).to_csv(O/'remaining_regional_source_deficit_priority_effective62.csv',index=False)
r={'status':'national_cached_bounded_positive_context_candidates_not_applied','effective_prior2010_source_deficit':483034,'all_protected_Table5_candidates_before_prior_overlap':len(c)+len(overlap),'excluded_already_effective510_overlap':len(overlap),'all_remaining_candidates':len(d),'all_remaining_candidate_delta':int(d.delta.sum()),'ready_rows':len(ready),'ready_old_population':int(ready.old_population.sum()),'ready_official_population':int(ready.official_population.sum()),'ready_delta_unapplied':int(ready.delta.sum()),'ready_actual_primary_UID_membership_rows':int(ready.already_primary_UID_credited_post62.sum()),'ready_actual_primary_UID_delta_unapplied':int(ready.loc[ready.already_primary_UID_credited_post62,'delta'].sum()),'held_rows':len(d)-len(ready),'held_delta':int(d[~d.status.str.startswith('ready')].delta.sum()),'ready_regions':len(byregion),'highest_ready_regions':byregion.head(12).reset_index().to_dict('records'),'sources':len(books),'no_network':True,'no_missing_NP_observation_admitted':True,'source_limits':'Official NationalTable5 covers directurbanNP, ruralcentres and large ruralNP; no complete small-rural inventories for top source-deficit regions. All aggregate rows excluded. Explicit positive county-context inferred from exact raw neighboring NP rosters without population; countyblank targets retain original provenance and require distinct standalone context review, not automatically claimed wrong. Inherited urbanparent errors are ignored. Rival/mismatched types/keys held. Prior510 source IDs excluded.','input_pins':pins,'outputs':{}}
for p in O.glob('*'):
 if p.is_file() and p.suffix in ['.gz','.csv']:r['outputs'][p.name]={'bytes':p.stat().st_size,'sha256':sha(p)}
(O/'national_batch_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','outputs']},ensure_ascii=False,indent=2))

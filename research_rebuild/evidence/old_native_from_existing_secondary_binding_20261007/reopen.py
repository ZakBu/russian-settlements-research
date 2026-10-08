import pandas as pd,pathlib,xlrd,json,re,hashlib,sys,math
R=pathlib.Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=E/'old_native_from_existing_secondary_binding_20261007';D=pd.read_csv(O/'scope_holds.csv',keep_default_na=False);books={};hashes={};witness=[]
def norm(x):return ' '.join(str(x).lower().replace('ё','е').replace('"','').split())
def ck(x):return ' '.join(re.sub(r'муниципальное образование|муниципальный район|муниципального района|муниципальный округ|муниципального округа|городской округ|городского округа|район|района|город|города|мр|го',' ',norm(x)).split())
for r in D.to_dict('records'):
 if r.get('hold_reason')!='historical_county_context_not_exact' or not str(r.get('old_source_record_id','')).startswith(('2002:','2010:')):continue
 parts=r['old_source_record_id'].split(':');p=pathlib.Path('/workspace/settlements-raw')/str(r['old_source_file'])
 if not p.exists() or p.suffix!='.xls':continue
 if str(p) not in books:books[str(p)]=xlrd.open_workbook(str(p));hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 try:sh=books[str(p)].sheet_by_name(parts[-2]);n=int(parts[-1])-1
 except:continue
 raw=sh.row_values(n);cs=[i for i,z in enumerate(raw) if norm(r['name']) in norm(z)];vals=[z for z in raw if str(z).replace('.0','')==str(int(float(r['old_native_population'])))];expected=ck(r['current_county']);capt=None
 for i in range(n,-1,-1):
  rr=sh.row_values(i);txt=' | '.join(map(str,rr));segments=[str(z) for z in rr if re.search('район|округ',str(z),re.I)]
  if not segments:continue
  meaningful=[z for z in segments if re.search('район|округ',z,re.I) and len(z.strip())>5]
  if meaningful:capt=(i+1,meaningful,txt);break
 if not capt or not cs or not vals:continue
 # Leading/type/style table cells excluded; exact printed county only.
 cleaned=[' '.join(re.sub(r'^\d+\.?\s*','',z.strip()).split()) for z in capt[1]]
 if not any(ck(z)==expected for z in cleaned):continue
 r.update(raw_old_source_file=str(p),raw_old_source_sha256=hashes[str(p)],raw_old_source_locator='sheet='+sh.name+';row_1based='+str(n+1),raw_old_row_json=json.dumps(raw,ensure_ascii=False),raw_old_county_row_1based=capt[0],raw_old_county_row_json=json.dumps(sh.row_values(capt[0]-1),ensure_ascii=False),raw_old_county_printed=cleaned[0],binding_proof='exact sourceNP/count/name/type/region; raw reopened nearest county caption matches owncurrent county; old/current exactcount competitor uniqueness; accepted owncurrentpoint',status='candidate_native_old_binding_not_admitted')
 witness.append(r)
pd.DataFrame(witness).to_csv(O/'raw_reopened_county_binding_candidates.csv',index=False);print('raw_reopen_candidates',len(witness));print(pd.DataFrame(witness)[['name','year','old_native_population','raw_old_county_printed']].to_string(index=False) if witness else '')

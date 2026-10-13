import json,re,sys,collections
from pathlib import Path
import pandas as pd,duckdb,xlrd
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize
from apply_unique_county_name_bridge_20261007 import county_key
obs=pd.read_parquet(O/'frozen_moderate_observations.parquet').set_index('source_record_id');p=pd.read_csv(O/'accepted_point_use_delta.csv.gz',keep_default_na=False);SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');c=duckdb.connect();meta=c.execute('select source_record_id,source_name_raw,source_sheet,source_row from read_parquet(?)',[str(SEL)]).fetchdf().set_index('source_record_id');c.close();pins={str(SEL):sha(SEL)};books={};indexes={};audit=[];rivals=[]
def nn(v):return ' '.join(re.sub('[^а-яa-z0-9]+',' ',re.sub(r'^(?:д\.|с\.|п\.|х\.|ст\.|ж\/д ст\.|рп|пгт|поселок(?: городского типа| сельского типа)?|посёлок|село|деревня|хутор|город|пгт|станица|аул|станция|разъезд|слобода)\s+','',normalize(v))).split())
def county(v):
 v=normalize(v);v=re.sub(r'ского(?=\s+район)','ский',v);return county_key(v)
for sid in p.target_source_record_id:
 r=obs.loc[sid];file=Path('/workspace/settlements-raw')/str(r.source_file);status=''
 if file.suffix!='.xls' or not file.exists():audit.append({'source_record_id':sid,'audit_status':'previous_source_bound_native_nonXLS_roster_requires_existing_witness','source_file':str(r.source_file),'protected_population':r.population});continue
 m=meta.loc[sid];sheet=str(m.source_sheet);key=(str(file),sheet)
 if key not in indexes:
  if file not in books:books[file]=xlrd.open_workbook(str(file),on_demand=True);pins[str(file)]=sha(file)
  b=books[file];sh=b.sheet_by_name(sheet) if sheet in b.sheet_names() else b.sheet_by_index(int(m.source_sheet));index=collections.defaultdict(list);header='';hrow=-1
  for i in range(sh.nrows):
   vals=sh.row_values(i)
   for v in vals:
    if isinstance(v,str) and re.search(r'\b(?:район(?:а)?|кожуун|улус)\b',normalize(v)) and not re.match(r'^\s*(?:село|деревня|хутор)\b',normalize(v)):header=v;hrow=i+1
   labels=[v for v in vals if isinstance(v,str) and re.match(r'^\s*(?:д\.|с\.|п\.|х\.|ст\.|рп|пгт|пос[её]лок|деревня|село|хутор|город|станица|аул|станция|разъезд|слобода)\s+',v,re.I)]
   # Flat federal2010 sheets print region and optional district on each leaf. A previous city district must never cross into later uncaptioned raw NP rows.
   rowheader=header;rowhrow=hrow
   if '/2010/' in str(file):
    d=vals[3] if len(vals)>3 and isinstance(vals[3],str) else ''
    rowheader=d if d and d not in labels and not re.match(r'^\s*(?:д\.|с\.|п\.|х\.|пос[её]лок|деревня|село|хутор|город|станица|аул|станция)',d,re.I) else '';rowhrow=i+1 if rowheader else -1
   labels.extend(vals[j]+' '+vals[j+1] for j in range(len(vals)-1) if isinstance(vals[j],str) and isinstance(vals[j+1],str) and normalize(vals[j]) in ['село','деревня','поселок','посёлок','хутор','город','станица','аул','станция'])
   for label in set(labels):index[nn(label)].append({'row1based':i+1,'raw_label':label,'county_caption':rowheader,'county_key':county(rowheader),'county_caption_row1based':rowhrow})
  indexes[key]=(sh,index)
 sh,index=indexes[key];rn=int(m.source_row);vals=sh.row_values(rn-1);exact=any(isinstance(v,str) and normalize(v)==normalize(m.source_name_raw) for v in vals) or any(isinstance(vals[j],str) and isinstance(vals[j+1],str) and normalize(vals[j]+' '+vals[j+1])==normalize(m.source_name_raw) for j in range(len(vals)-1));pool=index[nn(r.settlement_name)];own=[z for z in pool if z['row1based']==rn];ck=own[0]['county_key'] if own else '';same=[z for z in pool if ck and z['county_key']==ck];rivals.extend({'target_source_record_id':sid,'source_file':str(file),'sheet':sh.name,**z,'same_own_source_county':bool(ck and z['county_key']==ck)} for z in pool)
 audit.append({'source_record_id':sid,'source_file':str(file),'source_sha256':pins[str(file)],'source_locator':f'sheet={sh.name};row1based={rn}','exact_raw_native_label_reopened':exact,'protected_population':r.population,'raw_county_caption':own[0]['county_caption'] if own else '', 'same_raw_source_county_name_leaf_count':len(same),'all_raw_source_sheet_name_leaf_count':len(pool),'raw_source_name_rival_hold':len(same)>1,'raw_source_grain_county_ownlabel_unresolved':not exact or not own or not ck})
pd.DataFrame(audit).to_csv(O/'actual_native_leaf_roster_audit.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(rivals).to_csv(O/'all_actual_native_source_namesakes.csv.gz',index=False,compression={'method':'gzip','mtime':0});f=pd.DataFrame(audit);r={'status':'bulk native raw XLS leaf and whole-sheet county-qualified namesake audit; no count or identity edits','XLS_rows_checked':int(f.exact_raw_native_label_reopened.notna().sum()),'source_namesake_target_holds':f.loc[f.raw_source_name_rival_hold.eq(True),'source_record_id'].tolist(),'unresolved_leaf_targets':f.loc[f.raw_source_grain_county_ownlabel_unresolved.eq(True),'source_record_id'].tolist(),'input_pins':pins};(O/'actual_native_roster_audit_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print({'XLS_rows_checked':r['XLS_rows_checked'],'source_namesake_targets':len(r['source_namesake_target_holds']),'unresolved_leaf_targets':len(r['unresolved_leaf_targets'])})

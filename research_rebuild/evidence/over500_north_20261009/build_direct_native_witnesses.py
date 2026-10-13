from pathlib import Path
import pandas as pd,sys,json,hashlib,re,xlrd,ast,gzip
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from apply_unique_county_name_bridge_20261007 import county_key
from current_chain_state_20261007 import normalize
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
f=pd.read_parquet('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet').fillna('');b=f.set_index('source_record_id');m=pd.read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet').fillna('').set_index('source_record_id');pins={};books={};checks={};rawpar={};tree=ast.parse((O/'build_packet.py').read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='check');fn=ast.unparse(node).replace("actual = re.sub('ского$', 'ский', actual)","actual = re.sub('ского$', 'ский', actual); actual = re.sub('цкого$', 'цкий', actual)");exec(fn)
a=pd.read_csv(O/'assignment.csv').fillna('');a=a[a.has_ownpoint==False];out=[]
for z in a.to_dict('records'):
 sid=z['source_record_id'];w=check(sid);w.update(native_region=z['region_norm'],selected_county=z['district_raw'],county_key=county_key(z['district_raw']),primary_native_parent_header='',primary_native_parent_locator='',own_native_OKATO='',own_native_OKTMO=z['oktmo'])
 if sid in m.index:
  mm=m.loc[sid];q=Path('/workspace/settlements-raw')/mm.source_file
  if q.is_file() and q.suffix=='.xls' and str(q) in books:
   bk=books[str(q)];sn=str(mm.source_sheet);sh=bk.sheet_by_name(sn) if sn in bk.sheet_names() else bk.sheet_by_index(int(sn));rn=int(mm.source_row)-1
   lower=int(str(w.get('actual_county_locator','')).rsplit(':',1)[-1])-1 if w.get('actual_county_locator') else max(-1,rn-800)
   for nr in range(rn-1,max(lower,rn-800),-1):
    vs=sh.row_values(nr);ss=[x for x in vs if isinstance(x,str) and re.search('сельск.*(?:округ|совет|поселен)|волость|подчиненн.*администрации',normalize(x))]
    if ss:w.update(primary_native_parent_header=ss[0],primary_native_parent_locator=f'{sh.name}:{nr+1}',primary_native_parent_cells_json=json.dumps({i:x for i,x in enumerate(vs) if x!=''},ensure_ascii=False));break
 if w.get('raw_row_cells_json'):
  vals=json.loads(w['raw_row_cells_json']);w['raw_row_cells_json']=json.dumps({i:x for i,x in enumerate(vals) if x!=''},ensure_ascii=False) if isinstance(vals,list) else json.dumps(vals,ensure_ascii=False)
 out.append(w)
pd.DataFrame(out).to_csv(O/'direct_native_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'direct_native_witnesses_manifest.json').write_text(json.dumps({'rows':len(out),'native_label_count_passed':sum(bool(x['literal_label_population_passed']) for x in out),'source_pins':pins,'output_sha256':sha(O/'direct_native_witnesses.csv.gz')},ensure_ascii=False,indent=2));print('rows',len(out),'passed',sum(bool(x['literal_label_population_passed']) for x in out))
# Preserve successful live page captures; failed API responses remain cache only.
capture=json.loads(gzip.decompress(Path('/dev/shm/over500-20261009/north_wiki/capture.json.gz').read_bytes()));positive=[z for z in capture if z['page_response'].get('query',{}).get('pages')];(O/'live_positive_own_article_captures.json.gz').write_bytes(gzip.compress(json.dumps(positive,ensure_ascii=False).encode(),mtime=0))

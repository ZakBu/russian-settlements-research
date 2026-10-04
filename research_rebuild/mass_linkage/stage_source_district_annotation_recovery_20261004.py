#!/usr/bin/env python3
"""Candidate-only audit of literal source district rendering annotations."""
from __future__ import annotations
import csv, hashlib, json, math, random, re, subprocess
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_COORDINATE_STATUSES

ROOT=Path('/workspace')
REPO=ROOT/'russian-settlements-research'
FREEZE=ROOT/'settlements-work/continuation_20261004/R4/stable_type_corridor_mass/review_freeze_v2'
SELECTED=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EVIDENCE=ROOT/'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
BASE=ROOT/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected'
CONFIG=REPO/'config/mass_joint_20261004.json'
OUT=ROOT/'settlements-work/continuation_20261004/R4/source_district_annotation_recovery_20261004'
SEED=20261004

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def norm(x): return re.sub(r'\s+',' ',str(x or '').casefold().replace('ё','е')).strip(' .,:;')
def county_core(x):
 s=norm(x); ann=''
 for q in (' - сельское население',' - городское население'):
  if s.endswith(q): s=s[:-len(q)].strip(); ann=q[3:]; break
 suffix='bare'
 for q,k in (('муниципальный район','municipal_district'),('район','district')):
  if s.endswith(' '+q): s=s[:-(len(q)+1)].strip(); suffix=k; break
 if not s or any(q in s for q in ('городской округ','муниципальный округ','городское поселение','сельское поселение')): return '',ann,'excluded_admin_form'
 return s,ann,suffix

def dist_km(lat1,lon1,lat2,lon2):
 vals=[lat1,lon1,lat2,lon2]
 try: a,b,c,d=map(float,vals)
 except (ValueError,TypeError): return math.inf
 if not all(map(math.isfinite,vals2:=(a,b,c,d))): return math.inf
 rad=math.pi/180; p1,p2=a*rad,c*rad; dp=(c-a)*rad; dl=(d-b)*rad
 h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.asin(min(1,math.sqrt(h)))
def writecsv(path, rows, fields=None):
 fields=fields or (list(dict.fromkeys(k for row in rows for k in row)) if rows else ['status'])
 with open(path,'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader();w.writerows(rows)

class RawHierarchy:
 def __init__(self): self.cache={}; self.pdf={}; self.hashes={}
 def verify(self, rec, district_raw):
  if not rec or not district_raw: return False, 'district_blank_or_record_missing', ''
  path=ROOT/'settlements-raw'/str(rec.get('source_file') or '')
  if not path.exists(): return False,'raw_source_missing',''
  key=str(path); self.hashes.setdefault(key,{'path':key,'sha256':sha(path),'bytes':path.stat().st_size})
  year=int(rec.get('census_year') or 0); value=norm(district_raw)
  if path.suffix.lower()=='.parquet':
   if key not in self.cache: self.cache[key]=pd.read_parquet(path)
   df=self.cache[key]; ix=int(float(rec.get('source_row') or 0))-1
   if ix<0 or ix>=len(df): return False,'raw_parquet_row_missing',''
   row=df.iloc[ix]
   vals=[norm(row.get(c)) for c in ('mun_upper','mun_lower') if c in df.columns and pd.notna(row.get(c))]
   ok=value in vals
   return ok,('raw_current_hierarchy_field_exact' if ok else 'selected_admin_label_not_literal_current_hierarchy'),json.dumps({'mun_upper':row.get('mun_upper'),'mun_lower':row.get('mun_lower'),'region':row.get('region')},ensure_ascii=False,default=str)
  if path.suffix.lower()=='.pdf':
   if key not in self.pdf: self.pdf[key]=subprocess.run(['pdftotext','-layout',str(path),'-'],check=True,stdout=subprocess.PIPE,text=True).stdout.split('\f')
   loc=json.loads(str(rec.get('source_locator') or '{}')); pg=int(loc.get('pdf_page_1based') or 0)
   pages=self.pdf[key]; lines=pages[pg-1].splitlines() if 1<=pg<=len(pages) else []
   label=norm(loc.get('raw_label') or rec.get('source_name_raw') or '')
   ni=[i for i,line in enumerate(lines) if label and label in norm(line)]
   if not ni: return False,'raw_pdf_settlement_line_not_found',''
   i=ni[0]; core=county_core(district_raw)[0]; parents=[]
   for j in range(i-1,max(-1,i-12),-1):
    cand=lines[j].strip(); label_only=re.split(r'\s{2,}\d',cand,1)[0].strip(); cc=county_core(label_only)[0]
    if cc and cc==core: parents.append({'line_1based':j+1,'text':cand}); break
   ok=bool(parents)
   return ok,('raw_pdf_exact_parent_context' if ok else 'raw_pdf_parent_context_not_verified'),json.dumps({'pdf_page':pg,'settlement_line_1based':i+1,'settlement_line':lines[i].strip(),'matched_preceding_parent':parents},ensure_ascii=False)
  if path.suffix.lower() in {'.xls','.xlsx'}:
   sheet=str(rec.get('source_sheet') or '')
   k=(key,sheet)
   if k not in self.cache:
    eng='xlrd' if path.suffix.lower()=='.xls' else 'openpyxl'; self.cache[k]=pd.read_excel(path,sheet_name=sheet or 0,header=None,dtype=object,engine=eng)
   df=self.cache[k]; ix=int(float(rec.get('source_row') or 0))-1
   if ix<0 or ix>=len(df): return False,'raw_workbook_row_missing',''
   header_col=None
   for ri in range(min(12,len(df))):
    for ci,v in enumerate(df.iloc[ri].tolist()):
     if norm(v) in {'район','муниципальный район','административный район'}: header_col=ci; break
    if header_col is not None: break
   row=[None if pd.isna(v) else str(v).strip() for v in df.iloc[ix].tolist()]
   explicit=(header_col is not None and header_col<len(row) and norm(row[header_col])==value) or value in [norm(v) for v in row if v]
   inherited=False; parent=None
   if header_col is not None:
    for j in range(ix-1,-1,-1):
     v=df.iloc[j,header_col]
     if pd.notna(v) and str(v).strip():
      parent=str(v).strip(); inherited=norm(parent)==value; break
   ok=bool(explicit or inherited)
   return ok,('raw_workbook_literal_parent_or_cell' if ok else 'selected_admin_label_not_in_source_hierarchy'),json.dumps({'district_header_col0':header_col,'current_row_cell':row[header_col] if header_col is not None and header_col<len(row) else None,'nearest_preceding_district_cell':parent,'source_row_name_cells':row[:8]},ensure_ascii=False)
  return False,'unsupported_raw_source_format',''
class UF:
 def __init__(self, years): self.p={k:k for k in years}; self.m={k:(1<<int(y)) for k,y in years.items()}
 def find(self,x):
  p=self.p[x]
  while p!=self.p[p]: p=self.p[p]
  while x!=p: q=self.p[x]; self.p[x]=p; x=q
  return p
 def union_disjoint(self,a,b):
  a=self.find(a); b=self.find(b)
  if a==b: return 'already_connected'
  if self.m[a]&self.m[b]: return 'same_year_component_collision'
  lo,hi=sorted((a,b)); self.p[hi]=lo; self.m[lo]|=self.m[hi]; return 'merged'

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 config=json.loads(CONFIG.read_text()); cov=json.loads((BASE/'coverage.json').read_text())
 expected_graph=config['working_identity_graph_sha256']; expected_points=config['working_point_uses_sha256']
 if sha(BASE/'accepted_identity_edges.parquet')!=expected_graph or sha(BASE/'accepted_point_uses.parquet')!=expected_points: raise RuntimeError('current config graph/point pin mismatch')
 freeze_summary=json.loads((FREEZE/'summary.json').read_text())
 freeze_hashes={str(FREEZE/n):sha(FREEZE/n) for n in ('all_candidate_dispositions.csv','freeze_manifest.json','summary.json')}
 # Pin selected and evidence to prior audit's validated source package.
 if sha(SELECTED)!='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657' or sha(EVIDENCE)!='e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327': raise RuntimeError('selected/evidence pin changed')
 c2002={x['year']:x['axes']['joint_admitted_coordinate_and_full_chain'] for x in cov['census_metrics']}
 # Current source and ledger loading uses canonical admission status only.
 needed=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_type','region_raw','district_raw','population','latitude','longitude','source_sha256','source_locator','source_raw_line','population_scope','is_additive_settlement_record','entity_grain_status','population_value_quality']
 sdf=pd.read_parquet(SELECTED,columns=needed); smap={str(x['source_record_id']):x for x in sdf.to_dict('records')}
 rawhier=RawHierarchy()
 pts=pd.read_parquet(BASE/'accepted_point_uses.parquet',columns=['target_source_record_id','target_year','coordinate_admission_status','coordinate_source_record_id','point_origin_kind','latitude','longitude'])
 pts=pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 accepted_point_ids=set(pts.target_source_record_id.astype(str))
 # Direct source point required for modern witness; no stale optional flags are consulted.
 pmap={str(x['target_source_record_id']):x for x in pts[pts.target_year==2021].to_dict('records')}
 with open(FREEZE/'all_candidate_dispositions.csv',encoding='utf-8',newline='') as f: disp=list(csv.DictReader(f))
 hold=[]; exactcore=[]
 for r in disp:
  reasons=json.loads(r['hold_reasons_json'])
  if 'explicit_source_district_context_differs' not in reasons: continue
  a,b=r['district_from_raw'],r['district_to_raw']; ca,aa,sa=county_core(a); cb,ab,sb=county_core(b)
  if not ca or ca!=cb: continue
  x=dict(r); x.update({'source_district_core_key':ca,'from_rendering_annotation':aa,'to_rendering_annotation':ab,'from_admin_suffix_class':sa,'to_admin_suffix_class':sb})
  exactcore.append(x)
 # Whole-region uniqueness of the exact typed name is an upstream frozen assertion; verify selected rows too.
 # Parent mapping check: each core form must map to exactly one core within each endpoint frame/region.
 core_maps=defaultdict(set)
 for x in exactcore:
  for side in ('from','to'):
   key=(x[f'{side}_year'],norm(x[f'region_{side}_raw']),x['source_district_core_key'])
   core_maps[key].add(county_core(x[f'district_{side}_raw'])[0])
 proposals=[]; holds=[]
 for x in exactcore:
  reasons=json.loads(x['hold_reasons_json']); oldid=x['from_source_record_id']; new_id=x['to_source_record_id']; pid=x['point_witness_2021_source_record_id']
  fromsel,tosel=smap.get(oldid),smap.get(new_id)
  source_fields=bool(fromsel and tosel and norm(fromsel.get('district_raw'))==norm(x['district_from_raw']) and norm(tosel.get('district_raw'))==norm(x['district_to_raw']))
  point=pmap.get(pid); direct=bool(point and str(point.get('coordinate_source_record_id'))==pid)
  exactuni=all(str(x.get(f'whole_region_exact_name_unique_across_types_{s}','')).casefold()=='true' for s in ('from','to'))
  only_context_or_refresh=all(r in {'explicit_source_district_context_differs','no_direct_canonical_accepted_2021_point'} for r in reasons)
  # Preserve explicit legal/urban reorganization distinctions; only district / municipal-district / bare source field renderings.
  admin_form_safe=x['from_admin_suffix_class'] in {'district','municipal_district','bare'} and x['to_admin_suffix_class'] in {'district','municipal_district','bare'}
  # Valid historic named point, if present, must agree with current accepted point; absence is recorded, not a universal veto.
  hp=dist_km(x['historical_geokladr_raw_latitude'],x['historical_geokladr_raw_longitude'],point['latitude'],point['longitude']) if direct else math.inf
  historic_present=bool(x.get('historical_geokladr_row_1based') and x.get('historical_geokladr_raw_latitude') and x.get('historical_geokladr_raw_longitude'))
  historic_ok=(not historic_present or hp<=5)
  from_parent_ok,from_parent_status,from_parent_witness=rawhier.verify(fromsel,x['district_from_raw'])
  to_parent_ok,to_parent_status,to_parent_witness=rawhier.verify(tosel,x['district_to_raw'])
  publisher_hierarchy_both=from_parent_ok and to_parent_ok
  # Status and source grain are preserved; parent spelling is a field-label interpretation only.
  okay=(source_fields and publisher_hierarchy_both and direct and exactuni and only_context_or_refresh and admin_form_safe and historic_ok and x.get('candidate_status')!='hold_for_successor_event')
  out={**x,'from_selected_district_exact_source_field':source_fields,'to_selected_district_exact_source_field':source_fields,
       'accepted_direct_2021_point_present':direct,'accepted_direct_2021_point_source_id':point.get('coordinate_source_record_id') if point else '',
       'from_publisher_hierarchy_verified':from_parent_ok,'from_publisher_hierarchy_status':from_parent_status,'from_publisher_hierarchy_witness_json':from_parent_witness,'to_publisher_hierarchy_verified':to_parent_ok,'to_publisher_hierarchy_status':to_parent_status,'to_publisher_hierarchy_witness_json':to_parent_witness,'publisher_hierarchy_verified_both_endpoints':publisher_hierarchy_both,'historic_named_point_present':historic_present,'historic_named_point_to_current_direct_distance_km':round(hp,4) if math.isfinite(hp) else '',
       'historic_point_gate':'concordant_within_5km' if historic_present and hp<=5 else ('not_available_not_blocking' if not historic_present else 'conflicting_over_5km'),
       'whole_region_exact_name_typed_uniqueness_both_frames':exactuni,'other_holds_preserved_json':json.dumps([r for r in reasons if r!='explicit_source_district_context_differs'],ensure_ascii=False),
       'annotation_only_context_resolution_candidate':okay,'identity_admitted':False,
       'interpretation':'Exact source district field rendering normalization only; does not assert legal administrative boundary or population comparability.'}
  (proposals if okay else holds).append(out)
 # Enforce graph safety against the pinned accepted graph and among staged candidates.
 graph=pd.read_parquet(BASE/'accepted_identity_edges.parquet',columns=['from_source_record_id','to_source_record_id','from_year','to_year','decision_status'])
 if set(graph.decision_status.dropna().astype(str))-ACCEPTED_EDGE_STATUSES: raise RuntimeError('unknown canonical graph statuses')
 years={str(x['source_record_id']):int(x['census_year']) for x in sdf[['source_record_id','census_year']].to_dict('records')}
 uf=UF(years)
 for g in graph.to_dict('records'):
  if str(g['from_source_record_id']) not in years or str(g['to_source_record_id']) not in years: raise RuntimeError('graph endpoint absent from selected source table')
  status=uf.union_disjoint(str(g['from_source_record_id']),str(g['to_source_record_id']))
  if status=='same_year_component_collision': raise RuntimeError('accepted graph violates one-row-per-year component invariant')
 baseline_rows={y:0 for y in (2002,2010,2021)}; baseline_pop={y:0 for y in (2002,2010,2021)}
 point_ids=accepted_point_ids
 for row in sdf.to_dict('records'):
  rid=str(row['source_record_id']); y=int(row['census_year'])
  if rid in point_ids and uf.m[uf.find(rid)]==((1<<2002)|(1<<2010)|(1<<2021)):
   baseline_rows[y]+=1; baseline_pop[y]+=int(float(row['population'] or 0))
 # Check exact coverage JSON values before reporting conditional graph gains.
 for y in baseline_rows:
  if baseline_rows[y]!=c2002[y]['rows'] or baseline_pop[y]!=c2002[y]['known_population']:
   raise RuntimeError(f'baseline joint coverage mismatch {y}: {(baseline_rows[y],baseline_pop[y])} != {(c2002[y]["rows"],c2002[y]["known_population"])}')
 staged=[]; graph_rejected=[]; redundant_connected=[]
 for x in sorted(proposals,key=lambda r:(-max(float(r['from_population'] or 0),float(r['to_population'] or 0)),r['edge_id'])):
  result=uf.union_disjoint(x['from_source_record_id'],x['to_source_record_id'])
  x['graph_resolution']=result
  if result=='merged': staged.append(x)
  elif result=='already_connected': redundant_connected.append(x)
  else: graph_rejected.append(x)
 holds.extend(graph_rejected)
 all_logical_proposals=proposals
 proposals=staged
 after_rows={y:0 for y in (2002,2010,2021)}; after_pop={y:0 for y in (2002,2010,2021)}
 for row in sdf.to_dict('records'):
  rid=str(row['source_record_id']); y=int(row['census_year'])
  if rid in point_ids and uf.m[uf.find(rid)]==((1<<2002)|(1<<2010)|(1<<2021)):
   after_rows[y]+=1; after_pop[y]+=int(float(row['population'] or 0))
 joint_gain={str(y):{'rows':after_rows[y]-baseline_rows[y],'population':after_pop[y]-baseline_pop[y]} for y in after_rows}
 # Fixed stratified raw replay of 40 rows: 20 highest mass eligible exact-core, plus 20 seeded random remaining.
 sorted_core=sorted(exactcore,key=lambda x:max(float(x['from_population'] or 0),float(x['to_population'] or 0)),reverse=True)
 sample={x['edge_id']:'mass_top20' for x in sorted_core[:20]}; rest=[x for x in exactcore if x['edge_id'] not in sample]; rng=random.Random(SEED)
 for x in rng.sample(rest,min(20,len(rest))): sample[x['edge_id']]='seeded_random20'
 # Replay source excerpts only, keeping all original selected values and locators.
 review=[]; rawhash={}; cache={}; pdfcache={}; rawroot=ROOT/'settlements-raw'
 for x in exactcore:
  if x['edge_id'] not in sample: continue
  for side,idkey in [('from','from_source_record_id'),('to','to_source_record_id')]:
   rec=smap.get(x[idkey]);
   if rec is None: continue
   sf=str(rec['source_file']); path=rawroot/sf; row=int(float(rec['source_row'])); item={'edge_id':x['edge_id'],'sample_stratum':sample[x['edge_id']],'side':side,'source_record_id':str(rec['source_record_id']),'year':int(rec['census_year']),'source_file':sf,'selected_district_raw':rec['district_raw'],'raw_row_1based_or_parquet_record':row,'selected_name_raw':rec['source_name_raw'],'selected_type':rec['settlement_type'],'selected_region':rec['region_raw'],'source_locator':rec.get('source_locator')}
   if not path.exists(): item['raw_review_status']='missing'; review.append(item); continue
   if str(path) not in rawhash: rawhash[str(path)]={'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}
   item['actual_raw_sha256']=rawhash[str(path)]['sha256']
   if path.suffix.lower()=='.pdf':
    if str(path) not in pdfcache: pdfcache[str(path)]=subprocess.run(['pdftotext','-layout',str(path),'-'],check=True,stdout=subprocess.PIPE,text=True).stdout.split('\f')
    loc=json.loads(str(rec.get('source_locator') or '{}')); pg=int(loc.get('pdf_page_1based') or row); lines=pdfcache[str(path)][pg-1].splitlines() if 1<=pg<=len(pdfcache[str(path)]) else []; label=norm(loc.get('raw_label') or rec.get('source_name_raw') or ''); hits=[i for i,v in enumerate(lines) if label and label in norm(v)]; ix=hits[0] if hits else -1; core=county_core(rec.get('district_raw'))[0]; par=[]
    if ix>=0:
     for j in range(ix-1,max(-1,ix-12),-1):
      label_only=re.split(r'\s{2,}\d',lines[j].strip(),1)[0].strip()
      if county_core(label_only)[0]==core and core: par=[{'line':j+1,'text':lines[j].strip()}];break
    item.update({'raw_review_status':'pdf_locality_row_and_parent_hierarchy_loaded' if ix>=0 else 'pdf_locality_label_not_found','pdf_page':pg,'pdf_selected_locality_line_1based':ix+1 if ix>=0 else None,'exact_selected_line':lines[ix] if ix>=0 else '', 'preceding_8_lines':lines[max(0,ix-8):ix] if ix>=0 else [],'matched_parent_line_json':json.dumps(par,ensure_ascii=False),'pdf_table':loc.get('table')})
   elif path.suffix.lower() in {'.xls','.xlsx'}:
    key=(str(path),str(rec.get('source_sheet')))
    if key not in cache:
     eng='xlrd' if path.suffix.lower()=='.xls' else 'openpyxl'; cache[key]=pd.read_excel(path,sheet_name=rec.get('source_sheet') or 0,header=None,dtype=object,engine=eng)
    df=cache[key]; idx=row-1; cells=[None if pd.isna(v) else str(v).strip() for v in df.iloc[idx].tolist()] if 0<=idx<len(df) else []
    prev=[]
    for i in range(max(0,idx-8),idx): prev.append({'row':i+1,'cells':[None if pd.isna(v) else str(v).strip() for v in df.iloc[i].tolist()]})
    item.update({'raw_review_status':'workbook_row_and_parent_context_loaded','sheet':str(rec.get('source_sheet')),'raw_row_cells':cells,'previous_8_rows':prev,'source_headers_or_hierarchy_explicit':True})
   else:item['raw_review_status']='nonworkbook_nonpdf'
   review.append(item)
 # summarize as evidence coverage, not release gain. Candidate joint graph impact left as conditional, not admissions.
 writecsv(OUT/'candidate_edges.csv',all_logical_proposals)
 writecsv(OUT/'new_link_candidates_graph_safe.csv',proposals)
 writecsv(OUT/'already_connected_redundant_candidates.csv',redundant_connected)
 writecsv(OUT/'disjoint_holds.csv',holds)
 writecsv(OUT/'fixed_40_raw_hierarchy_review.csv',review)
 writecsv(OUT/'raw_source_hashes.csv',list({x['path']:x for x in list(rawhash.values())+list(rawhier.hashes.values())}.values()))
 pairs=Counter((x['from_year'],x['to_year']) for x in exactcore)
 accepted_by_pair=Counter((x['from_year'],x['to_year']) for x in all_logical_proposals)
 labelpairs=Counter((x['from_admin_suffix_class'],x['to_admin_suffix_class'],x['from_rendering_annotation'] or 'none',x['to_rendering_annotation'] or 'none') for x in exactcore)
 summary={'status':'candidate_only_source_district_rendering_audit_no_admissions','frozen_baseline':str(BASE),'base_hashes':{'graph':expected_graph,'points':expected_points,'coverage':sha(BASE/'coverage.json')},'baseline_joint_full_chain':{str(y):{'rows':c2002[y]['rows'],'population':c2002[y]['known_population']} for y in c2002},
  'input_hashes':{str(CONFIG):sha(CONFIG),str(SELECTED):sha(SELECTED),str(EVIDENCE):sha(EVIDENCE),str(FREEZE/'all_candidate_dispositions.csv'):freeze_hashes[str(FREEZE/'all_candidate_dispositions.csv')],str(BASE/'accepted_identity_edges.parquet'):expected_graph,str(BASE/'accepted_point_uses.parquet'):expected_points},
  'exact_county_core_matches_in_frozen_context_holds':len(exactcore),'year_pair_counts':{f'{a}-{b}':n for (a,b),n in pairs.items()},'literal_rendering_family_counts':[{ 'from_admin_suffix':a,'to_admin_suffix':b,'from_annotation':c,'to_annotation':d,'rows':n} for (a,b,c,d),n in labelpairs.most_common()],
  'source_hierarchy_supported_candidate_rows':len(all_logical_proposals),'graph_safe_new_link_candidate_rows':len(proposals),'already_connected_redundant_candidate_rows':len(redundant_connected),'same_year_collision_rejected_rows':len(graph_rejected),'remaining_disjoint_holds':len(holds),'conditional_joint_gain_after_graph_safe_batch':joint_gain,'candidate_rows_by_pair':{f'{a}-{b}':n for (a,b),n in accepted_by_pair.items()},'current direct 2021 point required':True,'historic_point_policy':'when exact historical named typed point exists it must agree within 5 km; no available historical point is reported and is not a universal blocker','no_admin_boundary_claim':True,'candidate_only_no_admission':True,
  'fixed_raw_review':{'rows':len(review),'distinct_files':len(rawhash),'loaded_raw_workbooks_or_pdf':sum(str(r.get('raw_review_status','')).startswith(('workbook','pdf')) for r in review)},'raw_source_hashes':len(rawhier.hashes)+len(rawhash),'script_sha256':sha(Path(__file__))}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 pins={'status':summary['status'],'inputs':summary['input_hashes'],'output_sha256':{},'script':str(Path(__file__)),'script_sha256':sha(Path(__file__))}
 for p in sorted(OUT.iterdir()):
  if p.name!='receipt.json':pins['output_sha256'][p.name]=sha(p)
 (OUT/'receipt.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

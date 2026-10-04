#!/usr/bin/env python3
"""Stage 2002 county/selsoviet backed homonym candidates for Moscow/Altai.

Candidate-only. The historical worksheet ancestry, 2009 classifier parent,
2011 named typed point, current publisher hierarchy/native OKTMO and admitted
current point are separate witnesses. No population or accepted ledger edits.
"""
from __future__ import annotations

import csv, hashlib, json, math, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pandas as pd
import numpy as np
import xlrd

ROOT=Path('/workspace')
BASE=ROOT/'settlements-work/continuation_20261004/R4/raw_2002_residual_admin_hierarchy_candidates_20261004'
OUT=BASE/'freeze_v4'
RESID=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/joint_residual.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/accepted_point_uses.parquet'
COVERAGE=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/coverage.json'
SELECTED=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
SQL=ROOT/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
DBF=ROOT/'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
SOURCES={
 'moscow':ROOT/'settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls',
 'altai':ROOT/'settlements-raw/data/raw/2002/066_76aa869929_Altai_krai1.xls',
}
sys.path.insert(0,str(ROOT/'russian-settlements-research/research_rebuild/mass_linkage'))
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES
from raw_okato_classifier import read_copy
from verify_geokladr_snapshot import parse_dbf_records

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
 return h.hexdigest()
def txt(v):
 if v is None or (isinstance(v,float) and math.isnan(v)): return ''
 return str(v).strip()
def norm(v):
 s=unicodedata.normalize('NFKC',txt(v)).casefold().replace('ё','е')
 return re.sub(r'\s+',' ',re.sub(r'[^а-яa-z0-9]+',' ',s)).strip()
def regkey(v):
 x=norm(v)
 for suf in ('автономная область','автономный округ','город федерального значения','республика','область','край'):
  x=re.sub(r'\b'+re.escape(suf)+r'\b','',x).strip()
 return x
def typekey(v):
 x=norm(v)
 return {'пгт':'поселок городского типа','посёлок городского типа':'поселок городского типа','посёлок':'поселок'}.get(x,x)
def admkey(v):
 x=norm(v)
 for p in ('сельское поселение ','городское поселение ','муниципальное образование ','муниципальный район ','муниципальный округ ','городской округ '):
  if x.startswith(p): x=x[len(p):].strip(); break
 for suf in ('сельский административный округ','сельский округ','сельсовет','муниципальным районом','муниципального района','муниципальный район','городской округ','муниципальном районе','район','р-н'):
  if x.endswith(' '+suf): x=x[:-(len(suf)+1)].strip(); break
 return x
def raw_parent_matches(raw_label, selected_label):
 a=norm(raw_label); b=norm(selected_label)
 if not a or not b:return False
 if a==b:return True
 # These exact suffixes are table grain headings attached to the printed
 # district/council name, not part of the administrative name.
 a=re.sub(r'\s+(?:все\s+)?(?:городское|сельское) население$','',a).strip()
 return a==b
def hav(a,b,c,d):
 try: x=[float(a),float(b),float(c),float(d)]
 except (TypeError,ValueError): return None
 if not all(math.isfinite(z) for z in x): return None
 r=math.pi/180; p1=x[0]*r;p2=x[2]*r
 q=math.sin((x[2]-x[0])*r/2)**2+math.cos(p1)*math.cos(p2)*math.sin((x[3]-x[1])*r/2)**2
 return 6371.0088*2*math.atan2(math.sqrt(q),math.sqrt(max(0,1-q)))
def csvout(path,rows):
 if not rows: Path(path).write_text('',encoding='utf-8'); return
 keys=[]; seen=set()
 for r in rows:
  for k in r:
   if k not in seen: seen.add(k);keys.append(k)
 with open(path,'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys,extrasaction='raise');w.writeheader();w.writerows(rows)

class DSU:
 def __init__(self,n,years): self.p=np.arange(n,dtype=np.int32);self.sz=np.ones(n,dtype=np.int32);self.years=[{int(y)} for y in years];self.point=np.zeros(n,dtype=np.bool_)
 def find(self,x):
  while self.p[x]!=x: self.p[x]=self.p[self.p[x]];x=int(self.p[x])
  return x
 def union(self,a,b):
  a=self.find(a);b=self.find(b)
  if a==b:return 'already_connected'
  if self.years[a]&self.years[b]: return 'year_collision'
  if self.sz[a]<self.sz[b]:a,b=b,a
  self.p[b]=a;self.sz[a]+=self.sz[b];self.years[a]|=self.years[b]
  return 'merged'

def workbook_ancestry(path, sheet_name, rownums):
 wb=xlrd.open_workbook(path,on_demand=True); sh=wb.sheet_by_name(sheet_name)
 # Audited family layout: Moscow label in column B; Altai in column A.
 label_col=1 if 'Moskovskaya' in str(path) else 0
 wanted={int(x) for x in rownums}; result={}; stack=[]
 for j in range(max(wanted,default=0)):
  v=sh.cell_value(j,label_col); raw=str(v) if v is not None else ''
  if not raw.strip(): continue
  depth=len(raw)-len(raw.lstrip(' '))
  stack=[z for z in stack if z['indent']<depth]
  if j+1 in wanted:
   result[j+1]=(list(stack),[sh.cell_value(j,k) for k in range(sh.ncols)])
  else:
   stack.append({'indent':depth,'row_1based':j+1,'label_raw':raw,'cells':[sh.cell_value(j,k) for k in range(sh.ncols)]})
 wb.release_resources()
 return result

def main():
 if OUT.exists() and any(OUT.iterdir()): raise SystemExit(f'Output exists; refusing overwrite: {OUT}')
 OUT.mkdir(parents=True,exist_ok=True)
 pins={str(p):sha(p) for p in [RESID,GRAPH,POINTS,COVERAGE,SELECTED,SQL,DBF,*SOURCES.values()]}
 # Candidate old observations are only actual unresolved source rows in the
 # two audited workbook families.
 c=duckdb.connect();c.execute("SET threads=1");c.execute("SET memory_limit='1GB'")
 old=c.execute(f"""SELECT source_record_id,census_year,source_file,source_sheet,source_row,source_native_id,source_name_raw,settlement_name,settlement_type,region_raw,region_norm,district_raw,municipality_raw,population,name_norm,type_norm,source_sha256,source_locator,population_scope,is_additive_settlement_record,entity_grain_status,identity_admission,coordinate_admission FROM read_parquet('{RESID}') WHERE census_year=2002 AND source_file IN ({','.join(repr(p.relative_to(ROOT/'settlements-raw').as_posix()) for p in SOURCES.values())})""").df()
 cur=c.execute(f"""SELECT source_record_id,census_year,source_file,source_sheet,source_row,source_native_id,source_name_raw,settlement_name,settlement_type,region_raw,region_norm,district_raw,municipality_raw,population,oktmo,okato,name_norm,type_norm,source_sha256,source_locator,population_scope,is_additive_settlement_record,entity_grain_status,identity_admission,coordinate_admission FROM read_parquet('{SELECTED}') WHERE census_year=2021""").df(); c.close()
 for df in (old,cur):
  for col in ('source_record_id','name_norm','type_norm','region_norm'): df[col]=df[col].fillna('').astype(str)
 cur['oktmo_s']=cur.oktmo.map(txt)
 oktmo_counts=Counter(cur.oktmo_s[cur.oktmo_s!=''])
 by_key=defaultdict(list)
 for r in cur.to_dict('records'): by_key[(r['name_norm'],r['type_norm'],r['region_norm'])].append(r)
 # Load classifier and DBF once. Codes are used only when the actual raw source
 # parent row and exact source typed name/region agree.
 cls=read_copy(SQL); cls_by_code=defaultdict(list)
 for r in cls.to_dict('records'): cls_by_code[txt(r['historical_okato'])].append(r)
 cls_unique={k:v[0] for k,v in cls_by_code.items() if len(v)==1}
 region_code={}
 for code,rowset in cls_by_code.items():
  if re.fullmatch(r'\d{2}000000',code) and len(rowset)==1: region_code[code[:2]]=rowset[0]
 cls_by_key=defaultdict(list)
 for r in cls.to_dict('records'):
  code=txt(r['historical_okato']); rr=region_code.get(code[:2])
  if len(code) not in (8,11) or r.get('is_settlement_raw')!='t' or not rr: continue
  cls_by_key[(regkey(rr['name_raw']),norm(r['name']),typekey(r['status']))].append(r)
 meta,dbf=parse_dbf_records(DBF); dbf_by_code=defaultdict(list)
 short={'д':'деревня','с':'село','г':'город','п':'поселок','пгт':'поселок городского типа','х':'хутор','ст':'станция','ст-ца':'станица','аул':'аул','м':'местечко','рзд':'железнодорожный разъезд'}
 for g in dbf:
  code=txt(g.get('historical_okato'))
  if code: dbf_by_code[code].append(g)
 # Current accepted direct point witnesses; ignore optional historical candidate
 # flags and honor only canonical coordinate admission statuses.
 pcols=['target_source_record_id','target_year','coordinate_admission_status','latitude','longitude','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']
 pts=pd.read_parquet(POINTS,columns=pcols); pts=pts[pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 direct={}
 for r in pts[pts.target_year==2021].to_dict('records'):
  rid=txt(r['target_source_record_id'])
  if rid==txt(r['coordinate_source_record_id']): direct[rid]=r
 # Prepare raw source ancestry and candidate review rows.
 selected_by_id={r['source_record_id']:r for r in old.to_dict('records')}
 ancmap={}; rawchecks={}; rawhash={}
 for fam,path in SOURCES.items():
  rawhash[str(path)]={'sha256':pins[str(path)],'bytes':path.stat().st_size}
  these=old[old.source_file==path.relative_to(ROOT/'settlements-raw').as_posix()]
  workbook_rows=workbook_ancestry(path,txt(these.iloc[0].source_sheet),these.source_row.tolist()) if len(these) else {}
  for o in these.to_dict('records'):
   rid=o['source_record_id'];stack,cells=workbook_rows[int(o['source_row'])]
   selected_label=txt(o['source_name_raw']); target_has_source_label=any(norm(v)==norm(selected_label) for v in cells if isinstance(v,str))
   anc_d=[a for a in stack if raw_parent_matches(a['label_raw'],o['district_raw'])]
   anc_m=[a for a in stack if raw_parent_matches(a['label_raw'],o['municipality_raw'])]
   rawchecks[rid]={'worksheet_row_1based':int(o['source_row']),'worksheet_raw_target_cells':cells,'source_name_raw_in_row':target_has_source_label,
    'district_ancestor_rows':anc_d,'municipality_ancestor_rows':anc_m,'district_source_value':o['district_raw'] or None,'municipality_source_value':o['municipality_raw'] or None,
    'district_visible_in_ancestor_stack':bool(anc_d),'municipality_visible_in_ancestor_stack':bool(anc_m)}
   ancmap[rid]=stack
 # Build one candidate per exact historical source object and exact current
 # same-name/type/province key after county/selsoviet / point disambiguation.
 staged=[]; holds=[]; redundant=[]
 for o in old.to_dict('records'):
  rid=o['source_record_id']; audit=rawchecks[rid]
  candidates=by_key.get((o['name_norm'],o['type_norm'],o['region_norm']),[])
  base={'from_source_record_id':rid,'from_year':2002,'from_source_file':o['source_file'],'from_source_row_1based':int(o['source_row']),'from_source_raw_name':o['source_name_raw'],
   'from_settlement_name':o['settlement_name'],'from_settlement_type':o['settlement_type'],'from_region_raw':o['region_raw'],'from_population':int(o['population'] or 0),
   'from_selected_district_raw':o['district_raw'] or None,'from_selected_municipality_raw':o['municipality_raw'] or None,
   'actual_raw_worksheet_parent_chain_json':json.dumps(ancmap[rid],ensure_ascii=False),'raw_row_and_ancestor_audit_json':json.dumps(audit,ensure_ascii=False),
   'current_exact_name_type_region_candidates':len(candidates)}
  reason=[]
  if not candidates: reason.append('no_exact_current_2021_name_type_province_candidate')
  if not audit['source_name_raw_in_row']: reason.append('raw_worksheet_settlement_label_not_reproduced')
  if o['district_raw'] and not audit['district_visible_in_ancestor_stack']: reason.append('selected_district_not_literal_raw_ancestor')
  if o['municipality_raw'] and not audit['municipality_visible_in_ancestor_stack']: reason.append('selected_municipality_not_literal_raw_ancestor')
  key=(regkey(o['region_raw']),norm(o['settlement_name']),typekey(o['settlement_type']))
  hrows=cls_by_key.get(key,[])
  # Require the classifier child to be uniquely located below the exact raw
  # census district, with a real unique 8-digit nonsettlement parent row.
  district_norm=admkey(o['district_raw'])
  matching=[]
  for h in hrows:
   code=txt(h['historical_okato']); parent_code=code[:5]+'000' if len(code) in (8,11) else ''
   parent=cls_unique.get(parent_code)
   if parent and parent.get('is_settlement_raw')=='f' and not txt(parent.get('status')) and admkey(parent.get('name_raw'))==district_norm:
    matching.append((h,parent,parent_code))
  if len(matching)!=1: reason.append('2009_classifier_child_not_unique_under_literal_census_district_ancestor')
  h=matching[0][0] if len(matching)==1 else None; parent=matching[0][1] if len(matching)==1 else None; pcode=matching[0][2] if len(matching)==1 else ''
  geo=None; geocode=''
  if h:
   hcode=txt(h['historical_okato']); geocode=hcode if len(hcode)==11 else (hcode+'000' if len(hcode)==8 else '')
   gs=dbf_by_code.get(geocode,[])
   valid=[]
   for g in gs:
    raw=txt(g.get('name_raw')).split(maxsplit=1); typ=short.get(raw[0].casefold(),'') if raw else ''; name=raw[1] if len(raw)>1 else ''
    if (g.get('deleted_marker_raw')==' ' and norm(name)==norm(o['settlement_name']) and typekey(typ)==typekey(o['settlement_type']) and
        regkey(region_code.get(geocode[:2],{}).get('name_raw',''))==regkey(o['region_raw'])): valid.append(g)
   if len(valid)==1: geo=valid[0]
  if geo is None: reason.append('2011_named_typed_physical_point_not_unique_exact_classifier_code')
  if geo is not None and (geo.get('latitude_from_lat') is None or geo.get('longitude_from_long') is None): reason.append('2011_point_missing')
  dists=[]; witnessed=[]
  for q in candidates:
   qid=q['source_record_id']; pt=direct.get(qid)
   code=txt(q.get('oktmo_s'))
   qx={**base,'to_source_record_id':qid,'to_year':2021,'to_source_file':q['source_file'],'to_source_row_1based':int(q['source_row']),
       'to_source_raw_name':q['source_name_raw'],'to_settlement_name':q['settlement_name'],'to_settlement_type':q['settlement_type'],'to_region_raw':q['region_raw'],
       'to_population':int(q['population'] or 0),'to_native_oktmo_raw':code or None,'to_district_raw':q['district_raw'] or None,'to_municipality_raw':q['municipality_raw'] or None,
       'to_source_locator':q['source_locator'],'to_publisher_sha256':q['source_sha256']}
   if code and oktmo_counts[code]!=1: qx['to_native_oktmo_unique_current_source']=False
   else: qx['to_native_oktmo_unique_current_source']=bool(code)
   dist=hav(geo.get('latitude_from_lat') if geo else None,geo.get('longitude_from_long') if geo else None,pt.get('latitude') if pt else None,pt.get('longitude') if pt else None) if pt else None
   dists.append((q,pt,dist,qx))
  # Candidate source hierarchy can directly disambiguate Altai administrative
  # homonyms. Moscow reorganized its county/council hierarchy; in that family
  # exact historical code+point chooses only an independently close current
  # physical place, retaining modern labels without asserting a rename.
  chosen=[]; family=''
  if fam=='altai':
   direct_admin=[x for x in dists if x[3]['to_native_oktmo_unique_current_source'] and
      district_norm and admkey(x[0].get('district_raw'))==district_norm and
      admkey(o['municipality_raw']) and admkey(x[0].get('municipality_raw'))==admkey(o['municipality_raw'])]
   if len(direct_admin)==1 and direct_admin[0][2] is not None and direct_admin[0][2]<=5:
    chosen=direct_admin; family='altai_literal_district_selsoviet_plus_native_2011_point'
   elif len(direct_admin)>1: reason.append('multiple_current_rows_share_literal_district_and_selsoviet')
  if not chosen and dists:
   measured=sorted([x for x in dists if x[2] is not None and x[3]['to_native_oktmo_unique_current_source']],key=lambda x:x[2])
   # Exact historic named native object and exact proper current source key
   # support a unique current target only when it is close and separated from
   # same-key current homonyms. A lone same-key record uses a 5 km continuity
   # envelope; a homonym disambiguation needs <=1 km and next competitor >5 km.
   if len(candidates)==1 and len(measured)==1 and measured[0][2]<=5:
    chosen=measured; family='unique_source_key_historic_typed_point_continuity'
   elif len(measured)>=1 and measured[0][2]<=1 and (len(measured)==1 or measured[1][2]>5):
    chosen=[measured[0]]; family='historic_typed_point_resolves_current_same_key_homonym'
  if not chosen:
   reason.append('current_homonym_not_resolved_by_exact_admin_or_separated_native_point')
  if chosen and not reason:
   q,pt,distance,qx=chosen[0]
   scope=str(q.get('population_scope') or '').casefold(); grain=str(q.get('entity_grain_status') or '').casefold()
   if q.get('is_additive_settlement_record') is not True: reason.append('current_row_not_explicitly_additive')
   if any(t in scope for t in ('federal','territor')) or 'aggregate' in grain: reason.append('current_source_federal_or_aggregate')
   if not qx['to_native_oktmo_unique_current_source']: reason.append('current_native_oktmo_missing_or_nonunique')
   if not pt: reason.append('no_canonical_accepted_direct_current_source_point')
   if distance is None or distance>5: reason.append('historical_to_current_point_distance_over_5km_or_unknown')
   if not reason:
    staged.append({**qx,'rule_family':family,'status':'candidate_only_not_admitted','same_place_inference':'same physical settlement between 2002 and 2021; historical and current administrative labels remain separate observations','current_population_scope':q.get('population_scope'),
      'current_accepted_point_latitude':pt['latitude'],'current_accepted_point_longitude':pt['longitude'],'current_point_origin_file':pt.get('point_origin_file'),'current_point_origin_sha256':pt.get('point_origin_sha256'),'current_point_origin_locator':pt.get('point_origin_locator'),'current_point_origin_kind':pt.get('point_origin_kind'),
      'historical_2009_code_raw':txt(h.get('historical_okato')),'historical_classifier_raw_name':txt(h.get('name_raw')),'historical_classifier_raw_type':txt(h.get('status')),'historical_classifier_child_line':h.get('source_line_1based') or h.get('line_number'),
      'historical_2009_parent_code_raw':pcode,'historical_2009_parent_name_raw':txt(parent.get('name_raw')),'historical_2011_code_raw':geocode,'historical_2011_name_raw':txt(geo.get('name_raw')),'historical_2011_type_raw':txt(geo.get('settlement_type_raw')),
      'historical_2011_dbf_record_1based':geo.get('record_number_1based'),'historical_2011_dbf_byte_offset_0based':geo.get('record_byte_offset_0based'),'historical_2011_point_latitude':geo.get('latitude_from_lat'),'historical_2011_point_longitude':geo.get('longitude_from_long'),
      'historical_to_current_point_distance_km':round(distance,6),'current_same_key_competitors_json':json.dumps([{'source_record_id':x[0]['source_record_id'],'district_raw':x[0].get('district_raw'),'municipality_raw':x[0].get('municipality_raw'),'native_oktmo':x[3].get('to_native_oktmo_raw'),'historical_point_distance_km':x[2]} for x in sorted(dists,key=lambda z:(z[2] is None,z[2] or 0))],ensure_ascii=False),
      'source_hierarchy_evidence_json':json.dumps(audit,ensure_ascii=False),'identity_edge_candidate':True,'point_use_candidate':True,'population_boundary_comparability_claimed':False,'legal_admin_rename_claimed':False})
   else:
    holds.append({**base,'candidate_current_rows_json':json.dumps([{'source_record_id':x[0]['source_record_id'],'district':x[0].get('district_raw'),'municipality':x[0].get('municipality_raw'),'oktmo':x[0].get('oktmo_s'),'distance_km':x[2]} for x in dists],ensure_ascii=False),'hold_reasons_json':json.dumps(sorted(set(reason)),ensure_ascii=False)})
  else:
   holds.append({**base,'hold_reasons_json':json.dumps(sorted(set(reason)),ensure_ascii=False)})
 # Candidate unique pair keys only; graph simulation below enforces no duplicate-year component.
 if len({(r['from_source_record_id'],r['to_source_record_id']) for r in staged})!=len(staged): raise SystemExit('duplicate candidate pair')
 # Full baseline graph simulation: all selected records are vertices, accepted
 # edges and points use canonical statuses. Optional legacy admission flags are ignored.
 allsel=pd.read_parquet(SELECTED,columns=['source_record_id','census_year','population','population_scope','is_additive_settlement_record','entity_grain_status'])
 ids=allsel.source_record_id.astype(str).tolist(); idx={x:i for i,x in enumerate(ids)}
 dsu=DSU(len(ids),allsel.census_year.astype(int).to_numpy())
 ep=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','decision_status'])
 ep=ep[ep.decision_status.isin(ACCEPTED_EDGE_STATUSES)]
 for a,b in ep[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
  if str(a) in idx and str(b) in idx: dsu.union(idx[str(a)],idx[str(b)])
 for x in pts.target_source_record_id.astype(str):
  if x in idx: dsu.point[idx[x]]=True
 def coverage():
  roots={}
  for i,rid in enumerate(ids):
   root=dsu.find(i); roots.setdefault(root,dsu.years[root])
  mask=[]
  for i,r in enumerate(allsel.itertuples(index=False)):
   root=dsu.find(i); ok=dsu.years[root]=={2002,2010,2021} and bool(dsu.point[i])
   mask.append(ok)
  f=pd.DataFrame({'year':allsel.census_year.astype(int),'population':allsel.population,'scope':allsel.population_scope,'add':allsel.is_additive_settlement_record,'grain':allsel.entity_grain_status,'full':mask})
  f=f[(f['add']==True)&(~f['scope'].fillna('').str.contains('federal|territor',case=False,regex=True))&(~f['grain'].fillna('').str.contains('aggregate',case=False))]
  return {str(y):{'rows':int(g.full.sum()),'population':int(g.loc[g.full,'population'].fillna(0).sum())} for y,g in f.groupby('year')}
 baseline=coverage(); expected=json.loads(COVERAGE.read_text())
 published={str(x['year']):{'rows':int(x['axes']['joint_admitted_coordinate_and_full_chain']['rows']),
   'population':int(x['axes']['joint_admitted_coordinate_and_full_chain']['known_population'])} for x in expected['census_metrics']}
 if baseline!=published:
  raise SystemExit(f'baseline mismatch; refusing conditional gains: recomputed={baseline}; published={published}')
 # Apply proposed identity+historic point-use additions, graph-safe.
 gains=[]; graphholds=[]; accepted=[]
 for r in sorted(staged,key=lambda x:(-int(x['from_population']),x['from_source_record_id'],x['to_source_record_id'])):
  a=idx[r['from_source_record_id']];b=idx[r['to_source_record_id']]
  res=dsu.union(a,b)
  if res=='year_collision': graphholds.append({**r,'graph_status':'hold_same_year_component_collision'});continue
  # Candidate historical native point is now conditionally used for the old row.
  dsu.point[a]=True
  accepted.append({**r,'conditional_graph_union_result':res,'identity_edge_candidate':res=='merged',
    'point_use_candidate':True,'candidate_kind':'identity_edge_plus_historical_point' if res=='merged' else 'historical_point_use_only_existing_identity_component',
    'candidate_only':True,'admission_allowed':False})
 after=coverage()
 # Exact conditional new coverage by year from actual graph/point simulation.
 gain={y:{'rows':after[y]['rows']-baseline[y]['rows'],'population':after[y]['population']-baseline[y]['population']} for y in after}
 csvout(OUT/'identity_edge_point_candidates.csv',accepted)
 csvout(OUT/'graph_safe_holds.csv',graphholds);csvout(OUT/'disjoint_source_holds.csv',holds)
 summary={'status':'candidate_only_raw_2002_admin_hierarchy_homonym_recovery_no_admissions','families':{'moscow':'literal census county ancestor + exact 2009/2011 typed native object; where current hierarchy was reorganized, exact historical point must uniquely resolve a same-key current homonym','altai':'literal census district and selsoviet ancestors + current proper municipality/district exact normalized wrapper comparison, corroborated by exact native 2011 point'},
  'candidate_counts':{'residual_old_source_rows':len(old),'source_and_hierarchy_candidate_pairs_before_graph':len(staged),'graph_safe_candidate_rows':len(accepted),'new_identity_edges':sum(r['identity_edge_candidate'] for r in accepted),'historical_point_uses_on_existing_components':sum(not r['identity_edge_candidate'] for r in accepted),'graph_year_collision_holds':len(graphholds),'source_or_identity_holds':len(holds)},
  'candidate_endpoint_population_sum_not_gain':{'old_2002':int(sum(int(r['from_population']) for r in accepted)),'current_2021':int(sum(int(r['to_population']) for r in accepted))},
  'baseline_joint_full_coverage_recomputed':baseline,'conditional_joint_full_gain_after_identity_and_old_native_point_candidates':gain,'conditional_coverage_after_batch':after,
  'rule_limits':['No Dadata/legacy helper OKATO fields used as native settlement codes.','Current native OKTMO is copied only from the selected 2021 publisher row and must be unique among selected 2021 records.','Old classifier child and parent are matched from the exact raw name/type/province and printed worksheet county ancestor; opaque source row IDs are not codes.','2009 classifier/2011 DBF point rows preserve raw codes, line/row/byte locators, labels and coordinates.','Current/old administrative labels are retained separately; no legal rename, district continuity, or population-boundary comparability is claimed.','Candidates and simulated gains require independent review and are not admissions.'],
  'input_pins':pins,'raw_sources':rawhash,'outputs':{},'accepted_edge_statuses':sorted(ACCEPTED_EDGE_STATUSES),'accepted_coordinate_statuses':sorted(ACCEPTED_COORDINATE_STATUSES)}
 for fn in ('identity_edge_point_candidates.csv','graph_safe_holds.csv','disjoint_source_holds.csv'):
  summary['outputs'][fn]={'sha256':sha(OUT/fn),'bytes':(OUT/fn).stat().st_size}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 summary['outputs']['summary.json_sha_before_receipt']=sha(OUT/'summary.json')
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'candidates':len(accepted),'holds':len(holds),'graph_holds':len(graphholds),'baseline':baseline,'conditional_gain':gain,'summary':str(OUT/'summary.json')},ensure_ascii=False,indent=2))

if __name__=='__main__': main()

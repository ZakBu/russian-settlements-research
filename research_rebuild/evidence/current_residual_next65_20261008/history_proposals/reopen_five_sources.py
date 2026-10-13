from pathlib import Path
import ast,json,re,unicodedata,sys,collections,time,resource
import pandas as pd,xlrd,duckdb
O=Path(__file__).parent;E=O.parent.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize
RULE=E/'current_cached_ownarticle_residual_expansion_20261008/review_articles.py';t=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
F=O/'source_bound_exact_county_history_counterpart_proposals.csv.gz';f=pd.read_csv(F,dtype=str,keep_default_na=False);groups=collections.defaultdict(list)
for z in f.to_dict('records'):
 q=json.loads(z['historic_native_observation_json']);p=Path('/workspace/settlements-raw')/q['source_file'];parts=q['source_record_id'].split(':');groups[p].append((z,parts[-2],int(parts[-1]),q))
verified=[];pins={};start=time.monotonic()
for p,targets in groups.items():
 pins[str(p)]=sha(p);b=xlrd.open_workbook(str(p),on_demand=True)
 for sn in set(s for z,s,r,q in targets):
  s=b.sheet_by_name(sn);wanted={r:(z,q) for z,ss,r,q in targets if ss==sn};co='';co_row=None;reg='';reg_row=None
  for i in range(max(wanted)):
   row=s.row_values(i);rn=i+1
   if len(row)>2 and str(row[2]).strip():reg=str(row[2]);reg_row=rn
   if len(row)>3 and str(row[3]).strip():co=str(row[3]);co_row=rn
   if rn not in wanted:continue
   z,q=wanted[rn];rawname=str(row[4]);ma=re.match(r'^\s*(с|д|п|н\.?п|пгт|рп)\.\s*(.+)$',rawname,re.I);n,typ=(ma.group(2),{'с':'село','д':'деревня','п':'поселок','нп':'населенный пункт','пгт':'пгт','рп':'рабочий поселок'}[ma.group(1).lower().replace('.','')]) if ma else splitname(rawname);assert namekey(n)==namekey(q['settlement_name']),(n,q);assert typekey(typ)==typekey(q['settlement_type']),(typ,q);assert county(co)==county(z['current_native_district']),(co,z['current_native_district']);assert float(row[5])==float(q['population']);assert regionkey(reg)==regionkey(q['region_norm']),(reg,q['region_norm'])
   z.update(historical_raw_workbook_literal_reopened=True,historical_raw_origin_file=str(p),historical_raw_origin_sha256=pins[str(p)],historical_raw_origin_locator=f'{sn}:row:{rn}:name_col5:population_col6',historical_raw_row_json=json.dumps(row,ensure_ascii=False),historical_county_header_literal=co,historical_county_header_row=co_row,historical_region_header_literal=reg,historical_region_header_row=reg_row,historical_county_header_row_json=json.dumps(s.row_values(co_row-1),ensure_ascii=False),historical_raw_rule='printed county col4 carried within printed region col3 to target physical NP col5; target name/type/population literal equals accepted native observation, county agrees current proper county; no code or finitepopulation identity shortcut',status='SOURCE_COUNTY_COUNTERPART_PROPOSAL_RAW_LITERAL_VERIFIED_NOT_ADMITTED');verified.append(z)
 b.release_resources();del b
pd.DataFrame(verified).to_csv(O/'raw_verified_five_history_counterpart_proposals.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'raw_verified_counterpart_proposals':len(verified),'historical_workbooks_opened_one_at_a_time':len(groups),'identity_edges_or_retrospective_points_admitted':0,'source_population_counts_unchanged':True,'seconds':time.monotonic()-start,'peak_RSS_MB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'input_pins':{str(F):sha(F),str(RULE):sha(RULE),str(O/'reopen_five_sources.py'):sha(O/'reopen_five_sources.py'),**pins}};(O/'five_raw_source_verification_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))

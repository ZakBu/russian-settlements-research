import re,json,sys,hashlib,gzip,collections
from pathlib import Path
import pandas as pd,pyarrow.parquet as pq,xlrd
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;E=ROOT/'research_rebuild/evidence';RAW=Path('/workspace/settlements-raw');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
PART=re.compile(r'\s*\(\s*часть\s*(\d+)\s*\)\s*$',re.I)
s=load(stage=20);cols=['source_record_id','source_sheet','source_row','source_name_raw','municipality_raw'];meta=pq.read_table(s.inputs[0],columns=cols).to_pandas();o=s.obs.merge(meta,on='source_record_id');o['base']=o.settlement_name.map(lambda n:normalize(PART.sub('',str(n))));o['d']=o.district_raw.map(county_key)
parts=o[o.census_year.eq(2002)&o.settlement_name.fillna('').str.contains(r'\(\s*часть\s*\d+\s*\)',case=False,regex=True)]
accepted=pd.read_csv(E/'complete_numbered_partition_batch_20261007/accepted_three_census_whole_place_series.csv');excluded={(normalize(r.place),r.region_norm) for r in accepted.itertuples()};excluded.add(('новая усмань','воронежская'))
controls=pd.read_csv(E/'numbered_partition_source_review_20261007/official_whole_row_candidates.csv');rows=[];candidates=[];members=[];source_checks=[];wiki=[]
# Cached code-bound dated claims are alternative controls only; annual date alone is not an explicit census proof.
qids={'Q4070628','Q4265612','Q4320950','Q19366027','Q2075571','Q4507738','Q4507734','Q18770358','Q18770359','Q18793519','Q18793521','Q18792027','Q18792028'}
popfile=RAW/'data/raw/wikimedia/wikidata_oktmo_population.tsv'
for lineno,line in enumerate(popfile.open(),1):
 if any('/'+q+'>' in line for q in qids) and '2002-' in line:
  wiki.append({'source_file':str(popfile),'source_row':lineno,'raw':line.strip(),'explicit_census_reference_asserted':False})
pd.DataFrame(wiki).drop_duplicates('raw').to_csv(OUT/'cached_2002_control_alternatives.csv',index=False)
for (base,region,typ,d),g in parts.groupby(['base','region_norm','settlement_type','d']):
 if (base,region) in excluded:continue
 ids=list(g.source_record_id);numbers=sorted(int(PART.search(n).group(1)) for n in g.settlement_name);total=int(g.population.sum());row={'base_name':base,'region':region,'type':typ,'printed_2002_county':d,'part_numbers':json.dumps(numbers),'part_count':len(g),'population_2002':total,'selected_member_ids':json.dumps(ids,ensure_ascii=False)};reasons=[]
 if numbers!=list(range(1,len(g)+1)) or len(g)<2:reasons.append('incomplete_numbered_set')
 ctl=controls[controls.base_name.map(normalize).eq(base)&controls.region.eq(region)&controls.official_population_candidate.eq(total)&controls.districts_in_selected_rows.map(county_key).eq(d)]
 if len(ctl)!=1:reasons.append('no_unique_actual_whole_2002_primary_total_equal_sum')
 endpoints={}
 for year in [2010,2021]:
  allg=o[o.census_year.eq(year)&o.base.eq(base)&o.region_norm.eq(region)&o.settlement_type.eq(typ)&o.is_additive_settlement_record.fillna(False)]
  # Full selected competitor set, including already-full3 rows; district null requires unique regional row.
  known=allg[allg.d.eq(d)];unknown=allg[allg.d.eq('')]
  choices=known if len(known) else unknown if len(allg)==1 else allg.iloc[:0]
  if len(choices)!=1 or (len(known) and len(unknown)):reasons.append(str(year)+'_whole_endpoint_not_uniquely_context_bound')
  else:endpoints[year]=choices.iloc[0]
 if 2021 in endpoints:
  cur=endpoints[2021];p=s.point_rows.get(cur.source_record_id)
  if p is None or cur.source_record_id in s.conflicting_point_targets or p.get('coordinate_source_record_id')!=cur.source_record_id:reasons.append('no_accepted_current_own_point')
 if reasons:row['status']='held';row['reasons']=';'.join(reasons);rows.append(row);continue
 # Read complete original worksheet roster for exactly this part-label base; compare full source set and original values.
 sourcefiles=set(g.source_file);sheets=set(g.source_sheet)
 if len(sourcefiles)!=1 or len(sheets)!=1:row.update(status='held',reasons='source_roster_not_single_sheet');rows.append(row);continue
 rel=next(iter(sourcefiles));path=RAW/rel;book=xlrd.open_workbook(str(path));sh=book.sheet_by_name(str(next(iter(sheets))));found=[]
 for i in range(sh.nrows):
  for v in sh.row_values(i):
   if isinstance(v,str) and PART.search(v) and normalize(PART.sub('',v)).endswith(base):found.append((i+1,v));break
 if sorted(n for n,v in found)!=sorted(int(n) for n in g.source_row):row.update(status='held',reasons='complete_original_source_part_roster_differs');rows.append(row);continue
 for r in g.itertuples():source_checks.append({'base_name':base,'source_record_id':r.source_record_id,'raw_workbook':str(path),'source_sha256':sha(path),'source_sheet':sh.name,'source_row':int(r.source_row),'raw_cells':' | '.join(str(v) for v in sh.row_values(int(r.source_row)-1) if v!=''),'selected_population':r.population})
 control=ctl.iloc[0];official=RAW/'data/raw/2002_official_tom1/1_TOM_01_04.xls';ob=xlrd.open_workbook(str(official));osh=ob.sheet_by_name('01-04');n=int(control.locator.split(':')[-1]);matches=[]
 for idx in [n-1,n]:
  vals=osh.row_values(idx);text=' | '.join(str(v) for v in vals if v!='')
  if base in normalize(text) and any(isinstance(v,(int,float)) and int(v)==total for v in vals):matches.append((idx+1,text))
 if len(matches)!=1:row.update(status='held',reasons='physical_primary_whole_control_not_exact');rows.append(row);continue
 row.update(status='candidate_complete_whole_place_projection',reasons='',native_2010_id=endpoints[2010].source_record_id,native_2021_id=endpoints[2021].source_record_id,population_2010=int(endpoints[2010].population),population_2021=int(endpoints[2021].population),point_ledger=p['point_ledger_path'],point_ledger_sha256=sha(Path(p['point_ledger_path'])),point_target=cur.source_record_id,latitude=p['latitude'],longitude=p['longitude'],official_whole_file=str(official),official_whole_sha256=sha(official),official_whole_excel_row=matches[0][0],official_whole_raw=matches[0][1],official_whole_count=total,official_district_context=control.nearest_context_raw,official_region_context=control.nearest_subject_raw,individual_part_coordinates_admitted=False,population_scope='complete_source_partition_whole_locality',population_values_modified=False)
 rows.append(row);candidates.append(row)
 for y,gyr in [(2002,g),(2010,o[o.source_record_id.eq(endpoints[2010].source_record_id)]),(2021,o[o.source_record_id.eq(endpoints[2021].source_record_id)])]:
  for r in gyr.itertuples():members.append({'place_base':base,'region':region,'year':y,'source_record_id':r.source_record_id,'population':r.population,'population_quality':r.population_value_quality,'candidate_only':True})
pd.DataFrame(rows).to_csv(OUT/'remaining_group_screen.csv',index=False);pd.DataFrame(candidates).to_csv(OUT/'candidate_complete_whole_place_series.csv',index=False);pd.DataFrame(members).to_csv(OUT/'candidate_exclusive_member_projection.csv',index=False);pd.DataFrame(source_checks).to_csv(OUT/'physical_source_checks.csv',index=False)
prior=set(pd.read_csv(E/'complete_numbered_partition_batch_20261007/accepted_exclusive_member_projection.csv').source_record_id)
# Credit by union of selected IDs, excluding ordinary-full3 and existing exclusive partition members.
new=[]
for r in members:
 sid=r['source_record_id'];covered=sid in prior or (sid in s.point_rows and s.years[s.uf.find(sid)]=={2002,2010,2021})
 if not covered:new.append(r)
net={str(y):int(sum(r['population'] for r in new if r['year']==y)) for y in [2002,2010,2021]}
receipt={'status':'candidate_only','stage':20,'remaining_numbered_groups':len(rows),'candidates':len(candidates),'net_new_selected_population_potential':net,'remaining_2002_population_upper_bound_excluding_prior_unions':int(sum(r['population_2002'] for r in rows)),'baseline_ordinary_full3':s.metrics(),'parts_never_matched_as_whole_rows':True,'individual_part_coordinates_admitted':False,'source_values_modified':False,'inputs':{str(p):sha(p) for p in s.inputs}|{str(popfile):sha(popfile)},'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}};(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs','outputs','baseline_ordinary_full3']},ensure_ascii=False,indent=2))

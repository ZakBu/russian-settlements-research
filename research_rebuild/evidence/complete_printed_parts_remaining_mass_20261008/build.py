import sys,json,re,hashlib
from pathlib import Path
import pandas as pd,xlrd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize
Z=Path(__file__).resolve().parent;E=Z.parent; RAW=Path('/workspace/settlements-raw'); s=load(51)
part=re.compile(r'\s*\(часть\s*(\d+)\)\s*$',re.I)
obs=s.obs.copy();obs['root']=obs.source_record_id.map(s.uf.find);obs['base']=obs.settlement_name.map(lambda n:part.sub('',n)); obs['row']=obs.source_record_id.map(lambda x:int(re.search(r'(\d+)$',x).group(1))); books={};manifest={}; witnesses=[]; anchors=[]; members=[];series=[];points=[];holds=[]
def county(x):return normalize(x).replace('муниципальный','').replace('район','').replace('городской округ','').strip()
def rawcheck(r):
 p=RAW/r.source_file;manifest[str(p)]=sha(p)
 if str(p) not in books:books[str(p)]=xlrd.open_workbook(str(p))
 sheet=r.source_record_id.rsplit(':',2)[1];sheet=books[str(p)].sheet_by_name(sheet); vals=[sheet.cell_value(r.row-1,c) for c in range(sheet.ncols)]; label=next((str(v) for v in vals if normalize(str(v)).endswith(normalize(r.settlement_name))),None)
 if label is None or not any(str(v).strip() in {str(int(r.population)),str(float(r.population))} for v in vals):raise ValueError('raw label/population mismatch')
 return dict(source_record_id=r.source_record_id,raw_label=label,raw_population=r.population,raw_source_path=str(p),raw_source_sha256=manifest[str(p)],raw_locator=f'{sheet.name}:{r.row}',population_value_quality=r.population_value_quality)
current_union=set()
for p in (E/'native2010_remaining_county_rule_mass_20261008').glob('baseline49_union_*.csv.gz'):
 f=pd.read_csv(p,keep_default_na=False);manifest[str(p)]=sha(p)
 if 'source_record_id' in f:current_union.update(f.source_record_id)
current_union.update(x for x in s.by_id.index if x in s.point_rows and s.years[s.uf.find(x)]=={2002,2010,2021})
for base,co in [('Архангельское','Аннинский'),('Никольское','Аннинский'),('Лозовое','Верхнемамонский')]:
 pid='remaining_printed_partition:'+hashlib.sha256((base+'|'+co).encode()).hexdigest()[:18]
 old=obs[(obs.census_year==2002)&obs.region_norm.eq('воронежская')&obs.base.eq(base)&obs.district_raw.map(county).eq(co.lower())]
 mid=obs[(obs.census_year==2010)&obs.region_norm.eq('воронежская')&obs.base.eq(base)&obs.settlement_name.str.contains('часть')]
 cur=obs[(obs.census_year==2021)&obs.region_norm.eq('воронежская')&obs.base.eq(base)&obs.district_raw.map(county).eq(co.lower())]
 try:
  if len(old)!=2 or len(mid)!=2 or len(cur)!=1:raise ValueError('not distinct closed2+2+whole1 set')
  if cur.iloc[0].source_record_id not in s.point_rows:raise ValueError('no whole own point')
  file=mid.iloc[0].source_file; eligible=obs[(obs.census_year==2010)&obs.source_file.eq(file)].sort_values('row')
  for r in mid.itertuples():
   sides=[]
   for sign in [-1,1]:
    neighbours=eligible[(eligible.row-r.row)*sign>0].copy();neighbours['distance']=(neighbours.row-r.row).abs();neighbours=neighbours.sort_values('distance')
    for a in neighbours.itertuples():
     g=obs[obs.root.eq(s.uf.find(a.source_record_id))]; o=g[g.census_year.eq(2002)]; c=g[g.census_year.eq(2021)]
     if len(o)==len(c)==1 and county(o.iloc[0].district_raw)==county(c.iloc[0].district_raw) and county(o.iloc[0].district_raw):
      sides.append(dict(target_source_record_id=r.source_record_id,anchor2010_source_record_id=a.source_record_id,offset=a.row-r.row,anchor2002_source_record_id=o.iloc[0].source_record_id,old_county=o.iloc[0].district_raw,anchor2021_source_record_id=c.iloc[0].source_record_id,current_county=c.iloc[0].district_raw,county_key=county(o.iloc[0].district_raw)));break
   anchors.extend(sides)
   if len(sides)!=2 or any(x['county_key']!=co.lower() for x in sides):raise ValueError('two-sided historical county anchor unresolved')
  point=s.point_rows[cur.iloc[0].source_record_id];points.append(dict(place_id=pid,whole_native2021_source_record_id=cur.iloc[0].source_record_id,whole_native_oktmo=cur.iloc[0].oktmo,**point))
  for year,g in [(2002,old),(2010,mid),(2021,cur)]:
   if year!=2021:
    nums=sorted(int(part.search(n).group(1)) for n in g.settlement_name)
    if nums!=[1,2]:raise ValueError('incompletepartset')
    source=RAW/g.iloc[0].source_file
    if str(source) not in books:books[str(source)]=xlrd.open_workbook(str(source))
    found=set()
    for sheet in books[str(source)].sheets():
     for row in range(sheet.nrows):
      for v in sheet.row_values(row):
       if isinstance(v,str) and part.search(v) and normalize(part.sub('',v)).endswith(normalize(base)):found.add(int(part.search(v).group(1)))
    if found!={1,2}:raise ValueError('source roster has additionalparts')
   for r in g.itertuples():
    witness=rawcheck(r) if year!=2021 else dict(source_record_id=r.source_record_id,raw_label=r.settlement_name,raw_population=r.population,raw_source_path=r.source_path,raw_source_sha256=r.source_sha256,raw_locator=r.source_locator,population_value_quality=r.population_value_quality)
    witnesses.append(witness);members.append(dict(place_id=pid,source_record_id=r.source_record_id,year=year,population=int(r.population),already_in_baseline51_native_union=r.source_record_id in current_union,coordinate_scope='whole_locality_projection',ordinary_same_place_graph_mutated=False))
   series.append(dict(place_id=pid,place=base,region_norm='воронежская',historical_county=co,year=year,population=int(g.population.sum()),member_source_record_ids_json=json.dumps(g.source_record_id.tolist(),ensure_ascii=False),member_population_quality_json=json.dumps(g.population_value_quality.tolist()),population_is_derived_sum=year!=2021,latitude=point['latitude'],longitude=point['longitude'],projection_status='candidate_complete_publisher_partition',native2002_official_whole_control_asserted=False,source_population_modified=False,population_boundary_comparability_asserted=False,individual_part_coordinates_admitted=False))
 except ValueError as e:holds.append(dict(place=base,reason=str(e)))
for name,rows in [('candidate_whole_place_three_census_series',series),('candidate_native_constituents',members),('candidate_own_whole_points',points),('actual_raw_source_witnesses',witnesses),('two_sided_historical_county_anchors',anchors),('candidate_holds',holds)]:pd.DataFrame(rows).to_csv(Z/(name+'.csv'),index=False)
gain={str(y):{'new_rows':sum(r['year']==y and not r['already_in_baseline51_native_union'] for r in members),'new_population':sum(r['population'] for r in members if r['year']==y and not r['already_in_baseline51_native_union'])} for y in [2002,2010,2021]}
receipt=dict(status='candidate_only_complete_printed_partition_batch',places=len(series)//3,conditional_source_ID_union_exclusive_gain=gain,holds=holds,baseline_working_stage=51,baseline_ordinary_metrics=s.metrics(),ordinary_graph_changed=False,accepted_points_added=False,official2002_whole_controls_not_asserted=True,source_hash_manifest=manifest)
(Z/'candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['places','conditional_source_ID_union_exclusive_gain','holds']},ensure_ascii=False))

from pathlib import Path
import pandas as pd, xlrd, re, json, hashlib, collections
E=Path(__file__).resolve().parent
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
C=Path('/workspace/settlements-work/continuation_20261004/independent_review/official2002_2010_external_controls/official_region_vs_selected_2002_2010.csv')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
s=pd.read_parquet(S);s=s[s.census_year==2002].copy()
q=pd.DataFrame(json.loads((E/'omitted_literal_np_review_rows.json').read_text()))
regs=['алтай','башкортостан','брянская','бурятия','владимирская','воронежская','ивановская','кемеровская','кировская','костромская','московская','новосибирская','омская','пензенская','самарская','саратовская','тверская','тульская','ульяновская','челябинская']
z=pd.concat([q[q.region.isin(regs)&~q.label.str.contains('сомон',case=False)],q[(q.region=='приморский')&(q.source_row!=756)],q[q.region=='астраханская']])
assert len(z)==128 and z.population.sum()==13027
inventories={p: set(pd.read_parquet(p,columns=['source_record_id']).source_record_id) for p in ['/workspace/settlements-baseline/output/source_observations.parquet','/workspace/settlements-baseline/output/excluded_source_observations.parquet','/workspace/settlements-baseline/evidence/replayed_observations.parquet']}
def norm(v):return re.sub(r'[^\w]+',' ',v.casefold().replace('ё','е')).strip()
rows=[];witnesses=[];pins={};local_proofs=[]
for (f,sh),g in z.groupby(['source_file','source_sheet']):
 p=Path('/workspace/settlements-raw')/f;pins[str(p)]=sha(p);x=xlrd.open_workbook(str(p)).sheet_by_name(sh);col=int(g.label_col.iloc[0]);sg=s[(s.source_file==f)&(s.source_sheet==sh)].copy();sel=set(sg.source_record_id)
 parent_stack=[];contexts={};controls=[];rawrows=[]
 for i in range(x.nrows):
  v=x.cell_value(i,col)
  if not isinstance(v,str)or not v.strip():continue
  ind=len(v)-len(v.lstrip()); label=v.strip()
  while parent_stack and parent_stack[-1][0]>=ind:parent_stack.pop()
  contexts[i+1]=list(parent_stack)
  aggregate=bool(re.search(r'сельсовет|сельский округ|волость$|\sСО$|сомон|район|сельское население|населенные пункты|населённые пункты|подч|администрац',label,re.I))
  try: count=float(x.cell_value(i,col+1));count=int(count) if count.is_integer() else None
  except:count=None
  rawrows.append((i+1,label,count,ind,aggregate))
  if aggregate:
   parent_stack.append((ind,i+1,label,count));controls.append((i+1,label,count,ind))
 for _,r in g.iterrows():
  ri=int(r.source_row);literal=x.cell_value(ri-1,col);count=int(float(x.cell_value(ri-1,col+1)));assert literal==r.label and count==r.population
  sid=f'2002:{Path(f).name}:{sh}:{ri}';assert sid not in set(s.source_record_id)
  ctx=contexts[ri];county=[a for a in ctx if re.search(r'район',a[2],re.I)];mun=[a for a in ctx if re.search(r'сельсовет|сельский округ|волость$|\sСО$|сомон',a[2],re.I)]
  countyraw=county[-1][2] if county else '';munraw=mun[-1][2] if mun else ''
  if f.endswith('Tver_obl.xls'):
   countyraw=str(x.cell_value(ri-1,1));munraw=str(x.cell_value(ri-1,2)) or munraw
  label=literal.strip();m=re.match(r'^(железнодорожныйОстановочный Пункт|железнодорожныйПутевой Пост|железнодорожныйБлокпост|железнодорожнаябудка|железнодорожная Казарма|железнодорожный дом|жележнодорожная станция|железнодорожная платформа|ж/д ст\.|посёлок, остановочный пункт|остановочный пункт|остановочная платформа|центральная усадьба|лесоучасток|База отдыха|Дома|Турбаза|турбаза|блок-пост|Блок-Пост|Казарма|казарма|населённый пункт|посёлок|хутор|погост|подстанция|маяк|слободка|зимовка|аул|кп)',label,re.I)
  typ=m.group(1) if m else '';name=label[len(typ):].strip() if typ else label
  other=[rr for rr in rawrows if rr[1]==label and rr[0]!=ri and not rr[4]]
  competitors=sg[sg.source_name_raw.map(lambda v:norm(str(v)))==norm(label)]
  nearest_before=sg[sg.source_row<ri].sort_values('source_row').tail(1);nearest_after=sg[sg.source_row>ri].sort_values('source_row').head(1)
  rec=dict(source_record_id=sid,census_year=2002,source_file=f,source_sheet=sh,source_row=ri,source_name_raw=literal,settlement_name=name,settlement_type=typ,region_raw=r.region,district_raw=countyraw,municipality_raw=munraw,population=count,source_path=str(p),source_sha256=pins[str(p)],source_locator=f'Excel {sh}, row {ri}, label column {col+1}, count column {col+2}',population_value_quality='direct_published_census_value',entity_grain_status='explicit_named_rural_NP_leaf_in_published_census_roster',candidate_status='ready_source_observation_no_temporal_link_or_point_assertion',record_inventory_status='existing_parsed_observation_excluded_from_selected' if sid in inventories[next(iter(inventories))] else 'new_observation_missing_from_parsed_inventory',original_parsed_type='пгт' if sid.endswith('Novosib.xls:Sheet1:1909') else '',full_region_same_literal_selected_count=len(competitors),full_raw_sheet_same_literal_other_count=len(other),full_raw_other_rows=json.dumps([rr[0]for rr in other]),latitude=None,longitude=None,coordinate_admission='none',identity_admission='not_evaluated')
  rec['census_reference_date']='2002-10-09'
  same_name=s[(s.region_raw==r.region)&(s.settlement_name.map(lambda v:norm(str(v)))==norm(name))]
  rec['full_region_same_name_selected_count']=len(same_name)
  rec['full_region_same_name_selected_IDs']=json.dumps(same_name.source_record_id.tolist(),ensure_ascii=False)
  rows.append(rec);witnesses.append(dict(source_record_id=sid,raw_cells=x.row_values(ri-1),ancestor_controls=ctx,selected_literal_competitors=competitors.source_record_id.tolist(),nearest_before=nearest_before[['source_record_id','source_name_raw','population']].to_dict('records'),nearest_after=nearest_after[['source_record_id','source_name_raw','population']].to_dict('records')))
 # Independent numeric leaf/control proof, record deepest municipal controls only.
 for ri,label,count,ind in controls:
  if count is None or not re.search(r'сельсовет|сельский округ|волость$|\sСО$|сомон',label,re.I):continue
  end=next((rr[0] for rr in rawrows if rr[0]>ri and rr[3]<=ind),x.nrows+1)
  selectedsum=sg[(sg.source_row>ri)&(sg.source_row<end)].population.sum();newsum=g[(g.source_row>ri)&(g.source_row<end)].population.sum()
  if newsum or count!=selectedsum:
   local_proofs.append(dict(source_file=f,source_sheet=sh,control_row=ri,control_label=label,control_population=count,end_row_exclusive=end,selected_leaf_population=int(selectedsum),new_literal_NP_population=int(newsum),control_minus_all_leaf=int(count-selectedsum-newsum)))
out=pd.DataFrame(rows);assert out.source_record_id.is_unique
out.to_csv(E/'explicit_missing_2002_np_observation_candidates.csv.gz',index=False)
(E/'literal_context_and_competitors.json').write_text(json.dumps(witnesses,ensure_ascii=False,indent=2))
pd.DataFrame(local_proofs).to_csv(E/'local_control_leaf_readback.csv',index=False)
d=pd.read_csv(C);d=d[d.census_year==2002].copy();delta=out.groupby('region_raw').population.sum();d['new_literal_np_population']=d.selected_region_raw.map(delta).fillna(0).astype(int);d['remaining_control_minus_source_leaf']=d.official_minus_selected_base_scope-d.new_literal_np_population;d.to_csv(E/'regional_control_before_after_source_candidates.csv',index=False)
receipt=dict(status='candidate_packet_not_applied',selected_2002_population=int(s.population.sum()),official_2002_control=145166731,original_gap=11726,official_urban_control_and_selected_urban_sum=106429049,official_rural_control=38737682,selected_rural_sum=38725956,positive_regional_deficits=14251,negative_regional_differences=-2525,explicit_np_candidates=len(out),candidate_population_sum=int(out.population.sum()),new_to_parsed_inventory=int(out.record_inventory_status.eq('new_observation_missing_from_parsed_inventory').sum()),existing_parsed_excluded_from_selected=int(out.record_inventory_status.ne('new_observation_missing_from_parsed_inventory').sum()),published_zero_count_rows=int(out.population.eq(0).sum()),prospective_selected_if_all_source_candidates_added=145168032,prospective_national_gap=-1301,regionally_closed_positive_deficit_regions=20,full_selected_literal_competitor_count=int(out.full_region_same_literal_selected_count.sum()),source_pins=pins,input_pins={str(S):sha(S),str(C):sha(C),**{p:sha(p)for p in inventories}},limitations=['All candidates are exact raw census-roster locality rows, not population allocation; temporal links and own points are not asserted.','Remaining positive controls: Arkhangelsk829, Leningrad9, Pskov338, Smolensk9, Yaroslavl93; total1278.','Tver omitted source locality rows total3171 against deficit3163; deepest municipal controls show source excesses2 and6.','Astrakhan two omitted locality rows46 are legitimate source omissions despite existing regional excess498; after addition source excess544.','No exclusions from negative differences are admitted; source hierarchy inconsistencies need distinct source evidence.','100% numerical closure would be misleading while signed discrepancies offset. Official total is partitioned entirely into urban and rural population; these cached controls do not establish a separate nonsettlement category.'])
official=Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')
ox=xlrd.open_workbook(str(official)).sheet_by_index(0)
assert [int(ox.cell_value(i,1))for i in [3,4,5]]==[145166731,106429049,38737682]
receipt['input_pins'][str(official)]=sha(official)
receipt['national_official_raw_row_readback']=[dict(source_row=i+1,raw_cells=ox.row_values(i))for i in [3,4,5]]
receipt['full_region_name_competitors']=out[out.full_region_same_name_selected_count>0][['source_record_id','settlement_name','full_region_same_name_selected_IDs']].to_dict('records')
receipt['output_pins']={str(p):sha(p)for p in E.iterdir() if p.is_file() and p.name not in ['receipt.json']}
(E/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items()if k not in ['source_pins','input_pins','output_pins']},ensure_ascii=False,indent=2))

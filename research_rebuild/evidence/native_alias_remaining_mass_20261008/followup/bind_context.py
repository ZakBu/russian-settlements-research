import sys,json,pandas as pd,duckdb,xlrd
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(27);s.add_deltas([O.parent/'accepted_identity_edge_delta.csv'],[O.parent/'accepted_point_use_delta.csv']);d=s.obs;c=duckdb.connect();meta=c.execute("select source_record_id,source_sheet,source_row from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf().set_index('source_record_id');d['sr']=d.source_record_id.map(meta.source_row);d['sheet']=d.source_record_id.map(meta.source_sheet);roots=d.source_record_id.map(s.uf.find);oldmap={s.uf.find(a.source_record_id):a for _,a in d[d.census_year.eq(2002)].iterrows()};newmap={s.uf.find(a.source_record_id):a for _,a in d[d.census_year.eq(2021)].iterrows()};rows=[];anchors=[];books={}
cases=[('красногвардейский','свердловская',4019,4825,3754),('восточный','свердловская',4648,5729,4316),('северка','свердловская',3507,3380,2917),('октябрьский','тульская',3282,3358,3159),('приупский','тульская',2132,3421,1890),('рассвет','тульская',4163,4002,3760),('ревякино','тульская',2970,3313,3423),('октябрьский','ульяновская',5679,6738,5035),('белый ключ','ульяновская',2330,2608,2208),('карлинское','ульяновская',2503,2607,2236)]
for name,region,p10,p02,p21 in cases:
 aa=d[d.census_year.eq(2010)&d.region_norm.eq(region)&d.name_norm.eq(name)&d.population.eq(p10)];bb=d[d.census_year.eq(2002)&d.region_norm.eq(region)&d.name_norm.eq(name)&d.population.eq(p02)];zz=d[d.census_year.eq(2021)&d.region_norm.eq(region)&d.name_norm.eq(name)&d.population.eq(p21)];assert len(aa)==len(bb)==len(zz)==1;a,b,z=aa.iloc[0],bb.iloc[0],zz.iloc[0];rn=int(meta.loc[a.source_record_id].source_row);an=[]
 peers=d[d.census_year.eq(2010)&d.source_file.eq(a.source_file)&d.sr.between(rn-80,rn+80)&d['sheet'].eq(meta.loc[a.source_record_id].source_sheet)]
 for _,peer in peers.iterrows():
  if peer.source_record_id==a.source_record_id:continue
  root=s.uf.find(peer.source_record_id);old=oldmap.get(root);new=newmap.get(root)
  if old is None or new is None or s.years[root]!={2002,2010,2021}:continue
  an.append(dict(target_source_record_id=a.source_record_id,anchor_source_record_id=peer.source_record_id,anchor_source_row=int(peer.sr),anchor_name=peer.settlement_name,anchor_2002_source_record_id=old.source_record_id,anchor_2002_county=old.district_raw,anchor_current_county=new.district_raw,current_county_key=county_key(new.district_raw),old_county_key=county_key(old.district_raw)))
 low=sorted([t for t in an if t['anchor_source_row']<rn],key=lambda t:t['anchor_source_row'],reverse=True);up=sorted([t for t in an if t['anchor_source_row']>rn],key=lambda t:t['anchor_source_row']);pair=None
 for l in low:
  for u in up:
   if l['current_county_key']==u['current_county_key'] and l['current_county_key']==county_key(z.district_raw) and l['anchor_name']!=u['anchor_name']:pair=[l,u];break
  if pair:break
 if pair:anchors.extend(pair)
 raw=[]
 for x in [a,b]:
  if not x.source_file.endswith('.xls'):continue
  bk=books.setdefault(x.source_file,xlrd.open_workbook('/workspace/settlements-raw/'+x.source_file));mm=meta.loc[x.source_record_id];sh=bk.sheet_by_name(str(mm.source_sheet)) if str(mm.source_sheet) in bk.sheet_names() else bk.sheet_by_index(int(mm.source_sheet));rr=int(mm.source_row);vals=sh.row_values(rr-1);raw.append({'source_record_id':x.source_record_id,'source_file':x.source_file,'source_sheet':mm.source_sheet,'source_row':rr,'literal_row':vals[:10],'previous_10_rows':[{'row':i+1,'values':sh.row_values(i)[:8]} for i in range(max(0,rr-11),rr)]})
 rows.append(dict(case=name+' '+region,source2010=a.source_record_id,source2002=b.source_record_id,source2021=z.source_record_id,current_code=z.okato,current_county=z.district_raw,current_point=json.dumps(s.point_rows.get(z.source_record_id,{}),ensure_ascii=False),old_point=json.dumps(s.point_rows.get(b.source_record_id,{}),ensure_ascii=False),two_sided_source_county=pair[0]['anchor_2002_county'] if pair else '',two_sided_current_county=pair[0]['anchor_current_county'] if pair else '',two_sided_anchors=json.dumps(pair,ensure_ascii=False),raw_context=json.dumps(raw,ensure_ascii=False)))
pd.DataFrame(rows).to_csv(O/'bounded_context_bindings.csv',index=False);pd.DataFrame(anchors).to_csv(O/'independent_two_sided_county_anchors.csv',index=False);print(pd.DataFrame(rows)[['case','current_code','current_county','two_sided_source_county','two_sided_current_county']].to_string(index=False))

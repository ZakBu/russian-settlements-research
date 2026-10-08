import sys,json,re
from pathlib import Path
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(26);c=duckdb.connect();meta=c.execute('select source_record_id,source_sheet,source_row from read_parquet(?)',['/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet']).fetchdf().set_index('source_record_id');oldcounty={s.uf.find(x.source_record_id):county_key(x.district_raw) for x in s.obs[s.obs.census_year.eq(2002)].itertuples() if county_key(x.district_raw)};peers=s.obs[s.obs.census_year.eq(2010)&s.obs.region_norm.eq('московская')].copy();peers['old2002county']=peers.source_record_id.map(lambda x:oldcounty.get(s.uf.find(x),''));peers['sheet']=peers.source_record_id.map(meta.source_sheet);peers['row']=peers.source_record_id.map(meta.source_row);options=pd.read_csv(O/'moscow_five_joined_future2010_native_options.csv');proof=[];books={}
for r in options.to_dict('records'):
 sid=r['candidate_2010_source_record_id'];a=s.by_id.loc[sid];m=meta.loc[sid];rn=int(m.source_row);neighbors=peers[peers.source_file.eq(a.source_file)&peers.sheet.eq(m.source_sheet)&peers.old2002county.ne('')&peers.row.sub(rn).abs().le(20)&peers.row.ne(rn)];lo=neighbors[neighbors.row.lt(rn)].sort_values('row',ascending=False);hi=neighbors[neighbors.row.gt(rn)].sort_values('row');pair=None
 for l in lo.itertuples():
  for u in hi.itertuples():
   if l.old2002county==u.old2002county and normalize(l.settlement_name)!=normalize(u.settlement_name):pair=(l,u);break
  if pair:break
 p=Path('/workspace/settlements-raw')/a.source_file;bk=books.setdefault(str(p),xlrd.open_workbook(p));sh=bk.sheet_by_name(str(m.source_sheet));vals=sh.row_values(rn-1);literal=[str(v) for v in vals if isinstance(v,str) and normalize(a.settlement_name) in normalize(v)];assert literal
 anchors=[]
 for peer in pair or []:
  vv=sh.row_values(int(peer.row)-1);lab=next(str(v) for v in vv if isinstance(v,str) and normalize(peer.settlement_name) in normalize(v));anchors.append({'source_record_id':peer.source_record_id,'row_1based':int(peer.row),'literal_raw_label':lab,'independently_accepted_historical_county':peer.old2002county})
 r.update(own_2010_type=a.settlement_type,physical_source_file=str(p),physical_source_sha256=sha(p),source_sheet=str(m.source_sheet),source_row_1based=rn,literal_own_raw_label=literal[0],raw_row_json=json.dumps(vals,ensure_ascii=False),two_sided_native_historical_county=pair[0].old2002county if pair else '',native_two_sided_anchors_json=json.dumps(anchors,ensure_ascii=False));proof.append(r)
pd.DataFrame(proof).to_csv(O/'moscow_five_2010_actual_native_context_review.csv',index=False);print(pd.DataFrame(proof)[['name','population_2010','own_2010_type','two_sided_native_historical_county','source_row_1based']].to_string(index=False))

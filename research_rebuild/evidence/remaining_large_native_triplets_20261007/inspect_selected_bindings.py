import sys,json,re
from pathlib import Path
from collections import defaultdict
import pandas as pd,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;s=load(18);f=pd.read_csv(O/'top_pointed_residual_component_review.csv',dtype=str,keep_default_na=False);c=pd.read_csv(O/'native_old_label_candidates.csv',dtype=str,keep_default_na=False);c=c[pd.to_numeric(c.population)>2000];c=pd.concat([c,pd.read_csv(O/'renamed_city_native_rows.csv',dtype=str,keep_default_na=False).assign(target_name=lambda d:d.settlement_name.map({'Беднодемьяновск':'Спасск','Красногвардейское':'Бирюч'}))],ignore_index=True);books={};out=[]
for a in c.to_dict('records'):
 sid=a['source_record_id'];r=s.by_id.loc[sid];targets=f[(f.name==a['target_name'])&(f.region==r.region_norm)&(f['years']=='2010|2021')]
 if len(targets)!=1:continue
 t=targets.iloc[0];bid=t.source_record_id
 if s.uf.find(sid)==s.uf.find(bid) or s.years[s.uf.find(sid)]&s.years[s.uf.find(bid)]:continue
 if s.years[s.uf.find(sid)]!={2002}:continue
 asset=Path('/workspace/settlements-raw')/r.source_file
 rownum=int(sid.rsplit(':',1)[1]);sheetname=sid.rsplit(':',2)[1]
 if not asset.is_file():continue
 if asset not in books:books[asset]=xlrd.open_workbook(str(asset),on_demand=True)
 book=books[asset]
 try:sh=book.sheet_by_name(sheetname)
 except:sh=book.sheet_by_index(int(sheetname))
 raw=' | '.join(str(v) for v in sh.row_values(rownum-1) if v!='');county='';headers=[]
 for i in range(rownum-2,max(-1,rownum-700),-1):
  vals=sh.row_values(i);txt=' | '.join(str(v) for v in vals if isinstance(v,str) and v.strip())
  if not txt:continue
  if len(headers)<8:headers.append([i+1,txt])
  if re.search(r'\bрайон\b',normalize(txt)) and not re.search(r'подчиненн|сельсовет|сс|городское население|сельское население',normalize(txt)):
   county=txt;countyrow=i+1;break
  if 'область' in normalize(txt) or 'край' in normalize(txt):break
 p=s.point_rows.get(sid,{});p2=s.point_rows[bid];dist=distance_km((p['latitude'],p['longitude']),(p2['latitude'],p2['longitude'])) if p else None
 out.append({'old_source_record_id':sid,'target_source_record_id':bid,'old_name':r.settlement_name,'current_name':t['name'],'region':r.region_norm,'old_type':r.settlement_type,'target_type':t.type,'old_population':r.population,'target_population':t.population,'old_printed_county_as_selected':str(r.district_raw),'source_county_header':county,'source_county_header_row':countyrow if county else None,'target_county':t.peer_counties,'old_raw_row':raw,'nearby_source_headers':json.dumps(headers,ensure_ascii=False),'source_file':str(asset),'source_sha256':sha(asset),'source_row_1based':rownum,'source_sheet':sheetname,'old_point_available':bool(p),'distance_km':dist,'old_point_json':json.dumps(p,ensure_ascii=False,default=str),'target_point_json':json.dumps(p2,ensure_ascii=False,default=str)})
out=pd.DataFrame(out);out.to_csv(O/'bounded_native_source_binding_review.csv',index=False);print(out[['old_name','current_name','region','old_population','source_county_header','target_county','old_point_available','distance_km']].to_string(index=False))

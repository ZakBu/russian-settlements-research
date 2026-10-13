from pathlib import Path
O=Path(__file__).parent;p=O/'native_individual_batch.py';s=p.read_text();s=s.replace("headers=[];books={};existing_ids=set()","headers=[];books={};competitors=[];existing_ids=set()")
pos=s.index('for county,city,a,b,c,d,municip in config:')
insert='''# Independently alreadyaccepted individual identity components provide sourcecounty anchors, before any point filter.
old_county={};last=''
for n in range(S02.nrows):
 label=str(S02.cell_value(n,1));match=re.match(r'^\\s{3}(.+?район)\\s*-\\s*все сельское население',label,re.I)
 if match:last=match.group(1).strip()
 old_county[n+1]=last
root_old={}
for root,frame in o[o.census_year.eq(2002)&o.source_file.eq('data/raw/2002/'+P02.name)].groupby(o[o.census_year.eq(2002)&o.source_file.eq('data/raw/2002/'+P02.name)].source_record_id.map(s.uf.find)):
 if len(frame)==1:root_old[root]=frame.iloc[0]
anchors={};direct={}
for z in regional[regional.census_year.eq(2010)&regional.source_file.eq('data/raw/2010/'+P10.name)].itertuples():
 old=root_old.get(z.root)
 if old is None:continue
 countyname=old_county.get(int(old.source_row),'')
 if not countyname:continue
 direct[z.source_record_id]={'county':countyname,'basis':'existingacceptedindividual2002_2010sameplace_component_and_original2002printedcounty','old_id':old.source_record_id,'old_source_row':int(old.source_row),'anchor2010_id':z.source_record_id,'anchor2010_row':int(z.source_row)}
 anchors[int(z.source_row)]=direct[z.source_record_id]
anchor_rows=sorted(anchors)
import bisect
bindings_county={}
for z in regional[regional.census_year.eq(2010)].itertuples():
 if z.source_record_id in direct:bindings_county[z.source_record_id]=direct[z.source_record_id];continue
 if z.source_file!='data/raw/2010/'+P10.name:continue
 row=int(z.source_row);ix=bisect.bisect_left(anchor_rows,row)
 if ix==0 or ix==len(anchor_rows):continue
 left,right=anchor_rows[ix-1],anchor_rows[ix]
 if row-left>5 or right-row>5 or anchors[left]['county']!=anchors[right]['county']:continue
 bindings_county[z.source_record_id]={'county':anchors[left]['county'],'basis':'two_nearest_independent_alreadyaccepted_native2010_sourcecounty_anchors_before_anypointfilter','left':anchors[left],'right':anchors[right]}
'''
s=s[:pos]+insert+s[pos:]
a=s.index("  key=(z.name_norm,z.type_norm);");b=s.index("  rawcur=raw.iloc[int(cur.source_row)-1]",a)
s=s[:a]+'''  key=(z.name_norm,z.type_norm);ns={year:int(counts.get((year,*key),0)) for year in [2002,2010,2021]}
  pools={year:by.get((year,*key),regional.iloc[:0]) for year in [2002,2010,2021]};ownold=pools[2002][pools[2002].source_file.eq('data/raw/2002/'+P02.name)&pools[2002].source_row.between(a,b)]
  current_pool=pools[2021];current_county=current_pool[[raw.iloc[int(n)-1].mun_upper==municip for n in current_pool.source_row]] if len(current_pool) else current_pool
  unknown10=[r.source_record_id for r in pools[2010].itertuples() if r.source_record_id not in bindings_county]
  own10=pools[2010][pools[2010].source_record_id.map(lambda sid:bindings_county.get(sid,{}).get('county')==county)]
  for yr,pool in pools.items():
   for cr in pool.itertuples():competitors.append({'case':'individual_sourcecounty_unique_'+z.source_record_id,'target_county':county,'year':yr,'source_record_id':cr.source_record_id,'name_norm':cr.name_norm,'type_norm':cr.type_norm,'county_context_proof_json':json.dumps(bindings_county.get(cr.source_record_id,{}),ensure_ascii=False) if yr==2010 else json.dumps({'printed2002county':old_county.get(int(cr.source_row),'')} if yr==2002 and cr.source_file=='data/raw/2002/'+P02.name else {'current_literal_municipality':raw.iloc[int(cr.source_row)-1].mun_upper} if yr==2021 else {},ensure_ascii=False),'point_filter_applied':False})
  if unknown10 or len(ownold)!=1 or len(own10)!=1 or len(current_county)!=1 or own10.iloc[0].source_record_id!=z.source_record_id:
   held.append({'county':county,'source_record_id':z.source_record_id,'reason':'countycontext competitor missing/ambiguous beforepointfilter','counts_json':json.dumps(ns),'context_counts_json':json.dumps({'2002':len(ownold),'2010':len(own10),'2021':len(current_county),'unresolved2010_competitor_IDs':unknown10})});continue
  rr={2002:ownold.iloc[0],2010:own10.iloc[0],2021:current_county.iloc[0]};old=rr[2002];cur=rr[2021]
''' +s[b:]
s=s.replace("'admission_rule':'All-regional normalized literal own name/type unique in each year before pointfilter; exact printed2002 county, original2010 source-order support, current ownNP municipality; existing ownpoint only'","'admission_rule':'All same-region typed name competitors enumerated beforepointfilter; every2010homonym sourcecounty bound independently by accepted2002component or two adjacent native anchors; unique own name/type within exact2002county/2010sourcecounty/currentownmunicip; existing individual ownpoint only'")
s=s.replace("'all_regional_competitor_counts_json':json.dumps(ns),","'all_regional_competitor_counts_json':json.dumps(ns),'target2010_county_binding_proof_json':json.dumps(bindings_county[z.source_record_id],ensure_ascii=False),")
s=s.replace("'sourcecounty_headers_and_urban_anchors',headers)","'sourcecounty_headers_and_urban_anchors',headers),('all_regional_homonym_sourcecounty_competitors',competitors)")
s=s.replace("'all_regional_competitors_enumerated_before_point_filter':True,","'all_regional_competitors_enumerated_before_point_filter':True,'all2010_homonym_sourcecounty_bindings_independently_resolved_beforepointfilter':True,")
(O/'native_individual_context_batch.py').write_text(s)

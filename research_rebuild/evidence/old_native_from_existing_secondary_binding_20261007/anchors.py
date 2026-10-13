exec(open('/workspace/settlements-work/old_native_from_existing_secondary_binding_20261007/reopen.py').read().split('for r in D.to_dict')[0])
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(21);current=s.obs[s.obs.census_year.eq(2021)];rootcurrent={s.uf.find(r.source_record_id):r for r in current.itertuples()};anchors={}
for r in s.obs[s.obs.census_year.eq(2010)].itertuples():
 parts=r.source_record_id.split(':')
 if len(parts)!=4 or not parts[0]=='2010' or not parts[-1].isdigit():continue
 c=rootcurrent.get(s.uf.find(r.source_record_id))
 if c is None or not ck(c.district_raw):continue
 key=(parts[1],parts[2]);anchors.setdefault(key,[]).append((int(parts[3]),r.source_record_id,ck(c.district_raw),c.source_record_id,c.settlement_name))
for key in anchors:anchors[key].sort()
witness=[]
for r in D.to_dict('records'):
 if r.get('hold_reason')!='historical_county_context_not_exact' or not str(r.get('old_source_record_id','')).startswith('2010:'):continue
 parts=r['old_source_record_id'].split(':')
 if len(parts)!=4 or not parts[-1].isdigit():continue
 n=int(parts[-1]);key=(parts[1],parts[2]);aa=anchors.get(key,[]);above=[a for a in aa if a[0]<n];below=[a for a in aa if a[0]>n]
 if not above or not below:continue
 a,b=above[-1],below[0];expected=ck(r['current_county'])
 if a[2]!=expected or b[2]!=expected or n-a[0]>25 or b[0]-n>25:continue
 c=s.by_id.loc[r['current_source_record_id']];old=s.by_id.loc[r['old_source_record_id']];root=s.uf.find(c.source_record_id)
 if s.years[s.uf.find(old.source_record_id)]&s.years[root]:continue
 dist=None
 if old.source_record_id in s.point_rows:
  p=s.point_rows[old.source_record_id];q=s.point_rows[c.source_record_id];la1,lo1,la2,lo2=map(math.radians,[p['latitude'],p['longitude'],q['latitude'],q['longitude']]);dist=6371.0088*2*math.asin(min(1,math.sqrt(math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2)))
  if dist>5:continue
 p=pathlib.Path('/workspace/settlements-raw')/str(r['old_source_file'])
 if str(p) not in books:books[str(p)]=xlrd.open_workbook(str(p));hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 sh=books[str(p)].sheet_by_name(parts[2]);raw=sh.row_values(n-1)
 if not any(norm(c.settlement_name) in norm(z) for z in raw) or not any(str(z).replace('.0','')==str(int(old.population)) for z in raw):continue
 compact=lambda rr:[z for z in rr if z!=''][:14]
 r.update(raw_old_source_file=str(p),raw_old_source_sha256=hashes[str(p)],raw_old_source_locator='sheet='+sh.name+';row_1based='+str(n),raw_old_row_json=json.dumps(compact(raw),ensure_ascii=False),anchor_above_source_record_id=a[1],anchor_above_current_source_record_id=a[3],anchor_above_current_name=a[4],anchor_above_raw_row_json=json.dumps(compact(sh.row_values(a[0]-1)),ensure_ascii=False),anchor_below_source_record_id=b[1],anchor_below_current_source_record_id=b[3],anchor_below_current_name=b[4],anchor_below_raw_row_json=json.dumps(compact(sh.row_values(b[0]-1)),ensure_ascii=False),anchor_admin_context=expected,old_existing_point_distance_km=dist,binding_proof='own censusname/type/region/count unique across oldcompetitors; accepted nearesttwo flanking sourceanchors samecurrentcounty (within25rawrows); rawoldname/nativevalue reopened; ownpoint geography compatible',status='candidate_native_binding_with_anchor_context_not_admitted',historical_county_directly_printed=False,historical_county_context_inferred_from_accepted_flanking_anchors=True)
 witness.append(r)
pd.DataFrame(witness).to_csv(O/'flanking_accepted_anchor_binding_candidates.csv',index=False);print('anchor_candidates',len(witness),sum(int(float(x['old_native_population'])) for x in witness));print(pd.DataFrame(witness)[['name','old_native_population','anchor_above_current_name','anchor_below_current_name']].to_string(index=False) if witness else '')

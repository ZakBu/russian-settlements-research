from pathlib import Path
import sys,json,gzip,re
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize
s=load(25);report=R/'research_rebuild/evidence/working_full_chain_20261007';pins={str(p):sha(p) for p in s.inputs};credit=set()
for _,g in s.obs.groupby('root',sort=False):
 if set(g.census_year)=={2002,2010,2021} and g.population.notna().all() and all(x in s.point_rows for x in g.source_record_id):credit.update(g.source_record_id)
for fn in ['qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_publisher_partition_members.csv']:
 p=report/fn;pins[str(p)]=sha(p);credit.update(pd.read_csv(p,dtype=str).source_record_id)
raw02=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls');raw10=Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls');f02=pd.read_excel(raw02,sheet_name='Sheet1',header=None);f10=pd.read_excel(raw10,sheet_name='Data Sheet',header=None)
for p in [raw02,raw10,O/'municipal_pages.json.gz',O/'municipal_entities.json.gz']:pins[str(p)]=sha(p)
f=pd.read_csv(O/'municipal_roster_native_member_candidates.csv').fillna('');f=f[f.qid.eq('Q5470559')];rows=[]
for y,lo,hi,raw,frame,col in [(2002,4685,4703,raw02,f02,2),(2010,12256,12274,raw10,f10,4)]:
 for source_row in range(lo,hi+1):
  sid=('2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:' if y==2002 else '2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:')+str(source_row)
  r=s.by_id.loc[sid];label=str(frame.iloc[source_row-1,1 if y==2002 else 3]);pop=float(frame.iloc[source_row-1,col]);assert pop==r.population
  candidates=f[f.year.eq(y)&f.candidate_source_IDs_json.map(lambda v:sid in json.loads(v))]
  if len(candidates)!=1:
   assert y==2002 and source_row==4685
   member_name='Фабрики имени 1-го Мая';alias='Published source abbreviates Фабрики им. 1 Мая; same whole NP within complete printed Ryazanovsky source hierarchy'
  else:member_name=candidates.member_name.iloc[0];alias='Exact name/type and complete source hierarchy/ordered literal roster binding'
  rows.append({'scope_id':'moscow2012_ryazanovskoye_complete19','scope_grain':'closed_named_municipal_transfer_constituent_projection','year':y,'member_name':member_name,'source_record_id':sid,'native_name':r.settlement_name,'native_type':r.settlement_type,'native_county':r.district_raw or 'Published 2010 contiguous roster with literal19 names and two-sided group limits','native_population':pop,'native_population_quality':r.population_value_quality,'raw_source_path':str(raw),'raw_source_sha256':pins[str(raw)],'raw_sheet':'Sheet1' if y==2002 else 'Data Sheet','raw_row_1based':source_row,'raw_label':label,'raw_population_cell':'C' if y==2002 else 'E','member_binding_rule':alias,'already_in_stage25_mixed_union':sid in credit,'new_native_population_if_scope_admitted':0 if sid in credit else pop,'candidate_status':'complete_published_roster_native_value_proof_root_review_pending','own_NP_2021_count_asserted':False})
r=pd.DataFrame(rows);assert len(r)==38 and r.source_record_id.nunique()==38
assert list(r.groupby('year').native_population.sum())==[14345,16499]
assert float(f02.iloc[4683,2])==14345
r.to_csv(O/'ryazanovskoye_complete19_native_closure.csv',index=False)
pg=json.load(gzip.open(O/'municipal_pages.json.gz','rt'))['query']['pages'];page=next(p for p in pg.values() if p.get('pageprops',{}).get('wikibase_item')=='Q5470559');text=page['revisions'][0]['slots']['main']['*'];sec=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',text,re.M).group(0)
# Positive published membership/legal basis, not a roster inferred from coordinates.
lines=[l for l in text.splitlines() if ('2005' in l and ('закон' in l.lower() or 'образован' in l.lower())) or ('2012' in l and ('Москв' in l or 'июля' in l))]
(O/'ryazanovskoye_literal_roster_and_transfer_excerpt.txt').write_text('Own municipal article revision '+str(page['revisions'][0]['revid'])+'\n'+sec+'\n\n'+'\n'.join(lines),encoding='utf8')
ent=json.load(gzip.open(O/'municipal_entities.json.gz','rt'))['entities']['Q5470559'];claims=[]
for st in ent['claims']['P1082']:
 for t in st.get('qualifiers',{}).get('P585',[]):
  v=t.get('datavalue',{}).get('value',{});year=int(v.get('time','+0000')[1:5])
  if year in [2010,2021]:claims.append({'year':year,'population':float(st['mainsnak']['datavalue']['value']['amount']),'date':v,'statement_id':st['id'],'references':st.get('references',[])})
assert any(c['year']==2021 and c['population']==28810 for c in claims)
net={str(y):int(g.new_native_population_if_scope_admitted.sum()) for y,g in r.groupby('year')}
receipt={'status':'candidate_complete_native_closure_root_review_pending','baseline_working_stage':25,'scope_id':'moscow2012_ryazanovskoye_complete19','grain':'complete19_named_NP_constituent_projection_for_whole_municipal_transfer; not ownNP series','literal_roster_members':19,'complete_native_members_each_year':19,'native2002_published_parent_row':4684,'native2002_parent_count':14345,'native2002_constituent_sum':14345,'native2010_constituent_sum_protected_values':16499,'municipal2010_census_secondary_count':16500,'native2010_minus_municipal_secondary':-1,'difference_handling':'Preserve all actual protected native values; no allocation or correction; separate direct municipal claim grain','municipal2021_actual_secondary_count':28810,'municipal_actual_census_claims':claims,'conditional_new_unique_native_population':net,'2021_national_new_credit':0,'own_NP2021_counts_claimed':False,'ordinary_identity_edges_proposed':0,'admitted_population_gain':0,'receiving_point_route':'Existing accepted Moscow-city physical representative at event/territorial grain only; individual19 own-point/full3 series not asserted','closure_limits':'2002 all sourcechildren rows4685–4703 bounded by parent4684 and nextparent4704;2010 exact19names rows12256–12274; positive own published legal roster; municipal count comparison shown separately','source_pins_sha256':sha(O/'source_manifest.json')}
(O/'ryazanovskoye_complete19_candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));(O/'closed_scope_source_manifest.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2));print(json.dumps(net))

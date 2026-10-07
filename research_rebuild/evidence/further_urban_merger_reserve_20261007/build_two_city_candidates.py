"""Candidate-only complete 2004 event lineages after first seven admitted groups."""
import json,gzip,hashlib,math,sys
from pathlib import Path
import pandas as pd,duckdb
R=Path(__file__).resolve().parents[3];O=Path(__file__).resolve().parent;E=R/'research_rebuild/evidence'
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from measure_event_aware_path_union_20261005 import SELECTED

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def js(x):return json.dumps(x,ensure_ascii=False)
def main():
 s=load(16);d=s.obs.merge(duckdb.connect().execute('select source_record_id,source_sheet,source_row from read_parquet(?)',[str(SELECTED)]).fetchdf(),on='source_record_id')
 pins={str(p):sha(p) for p in s.inputs};pins[str(SELECTED)]=sha(SELECTED)
 for name in ['working_state_20261007.py','current_chain_state_20261007.py']:
  p=R/'research_rebuild/mass_linkage'/name;pins[str(p)]=sha(p)
 witnesses=[]
 for fn in ['kemerovo64_archive','kemerovo_city198_archive']:
  text=(O/(fn+'.txt')).read_text();start='Статья 1.' if fn=='kemerovo64_archive' else 'В связи с принятием';end='Статья 2.' if fn=='kemerovo64_archive' else '4. Опубликовать'
  excerpt=text[text.index(start):text.index(end,text.index(start))];p=O/(fn+'.html');pins[str(p)]=sha(p);pins[str(O/(fn+'.txt'))]=sha(O/(fn+'.txt'))
  witnesses.append({'key':fn,'source_path':str(p),'source_sha256':sha(p),'exact_excerpt':excerpt,'source_class':'secondary_archived_actual_act_body','official_act_verified':False})
 for fn in ['proper_own_localities.json.gz','novokuznetsk_own_revision_response.json.gz']:
  p=O/fn;pins[str(p)]=sha(p);j=json.load(gzip.open(p))
  for pg in j['query']['pages']:
   if pg['title'] not in ['Боровой (Кемерово)','Кедровка (Кемерово)','Ягуновский','Промышленновский','Абагур','Листвяги (Кемеровская область)','Притомский (Новокузнецк)']:continue
   rev=pg['revisions'][0]
   for line in rev['slots']['main']['content'].splitlines():
    if '2004' in line and any(x in line for x in ['включ','состав','черте','присоед','объедин']):
     witnesses.append({'key':pg['title'],'source_path':str(p),'source_sha256':sha(p),'exact_excerpt':line,'source_class':'secondary_exact_own_locality_receiving_city_event_history','page_title':pg['title'],'revision_id':rev['revid'],'revision_timestamp':rev['timestamp'],'official_act_verified':False})
 (O/'complete_two_city_event_witnesses.json').write_text(json.dumps(witnesses,ensure_ascii=False,indent=2)+'\n')
 configs={'Kemerovo_2004_named':['Кемерово','Боровой','Кедровка','Пионер','Промышленновский','Ягуновский'],'Novokuznetsk_2004_named':['Новокузнецк','Абагур','Листвяги','Притомский']}
 obs=[];members=[];points=[];edges=[];native_w=[];urban=None
 for g,names in configs.items():
  parent=names[0];pr=d[d.census_year.eq(2021)&d.region_norm.eq('кемеровская')&d.settlement_name.eq(parent)&d.settlement_type.eq('город')];assert len(pr)==1
  sid=pr.iloc[0].source_record_id;p=s.point_rows[sid];assert p['target_source_record_id']==sid and all(math.isfinite(float(p[k])) for k in ['latitude','longitude'])
  assert sha(p['point_origin_file'])==p['point_origin_sha256'];pins[p['point_origin_file']]=p['point_origin_sha256'];pins[p['point_ledger_path']]=sha(p['point_ledger_path'])
  points.append({'group':g,'scope_point_role':'representative_scope','parent_source_record_id':sid,'verified_active_state':16,'latitude':p['latitude'],'longitude':p['longitude'],'point_provenance_json':js(p),'historical_constituent_own_point_asserted':False,'candidate_only':True})
  laws=[w for w in witnesses if w['key']=='kemerovo64_archive' or (g.startswith('Kemerovo') and w['key'] in ['kemerovo_city198_archive','Боровой (Кемерово)','Кедровка (Кемерово)','Ягуновский','Промышленновский']) or (g.startswith('Novokuznetsk') and w['key'] in ['Абагур','Листвяги (Кемеровская область)','Притомский (Новокузнецк)'])]
  for y in [2002,2010,2021]:
   mm=[]
   for n in names if y==2002 else [parent]:
    f=d[d.census_year.eq(y)&d.region_norm.eq('кемеровская')&d.settlement_name.eq(n)&d.settlement_type.isin(['город'] if n==parent else ['пгт'])];assert len(f)==1,(g,y,n,len(f));r=f.iloc[0];path=Path('/workspace/settlements-raw')/r.source_file;pins[str(path)]=sha(path)
    raw_name='';raw_population='';context=''
    if y==2002:
     assert path.name=='1_TOM_01_04.xls'
     if urban is None:urban=pd.read_excel(path,header=None)
     raw=urban.iloc[int(r.source_row)-1];raw_name=str(raw[0]);raw_population=int(raw[1]);assert int(r.population)==raw_population and n.lower().replace('ё','е') in raw_name.lower().replace('ё','е')
     context=js([{'one_based_row':i+1,'native_name':str(urban.iloc[i,0]),'native_population':str(urban.iloc[i,1])} for i in range(max(0,int(r.source_row)-4),min(len(urban),int(r.source_row)+2))])
    m={'group':g,'census_year':y,'source_record_id':r.source_record_id,'settlement_name':r.settlement_name,'settlement_type':r.settlement_type,'district_raw':r.district_raw,'population':int(r.population),'source_population_unmodified':True,'source_file':r.source_file,'source_file_sha256':sha(path),'source_row_locator':f'{r.source_sheet}!row={r.source_row}','additive_only_within_complete_named_year_group':True,'exclusive_source_ID_credit':True,'separate_population_credit_in_addition_to_group':False,'own_native_point_available':r.source_record_id in s.point_rows,'ordinary_same_place_edge_created':False,'candidate_only':True}
    members.append(m);mm.append(m);native_w.append({'group':g,'source_record_id':r.source_record_id,'region_norm':r.region_norm,'district_raw':r.district_raw,'source_row_locator':m['source_row_locator'],'raw_2002_name':raw_name,'raw_2002_population':raw_population,'nearby_native_hierarchy_json':context,'selected_id_population_binding_verified':True})
   obs.append({'group':g,'census_year':y,'observation_id':f'named_merger:{g}:{y}','population':sum(m['population'] for m in mm),'population_derivation':'explicit_sum_complete_named_event_roster' if y==2002 else 'direct_published_successor_city','constituent_count':len(mm),'source_record_ids_json':js([m['source_record_id'] for m in mm]),'members_json':js(mm),'roster_complete':True,'identity_axis':'named_merger_event_lineage','ordinary_same_place':False,'boundary_comparability':'UNKNOWN','population_series_scope':'named_event_lineage_not_constant_modern_boundary_estimate','legal_basis_json':js(laws),'official_act_verified':False,'point_role':'representative_scope','representative_parent_source_record_id':sid,'latitude':p['latitude'],'longitude':p['longitude'],'point_provenance_json':js(p),'no_fake_2021_child_population':True,'candidate_only':True})
  for a,b in [(2002,2010),(2010,2021)]:edges.append({'group':g,'from_observation_id':f'named_merger:{g}:{a}','to_observation_id':f'named_merger:{g}:{b}','relation':'complete_named_merger_lineage','ordinary_same_place':False,'boundary_comparability':'UNKNOWN','candidate_only':True})
 roots={root for root,ys in s.years.items() if ys=={2002,2010,2021}}
 for sid in s.obs.source_record_id:
  root=s.uf.find(sid)
  if root in roots and (sid not in s.point_rows or not math.isfinite(float(s.by_id.loc[sid,'population']))):roots.discard(root)
 ordinary=d[d.is_additive_settlement_record.fillna(False)&~d.region_norm.isin(['москва','санкт петербург','севастополь'])&~(d.census_year.eq(2021)&d.region_norm.eq('крым'))];base=set(ordinary.loc[ordinary.source_record_id.map(lambda x:s.uf.find(x) in roots),'source_record_id'])
 for path in [PARTITION_MEMBERS,E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'named_urban_merger_application_20261007/accepted_constituent_credit_union.csv',E/'next_named_urban_merger_application_20261007/accepted_constituent_credit_union.csv']:
  pins[str(path)]=sha(path);base|=set(pd.read_csv(path).source_record_id)
 gains=[]
 for g in configs:
  new={m['source_record_id'] for m in members if m['group']==g}-base
  for y in [2002,2010,2021]:
   add=d[d.census_year.eq(y)&d.source_record_id.isin(new)];gains.append({'group':g,'census_year':y,'baseline_active_state':16,'baseline_includes_first_seven_admitted_named_merger_groups':True,'new_unique_source_IDs':len(add),'net_population_gain_if_admitted':int(add.population.sum()),'net_source_record_ids_json':js(add.source_record_id.tolist()),'candidate_only':True})
 for m in members:m['already_in_existing_source_ID_union_after_first7']=m['source_record_id'] in base
 for key,rows in [('group_observations',obs),('constituent_credit_union',members),('representative_scope_points',points),('event_edges',edges)]:pd.DataFrame(rows).to_csv(O/('candidate_'+key+'.csv'),index=False)
 pd.DataFrame(native_w).to_csv(O/'exact_native_hierarchy_witnesses.csv',index=False);pd.DataFrame(gains).to_csv(O/'net_source_ID_union_gain_after_first7.csv',index=False)
 receipt={'status':'two_complete_named_event_candidates_not_admitted_voronezh_whole_hold','candidate_only':True,'groups_ready':2,'observations':len(obs),'constituents':len(members),'points':len(points),'event_edges':len(edges),'active_state':16,'boundary_comparability':'UNKNOWN','official_act_verified':False,'ordinary_same_place_edges_created':False,'gains':gains,'source_population_values_modified':False,'holds':[{'group':'Voronezh_2011_named','status':'WHOLE_GROUP_HOLD_COMPLETE_ROSTER_AND_NATIVE_BINDINGS','reason':'Direct2011 law106027129503; HTTP/HTTPS Wayback variants404; no complete24settlement roster recovered; no partial sum.'}],'inputs_sha256':pins,'outputs':{path.name:sha(path) for path in O.glob('*') if path.is_file() and path.name not in ['receipt.json','two_city_candidate_receipt.json']}}
 (O/'two_city_candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(js({'groups':2,'observations':len(obs),'constituents':len(members),'series':[(r['group'],r['census_year'],r['population']) for r in obs],'gains':gains}))
if __name__=='__main__':main()

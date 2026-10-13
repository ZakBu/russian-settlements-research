from pathlib import Path
import sys,json,csv,math,gzip,hashlib
import pandas as pd,duckdb
ROOT=Path('/workspace/russian-settlements-research');E=ROOT/'research_rebuild/evidence';O=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from measure_event_aware_path_union_20261005 import SELECTED

def sha(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def norm(s):return str(s).lower().replace('ё','е')
def clean(r):return {k:None if pd.isna(v) else v.item() if hasattr(v,'item') else v for k,v in r.items()}
def write(n,rows):
 with (O/n).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
state=load(stage=15);obs=state.obs.merge(duckdb.connect().execute('select source_record_id,source_sheet,source_row from read_parquet(?)',[str(SELECTED)]).fetchdf(),on='source_record_id');pins={str(p):sha(p) for p in state.inputs}
# Source witnesses are excerpts with full original asset pins, revision IDs and exact law clauses.
w=[]
for key,start,end in [('krasnodar155','постановляет:','Председатель Законодательного'),('tula595','Статья 1','Статья 3'),('khimki140','постановляю:','Губернатор Московской'),('khimki163','постановляю:','Губернатор Московской')]:
 p=O/(key+'.txt');t=p.read_text();i=t.index(start);j=t.index(end,i);w.append({'key':key,'asset_path':str(p),'asset_sha256':sha(p),'exact_excerpt':t[i:j],'source_class':'secondary_actual_act_text','official_verified':False})
for asset,title in [(O/'wikipedia_live_revision_response.json.gz','Химки'),(O/'wikipedia_live_revision_response.json.gz','Донской (город)')]:
 d=json.load(gzip.open(asset));page=next(x for x in d['query']['pages'] if x['title']==title);rev=page['revisions'][0];t=rev['slots']['main']['content'];lines=[l for l in t.splitlines() if (title=='Химки' and 'С 15 сентября 2004' in l) or (title.startswith('Донской') and 'В 2005' in l)]
 assert len(lines)==1;w.append({'key':'khimki209_wiki' if title=='Химки' else 'donskoy2005_wiki','asset_path':str(asset),'asset_sha256':sha(asset),'exact_excerpt':lines[0],'source_class':'secondary_own_city_article_complete_named_event_roster' if title!='Химки' else 'secondary_own_city_article_named_final_event','official_verified':False,'page_title':title,'revision_id':rev['revid'],'revision_timestamp':rev['timestamp']})
(O/'source_witnesses.json').write_text(json.dumps(w,ensure_ascii=False,indent=2)+'\n');pins.update({x['asset_path']:x['asset_sha256'] for x in w})
configs={'Krasnodar_2003_named':('краснодарский','Краснодар',['Краснодар','Калинино','Пашковский'],['krasnodar155']), 'Khimki_2004_named':('московская','Химки',['Химки','Сходня','Фирсановка','Усково','Новоподрезково','Новогорск','Кирилловка','Подсобного Хозяйства "Сходня"','Филино','Старбеево','Вашутино','Клязьма','Яковлево','Трахонеево','Свистуха','Ивакино','Терехово'],['khimki140','khimki163','khimki209_wiki']), 'Tula_2005_named':('тульская','Тула',['Тула','Горелки','Косая Гора','Менделеевский','Скуратовский'],['tula595']), 'Donskoy_2005_named':('тульская','Донской',['Донской','Северо-Задонск','Подлесный','Руднев','Новоугольный','Комсомольский','Шахтерский','Задонье'],['donskoy2005_wiki'])}
rows=[];series=[];points=[];edges=[];hierarchy=[]
urban=Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls');ud=pd.read_excel(urban,header=None);pins[str(urban)]=sha(urban)
rural=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls');rd=pd.read_excel(rural,header=None);pins[str(rural)]=sha(rural)
for g,(region,parent,names,keys) in configs.items():
 members={}
 for y in [2002,2010,2021]:
  members[y]=[]
  for n in names if y==2002 else [parent]:
   d=obs[(obs.census_year==y)&obs.region_norm.eq(region)&obs.settlement_name.map(norm).eq(norm(n))]
   if n==parent:d=d[d.settlement_type.eq('город')]
   elif g=='Khimki_2004_named' and n not in ['Сходня','Фирсановка','Новоподрезково','Старбеево']:d=d[d.district_raw.eq('Химкинский район')]
   else:d=d[d.settlement_type.isin(['пгт','город'])]
   assert len(d)==1,(g,y,n,d.source_record_id.tolist());r=clean(d.iloc[0].to_dict());assert math.isfinite(r['population']);members[y].append(r)
   if y==2002:
    if r['source_file'].endswith('1_TOM_01_04.xls'):
     raw=ud.iloc[int(r['source_row'])-1];assert int(raw[1])==int(r['population']);rawtext=str(raw[0]);h='official urban named roster; source1based row'
    else:
     raw=rd.iloc[int(r['source_row'])-1];assert int(raw[2])==int(r['population']);rawtext=str(raw[1]);h='Химкинский район; exact municipality/subordination hierarchy retained in original rows6298-6315'
    hierarchy.append({'group':g,'source_record_id':r['source_record_id'],'source_file':r['source_file'],'source_sha256':sha(Path('/workspace/settlements-raw')/r['source_file']),'source_row':r['source_row'],'raw_text':rawtext,'raw_population':int(r['population']),'hierarchy_context':h})
 successor=members[2021][0];sid=successor['source_record_id'];assert sid in state.point_rows;point=clean(state.point_rows[sid]);assert math.isfinite(point['latitude']) and math.isfinite(point['longitude']);pj=json.dumps(point,ensure_ascii=False)
 points.append({'group':g,'parent_source_record_id':sid,'point_role':'representative_scope','verified_state':15,'latitude':point['latitude'],'longitude':point['longitude'],'point_provenance_json':pj,'historical_child_own_point_asserted':False})
 for y,mm in members.items():
  ids=[]
  for r in mm:
   p=Path('/workspace/settlements-raw')/r['source_file'];pins[str(p)]=sha(p);ids.append(r['source_record_id']);rows.append({'group':g,'census_year':y,'source_record_id':r['source_record_id'],'settlement_name':r['settlement_name'],'settlement_type':r['settlement_type'],'population':int(r['population']),'source_population_unmodified':True,'source_file':r['source_file'],'source_file_sha256':sha(p),'source_row_locator':f"{r['source_sheet']}!row={r['source_row']}",'component_population_separately_additive':False,'exclusive_source_ID_credit':True,'ordinary_same_place':False})
  series.append({'group':g,'census_year':y,'observation_id':f'named_merger:{g}:{y}','population':sum(int(r['population']) for r in mm),'population_derivation':'explicit_sum_complete_named_event_roster' if y==2002 else 'direct_published_successor_city','constituent_count':len(mm),'source_record_ids_json':json.dumps(ids,ensure_ascii=False),'roster_complete':True,'event_source_witness_keys_json':json.dumps(keys),'population_series_scope':'named_event_lineage_not_constant_modern_boundary_estimate','boundary_comparability':'UNKNOWN','ordinary_same_place':False,'point_role':'representative_scope','parent_source_record_id':sid,'latitude':point['latitude'],'longitude':point['longitude'],'point_provenance_json':pj,'candidate_only':True,'no_fake2021_child_values':True})
 for a,b in [(2002,2010),(2010,2021)]:edges.append({'group':g,'from_observation_id':f'named_merger:{g}:{a}','to_observation_id':f'named_merger:{g}:{b}','relation':'complete_named_merger_lineage','ordinary_same_place':False,'boundary_comparability':'UNKNOWN','candidate_only':True})
# Exact ID union at frozen state15, plus already admitted previous named series.
roots={root for root,ys in state.years.items() if ys=={2002,2010,2021}}
for sid in state.obs.source_record_id:
 root=state.uf.find(sid)
 if root in roots and (sid not in state.point_rows or not math.isfinite(float(state.by_id.loc[sid,'population']))):roots.discard(root)
ordinary=obs[obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((obs.census_year==2021)&obs.region_norm.eq('крым'))];base=set(ordinary.loc[ordinary.source_record_id.map(lambda sid:state.uf.find(sid) in roots),'source_record_id'])
for p in [PARTITION_MEMBERS,E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'named_urban_merger_application_20261007/candidate_constituent_credit_union.csv']:
 pins[str(p)]=sha(p);base|=set(pd.read_csv(p).source_record_id)
new=set(r['source_record_id'] for r in rows)
for r in rows:r['already_in_existing_source_ID_union']=r['source_record_id'] in base
fed=E/'federal_territory_spatial_overlay_20261005/federal_territory_observations.csv';pins[str(fed)]=sha(fed);f=pd.read_csv(fed);fp=f[f.territory_key.isin(['RU-FED-MOW','RU-FED-SPB'])].groupby('census_year').territory_population.sum().to_dict()
gains=[]
for y in [2002,2010,2021]:
 d=obs[obs.census_year==y];b=d[d.source_record_id.isin(base)];add=d[d.source_record_id.isin(new-base)];gains.append({'census_year':y,'baseline_state':15,'baseline_includes_prior_admitted_named_merger3':True,'baseline_plus_federal_population':int(b.population.sum())+int(fp[y]),'new_unique_source_IDs':len(add),'net_national_population_added':int(add.population.sum()),'after_plus_federal_population':int(b.population.sum()+add.population.sum())+int(fp[y]),'net_source_IDs_json':json.dumps(add.source_record_id.tolist()),'federal_population_added':0})
write('candidate_group_observations.csv',series);write('candidate_constituent_credit_union.csv',rows);write('candidate_representative_scope_points.csv',points);write('candidate_event_edges.csv',edges);write('exact_source_row_witnesses.csv',hierarchy);write('net_source_ID_union_gain.csv',gains)
holds=[{'group':'Kemerovo_2004_named','status':'HOLD_COMPLETE_NAMED_EVENT_ROSTER_CORROBORATION','reason':'Official2002 hierarchy contains Kemerovo and five pgt Borovoy6093,Kedrovka18203,Pioner6168,Promyshlennovsky6308,Yagunovsky8408. Own articles corroborate2004 inclusion but Pioner claim tagged нет в источнике; full64-OZ named act roster unavailable503. No partial sum emitted.'},{'group':'Voronezh_2011_named','status':'HOLD_COMPLETE_NAMED_EVENT_ROSTER_AND_SOURCE_BINDINGS','reason':'2011 union involves more than20 settlements; own Pridonskoy/Somovo articles prove their inclusion but no complete named act roster recovered. Exact law citation nd106027129 returns503; no partial sum emitted.'}];write('held_groups.csv',holds)
(O/'receipt.json').write_text(json.dumps({'status':'four_complete_named_merger_candidates_two_whole_group_holds','candidate_only':True,'active_state':15,'groups_ready':4,'observations':12,'constituents':len(rows),'event_edges':8,'representative_scope_points':4,'gains':gains,'holds':holds,'source_populations_unchanged':True,'boundary_comparability':'UNKNOWN','inputs_sha256':pins,'outputs_sha256':{p.name:sha(p) for p in O.glob('*.csv')},'source_witness_sha256':sha(O/'source_witnesses.json')},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'series':[(r['group'],r['census_year'],r['population']) for r in series],'gains':gains},ensure_ascii=False))

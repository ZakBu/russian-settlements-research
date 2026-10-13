"""Action-ready exact-name neutral county-caption subset, no accepted files mutated."""
import sys,json,re
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
O=Path(__file__).resolve().parent;W=Path('/workspace/settlements-work/cross_county_independent_point_bridge_20261007')
f=pd.read_csv(W/'candidates.csv.gz',dtype=str,keep_default_na=False)
# Deliberately explicit geographic noun/adjective equivalences: no approximate county matching.
pairs={
'Алапаевский район':'Городской округ муниципальное образование Алапаевское',
'Антроповский район':'Антроповский муниципальный район',
'Балашихинский район':'Городской округ Балашиха',
'Богдановичский район':'Городской округ Богданович',
'Волотовский район':'Волотовский муниципальный округ Новгородской области',
'Воскресенский район':'Городской округ Воскресенск',
'Домодедовский район':'Городской округ Домодедово',
'Егорьевский район':'Городской округ Егорьевск',
'Ефремовский район':'Городской округ город Ефремов',
'Зарайский район':'Городской округ Зарайск',
'Ирбитский район':'Городской округ Ирбитское муниципальное образование',
'Иркутский район':'Иркутское районное муниципальное образование',
'Истринский район':'Городской округ Истра',
'Каширский район':'Городской округ Кашира',
'Кировский район':'Муниципальный район "Город Киров и Кировский район"',
'Клинский район':'Городской округ Клин',
'Коломенский район':'Городской округ Коломна',
'Котласский район':'Котласский муниципальный район',
'Кулебакский район':'Городской округ город Кулебаки',
'Лотошинский район':'Городской округ Лотошино',
'Луховицкий район':'Городской округ Луховицы',
'Люберецкий район':'Городской округ Люберцы',
'Людиновский район':'Муниципальный район "Город Людиново и Людиновский район"',
'Маревский район':'Марёвский муниципальный округ Новгородской области',
'Михайловский район':'Городской округ город Михайловка',
'Мытищинский район':'Городской округ Мытищи',
'Нерехтский район':'Муниципальный район город Нерехта и Нерехтский район',
'Павлово-Посадский район':'Городской округ Павловский Посад',
'Переславский район':'Городской округ город Переславль-Залесский',
'Подольский район':'Городской округ Подольск',
'Саратовский район':'Городской округ город Саратов',
'Сафоновский район':'Сафоновский муниципальный район',
'Серебряно-Прудский район':'Городской округ Серебряные Пруды ',
'Серпуховский район':'Городской округ Серпухов',
'Славгородский район':'Городской округ город Славгород',
'Солецкий район':'Солецкий муниципальный округ Новгородской области',
'Солнечногорский район':'Городской округ Солнечногорск',
'Ступинский район':'Городской округ Ступино',
'Усольский район':'Усольское районное муниципальное образование',
'Хвойнинский район':'Хвойнинский муниципальный округ Новгородской области',
'Чеховский район':'Городской округ Чехов',
'Чкаловский район':'Городской округ город Чкаловск',
'Чунский район':'Чунское районное муниципальное образование',
'Шатурский район':'Городской округ Шатура',
'Шаховской район':'Городской округ Шаховская',
'Шахунский район':'Городской округ город Шахунья',
'Щёлковский район':'Городской округ Щёлково',
}
neutral={(normalize(a),normalize(b)) for a,b in pairs.items()}
f['county_caption_class']=f.apply(lambda a:'neutral_same_geographic_county_caption' if (normalize(a.old_district_raw),normalize(a.current_district_raw)) in neutral else 'hold_different_geographic_county_stem_requires_direct_identity',axis=1)
held=f[f.county_caption_class.str.startswith('hold')].copy();nf=f[~f.county_caption_class.str.startswith('hold')].copy();held.to_csv(W/'different_geographic_stem_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0})
classcounts=f.groupby(['old_district_raw','current_district_raw','county_caption_class']).size().reset_index(name='candidate_edges');classcounts.to_csv(O/'county_caption_classification.csv',index=False)
s=load(17);before=s.metrics();members=defaultdict(list)
for a in s.obs.to_dict('records'):members[s.uf.find(a['source_record_id'])].append(a)
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
edges=[];uses=[];donorhash={};taken=set();counts=Counter();action=[]
for a in nf.to_dict('records'):
 sid,bid=a['old_source_record_id'],a['current_source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid);cp=s.point_rows[bid]
 if ra==rb:counts['already_connected_batch']+=1;continue
 if s.years[ra]&s.years[rb]:counts['batch_repeated_census_year_hold']+=1;continue
 relevant=members[ra]+members[rb]
 if any(r['source_record_id'] in s.point_rows and distance_km((s.point_rows[r['source_record_id']]['latitude'],s.point_rows[r['source_record_id']]['longitude']),(cp['latitude'],cp['longitude']))>5 for r in relevant):counts['component_point_contradiction_hold']+=1;continue
 if any(r['source_record_id'] not in s.point_rows and r['source_record_id'] not in taken and occupied.get((int(r['census_year']),cp['latitude'],cp['longitude']),set())-{r['source_record_id']} for r in relevant):counts['batch_sameyear_point_collision_hold']+=1;continue
 assert a['region_norm']==str(s.by_id.loc[bid,'region_norm'])==str(s.by_id.loc[sid,'region_norm'])
 s.union(sid,bid);members[s.uf.find(sid)]=relevant;action.append(a)
 edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','rule':'exact_name_independent_sourcebound_points_neutral_county_caption','old_district_raw':a['old_district_raw'],'current_district_raw':a['current_district_raw'],'administrative_event_date':'UNKNOWN','population_boundary_comparability_asserted':False})
 ledger=Path(cp['point_ledger_path']);donorhash.setdefault(str(ledger),sha(ledger))
 for r in relevant:
  tid=r['source_record_id'];yr=int(r['census_year'])
  if tid in s.point_rows or tid in taken:continue
  p={k:v for k,v in cp.items() if k!='point_ledger_path'};p.update(target_source_record_id=tid,target_year=yr,latitude=cp['latitude'],longitude=cp['longitude'],coordinate_source_record_id=bid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_origin_ledger=str(ledger),coordinate_origin_ledger_sha256=donorhash[str(ledger)],coordinate_origin_ledger_locator='target_source_record_id='+bid,point_origin_kind='retrospective_spatial_continuity_inference',direct_historical_measurement=False,population_boundary_comparability_asserted=False,administrative_event_date='UNKNOWN');uses.append(p);taken.add(tid);occupied[(yr,cp['latitude'],cp['longitude'])].add(tid)
# Check status against the actual state API accepted set, and replay as a read-only simulation.
from build_long_table import ACCEPTED_COORDINATE_STATUSES
assert 'reviewed_extension_rule_accepted' in ACCEPTED_COORDINATE_STATUSES
pd.DataFrame(edges).to_csv(W/'neutral_identity_edge_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(uses).to_csv(W/'neutral_point_use_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(action).to_csv(W/'neutral_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
after=s.metrics(extra_point_ids=taken)
receipt={'status':'action_ready_rule_subset_not_applied','stage':17,'rule':'Exact physical name, identical region, unique source-bound old own label/type/historical county, independent admitted current point within5km, no all-current rivals, and explicit neutral same-geographic county caption equivalence. Raw old point need not already be admitted. Different geographic county stems held unless direct identity established separately.','neutral_candidate_edges':len(nf),'action_ready_edges':len(edges),'action_ready_pointuses':len(uses),'different_geographic_stem_held_edges':len(held),'baseline':before,'simulation':after,'marginal_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'marginal_full_three_rows':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'batch_hold_counts':dict(counts),'raw_point_independence_binding_inherited':True,'source_check_receipt_sha256':sha(O/'source_check_receipt.json'),'sourceclasses':pd.DataFrame(action).groupby('old_point_route').size().to_dict(),'administrative_eventdate':'UNKNOWN','boundaries_and_population_comparability_asserted':False,'source_population_changed':False,'inputs':{str(p):sha(p) for p in [*s.inputs,W/'candidates.csv.gz',O/'source_check_receipt.json',Path(__file__)]},'donor_ledger_sha256':donorhash,'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [W/'neutral_identity_edge_delta.csv.gz',W/'neutral_point_use_delta.csv.gz',W/'neutral_candidates.csv.gz',W/'different_geographic_stem_holds.csv.gz',O/'county_caption_classification.csv']}}
(O/'neutral_subset_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['action_ready_edges','action_ready_pointuses','different_geographic_stem_held_edges','marginal_population_gain','marginal_full_three_rows','batch_hold_counts']}))

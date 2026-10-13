"""Replay the frozen stage24 exclusive credit union and persisted full-roster sums."""
import sys,json,collections,math
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;REPORT=ROOT/'research_rebuild/evidence/working_full_chain_20261007';sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
r=json.loads((OUT/'application_receipt.json').read_text())
for path,digest in r['inputs_sha256'].items():assert sha(Path(path))==digest,path
for name,digest in r['outputs'].items():assert sha(OUT/name)==digest,name
s=load(stage=24);members=pd.read_csv(OUT/'accepted_constituent_credit_union.csv');obs=pd.read_csv(OUT/'accepted_group_observations.csv');points=pd.read_csv(OUT/'accepted_representative_scope_points.csv');events=pd.read_csv(OUT/'accepted_event_edges.csv');assert (len(members),len(obs),len(points),len(events))==(85,3,1,2);assert not members.source_record_id.duplicated().any()
for row in members.itertuples():
 native=s.by_id.loc[row.source_record_id];assert int(native.population)==int(row.population) and int(native.census_year)==int(row.census_year);assert native.population_value_quality==row.source_population_quality;assert row.source_population_unmodified and not row.ordinary_same_place_edge_created
for row in obs.itertuples():
 subset=members[members.census_year.eq(row.census_year)];assert set(json.loads(row.source_record_ids_json))==set(subset.source_record_id);assert int(subset.population.sum())==int(row.population);assert row.roster_complete and not row.ordinary_same_place and row.boundary_comparability=='UNKNOWN'
root_members=collections.defaultdict(list)
for row in s.obs.itertuples():root_members[s.uf.find(row.source_record_id)].append(row)
prior=set()
for root,rs in root_members.items():
 if s.years[root]=={2002,2010,2021} and all(row.source_record_id in s.point_rows and pd.notna(row.population) and math.isfinite(float(row.population)) for row in rs):prior.update(row.source_record_id for row in rs)
for name in ['complete_publisher_partition_members.csv','qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv']:prior.update(pd.read_csv(REPORT/name).source_record_id)
net=pd.read_csv(OUT/'net_source_ID_union_gain.csv');assert members.already_in_existing_source_ID_union.equals(members.source_record_id.isin(prior))
for row in net.itertuples():
 actual=members[members.census_year.eq(row.census_year)&~members.source_record_id.isin(prior)];assert len(actual)==row.new_unique_source_IDs and int(actual.population.sum())==row.net_population_gain_if_admitted;assert set(actual.source_record_id)==set(json.loads(row.net_source_record_ids_json))
p=points.iloc[0];active=s.point_rows[p.parent_source_record_id];assert (float(p.latitude),float(p.longitude))==(active['latitude'],active['longitude']);origin=json.loads(p.point_provenance_json);assert sha(Path(origin['point_origin_file']))==origin['point_origin_sha256'];assert not p.historical_constituent_own_point_asserted
r['disk_replay_stage24_unique_credit_union_verified']=True;r['all85_original_selected_populations_and_quality_flags_preserved']=True;(OUT/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('Replay passed:3 complete source-hierarchy observations,85 distinct native members,82 new source IDs, point only on scope.')

"""Retain actual named quarter counts in explicitly typed recreation trajectories."""
import json, math
from pathlib import Path
import pandas as pd
import xlrd
from current_chain_state_20261007 import sha, distance_km
from working_state_20261007 import E, load

REVIEW = E / 'large_observed_year_recovery_20261007'
OUT = E / 'recreated_named_locality_event_application_20261007'
TRAJECTORIES = ['large_ownyear:Q4365077','large_ownyear:Q4078592']


def main():
    review = json.loads((REVIEW/'package_receipt.json').read_text())
    for name, expected in review['outputs'].items():
        if sha(REVIEW/name) != expected:
            raise ValueError('Candidate output changed: '+name)
    source = REVIEW/'candidate_qualified_actual_observations.csv'
    frame = pd.read_csv(source, keep_default_na=False)
    frame = frame[frame.trajectory_id.isin(TRAJECTORIES)].copy()
    if len(frame) != 6 or frame[['trajectory_id','year']].duplicated().any():
        raise ValueError('Incomplete named event series')
    state = load(17)
    pins = {}
    def pin(path, expected):
        path = Path(path)
        pins.setdefault(str(path), sha(path))
        if pins[str(path)] != expected:
            raise ValueError('Source bytes changed: '+str(path))
    witness = REVIEW/'own_pages.json.gz'
    pin(witness, review['event_secondary_disaggregation_witness_sha256'])
    for trajectory, rows in frame.groupby('trajectory_id'):
        if set(rows.year) != {2002,2010,2021}:
            raise ValueError('Missing actual census year')
        parent = rows.loc[rows.year.eq(2021),'source_record_id'].iloc[0]
        current = state.point_rows[parent]
        for row in rows.to_dict('records'):
            if not math.isfinite(float(row['population_source_value'])):
                raise ValueError('Unknown population cannot be imputed')
            pin(row['source_path'],row['source_sha256'])
            pin(row['point_origin_file'],row['point_origin_sha256'])
            if distance_km((float(row['latitude']),float(row['longitude'])),
                           (current['latitude'],current['longitude'])) > .00001:
                raise ValueError('Representative trajectory point differs')
            if int(row['year']) == 2002:
                if not row['nonadditive_observation'] or 'district' not in row['grain']:
                    raise ValueError('Historical quarter misrepresented as ordinary NP')
                index = int(row['source_record_id'].rsplit('row',1)[1])-1
                book = xlrd.open_workbook(row['source_path'],on_demand=True)
                cells = book.sheet_by_name('01-04').row_values(index)
                expected_word = 'Плиевский' if trajectory.endswith('Q4365077') else 'Барсукинский'
                if expected_word not in str(cells[0]) or int(cells[1]) != int(row['population_source_value']):
                    raise ValueError('Actual named quarter cell differs')
                book.release_resources()
            else:
                native = state.by_id.loc[row['source_record_id']]
                if int(native.population) != int(row['population_source_value']) or state.uf.find(parent) != state.uf.find(row['source_record_id']):
                    raise ValueError('Actual selected year observation differs')
    OUT.mkdir(parents=True,exist_ok=True)
    frame['scope'] = 'secondary_documented_named_district_recreation_2009'
    frame['decision_status'] = 'qualified_accepted_secondary_event_witness'
    frame['ordinary_NP3_asserted'] = False
    frame['boundary_comparability'] = 'UNKNOWN'
    frame['event_witness_file'] = str(witness)
    frame['event_witness_sha256'] = pins[str(witness)]
    frame['event_witness_claim'] = 'Own named district incorporated in Nazran in 1995; village recreated from abolished own named district in 2009; secondary own-article statement'
    name = 'accepted_qualified_physical_observations.csv'
    frame.to_csv(OUT/name,index=False)
    receipt = {'status':'applied_secondary_documented_named_district_recreation_series',
               'application_stage':17,'series':2,'observations':6,
               '2002_observation_grain':'published named intraurban quarter, not ordinary NP',
               '2002_population_credit':'nonadditive under existing Nazran census population',
               'event_source_quality':'own Wikipedia revision; primary legal act not independently authenticated',
               'boundary_comparability':'UNKNOWN','ordinary_same_place_graph_modified':False,
               'source_population_values_modified':False,'candidate_source_sha256':sha(source),
               'inputs':pins,'outputs':{name:sha(OUT/name)}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'series':2,'selected_reference_population':{int(y):int(g.population_source_value.sum()) if int(y)!=2002 else 0 for y,g in frame.groupby('year')}}))


if __name__ == '__main__': main()

"""Admit complete named event rosters, retaining their distinct physical scope."""
import json
from pathlib import Path
import pandas as pd
from current_chain_state_20261007 import sha, distance_km
from working_state_20261007 import load, E

OUT = E / 'named_urban_merger_application_20261007'
FILES = ('group_observations', 'constituent_credit_union',
         'representative_scope_points', 'event_edges')
EXPECTED = {
    'Podolsk_Klimovsk_Lvovskiy': (248513, 255003, 314934),
    'Balashikha_Zheleznodorozhny': (288744, 346751, 520962),
    'Korolev_Yubileiny': (201395, 216639, 228095),
}


def main():
    review = json.loads((OUT / 'receipt.json').read_text())
    for path, expected in review['inputs_sha256'].items():
        if sha(Path(path)) != expected:
            raise ValueError('Candidate input changed: ' + path)
    for name, expected in review['output_sha256'].items():
        if sha(OUT / name) != expected:
            raise ValueError('Candidate output changed: ' + name)
    state = load(15)
    frames = {key: pd.read_csv(OUT / ('candidate_' + key + '.csv'),
                              keep_default_na=False) for key in FILES}
    obs, members, points, events = (frames[key] for key in FILES)
    if len(obs) != 9 or len(members) != 34 or len(points) != 3 or len(events) != 6:
        raise ValueError('Unexpected named event roster')
    if members.source_record_id.duplicated().any():
        raise ValueError('Duplicate constituent credit')
    for group, populations in EXPECTED.items():
        rows = obs[obs.group.eq(group)].sort_values('census_year')
        if tuple(rows.population) != populations or set(rows.census_year) != {2002, 2010, 2021}:
            raise ValueError('Named series differs')
        for row in rows.to_dict('records'):
            selected = members[members.group.eq(group) & members.census_year.eq(row['census_year'])]
            if set(json.loads(row['source_record_ids_json'])) != set(selected.source_record_id):
                raise ValueError('Incomplete named event roster')
            if int(selected.population.sum()) != int(row['population']):
                raise ValueError('Constituent sum differs')
            if not row['roster_complete'] or row['ordinary_same_place'] or row['boundary_comparability'] != 'UNKNOWN':
                raise ValueError('Incorrect identity or comparability claim')
            for law in json.loads(row['legal_basis_json']):
                path = E.parents[1] / law['compressed_path']
                if sha(path) != law['compressed_sha256']:
                    raise ValueError('Legal source changed')
    for row in members.to_dict('records'):
        native = state.by_id.loc[row['source_record_id']]
        if int(native.census_year) != int(row['census_year']) or int(native.population) != int(row['population']):
            raise ValueError('Native source population changed')
        path = Path(native.source_path) if isinstance(native.source_path, str) and native.source_path else Path('/workspace/settlements-raw') / native.source_file
        if not path.is_file():
            path = Path('/workspace/settlements-raw') / native.source_file
        if sha(path) != row['source_file_sha256']:
            raise ValueError('Original census file changed')
    for row in points.to_dict('records'):
        native = state.point_rows[row['parent_source_record_id']]
        if distance_km((float(row['latitude']), float(row['longitude'])),
                       (native['latitude'], native['longitude'])) > .00001:
            raise ValueError('Active receiving-city point differs')
        if row['historical_constituent_own_point_asserted']:
            raise ValueError('Parent point assigned to historical child')
    outputs = {}
    for key, frame in frames.items():
        if 'candidate_only' in frame:
            frame['candidate_only'] = False
        frame['decision_status'] = 'accepted_complete_named_event_scope_secondary_legal_text'
        name = 'accepted_' + key + '.csv'
        frame.to_csv(OUT / name, index=False)
        outputs[name] = sha(OUT / name)
    receipt = {
        'status': 'applied_separate_complete_named_merger_event_lineage',
        'ordinary_same_place_graph_modified': False,
        'historical_child_points_or_missing_year_populations_created': False,
        'boundary_comparability': 'UNKNOWN',
        'modern_boundary_harmonization_asserted': False,
        'legal_source_quality': 'secondary legal-text mirrors; official authentication unasserted',
        'candidate_receipt_sha256': sha(OUT / 'receipt.json'),
        'source_population_values_modified': False,
        'outputs': outputs,
        'admission_stage': 15,
        'net_selected_source_id_union_gain_at_admission': review['net_gain'],
    }
    (OUT / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'groups': 3, 'observations': 9,
                      'net_population_gain': [r['net_national_population_added'] for r in review['net_gain']]}))


if __name__ == '__main__':
    main()

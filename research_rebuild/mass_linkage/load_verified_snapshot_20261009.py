"""Load the verified complete stage70 graph without replaying obsolete intermediates."""
from pathlib import Path
import json
import sys
import pandas as pd
from current_chain_state_20261007 import State, sha
from build_long_table import UnionFind, ACCEPTED_COORDINATE_STATUSES

def load_verified_snapshot(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'release-assets-manifest.json').read_text())
    entries = {row['name']: row for row in manifest['assets']}
    names = ['applied_state_observations.parquet', 'applied_component_snapshot.csv.gz',
             'applied_point_snapshot.parquet', 'full_export_receipt.json']
    for name in names:
        path = directory / name
        if path.stat().st_size != entries[name]['bytes'] or sha(path) != entries[name]['sha256']:
            raise ValueError(f'Final snapshot differs: {name}')
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / 'research_rebuild/evidence/main_axis_residual_application68_20261008'))
    from hydrate_point_snapshot import hydrate_active_point_rows
    state = State.__new__(State)
    state.obs = pd.read_parquet(directory / names[0])
    state.by_id = state.obs.set_index('source_record_id', drop=False)
    components = pd.read_csv(directory / names[1], dtype=str, keep_default_na=False)
    if set(components.source_record_id) != set(state.obs.source_record_id):
        raise ValueError('Component and observation UID sets differ')
    state.uf = UnionFind(state.obs.source_record_id)
    for component_root, members in components.groupby('root').source_record_id:
        for sid in members:
            state.uf.union(component_root, sid)
    if any(state.uf.find(sid) != component_root for sid, component_root in components[['source_record_id','root']].itertuples(index=False, name=None)):
        raise ValueError('Hydrated component roots differ')
    state.years = {r: set(map(int, years)) for r, years in state.obs.groupby('root').census_year}
    state.point_rows, _ = hydrate_active_point_rows(directory / names[2], ACCEPTED_COORDINATE_STATUSES)
    state.point_alternatives = []
    state.conflicting_point_targets = set()
    state.inputs = [directory / name for name in names]
    receipt = json.loads((directory / names[3]).read_text())
    if len(state.obs) != receipt['selected_observation_rows'] or len(state.point_rows) != receipt['active_point_rows']:
        raise ValueError('Final snapshot row totals differ')
    return state

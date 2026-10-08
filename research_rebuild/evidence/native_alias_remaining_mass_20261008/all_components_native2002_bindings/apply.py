"""Apply frozen source-bound native census links to the actual stage36 state."""
import importlib.util
import json
import sys
from pathlib import Path

R = Path('/workspace/russian-settlements-research')
sys.path.insert(0, str(R / 'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha

O = Path(__file__).parent

def finite_metrics(state):
    spec = importlib.util.spec_from_file_location('native_finite_metrics', R / 'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.finite_metrics(state)

def apply(state):
    receipt = json.loads((O / 'application_receipt.json').read_text())
    for path, expected in receipt['input_pins'].items():
        assert sha(Path(path)) == expected, path
    for name, expected in receipt['output_pins'].items():
        assert sha(O / name) == expected, name
    assert state.metrics() == receipt['before'], 'Frozen actual36 metrics differ'
    assert finite_metrics(state) == receipt['before_finite_all3_all_points']
    state.add_deltas([O / 'accepted_identity_edge_delta.csv'], [O / 'accepted_point_use_delta.csv'])
    assert state.metrics() == receipt['after']
    assert finite_metrics(state) == receipt['after_finite_all3_all_points']
    return state

if __name__ == '__main__':
    from working_state_20261007 import load
    apply(load(36))
    print('Actual36 source/output pins and finite native3 point replay passed')

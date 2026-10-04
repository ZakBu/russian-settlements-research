"""Locate accepted three-census components lacking row-level admitted points.

Read-only diagnosis: an existing graph path does not admit a missing point, and
a historic point-route hold is not silently removed. Inputs are pinned by the
current working configuration. Large output stays outside Git.
"""
from pathlib import Path
import argparse
import hashlib
import json
import time
import pandas as pd
from research_rebuild.mass_linkage.coverage import identity_sets


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(config_path, blocked_path, output):
    started = time.monotonic()
    cfg = json.loads(Path(config_path).read_text())
    paths = {k: Path(cfg[k]) for k in ('working_population_layer',
        'working_identity_graph', 'working_point_uses')}
    hashes = {k: sha(v) for k, v in paths.items()}
    for key in ('working_identity_graph', 'working_point_uses'):
        if hashes[key] != cfg[key + '_sha256']:
            raise ValueError(f'working input checksum mismatch: {key}')
    selected = pd.read_parquet(paths['working_population_layer'], columns=[
        'source_record_id', 'census_year', 'population', 'settlement_name', 'type_norm'])
    graph = pd.read_parquet(paths['working_identity_graph'], columns=[
        'from_source_record_id', 'to_source_record_id'])
    points = pd.read_parquet(paths['working_point_uses'], columns=[
        'target_source_record_id', 'coordinate_admission_status'])
    from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
    if not points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all():
        raise ValueError('point ledger contains a non-admitted canonical status')
    _, full, components = identity_sets(selected, graph)
    # Construct this once: rebuilding the large set per component is quadratic.
    point_ids = set(points.target_source_record_id)
    blocked = set(json.loads(Path(blocked_path).read_text())['blocked_target_source_record_ids'])
    seed_ids = point_ids - blocked
    reasons = {}
    for members in components:
        if not members <= full:
            continue
        has_seed = bool(members & seed_ids)
        for sid in members - point_ids:
            reasons[sid] = ('global_target_hold' if sid in blocked else
                'no_accepted_seed' if not has_seed else 'continuity_application_hold_requires_inspection')
    result = selected[selected.source_record_id.isin(reasons)].copy()
    result['why'] = result.source_record_id.map(reasons)
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)
    groups = result.groupby(['census_year', 'why']).agg(
        rows=('source_record_id', 'size'), population=('population', 'sum')).reset_index()
    receipt = {'status': 'diagnostic_only_no_admissions', 'inputs': {
        k: {'path': str(v), 'sha256': hashes[k]} for k, v in paths.items()},
        'blocked_targets': {'path': str(blocked_path), 'sha256': sha(blocked_path)},
        'output': {'path': str(output), 'sha256': sha(output)},
        'groups': groups.to_dict('records'), 'elapsed_seconds': time.monotonic() - started}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/mass_joint_20261004.json')
    parser.add_argument('--blocked', default='/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.config, args.blocked, args.output)

"""Replay every actually applied scope named in a frozen working configuration."""
import argparse
import json
from pathlib import Path
from research_rebuild.mass_linkage.measure_scoped_joint_coverage_eighth_20261004 import run


def measure(config, output, residual, graph=None, points=None):
    config = Path(config)
    cfg = json.loads(config.read_text())
    folder = lambda key: str(Path(cfg[key]).parent) if cfg.get(key) else None
    folders = lambda key: [str(Path(p).parent) for p in cfg.get(key, [])]
    run(points=points or cfg['working_point_uses'], graph=graph or cfg['working_identity_graph'],
        output=output, residual_output=residual,
        supplemental=folder('accepted_scoped_2014_supplement'),
        official_scope=folder('accepted_official_primary_scoped_trajectories'),
        secondary_scope=folder('accepted_secondary_supported_trajectories'),
        typed_scope=folders('accepted_typed_intracity_scope_layers'),
        inclusion_scope=folders('accepted_secondary_reported_inclusion_scope_layers'),
        complete_partition_scope=folders('accepted_complete_partition_scope_layers'),
        reported_inclusion_reference_scope=folders('accepted_reported_inclusion_reference_scopes'),
        combined_temporal_scope=folders('accepted_combined_temporal_scope_layers'),
        event_aware_selected_scope=folders('accepted_event_aware_selected_scope_layers'),
        auxiliary_primary_temporal_scope=folders('accepted_auxiliary_primary_temporal_scope_layers'),
        target_fraction=cfg['current_user_goal_population_fraction'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--residual', required=True)
    parser.add_argument('--graph')
    parser.add_argument('--points')
    a = parser.parse_args()
    measure(a.config, a.output, a.residual, a.graph, a.points)

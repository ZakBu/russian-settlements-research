#!/usr/bin/env python3
"""Run the five dated pilot comparisons from one unpacked release directory."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

CASES = ('medical_presence', 'medical_count', 'school_presence', 'school_count', 'official_udmurt_selected_plan')


def build_commands(data: Path, costs: Path, output: Path, *, half_lives='15,30,60', floors='0.01,0.05,0.1', only=CASES, reference_all_regions=False):
    model = Path(__file__).resolve().with_name('model.py')
    commands = []
    for case in CASES:
        if case not in only:
            continue
        cmd = [sys.executable, str(model), '--settlements', str(data/'settlements.parquet'),
               '--costs', str(costs), '--output', str(output/case),
               '--half-lives', half_lives, '--floors', floors, '--families', 'exponential,power', '--max-cost-minutes', '180']
        if case == 'official_udmurt_selected_plan':
            cmd += ['--supply', str(data/'supply_official_udmurt_2025.parquet'), '--functions', 'healthcare',
                    '--orders', 'primary_fap', '--regions', 'удмуртская', '--models', 'functional', '--supply-transform', 'binary']
        else:
            cmd += ['--supply', str(data/'supply_all_2021.parquet'),
                    '--context-supply', str(data/'supply_context2021.parquet'),
                    '--source-scenarios', 'spatial_proxy', '--regions', 'ленинградская,удмуртская',
                    '--models', 'nearest,population,functional']
            cmd += ['--supply-transform', 'object_count' if case.endswith('_count') else 'binary']
            if case.startswith('medical'):
                cmd += ['--functions', 'healthcare', '--collapse-orders']
            else:
                cmd += ['--functions', 'education', '--orders', 'school']
        commands.append((case, cmd))
        if reference_all_regions and case != 'official_udmurt_selected_plan':
            ref_cmd = list(cmd)
            for option, value in [('--half-lives', '30'), ('--floors', '0.05'), ('--families', 'exponential')]:
                ref_cmd[ref_cmd.index(option)+1] = value
            idx = ref_cmd.index('--regions')
            del ref_cmd[idx:idx+2]
            ref_cmd[ref_cmd.index('--output')+1] = str(output/'reference_all_regions'/case)
            commands.append(('reference_all_regions/'+case, ref_cmd))
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--costs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--half-lives', default='15,30,60')
    parser.add_argument('--floors', default='0.01,0.05,0.1')
    parser.add_argument('--reference-all-regions', action='store_true', help='Also run exp30/floor0.05 reference on all four prepared regions')
    parser.add_argument('--only', nargs='+', choices=CASES, default=list(CASES))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'running', 'completed_cases': [], 'commands': []}
    path = args.output/'run_manifest.json'
    commands = build_commands(args.data, args.costs, args.output, half_lives=args.half_lives, floors=args.floors, only=args.only, reference_all_regions=args.reference_all_regions)
    manifest['commands'] = [{'case': case, 'argv': cmd} for case, cmd in commands]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for case, cmd in commands:
        print(f'Running {case}', flush=True)
        subprocess.run(cmd, check=True)
        manifest['completed_cases'].append(case)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    manifest.update(status='completed', finished_at_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()

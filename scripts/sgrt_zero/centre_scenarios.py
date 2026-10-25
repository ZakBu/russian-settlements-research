#!/usr/bin/env python3
"""Screen corrected direct choices under the existing, explicitly dated scenarios.

No observed assignments, new travel thresholds or transitive merging are added.
The original profile partitions are not used as territorial units.
"""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screens import canonical, with_admission, SCENARIOS, RAW_CODES, digest
from centre_stars import build_centre_stars


def run(bundle, corrected_routes, output, scenarios, endpoints=None):
    if output.resolve().is_relative_to(bundle.resolve()):
        raise ValueError('Do not write inside the immutable control')
    output.mkdir(parents=True, exist_ok=True)
    ref_path = bundle / 'context/analysis_reference.parquet'
    reference = pd.read_parquet(ref_path)
    inputs = {str(ref_path): digest(ref_path)}
    if endpoints is None:
        endpoints = bundle / 'routes/endpoints.parquet'
    endpoint_frame = pd.read_parquet(endpoints)
    if 'verified_component_node_count' in endpoint_frame:
        endpoint_frame['audit_component_size'] = endpoint_frame.verified_component_node_count
    inputs[str(endpoints)] = digest(endpoints)
    canonical_cache = {}
    result = {}
    for sid in scenarios:
        cfg = SCENARIOS[sid]
        frames = []
        for family in cfg['families']:
            code = cfg.get('parcel_raw_code', RAW_CODES[family]) if family == 'parcel_pickup' else RAW_CODES[family]
            if code not in canonical_cache:
                if code == 'daily_grocery':
                    path = corrected_routes / 'derived_nearest/daily_grocery_evidence_union.parquet'
                elif code == 'parcel_pickup_wildberries_current':
                    path = bundle / 'routes_wb/nearest' / (code + '.parquet')
                elif code == 'parcel_pickup_yandex_current':
                    path = bundle / 'routes_yandex/nearest' / (code + '.parquet')
                else:
                    path = corrected_routes / 'nearest' / (code + '.parquet')
                    if not path.exists():
                        if code != 'medical_basic_primary':
                            raise FileNotFoundError('Corrected required layer is missing: ' + str(path))
                        path = bundle / 'routes/nearest' / (code + '.parquet')
                raw = pd.read_parquet(path)
                declared = set(raw.service_code.dropna())
                expected = {'daily_grocery_evidence_union'} if code == 'daily_grocery' else {code}
                if declared != expected:
                    raise ValueError('Layer contents have the wrong service: ' + str(path))
                canonical_cache[code] = canonical(raw, reference)
                inputs[str(path)] = digest(path)
            limit = 30. if family == 'medical_basic' else cfg['school_minutes'] if family == 'school' else cfg['retail_minutes']
            rule = ('dated_SP42_rural_primary_care_transport_scenario' if family == 'medical_basic' else
                    'dated_SP42_general_school_transport_stage_unknown_scenario' if family == 'school' else
                    'author_selected_car_minutes_sensitivity_not_regulation_or_empirical_trip_fit')
            frames.append(with_admission(canonical_cache[code], family, code, sid, limit, rule))
        edges = pd.concat(frames, ignore_index=True)
        tables, summary = build_centre_stars(edges, reference, endpoint_frame)
        target = output / sid
        target.mkdir(exist_ok=True)
        # Complete evidence is retained for the primary variant. Sensitivity
        # keeps the checked subsets and aggregate counts without duplicating
        # the same raw directions five times.
        main = sid == 'daily_20_school30_wb'
        if main:
            edges.to_parquet(target / 'daily_edges.parquet', index=False, compression='zstd')
        for name, frame in tables.items():
            if main or name in {'centre_stars', 'strict_three_core_stars', 'strict_three_core_memberships'}:
                frame.to_parquet(target / (name + '.parquet'), index=False, compression='zstd')
        summary['input_sha256'] = dict(inputs)
        summary['travel_limits_minutes'] = {f: 30. if f == 'medical_basic' else cfg['school_minutes'] if f == 'school' else cfg['retail_minutes'] for f in cfg['families']}
        (target / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        result[sid] = summary
        print(json.dumps({'scenario': sid, **{k: v for k, v in summary.items() if k not in {'input_sha256'}}}, ensure_ascii=False), flush=True)
        del tables, frames, edges
        gc.collect()
    for path, checksum in inputs.items():
        if digest(Path(path)) != checksum:
            raise RuntimeError('Input changed during construction: ' + path)
    manifest = {'source_inputs_unchanged': True, 'scenarios': result,
                'membership_rule': 'direct function-specific and same-centre cross-function support; no transitive closure',
                'not_a_complete_exclusive_sgrt_partition': True,
                'code_sha256': {p.name: digest(p) for p in [Path(__file__), Path(__file__).with_name('centre_stars.py'), Path(__file__).with_name('screens.py')]}}
    (output / 'summary.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--corrected-routes', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--endpoints', type=Path)
    p.add_argument('--scenarios', nargs='+', choices=sorted(SCENARIOS), default=['daily_20_school30_wb', 'daily_10_school15_wb', 'daily_30_school30_wb', 'core3_20_school30', 'daily_20_school30_yandex'])
    a = p.parse_args()
    run(a.bundle, a.corrected_routes, a.output, a.scenarios, a.endpoints)

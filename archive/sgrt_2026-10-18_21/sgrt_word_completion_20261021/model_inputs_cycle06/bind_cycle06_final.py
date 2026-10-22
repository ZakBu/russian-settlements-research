"""Bind an actual new provisional Ci without reusing old assignments or ranks."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''):
            h.update(b)
    return h.hexdigest()

def rel(p):
    return str(p.resolve().relative_to(REPO))

def accepted(review, subject_hashes):
    raw = review.read_text()
    obj = json.loads(raw)
    status = str(obj.get('status', ''))
    allowed = {'ACCEPTED', 'FINAL_MERGED_DATED2021_THEMATIC_INPUT_INDEPENDENTLY_ACCEPTED'}
    failed = obj.get('n_failed', obj.get('n_failed_checks'))
    if status not in allowed or failed != 0:
        raise ValueError('Review is not accepted: ' + str(review))
    if not all(h in raw for h in subject_hashes):
        raise ValueError('Review does not pin actual subject bytes: ' + str(review))

def run(a):
    import pandas as pd
    provisional = a.provisional_config.resolve()
    pc = json.loads(provisional.read_text())
    config = copy.deepcopy(pc)
    ci_dir = a.ci_directory.resolve()
    receipt = ci_dir/'receipt.json'
    ci = ci_dir/'word_ci_center_features.parquet'
    saved_mass = ci_dir/'fixed_own_mass_components.parquet'
    r = json.loads(receipt.read_text())
    if r['input_bytes_changed'] or r['own_mass_refit'] or r['provisional_iterations'] != 1:
        raise ValueError('The provisional source/fixed mass contract failed')
    if r['input_sha256'].get(str(provisional)) != sha(provisional):
        raise ValueError('Ci used a different source configuration')
    if r['selected_rural_volume_policy'] != pc['settlement_role_policy']['rural_volume']:
        raise ValueError('Rural bound changed')
    if r['variant'] != pc['cycle05_variant']:
        raise ValueError('Variant changed')
    for filename, digest in r['input_sha256'].items():
        if sha(Path(filename)) != digest:
            raise ValueError('Actual provisional input changed: ' + filename)
    matrix = REPO/pc['travel_manifest']
    snap = next(REPO/l['path'] for l in pc['layers'] if l.get('prefix') == 'road_')
    accepted(a.transport_review, [sha(matrix), sha(snap)])
    # Use only the final protocol's declarations, never old data/ranks/memberships.
    template_variant = 'baseline' if r['variant'] == 'source_geography_inclusive' else r['variant']
    template = json.loads((ROOT/'model_inputs_cycle05'/('config_'+template_variant+'_final.json')).read_text())
    thematic = next(copy.deepcopy(l) for l in template['layers'] if '/thematic2021/' in l['path'])
    thematic['path'] = rel(ROOT/'model_inputs_cycle05/thematic2021/settlement_thematic_features_2021.parquet')
    thematic['retain_evidence_suffix'] = False
    thematic['retain_prefixes'] = list(dict.fromkeys(thematic.get('retain_prefixes', [])+['ethnicity_']))
    accepted(a.thematic_review, [sha(REPO/thematic['path'])])
    projection = HERE/'nonchernozem_context_v1/settlement_nonchernozem_hypothesis_only.parquet'
    accepted(a.nonchernozem_review, [sha(projection)])
    zone = json.loads((HERE/'nonchernozem_context_v1/additive_nonmass_layer_stanza.json').read_text())
    zone_sidecars = zone.get('provenance_sidecars', [])
    if 'layer' in zone:
        zone = zone['layer']
    if zone.get('path') != rel(projection):
        raise ValueError('Unexpected nonmass projection')
    config['layers'] += [dict(path=rel(ci), key='id', prefix='wordci_', optional=False,
                              retain_prefixes=['word_', 'provisional_', 'normalized_', 'own_mass_',
                                               'historical_', 'rural_unit_', 'true_person_', 'person_']),
                         thematic, zone]
    for k in ['rank_index', 'rank_feature_columns', 'hierarchy_strength_column']:
        config[k] = copy.deepcopy(template[k])
    config['rank_index']['provisional_receipt_sha256'] = sha(receipt)
    config['rank_index']['fixed_own_mass_values_sha256'] = r['own_mass_values_sha256']
    config['rank_provisional_receipt'] = rel(receipt)
    config['required_input_columns'] = list(dict.fromkeys(config['required_input_columns']+['wordci_own_positive_mass']))
    config['provenance_sidecars'] = list(dict.fromkeys(config.get('provenance_sidecars', []) + zone_sidecars +
        [rel(p) for p in [receipt, a.transport_review, a.thematic_review, a.nonchernozem_review, Path(__file__)]]))
    x = pd.read_parquet(ci)
    mass = pd.read_parquet(saved_mass)
    expected_ids = set(mass.loc[mass.candidate_center.fillna(False), 'id'])
    if set(x.id) != expected_ids or len(x) != r['eligible_centers']:
        raise ValueError('Actual Ci does not cover exactly the eligible candidate identities')
    fingerprint = hashlib.sha256(pd.util.hash_pandas_object(mass[['id', 'own_positive_mass']], index=False).to_numpy().tobytes()).hexdigest()
    if fingerprint != r['own_mass_values_sha256']:
        raise ValueError('Saved mass differs from the actual provisional receipt fingerprint')
    if not x.id.is_unique or x.word_centrality_observed2021_frame_0_1.isna().any():
        raise ValueError('Missing or duplicate actual candidate Ci')
    z = x[['id', 'own_positive_mass']].merge(mass[['id', 'own_positive_mass']], on='id', validate='one_to_one', suffixes=('_Ci', '_fixed'))
    if not z.own_positive_mass_Ci.equals(z.own_positive_mass_fixed):
        raise ValueError('Ci changed fixed own mass')
    sys.path.insert(0, str(ROOT/'model'))
    import run_word_model_cycle06 as model
    current, watched = model.load_nodes(config)
    current_mass, components = model.build_mass(current, config)
    compare = [c for c in mass if c in ['id', 'own_positive_mass', 'n_observed_mass_blocks'] or c.endswith(('_raw', '_z'))]
    if not current_mass[compare].equals(mass[compare]):
        raise ValueError('Final supplementary evidence changed an actual own mass component')
    if not current_mass.candidate_center.equals(mass.candidate_center):
        raise ValueError('Final supplementary evidence changed candidate eligibility')
    config['cycle06_final_binding'] = dict(actual_Ci_sha256=sha(ci), actual_provisional_receipt_sha256=sha(receipt),
        provisional_config_sha256=sha(provisional), all_actual_Mi_components_identical=True,
        no_previous_memberships_or_ranks_reused=True, nonmass_nonchernozem_historical_hypothesis_only=True)
    out = a.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(status='BOUND_TO_ACTUAL_NEW_CI_AND_ACCEPTED_SOURCES', configuration=rel(out),
        configuration_sha256=sha(out), own_mass_components_compared=compare, candidate_count=int(current_mass.candidate_center.sum())), ensure_ascii=False))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ['provisional-config', 'ci-directory', 'transport-review', 'thematic-review', 'nonchernozem-review', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    run(p.parse_args())

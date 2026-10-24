#!/usr/bin/env python3
"""Check the source tables committed for the SGRT pilot. Does not download anything."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'sgrt' / 'sources'
ACCESS = {'downloaded', 'sample_only', 'metadata_only', 'blocked'}
STATUS = {'observed', 'proxy', 'unknown', 'confirmed_absent', 'not_applicable'}
EVIDENCE = {'observed_flow', 'normative_attachment', 'route'}


def read(name):
    with (SRC / name).open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    errors = []
    inventory = read('inventory.csv')
    if not inventory:
        errors.append('inventory is empty')
    for row in inventory:
        if row['access_status'] not in ACCESS:
            errors.append(f"bad access_status {row['source_id']}")
        if row['artifact_path'].startswith('/tmp/'):
            errors.append(f"temporary path left in {row['source_id']}")

    education = read('education_objects.csv')
    if len(education) != 831:
        errors.append(f'education rows {len(education)} != 831')
    if any(row['value_status'] == 'confirmed_absent' for row in education):
        errors.append('a listed school is marked confirmed_absent')
    if any(row['value_status'] not in STATUS for row in education):
        errors.append('education value_status outside the agreed set')

    divisions = read('healthcare_udmurtia_divisions.csv')
    faps = [row for row in divisions if row['service_order'] == 'fap']
    if len(divisions) != 2476 or len(faps) != 556:
        errors.append(f'Udmurtia divisions {len(divisions)}, FAPs {len(faps)}')
    if len({row['address_raw'] for row in faps}) != 556:
        errors.append('Udmurtia FAP addresses are not all distinct')

    vologda = read('healthcare_vologda_divisions.csv')
    if len(vologda) != 1967:
        errors.append(f'Vologda divisions {len(vologda)} != 1967')

    links = read('observed_links.csv')
    if len(links) != 617:
        errors.append(f'links {len(links)} != 617')
    if any(row['evidence_kind'] not in EVIDENCE for row in links):
        errors.append('unknown evidence kind')
    if any(row['evidence_kind'] == 'observed_flow' for row in links):
        errors.append('a link is marked as an observed flow')
    if any(row['value'] != '1' for row in links):
        errors.append('a link value is not the presence marker 1')
    sarapul = [row for row in links if row['source_id'] == 'udm_sarapul_prikaz_48_2025']
    if len(sarapul) != 86 or any(row['holdout'] != 'no' for row in sarapul):
        errors.append('Sarapul holdout split changed')
    if sum(row['holdout'] == 'yes' for row in links) != 531:
        errors.append('holdout count changed')

    cases = read('cases.csv')
    if len(cases) != 10 or sum(row['holdout'] == 'yes' for row in cases) != 8:
        errors.append('pilot cases changed')
    if not any('Долгодеревенское' in row['place_name'] for row in cases):
        errors.append('Dolgodeverenskoe case missing')

    if errors:
        print('\n'.join(errors))
        return 1
    print(f'ok inventory={len(inventory)} education=831 udmurtia_fap=556 links=617')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Verify and publish immutable zero-level results or the supplemental medical input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

REPOSITORY = 'ZakBu/russian-settlements-research'
RESULT_TAG = 'sgrt-zero-systems-20261025-v1'
MEDICAL_TAG = 'sgrt-zero-medical-inputs-20261025-v1'
MEDICAL_URL = 'http://www.sartfoms.ru/spravka/archives/2021/list/TERREESTRMO2021_31.12.2021.pdf'
MEDICAL_SHA256 = 'f8fca17deb75e86b711b3c18a15d909e7341b9baa53b3d93ae6f383835de5c6c'
MEDICAL_BYTES = 2151654
MEDICAL_NAME = 'TERREESTRMO2021_31.12.2021.pdf'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def gh(*args):
    return subprocess.check_output(['gh', *map(str, args)], text=True)


def verify(path, metadata):
    if path.stat().st_size != metadata['bytes'] or sha(path) != metadata['sha256']:
        raise ValueError('Asset differs from pinned metadata: ' + path.name)


def freeze_medical(built, source_commit):
    """Anonymous download of a fixed public PDF; never change an existing local snapshot."""
    if not re.fullmatch('[0-9a-fA-F]{40}', source_commit):
        raise ValueError('Complete source commit SHA required')
    built.mkdir(parents=True, exist_ok=True)
    path = built / MEDICAL_NAME
    metadata = {'bytes': MEDICAL_BYTES, 'sha256': MEDICAL_SHA256}
    if not path.exists():
        req = urllib.request.Request(MEDICAL_URL, headers={'User-Agent': 'sgrt-research/1'})
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read()
        if len(body) != MEDICAL_BYTES or hashlib.sha256(body).hexdigest() != MEDICAL_SHA256 or not body.startswith(b'%PDF-'):
            raise ValueError('Public medical PDF differs from fixed source; no asset written')
        path.write_bytes(body)
    verify(path, metadata)
    manifest = {'repository': REPOSITORY, 'release_tag': MEDICAL_TAG,
                'source_commit': source_commit, 'source_url': MEDICAL_URL,
                'source_reference_year': 2021, 'snapshot_label': '2021-12-31',
                'acquisition_is_not_reference_year': True,
                'scope': 'Saratov territorial compulsory medical insurance registry; historical supplemental evidence, not a national inventory',
                'assets': [{'asset': MEDICAL_NAME, **metadata}]}
    (built / 'medical_source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def verify_remote(release, files, expected, tag):
    for path in files:
        matches = [a for a in release['assets'] if a['name'] == path.name]
        if len(matches) != 1 or matches[0]['size'] != expected[path.name]['bytes']:
            raise ValueError('Remote asset missing, duplicated or wrong size: ' + path.name)
        digest = matches[0].get('digest')
        if digest:
            if digest != 'sha256:' + expected[path.name]['sha256']:
                raise ValueError('Remote asset SHA differs: ' + path.name)
        else:
            # Older GitHub responses may lack digest; verify bytes downloaded from the draft.
            with tempfile.TemporaryDirectory() as tmp:
                gh('release', 'download', tag, '--repo', REPOSITORY,
                   '--pattern', path.name, '--dir', tmp)
                verify(Path(tmp) / path.name, expected[path.name])


def publish(built, medical=False):
    built = Path(built)
    manifest_name = 'medical_source_manifest.json' if medical else 'zero_catalog.json'
    cat = json.loads((built / manifest_name).read_text())
    tag = MEDICAL_TAG if medical else RESULT_TAG
    if cat['release_tag'] != tag or cat['repository'] != REPOSITORY:
        raise ValueError('Unexpected publication target')
    if not re.fullmatch('[0-9a-fA-F]{40}', cat['source_commit']):
        raise ValueError('Complete source commit SHA required')
    names = [MEDICAL_NAME, manifest_name] if medical else ['zero-data.zip', 'zero_catalog.json', 'zero_atlas.pdf', 'preview.png']
    files = [built / name for name in names]
    for path in files:
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing or empty publication asset: ' + path.name)
    expected = {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files}
    pinned_name = MEDICAL_NAME if medical else 'zero-data.zip'
    declared = [a for a in cat['assets'] if a['asset'] == pinned_name]
    if len(declared) != 1:
        raise ValueError('Exactly one declared archive/source asset required')
    verify(built / pinned_name, declared[0])
    if medical:
        verify(built / MEDICAL_NAME, {'bytes': MEDICAL_BYTES, 'sha256': MEDICAL_SHA256})
        if cat['source_url'] != MEDICAL_URL:
            raise ValueError('Unexpected medical source URL')
    # Paginate so older published versions cannot disappear behind the first 100 results.
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{REPOSITORY}/releases?per_page=100'))
    matches = [r for page in pages for r in page if r['tag_name'] == tag]
    if len(matches) > 1:
        raise ValueError('Ambiguous release target')
    release = matches[0] if matches else None
    if release and not release['draft']:
        raise ValueError('Published version is immutable; choose a new version in code')
    body = ('Исторический реестр медицинских организаций Саратовской области на 31.12.2021; дополнительный источник с закреплённой контрольной суммой. '
            'Исходный национальный архив не изменяется.' if medical else
            'Нулевой уровень по повседневным услугам и ограниченные сценарии верхних объединений. '
            'Сохраняются неизвестность источников, различия операторов ПВЗ и годы наблюдений. '
            'Модельные направления не объявляются наблюдёнными поездками. Обзор: https://github.com/' + REPOSITORY + '/blob/main/sgrt/zero/README.md')
    body += '\n\nКод: ' + cat['source_commit']
    title = 'Дополнительный медицинский источник — Саратов, 2021' if medical else 'Россия: нулевой уровень и ограниченные верхние сценарии — 25.10.2026'
    metadata = built / 'publication_request.json'
    if release is None:
        metadata.write_text(json.dumps({'tag_name': tag, 'target_commitish': cat['source_commit'],
            'draft': True, 'make_latest': 'false', 'name': title, 'body': body}, ensure_ascii=False))
        release = json.loads(gh('api', '--method', 'POST', f'repos/{REPOSITORY}/releases', '--input', metadata))
    # Draft retries are allowed; no published release is ever overwritten.
    gh('release', 'upload', tag, *files, '--repo', REPOSITORY, '--clobber')
    current = json.loads(gh('api', f'repos/{REPOSITORY}/releases/{release["id"]}'))
    if not current['draft']:
        raise ValueError('Release became public during upload; refusing publication mutation')
    verify_remote(current, files, expected, tag)
    for path in files:
        verify(path, expected[path.name])
    metadata.write_text(json.dumps({'draft': False, 'make_latest': 'false', 'body': body}, ensure_ascii=False))
    gh('api', '--method', 'PATCH', f'repos/{REPOSITORY}/releases/{release["id"]}', '--input', metadata)
    result = {'url': f'https://github.com/{REPOSITORY}/releases/tag/{tag}', 'assets': expected}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--built', type=Path, required=True)
    parser.add_argument('--freeze-medical', action='store_true')
    parser.add_argument('--source-commit')
    args = parser.parse_args()
    if args.freeze_medical:
        freeze_medical(args.built, args.source_commit or '')
    publish(args.built, medical=args.freeze_medical)

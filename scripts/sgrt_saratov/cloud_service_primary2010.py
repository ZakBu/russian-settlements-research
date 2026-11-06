"""Publish a small, separate primary-2010 sensitivity companion."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import subprocess
import urllib.request
import zipfile
from scripts.sgrt_zero.cloud_common_systems import acquire
from scripts.sgrt_saratov.system_primary2010 import run

ROOT = Path(__file__).resolve().parents[2]
REPO = 'ZakBu/russian-settlements-research'
TAG = 'sgrt-saratov-service-systems-primary2010-20261106-v1'
PRIMARY = 'sgrt/saratov-fields20261029-v2/results/context_physical_official_primary2010/np_context.parquet'
PACK = ('primary2010_demographic_components.parquet', 'primary2010_demographic_profiles.parquet',
        'primary2010_profile_comparison.parquet', 'primary2010_member_evidence.parquet',
        'primary2010_summary.json')


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def publish(work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    producer = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit the companion producer before publishing')
    parent = json.loads((ROOT/'research_context/analysis_snapshots/saratov_service_systems_manifest_20261106.json').read_text())
    asset = next(a for a in parent['assets'] if a['asset'] == 'saratov-service-systems.zip')
    with urllib.request.urlopen(asset['url'], timeout=90) as response:
        raw = response.read()
    if len(raw) != asset['bytes'] or hashlib.sha256(raw).hexdigest() != asset['sha256']:
        raise ValueError('Original local-system release differs')
    baseline = work/'baseline'
    baseline.mkdir(exist_ok=True)
    names = {'membership.parquet': 'structure/system_members.parquet',
             'profiles.parquet': 'economy/system_demographic_profiles.parquet'}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for destination, member in names.items():
            (baseline/destination).write_bytes(z.read('saratov-service-systems/results/'+member))
    proof = acquire(ROOT/'data/saratov_fields_catalog_20261029_v2.json',
                    lambda p: p == PRIMARY, work/'input', work/'cache')
    output = work/'results'
    actual = run(baseline/'membership.parquet', baseline/'profiles.parquet',
                 work/'input'/PRIMARY, output)
    expected = json.loads((ROOT/'research_context/analysis_snapshots/saratov_service_systems_primary2010_local_20261106.json').read_text())
    if actual != expected:
        raise ValueError('Fresh primary-2010 sensitivity differs from the local result')
    write(output/'input_provenance.json', {'unchanged_parent_release': parent['release'],
        'parent_archive': asset, 'primary_2010_context': proof})
    archive = work/'saratov-service-systems-primary2010.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in (*PACK, 'input_provenance.json'):
            z.write(output/name, 'saratov-service-systems-primary2010/'+name)
    manifest = {'release': TAG, 'source_commit': producer,
        'parent_release_unchanged': parent['release'], 'assets': [{
            'asset': archive.name, 'bytes': archive.stat().st_size,
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'url': f'https://github.com/{REPO}/releases/download/{TAG}/'+archive.name}]}
    write(work/'manifest.json', manifest)
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPO, '--target', producer,
        '--title', 'Местные системы: отдельная проверка первичных чисел переписи 2010 года',
        '--notes', 'Малое дополнение к неизменённому выпуску местных систем. Пять школьных и три медицинских состава получают три первичных числа; тождество исторических территорий не установлено. Первичная база и прежние результаты сохранены.',
        str(archive), str(work/'manifest.json')], check=True)
    a = manifest['assets'][0]
    with urllib.request.urlopen(a['url'], timeout=90) as response:
        published = response.read()
    if len(published) != a['bytes'] or hashlib.sha256(published).hexdigest() != a['sha256']:
        raise ValueError('Public primary-2010 companion differs')
    write(ROOT/'research_context/analysis_snapshots/saratov_service_systems_primary2010_20261106.json', actual)
    write(ROOT/'research_context/analysis_snapshots/saratov_service_systems_primary2010_manifest_20261106.json', manifest)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    publish(p.parse_args().work)

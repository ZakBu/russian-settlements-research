"""Recompute fixed local service structures from small pinned Saratov inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import urllib.request
import zipfile
from scripts.sgrt_zero.cloud_common_systems import acquire
from scripts.sgrt_saratov.system_structure import run as structure_run
from scripts.sgrt_saratov.system_economy import run as economy_run
from scripts.sgrt_saratov.system_maps import run as maps_run
from scripts.sgrt_saratov.source_inventory import BOUNDARY_URL

ROOT = Path(__file__).resolve().parents[2]
TAG = 'sgrt-saratov-service-systems-20261106-v1'
REPOSITORY = 'ZakBu/russian-settlements-research'
PREFIX = 'sgrt/saratov-fields20261029-v2/results'
PDF_URL = 'https://g-64.ru/upload/iblock/8c9/381rqs2g1xo1uzmifb3oys3mwoztz3ly.pdf'
PDF_SHA = '9b5fcaadee7b125f817279fe1b0b693f938a97d7cc089c37eb8074cf2d67cdda'
INPUTS = frozenset({'fields/regional_roster.parquet',
    'physical_official/basic_centre_profiles.parquet',
    'physical_official/basic_centre_members.parquet',
    'physical_official/functional_links.parquet', 'organisation/point_maxima.parquet',
    'context_physical_official/np_context.parquet',
    'context_physical_official/municipal_agriculture_context.parquet'})


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def calculate(work, acquire_data=True):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    source, output = work/'input', work/'results'
    if acquire_data:
        catalogue = ROOT/'data/saratov_fields_catalog_20261029_v2.json'
        specs = json.loads(catalogue.read_text())['files']
        selected = {f['path'].split('/results/', 1)[1] for f in specs
                    if '/results/' in f['path'] and f['path'].split('/results/', 1)[1] in INPUTS}
        if selected != INPUTS:
            raise ValueError('Incomplete pinned input inventory')
        proof = acquire(catalogue, lambda p: p.startswith(PREFIX+'/') and
                        p[len(PREFIX)+1:] in INPUTS, source, work/'cache')
        write(work/'input_provenance.json', proof)
    boundary = work/'RUS-adm1.geojson'
    if not boundary.exists():
        with urllib.request.urlopen(BOUNDARY_URL, timeout=60) as response:
            boundary.write_bytes(response.read())
    result = structure_run(source/PREFIX,
        ROOT/'sgrt/saratov/documented_school_catchments_2025.csv', output/'structure',
        ROOT/'sgrt/saratov/documented_medical_frameworks_2025.csv')
    economy = economy_run(output/'structure/system_members.parquet',
        source/PREFIX/'context_physical_official/np_context.parquet',
        source/PREFIX/'context_physical_official/municipal_agriculture_context.parquet',
        output/'economy')
    maps = maps_run(output/'structure', source/PREFIX/'fields/regional_roster.parquet',
                    boundary, output/'maps')
    return {'structure': result, 'economy': economy, 'maps': maps}


def publish(work):
    work = Path(work)
    producer = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit the producer and extracted evidence before publication')
    actual = calculate(work)
    expected = json.loads((ROOT/'research_context/analysis_snapshots/saratov_service_systems_local_20261106.json').read_text())
    if actual != expected:
        raise ValueError('Focused repeat differs from the committed scientific summary')
    pdf = work/'programme2025.pdf'
    with urllib.request.urlopen(PDF_URL, timeout=90) as response:
        pdf.write_bytes(response.read())
    if pdf.stat().st_size != 1525126 or digest(pdf) != PDF_SHA:
        raise ValueError('Primary medical programme differs from the read source')
    archive = work/'saratov-service-systems.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted((work/'results').rglob('*')):
            if p.is_file() and p.suffix in {'.parquet', '.json', '.geojson'}:
                z.write(p, 'saratov-service-systems/'+str(p.relative_to(work)))
        z.write(work/'input_provenance.json', 'saratov-service-systems/input_provenance.json')
        z.write(pdf, 'saratov-service-systems/source_documents/programme2025.pdf')
        for name in ['documented_school_catchments_2025.csv', 'documented_medical_frameworks_2025.csv',
                     'medical_identity_overrides_20261106.csv']:
            z.write(ROOT/'sgrt/saratov'/name, 'saratov-service-systems/source_documents/'+name)
        z.write(ROOT/'sgrt/saratov/SERVICE_SYSTEMS_20261106.md', 'saratov-service-systems/README.md')
    paths = [archive, *sorted((work/'results/maps').glob('*.geojson'))]
    manifest = {'release': TAG, 'source_commit': producer, 'assets': []}
    for p in paths:
        manifest['assets'].append({'asset': p.name, 'bytes': p.stat().st_size,
            'sha256': digest(p), 'url': f'https://github.com/{REPOSITORY}/releases/download/{TAG}/'+p.name})
    write(work/'manifest.json', manifest)
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY,
        '--target', producer, '--title', 'Саратов: документированные местные системы и их функциональная структура',
        '--notes', 'Раздельные школьные и медицинские составы 2025 года, внутренние роли, демография и хозяйственный контекст. Не наблюдённые поездки и не универсальная иерархия. Прежние выпуски сохранены.',
        *map(str, paths), str(work/'manifest.json')], check=True)
    for a in manifest['assets']:
        with urllib.request.urlopen(a['url'], timeout=90) as response:
            raw = response.read()
        if len(raw) != a['bytes'] or hashlib.sha256(raw).hexdigest() != a['sha256']:
            raise ValueError('Public asset differs: '+a['asset'])
    write(ROOT/'research_context/analysis_snapshots/saratov_service_systems_20261106.json', actual)
    write(ROOT/'research_context/analysis_snapshots/saratov_service_systems_manifest_20261106.json', manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--calculate-only', action='store_true')
    parser.add_argument('--reuse-verified-local-inputs', action='store_true')
    args = parser.parse_args()
    if args.calculate_only:
        print(json.dumps(calculate(args.work, not args.reuse_verified_local_inputs), ensure_ascii=False, indent=2))
    else:
        publish(args.work)

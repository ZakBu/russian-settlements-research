"""Rebuild the focused domestic-route study and publish a small new release."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import urllib.request
import zipfile
from scripts.sgrt_zero.cloud_common_systems import acquire
from scripts.sgrt_saratov.source_inventory import BOUNDARY_URL
from scripts.sgrt_saratov.domestic_routes import run

ROOT=Path(__file__).resolve().parents[2]
TAG='sgrt-saratov-domestic-routes-20261104-v1'
REPOSITORY='ZakBu/russian-settlements-research'
EXPECTED=ROOT/'research_context/analysis_snapshots/saratov_domestic_routes_local_20261104.json'
PACK_FILES=('np_route_comparison.parquet','service_choice_margins.parquet',
    'service_choice_margin_summary.csv','target_certificates.csv','native_node_axis.parquet',
    'domestic_anchor_node_costs.npz','school_locality_route_checks.csv',
    'school_case_domestic_paths.geojson','summary.json','input_provenance.json','README.md')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def acquire_inputs(work):
    source=work/'input'
    old={'inputs/centres.csv','model/native_edges.parquet','model/road_arrivals.parquet','model/summary.json'}
    new={'fields/regional_roster.parquet','fields/regional_costs.npy',
        'physical_official/basic_centre_profiles.parquet','physical_official/functional_links.parquet'}
    proof=acquire(ROOT/'data/saratov_isochrones_catalog_20261028.json',
        lambda p:'/results/' in p and any(p.endswith('/'+n) for n in old),source,work/'cache')
    proof+=acquire(ROOT/'data/saratov_fields_catalog_20261029_v2.json',
        lambda p:'/results/' in p and any(p.endswith('/'+n) for n in new),source,work/'cache')
    boundary=work/'RUS-adm1.geojson'
    with urllib.request.urlopen(BOUNDARY_URL,timeout=60) as r:boundary.write_bytes(r.read())
    return source,boundary,proof


def control(actual):
    expected=json.loads(EXPECTED.read_text())
    keys=['native_segments','native_nodes','baseline_directed_arcs','domestic_directed_arcs',
        'certified_v2_matrix_cells_checked','preferred_candidate_axis','targets_requested',
        'external_pairs_compared','external_pairs_with_exact_domestic_cost',
        'distinct_origins_with_exact_domestic_cost','preferred_candidates_with_exact_domestic_cost',
        'changed_exact_domestic_pairs','school_disagreement_native_path_witnesses','pair_status_counts']
    for key in keys:
        if actual[key]!=expected[key]:raise ValueError('Local scientific result differs: '+key)
    if actual['maximum_certified_baseline_error_minutes']>1e-7:
        raise ValueError('Archived baseline fails the existing arithmetic tolerance')


def publish(work):
    producer=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('Commit producer before publishing')
    source,boundary,proof=acquire_inputs(work)
    output=work/'results';actual=run(source,boundary,output);control(actual)
    (output/'input_provenance.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    (output/'README.md').write_text((ROOT/'sgrt/saratov/DOMESTIC_ROUTES_20261104.md').read_text())
    archive=work/'saratov-domestic-routes.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in PACK_FILES:z.write(output/name,'saratov-domestic-routes/'+name)
    paths=[archive,output/'school_case_domestic_paths.geojson']
    manifest={'release':TAG,'source_commit':producer,'scope':actual['scope'],'assets':[]}
    for p in paths:
        manifest['assets'].append({'asset':p.name,'bytes':p.stat().st_size,'sha256':digest(p.read_bytes()),
            'url':f'https://github.com/{REPOSITORY}/releases/download/{TAG}/'+p.name})
    (work/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    subprocess.run(['gh','release','create',TAG,'--repo',REPOSITORY,'--target',producer,
        '--title','Саратов: проверенные российские пути и устойчивость выбора услуг',
        '--notes','Частичный точный пересчёт по исходным дорогам внутри контура России. Не наблюдённые поездки и не новая итоговая иерархия. Прежние выпуски сохранены.',
        *map(str,paths),str(work/'manifest.json')],check=True)
    for asset in manifest['assets']:
        with urllib.request.urlopen(asset['url'],timeout=90) as r:raw=r.read()
        if len(raw)!=asset['bytes'] or digest(raw)!=asset['sha256']:raise ValueError('Public asset differs')
    for name,data in [('saratov_domestic_routes_20261104.json',actual),('saratov_domestic_manifest_20261104.json',manifest)]:
        (ROOT/'research_context/analysis_snapshots'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True);publish(a.work)

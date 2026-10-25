"""Build an inspectable ledger of this targeted public-source search and acquisition."""
from pathlib import Path
from collections import Counter
import hashlib,json

ROOT=Path(__file__).resolve().parent
requests=[]
for file in sorted((ROOT/'raw').glob('*.request.json')):
    meta=json.loads(file.read_text())
    body=ROOT/meta['body']
    assert body.exists()and hashlib.sha256(body.read_bytes()).hexdigest()==meta['sha256']
    requests.append({'request_file':str(file.relative_to(ROOT)),**meta})
queries={'retrieved_on':'2026-10-24','scope':'Targeted search for Ozon2019–2025 object history; not exhaustive proof of absence',
    'prior_searches_read':['history_stage_20261024/network/search_manifest.json','national/ozon_acquisition.txt'],
    'new_directions':['GitHub delivery/logistics/geo/points repositories with checked trees and pinned actual data',
        'Wayback official /geo point pages and their embedded state/JSON-LD',
        'Wayback public partner-map JavaScript; derive production backend; then archived point-search JSON'],
    'requests_n':len(requests),'status_counts':{str(k):v for k,v in Counter(x.get('status')for x in requests).items()},
    'requests_and_saved_responses':requests,
    'web_search_queries':['ozon deliverypoints github','ozon pickupPoints json github','Ozon Rocket widget js',
        'active_points_Other.xlsx','Пункты приёма в регионах (ПВЗ)'],
    'limits':['GitHub current trees do not prove no historic data in uninspected commits.',
        'CDX105geoURLkeys/46point-likeURLs,2019–2025 filter,does not equal a complete catalogue.',
        'Transport SSL EOF failures occurred in a parallel page batch; bounded selective retries succeeded.',
        'Official point-search has two successful archived captures with different spatial extents and unknown original POST bodies.',
        'No national uniformly observed Ozon historical registry established.']}
(ROOT/'query_manifest.json').write_text(json.dumps(queries,ensure_ascii=False,indent=2))
normal=json.loads((ROOT/'normalization_summary.json').read_text())
api=[json.loads((ROOT/f'archived_api_summary_{date}.json').read_text())for date in ['20230319','20240609']]
manifest={'retrieved_on':'2026-10-24','primary_historical_acquisitions':api,
    'official_geo_page_evidence':normal,'archived_api_ID_continuity':json.loads((ROOT/'archived_api_current_ID_summary.json').read_text()),
    'current_source_was_read_only':True,
    'licence':'No explicit open-data redistribution licence established; raw source bodies retained locally, no publication performed.',
    'date_rules':['Archive capture date is a dated positive catalogue signal, never an opening date.',
        'Working-hours dates kept as embedded schedule dates, never publication/opening dates.',
        'XLSX core2025created/modified metadata kept separately; observation_date remains unknown.',
        'Git2026commit never substituted for2025observation.'],
    'key_files':[]}
for file in sorted(ROOT.glob('*')):
    if file.is_file()and file.name not in ['acquisition_manifest.json','query_manifest.json']:
        manifest['key_files'].append({'path':file.name,'bytes':file.stat().st_size,
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
(ROOT/'acquisition_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('PASS: request ledger and acquisition manifest built;',len(requests),'saved request/response receipts.')

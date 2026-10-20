#!/usr/bin/env python3
"""Bounded education-source checks; every run writes a new dated capture directory.

No CAPTCHA bypass, no inferred absence from a failed request, no automatic
promotion of geographical OSM candidates to accepted settlement links.
"""
from pathlib import Path
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import time
import urllib.parse
import urllib.request


def fetch(job, out):
    name, url, timeout = job
    start = time.time()
    result = dict(source_id=name, requested_url=url,
                  requested_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        split = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit((split.scheme, split.netloc,
              urllib.parse.quote(split.path, safe='/%'), split.query, split.fragment))
        req = urllib.request.Request(url, headers={'User-Agent': 'SGRT scholarly education provenance check'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(30 * 1024 * 1024)
            result.update(http_status=response.status, response_url=response.url,
                content_type=response.headers.get('Content-Type'), bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest())
        capture = out / f'{name}.response'
        capture.write_bytes(body)
        result.update(result='response_saved', file=capture.name)
        if name.startswith('overpass'):
            data = json.loads(body)
            result.update(elements=len(data.get('elements', [])), remark=data.get('remark'),
                osm_timestamp=data.get('osm3s', {}).get('timestamp_osm_base'),
                source_scope='OSM school locations_not_official_school_census')
    except Exception as exc:
        result.update(result='request_failed', error=repr(exc))
    result['seconds'] = round(time.time() - start, 3)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-overpass', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output or Path(__file__).resolve().parent / 'acquisition_runs' / datetime.datetime.now(
        datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True, exist_ok=False)
    jobs = [('rlic', 'https://islod.obrnadzor.gov.ru/rlic/', 18),
            ('bus', 'https://bus.gov.ru/', 18),
            ('nt2026', 'https://education-ntura.ru/прием-в-общеобразовательную-организ/', 18)]
    if not args.skip_overpass:
        q = '[out:json][timeout:40];nwr["amenity"="school"](41,19,83,180);out center tags;'
        for i, host in enumerate(['overpass-api.de', 'overpass.kumi.systems', 'overpass.private.coffee']):
            jobs.append((f'overpass_bbox_{i}', f'https://{host}/api/interpreter?' +
                         urllib.parse.urlencode({'data': q}), 48))
        (out / 'overpass_query.txt').write_text(q + '\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda j: fetch(j, out), jobs))
    (out / 'receipt.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

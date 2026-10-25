"""Inspect acquired primary author pages and the downloaded HSE thesis."""
from pathlib import Path
from html.parser import HTMLParser
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.urls.append(a['href'])


def main():
    manifest = []
    for file in ['melnichuk.html', 'kalinichev.html', 'kuksin.html']:
        p = OUT/file
        b = p.read_bytes()
        parser = Links()
        parser.feed(b.decode('utf-8', errors='replace'))
        candidates = [u for u in parser.urls if any(
            token in u.lower() for token in ['github', 'zenodo', 'getwork', 'download=', '.zip', '.csv']
        )]
        manifest.append({'file': file, 'sha256': hashlib.sha256(b).hexdigest(),
                         'attachment_candidates': candidates})
    file = OUT/'Kalinichev2025.docx'
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(file) as z:
        root = ET.fromstring(z.read('word/document.xml'))
        paras = [''.join(t.text or '' for t in e.findall('.//w:t', ns))
                 for e in root.findall('.//w:p', ns)]
        links = []
        for name in z.namelist():
            if name.endswith('.rels'):
                links.extend(e.attrib.get('Target') for e in ET.fromstring(z.read(name))
                             if e.attrib.get('TargetMode') == 'External')
    text = '\n'.join(paras)
    (OUT/'Kalinichev2025.txt').write_text(text)
    assert 'актуальную на январь 2025 года' in text
    assert '51 тысячи' in text
    assert '2 594' in text
    versions = json.loads((OUT/'zenodo_versions.json').read_text())
    records = versions['hits']['hits']
    files = [{'record': r['id'], 'created': r['created'],
              'files': [{'name': f['key'], 'bytes': f['size']} for f in r.get('files', [])]}
             for r in records]
    result = {
        'pages': manifest,
        'thesis': {
            'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
            'paragraphs': len(paras), 'external_links': links,
            'methods_read': 'sections2.1–2.2 and appendix inventory',
            'data_snapshot_as_reported': 'January2025',
            'data_provider_as_reported': 'WBCON',
            'reported_points': 'more than51000',
            'reported_municipalities': 2594,
            'raw_dataset_acquired': False,
            'caveat': 'Thesis object description says2024, actual methods specifyJanuary2025; covariates mainly2023.',
        },
        'zenodo_versions': files,
        'zenodo_raw_data_attachment_found': any(
            f['name'].lower().endswith(('.csv', '.parquet', '.zip', '.xlsx'))
            for r in files for f in r['files']
        ),
        'kuksin_figure': {
            'source_pdf_page': 9, 'printed_page': 202,
            'panel_labels': ['WB2021', 'Ozon2021', 'WB2023', 'Ozon2023', 'WB2025', 'Ozon2025'],
            'caption_period': '2020–2025',
            'point_data_recovered': False,
            'note': 'Published maps visually inspected; symbols are not geocoded object records.',
        },
        'outreach_sent': False,
    }
    assert not result['zenodo_raw_data_attachment_found']
    (OUT/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print('PASS: HSE actual January2025 source date; no raw table in checked Zenodo version; attachment inventory saved')


if __name__ == '__main__':
    main()

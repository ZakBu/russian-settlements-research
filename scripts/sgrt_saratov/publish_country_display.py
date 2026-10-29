"""Publish only the corrected country-clipped drawings, preserving v2 science.

One small release and one public byte check; no repeat of national calculations.
Requires GH_TOKEN in an authorized GitHub Actions worker for publication.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from scripts.sgrt_saratov.country_scope import load_russia, clip
from scripts.sgrt_saratov.source_inventory import BOUNDARY_URL

TAG = 'sgrt-saratov-russia-display-20261029-v1'
REPOSITORY = 'ZakBu/russian-settlements-research'


def write(path, doc):
    path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')


def download(url):
    with urllib.request.urlopen(url,timeout=60) as stream:
        return stream.read()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    producer=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise ValueError('Commit changes before publishing country drawings')
    boundary=out/'RUS-adm1.geojson';boundary.write_bytes(download(BOUNDARY_URL));mask=load_russia(boundary)
    datasets=json.loads(Path('web/content/datasets.json').read_text())
    source=[d for d in datasets if d['id'].endswith('20261029-v2') and d['url'].endswith('.geojson')]
    if len(source)!=13:raise ValueError('Expected thirteen immutable v2 map sources')
    manifest={'release':TAG,'source_commit':producer,'boundary_url':BOUNDARY_URL,
        'boundary_sha256':hashlib.sha256(boundary.read_bytes()).hexdigest(),
        'scope':'Only final drawing geometry changes. Old routing costs are not certified against foreign transit.',
        'numerical_outside_area_tolerance_deg2':1e-14,'assets':[]}
    for d in source:
        raw=download(d['url'])
        if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('Original map SHA differs: '+d['id'])
        doc,diagnostics=clip(json.loads(raw),mask)
        name=d['url'].rsplit('/',1)[-1];path=out/name
        path.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n')
        manifest['assets'].append({'asset':name,'original_dataset_id':d['id'],
            'original_sha256':d['sha256'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes':path.stat().st_size,'features':len(doc['features']),
            'removed_display_area_km2':sum(x['removed_display_area_km2'] for x in diagnostics)})
    write(out/'manifest.json',manifest)
    if not args.publish:return
    # Never replace an existing release or its assets.
    subprocess.run(['gh','release','create',TAG,'--repo',REPOSITORY,'--target',producer,
        '--title','Саратовский пилот: карты строго в контуре России',
        '--notes','Исправлены только геометрии отображения 13 слоёв. Исходные расчёты v2 сохранены. Зарубежный транзит в старых временах пока не проверен.',
        *[str(out/a['asset']) for a in manifest['assets']],str(out/'manifest.json')],check=True)
    for a in manifest['assets']+[{'asset':'manifest.json','sha256':hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()}]:
        raw=download(f'https://github.com/{REPOSITORY}/releases/download/{TAG}/'+a['asset'])
        if hashlib.sha256(raw).hexdigest()!=a['sha256']:raise ValueError('Public asset SHA differs')
    mapping={}
    for a in manifest['assets']:
        old=next(d for d in source if d['id']==a['original_dataset_id'])
        new={**old,'id':old['id']+'-russia-display-v1','release':TAG,
            'sourceCommit':producer,'sha256':a['sha256'],
            'url':f'https://github.com/{REPOSITORY}/releases/download/{TAG}/'+a['asset'],
            'limitations':old['limitations']+['Отображение обрезано по контуру России. Отсутствие зарубежного транзита в старых дорожных временах ещё не проверено.']}
        mapping[old['id']]=new['id'];datasets.append(new)
    write(Path('web/content/datasets.json'),datasets)
    def replace(value):
        if isinstance(value,str):
            if value in mapping:return mapping[value]
            for old,new in mapping.items():value=value.replace('[@data:'+old+']','[@data:'+new+']')
            return value
        if isinstance(value,list):return [replace(v) for v in value]
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        return value
    for category in ('layers','visuals','materials'):
        for path in Path('web/content',category).glob('*.json'):
            old=json.loads(path.read_text());new=replace(old)
            if new!=old:write(path,new)
    write(Path('research_context/analysis_snapshots/saratov_russia_display_20261029.json'),manifest)


if __name__ == '__main__':main()

#!/usr/bin/env python3
"""Publish a newly reproduced local study with the runner's ordinary GH_TOKEN."""
import argparse
import json
from pathlib import Path
import subprocess
from reproduce import digest

REPO='ZakBu/russian-settlements-research'


def gh(*args):
    return subprocess.check_output(['gh',*map(str,args)],text=True)


def publish(built):
    cat=json.loads((built/'local_catalog.json').read_text())
    tag=cat['release_tag']
    if tag!='sgrt-local-systems-20261024-v1' or cat['repository']!=REPO:raise ValueError('Unexpected publication target')
    archive=built/'local-systems-data.zip'
    if digest(archive)!=cat['assets'][0]['sha256']:raise ValueError('Archive SHA mismatch')
    releases=json.loads(gh('api',f'repos/{REPO}/releases?per_page=100'))
    release=next((r for r in releases if r['tag_name']==tag),None)
    body='Документированные локальные школьные и медицинские системы Учалинского района, дорожная доступность, демография, аграрный контекст и 205 работников юридического лица по ФНС. Полная многоуровневая система СГРТ пока не установлена.\n\nОбзор: https://github.com/'+REPO+'/blob/main/sgrt/local_systems/README.md\n\nКод расчёта: '+cat['source_commit']
    if release and not release['draft']:raise ValueError('Published release is immutable; choose a new version')
    if release is None:
        metadata=built/'create_release.json'
        metadata.write_text(json.dumps({'tag_name':tag,'target_commitish':cat['source_commit'],'draft':True,
            'name':'Локальные системы: школы, ФАП, аграрная база и работодатель — 24.10.2026','body':body},ensure_ascii=False))
        release=json.loads(gh('api','--method','POST',f'repos/{REPO}/releases','--input',metadata))
    files=[archive,built/'local_catalog.json',built/'local_systems_atlas.pdf',built/'local_system_preview.png']
    gh('release','upload',tag,*files,'--repo',REPO,'--clobber')
    current=json.loads(gh('api',f'repos/{REPO}/releases/{release["id"]}'))
    for path in files:
        asset=next(a for a in current['assets'] if a['name']==path.name)
        if asset['size']!=path.stat().st_size:raise ValueError('Remote size differs')
        if asset.get('digest') and asset['digest']!='sha256:'+digest(path):raise ValueError('Remote digest differs')
    metadata=built/'publish_release.json';metadata.write_text(json.dumps({'draft':False,'make_latest':'false','body':body},ensure_ascii=False))
    gh('api','--method','PATCH',f'repos/{REPO}/releases/{release["id"]}','--input',metadata)
    print(f'https://github.com/{REPO}/releases/tag/{tag}')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--built',type=Path,required=True)
    publish(p.parse_args().built)

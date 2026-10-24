#!/usr/bin/env python3
"""Publish immutable nationally computed research data with normal runner auth."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO='ZakBu/russian-settlements-research'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def gh(*args):return subprocess.check_output(['gh',*map(str,args)],text=True)


def publish(built):
    cat=json.loads((built/'mass_catalog.json').read_text());tag=cat['release_tag']
    if not re.fullmatch(r'sgrt-mass-local-systems-20261024-v\d+',tag) or cat['repository']!=REPO:raise ValueError('Unexpected publication target')
    archive=built/'mass-data.zip'
    if archive.stat().st_size!=cat['assets'][0]['bytes'] or sha(archive)!=cat['assets'][0]['sha256']:raise ValueError('Archive differs from catalogue')
    releases=json.loads(gh('api',f'repos/{REPO}/releases?per_page=100'))
    release=next((x for x in releases if x['tag_name']==tag),None)
    if release and not release['draft']:raise ValueError('Published data version is immutable')
    body='Массовый расчёт доступности и кандидатных локальных функциональных систем на пространственной базе 153 800 населённых пунктов. Учреждения разных порядков, фактические образовательные объекты, демография, муниципальное сельское хозяйство и частичная численность работников. Модельные связи не объявляются наблюдёнными поездками.\n\nОбзор: https://github.com/'+REPO+'/blob/main/sgrt/mass/README.md\nКод: '+cat['source_commit']
    if release is None:
        metadata=built/'create.json';metadata.write_text(json.dumps({'tag_name':tag,'target_commitish':cat['source_commit'],'draft':True,'name':'Россия: локальные функциональные системы и данные — 24.10.2026','body':body},ensure_ascii=False))
        release=json.loads(gh('api','--method','POST',f'repos/{REPO}/releases','--input',metadata))
    files=[archive,built/'mass_catalog.json',built/'mass_atlas.pdf',built/'preview.png']
    gh('release','upload',tag,*files,'--repo',REPO,'--clobber')
    current=json.loads(gh('api',f'repos/{REPO}/releases/{release["id"]}'))
    for path in files:
        found=next((x for x in current['assets'] if x['name']==path.name),None)
        if not found or found['size']!=path.stat().st_size:raise ValueError('Remote asset size differs')
        if found.get('digest') and found['digest']!='sha256:'+sha(path):raise ValueError('Remote asset SHA differs')
    metadata=built/'publish.json';metadata.write_text(json.dumps({'draft':False,'make_latest':'false','body':body},ensure_ascii=False))
    gh('api','--method','PATCH',f'repos/{REPO}/releases/{release["id"]}','--input',metadata)
    print(json.dumps({'url':f'https://github.com/{REPO}/releases/tag/{tag}','files':len(cat['files']),'archive_sha256':cat['assets'][0]['sha256']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--built',type=Path,required=True)
    publish(p.parse_args().built)

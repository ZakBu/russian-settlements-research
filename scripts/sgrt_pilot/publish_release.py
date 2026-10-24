#!/usr/bin/env python3
"""Publish newly reproduced pilot bytes using the runner's normal GitHub CLI.

Never replaces assets in a published release. No credentials are read or saved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = 'ZakBu/russian-settlements-research'


def gh(*args):
    return subprocess.check_output(['gh', *map(str,args)], text=True)


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def publish(built,tag):
    if not re.fullmatch(r'sgrt-pilot-\d{8}-v\d+',tag):raise ValueError('Unexpected pilot tag')
    cat=json.loads((built/'pilot_catalog.json').read_text())
    if cat['release_tag']!=tag or cat['repository']!=REPO:raise ValueError('Catalogue target mismatch')
    archive=built/'sgrt-pilot-data.zip';expected=cat['assets'][0]
    if archive.stat().st_size!=expected['bytes'] or sha256(archive)!=expected['sha256']:
        raise ValueError('Archive differs from newly generated catalogue')
    releases=json.loads(gh('api',f'repos/{REPO}/releases?per_page=100'))
    release=next((r for r in releases if r['tag_name']==tag),None)
    if not release or not release['draft']:raise ValueError('Expected unpublished pilot draft; refusing replacement')
    files=[archive,built/'pilot_catalog.json',built/'pilot_atlas.pdf']
    gh('release','upload',tag,*files,'--repo',REPO,'--clobber')
    release=json.loads(gh('api',f'repos/{REPO}/releases/{release["id"]}'))
    for path in files:
        remote=next((a for a in release['assets'] if a['name']==path.name),None)
        if not remote or remote['size']!=path.stat().st_size:raise ValueError('Release size mismatch')
        if remote.get('digest') and remote['digest']!='sha256:'+sha256(path):raise ValueError('Release digest mismatch')
    body={'draft':False,'make_latest':'false','body':release['body']}
    metadata=built/'publish.json';metadata.write_text(json.dumps(body,ensure_ascii=False))
    gh('api','--method','PATCH',f'repos/{REPO}/releases/{release["id"]}','--input',metadata)
    print(json.dumps({'release':f'https://github.com/{REPO}/releases/tag/{tag}',
                      'archive_sha256':expected['sha256'],'source_commit':cat['source_commit']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--built',type=Path,required=True);p.add_argument('--tag',required=True)
    a=p.parse_args();publish(a.built,a.tag)

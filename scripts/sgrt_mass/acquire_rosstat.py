#!/usr/bin/env python3
"""Preserve the pinned original Rosstat settlement workbook distribution.

This is a source snapshot, not a new analysis. The archive is never committed
to Git. A runner may publish it as a separate immutable source release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import urllib.request

URL='https://rosstat.gov.ru/storage/mediabank/stat.info_NP_2025.rar'
SHA='520b79e3a7a9263f89712df3715b7f1fe1b121055c8bf56d1d6d0835b13cf9e3'
TAG='sgrt-rosstat-settlement-books-2025-source-v1'
REPO='ZakBu/russian-settlements-research'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def gh(*args):
    return subprocess.check_output(['gh',*map(str,args)],text=True)


def acquire(out,publish=False):
    out.mkdir(parents=True,exist_ok=True);archive=out/'stat.info_NP_2025.rar'
    if not archive.exists() or digest(archive)!=SHA:
        temp=archive.with_suffix('.partial')
        code=subprocess.call(['curl','-fL','--retry','2','--max-time','180','-o',str(temp),URL])
        if code:
            # The public Rosstat endpoint has served an incomplete CA chain in
            # the runner. The exact independently pinned archive SHA remains
            # mandatory even for this narrowly scoped fallback.
            request=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(request,timeout=180,context=ssl._create_unverified_context()) as response,temp.open('wb') as target:
                while chunk:=response.read(4*1024*1024):target.write(chunk)
        if digest(temp)!=SHA:raise ValueError('Rosstat original archive SHA256 differs')
        temp.replace(archive)
    metadata={'source_id':'ROSSTAT_SETTLEMENT_BOOKS_2025','source_url':URL,'edition_year':2025,
              'value_reference_year':'inspect_each_workbook_header_not_inferred_from_filename',
              'bytes':archive.stat().st_size,'sha256':SHA,'release_tag':TAG,
              'purpose':'Frozen original settlement-level workbooks for independent parsing of school/preschool and employment data.'}
    manifest=out/'source_manifest.json';manifest.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    if publish:
        existing=next((x for x in json.loads(gh('api',f'repos/{REPO}/releases?per_page=100')) if x['tag_name']==TAG),None)
        if existing and not existing['draft']:
            found=next(a for a in existing['assets'] if a['name']==archive.name)
            if found['size']!=archive.stat().st_size or found.get('digest') not in [None,'sha256:'+SHA]:raise ValueError('Existing published source differs')
        else:
            if existing is None:
                body=out/'create.json';body.write_text(json.dumps({'tag_name':TAG,'draft':True,'name':'Первоисточник: поселенческие книги Росстата, издание2025','body':'Оригинальный архив Росстата с обязательной проверкой SHA256. Год наблюдения каждого показателя устанавливается по шапке книги; edition2025 не переносится автоматически на значения.'},ensure_ascii=False))
                existing=json.loads(gh('api','--method','POST',f'repos/{REPO}/releases','--input',body))
            gh('release','upload',TAG,archive,manifest,'--repo',REPO,'--clobber')
            body=out/'publish.json';body.write_text(json.dumps({'draft':False,'make_latest':'false'}))
            gh('api','--method','PATCH',f'repos/{REPO}/releases/{existing["id"]}','--input',body)
    print(json.dumps(metadata,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--publish',action='store_true')
    a=p.parse_args();acquire(a.output,a.publish)

#!/usr/bin/env python3
"""Freeze public, time-varying pickup inputs before the research computation."""
from __future__ import annotations
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

from commerce import acquire_yandex_public_widget
from city_context import acquire as acquire_cities, read_context

REPOSITORY='ZakBu/russian-settlements-research'
TAG='sgrt-zero-inputs-20261025-v1'
WB_URL='https://static-basket-01.wbbasket.ru/vol0/data/all-poo-fr-v11.json'
FUA_URL='https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_FUA_UCDB2015_GLOBE_R2019A/V1-0/GHS_FUA_UCDB2015_GLOBE_R2019A_54009_1K_V1_0.zip'
FUA_SHA='d54de59b82b8c4d64a710f90ccd554975a3be92233f14115ac154094c3549979'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def gh(*args):return subprocess.check_output(['gh',*map(str,args)],text=True)


def read_public(url):
    request=urllib.request.Request(url,headers={'User-Agent':'SGRT-Research/1.0 (public geographic research)'})
    with urllib.request.urlopen(request,timeout=120) as response:
        return response.read(),dict(http_status=response.status,content_type=response.headers.get('Content-Type'))


def capture(output,snapshot):
    output=Path(output);root=output/'source_inputs';root.mkdir(parents=True,exist_ok=True)
    raw,headers=read_public(WB_URL)
    data=json.loads(raw)
    if isinstance(data,list):ru=next(x['items'] for x in data if x.get('country')=='ru')
    elif isinstance(data,dict) and 'ru' in data:ru=data['ru']
    else:raise ValueError('Unrecognized Wildberries country source')
    if not ru:raise ValueError('Empty public Wildberries catalogue')
    with gzip.GzipFile(filename=str(root/'wildberries.json.gz'),mode='wb',mtime=0) as f:f.write(raw)
    wb=dict(source_id='WILDBERRIES_PUBLIC_MAP',url=WB_URL,acquisition_moscow=datetime.now(ZoneInfo('Europe/Moscow')).isoformat(),
        sha256_uncompressed=hashlib.sha256(raw).hexdigest(),publisher_ru_records=len(ru),
        declared_types_8_34=sum(x.get('typePoint') in [8,34] for x in ru),source_date_not_claimed=True,**headers)
    (root/'wildberries.metadata.json').write_text(json.dumps(wb,ensure_ascii=False,indent=2)+'\n')
    for operator in ['market_l4g','5post']:
        path,metadata=acquire_yandex_public_widget(root,snapshot,network_operator=operator)
        print(json.dumps({'operator':operator,'points':metadata['point_count'],'sha256':metadata['sha256']},ensure_ascii=False),flush=True)
    acquire_cities(root/'city_context');read_context(root/'city_context')
    fua,_=read_public(FUA_URL)
    if hashlib.sha256(fua).hexdigest()!=FUA_SHA:raise ValueError('Pinned JRC source differs')
    (root/'ghs_fua_2015.zip').write_bytes(fua)
    files={p.relative_to(root).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file()}
    manifest={'source_release_tag':TAG,'repository':REPOSITORY,'acquisition_moscow':datetime.now(ZoneInfo('Europe/Moscow')).isoformat(),
        'snapshot_label':snapshot,'contains_fresh_public_pickup_responses':True,'census_population_is_not_replaced':True,
        'files':files,'wildberries':wb,'external_urban_reference':{'url':FUA_URL,'sha256':FUA_SHA,'source_epoch':2015,'observed_commuting':False}}
    (root/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=output/'source-inputs.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():z.write(p,Path('source_inputs')/p.relative_to(root))
    manifest['archive']={'name':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size}
    (output/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def publish(output,manifest):
    output=Path(output)
    releases=json.loads(gh('api',f'repos/{REPOSITORY}/releases?per_page=100'))
    release=next((r for r in releases if r['tag_name']==TAG),None)
    if release and not release['draft']:raise ValueError('Published inputs are immutable')
    if release is None:
        p=output/'create.json';p.write_text(json.dumps({'tag_name':TAG,'target_commitish':'main','draft':True,
            'name':'Исходные публичные выгрузки для нулевого уровня — октябрь 2026'},ensure_ascii=False))
        release=json.loads(gh('api','--method','POST',f'repos/{REPOSITORY}/releases','--input',p))
    gh('release','upload',TAG,output/'source-inputs.zip',output/'source_manifest.json','--repo',REPOSITORY,'--clobber')
    remote=json.loads(gh('api',f'repos/{REPOSITORY}/releases/{release["id"]}'))
    for p in [output/'source-inputs.zip',output/'source_manifest.json']:
        asset=next((x for x in remote['assets'] if x['name']==p.name),None)
        if not asset or asset['size']!=p.stat().st_size:raise ValueError('Remote input asset differs')
        if asset.get('digest') and asset['digest']!='sha256:'+sha(p):raise ValueError('Remote input digest differs')
    p=output/'publish.json';p.write_text(json.dumps({'draft':False,'make_latest':'false',
        'body':'Фиксированные открытые ответы карт ПВЗ, исходные городские координаты и внешний модельный слой агломераций. Даты и SHA — в source_manifest.json. Снимок первоисточников сохраняется отдельно от результатов расчёта; база переписей не заменяется.'},ensure_ascii=False))
    gh('api','--method','PATCH',f'repos/{REPOSITORY}/releases/{release["id"]}','--input',p)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--snapshot',default='2026-10-25');p.add_argument('--publish',action='store_true');a=p.parse_args()
    manifest=capture(a.output,a.snapshot)
    if a.publish:publish(a.output,manifest)
    print(json.dumps({'tag':TAG,'archive':manifest['archive']},ensure_ascii=False))

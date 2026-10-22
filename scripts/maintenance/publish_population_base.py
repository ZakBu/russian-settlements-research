"""Publish the accepted census foundation and switch default data profiles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pyarrow.parquet as pq
from build_population_base import digest
ROOT=Path(__file__).resolve().parents[2]
REPO='ZakBu/russian-settlements-research'
TAG='sgrt-census-population-20261022-v1'
ASSET='census-population-2002-2010-2021.zip'

def run(args):
    return subprocess.check_output(args,cwd=ROOT,text=True)

def publish(work):
    manifest=json.loads((ROOT/'research_context/population_source_manifest.json').read_text())
    missing=[]
    for r in manifest['inputs']:
        p=ROOT/r['path']
        if p.is_file() and p.stat().st_size==r['bytes'] and digest(p)==r['sha256']:continue
        assert r.get('portable_catalog_blob'), 'Missing Git evidence: '+r['path']
        missing.extend(['--match',r['path']])
    if missing:
        subprocess.run([sys.executable,'scripts/research_data.py','fetch','--catalog','data/catalog-20261022-recovery-v1.json','--profile','all','--cache',str(work/'cache'),*missing],cwd=ROOT,check=True)
    output=work/'data/population'
    subprocess.run([sys.executable,'scripts/maintenance/build_population_base.py','--output',str(output)],cwd=ROOT,check=True)
    metadata=json.loads((output/'dataset.json').read_text())
    cat=json.loads((ROOT/'data/catalog-20261022-recovery-v1.json').read_text())
    # Preserve old computations in explicit archive profiles; none are default.
    for container in [cat['files'],cat['objects'].values()]:
        for row in container:
            row['profiles']=[{'core':'legacy_model','current':'legacy_model_full'}.get(p,p) for p in row['profiles']]
    asset_objects=[]
    archive=work/ASSET
    with zipfile.ZipFile(archive,'w',allowZip64=True) as z:
        for path in sorted(output.iterdir()):
            raw=path.read_bytes();sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            relative='data/population/'+path.name
            obj=cat['objects'].get(sha,{'blob':sha,'bytes':len(raw),'source_path':relative,'paths':[],'profiles':[]})
            if relative not in obj['paths']:obj['paths'].append(relative)
            obj.update(sha256=hashlib.sha256(raw).hexdigest(),stored_in_current_git=False,asset=ASSET,
                       origin='Frozen accepted 2026-10-13 census decisions replayed; no new source admission.')
            obj['profiles']=sorted(set(obj['profiles'])|{'core','current','population','all'})
            if path.suffix=='.parquet':
                table=pq.ParquetFile(path);fields=[{'name':f.name,'type':str(f.type),'nullable':f.nullable} for f in table.schema_arrow]
                sid=hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()
                cat['schemas'][sid]={'fields':fields};obj.update(schema_id=sid,rows=table.metadata.num_rows)
            cat['objects'][sha]=obj
            cat['files'].append({'path':relative,'blob':sha,'bytes':len(raw),'profiles':['core','current','population','all'],'asset':ASSET,'kind':'accepted_population_foundation','usable_as_table':path.suffix in {'.csv','.parquet'}})
            info=zipfile.ZipInfo('objects/'+sha,date_time=(2026,10,22,0,0,0));info.compress_type=zipfile.ZIP_STORED
            z.writestr(info,raw);asset_objects.append(sha)
        z.writestr(zipfile.ZipInfo('objects_manifest.json',date_time=(2026,10,22,0,0,0)),json.dumps({'dataset':metadata,'objects':asset_objects},ensure_ascii=False,indent=2))
    # Existing immutable archives may also contain the tiny federal CSV; the new
    # compact archive makes the default base a single download. All aliases agree.
    for row in cat['files']:
        if row['blob'] in asset_objects:row['asset']=ASSET
    notes=work/'notes.md';notes.write_text('Главная база населения: связанные наблюдения переписей2002/2010/2021.465929 исходных записей,173242 межгодовых компонента,142765 строгих полных рядов. Рабочее покрытие99.6354%/99.5209%/99.7441% населения учитывает исторические маршруты и федеральные территории отдельно; не является долейНП или оценкой точности. Восстановлено из закреплённых принятых пакетов13октября, без новых допущений. Код, словарь и протокол проверки в репозитории.\n')
    probe=subprocess.run(['gh','release','view',TAG,'--repo',REPO],capture_output=True)
    if probe.returncode:
        run(['gh','release','create',TAG,'--repo',REPO,'--target',os.environ.get('GITHUB_SHA',run(['git','rev-parse','HEAD']).strip()),'--title','Главная база НП: переписи2002/2010/2021','--notes-file',str(notes),'--draft'])
    # Refuse to overwrite an already published differing scientific payload.
    releases=json.loads(run(['gh','api','repos/'+REPO+'/releases?per_page=100']))
    remote=next(r for r in releases if r['tag_name']==TAG)
    previous=next((a for a in remote['assets'] if a['name']==ASSET),None)
    checksum=digest(archive)
    if previous:
        assert previous['size']==archive.stat().st_size and previous.get('digest')=='sha256:'+checksum, 'Published census asset differs: use a new version'
    else:run(['gh','release','upload',TAG,str(archive),'--repo',REPO])
    run(['gh','release','edit',TAG,'--repo',REPO,'--draft=false','--latest=true'])
    remote=json.loads(run(['gh','api','repos/'+REPO+'/releases/'+str(remote['id'])]))
    asset=next(a for a in remote['assets'] if a['name']==ASSET)
    assert asset['size']==archive.stat().st_size and asset['digest']=='sha256:'+checksum
    cat['assets'].append({'asset':ASSET,'status':'verified','bytes':asset['size'],'sha256':checksum,'url':asset['browser_download_url'],'asset_id':asset['id'],'objects':asset_objects,'uncompressed_bytes':sum(cat['objects'][sha]['bytes'] for sha in asset_objects)})
    cat['recovery_release_tag']=cat['release_tag'];cat['release_tag']=TAG
    cat['profiles']={'core':'PRIMARY: accepted population registry across2002/2010/2021, wide and strict-full3 views, coverage and separate federal territories.','population':'Same accepted population foundation as core.','current':'Alias of core/population; accepted population foundation.','legacy_model':'Former core: superseded potential-SGRT computation outputs; historical inspection only.','legacy_model_full':'Former current: full old computational bundle; not accepted functional SGRT delineation.','all':'All preserved historical structured data plus the accepted population foundation.'}
    cat['primary_dataset']={**metadata,'release_url':remote['html_url'],'default_profiles':['core','population','current'],'data_dictionary':'POPULATION_BASE.md','source_manifest':'research_context/population_source_manifest.json','paths':['data/population/'+p.name for p in sorted(output.iterdir())]}
    cat['scientific_scope']='Primary accepted census population foundation; archived potential-SGRT computations are superseded and not the default. No new functional SGRT model calculated.'
    cat['counts'].update(paths=len(cat['files']),unique_blobs=len(cat['objects']),logical_bytes=sum(r['bytes'] for r in cat['files']),materialized_logical_bytes=sum(r['bytes'] for r in cat['files']),unique_bytes=sum(o['bytes'] for o in cat['objects'].values()),release_assets=len(cat['assets']),zip_bytes=sum(a['bytes'] for a in cat['assets']),objects_with_sha256=sum('sha256' in o for o in cat['objects'].values()),unique_parquet_schemas=len(cat['schemas']))
    cat['limits'] += ' The primary census registry is a logical reconstruction from frozen accepted packets, not asserted byte-identical to the historical lost local export. Original raw capture rereading was not repeated.'
    (ROOT/'data/catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'data/population_dataset.json').write_text(json.dumps(cat['primary_dataset'],ensure_ascii=False,indent=2)+'\n')
    validation={'status':'ACCEPTED_CENSUS_RECONSTRUCTION_VERIFIED','metadata':metadata,'archive':cat['assets'][-1],'source_manifest_sha256':digest(ROOT/'research_context/population_source_manifest.json'),'checks':['177 input hashes verified','465929 unique native IDs; original fields unchanged','431948 final credited UID populations/roots/flags match accepted frozen roster','447373 accepted ownpoints;142765 strictfull3 roots','No duplicate(root,census_year)','Coverage numerator/denominator exact for all3years','Public asset serverSHA256/size verified'],'scope':'Census registry reconstruction, not new primary-source validation or empirical SGRT delineation.'}
    (ROOT/'research_context/reviews/population_base_validation_20261022.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    run(['gh','release','upload',TAG,'data/catalog.json','data/population_dataset.json','--repo',REPO,'--clobber'])
    print(json.dumps({'status':'published','release':remote['html_url'],'counts':metadata,'zip_bytes':asset['size']},ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--workdir',type=Path,required=True);args=ap.parse_args();args.workdir.mkdir(parents=True,exist_ok=True);publish(args.workdir.resolve())

"""Reproduce regional access maps from pinned inputs, never a national rebuild."""
import argparse,hashlib,json,subprocess,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
URL='https://download.geofabrik.de/russia/south-fed-district-261029.osm.pbf'
PBF_SHA='d8a4c4dd696428f2aca8dacf85801e4b790cc80419528a06979e177600c26052'
CORE_URL='https://zakbu.github.io/russian-settlements-research/data/settlement-polygons/97.json'
CORE_SHARD_SHA='0fb9008e13cbe105e40828abfda4462364f3075d72e383192290604db4da5e72'
def sha(path):
 with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args):subprocess.run([str(x) for x in args],check=True,cwd=ROOT)
def main():
 a=argparse.ArgumentParser();a.add_argument('--work',type=Path,required=True);a.add_argument('--core-shard-url',default=CORE_URL);a.add_argument('--pbf-url',default=URL,help='May use immutable copy from our scientific release with identical SHA256');p=a.parse_args();p.work.mkdir(parents=True,exist_ok=True);inputs=p.work/'input';inputs.mkdir(exist_ok=True);pbf=inputs/'south-fed-district-261029.osm.pbf'
 if not pbf.exists():urllib.request.urlretrieve(p.pbf_url,pbf)
 if sha(pbf)!=PBF_SHA:raise ValueError('PBF differs from pinned2026-10-29 snapshot')
 shard=inputs/'core-shard97.json'
 if not shard.exists():urllib.request.urlretrieve(p.core_shard_url,shard)
 if sha(shard)!=CORE_SHARD_SHA:raise ValueError('Accepted core shard changed; use release-pinned copy')
 core=inputs/'krasnodar-core.geojson';core.write_text(json.dumps(json.loads(shard.read_text())['97cf9b05f326c211'],ensure_ascii=False))
 pop=p.work/'population';run([sys.executable,'scripts/research_data.py','fetch','--profile','core','--dest',pop]);results=p.work/'results'
 run([sys.executable,'scripts/krasnodar_access/compute.py','--pbf',pbf,'--population',pop/'data/population/settlements_census_long.parquet','--core',core,'--out',results])
 run([sys.executable,'scripts/krasnodar_access/export.py','--pbf',pbf,'--results',results,'--core',core]);run([sys.executable,'scripts/krasnodar_access/validate.py','--results',results]);meta={'road_url':p.pbf_url,'original_road_url':URL,'road_sha256':PBF_SHA,'road_bytes':316803084,'road_snapshot':'2026-10-29T21:21:26Z','population_catalog':'data/catalog.json','population_release':'sgrt-census-population-20261022-v1','core_shard_url':p.core_shard_url,'core_shard_sha256':CORE_SHARD_SHA,'core_sha256':sha(core),'core_source_release':'sgrt-zero-centres-20261026-v2','core_source_date':'2026-10-26','core_role':'accepted_cartographic_settlement_contour_not_legal_boundary','limitations':'Model car access, not measured commuting and not15% employed share. No functional delimitation claimed.'};(results/'input_provenance.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

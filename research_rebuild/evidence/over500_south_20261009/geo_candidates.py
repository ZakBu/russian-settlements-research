import sys,re,json
from pathlib import Path
import pandas as pd
sys.path.insert(0,'research_rebuild/mass_linkage')
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
from verify_geokladr_snapshot import parse_dbf_header
from raw_okato_classifier import read_copy
SQL=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
cache=Path('/dev/shm/over500-20261009/raw_classifier.parquet')
if not cache.exists():read_copy(SQL).to_parquet(cache,index=False)
x=pd.read_parquet(cache);idx=x.set_index('historical_okato')['name'].to_dict();regionmap={'03':'краснодарский','07':'ставропольский','12':'астраханская','14':'белгородская','18':'волгоградская','20':'воронежская','26':'ингушетия','36':'самарская','42':'липецкая','56':'пензенская','60':'ростовская','63':'саратовская','68':'тамбовская','73':'ульяновская','79':'адыгея','82':'дагестан','83':'кабардино балкарская','85':'калмыкия','88':'марий эл','89':'мордовия','90':'северная осетия алания','96':'чеченская'}
def literal_keys(v):
 v=normalize(v); keys={v};m=re.search(r'^(.*?)\s*[\(\[]([^\)\]]+)[\)\]]$',v)
 if m:
  keys.add(m[1].strip())
  if normalize(m[2]) not in ['село']:keys.add(normalize(m[2]))
 out=set()
 for k in keys:
  k=re.sub(r'["«»]', '', k);k=re.sub(r'\bим\.', 'имени', k);k=re.sub(r'\bсовхоза\b','совхоз',k);k=re.sub(r'\bотделения\b','отделение',k);k=re.sub(r'\bплемзавода\b','племзавод',k);k=re.sub(r'(?<=\d)-(го|е|я|ой|й)\b','',k);k=re.sub(r'\b(первая|первое|первый)\b','1',k);k=re.sub(r'\b(вторая|второе|второй)\b','2',k);k=re.sub(r'\bстанция\b','',k);k=k.replace('ново-осетинская','новоосетинская');out.add(' '.join(k.split()))
 return out
x=x[x.is_settlement_raw.eq('t')&x.historical_okato.str.len().eq(11)].copy();x['region']=x.historical_okato.str[:2].map(regionmap);x['county']=x.historical_okato.str[:5].map(lambda v:county_key(idx[v+'000']) if v+'000' in idx else '');x['n']=x.name.map(literal_keys);x=x.explode('n');x['t']=x.status.map(lambda v:'поселок' if v=='поселок сельского типа' else normalize(v));r=pd.read_csv('research_rebuild/evidence/over500_south_20261009/dispositions.csv');obs=pd.read_parquet('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet');obs=obs[obs.source_record_id.isin(r.source_record_id)].copy();obs['county']=obs.district_raw.map(county_key);obs['n']=obs.name_norm.map(literal_keys);obs=obs.explode('n');obs['t']=obs.type_norm.map(normalize);matches=obs.merge(x,left_on=['region_norm','county','n','t'],right_on=['region','county','n','t']);codes=set(matches.historical_okato); found=[]
with DBF.open('rb') as f:
 h=f.read(32);hl=int.from_bytes(h[8:10],'little');f.seek(0);header=f.read(hl);n,hl,rl,fields=parse_dbf_header(header);fields={x['name']:x for x in fields}
 for no in range(1,n+1):
  raw=f.read(rl)
  def field(k):s=fields[k];return raw[s['offset']:s['offset']+s['width']].decode('cp1251').strip()
  code=''.join(field(k) for k in ['TER','KOD1','KOD2','KOD3'])
  if code in codes:
   found.append(dict(historical_okato=code,raw_record_1based=no,raw_byte_offset=hl+(no-1)*rl,deleted_marker=raw[:1].decode('ascii'),geo_name=field('NAME1'),geo_type=field('SCOKATO'),latitude=field('LAT'),longitude=field('LONG'),geo_status=field('STATUS')))
g=pd.DataFrame(found);m=matches.merge(g,on='historical_okato');m.to_csv('/dev/shm/over500-20261009/south_geo_matches.csv',index=False);print(m[['source_record_id','settlement_name','district_raw','historical_okato','name_raw','geo_name','geo_type','latitude_y','longitude_y']].to_string(index=False))

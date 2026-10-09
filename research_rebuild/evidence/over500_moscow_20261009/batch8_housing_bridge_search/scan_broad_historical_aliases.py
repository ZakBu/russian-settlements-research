from pathlib import Path
import struct,re,pandas as pd,json,hashlib
O=Path(__file__).parent;f=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');b=f.read_bytes();n,h,r=struct.unpack_from('<IHH',b,4);fields=[];off=1
for pos in range(32,h,32):
 if b[pos]==13:break
 desc=b[pos:pos+32];name=desc[:11].split(b'\0')[0].decode();w=desc[16];fields.append((name,off,w));off+=w
assert off==r;fd={name:(off,w)for name,off,w in fields};out=[];pattern=re.compile('луч|фабр|участ|холмогор|звенигор|юдин',re.I)
for i in range(n):
 block=b[h+i*r:h+(i+1)*r];a,w=fd['TER'];ter=block[a:a+w].decode('cp1251').strip()
 if ter!='46':continue
 a,w=fd['NAME1'];name=block[a:a+w].decode('cp1251').strip()
 if not pattern.search(name):continue
 row=dict(record_number_1based=i+1,byte_offset_0based=h+i*r,deleted=block[:1].decode(),source_path=str(f),source_sha256=hashlib.sha256(b).hexdigest())
 for name,off,w in fields:row[name]=block[off:off+w].decode('cp1251').strip()
 out.append(row)
pd.DataFrame(out).to_csv(O/'all_Moscow_rawGeo_broad_institutional_historical_alias_candidates.csv',index=False);(O/'rawGeo_broad_alias_source_manifest.json').write_text(json.dumps(dict(path=str(f),sha256=hashlib.sha256(b).hexdigest(),record_count=n,field_specs=fields,regex=pattern.pattern,candidate_only=True),ensure_ascii=False,indent=2));print(pd.DataFrame(out)[['record_number_1based','NAME1','KOD1','KOD2','KOD3','LONG','LAT','STATUS']].to_string(index=False))

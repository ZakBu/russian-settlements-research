from pathlib import Path
import struct,json,pandas as pd
O=Path(__file__).parent;f=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');terms=['усадьб','стройполимер','ткацк','бужанин','светлый','волоколамец','щекино','красный холм','поречье','петелин','клязьмин','совхоза','агрогород','пушкино','подольский','шеметово','кудиново','чапаева','луговая','гришенки','поповка','юдино']
with f.open('rb')as x:
 hd=x.read(32);num=struct.unpack('<I',hd[4:8])[0];hlen,rlen=struct.unpack('<HH',hd[8:12]);defs=[];off=1
 while x.tell()<hlen-1:
  z=x.read(32)
  if z[0]==13:break
  name=z[:11].split(b'\0')[0].decode();w=z[16];defs.append((name,off,w));off+=w
 x.seek(hlen);rows=[]
 for i in range(num):
  z=x.read(rlen)
  # MoscowTER46 or composedSCOKATO46, decode only likely namefield relevantbody.
  if b'46'not in z[:45]:continue
  fields={n:z[o:o+w].decode('cp1251',errors='replace').strip()for n,o,w in defs}
  if fields['TER']!='46':continue
  if not any(q in str(fields).lower().replace('ё','е')for q in terms):continue
  rows.append(dict(record_number_1based=i+1,byte_offset_0based=hlen+i*rlen,deleted=z[:1].decode(),**fields))
pd.DataFrame(rows).to_csv(O/'raw2011_geo_all_ownname_candidates.csv',index=False);print('definitions',defs);print(pd.DataFrame(rows).to_string(index=False))

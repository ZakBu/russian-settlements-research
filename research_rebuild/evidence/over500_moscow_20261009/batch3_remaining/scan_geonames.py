from pathlib import Path
import zipfile,json,pandas as pd,hashlib
O=Path(__file__).parent;f=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');terms=['Kholmogork','Abramtsev','Karavae','Karavay','Timokhov','Uchast','Luch','Zvenigorod','Alabino','Yudino','Minvnesh','Porokhov','Pogranich','Nikolsk','Kuznetsov','Ivanovsk','Zakharov','Zelenograd','Nekrasov','Vnukov','Vostochny'];rows=[]
with zipfile.ZipFile(f).open('RU.txt')as gf:
 for i,bb in enumerate(gf,1):
  cc=bb.decode().rstrip('\n').split('\t')
  if cc[6]=='P' and cc[10]in['47','48']and any(t.lower()in (cc[1]+'|'+cc[3]).lower()for t in terms):rows.append(dict(geonameid=cc[0],name=cc[1],ascii=cc[2],aliases=cc[3],latitude=cc[4],longitude=cc[5],feature_class=cc[6],feature_code=cc[7],admin1=cc[10],admin2=cc[11],population=cc[14],source_line=i,raw_cells_json=json.dumps(cc,ensure_ascii=False)))
pd.DataFrame(rows).to_csv(O/'GeoNames_Moscow_all_relevant_populated_objects.csv',index=False);(O/'GeoNames_source_pin.json').write_text(json.dumps(dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest()),indent=2));print(pd.DataFrame(rows)[pd.DataFrame(rows).name.str.contains('Kholm|Abram|Karav|Timok|Uchast|Luch|Alabino|Zvenigo|Yudino',case=False)][['geonameid','name','aliases','latitude','longitude','feature_code','admin1']].to_string(index=False))

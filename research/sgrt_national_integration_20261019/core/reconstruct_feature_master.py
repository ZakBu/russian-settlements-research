from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent
m=json.loads((r/'master_parts.json').read_text())
dest=r/m['output_name']
if dest.exists():
    if hashlib.sha256(dest.read_bytes()).hexdigest()!=m['sha256']:raise RuntimeError('Existing file differs; preserve it before reconstruction')
else:
    pieces=[]
    for part in m['parts']:
        data=(r/'feature_master.parquet.parts'/part['name']).read_bytes()
        assert len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256']
        pieces.append(data)
    data=b''.join(pieces)
    assert len(data)==m['bytes'] and hashlib.sha256(data).hexdigest()==m['sha256']
    dest.write_bytes(data)
print(str(dest),m['rows'],m['columns'],m['sha256'])

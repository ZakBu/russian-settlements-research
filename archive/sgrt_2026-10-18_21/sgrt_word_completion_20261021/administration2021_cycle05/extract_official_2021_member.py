"""Verify the durable official archive and its exact January 2021 member."""
from pathlib import Path
import hashlib
import zipfile
ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / 'sources/official_oktmo_archive_20220401.zip'
MEMBER = 'data-20210118-structure-20150128.csv'
def sha(data): return hashlib.sha256(data).hexdigest()
assert sha(ARCHIVE.read_bytes()) == '94ae8a04065dc807fffc1721892fe7bf63d318b8dc4096f1fb175019a413bdd7'
with zipfile.ZipFile(ARCHIVE) as z:
    assert z.testzip() is None
    matches = [n for n in z.namelist() if Path(n).name == MEMBER]
    assert len(matches) == 1, matches
    data = z.read(matches[0])
assert sha(data) == 'ac724b628c036d9aeb63b84f43f37ce326ebd18e7b5f77f223872257206aa867'
target = ROOT / 'sources' / MEMBER
if target.exists():
    assert target.read_bytes() == data
else:
    target.write_bytes(data)
print('PASS: archive CRCs and January 2021 member SHA256 verified')

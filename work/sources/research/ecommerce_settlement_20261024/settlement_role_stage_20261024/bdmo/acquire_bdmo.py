"""Acquire the pinned public BDMO retail section and extract only Parquet.

The ZIP also contains a5.4GB CSV; this script deliberately does not unpack it.
"""
from pathlib import Path
from datetime import datetime,timezone
import urllib.request
import hashlib
import json
import zipfile

OUT=Path(__file__).resolve().parent
RAW=OUT/'raw'
URL='https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20260928/by_section/data_section2_112_v20260928_section_file.zip'
EXPECTED='9fc60d9b0531f24dd80d0b58f6e2899571c4418e732c97a814a63e8b916a4c07'


def main():
    RAW.mkdir(exist_ok=True)
    target=RAW/'section2.zip'
    if not target.exists():
        with urllib.request.urlopen(URL,timeout=60) as response,target.open('wb') as out:
            for b in iter(lambda:response.read(1024*1024),b''):
                out.write(b)
    sha=hashlib.sha256(target.read_bytes()).hexdigest()
    assert sha==EXPECTED, 'Versioned public object changed; stop before mixing versions.'
    with zipfile.ZipFile(target) as z:
        infos=[{'name':i.filename,'bytes':i.file_size} for i in z.infolist()]
        names=[i.filename for i in z.infolist() if i.filename.endswith('.parquet')]
        assert len(names)==1
        filename=names[0]
        with z.open(filename) as source,(RAW/filename).open('wb') as out:
            for b in iter(lambda:source.read(1024*1024),b''):
                out.write(b)
    record={'url':URL,'source_page':'https://tochno.st/datasets/bdmo',
            'zip_sha256':sha,'zip_bytes':target.stat().st_size,
            'parquet_file':filename,'zip_entries':infos,
            'verification_utc':datetime.now(timezone.utc).isoformat(),
            'only_parquet_extracted':True,'tls_verification':True}
    (OUT/'replay_acquisition.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print('PASS pinned ZIP; only Parquet extracted')


if __name__=='__main__':
    main()

import io
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from scripts.sgrt_zero.acquire_geofabrik_places import restore_shard, package_sources


class Response(io.BytesIO):
    def __init__(self, data, status=206, etag='"frozen"'):
        super().__init__(data)
        self.status=status
        self.headers={'ETag':etag, 'Content-Range':f'bytes 0-{len(data)-1}/{len(data)}'}


class AcquireGeofabrikTests(unittest.TestCase):
    def fixture(self):
        stream=io.BytesIO(); raw=b'original-source-data'
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('test.dbf',raw)
        data=stream.getvalue()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info=z.getinfo('test.dbf')
        member={'name':'test.dbf','raw':len(raw),'crc':zlib.crc32(raw),
                'sha256':hashlib.sha256(raw).hexdigest(),'offset':0,'compressed':info.compress_size}
        return {'shard':'test','url':'https://example.invalid/source.zip','http_etag':'"frozen"',
                'selected_range':[0,len(data)-1],'members':[member]},data,raw

    def test_exact_pinned_transfer_and_verified_reuse(self):
        shard,data,raw=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with patch('urllib.request.urlopen',return_value=Response(data)) as request:
                restore_shard(shard,p)
                supplied=request.call_args.args[0]
                self.assertEqual(supplied.get_header('If-match'),'"frozen"')
                self.assertEqual(supplied.get_header('Range'),f'bytes=0-{len(data)-1}')
            self.assertEqual((p/'test/test.dbf').read_bytes(),raw)
            with patch('urllib.request.urlopen',side_effect=AssertionError('No network on exact reuse')):
                restore_shard(shard,p)

    def test_existing_source_corruption_is_not_overwritten(self):
        shard,data,raw=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'test').mkdir();(p/'test/test.dbf').write_bytes(b'wrong')
            with self.assertRaises(ValueError), patch('urllib.request.urlopen') as request:
                restore_shard(shard,p)
            request.assert_not_called()
            self.assertEqual((p/'test/test.dbf').read_bytes(),b'wrong')

    def test_full_archive_response_and_changed_etag_are_rejected(self):
        shard,data,_=self.fixture()
        for response in [Response(data,status=200),Response(data,etag='"changed"')]:
            with tempfile.TemporaryDirectory() as d, patch('urllib.request.urlopen',return_value=response):
                with self.assertRaises(ValueError):restore_shard(shard,Path(d))

    def test_wrong_member_sha_is_rejected_before_writing(self):
        shard,data,_=self.fixture();shard['members'][0]['sha256']='0'*64
        with tempfile.TemporaryDirectory() as d, patch('urllib.request.urlopen',return_value=Response(data)):
            with self.assertRaises(ValueError):restore_shard(shard,Path(d))
            self.assertFalse((Path(d)/'test/test.dbf').exists())

    def test_packaging_is_deterministic_and_does_not_duplicate_parquet(self):
        shard,_,raw=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'test').mkdir();(p/'test/test.dbf').write_bytes(raw)
            prov=p/'source.json';prov.write_text(json.dumps({'shards':[shard]}))
            a=package_sources({'shards':[shard]},prov,p,p/'a.zip')
            b=package_sources({'shards':[shard]},prov,p,p/'b.zip')
            self.assertEqual(a['sha256'],b['sha256'])
            self.assertFalse(a['includes_parquet'])


if __name__=='__main__': unittest.main()

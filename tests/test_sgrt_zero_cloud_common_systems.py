import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.cloud_common_systems import RemoteZip, RangeUnsupported, extract_checked, membership_site_frame, hierarchy_created_nodes
import pandas as pd


class Response(io.BytesIO):
    def __init__(self, data, status=206, content_range=None):
        super().__init__(data)
        self.status = status
        self.headers = {'Content-Range': content_range}


class CloudCommonSystemsTests(unittest.TestCase):
    def test_zip_reader_handles_backwards_seek_and_exact_ranges(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('objects/first', b'the known reference')
            archive.writestr('objects/second', b'a different object')
        data = output.getvalue(); calls = []
        def opener(request, timeout):
            start, end = map(int, request.headers['Range'].removeprefix('bytes=').split('-'))
            calls.append((start, end))
            return Response(data[start:end+1], content_range=f'bytes {start}-{end}/{len(data)}')
        remote = RemoteZip('https://example.test/pinned.zip', len(data), opener)
        with zipfile.ZipFile(remote) as archive:
            self.assertEqual(archive.read('objects/second'), b'a different object')
            self.assertEqual(archive.read('objects/first'), b'the known reference')
        self.assertGreater(len(calls), 2)
        self.assertTrue(any(a > c for (a,b),(c,d) in zip(calls,calls[1:])))

    def test_server_ignoring_range_never_silently_returns_full_archive(self):
        remote = RemoteZip('https://example.test/file', 10,
                           lambda request,timeout: Response(b'0123456789',status=200))
        with self.assertRaises(RangeUnsupported): remote.read(2)

    def test_wrong_content_range_or_short_response_stops_before_extraction(self):
        for response in [Response(b'abc',content_range='bytes 2-4/10'),
                         Response(b'a',content_range='bytes 0-2/10')]:
            remote = RemoteZip('https://example.test/file',10,lambda request,timeout:response)
            with self.assertRaises(ValueError): remote.read(3)

    def test_uncompressed_digest_and_safe_destination_are_required(self):
        content=b'original bytes'; spec={'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive: archive.writestr('object',content)
        with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
            target=Path(temp)
            result=extract_checked(archive,[('safe/reference.parquet','object',spec)],target)
            self.assertEqual((target/'safe/reference.parquet').read_bytes(),content)
            self.assertEqual(result[0]['sha256'],spec['sha256'])
            with self.assertRaises(ValueError):extract_checked(archive,[('../escape','object',spec)],target)
            wrong={**spec,'sha256':'0'*64}
            with self.assertRaises(ValueError):extract_checked(archive,[('bad','object',wrong)],target)
            self.assertFalse((target/'bad').exists())
            self.assertFalse((target/'bad.incoming').exists())

    def test_membership_map_keeps_anchors_and_does_not_turn_unknown_into_zero(self):
        members=pd.DataFrame(dict(origin_id=['anchor','partial','unknown','empty'],
            name=['Центр','Село','Деревня','Пустое'],lat=50.,lon=40.,
            unit_id=['u','u',None,None],
            membership_status=['registered_centre_preserved_as_self_anchor',
                               'one_known_function_primary_provisional',
                               'no_known_direction_not_no_dependency','no_known_direction_not_no_dependency'],
            positive_whole_origin=[False,True,True,False],is_registered_centre=[True,False,False,False]))
        centres=pd.DataFrame(dict(unit_id=['u'],name=['Центр']))
        points=membership_site_frame(members,centres)
        self.assertEqual(len(points),3)
        self.assertEqual(points.value.iloc[:2].tolist(),[1,4])
        self.assertTrue(pd.isna(points.value.iloc[2]))
        self.assertEqual(points.name.iloc[1],'Село → Центр')
        self.assertTrue(points.id.is_unique)
        members.loc[1,'unit_id']='unrecorded'
        with self.assertRaises(ValueError):membership_site_frame(members,centres)

    def test_map_depth_follows_creation_tree_not_functional_stage_number(self):
        first=pd.DataFrame(dict(unit_id=['a','zero'],new_territorial_merger=[True,False],
            effective_merge_depth=[1,0],stage_index=1,name=['Первый','Низовой'],lat=50.,lon=40.))
        second=pd.DataFrame(dict(unit_id=['a','b','c'],new_territorial_merger=[False,True,True],
            effective_merge_depth=[1,1,2],stage_index=2,name=['Первый','Другой','Старший'],lat=50.,lon=40.))
        result=hierarchy_created_nodes([first,second])
        self.assertEqual(result.unit_id.tolist(),['a','b','c'])
        self.assertEqual(result.effective_merge_depth.tolist(),[1,1,2])
        self.assertEqual(result.stage_index.tolist(),[1,2,2])
        changed=first.iloc[[0]].copy();changed['name']='Другой узел с тем же ID'
        with self.assertRaises(ValueError):hierarchy_created_nodes([first,changed])

    def test_duplicate_archive_member_is_not_silently_selected(self):
        output=io.BytesIO();content=b'bytes'
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('object',content)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                archive.writestr('object',content)
        spec={'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        with tempfile.TemporaryDirectory() as temp,zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
            with self.assertRaises(ValueError):extract_checked(archive,[('safe','object',spec)],Path(temp))


if __name__=='__main__':unittest.main()

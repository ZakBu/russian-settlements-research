"""Verify the handoff path using real ZIP archives and checksum failures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/research_data.py'


class DataTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.dest=self.root/'dest';self.dest.mkdir()
        self.data=b'byte-exact research evidence\n';self.blob=hashlib.sha1(b'blob '+str(len(self.data)).encode()+b'\0'+self.data).hexdigest()
        self.archive=self.root/'data.zip'
        with zipfile.ZipFile(self.archive,'w') as z:z.writestr('objects/'+self.blob,self.data)
        self.catalog={'schema':'sgrt.portable_data.v1','status':'verified_complete','files':[{'path':p,'blob':self.blob,'bytes':len(self.data),'profiles':['core']} for p in ['a.parquet','nested/b.parquet']], 'objects':{self.blob:{'sha256':hashlib.sha256(self.data).hexdigest(),'bytes':len(self.data),'asset':'data.zip'}},'assets':[{'asset':'data.zip','status':'verified','bytes':self.archive.stat().st_size,'url':self.archive.as_uri(),'sha256':hashlib.sha256(self.archive.read_bytes()).hexdigest(),'objects':[self.blob]}]}
        self.path=self.root/'catalog.json';self.path.write_text(json.dumps(self.catalog))

    def command(self,operation,*flags):
        return subprocess.run([sys.executable,str(SCRIPT),operation,'--catalog',str(self.path),'--dest',str(self.dest),'--cache',str(self.root/'cache'),*flags],capture_output=True,text=True)

    def test_fetch_verifies_and_aliases_are_independent(self):
        result=self.command('fetch');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.dest/'a.parquet').read_bytes(),self.data)
        self.assertFalse((self.root/'cache/data.zip').exists())
        self.assertEqual(list((self.root/'cache/objects').glob('*')),[])
        (self.dest/'a.parquet').write_bytes(b'changed')
        self.assertEqual((self.dest/'nested/b.parquet').read_bytes(),self.data)
        self.assertEqual(self.command('verify').returncode,1)
        self.assertEqual(self.command('fetch').returncode,1)
        self.assertEqual((self.dest/'a.parquet').read_bytes(),b'changed')

    def test_filter_materializes_only_selected_paths(self):
        result=self.command('fetch','--match','nested/*')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.dest/'a.parquet').exists())
        self.assertEqual((self.dest/'nested/b.parquet').read_bytes(),self.data)

    def named_archive(self, member, *, payload=None):
        """Use the released-result layout and a SHA256 object key, not Git SHA1."""
        old_blob = self.blob
        self.blob = hashlib.sha256(self.data).hexdigest()
        obj = self.catalog['objects'].pop(old_blob)
        obj['archive_member'] = member
        self.catalog['objects'][self.blob] = obj
        for row in self.catalog['files']:
            row['blob'] = self.blob
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr(member, self.data if payload is None else payload)
        self.catalog['assets'][0].update(objects=[self.blob], bytes=self.archive.stat().st_size,
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.path.write_text(json.dumps(self.catalog))

    def test_explicit_archive_member_fetches_and_verifies_sha256_object_key(self):
        member = 'sgrt/identity20261026/registry/level0_centres.csv'
        self.named_archive(member)
        result = self.command('fetch')
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in self.catalog['files']:
            self.assertEqual((self.dest / row['path']).read_bytes(), self.data)
        self.assertEqual(self.command('verify').returncode, 0)

    def test_explicit_member_payload_checksum_is_still_required(self):
        self.named_archive('sgrt/identity20261026/registry/level0_centres.csv', payload=b'wrong bytes')
        result = self.command('fetch')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Data object checksum mismatch', result.stderr)
        self.assertFalse((self.dest / 'a.parquet').exists())

    def test_unknown_member_does_not_fall_back_to_legacy_object(self):
        self.catalog['objects'][self.blob]['archive_member'] = 'sgrt/absent.parquet'
        self.path.write_text(json.dumps(self.catalog))
        result = self.command('fetch')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Archive member is absent or duplicated', result.stderr)
        self.assertFalse((self.dest / 'a.parquet').exists())

    def test_unsafe_archive_member_is_rejected_before_fetch(self):
        for member in ['../escape', '/absolute', 'root/../escape', 'root/./file',
                       'root//file', 'root\\file', 'C:/drive', 'root/file\0suffix', '', None]:
            with self.subTest(member=member):
                self.catalog['objects'][self.blob]['archive_member'] = member
                self.path.write_text(json.dumps(self.catalog))
                result = self.command('fetch')
                self.assertEqual(result.returncode, 1)
                self.assertIn('Unsafe archive member', result.stderr)
                self.assertFalse((self.dest / 'a.parquet').exists())
                self.assertFalse((self.root / 'cache/data.zip').exists())

    def test_explicit_member_cannot_hide_a_cache_object_path_escape(self):
        obj = self.catalog['objects'].pop(self.blob)
        obj['archive_member'] = 'objects/' + self.blob
        self.catalog['objects']['../outside'] = obj
        for row in self.catalog['files']:
            row['blob'] = '../outside'
        self.catalog['assets'][0]['objects'] = ['../outside']
        self.path.write_text(json.dumps(self.catalog))
        result = self.command('fetch')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Unsafe catalog path', result.stderr)
        self.assertFalse((self.dest / 'a.parquet').exists())

    def test_bad_archive_checksum_is_rejected(self):
        self.catalog['assets'][0]['sha256']='0'*64;self.path.write_text(json.dumps(self.catalog))
        self.assertEqual(self.command('fetch').returncode,1)
        self.assertFalse((self.dest/'a.parquet').exists())

    def test_interrupted_copy_is_resumable(self):
        spec=importlib.util.spec_from_file_location('data',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        source=self.root/'source';source.write_bytes(self.data);target=self.dest/'file.parquet'
        row=self.catalog['files'][0];obj=self.catalog['objects'][self.blob]
        def interrupted(src,dst):
            Path(dst).write_bytes(b'partial')
            raise OSError('simulated interrupted copy')
        with patch.object(module.shutil,'copyfile',side_effect=interrupted):
            with self.assertRaises(OSError):module.copy_verified(source,target,row,obj)
        self.assertFalse(target.exists())
        module.copy_verified(source,target,row,obj)
        self.assertEqual(target.read_bytes(),self.data)
        self.assertFalse(target.with_name(target.name+'.sgrt-part').exists())

    def test_path_escape_is_rejected(self):
        spec=importlib.util.spec_from_file_location('data',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaises(ValueError):module.destination(self.dest,'../outside')
        (self.dest/'link').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):module.destination(self.dest,'link/outside')


if __name__=='__main__':unittest.main()

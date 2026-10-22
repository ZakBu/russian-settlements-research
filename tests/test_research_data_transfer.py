"""Verify the handoff path using real ZIP archives and checksum failures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
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

    def command(self,operation):
        return subprocess.run([sys.executable,str(SCRIPT),operation,'--catalog',str(self.path),'--dest',str(self.dest),'--cache',str(self.root/'cache')],capture_output=True,text=True)

    def test_fetch_verifies_and_aliases_are_independent(self):
        result=self.command('fetch');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.dest/'a.parquet').read_bytes(),self.data)
        (self.dest/'a.parquet').write_bytes(b'changed')
        self.assertEqual((self.dest/'nested/b.parquet').read_bytes(),self.data)
        self.assertEqual(self.command('verify').returncode,1)
        self.assertEqual(self.command('fetch').returncode,1)
        self.assertEqual((self.dest/'a.parquet').read_bytes(),b'changed')

    def test_bad_archive_checksum_is_rejected(self):
        self.catalog['assets'][0]['sha256']='0'*64;self.path.write_text(json.dumps(self.catalog))
        self.assertEqual(self.command('fetch').returncode,1)
        self.assertFalse((self.dest/'a.parquet').exists())

    def test_path_escape_is_rejected(self):
        spec=importlib.util.spec_from_file_location('data',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaises(ValueError):module.destination(self.dest,'../outside')
        (self.dest/'link').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):module.destination(self.dest,'link/outside')


if __name__=='__main__':unittest.main()

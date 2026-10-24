import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts/sgrt_zero'))
spec=importlib.util.spec_from_file_location('zero_capture_tested',root/'scripts/sgrt_zero/capture_sources.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class InputCaptureTests(unittest.TestCase):
    def test_existing_published_source_release_is_immutable(self):
        with patch.object(module,'gh',return_value=json.dumps([{'tag_name':module.TAG,'draft':False,'id':1}])) as gh:
            with self.assertRaisesRegex(ValueError,'immutable'):module.publish(Path('/unused'),{})
            self.assertEqual(gh.call_count,1)

    def test_empty_public_country_catalogue_cannot_be_published_as_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module,'read_public',return_value=(b'[{"country":"ru","items":[]}]',{})):
                with self.assertRaisesRegex(ValueError,'Empty'):module.capture(Path(tmp),'2026-10-25')
            self.assertFalse((Path(tmp)/'source_manifest.json').exists())


if __name__=='__main__':unittest.main()

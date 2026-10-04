import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).with_name('stage_source_order_localdistrict_successor_20261004.py')
TREE = ast.parse(SCRIPT.read_text(encoding='utf-8'))
NODE = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'strip_repeated_type_prefix')
TYPE_RE = re.compile(r'^(?:село|с\.)\s*', re.I)
ENV = {'rawrules': SimpleNamespace(TYPE_RE=TYPE_RE)}
exec(compile(ast.Module(body=[NODE], type_ignores=[]), str(SCRIPT), 'exec'), ENV)
strip_name = ENV['strip_repeated_type_prefix']

class PrefixStripRegression(unittest.TestCase):
    def test_repeated_prefix_is_removed_with_compiled_type_regex(self):
        self.assertEqual(strip_name('село Березовка'), 'Березовка')
        self.assertEqual(strip_name('с. Березовка'), 'Березовка')

    def test_unprefixed_name_is_preserved(self):
        self.assertEqual(strip_name('Березовка'), 'Березовка')

    def test_nonmatching_prefix_like_text_is_preserved(self):
        self.assertEqual(strip_name('Сельхозтехника'), 'Сельхозтехника')

if __name__ == '__main__':
    unittest.main()

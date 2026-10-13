import gzip
import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.annual_module_recovery import _table_end, recover_module


class AnnualModuleRecoveryTest(unittest.TestCase):
    def test_table_scanner_ignores_braces_in_strings_and_dash_comments(self):
        sample = "{ 'literal } { -- still text', -- comment with } {\n {2021, 10, 'A'},\n}"
        self.assertEqual(sample[_table_end(sample, 0)], "}")

    def test_recover_nested_braces_dashes_year_and_source_note(self):
        source = """return { -- Module:Statistical/RUS-TST
['Источники'] = {
['2001A'] = {'{{cite web|title=A {nested} — test}}', 'на 1 января 2001 года'},
['2002B'] = {'reference -- literal', ''},
},
[123456] = { -- Берёзовка — тест
{2001, 42, '2001A'}, -- } comment must not close table
{2002, 0, '2002B'},
},
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RUS-TST.lua.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(source)
            rows, receipt = recover_module(path)

        self.assertEqual(receipt["recovered_assertion_count"], 2)
        self.assertEqual([row["observation_year"] for row in rows], [2001, 2002])
        self.assertEqual(rows[0]["population_value"], 42)
        self.assertEqual(rows[0]["source_text_raw"], "{{cite web|title=A {nested} — test}}")
        self.assertEqual(rows[0]["source_date_note_raw"], "на 1 января 2001 года")
        self.assertEqual(rows[1]["population_value"], 0)
        self.assertEqual(rows[1]["source_text_raw"], "reference -- literal")
        self.assertEqual(rows[0]["entry_title_comment_raw"], "Берёзовка — тест")
        self.assertEqual(rows[0]["exact_population_status"], "unknown")
        self.assertEqual(rows[0]["source_locator"], "line:3")
        self.assertEqual(rows[1]["source_locator"], "line:4")
        for row in rows:
            line = source.splitlines()[int(row["source_locator"].split(":")[1]) - 1]
            self.assertIn("['" + row["source_key_raw"] + "']", line)


if __name__ == "__main__":
    unittest.main()

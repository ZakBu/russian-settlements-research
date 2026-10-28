from pathlib import Path
import unittest
from scripts.sgrt_saratov.primary2010_independent_checks import independent_rows

TITLE='Численность населения по городским и сельским населенным пунктам на 14 октября 2010 г.'

class Primary2010Independent(unittest.TestCase):
    def parse(self,body):return independent_rows(TITLE+'\n'+body+'\nМетодологические пояснения')[0]

    def test_capital_kind_inside_name_and_adjacent_zero_rows(self):
        rows=self.parse('Питерский район\nВсего по району Сельское население 5 2 3 40,0 60,0 село Новое Село 5 2 3 40,0 60,0 хутор Пустой - - - - -cело Дальнее - - - - -')
        self.assertEqual([(r['kind'],r['name'],r['population']) for r in rows],[('село','Новое Село',5),('хутор','Пустой',0),('село','Дальнее',0)])

    def test_municipal_caption_is_not_an_extra_city(self):
        rows=self.parse('Городское поселение г. Городок 100 40 60 40,0 60,0 г. Городок 90 36 54 40,0 60,0')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['population'],90)

    def test_mikhailovsky_scope_annotation_is_preserved_as_raw_text(self):
        rows=self.parse('Городской округ поселок Михайловский (ЗАТО) поселок Михайловский (сельское население) 2328 1155 1173 49,6 50,4')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['name'],'Михайловский (сельское население)')

    def test_frozen_book_has_all_declared_np_counts_without_population_matching(self):
        text=(Path(__file__).resolve().parents[1]/'references/primary/saratov_census2010/reader_extract.txt').read_text()
        rows,held,_=independent_rows(text)
        self.assertEqual(len(rows),1823)
        self.assertEqual(sum(r['population']==0 for r in rows),95)
        self.assertEqual(sum(r['population'] for r in rows),2521892)
        self.assertTrue(all(r['male']+r['female']==r['population'] for r in rows))

if __name__=='__main__':unittest.main()

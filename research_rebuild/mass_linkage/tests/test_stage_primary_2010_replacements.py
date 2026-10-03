import unittest

from research_rebuild.mass_linkage.stage_primary_2010_replacements import (
    district_norm,
    int_population,
    classify_raw_table5_label,
    sheet_district_context,
)


class StagePrimary2010Tests(unittest.TestCase):
  def test_table5_population_section_suffix_is_not_part_of_district_key(self):
    self.assertEqual(district_norm('Усть-Лабинский район - сельское население'), 'усть-лабинский')
    self.assertEqual(district_norm('Усть-Лабинский район'), 'усть-лабинский')


  def test_secondary_district_context_uses_raw_explicit_then_raw_block_only(self):
    profile = {'district_cols': [1, 2]}
    raw_district, status = sheet_district_context(['', 'Район А', 'Район А'], profile, None)
    self.assertEqual((raw_district, status), ('Район А', 'explicit'))
    self.assertEqual(sheet_district_context(['', '', ''], profile, raw_district), (
        'Район А', 'inherited_raw_source_block'
    ))
    self.assertEqual(sheet_district_context(['', 'Район А', 'Район Б'], profile, None), (
        'Район А', 'conflicting_explicit_cells'
    ))


  def test_dash_is_never_a_population_zero(self):
    self.assertIsNone(int_population('-'))
    self.assertIsNone(int_population('—'))
    self.assertEqual(int_population(0), 0)

  def test_raw_table5_typed_locality_and_population_qualifier(self):
    self.assertEqual(classify_raw_table5_label('Городское население - г. Пример'), (True, 'Городское'))
    self.assertEqual(classify_raw_table5_label('Город и подчиненные населенные пункты'), (False, None))

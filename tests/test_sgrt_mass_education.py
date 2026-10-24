"""Regression checks for actual source-shape errors found in the national pass."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd
from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/sgrt_mass'))
from education import classify_primary_grain, parse_primary_books, primary_cell, osm_temporal_status, osm_lifecycle_reason


class EducationSourceRegression(unittest.TestCase):
    def test_operational_dates_use_precision_not_approximate_years(self):
        self.assertEqual(osm_temporal_status(None,'2016'),'ended_before_snapshot')
        self.assertEqual(osm_temporal_status('2022',None),'started_after_snapshot')
        self.assertEqual(osm_temporal_status('2021',None),'no_demonstrated_temporal_conflict')
        self.assertEqual(osm_temporal_status(None,'2021'),'no_demonstrated_temporal_conflict')
        self.assertEqual(osm_temporal_status('2021-02-01',None),'started_after_snapshot')
        self.assertEqual(osm_temporal_status(None,'2016?'),'unresolved_date_literal')
        self.assertEqual(osm_temporal_status(None,'2020-99-99'),'unresolved_date_literal')
        self.assertEqual(osm_temporal_status(None,'17.08.2019'),'ended_before_snapshot')
        self.assertEqual(osm_temporal_status(None,'31 Мая 2015'),'ended_before_snapshot')
        self.assertEqual(osm_temporal_status(None,'2016 г.'),'ended_before_snapshot')
        self.assertEqual(osm_temporal_status(None,'~2016'),'unresolved_date_literal')

    def test_lifecycle_does_not_infer_inactivity_from_building_or_name(self):
        self.assertEqual(osm_lifecycle_reason('{"abandoned":"yes","amenity":"kindergarten"}'),'abandoned=yes')
        self.assertEqual(osm_lifecycle_reason('{"building":"school","name":"Старая школа","disused":"no"}'),'')

    def workbook(self,root,rows):
        p=root/'stat.info_NP_2025'/'5. Приволжский федеральный округ'/'Самарская область'/'36-51_Образование'/'п. 39_Число мест_НП.xlsx'
        p.parent.mkdir(parents=True)
        wb=Workbook();ws=wb.active
        for row in rows:ws.append(row)
        wb.save(p)

    def test_total_and_doo_component_are_not_shifted_to_code_and_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.workbook(root,[['Число мест по населенным пунктам за 2025 год'],[None,None,'(единица)'],
                ['Населенные пункты','Всего','в том числе: в дошкольных организациях'],['пгт Безенчук',1113,934]])
            books,rows,cells,errors=parse_primary_books(root)
            self.assertEqual(errors,[])
            self.assertEqual(rows.source_oktmo.iloc[0],'')
            self.assertEqual(rows.observation_year.iloc[0],2025)
            self.assertEqual(cells[cells.is_total_column].reported_value.tolist(),[1113])
            self.assertEqual(cells[~cells.is_total_column].reported_value.tolist(),[934])

    def test_letter_header_preserves_real_code_before_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.workbook(root,[['Число мест по населенным пунктам за 2025 год'],[None,None,'Всего'],
                ['A','B',1],['пгт Безенчук','36604151051',1113]])
            _,rows,cells,errors=parse_primary_books(root)
            self.assertEqual(errors,[])
            self.assertEqual(rows.source_oktmo.iloc[0],'36604151051')
            self.assertEqual(cells.source_column.tolist(),['C'])
            self.assertEqual(cells.reported_value.tolist(),[1113])

    def test_city_aggregate_does_not_double_count_its_settlement(self):
        frame=pd.DataFrame([
            {'book_id':'same','source_excel_row':234,'settlement':'город Тула','raw_source_code':'','source_row_grain':'named_settlement','places':27212},
            {'book_id':'same','source_excel_row':235,'settlement':'г Тула','raw_source_code':'','source_row_grain':'named_settlement','places':23309}])
        result=classify_primary_grain(frame)
        kept=result[result.source_row_grain.eq('named_settlement')]
        self.assertEqual(kept.places.tolist(),[23309])
        self.assertEqual(result.source_row_grain.iloc[0],'city_aggregate')

    def test_standalone_full_city_word_is_not_automatically_aggregate(self):
        frame=pd.DataFrame([{'book_id':'one','source_excel_row':6,'settlement':'город Тула','raw_source_code':'70701000001','source_row_grain':'named_settlement'}])
        self.assertEqual(classify_primary_grain(frame).source_row_grain.iloc[0],'named_settlement')

    def test_suppressed_and_dash_never_turn_into_numeric_zero(self):
        for literal in ['...','…','…1)','-']:
            value,status=primary_cell(literal)
            self.assertTrue(pd.isna(value),literal)
            self.assertNotEqual(status,'observed')
        self.assertEqual(primary_cell(0),(0.0,'observed'))


if __name__=='__main__':unittest.main()

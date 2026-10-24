import datetime as dt
import importlib.util
from pathlib import Path
import unittest
import tempfile

p = Path(__file__).parents[1] / 'scripts/sgrt_zero/medical_regional_sources.py'
spec = importlib.util.spec_from_file_location('medical_regional_sources', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ASOF = dt.date(2026, 10, 23)

class FederalSourceTests(unittest.TestCase):
    def test_annual_end_is_valid_not_closed(self):
        assert m.validity({'DATEBEG':'01.01.2026','DATEEND':'31.12.2026'}, ASOF) == 'valid_at_snapshot'

    def test_future_and_ended_rows_not_current(self):
        assert m.validity({'DATEBEG':'01.01.2027','DATEEND':'31.12.2027'}, ASOF) == 'outside_snapshot_interval'
        assert m.validity({'DATEBEG':'01.01.2026','DATEEND':'22.10.2026'}, ASOF) == 'outside_snapshot_interval'

    def test_boundaries_inclusive(self):
        assert m.validity({'DATEBEG':'23.10.2026','DATEEND':'23.10.2026'}, ASOF) == 'valid_at_snapshot'

    def test_missing_invalid_dates_not_inferred(self):
        assert m.validity({'DATEBEG':None,'DATEEND':'31.12.2026'}, ASOF) == 'unknown_validity'
        assert m.validity({'DATEBEG':'31.02.2026','DATEEND':'31.12.2026'}, ASOF) == 'unknown_validity'
        assert m.validity({'DATEBEG':'31.12.2026','DATEEND':'01.01.2026'}, ASOF) == 'invalid_interval'

    def test_stream_preserves_literal_identity_and_cp1251(self):
        xml = '<?xml version="1.0" encoding="windows-1251"?><packet><zglv><DATE>23.10.2026</DATE></zglv><zap><UIDMO>01202600100</UIDMO><ADDR>с. Ёлкино</ADDR><EMPTY/></zap><zap><UIDMO>01202600100</UIDMO><ADDR>Другой адрес</ADDR></zap></packet>'
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name)/'test.xml'; path.write_bytes(xml.encode('cp1251'))
        rows = list(m.records(path))
        assert len(rows) == 2 and rows[0]['UIDMO'] == '01202600100'
        assert rows[0]['ADDR'] == 'с. Ёлкино' and rows[0]['EMPTY'] is None
        assert m.header(path) == {'DATE':'23.10.2026'}

class FederalJoinTests(unittest.TestCase):
    def setUp(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        def save(code, rows):
            pq.write_table(pa.Table.from_pylist(rows), self.root/f'{code}_current.parquet')
        self.save = save
        save('F032',[dict(UIDMO='01202600100',NAM_MOP='Organization',NAM_MOK='Org',SUBJ='Region',VID_MO='Hospital',OID_MO='oid',INN='inn',OGRN='ogrn',MCOD='010076',VEDPRI='0',DATEBEG='01.01.2026',DATEEND='31.12.2026',JURADDRESS_ADDRESS='LEGAL ADDRESS',D_BEGIN_OMS='01.01.2026',D_END='',NAME_E='')])
        save('F033',[dict(UIDSPMO='01202600100001005',NAM_SPMO='Subdivision',NAM_SK_SPMO='Sub',VID_SPMO='Profile',OID_SPMO='suboid',DATEBEG='01.01.2026',DATEEND='31.12.2026')])
        self.address=dict(UIDSPMO='01202600100001005',IDADDRESS='001',ADDR='REAL CARE ADDRESS',ADDR_GAR='gar',N_DOC='license',UIDMO='01202600100',DATEBEG='01.01.2026',DATEEND='31.12.2026')
        save('F038',[self.address])
        save('F034',[dict(UIDSPMO='01202600100001005',IDADDRESS=a,MPVID='12',MPUSL='3',MPROF='97',DATEBEG='01.01.2026',DATEEND='31.12.2026') for a in ['001','002']])

    def test_exact_pair_does_not_leak_or_substitute_legal_address(self):
        import pyarrow.parquet as pq
        audit=m.join_current(self.root)
        rows=pq.read_table(self.root/'care_site_profiles_current.parquet').to_pylist()
        by={r['IDADDRESS']:r for r in rows}
        self.assertEqual(audit['join_counts'],(2,2,1,1))
        self.assertEqual(by['001']['ADDR'],'REAL CARE ADDRESS')
        self.assertIsNone(by['002']['ADDR'])
        self.assertFalse(by['002']['care_address_exact_pair_join'])
        self.assertNotIn('JURADDRESS_ADDRESS',by['001'])

    def test_ambiguous_addresses_fail_before_cartesian_join(self):
        self.save('F038',[self.address,self.address])
        with self.assertRaisesRegex(ValueError,'ambiguous join keys'):
            m.join_current(self.root)

    def test_registry_version_can_be_current_after_oms_participation_ended(self):
        import pyarrow.parquet as pq
        rows=pq.read_table(self.root/'F032_current.parquet').to_pylist()
        rows[0]['D_END']='01.09.2026'; rows[0]['NAME_E']='source-reason-id'
        self.save('F032',rows)
        m.join_current(self.root)
        result=pq.read_table(self.root/'care_site_profiles_current.parquet').to_pylist()
        by={r['IDADDRESS']:r for r in result}
        self.assertTrue(by['001']['organization_oms_participation_ended_asof'])
        self.assertEqual(by['001']['organization_oms_participation_status'],'oms_participation_ended_not_closure')
        self.assertIsNone(by['002']['organization_oms_participation_ended_asof'])
